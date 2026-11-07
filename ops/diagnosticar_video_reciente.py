"""Sondeo acotado de metadatos del último fallo propio; no descarga ni envía video."""
import asyncio,json,sqlite3,os,tempfile
from pathlib import Path
from urllib.parse import urlsplit
from botsky.config import Settings
from botsky.engines.downloads import Downloader,_proxy,download_source,_allowed_host
from botsky.engines.process import run_process,MediaError
ROOT=Path(__file__).resolve().parents[1]
async def main():
 os.umask(0o077);settings=Settings.load(ROOT/'private/production/config.toml')
 with sqlite3.connect('file:'+str(settings.database)+'?mode=ro',uri=True) as db:
  failed=json.loads(db.execute("SELECT arguments_json FROM jobs WHERE operation='download_media.url' AND state='failed' ORDER BY created_ms DESC LIMIT 1").fetchone()[0]);url=failed['url']
  payload=json.loads(db.execute("SELECT result_json FROM jobs WHERE operation='download_media.search' AND state='succeeded' ORDER BY created_ms DESC LIMIT 1").fetchone()[0]);choices=payload['data']['choices']
 thumbs=[]
 for i,c in enumerate(choices,1):
  t=c.get('thumbnail_url');s=download_source(c['url']);p=urlsplit(t or '')
  thumbs.append({'number':i,'present':bool(t),'scheme':p.scheme,'host_allowed':bool(p.hostname and _allowed_host(p.hostname,s)),'source':s})
 report={'metadata_only':True,'video_downloaded':False,'messages':0,'thumbnail_metadata':thumbs}
 private=ROOT/'private/video-diagnostic';private.mkdir(mode=0o700,exist_ok=True)
 with tempfile.TemporaryDirectory() as tmp:
  client=Downloader(Path(tmp),adult_sources_enabled=True);source=download_source(url)
  def error(stderr):
   (private/'extractor-stderr.txt').write_bytes(stderr)
   text=stderr.decode(errors='replace').lower()
   for marker,code in [('requested format is not available','source_format_unavailable'),('impersonat','impersonation_error'),('http error 403','source_http_403'),('http error 429','source_http_429'),('proxy','proxy_error'),('unable to extract','extractor_error')]:
    if marker in text:return code
   return 'source_failed'
  try:
   async with _proxy(source) as proxy:
    raw=await run_process(client._base(proxy,source)+['--impersonate','','--skip-download','--dump-single-json','--',url],25,env={'PATH':os.environ.get('PATH','')},failure_code=error)
    data=json.loads(raw);formats=data.get('formats',[])
    report['metadata']={'success':True,'duration':data.get('duration'),'formats':[{'id':x.get('format_id'),'protocol':x.get('protocol'),'height':x.get('height'),'has_audio':x.get('acodec')!='none','url_https':str(x.get('url','')).startswith('https://'),'host_allowed':_allowed_host(urlsplit(x.get('url','')).hostname or '',source)} for x in formats]}
  except MediaError as exc:report['metadata']={'success':False,'code':exc.code}
 out=ROOT/'docs/evidencia/CORRECCION_VIDEO_20261107/diagnostic.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':asyncio.run(main())
