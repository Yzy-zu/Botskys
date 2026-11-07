"""Inferencias locales aisladas con catálogo completo y oracles congelados."""
import argparse
import asyncio
import hashlib
import json
import os
import time
from dataclasses import asdict
from datetime import UTC,datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter
from botsky.frontend.service import FrontendService
from evaluar_frontend_f7 import evaluate

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidencia/QWEN_LOCAL_20261107'
URL='http://127.0.0.1:11435'


def memory_available_mb():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])//1024
    raise RuntimeError('memory_observation_unavailable')


class LocalHTTP:
    def __init__(self,http,model):
        self.http,self.model=http,model
        self.metrics=None;self.response=None
    async def post(self,url,*,headers,json,timeout):
        # Explicit local destination. Credentials and supplied Cloudflare URL are never forwarded.
        payload={'model':self.model,'messages':json['messages'],'format':'json','stream':False,'think':False,'keep_alive':'10m',
                 'options':{'num_ctx':32768,'num_predict':512,'temperature':0,'num_thread':1,'num_batch':128,'seed':1234}}
        response=await self.http.post(URL+'/api/chat',json=payload,timeout=timeout)
        body=response.json()
        fields=('total_duration','load_duration','prompt_eval_count','prompt_eval_cached_count','prompt_eval_duration','eval_count','eval_duration')
        self.metrics={k:body.get(k) for k in fields}
        self.response={'status':response.status_code,'done':body.get('done'),'done_reason':body.get('done_reason'),'content':body.get('message',{}).get('content'),'metrics':self.metrics,'error':body.get('error')}
        if response.status_code!=200:return httpx.Response(response.status_code,json={'errors':[{'code':'ollama_error'}]})
        return httpx.Response(200,json={'choices':[{'finish_reason':body.get('done_reason'),'message':{'content':body.get('message',{}).get('content'),'tool_calls':body.get('message',{}).get('tool_calls',[])}}],
              'usage':{'prompt_tokens':body.get('prompt_eval_count'),'completion_tokens':body.get('eval_count')}})


class LocalProvider(CloudflareInterpreter):
    def __init__(self,http,model):
        self.local=LocalHTTP(http,model)
        super().__init__(self.local,{'account_id':'a'*32,'api_token':'local-only'},deadline_seconds=600,max_concurrency=1)
    async def propose(self,messages,tools):
        try:return await super().propose(messages,tools)
        finally:
            if self.last_metrics:
                self.last_metrics['model']=self.local.model
                self.last_metrics['ollama']=self.local.metrics


async def guarded(awaitable):
    task=asyncio.create_task(awaitable)
    try:
        while not task.done():
            if memory_available_mb()<1536:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
                raise RuntimeError('resource_guard_memory_below_1536mb')
            await asyncio.wait([task],timeout=1)
        return await task
    finally:
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


async def run(live,selected_model=None):
    manifest=json.loads((EVIDENCE/'manifest.json').read_text())
    if not live:print(json.dumps({'network_inference':False,'models':manifest['models'],'cases':len(manifest['cases'])}));return
    models=[selected_model] if selected_model else manifest['models']
    os.umask(0o077)
    out=ROOT/'private'/('qwen-local-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(mode=0o700)
    report={'status':'running','models_selected':models,'results':[],'metadata':{},'backend_effects':0,'production_changes':0,'automatic_resume':False,'manifest_sha256':hashlib.sha256((EVIDENCE/'manifest.json').read_bytes()).hexdigest()}
    def save():
        tmp=out/'summary.tmp';tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,out/'summary.json')
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=600) as http:
        for model in models:
            tags=(await http.get(URL+'/api/tags')).json()['models'];entry=next(m for m in tags if m['name']==model)
            show=(await http.post(URL+'/api/show',json={'model':model})).json()
            report['metadata'][model]={'digest':entry['digest'],'size':entry['size'],'details':entry.get('details'),'capabilities':show.get('capabilities')}
            provider=LocalProvider(http,model);service=FrontendService(provider);service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
            for index,case in enumerate(manifest['cases']):
                deadline=600 if index==0 else 180
                provider.deadline=deadline;provider.last_metrics=None;provider.local.response=None
                report['current']={'model':model,'case':case['id'],'deadline_seconds':deadline,'started_utc':datetime.now(UTC).isoformat()};save()
                started=time.monotonic();available=memory_available_mb()
                print(json.dumps({'model':model,'case':case['id'],'status':'started','deadline_seconds':deadline}),flush=True)
                try:
                    decision=await guarded(service.decide(case['message'],case['context']))
                    row={'model':model,'case':case['id'],'pass':evaluate(decision,case['expected']),'decision_type':type(decision).__name__,'decision':asdict(decision)}
                except Exception as exc:
                    row={'model':model,'case':case['id'],'pass':False,'error':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__}
                row.update(duration_seconds=round(time.monotonic()-started,3),metrics=provider.last_metrics,ollama=provider.local.metrics,meets_40s=time.monotonic()-started<=40,memory_available_before_mb=available,memory_available_after_mb=memory_available_mb())
                report['results'].append(row);save()
                (out/f'{model.replace(":","-")}-{case["id"]}.json').write_text(json.dumps({'result':row,'response':provider.local.response},ensure_ascii=False,indent=2)+'\n')
                print(json.dumps(row,ensure_ascii=False),flush=True)
                if row.get('error') in ('TimeoutError','resource_guard_memory_below_1536mb'):
                    report.setdefault('incomplete_models',[]).append(model);save();break
            # Release this own model before loading the next one.
            await http.post(URL+'/api/generate',json={'model':model,'keep_alive':0,'stream':False},timeout=60)
        report['status']='finished_with_limits' if report.get('incomplete_models') else 'finished'
        report.pop('current',None);save()
    print(json.dumps({'directory':str(out),'status':report['status'],'results':len(report['results'])}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--freeze',action='store_true');parser.add_argument('--model',choices=('qwen3.5:2b','qwen3.5:4b'));args=parser.parse_args()
    if args.freeze:
        corpus=json.loads((ROOT/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())['cases']
        ids=['01-saludo','03-nota-markdown','04-nota-hostil','08-sin-formato','09-continuar','11-video','15-dos-listas','17-confirmar','24-gemini']
        data={'models':['qwen3.5:2b','qwen3.5:4b'],'cases':[c for c in corpus if c['id'] in ids],'catalog':'actual155variantes completo,no recorte','num_ctx':32768,'num_predict':512,'think':False,'num_thread':1,'num_parallel':1,'cold_deadline_seconds':600,'warm_deadline_seconds':180,'target_runtime_deadline_seconds':40,'minimum_available_memory_mb':1536,'backend_effects':0,'production_changes':0,'automatic_resume':False,'cache_policy':'Primer turno frío;resto mantiene modelo/prefijo yregistra caché si Ollama la reporta. No equiparar tiempos calientes con fríoCloudflare.'}
        with (EVIDENCE/'manifest.json').open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
    asyncio.run(run(args.live,args.model))
