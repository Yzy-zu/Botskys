"""Adopta propuestas GLM capturadas en SQLite/artefactos sintéticos, sin red."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from pypdf import PdfReader
from botsky.app import Application
from botsky.config import Settings
from botsky.adapters.local import LocalAdapter
from botsky.frontend.catalog import Catalog
from botsky.frontend.contracts import ActionRequest
from botsky.frontend.worker import run_one
from botsky.contracts import Result

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidencia/REMODELACION'
SOURCES={'03-nota-markdown':'F7-ajuste-temporal.json','04-nota-hostil':'F7-ajuste.json',
         '06-convertir':'F7-ajuste.json','18-recordatorio':'F7-ajuste-temporal.json'}


class Capture:
    def __init__(self, decision):
        self.decision=ActionRequest(**decision)
        self.catalog=Catalog()
        self.calls=0

    async def decide(self, text, context):
        self.calls+=1
        if self.calls>1:
            raise AssertionError('No debe volver a interpretar después del dominio')
        return self.decision


async def main():
    results=[]
    for case_id,source in SOURCES.items():
        recorded=next(r for r in json.loads((EVIDENCE/source).read_text())['results'] if r['id']==case_id)
        assert recorded['pass'] and recorded['decision_type']=='ActionRequest'
        with TemporaryDirectory() as directory:
            root=Path(directory)
            now=1794000000000
            settings=Settings(root,'f7-replay','local',1,root/'private/db.sqlite',now-1000,'owner',frozenset({'alice'}),frozenset())
            frontend=Capture(recorded['decision'])
            assert frontend.decision.action_key in ('nota.guardar','convertir','recordar.en')
            app=Application(settings,clock=lambda:now,frontend=frontend)
            incoming=LocalAdapter(settings,lambda:now).incoming('synthetic','alice','private','petición sintética capturada')
            if case_id=='06-convertir':
                image=root/'synthetic.png'
                Image.new('RGB',(20,20),'white').save(image)
                incoming=app.attach_local(incoming,image)
            receipt=app.receive(incoming)
            await run_one(app)
            await app.jobs.run_pending()
            app.recover()
            with app.store.transaction() as db:
                result=Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?',(receipt.id,)).fetchone()[0])
                if case_id.startswith(('03','04')):
                    text=db.execute('SELECT text FROM notes').fetchone()[0]
                    assert text==recorded['decision']['arguments']['text']
                elif case_id=='18-recordatorio':
                    reminder=db.execute('SELECT text,due_ms FROM reminders').fetchone()
                    assert reminder['text']=='entregar la tarea' and reminder['due_ms']==now+600000
                else:
                    assert result.code=='document_converted'
                    assert len(PdfReader(app.artifacts.path(result.data['artifacts'][0])).pages)==1
                assert db.execute('SELECT count(*) FROM outbox').fetchone()[0]>=1
                assert db.execute("SELECT count(*) FROM outbox WHERE state='accepted'").fetchone()[0]==0
                assert frontend.calls==1
                results.append({'id':case_id,'source':source,'code':result.code,'local_oracle':'PASS','interpreter_calls':frontend.calls,'provider_ack':False})
    (EVIDENCE/'F7-replay-local.json').write_text(json.dumps({'scope':'SQLITE_Y_MOTORES_LOCALES_SIN_RED','results':results},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
