"""Despliegue reversible del catálogo íntegro, con aceptación previa y datos preservados."""
import argparse,json,os,subprocess,sqlite3,shutil,hashlib,time
from datetime import UTC,datetime
from pathlib import Path
import httpx
from botsky.config import Settings
from botsky.integrations import read_profile,compose_frontend
from botsky.frontend.compact_catalog import LosslessCatalog
ROOT=Path(__file__).resolve().parents[1];SERVICE='botsky-production-runtime';PREVIOUS='3c29a21'

def main(live):
 if not live:return
 os.umask(0o077)
 evidence=ROOT/'docs/evidencia/DESPLIEGUE_COMPACTO_20261107'
 accepted=json.loads((evidence/'acceptance.json').read_text());manifest=json.loads((evidence/'manifest.json').read_text())
 supplement=json.loads((evidence/'supplement/acceptance.json').read_text())
 assert supplement['status']=='accepted_cases' and len(supplement['results'])==2 and all(r['passed'] for r in supplement['results'])
 latest={r['case']:r for r in accepted['results']+supplement['results']}
 assert set(latest)=={c['id'] for c in manifest['cases']} and all(r['passed'] for r in latest.values())
 assert hashlib.sha256((ROOT/'src/botsky/frontend/compact_catalog.py').read_bytes()).hexdigest()==manifest['source_sha256']
 profile_path=ROOT/'private/integrations.production.json';profile=read_profile(profile_path);config_path=ROOT/'private/production/config.toml';settings=Settings.load(config_path)
 out=ROOT/'private'/('deploy-compact-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(mode=0o700)
 report={'phase':'preflight','previous_commit':PREVIOUS,'target_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'messages':0,'calls':0,'inferences_during_deploy':0}
 def save(): (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
 def pm():return {v['name']:{'pid':v['pid'],'status':v['pm2_env']['status']} for v in json.loads(subprocess.check_output(['pm2','jlist'],text=True))}
 def control(action):subprocess.run(['pm2',action,SERVICE],check=True,stdout=subprocess.DEVNULL)
 def health():
  with httpx.Client(trust_env=False,timeout=5) as h:
   def get(block,path):
    b=profile[block];token=b['webhook_token'] if block=='runtime' else b['token'];r=h.get('http://127.0.0.1:'+str(b['port'])+path,headers={'Authorization':'Bearer '+token});r.raise_for_status();return r.json()
   r=get('runtime','/healthz');c=get('call_service','/healthz');s=get('call_service','/v1/status')
   result={'runtime_ready':r.get('ready'),'calls_ready':c.get('ready'),'active_call':s.get('activeCall') is not None,'external_call':s.get('externalCallPresent')}
   assert result['runtime_ready'] and result['calls_ready'] and not result['active_call'] and result['external_call'] is False
   return result
 def wait():
  for _ in range(40):
   try:return health()
   except Exception:time.sleep(1)
  raise RuntimeError('health_unavailable')
 def dbstate(path):
  with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as d:
   assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and d.execute('PRAGMA foreign_key_check').fetchall()==[]
   result={'schema':d.execute('PRAGMA user_version').fetchone()[0]}
   for table,states in [('jobs',"'queued','running'"),('outbox',"'pending','sending','uncertain'"),('frontend_tasks',"'pending','running'")]:result[table]=d.execute('SELECT count(*) FROM '+table+' WHERE state IN ('+states+')').fetchone()[0]
   assert result['schema']==20
   return result
 def snapshot(path):
  with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as d:
   result={}
   for (table,) in d.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
    quoted='"'+table.replace('"','""')+'"';digest=hashlib.sha256()
    for row in d.execute('SELECT * FROM '+quoted+' ORDER BY rowid'):digest.update(repr(row).encode())
    result[table]=digest.hexdigest()
   return result
 before=pm();report['preflight']=health();report['db_before']=dbstate(settings.database)
 assert before[SERVICE]['status']=='online' and all(report['db_before'][k]==0 for k in ('jobs','outbox','frontend_tasks'))
 report['profile_hash']=hashlib.sha256(profile_path.read_bytes()).hexdigest();save()
 control('stop')
 try:
  assert pm()[SERVICE]['status']=='stopped'
  assert all(dbstate(settings.database)[k]==0 for k in ('jobs','outbox','frontend_tasks'))
  with sqlite3.connect(settings.database) as source,sqlite3.connect(out/'before.sqlite3') as target:source.backup(target)
  dbstate(out/'before.sqlite3');original=snapshot(out/'before.sqlite3');assert snapshot(settings.database)==original
  shutil.copy2(profile_path,out/'integrations.production.json');shutil.copy2(config_path,out/'config.toml')
  shutil.copytree(settings.root/'private/cloudflare-pool',out/'cloudflare-pool')
  for label,ref in [('previous',PREVIOUS),('target',report['target_commit'])]:
   with (out/(label+'-code.tar')).open('wb') as stream:subprocess.run(['git','archive',ref],stdout=stream,check=True)
  frontend=compose_frontend(settings,profile['interpreter'],None)
  assert isinstance(frontend.catalog,LosslessCatalog) and len(frontend.provider.entries)==5
  assert snapshot(settings.database)==original
  report.update(backup_verified=True,data_unchanged_while_stopped=True,pool_accounts=5,compact_default=True,phase='backed_up')
  save();control('start');report['postflight']=wait();after=pm()
  assert all(after.get(k)==v for k,v in before.items() if k!=SERVICE)
  assert hashlib.sha256(profile_path.read_bytes()).hexdigest()==report['profile_hash']
  report.update(phase='active_healthy',new_runtime_pid=after[SERVICE]['pid'],other_services_unchanged=True,profile_unchanged=True,db_after=dbstate(settings.database))
  report['backup_hashes']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='summary.json'};save()
  (evidence/'deployment.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 except Exception:
  control('stop')
  # Only modified previously deployed source file; keep DB/profile/new data intact.
  old=subprocess.check_output(['git','show',PREVIOUS+':src/botsky/frontend/service.py'])
  (ROOT/'src/botsky/frontend/service.py').write_bytes(old)
  control('start');report['phase']='rolled_back_source';report['rollback_health']=wait();save();raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');main(p.parse_args().live)
