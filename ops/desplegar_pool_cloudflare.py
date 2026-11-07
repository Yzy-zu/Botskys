"""Corte propio autorizado: modelo contrastado y pool privado, sin entregas de prueba."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import UTC,datetime,timedelta
from pathlib import Path

import httpx
from botsky.config import Settings
from botsky.integrations import read_profile,compose_frontend
from botsky.adapters.cloudflare_pool import write_private,read_private
from botsky.adapters.cloudflare_interpreter import read_credentials
from registrar_cuenta_cloudflare import register

ROOT=Path(__file__).resolve().parents[1]
SERVICE='botsky-production-runtime'


def main(live):
    if not live:print(json.dumps({'mutations':False,'requires':'--live'}));return
    os.umask(0o077)
    folder=ROOT/'private'/('deploy-cloudflare-pool-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir(mode=0o700)
    profile_path=ROOT/'private/integrations.production.json'
    settings=Settings.load(ROOT/'private/production/config.toml')
    original=read_profile(profile_path)
    report={'phase':'preflight','target_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'messages':0,'calls':0,'inferences_during_deploy':0}
    def save():write_private(folder/'summary.json',report)
    def pm():return {x['name']:{'status':x['pm2_env']['status'],'pid':x['pid']} for x in json.loads(subprocess.check_output(['pm2','jlist'],text=True))}
    def control(action):subprocess.run(['pm2',action,SERVICE],check=True,stdout=subprocess.DEVNULL)
    def health():
        with httpx.Client(trust_env=False,timeout=5) as http:
            def get(port,path,token):
                r=http.get(f'http://127.0.0.1:{port}'+path,headers={'Authorization':'Bearer '+token});r.raise_for_status();return r.json()
            r=get(original['runtime']['port'],'/healthz',original['runtime']['webhook_token'])
            c=get(original['call_service']['port'],'/healthz',original['call_service']['token'])
            state=get(original['call_service']['port'],'/v1/status',original['call_service']['token'])
            result={'runtime_ready':r.get('ready'),'calls_ready':c.get('ready'),'active_call':state.get('activeCall') is not None,'external_call':state.get('externalCallPresent')}
            assert result['runtime_ready'] and result['calls_ready'] and not result['active_call'] and result['external_call'] is False
            return result
    def counts(require_idle=True):
        with sqlite3.connect('file:'+str(settings.database)+'?mode=ro',uri=True) as db:
            result={'schema':db.execute('PRAGMA user_version').fetchone()[0],'jobs':db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0],'outbox':db.execute("SELECT count(*) FROM outbox WHERE state IN ('pending','sending','uncertain')").fetchone()[0],'frontend':db.execute("SELECT count(*) FROM frontend_tasks WHERE state IN ('pending','running')").fetchone()[0]}
            assert result['schema']==20
            if require_idle:assert result['jobs']==result['outbox']==result['frontend']==0
            return result
    def wait():
        for _ in range(40):
            try:return health()
            except Exception:time.sleep(1)
        raise RuntimeError('postflight_unavailable')
    before=pm();report['preflight']=health();report['before']=counts();save()
    assert before[SERVICE]['status']=='online'
    control('stop');report['phase']='stopped';save()
    assert pm()[SERVICE]['status']=='stopped'
    try:
        counts()
        with sqlite3.connect(settings.database) as source,sqlite3.connect(folder/'before.sqlite3') as target:
            source.backup(target)
            assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert target.execute('PRAGMA foreign_key_check').fetchall()==[]
        shutil.copy2(profile_path,folder/'integrations.production.json')
        shutil.copy2(ROOT/'private/production/config.toml',folder/'config.toml')
        (folder/'integrations.production.json').chmod(0o600);(folder/'config.toml').chmod(0o600)
        with (folder/'previous-code.tar').open('wb') as f:subprocess.run(['git','archive','641844a'],cwd=ROOT,stdout=f,check=True)
        with (folder/'target-code.tar').open('wb') as f:subprocess.run(['git','archive',report['target_commit']],cwd=ROOT,stdout=f,check=True)
        pool_file='private/cloudflare-pool/registry.json'
        pool_path=settings.root/pool_file
        if pool_path.exists():raise RuntimeError('pool_already_registered_no_automatic_repeat')
        register(settings.root,pool_file,'cf01',ROOT/'private/cloudflare-toolcall.json')
        register(settings.root,pool_file,'cf02',ROOT/'private/cloudflare-pool/cf02.json')
        old=read_credentials(ROOT/'private/cloudflare-toolcall.json')
        until=(datetime.now(UTC)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        observed=read_private(ROOT/'private/cloudflare-pool/quota-state.json')
        pauses=dict(observed['paused_until'])
        pauses[hashlib.sha256(old['account_id'].lower().encode()).hexdigest()]=until.isoformat()
        write_private(pool_path.with_name('quota-state.json'),{'version':1,'paused_until':pauses})
        new={**original,'interpreter':{'enabled':True,'provider':'cloudflare','model':'@cf/qwen/qwen3.8-27b','reasoning_effort':'low','pool_file':pool_file,'deadline_seconds':40,'max_concurrency':2}}
        assert {k:v for k,v in new.items() if k!='interpreter'}=={k:v for k,v in original.items() if k!='interpreter'}
        write_private(profile_path,new);read_profile(profile_path)
        provider=compose_frontend(settings,new['interpreter'],None).provider
        assert len(provider.entries)==2
        report['accounts_not_paused_by_observed_quota']=len([e for e in provider.entries if provider.pauses.get(e[1],datetime.now(UTC))<=datetime.now(UTC)])
        report['provider_quota_available_now']=report['accounts_not_paused_by_observed_quota']>0
        report['backup_verified']=True;report['pool_accounts']=2;report['cf01_observed_quota_pause']=True;report['configuration_composed']=True;report['phase']='configured';save()
        control('start');report['postflight']=wait()
        after=pm();report['other_supervisors_unchanged']=all(after.get(k)==v for k,v in before.items() if k!=SERVICE)
        assert report['other_supervisors_unchanged']
        report['new_runtime_pid']=after[SERVICE]['pid'];report['after']=counts(False)
        with sqlite3.connect(settings.database) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and db.execute('PRAGMA foreign_key_check').fetchall()==[]
        report['phase']='active_healthy';report['model']=new['interpreter']['model'];report['reasoning_effort']='low'
        report['hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name!='summary.json'}
        save();print(json.dumps(report))
    except Exception:
        report['phase']='failed_restoring_previous_profile';save()
        control('stop');write_private(profile_path,original);control('start')
        report['rollback_health']=wait();save()
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');main(p.parse_args().live)
