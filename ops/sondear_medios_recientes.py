"""Lectura acotada de miniaturas y muestra de stream; nunca entrega ni descarga completa."""
import asyncio,json,sqlite3,os,tempfile
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from botsky.config import Settings
from botsky.engines import downloads as d
from botsky.engines.process import run_process,MediaError
from botsky.engines.search_collage import fetch_thumbnail,decode_thumbnail
ROOT=Path(__file__).resolve().parents[1]
async def main():
 os.umask(0o077);s=Settings.load(ROOT/'private/production/config.toml')
 with sqlite3.connect('file:'+str(s.database)+'?mode=ro',uri=True) as db:
  url=json.loads(db.execute("SELECT arguments_json FROM jobs WHERE operation='download_media.url' AND state='failed' ORDER BY created_ms DESC LIMIT 1").fetchone()[0])['url']
  choices=json.loads(db.execute("SELECT result_json FROM jobs WHERE operation='download_media.search' AND state='succeeded' ORDER BY created_ms DESC LIMIT 1").fetchone()[0])['data']['choices']
 report={'bounded_samples':True,'messages':0,'thumbnails':[],'denied_hosts':[]};original=d._allowed_host
 def allowed(host,source=None):
  yes=original(host,source)
  if not yes and host not in report['denied_hosts']:report['denied_hosts'].append(host)
  return yes
 d._allowed_host=allowed
 sem=asyncio.Semaphore(2)
 async def thumb(i,c):
  async with sem:
   raw=await fetch_thumbnail(c.get('thumbnail_url'),d.download_source(c['url']))
   return {'number':i,'downloaded_bytes':len(raw or b''),'decodes':decode_thumbnail(raw) is not None}
 report['thumbnails']=await asyncio.gather(*(thumb(i,c) for i,c in enumerate(choices,1)))
 with tempfile.TemporaryDirectory() as tmp:
  source=d.download_source(url);client=d.Downloader(Path(tmp),adult_sources_enabled=True)
  try:
   async with d._proxy(source) as proxy:
    data=json.loads(await run_process(client._base(proxy,source)+['--impersonate','','--skip-download','--dump-single-json','--',url],25,env={'PATH':os.environ.get('PATH','')}))
    candidates=[x for x in data.get('formats',[]) if x.get('height')==240]
    report['samples']=[]
    async with httpx.AsyncClient(proxy=proxy,trust_env=False,timeout=10,follow_redirects=False) as http:
     for f in candidates[:2]:
      try:
       async with http.stream('GET',f['url'],headers={'Range':'bytes=0-1023',**data.get('http_headers',{})}) as r:
        n=0
        async for chunk in r.aiter_bytes():n+=min(len(chunk),1024);break
        report['samples'].append({'protocol':f.get('protocol'),'http':r.status_code,'bytes_observed_max':n,'content_type':r.headers.get('content-type')})
      except httpx.HTTPError:report['samples'].append({'protocol':f.get('protocol'),'error':'http_error'})
  except MediaError as exc:report['metadata_error']=exc.code
 (ROOT/'docs/evidencia/CORRECCION_VIDEO_20261107/samples.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':asyncio.run(main())
