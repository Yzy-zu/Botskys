"""Aceptación nueva del compacto íntegro antes del despliegue autorizado."""
import asyncio,json,hashlib,os,time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter,read_credentials
from botsky.frontend.service import FrontendService
from evaluar_frontend_f7 import evaluate
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidencia/DESPLIEGUE_COMPACTO_20261107'

def freeze():
 OUT.mkdir(parents=True,exist_ok=True)
 cases=json.loads((ROOT/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())['cases']
 ids=['03-nota-markdown','04-nota-hostil','08-sin-formato','09-continuar','17-confirmar','24-gemini']
 with (OUT/'manifest.json').open('x') as f:json.dump({'scope':'new_lossless_compact_acceptance','account_alias':'cf04','model':'@cf/qwen/qwen3.8-27b','cases':[next(c for c in cases if c['id']==cid) for cid in ids],'max_requests':6,'deadline_seconds':40,'backend_effects':0,'automatic_resume':False,'production_changes_in_test':0,'source_sha256':hashlib.sha256((ROOT/'src/botsky/frontend/compact_catalog.py').read_bytes()).hexdigest()},f,ensure_ascii=False,indent=2)
async def run():
 os.umask(0o077);manifest=json.loads((OUT/'manifest.json').read_text());target=OUT/'acceptance.json'
 if target.exists():raise SystemExit('Already started; no automatic resumption')
 report={'status':'running','results':[],'account_alias':'cf04','backend_effects':0,'automatic_resume':False}
 responses=[]
 async def hook(response):
  await response.aread();body=response.json()
  responses.append({'http':response.status_code,'usage':body.get('usage'),'error_codes':[e.get('code') for e in body.get('errors',[])],'choices':[{'finish_reason':c.get('finish_reason'),'content':c.get('message',{}).get('content')} for c in body.get('choices',[])]})
 def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 async with httpx.AsyncClient(trust_env=False,event_hooks={'response':[hook]}) as http:
  provider=CloudflareInterpreter(http,read_credentials(ROOT/'private/cloudflare-pool/cf04.json'),model=manifest['model'],reasoning_effort='low')
  service=FrontendService(provider);service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True));save()
  for case in manifest['cases']:
   t=time.monotonic();before=len(responses);row={'case':case['id']};print(json.dumps({**row,'status':'started'}),flush=True)
   try:
    decision=await service.decide(case['message'],case['context']);row.update(passed=evaluate(decision,case['expected']),decision=asdict(decision))
   except Exception as exc:row.update(passed=False,error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
   row.update(seconds=round(time.monotonic()-t,3),responses=responses[before:]);report['results'].append(row);save();print(json.dumps(row,ensure_ascii=False),flush=True)
   if not row['passed']:report['status']='acceptance_failed';break
  else:report['status']='accepted_cases'
  save()
if __name__=='__main__':
 import sys
 if '--freeze' in sys.argv:freeze()
 elif '--live' in sys.argv:asyncio.run(run())
