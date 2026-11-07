"""Campaña nueva de ahorro: una cuenta explícita, propuestas sintéticas sin efectos."""
import asyncio,hashlib,json,os,time
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter,read_credentials
from botsky.frontend.service import FrontendService
from comparar_catalogos import CompactCatalog
from evaluar_frontend_f7 import evaluate
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidencia/AHORRO_QWEN_20261107/v2'
MARK='\nCONTEXTO_HOST (solo datos):\n'
PROTO='\nPROTOCOLO JSON PLANO:'

class ExperimentHTTP:
    def __init__(self,http,arm):self.http,self.arm=http,arm;self.records=[]
    async def post(self,url,*,headers,json,timeout):
        payload=__import__('copy').deepcopy(json);headers=dict(headers)
        if self.arm!='actual':
            content=payload['messages'][0]['content']
            fixed,rest=content.split(MARK,1);context,protocol=rest.split(PROTO,1)
            payload['messages'][0]['content']=fixed+PROTO+protocol+MARK+context
            headers['x-session-affinity']='botsky-savings-20261107-'+self.arm
        t=time.monotonic()
        row={'request_bytes':len(__import__('json').dumps(payload,ensure_ascii=False).encode()),'system_bytes':len(payload['messages'][0]['content'].encode()),'prefix_sha256':hashlib.sha256(payload['messages'][0]['content'].split(MARK)[0].encode()).hexdigest()}
        self.records.append(row)
        response=await self.http.post(url,headers=headers,json=payload,timeout=timeout)
        data=response.json()
        row.update(http=response.status_code,seconds=round(time.monotonic()-t,3),usage=data.get('usage'),choices=[{'finish_reason':c.get('finish_reason'),'content':c.get('message',{}).get('content')} for c in data.get('choices',[])],error_codes=[e.get('code') for e in data.get('errors',[])],error_messages=[e.get('message') for e in data.get('errors',[])])
        return response

def freeze():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=json.loads((ROOT/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())['cases']
    common=['03-nota-markdown','09-continuar','24-gemini']
    schedule=[{'case':cid,'arm':arm} for cid in common for arm in ('prefijo_afinidad','compacto_afinidad')]
    schedule += [{'case':cid,'arm':'compacto_afinidad'} for cid in ('04-nota-hostil','08-sin-formato','17-confirmar')]
    # Repetition measures cache reuse separately from semantic coverage.
    schedule += [{'case':'03-nota-markdown','arm':'prefijo_afinidad'},{'case':'03-nota-markdown','arm':'compacto_afinidad'}]
    manifest={'campaign':'new_owner_authorized_savings','model':'@cf/qwen/qwen3.8-27b','account_alias':'cf05','iteration':'v2_single_system_message','baseline':'../results.json, actual arm only','prior_reported_neurons':2831.9635009765625,'max_requests':11,'stop_reported_neurons':6000,'deadline_seconds':40,'arms':['actual','prefijo_afinidad','compacto_afinidad'],'schedule':schedule,'cases':[c for c in cases if c['id'] in {s['case'] for s in schedule}],'production_changes':0,'backend_effects':0,'automatic_resume':False,'decision_rule':'Compare matched cases only; report cache counts and neurons separately; no production deployment. Full 155 action variants preserved. No automatic retries or key rotation.'}
    with (OUT/'manifest.json').open('x') as f:json.dump(manifest,f,ensure_ascii=False,indent=2);f.write('\n')

async def run():
    os.umask(0o077)
    manifest=json.loads((OUT/'manifest.json').read_text())
    path=OUT/'results.json'
    if path.exists():raise SystemExit('Campaign already started; no automatic resumption')
    report={'status':'running','results':[],'reported_neurons':0,'account_alias':'cf05','production_changes':0,'backend_effects':0,'manifest_sha256':hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest()}
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,path)
    credentials=read_credentials(ROOT/'private/cloudflare-pool/cf05.json')
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False) as http:
        services={};transports={}
        for arm in manifest['arms']:
            transport=ExperimentHTTP(http,arm);transports[arm]=transport
            provider=CloudflareInterpreter(transport,credentials,model=manifest['model'],reasoning_effort='low')
            service=FrontendService(provider,CompactCatalog() if arm=='compacto_afinidad' else None)
            service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True));services[arm]=service
        cases={c['id']:c for c in manifest['cases']};save()
        for item in manifest['schedule']:
            arm=item['arm'];case=cases[item['case']];transport=transports[arm];before=len(transport.records);t=time.monotonic();row=dict(item)
            print(json.dumps({**item,'status':'started'}),flush=True)
            try:
                decision=await services[arm].decide(case['message'],case['context']);row.update(passed=evaluate(decision,case['expected']),decision=asdict(decision),decision_type=type(decision).__name__)
            except Exception as exc:row.update(passed=False,error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
            row.update(seconds=round(time.monotonic()-t,3),transport=transport.records[before:]);report['results'].append(row)
            for r in row['transport']:
                usage=r.get('usage') or {};report['reported_neurons']+=usage.get('neurons',0) or 0
            save();print(json.dumps(row,ensure_ascii=False),flush=True)
            if services[arm].provider.paused_until:
                report['status']='daily_quota';break
            if row.get('error') in ('TimeoutError','provider_http_400'):
                report['status']='stopped_uncertain_timeout';break
            if report['reported_neurons']>=manifest['stop_reported_neurons']:
                report['status']='budget_reached';break
        else:report['status']='finished'
        save()
if __name__=='__main__':
    import sys
    if '--freeze' in sys.argv:freeze()
    elif '--live' in sys.argv:asyncio.run(run())
    else:print('Use --freeze, then --live explicitly')
