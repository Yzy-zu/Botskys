"""Experimento nuevo de modelos Cloudflare; propuestas, sin ejecutor ni despliegue."""
import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter, read_credentials, MODEL
from botsky.frontend.service import FrontendService
from evaluar_frontend_f7 import evaluate

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidencia/MODELOS_CF_20261107'
MODELS=[
 {'label':'GLM4.7Flash','id':MODEL,'extra':{}},
 {'label':'Gemma4-26B','id':'@cf/google/gemma-4-26b-a4b-it','extra':{}},
 {'label':'Llama4Scout','id':'@cf/meta/llama-4-scout-17b-16e-instruct','extra':{}},
 {'label':'GPT-OSS20B','id':'@cf/openai/gpt-oss-20b','extra':{}},
 {'label':'Qwen3.8-27B-low','id':'@cf/qwen/qwen3.8-27b','extra':{'reasoning_effort':'low'}},
]


class ModelHTTP:
    def __init__(self,http,profile):self.http,self.profile=http,profile
    async def post(self,url,*,headers,json,timeout):
        payload={**json,'model':self.profile['id'],**self.profile['extra']}
        return await self.http.post(url,headers=headers,json=payload,timeout=timeout)


class ModelProvider(CloudflareInterpreter):
    def __init__(self,http,credentials,profile):
        super().__init__(ModelHTTP(http,profile),credentials)
        self.profile=profile
    async def propose(self,messages,tools):
        try:return await super().propose(messages,tools)
        finally:
            if self.last_metrics:self.last_metrics['model']=self.profile['id']


def manifest():
    cases=json.loads((ROOT/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())['cases']
    selected=['04-nota-hostil','11-video','03-nota-markdown','09-continuar','17-confirmar','24-gemini']
    return {'models':MODELS,'screen':['04-nota-hostil','11-video'],
            'followup':['03-nota-markdown','09-continuar','17-confirmar','24-gemini'],
            'cases':[c for c in cases if c['id'] in selected],'catalog':'actual completo155variantes',
            'deadline_seconds':40,'max_completion_tokens':2048,'temperature':0,
            'selection':'Dos alternativas con más oracles correctos en screening;desempate por menor mediana de latencia. Elegibilidad requiere dos inferencias sin error de acceso/modelo. Conservar controlGLM. Screening no acredita ganador global.',
            'backend_effects':0,'production_changes':0,'automatic_resume':False,
            'billing_read':'403,no se conoce plan/saldo real;no habilitar plan/créditos ni probar modelos restringidos de pago;parar al error3036',
            'sources':['https://developers.cloudflare.com/workers-ai/platform/pricing/',*[f'https://developers.cloudflare.com/workers-ai/models/{p["id"].split("/")[-1]}/' for p in MODELS[1:]]]}


async def run(live):
    data=json.loads((EVIDENCE/'manifest.json').read_text())
    if not live:print(json.dumps({'network':False,'models':len(data['models']),'screen_requests':10,'followup_max_requests':12}));return
    os.umask(0o077)
    directory=ROOT/'private'/('models-cf-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(mode=0o700)
    report={'manifest_sha256':hashlib.sha256((EVIDENCE/'manifest.json').read_bytes()).hexdigest(),'results':[],'status':'running','backend_effects':0,'production_changes':0,'automatic_resume':False,'finalists':[]}
    def save():
        tmp=directory/'summary.tmp';tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,directory/'summary.json')
    requests=[];responses=[]
    async def request_hook(request):requests.append(True)
    async def response_hook(response):
        await response.aread()
        try:body=response.json()
        except ValueError:body={}
        responses.append({'status':response.status_code,'choices':[{'finish_reason':c.get('finish_reason'),'content':c.get('message',{}).get('content')} for c in body.get('choices',[])], 'usage':body.get('usage'),'error_codes':[e.get('code') for e in body.get('errors',[]) if isinstance(e,dict)]})
    cases={c['id']:c for c in data['cases']}
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False,event_hooks={'request':[request_hook],'response':[response_hook]}) as http:
        credentials=read_credentials(ROOT/'private/cloudflare-toolcall.json')
        providers={p['label']:ModelProvider(http,credentials,p) for p in data['models']}
        services={label:FrontendService(p) for label,p in providers.items()}
        for service in services.values():service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
        async def attempt(label,cid,stage):
            case=cases[cid];provider=providers[label];provider.last_metrics=None
            before=len(requests);before_responses=len(responses);started=asyncio.get_running_loop().time()
            try:
                decision=await services[label].decide(case['message'],case['context'])
                row={'model':label,'case':cid,'stage':stage,'pass':evaluate(decision,case['expected']),'decision_type':type(decision).__name__,'decision':asdict(decision)}
            except Exception as exc:row={'model':label,'case':cid,'stage':stage,'pass':False,'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
            row.update(requests=len(requests)-before,duration_seconds=round(asyncio.get_running_loop().time()-started,3),metrics=provider.last_metrics)
            report['results'].append(row)
            (directory/f'{len(report["results"]):02d}-{label}-{cid}.json').write_text(json.dumps({'result':row,'responses':responses[before_responses:]},ensure_ascii=False,indent=2)+'\n')
            save();print(json.dumps(row,ensure_ascii=False),flush=True)
            if provider.paused_until:
                report['status']='provider_daily_quota';save();return False
            return True
        labels=list(providers)
        save()
        for i,cid in enumerate(data['screen']):
            order=labels[i:]+labels[:i]
            for label in order:
                if not await attempt(label,cid,'screen'):break
            if report['status']!='running':break
        if report['status']=='running':
            import statistics
            eligible=[]
            for label in labels[1:]:
                rows=[r for r in report['results'] if r['model']==label]
                if len(rows)==2 and all(r.get('metrics') is not None for r in rows):
                    eligible.append((sum(r['pass'] for r in rows),-statistics.median(r['duration_seconds'] for r in rows),label))
            finalists=[x[2] for x in sorted(eligible,reverse=True)[:2]]
            report['finalists']=finalists;save()
            if finalists:
                compared=[labels[0],*finalists]
                for i,cid in enumerate(data['followup']):
                    order=compared[i%len(compared):]+compared[:i%len(compared)]
                    for label in order:
                        if not await attempt(label,cid,'followup'):break
                    if report['status']!='running':break
            if report['status']=='running':report['status']='finished'
        save()
    print(json.dumps({'directory':str(directory),'status':report['status'],'finalists':report['finalists'],'attempts':len(report['results'])}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
    if args.freeze:
        with (EVIDENCE/'manifest.json').open('x') as stream:json.dump(manifest(),stream,ensure_ascii=False,indent=2);stream.write('\n')
    asyncio.run(run(args.live))
