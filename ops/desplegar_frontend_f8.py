"""Corte propio F8 por encargo explícito; sin mensajes, inferencias ni llamadas."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from botsky.config import Settings
from botsky.store import Store
from botsky.integrations import read_profile, compose_frontend

ROOT=Path(__file__).resolve().parents[1]
NAME='botsky-production-runtime'


def main(live):
    if not live:
        print(json.dumps({'mutations':False,'requires':'--live'}));return
    os.umask(0o077)
    out=ROOT/'private'/('deploy-frontend-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(mode=0o700)
    profile_path=ROOT/'private/integrations.production.json'
    config_path=ROOT/'private/production/config.toml'
    settings=Settings.load(config_path)
    profile=read_profile(profile_path)
    report={'phase':'preflight','target_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'messages':0,'calls':0,'inferences':0,'backup_directory':str(out)}
    def save():
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def pm():
        return {v['name']:{'pid':v.get('pid'),'status':v['pm2_env']['status']} for v in json.loads(subprocess.check_output(['pm2','jlist'],text=True))}
    def health():
        with httpx.Client(trust_env=False,timeout=5) as http:
            def get(port,path,token):
                r=http.get(f'http://127.0.0.1:{port}'+path,headers={'Authorization':'Bearer '+token});r.raise_for_status();return r.json()
            runtime=get(profile['runtime']['port'],'/healthz',profile['runtime']['webhook_token'])
            call=get(profile['call_service']['port'],'/healthz',profile['call_service']['token'])
            state=get(profile['call_service']['port'],'/v1/status',profile['call_service']['token'])
            ops=get(profile['call_service']['port'],'/v1/operations',profile['call_service']['token'])
            result={'runtime_ready':runtime.get('ready'),'calls_ready':call.get('ready'),'active_call':state.get('activeCall') is not None,'external_call':state.get('externalCallPresent'),'idle_media_released':ops['health']['idleMediaReleased'],'reserved_agenda':ops['agenda']['reservedKeys'],'warnings':ops['health']['warnings']}
            assert result['runtime_ready'] and result['calls_ready'] and not result['active_call'] and result['external_call'] is False and result['reserved_agenda']==0
            return result
    def dbcheck():
        with sqlite3.connect('file:'+str(settings.database)+'?mode=ro',uri=True) as db:
            result={'schema':db.execute('PRAGMA user_version').fetchone()[0],'jobs':db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0],'outbox':db.execute("SELECT count(*) FROM outbox WHERE state IN ('pending','sending','uncertain')").fetchone()[0]}
            assert result['jobs']==result['outbox']==0
            return result
    def columns_snapshot(path,layout=None):
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            if layout is None:
                tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_version'")]
                layout={t:[r[1] for r in db.execute('PRAGMA table_info("'+t.replace('"','""')+'")')] for t in tables}
            hashes={}
            for table,cols in layout.items():
                quoted=lambda s:'"'+s.replace('"','""')+'"'
                digest=hashlib.sha256()
                for row in db.execute('SELECT '+','.join(map(quoted,cols))+' FROM '+quoted(table)+' ORDER BY rowid'):
                    digest.update(repr(row).encode());digest.update(b'\n')
                hashes[table]=digest.hexdigest()
            return layout,hashes
    def control(action):
        subprocess.run(['pm2',action,NAME],check=True,stdout=subprocess.DEVNULL)
    def wait_ready():
        for _ in range(40):
            try:return health()
            except (Exception,):time.sleep(1)
        raise RuntimeError('health_failed')
    before=pm();report['preflight']=health();report['db_before']=dbcheck();report['before_supervisors']=before;save()
    assert before[NAME]['status']=='online' and report['db_before']['schema']==19
    control('stop');report['phase']='stopped';save()
    assert pm()[NAME]['status']=='stopped'
    try:
        dbcheck()
        with sqlite3.connect(settings.database) as source,sqlite3.connect(out/'before.sqlite3') as target:
            source.backup(target)
            assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert target.execute('PRAGMA foreign_key_check').fetchall()==[]
        shutil.copy2(profile_path,out/'integrations.production.json')
        shutil.copy2(config_path,out/'config.toml')
        previous=json.loads((ROOT/'private/deploy-ui-20261107/summary.json').read_text())['target_commit']
        with (out/'previous-code.tar').open('wb') as stream:
            subprocess.run(['git','archive',previous],cwd=ROOT,stdout=stream,check=True)
        with (out/'target-code.tar').open('wb') as stream:
            subprocess.run(['git','archive',report['target_commit']],cwd=ROOT,stdout=stream,check=True)
        layout,original=columns_snapshot(out/'before.sqlite3')
        report['backup_verified']=True;report['previous_commit']=previous;report['phase']='backed_up';save()
        Store(settings.database)
        _,migrated=columns_snapshot(settings.database,layout)
        assert migrated==original
        with sqlite3.connect(settings.database) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('PRAGMA user_version').fetchone()[0]==20
        profile['interpreter']={'enabled':False,'provider':'cloudflare','model':'@cf/zai-org/glm-4.7-flash','credentials_file':'private/cloudflare-toolcall.json','deadline_seconds':40,'max_concurrency':2}
        def write_profile():
            temporary=profile_path.with_suffix('.f8-new.json')
            temporary.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,profile_path)
            read_profile(profile_path)
        write_profile()
        report['phase']='installed_schema20_frontend_disabled';report['preserved_tables']=len(layout);save()
        control('start');report['disabled_health']=wait_ready()
        control('stop');assert pm()[NAME]['status']=='stopped';dbcheck()
        secret=settings.root/'private/cloudflare-toolcall.json';secret.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        shutil.copy2(ROOT/'private/cloudflare-toolcall.json',secret);secret.chmod(0o600)
        profile['interpreter']['enabled']=True;write_profile()
        assert compose_frontend(settings,profile['interpreter'],None) is not None
        report['credentials_composed']=True
        report['phase']='configured_enabled_stopped';save()
    except Exception:
        report['phase']='failed';save()
        # Preserve schema20/data and restore availability on compatible current code.
        profile['interpreter']={'enabled':False}
        temporary=profile_path.with_suffix('.f8-recovery.json');temporary.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,profile_path)
        control('start')
        raise
    try:
        control('start');report['enabled_health']=wait_ready()
        after=pm();report['other_supervisors_unchanged']=all(after.get(k)==v for k,v in before.items() if k!=NAME)
        assert report['other_supervisors_unchanged']
        report['new_runtime_pid']=after[NAME]['pid'];report['db_after']=dbcheck();report['interpreter_enabled']=True
        report['hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='summary.json'}
        report['phase']='active_healthy';save()
        print(json.dumps(report))
    except Exception:
        report['phase']='activation_failed';save()
        control('stop')
        profile['interpreter']['enabled']=False;write_profile()
        control('start');report['recovery_health']=wait_ready();save()
        raise



if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true')
    main(parser.parse_args().live)
