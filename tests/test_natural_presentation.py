import json
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from botsky.commands.registry import Registry
from botsky.contracts import Result
from botsky.presentation import Block, Document, attach_document
from botsky.presentation.domains import present
from botsky.presentation.help import render_natural_help
from botsky.presentation.natural import adapt


class NaturalPresentationTests(unittest.TestCase):
    def test_samples_preserve_literals_and_consequences(self):
        literal = '*pan* /dl elegir NUMERO `codigo` https://example.org/a'
        samples = {
            'ayuda': Result('ok','help',render_natural_help(Registry())),
            'nota': adapt(present(Result('ok','notes_found',data={'items':[{'id':1,'text':literal}], 'total':1,'page':1,'pages':2}))),
            'collage': adapt(attach_document(Result('ok','download_choices'), Document((Block('literal',literal),Block('next_action','/dl elegir VIEW NUMERO'))))),
            'conversion': adapt(Result('needs_input','attachment_required','Uso: /convertir pdf')),
            'recado': adapt(present(Result('needs_input','message_preview',data={'recipients':['Ana'],'content':literal,'expires_ms':1794000000000,'draft_id':'real'}))),
            'confirmacion': adapt(present(Result('needs_input','pack_offer',data={'category':'Prueba','price':150,'min_photos':3,'max_photos':5,'expires_ms':1794000000000,'purchase_id':'real'}))),
            'error': adapt(Result('needs_input','selection_ambiguous','/dl elegir ID NUMERO')),
            'conversacion': adapt(Result('ok','frontend_reply','Hola. ¿Qué necesitas?')),
        }
        self.samples = samples
        for key,result in samples.items():
            with self.subTest(sample=key):
                self.assertNotIn('Uso:',result.text)
        for key in ('nota','collage','recado'):
            self.assertIn(literal,samples[key].text)
        self.assertIn('150 XP',samples['confirmacion'].text)
        self.assertIn('No he cobrado',samples['confirmacion'].text)
        self.assertIn('sí, envíalo',samples['recado'].text)
        self.assertNotIn('/recado enviar',samples['recado'].text)
        self.assertIn('número del video',samples['collage'].text)
        self.assertIn('siguiente página',samples['nota'].text)
        self.assertNotIn('/notas --pagina',samples['nota'].text)

    def test_original_document_and_command_mode_unchanged(self):
        result = attach_document(Result('ok','fixture'),Document((Block('literal','/recado enviar REAL'),Block('next_action','/recado enviar REAL'))))
        adapted = adapt(result)
        self.assertEqual(result.data['document']['blocks'][1]['text'],'/recado enviar REAL')
        self.assertEqual(adapted.data['document']['blocks'][0]['text'],'/recado enviar REAL')

    def test_specific_help_and_retry_notice(self):
        help_text = render_natural_help(Registry(),'descargas')
        self.assertIn('Busca videos de gatos',help_text)
        self.assertNotIn('/dl',help_text)
        retry = adapt(Result('needs_input','delivery_retry_preview',data={'part_count':2}))
        self.assertIn('duplicarla',retry.text)
        self.assertIn('no se repetirá',retry.text)

    def test_natural_dates_bytes_and_validity_cleanup(self):
        doc = Document((
            Block('paragraph', 'Archivo: prueba.pdf · 1.00 KiB (1024 bytes) · 2026-11-06 22:00:00 · America/Mexico_City'),
            Block('notice', 'Vigencia máxima: 5:00 desde la preparación. Vence: 2026-11-06 22:05:00 · America/Mexico_City. Opciones 1–4.'),
            Block('literal', 'No tocar: 1.00 KiB (1024 bytes) 2026-11-06 22:00:00 · America/Mexico_City'),
        ))
        adapted = adapt(attach_document(Result('ok', 'test_cleanup'), doc))
        self.assertIn('1.00 KiB · 06/11/2026, 10:00 p.m.', adapted.text)
        self.assertNotIn('(1024 bytes)', adapted.text.split('No tocar:')[0])
        self.assertIn('⏱️ _Opciones válidas por 5 min. Elige respondiendo del 1 al 4._', adapted.text)
        self.assertIn('No tocar: 1.00 KiB (1024 bytes) 2026-11-06 22:00:00 · America/Mexico_City', adapted.text)

    def test_fase_3_emojis_and_conversational_messages(self):
        doc = Document((
            Block('heading', 'Notas'),
            Block('heading', 'Recordatorio 10 guardado'),
            Block('next_action', '/admin nuclear-confirmar ID'),
            Block('next_action', '/coop aportar C1 50'),
            Block('next_action', '/tarea 5'),
        ))
        adapted = adapt(attach_document(Result('ok', 'fixture'), doc))
        self.assertIn('*📝 Notas*', adapted.text)
        self.assertIn('*🔔 Recordatorio 10 guardado*', adapted.text)
        self.assertIn('expulsión grupal', adapted.text)
        self.assertIn('50 XP', adapted.text)
        self.assertIn('número de tarea', adapted.text)

        for code, expected_fragment in (
            ('invalid_proposal', 'No entendí qué opción deseas'),
            ('confirmation_unavailable', 'La confirmación ya venció'),
            ('ai_quote_unavailable', 'No encontré el mensaje citado'),
            ('previous_download_missing', 'No encontré un archivo previo'),
            ('note_filter_required', 'Dime qué palabra o asunto deseas buscar'),
        ):
            res = adapt(Result('needs_input', code))
            self.assertIn(expected_fragment, res.text)


class ReceiptModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_help_and_receipt_mode_survive_configuration_change(self):
        import test_frontend_worker as fixtures
        from botsky.app import Application
        from botsky.adapters.local import LocalAdapter
        from botsky.config import Settings
        from botsky.frontend.contracts import ActionRequest
        from botsky.frontend.worker import run_one
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(root,'lab','local',1,root/'db.sqlite',999,'owner',frozenset({'alice'}),frozenset())
            frontend = fixtures.FrontendDouble()
            frontend.decision = ActionRequest('ayuda', {})
            app = Application(settings, clock=lambda:1000, frontend=frontend)
            adapter = LocalAdapter(settings,lambda:1000)
            receipt = app.receive(adapter.incoming('1','alice','private','ayuda'))
            await run_one(app)
            with app.store.transaction() as db:
                mode = db.execute('SELECT input_mode FROM inbox WHERE id=?',(receipt.id,)).fetchone()[0]
                self.assertEqual(mode,'natural')
                body = db.execute('SELECT payload FROM outbox WHERE receipt_id=?',(receipt.id,)).fetchone()[0]
                self.assertIn('Pídeme',body)
            app.frontend = None
            with app.store.transaction() as db:
                from botsky.store import context_of
                row = db.execute('SELECT * FROM inbox WHERE id=?',(receipt.id,)).fetchone()
                db.execute('DELETE FROM outbox WHERE receipt_id=?',(receipt.id,))
                app.store.enqueue(db,context_of(row),Result('needs_input','attachment_required','Uso: /convertir pdf'),1000)
                body = db.execute('SELECT payload FROM outbox WHERE receipt_id=?',(receipt.id,)).fetchone()[0]
                self.assertNotIn('Uso:',body)
                self.assertIn('Adjunta',body)
            self.assertEqual(frontend.calls,1)

    async def test_owner_can_resume_naturally_while_paused(self):
        import test_frontend_worker as fixtures
        from botsky.app import Application
        from botsky.adapters.local import LocalAdapter
        from botsky.config import Settings
        from botsky.frontend.contracts import ActionRequest
        from botsky.frontend.worker import run_one
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(root,'lab','local',1,root/'db.sqlite',999,'owner',frozenset(),frozenset())
            frontend = fixtures.FrontendDouble()
            app = Application(settings,clock=lambda:1000,frontend=frontend)
            adapter = LocalAdapter(settings,lambda:1000)
            pause = next(s for s in Registry().specs if s.family=='manage_conversation' and s.original_action=='pause')
            resume = next(s for s in Registry().specs if s.family=='manage_conversation' and s.original_action=='resume')
            app.receive(adapter.incoming('1','owner','private',pause.sample))
            frontend.decision = ActionRequest('.'.join(resume.path),{})
            receipt = app.receive(adapter.incoming('2','owner','private','reanuda Botsky'))
            await run_one(app)
            with app.store.transaction() as db:
                result = Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?',(receipt.id,)).fetchone()[0])
                self.assertEqual(result.code,'bot_mode_updated')
                self.assertEqual(result.data['paused_until_ms'],0)
