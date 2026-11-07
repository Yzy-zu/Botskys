"""Reproducir respuestas HTTP sintéticas capturadas con el decodificador actual."""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter
from botsky.frontend.service import FrontendService
from evaluar_frontend_f7 import evaluate

ROOT=Path(__file__).resolve().parents[1]


async def main(source):
    cases={c['id']:c for c in json.loads((ROOT/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())['cases']}
    results=[]
    for item in sorted(source.glob('*.json')):
        data=json.loads(item.read_text())
        if 'response' not in data:
            continue
        case=cases[data['result']['id']]
        recorded=data['response'][0]
        calls=[]
        def handle(request):
            calls.append(True)
            return httpx.Response(recorded['status'],json={'choices':[{'finish_reason':c['finish_reason'],'message':{'content':c.get('content'),'tool_calls':c.get('tool_calls',[])}} for c in recorded['choices']],'usage':recorded['usage'],'errors':recorded['errors']})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            service=FrontendService(CloudflareInterpreter(http,{'account_id':'a'*32,'api_token':'synthetic'}))
            service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
            decision=await service.decide(case['message'],case['context'])
            assert evaluate(decision,case['expected'])
            assert len(calls)==1
            results.append({'id':case['id'],'oracle':'PASS','http_double_calls':len(calls)})
    output={'scope':'REPLAY_LOCAL_HTTP_CAPTURADO_SIN_INFERENCIA_NUEVA','results':results}
    (ROOT/'docs/evidencia/REMODELACION/F7-wire-replay.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    asyncio.run(main(parser.parse_args().source))
