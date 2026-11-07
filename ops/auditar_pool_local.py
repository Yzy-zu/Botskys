"""Auditoría sin red ni escritura productiva; fixtures propios para medir overhead."""
import asyncio,json,stat,time,tempfile,statistics,subprocess
from pathlib import Path
from datetime import UTC,datetime
from botsky.adapters.cloudflare_pool import CloudflarePool,write_private
from botsky.integrations import read_profile,compose_frontend
from botsky.config import Settings
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidencia/AUDITORIA_POOL_20261107'
class Dummy:
 def __init__(self,*args,**kwargs):self.last_metrics=None;self.paused_until=None
 async def propose(self,messages,tools):return {'synthetic':True}
async def main():
 timings={}
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder);(root/'private').mkdir(mode=0o700)
  for count in (5,7,10):
   entries=[]
   for i in range(count):
    name='private/cf'+str(i)+'.json';write_private(root/name,{'account_id':format(i+1,'032x'),'api_token':'synthetic'});entries.append({'id':'cf'+str(i),'credentials_file':name})
   write_private(root/'private/pool.json',{'version':1,'entries':entries})
   pool=CloudflarePool(None,root,'private/pool.json',factory=Dummy);samples=[]
   for _ in range(1000):
    start=time.perf_counter_ns();await pool.propose([],[]);samples.append((time.perf_counter_ns()-start)/1e6)
   samples.sort();timings[str(count)]={'iterations':1000,'median_ms':statistics.median(samples),'p95_ms':samples[949],'max_ms':max(samples),'network':False,'scope':'registry+credential reload,selection,dummy provider; no prompt generation/network/inference'}
 settings=Settings.load(ROOT/'private/production/config.toml');profile=read_profile(ROOT/'private/integrations.production.json');frontend=compose_frontend(settings,profile['interpreter'],None);pool=frontend.provider;now=datetime.now(UTC)
 aliases=[e[0] for e in pool.entries];private_modes={}
 for entry in json.loads(pool.path.read_text())['entries']:
  path=settings.root/entry['credentials_file'];private_modes[entry['id']]=oct(stat.S_IMODE(path.stat().st_mode))
 service=[{'name':v['name'],'pid':v['pid'],'status':v['pm2_env']['status']} for v in json.loads(subprocess.check_output(['pm2','jlist'],text=True)) if v['name']=='botsky-production-runtime']
 result={'checked_utc':now.isoformat(),'network_requests':0,'production_changes':0,'local_timing':timings,'production':{'accounts':len(pool.entries),'distinct_accounts':len({e[1] for e in pool.entries}),'aliases':aliases,'private_modes':private_modes,'paused_by_observed_quota':[a for a,k,p in pool.entries if pool.pauses.get(k,now)>now],'quota_not_measured':True,'configured_max_concurrency_per_account':pool.options['max_concurrency'],'runtime_worker_concurrency':2,'services':service,'model':pool.options['model']},'limits_confirmed':['401 invalid credential has no quarantine','disabled credential is still read and validated','shared state writes lose pauses with two pool instances']}
 (OUT/'inspection.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':asyncio.run(main())
