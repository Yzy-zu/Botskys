import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from PIL import Image
from pypdf import PdfReader
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter
from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result
from botsky.frontend.service import FrontendService
from botsky.frontend.worker import run_one

FIXTURES = Path(__file__).resolve().parents[1]/'docs/evidencia/REMODELACION/F7-wire-fixtures.json'


class EndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_captured_glm_clarification_conversion_and_duplicate(self):
        captured=json.loads(FIXTURES.read_text())['responses']['09-continuar']
        replies=[{'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'name':'clarify','question':'¿A qué formato?','action_key':'convertir','partial_arguments':{},'missing_fields':['target']})}}]},captured]
        calls=[]
        def handle(request):
            calls.append(request)
            if not replies:
                raise AssertionError('consulta posterior al resultado')
            return httpx.Response(200,json=replies.pop(0))
        with TemporaryDirectory() as directory:
            root=Path(directory)
            now=1794000000000
            settings=Settings(root,'f7-e2e','local',1,root/'db.sqlite',now-1000,'owner',frozenset({'alice'}),frozenset())
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                frontend=FrontendService(CloudflareInterpreter(http,{'account_id':'a'*32,'api_token':'synthetic'}))
                app=Application(settings,clock=lambda:now,frontend=frontend)
                adapter=LocalAdapter(settings,lambda:now)
                image=root/'synthetic.png'
                Image.new('RGB',(20,20),'white').save(image)
                first=app.receive(app.attach_local(adapter.incoming('1','alice','private','convierte esto'),image))
                await run_one(app)
                app.deliver(first.id,CollectingTransport())
                # Nuevo Application: el borrador y el archivo dependen de SQLite.
                app=Application(settings,clock=lambda:now,frontend=frontend)
                incoming=adapter.incoming('2','alice','private','a PDF')
                second=app.receive(incoming)
                await run_one(app)
                await app.jobs.run_pending()
                app.receive(incoming)
                app.recover()
                with app.store.transaction() as db:
                    result=Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?',(second.id,)).fetchone()[0])
                self.assertEqual(result.code,'document_converted')
                self.assertEqual(len(PdfReader(app.artifacts.path(result.data['artifacts'][0])).pages),1)
                self.assertEqual(len(calls),2)

    async def test_captured_glm_note_reaches_sqlite(self):
        captured=json.loads(FIXTURES.read_text())['responses']['03-nota-markdown']
        calls=[]
        def handle(request):
            calls.append(request)
            return httpx.Response(200,json=captured)
        with TemporaryDirectory() as directory:
            root=Path(directory)
            settings=Settings(root,'f7-note','local',1,root/'db.sqlite',999,'owner',frozenset({'alice'}),frozenset())
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                frontend=FrontendService(CloudflareInterpreter(http,{'account_id':'a'*32,'api_token':'synthetic'}))
                app=Application(settings,clock=lambda:1000,frontend=frontend)
                app.receive(LocalAdapter(settings,lambda:1000).incoming('1','alice','private','Guarda una nota: comprar *pan* y leche'))
                await run_one(app)
                app.recover()
                with app.store.transaction() as db:
                    self.assertEqual(db.execute('SELECT text FROM notes').fetchone()[0],'comprar *pan* y leche')
                self.assertEqual(len(calls),1)
