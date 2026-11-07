import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from botsky.adapters.local import LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.frontend.catalog import Catalog
from botsky.frontend.contracts import ActionRequest, ReplyDecision
from botsky.frontend.worker import run_one


class FrontendDouble:
    def __init__(self):
        self.catalog = Catalog()
        self.calls = 0
        self.wait = None
        self.decision = ActionRequest('nota.guardar', {'text': '*pan* literal'})

    async def decide(self, text, context):
        self.calls += 1
        if self.wait:
            await self.wait.wait()
        return self.decision


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.now = 1794000000000
        self.settings = Settings(root, 'lab', 'local', 1, root/'private/test.sqlite3', self.now-1000,
                                 'owner', frozenset({'alice'}), frozenset({'group'}))
        self.frontend = FrontendDouble()
        self.app = Application(self.settings, clock=lambda: self.now, frontend=self.frontend)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)

    def incoming(self, mid='1', text='guarda pan', actor='alice', **kw):
        return self.adapter.incoming(mid, actor, 'private', text, **kw)

    def count(self, table):
        with self.app.store.transaction() as db:
            return db.execute('SELECT count(*) FROM '+table).fetchone()[0]

    async def test_note_duplicate_and_restart(self):
        incoming = self.incoming()
        receipt = self.app.receive(incoming)
        self.assertEqual(receipt.state, 'queued')
        self.assertEqual(self.frontend.calls, 0)
        self.assertEqual(self.count('notes'), 0)
        await run_one(self.app)
        self.assertEqual(self.count('notes'), 1)
        self.assertEqual(self.count('outbox'), 1)
        self.app.receive(incoming)
        self.app = Application(self.settings, clock=lambda: self.now, frontend=self.frontend)
        await run_one(self.app)
        self.app.recover()
        self.assertEqual(self.frontend.calls, 1)
        self.assertEqual(self.count('notes'), 1)

    async def test_cancel_late_response_and_command_not_blocked(self):
        receipt = self.app.receive(self.incoming())
        self.frontend.wait = asyncio.Event()
        task = asyncio.create_task(run_one(self.app))
        await asyncio.sleep(0)
        self.app.receive(self.incoming('2', '/nota guardar independiente'))
        self.assertEqual(self.count('notes'), 1)
        self.app.receive(self.incoming('3', '/cancelar '+receipt.id))
        self.frontend.wait.set()
        await task
        self.assertEqual(self.count('notes'), 1)

    async def test_reply_no_effect_and_unauthorized(self):
        self.frontend.decision = ReplyDecision('Hola')
        self.app.receive(self.incoming())
        await run_one(self.app)
        self.assertEqual(self.count('effects'), 0)
        self.assertEqual(self.count('outbox'), 1)
        self.app.receive(self.incoming('2', actor='stranger'))
        await run_one(self.app)
        self.assertEqual(self.frontend.calls, 1)

    async def test_interrupted_inference_not_retried(self):
        receipt = self.app.receive(self.incoming())
        with self.app.store.transaction() as db:
            db.execute("UPDATE frontend_tasks SET state='running',token='old',deadline_ms=? WHERE receipt_id=?", (self.now-1, receipt.id))
        await run_one(self.app)
        self.assertEqual(self.frontend.calls, 0)
        self.assertEqual(self.count('notes'), 0)
        self.assertEqual(self.count('outbox'), 1)

    async def test_conversion_real_fixture(self):
        from PIL import Image
        from pypdf import PdfReader
        from botsky.contracts import Result
        source = self.settings.root / 'synthetic.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        self.frontend.decision = ActionRequest('convertir', {'target': 'pdf'})
        incoming = self.app.attach_local(self.incoming(text='pasa esto a PDF'), source)
        receipt = self.app.receive(incoming)
        await run_one(self.app)
        await self.app.jobs.run_pending()
        with self.app.store.transaction() as db:
            result = Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?', (receipt.id,)).fetchone()[0])
        self.assertEqual(result.code, 'document_converted')
        self.assertEqual(len(PdfReader(self.app.artifacts.path(result.data['artifacts'][0])).pages), 1)
        self.assertEqual(self.frontend.calls, 1)

    async def test_restart_after_adoption_does_not_interpret(self):
        import json
        receipt = self.app.receive(self.incoming())
        parsed = self.frontend.catalog.build(self.frontend.decision)
        with self.app.store.transaction() as db:
            db.execute("UPDATE inbox SET command_json=?,path_json=?,permission=? WHERE id=?", (parsed.canonical(), json.dumps(parsed.spec.path), parsed.spec.permission, receipt.id))
            db.execute("UPDATE frontend_tasks SET state='adopted' WHERE receipt_id=?", (receipt.id,))
        self.app = Application(self.settings, clock=lambda: self.now, frontend=self.frontend)
        await run_one(self.app)
        self.app.recover()
        self.assertEqual(self.count('notes'), 1)
        self.assertEqual(self.frontend.calls, 0)

    async def test_pause_discards_even_after_resume(self):
        self.app.receive(self.incoming())
        self.frontend.wait = asyncio.Event()
        task = asyncio.create_task(run_one(self.app))
        await asyncio.sleep(0)
        from botsky.commands.registry import Registry
        pause = next(s for s in Registry().specs if s.family == 'manage_conversation' and s.original_action == 'pause')
        resume = next(s for s in Registry().specs if s.family == 'manage_conversation' and s.original_action == 'resume')
        self.app.receive(self.incoming('2', pause.sample, actor='owner'))
        self.app.receive(self.incoming('3', resume.sample, actor='owner'))
        self.frontend.wait.set()
        await task
        self.assertEqual(self.count('notes'), 0)
