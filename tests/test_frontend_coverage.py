import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from botsky.app import Application
from botsky.adapters.local import LocalAdapter
from botsky.commands.registry import Registry
from botsky.commands.router import Router
from botsky.config import Settings
from botsky.contracts import Result
from botsky.frontend.catalog import Catalog
from botsky.frontend.contracts import ActionRequest
from botsky.store import context_of

ROUTES = {
    'control_call': 'calls', 'audiovisual.clip': 'calls', 'audiovisual.avatar': 'calls', 'audiovisual.agenda': 'calls',
    'manage_admin': 'admin', 'manage_minecraft': 'minecraft', 'manage_roulette': 'roulette',
    'manage_cooperacha': 'cooperacha', 'manage_pack': 'packs', 'manage_happy_hour': 'happy_hour',
    'manage_economy': 'economy', 'manage_blackjack': 'blackjack', 'make_prank': 'prank',
    'manage_drive': 'drive', 'manage_messages': 'messages', 'manage_conversation': 'bot',
    'conversation': 'ai', 'make_voice': 'ai', 'transcribe_media': 'ai',
    'manage_memory': 'organization', 'manage_reminder': 'organization', 'manage_school': 'organization',
    'manage_poll': 'organization', 'manage_pdf': 'pdf', 'download_media': 'downloads',
    'save_note': 'notes.save', 'find_notes': 'notes.find',
}


class CoverageTests(unittest.TestCase):
    def test_every_variant_dispatches_to_existing_backend(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(root, 'lab', 'local', 1, root/'db.sqlite', 999, 'owner', frozenset(), frozenset())
            app = Application(settings, clock=lambda: 1000, web=SimpleNamespace(enabled=True))
            receipt = app.admit(LocalAdapter(settings, lambda: 1000).incoming('fixture', 'owner', 'private', '/ayuda'))
            with ExitStack() as stack:
                stack.enter_context(patch('botsky.access.authorize', return_value=None))
                stack.enter_context(patch('botsky.domains.bot.gate', return_value=None))
                for module in set(ROUTES.values()):
                    target = 'botsky.domains.' + (module if '.' in module else module+'.execute')
                    stack.enter_context(patch(target, return_value=Result('ok', 'routed', module)))
                stack.enter_context(patch.object(app.jobs, 'reserve', return_value=Result('ok', 'routed', 'jobs')))
                stack.enter_context(patch.object(app.artifacts, 'resolve', return_value=['synthetic']))
                stack.enter_context(patch.object(app.store, 'follow', return_value=Result('ok', 'routed', 'follow')))
                stack.enter_context(patch('botsky.interactions.confirm', return_value=Result('ok', 'routed', 'confirm')))
                with app.store.transaction() as db:
                    row = db.execute('SELECT * FROM inbox WHERE id=?', (receipt.id,)).fetchone()
                    catalog = Catalog()
                    for spec in Registry().specs:
                        with self.subTest(path=spec.path):
                            parsed = Router().parse(spec.sample)
                            args = {k: list(v) if isinstance(v, tuple) else v for k,v in parsed.arguments.items() if k not in dict(spec.constants)}
                            native = catalog.build(ActionRequest('.'.join(spec.path), args))
                            result = app._handle(db, context_of(row), spec.path, json.loads(native.canonical()), 'synthetic-effect', 1000)
                            if spec.operation == 'core.help':
                                self.assertEqual(result.code, 'help')
                            else:
                                expected = ROUTES.get(spec.family, 'follow' if spec.operation in ('core.estado','core.cancelar') else 'confirm' if spec.operation == 'core.confirmar' else 'jobs')
                                self.assertEqual((result.code, result.text), ('routed', expected))

    def test_search_sources_required_and_enabled(self):
        catalog = Catalog()
        catalog.configure_downloads(SimpleNamespace(enabled=True, adult_sources_enabled=False))
        for args in [{'container':'mp4','query':'gatos'}, {'container':'mp4','query':'gatos','source':'vimeo'}, {'container':'mp4','query':'gatos','source':'adult'}]:
            with self.assertRaises(ValueError):
                catalog.build(ActionRequest('dl.buscar', args))
        catalog.build(ActionRequest('dl.buscar', {'container':'mp4','query':'gatos','source':'youtube'}))
        catalog.configure_downloads(None)
        with self.assertRaises(ValueError):
            catalog.build(ActionRequest('dl.buscar', {'container':'mp4','query':'gatos','source':'youtube'}))

    def test_editorial_and_variants_complete(self):
        catalog = Catalog()
        rows = catalog.describe()
        self.assertEqual(len(rows),155)
        self.assertEqual(len({r['action_key'] for r in rows}),155)
        self.assertTrue(all(r['description'] and 'references' in r for r in rows))
        self.assertEqual(len({r['operation'] for r in rows}),146)


class PermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_owner_action_keeps_backend_permission(self):
        import test_frontend_worker as fixtures
        from botsky.frontend.worker import run_one
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(root, 'lab', 'local', 1, root/'db.sqlite', 999, 'owner', frozenset({'alice'}), frozenset())
            frontend = fixtures.FrontendDouble()
            spec = next(s for s in Registry().specs if s.permission == 'owner' and s.family == 'manage_admin')
            parsed = Router().parse(spec.sample)
            frontend.decision = ActionRequest('.'.join(spec.path), {k:list(v) if isinstance(v,tuple) else v for k,v in parsed.arguments.items() if k not in dict(spec.constants)})
            app = Application(settings, clock=lambda:1000, frontend=frontend)
            receipt = app.receive(LocalAdapter(settings,lambda:1000).incoming('1','alice','private','administrar'))
            await run_one(app)
            with app.store.transaction() as db:
                result = Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?',(receipt.id,)).fetchone()[0])
            self.assertEqual(result.code,'owner_required')
            self.assertEqual(frontend.calls,1)
