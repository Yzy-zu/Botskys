import json

import unittest
import test_frontend_worker as worker_tests
from botsky.app import Application
from botsky.frontend.contracts import ActionRequest, ClarifyDecision, ReplyDecision
from botsky.frontend.worker import run_one
from botsky.frontend.context import load, adopt_context


class ContextTests(unittest.IsolatedAsyncioTestCase):
    setUp = worker_tests.WorkerTests.setUp
    incoming = worker_tests.WorkerTests.incoming
    count = worker_tests.WorkerTests.count

    def publish_fixture(self, receipt):
        # Doble de entrega local: no ACK de proveedor real.
        with self.app.store.transaction() as db:
            db.execute("UPDATE outbox SET state='accepted',provider_message_id=? WHERE receipt_id=?", ('reply-'+receipt.id, receipt.id))
            db.execute("UPDATE interactions SET state='active' WHERE receipt_id=? AND state='pending_delivery'", (receipt.id,))

    async def test_clarification_pdf_after_restart(self):
        from PIL import Image
        from pypdf import PdfReader
        from botsky.contracts import Result
        source = self.settings.root/'input.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        self.frontend.decision = ClarifyDecision('¿A qué formato?', 'convertir', {}, ('target',))
        receipt = self.app.receive(self.app.attach_local(self.incoming(text='convierte esto'), source))
        await run_one(self.app)
        self.assertEqual(self.count('jobs'), 0)
        self.publish_fixture(receipt)
        self.app = Application(self.settings, clock=lambda: self.now, frontend=self.frontend)
        self.frontend.decision = ActionRequest('convertir', {'target': 'pdf'})
        second = self.app.receive(self.incoming('2', 'a PDF'))
        await run_one(self.app)
        await self.app.jobs.run_pending()
        with self.app.store.transaction() as db:
            result = Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?', (second.id,)).fetchone()[0])
        self.assertEqual(result.code, 'document_converted')
        self.assertEqual(len(PdfReader(self.app.artifacts.path(result.data['artifacts'][0])).pages), 1)
        self.assertEqual(self.frontend.calls, 2)

    async def test_other_actor_and_expiry_hide_draft(self):
        self.frontend.decision = ClarifyDecision('¿Formato?', 'convertir', {}, ('target',))
        receipt = self.app.receive(self.incoming())
        await run_one(self.app)
        self.publish_fixture(receipt)
        other = self.app.receive(self.incoming('2', actor='owner'))
        with self.app.store.transaction() as db:
            row = db.execute('SELECT * FROM inbox WHERE id=?', (other.id,)).fetchone()
            self.assertIsNone(load(self.app, db, row, self.now)[1])
            db.execute('UPDATE interactions SET expires_ms=?', (self.now-1,))
            self.assertIsNone(load(self.app, db, row, self.now)[1])

    async def test_new_topic_cancels_draft(self):
        self.frontend.decision = ClarifyDecision('¿Formato?', 'convertir')
        receipt = self.app.receive(self.incoming())
        await run_one(self.app)
        self.publish_fixture(receipt)
        self.frontend.decision = ReplyDecision('Hola')
        self.app.receive(self.incoming('2', 'hola'))
        await run_one(self.app)
        with self.app.store.transaction() as db:
            self.assertEqual(db.execute("SELECT state FROM interactions WHERE kind='frontend_draft'").fetchone()[0], 'cancelled')
        self.assertEqual(self.count('jobs'), 0)

    async def test_lists_and_confirmations_are_exact(self):
        receipt = self.app.receive(self.incoming())
        with self.app.store.transaction() as db:
            row = db.execute('SELECT * FROM inbox WHERE id=?', (receipt.id,)).fetchone()
            snapshot = {'references': [{'kind': 'download', 'view_id': 'list-one'}, {'kind': 'download', 'view_id': 'list-two'}]}
            with self.assertRaises(ValueError):
                adopt_context(self.app, db, row, ActionRequest('dl.elegir', {'choice': 2}), snapshot, None, self.now)
            selected = adopt_context(self.app, db, row, ActionRequest('dl.detalle', {'choice': 2}), {'references': snapshot['references'][:1]}, None, self.now)
            self.assertEqual(selected.action_key, 'dl.detalle')
            self.assertEqual(selected.arguments['view_id'], 'list-one')
            with self.assertRaises(ValueError):
                adopt_context(self.app, db, row, ActionRequest('recado.enviar', {'draft_id': 'invented'}), snapshot, None, self.now)
            confirmed = adopt_context(self.app, db, row, ActionRequest('recado.enviar', {'draft_id': 'real'}), {'references': [{'kind': 'message_preview', 'action_key': 'recado.enviar', 'arguments': {'draft_id': 'real'}}]}, None, self.now)
            self.assertEqual(confirmed.action_key, 'recado.enviar')

    async def test_quote_filters_delivered_lists_and_expired_preview(self):
        from botsky.store import context_of
        self.frontend.decision = ReplyDecision('Lista sintética')
        first = self.app.receive(self.incoming())
        await run_one(self.app)
        self.publish_fixture(first)
        second = self.app.receive(self.incoming('2', 'otra lista'))
        await run_one(self.app)
        self.publish_fixture(second)
        third = self.app.receive(self.incoming('3', 'el segundo', quoted_message_id='reply-'+first.id))
        with self.app.store.transaction() as db:
            row = db.execute('SELECT * FROM inbox WHERE id=?', (third.id,)).fetchone()
            context = context_of(row)
            for identifier, parent in [('view1', first), ('view2', second)]:
                db.execute("INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,'download','{}','[]',?,'active',?)", (identifier, parent.id, *context.scope_key, json.dumps({'choices':[{'title':'Uno'},{'title':'Dos'}]}), self.now+1000))
            snapshot, _ = load(self.app, db, row, self.now)
            self.assertEqual([v['view_id'] for v in snapshot['references']], ['view1'])
            selected = adopt_context(self.app, db, row, ActionRequest('dl.elegir', {'choice': 2}), snapshot, None, self.now)
            self.assertEqual(selected.arguments['view_id'], 'view1')
            db.execute("UPDATE interactions SET kind='message_preview',expires_ms=? WHERE id='view1'", (self.now-1,))
            snapshot, _ = load(self.app, db, row, self.now)
            self.assertEqual(snapshot['references'], [])
            with self.assertRaises(ValueError):
                adopt_context(self.app, db, row, ActionRequest('recado.enviar', {'draft_id':'view1'}), snapshot, None, self.now)

    async def test_quoted_pagination_isolates_search_and_filters_and_determines_result(self):
        from botsky.adapters.local import CollectingTransport
        from botsky.contracts import Result

        for i in range(7):
            self.app.receive(self.incoming(f'c-{i}', f'/nota guardar cable {i}'))
            self.app.receive(self.incoming(f't-{i}', f'/nota guardar tarea {i}'))
        cable_p1 = self.app.receive(self.incoming('s-cable', '/notas cable'))
        tarea_p1 = self.app.receive(self.incoming('s-tarea', '/notas tarea'))
        self.app.deliver(cable_p1.id, CollectingTransport())
        self.app.deliver(tarea_p1.id, CollectingTransport())
        with self.app.store.transaction() as db:
            cable_msg_id = db.execute(
                'SELECT provider_message_id FROM outbox WHERE receipt_id=?', (cable_p1.id,)
            ).fetchone()[0]
        next_cable = self.app.receive(
            self.incoming('next-cable', 'siguiente', quoted_message_id=cable_msg_id)
        )
        with self.app.store.transaction() as db:
            row = db.execute('SELECT * FROM inbox WHERE id=?', (next_cable.id,)).fetchone()
            snapshot, _ = load(self.app, db, row, self.now)
        self.assertEqual(
            snapshot['references'],
            [
                {
                    'kind': 'pagination',
                    'action_key': 'notas',
                    'arguments': {'query': 'cable', 'page': 2},
                }
            ],
        )
        # Incluso si el modelo omite el filtro query al proponer la página 2, la cita determina el filtro «cable»
        self.frontend.decision = ActionRequest('notas', {'page': 2})
        await run_one(self.app)
        with self.app.store.transaction() as db:
            result = Result.from_json(
                db.execute('SELECT result_json FROM inbox WHERE id=?', (next_cable.id,)).fetchone()[0]
            )
        self.assertEqual(result.code, 'notes_found')
        self.assertEqual(result.data['query'], 'cable')
        self.assertEqual(result.data['page'], 2)
        self.assertEqual(len(result.data['items']), 2)
        self.assertTrue(all('cable' in item['text'] for item in result.data['items']))

    async def test_group_quoted_selection_bare_number_silence_and_private_single_list_selection(self):
        from dataclasses import replace
        from botsky.adapters.local import CollectingTransport, LocalAdapter
        from botsky.engines.downloads import DownloadOption

        class StubDownloads:
            enabled = True
            adult_sources_enabled = False

            def __init__(self, root):
                self.root = root
                self.downloads = []

            async def search(self, query, source, directory):
                return (
                    DownloadOption('https://media.w3.org/2010/05/bunny/trailer.mp4', 'Video 1', 10, 'Autor'),
                    DownloadOption('https://www.youtube.com/watch?v=AbCDEfgHI12', 'Video 2', 20, 'Autor'),
                )

            async def download(self, url, options, directory):
                self.downloads.append(url)
                out = directory / 'out.mp4'
                out.write_bytes(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom')
                return out

        self.settings = replace(
            self.settings,
            allowed_groups=frozenset({'group-1'}),
            friends=frozenset({'alice'}),
        )
        self.app.settings = self.settings
        self.app.downloads = StubDownloads(self.settings.root)
        adapter = LocalAdapter(self.settings, lambda: self.now)

        # 1. En grupo: publicar búsqueda
        g_search = self.app.receive(
            adapter.incoming('g-1', 'alice', 'group-1', '/dl buscar mp4 gatos', is_group=True)
        )
        await self.app.jobs.run_pending()
        transport = CollectingTransport()
        self.app.deliver(g_search.id, transport)
        self.assertIn(
            'Usa Responder sobre esta lista y escribe el número',
            transport.parts[0].payload.get('caption', '') or transport.parts[0].text,
        )
        with self.app.store.transaction() as db:
            group_list_msg = db.execute(
                'SELECT provider_message_id FROM outbox WHERE receipt_id=?', (g_search.id,)
            ).fetchone()[0]

        # 2. Silencio ante números sueltos en grupos
        bare = self.app.receive(
            adapter.incoming('g-bare', 'alice', 'group-1', '1', is_group=True)
        )
        self.assertEqual(bare.state, 'ignored')
        with self.app.store.transaction() as db:
            self.assertEqual(
                db.execute('SELECT count(*) FROM outbox WHERE receipt_id=?', (bare.id,)).fetchone()[0],
                0,
            )

        # 3. Elección citada en grupo funciona
        self.frontend.decision = ActionRequest('dl.elegir', {'choice': 1})
        quoted_choice = self.app.receive(
            adapter.incoming(
                'g-quoted',
                'alice',
                'group-1',
                '1',
                is_group=True,
                quoted_message_id=group_list_msg,
            )
        )
        self.assertEqual(quoted_choice.state, 'queued')
        await run_one(self.app)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.app.downloads.downloads), 1)

        # 4. Elección directa con una sola lista en privado
        p_search = self.app.receive(
            adapter.incoming('p-1', 'alice', 'private-alice', '/dl buscar mp4 perros', is_group=False)
        )
        await self.app.jobs.run_pending()
        self.app.deliver(p_search.id, CollectingTransport())
        self.frontend.decision = ActionRequest('dl.elegir', {'choice': 1})
        direct_private = self.app.receive(
            adapter.incoming('p-direct', 'alice', 'private-alice', '1', is_group=False)
        )
        self.assertEqual(direct_private.state, 'queued')
        await run_one(self.app)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.app.downloads.downloads), 2)
