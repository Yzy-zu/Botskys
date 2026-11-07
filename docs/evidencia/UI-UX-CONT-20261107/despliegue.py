"""Corte propio autorizado. No herramientas de chat, POST de prueba ni perfiles."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

import httpx
from botsky.config import Settings
from botsky.store import Store

os.umask(0o077)
ROOT=Path('/home/petrov/botsky')
PROFILE=ROOT/'private/integrations.production.json'
CONFIG=ROOT/'private/production/config.toml'
OUT=ROOT/'private/deploy-ui-cont-20261107'
OUT.mkdir(mode=0o700,exist_ok=False)
SETTINGS=Settings.load(CONFIG)
profile=json.loads(PROFILE.read_text())
report={'target_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'phase':'preflight','test_messages':0,'calls':0}

def save():
 (OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

def supervisors():
 values=json.loads(subprocess.check_output(['pm2','jlist'],text=True))
 return {v['name']:{'pid':v.get('pid'),'status':v['pm2_env']['status'],'restarts':v['pm2_env'].get('restart_time')} for v in values}

def health():
 with httpx.Client(trust_env=False,timeout=5) as http:
  result={}
  def get(port,path,token):
   r=http.get(f'http://127.0.0.1:{port}'+path,headers={'Authorization':'Bearer '+token});r.raise_for_status();return r.json()
  result['runtime']=get(profile['runtime']['port'],'/healthz',profile['runtime']['webhook_token'])
  port=profile['call_service']['port'];token=profile['call_service']['token']
  result['calls']=get(port,'/healthz',token)
  state=get(port,'/v1/status',token)
  result['active_call']=state.get('activeCall') is not None
  result['external_call']=state.get('externalCallPresent')
  ops=get(port,'/v1/operations',token)
  result['idle_media_released']=ops['health']['idleMediaReleased']
  result['warnings']=ops['health']['warnings']
  result['reserved_agenda']=ops['agenda']['reservedKeys']
  result['resources']=ops['resources']['trackedProcesses']
  assert result['runtime'].get('ready') is True and result['calls'].get('ready') is True
  assert not result['active_call'] and result['external_call'] is False
  assert result['idle_media_released'] is True and result['reserved_agenda']==0
  return result

def dbstate():
 with sqlite3.connect('file:'+str(SETTINGS.database)+'?mode=ro',uri=True) as db:
  return {'active_jobs':db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0],
          'unsettled_deliveries':db.execute("SELECT count(*) FROM outbox WHERE state IN ('pending','sending','uncertain')").fetchone()[0],
          'schema':db.execute('PRAGMA user_version').fetchone()[0]}

def snapshot(path):
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
  tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
  return {t:{'cols':[r[1] for r in db.execute(f'PRAGMA table_info("{t}")')],
             'rows':db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall()} for t in tables}

CATALOGUE=ROOT/'docs/evidencia/UI-UX-CATALOGO-20261107/033459'
regression=json.loads((CATALOGUE/'summary.json').read_text())
assert regression['success'] is True and regression['non_loopback_attempts']==0
assert regression['source_unchanged'] and regression['tests']==321
assert regression['captured_routes']==regression['semantic_candidate_routes']==155
for path,digest in regression['source_sha256'].items():
 assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
report['catalogue']=str(CATALOGUE.relative_to(ROOT))
report['source_revision']=regression['source_revision']
before=supervisors();report['preflight']=health();report['db_before']=dbstate()
assert report['db_before']['active_jobs']==report['db_before']['unsettled_deliveries']==0
assert report['db_before']['schema']==19
report['old_runtime_pid']=before['botsky-production-runtime']['pid'];save()
stopped=False
try:
 subprocess.run(['pm2','stop','botsky-production-runtime'],check=True,stdout=subprocess.DEVNULL)
 stopped=True;report['phase']='stopped';save()
 assert supervisors()['botsky-production-runtime']['status']=='stopped'
 assert dbstate()['active_jobs']==dbstate()['unsettled_deliveries']==0
 with sqlite3.connect(SETTINGS.database) as source, sqlite3.connect(OUT/'before.sqlite3') as backup:
  source.backup(backup)
  assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert backup.execute('PRAGMA foreign_key_check').fetchall()==[]
 shutil.copy2(PROFILE,OUT/'integrations.production.json');shutil.copy2(CONFIG,OUT/'config.toml')
 for name,revision in [('previous-code-4482c46','4482c46'),('verified-code',report['target_commit'])]:
  with (OUT/(name+'.tar')).open('wb') as output:
   subprocess.run(['git','archive',revision],cwd=ROOT,stdout=output,check=True)
 previous=snapshot(OUT/'before.sqlite3');current=snapshot(SETTINGS.database)
 assert current==previous,'Stopped database changed'
 report['preserved_tables']=len(previous)
 report['migration']='none; schema19; every table, column and row identical before restart'
 report['native_tables_enabled']=profile['evolution']['native_tables_enabled']
 assert report['native_tables_enabled'] is True
 report['phase']='backed_up';save()
finally:
 if stopped:
  subprocess.run(['pm2','start','botsky-production-runtime'],check=True,stdout=subprocess.DEVNULL)
  report['phase']='started';save()
last_error=''
for attempt in range(40):
 try:
  report['postflight']=health();break
 except Exception as exc:
  last_error=type(exc).__name__;time.sleep(1)
else:
 report['postflight_error']=last_error;save();raise RuntimeError('POSTFLIGHT_FAILED; preserve current database and inspect before code rollback')
after=supervisors()
report['other_supervisors_unchanged']=all(v==after.get(name) for name,v in before.items() if name!='botsky-production-runtime')
assert report['other_supervisors_unchanged']
report['new_runtime_pid']=after['botsky-production-runtime']['pid']
report['db_after']=dbstate();assert report['db_after']['schema']==19
with sqlite3.connect(SETTINGS.database) as db:
 report['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
 assert report['integrity']=='ok' and db.execute('PRAGMA foreign_key_check').fetchall()==[]
report['backup_sha256']=hashlib.sha256((OUT/'before.sqlite3').read_bytes()).hexdigest()
report['rollback']='Previous code archived; stop only own runtime, require zero active jobs/unsettled v2 plans, retain live schema19 database. Never restore old database over new effects. See reversion.md.'
report['phase']='deployed_healthy';save()
print(json.dumps({k:v for k,v in report.items() if k not in ('backup_sha256',)}))
