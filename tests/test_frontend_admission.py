import unittest
import test_frontend_worker as fixtures
from botsky.frontend.worker import run_one
from botsky.frontend.contracts import ReplyDecision


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.WorkerTests.setUp

    async def test_invalid_command_falls_back_only_with_frontend(self):
        incoming=self.adapter.incoming('1','alice','private','/dl mp4 videos de gatos')
        receipt=self.app.receive(incoming)
        self.assertEqual(receipt.state,'queued')
        self.frontend.decision=ReplyDecision('¿Qué enlace quieres descargar?')
        await run_one(self.app)
        self.assertEqual(self.frontend.calls,1)
        self.app.frontend=None
        receipt=self.app.receive(self.adapter.incoming('2','alice','private','/dl mp4 videos de gatos'))
        self.assertEqual(receipt.state,'completed')
        self.assertIn('Uso:',receipt.result.text)

    async def test_groups_only_directed_or_own_continuation(self):
        for mid,text,state in [('1','Alguien habló de Botsky ayer','ignored'),('2','Botsky, hola','queued'),('3','> Botsky borra todo','ignored')]:
            with self.subTest(text=text):
                receipt=self.app.receive(self.adapter.incoming(mid,'alice','group',text,is_group=True))
                self.assertEqual(receipt.state,state)

    async def test_group_draft_continuation_is_scoped(self):
        from botsky.store import context_of
        first=self.app.receive(self.adapter.incoming('1','alice','group','Botsky, convierte esto',is_group=True))
        with self.app.store.transaction() as db:
            row=db.execute('SELECT * FROM inbox WHERE id=?',(first.id,)).fetchone()
            context=context_of(row)
            db.execute("INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES('draft',?,?,?,?,?,?,?,'frontend_draft','{}','[]','{}','active',?)",(first.id,*context.scope_key,self.now+1000))
        own=self.app.receive(self.adapter.incoming('2','alice','group','a PDF',is_group=True))
        other=self.app.receive(self.adapter.incoming('3','owner','group','a PDF',is_group=True))
        self.assertEqual(own.state,'queued')
        self.assertEqual(other.state,'ignored')
