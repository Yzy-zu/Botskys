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

    async def test_drive_wait_closed_by_natural_forget_and_other_action_uploads_zero_and_active_wait_uploads_once(self):
        from types import SimpleNamespace
        from PIL import Image
        from botsky.adapters.local import CollectingTransport
        from botsky.frontend.contracts import NoActionDecision

        class StubDrive:
            available = True
            folder_id = 'folder-1'

            def __init__(self):
                self.uploads = []

            async def folder(self):
                return self.folder_id

            async def generate_id(self):
                return f'remote-{len(self.uploads) + 1}'

            async def upload_file(self, remote_id, name, mime, path, *, scope_key):
                self.uploads.append((remote_id, name, mime, scope_key, path.read_bytes()))
                return SimpleNamespace(
                    id=remote_id,
                    name=name,
                    web_view_link=f'https://drive.google.com/file/d/{remote_id}/view',
                )

        drive = StubDrive()
        self.app.drive = drive
        sample_file = self.settings.root / 'drive_sample.png'
        Image.new('RGB', (16, 16), 'blue').save(sample_file)

        # Caso 1: «ya no, olvídalo» tras /drive guardar sin adjunto -> siguiente adjunto sin texto = 0 subidas
        wait1 = self.app.receive(self.incoming('w1', '/drive guardar'))
        self.assertEqual(wait1.result.code, 'attachment_required')
        self.app.deliver(wait1.id, CollectingTransport())
        self.frontend.decision = NoActionDecision('usuario desistió')
        forget = self.app.receive(self.incoming('w2', 'ya no, olvídalo'))
        await run_one(self.app)
        self.app.deliver(forget.id, CollectingTransport())
        att1 = self.app.attach_local(self.incoming('w3', ''), sample_file)
        res1 = self.app.receive(att1)
        self.assertEqual(res1.state, 'ignored')
        await self.app.jobs.run_pending()
        self.assertEqual(len(drive.uploads), 0)

        # Caso 2: «mejor guarda la nota pan» tras /drive guardar sin adjunto -> siguiente adjunto sin texto = 0 subidas
        wait2 = self.app.receive(self.incoming('w4', '/drive guardar'))
        self.assertEqual(wait2.result.code, 'attachment_required')
        self.app.deliver(wait2.id, CollectingTransport())
        self.frontend.decision = ActionRequest('nota.guardar', {'text': 'pan'})
        better_note = self.app.receive(self.incoming('w5', 'mejor guarda la nota pan'))
        await run_one(self.app)
        self.app.deliver(better_note.id, CollectingTransport())
        self.assertEqual(self.count('notes'), 1)
        att2 = self.app.attach_local(self.incoming('w6', ''), sample_file)
        res2 = self.app.receive(att2)
        self.assertEqual(res2.state, 'ignored')
        await self.app.jobs.run_pending()
        self.assertEqual(len(drive.uploads), 0)

        # Caso 3: con la espera vigente -> el siguiente adjunto sin texto se sube una vez
        wait3 = self.app.receive(self.incoming('w7', '/drive guardar'))
        self.assertEqual(wait3.result.code, 'attachment_required')
        self.app.deliver(wait3.id, CollectingTransport())
        att3 = self.app.attach_local(self.incoming('w8', ''), sample_file)
        res3 = self.app.receive(att3)
        self.assertEqual(res3.result.code, 'job_queued')
        await self.app.jobs.run_pending()
        self.assertEqual(len(drive.uploads), 1)

    async def test_turn_order_per_person_and_chat_while_other_chats_advance(self):
        from dataclasses import replace
        from botsky.adapters.local import LocalAdapter
        from botsky.contracts import Result

        self.settings = replace(self.settings, friends=frozenset({'alice', 'bob'}))
        self.app.settings = self.settings
        pan_entered = asyncio.Event()
        release_pan = asyncio.Event()
        bob_finished = asyncio.Event()

        class ControlledFrontend:
            def __init__(self, catalog):
                self.catalog = catalog

            async def decide(self, text, context):
                if text == 'guarda la nota pan':
                    pan_entered.set()
                    await release_pan.wait()
                    return ActionRequest('nota.guardar', {'text': 'pan'})
                if text == 'muéstrame mis notas':
                    return ActionRequest('notas', {})
                return ReplyDecision('Hola Bob')

        self.app.frontend = ControlledFrontend(self.frontend.catalog)
        t1 = self.app.receive(self.incoming('ord-1', 'guarda la nota pan', actor='alice'))
        t2 = self.app.receive(self.incoming('ord-2', 'muéstrame mis notas', actor='alice'))

        worker1 = asyncio.create_task(run_one(self.app))
        await asyncio.wait_for(pan_entered.wait(), 2)
        worker2 = asyncio.create_task(run_one(self.app))
        await asyncio.sleep(0.02)
        self.assertFalse(worker2.done())

        # Mientras el chat de alice espera, otro chat (bob) avanza sin bloquearse
        bob_incoming = LocalAdapter(self.settings, lambda: self.now).incoming('ord-bob', 'bob', 'private-bob', 'hola botsky')
        t_bob = self.app.receive(bob_incoming)
        worker_bob = asyncio.create_task(run_one(self.app))
        await asyncio.wait_for(worker_bob, 2)
        bob_finished.set()
        self.assertTrue(bob_finished.is_set())
        with self.app.store.transaction() as db:
            bob_res = Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?', (t_bob.id,)).fetchone()[0])
        self.assertEqual(bob_res.text, 'Hola Bob')

        # Liberar «guarda la nota pan»: debe completarse antes de «muéstrame mis notas»
        release_pan.set()
        await asyncio.wait_for(asyncio.gather(worker1, worker2), 2)
        with self.app.store.transaction() as db:
            notes_res = Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?', (t2.id,)).fetchone()[0])
        self.assertEqual(notes_res.code, 'notes_found')
        self.assertIn('pan', notes_res.text)
        self.assertEqual([item['text'] for item in notes_res.data['items']], ['pan'])
