"""Corrida nueva explícita; propuestas sintéticas sin ejecutor ni reanudación."""
import argparse
import asyncio
import hashlib
import json
import statistics
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter, MODEL, read_credentials
from botsky.frontend.service import FrontendService
from botsky.frontend.contracts import ActionRequest, ReplyDecision, ClarifyDecision

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT/'docs/evidencia/REMODELACION/F7-casos.json'


def evaluate(decision, expected):
    kind = 'action' if isinstance(decision, ActionRequest) else 'reply' if isinstance(decision, ReplyDecision) else 'clarify' if isinstance(decision, ClarifyDecision) else 'no_action'
    if kind != expected['decision']:
        return False
    if kind == 'clarify':
        return (not expected.get('action_key') or decision.action_key == expected['action_key']) and all(k in decision.missing_fields for k in expected.get('missing_fields', []))
    if kind != 'action':
        return True
    return decision.action_key == expected['action_key'] and all(decision.arguments.get(k) == v for k,v in expected['arguments'].items())


async def main(options):
    corpus_path = Path(options.corpus) if options.corpus else CORPUS
    corpus = json.loads(corpus_path.read_text())
    if not options.live:
        print(json.dumps({'cases':len(corpus['cases']),'network':False}))
        return
    selected = [c for c in corpus['cases'] if not options.ids or c['id'] in options.ids.split(',')]
    if not selected:
        raise SystemExit('No cases selected')
    output = ROOT/'private'/('frontend-f7-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(mode=0o700)
    calls = []
    requests = []
    async def register_request(request):
        requests.append(True)
    async def capture(response):
        await response.aread()
        try:
            data = response.json()
        except ValueError:
            data = {}
        # No cabeceras, claves, razonamiento ni conversaciones completas.
        calls.append({'status':response.status_code,'choices':[{'finish_reason':c.get('finish_reason'),'tool_calls':c.get('message',{}).get('tool_calls',[]), 'content': c.get('message',{}).get('content')} for c in data.get('choices',[])], 'usage':data.get('usage'), 'errors': [{'code':e.get('code'), 'message':str(e.get('message',''))[:2000]} for e in data.get('errors',[]) if isinstance(e,dict)]})
    summary = {'model':MODEL,'corpus_sha256':hashlib.sha256(corpus_path.read_bytes()).hexdigest(),'backend_effects':0,'automatic_resume':False,'results':[]}
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False,event_hooks={'request':[register_request], 'response':[capture]}) as http:
        provider = CloudflareInterpreter(http,read_credentials(ROOT/'private/cloudflare-toolcall.json'))
        service = FrontendService(provider)
        service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
        for case in selected:
            before = len(calls)
            before_requests = len(requests)
            started = asyncio.get_running_loop().time()
            provider.last_metrics = None
            try:
                decision = await service.decide(case['message'],case['context'])
                result = {'id':case['id'],'pass':evaluate(decision,case['expected']),'decision_type':type(decision).__name__,'decision':asdict(decision)}
            except Exception as exc:
                result = {'id':case['id'],'pass':False,'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
            result.update(calls=len(requests)-before_requests,duration_seconds=round(asyncio.get_running_loop().time()-started,3),metrics=provider.last_metrics)
            summary['results'].append(result)
            # Cada resultado queda durable antes de continuar. No checkpoint de reanudación.
            path=output/(case['id']+'.json')
            with path.open('x') as stream:
                path.chmod(0o600)
                json.dump({'result':result,'response':calls[before:]},stream,ensure_ascii=False,indent=2)
            print(json.dumps(result,ensure_ascii=False),flush=True)
            if provider.paused_until:
                break
    summary['passed']=sum(r['pass'] for r in summary['results'])
    summary['median_seconds']=statistics.median(r['duration_seconds'] for r in summary['results'])
    path=output/'summary.json'
    with path.open('x') as stream:
        path.chmod(0o600)
        json.dump(summary,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'output':str(output),'passed':summary['passed'],'total':len(summary['results'])}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--ids',default='')
    parser.add_argument('--corpus',default='')
    asyncio.run(main(parser.parse_args()))
