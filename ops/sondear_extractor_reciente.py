"""Reproductor acotado del extractor: --test parcial propio, sin entrega ni descarga completa."""
import asyncio,json,sqlite3,tempfile,os
from pathlib import Path
import httpx
from botsky.config import Settings
from botsky.engines.downloads import Downloader,_proxy,download_source
from botsky.engines.process import run_process,MediaError
ROOT=Path(__file__).resolve().parents[1]
async def main():
 os.umask(0o077);s=Settings.load(ROOT/'private/production/config.toml')
 with sqlite3.connect('file:'+str(s.database)+'?mode=ro',uri=True) as db:
  args=json.loads(db.execute("SELECT arguments_json FROM jobs WHERE operation='download_media.url' AND state='failed' ORDER BY created_ms DESC LIMIT 1").fetchone()[0]);url=args['url']
  choices=json.loads(db.execute("SELECT result_json FROM jobs WHERE operation='download_media.search' AND state='succeeded' ORDER BY created_ms DESC LIMIT 1").fetchone()[0])['data']['choices']
 report={'partial_extractor_test':True,'delivery':False,'full_download':False,'thumbnail_http':[]};private=ROOT/'private/video-diagnostic';private.mkdir(mode=0o700,exist_ok=True)
 with tempfile.TemporaryDirectory() as tmp:
  client=Downloader(Path(tmp),adult_sources_enabled=True);source=download_source(url)
  async with _proxy(source) as proxy:
   selected=await client._fitting_adult_video_format(proxy,source,url);report['selected_format']=selected
   def error(raw):
    (private/'partial-stderr.txt').write_bytes(raw)
    text=raw.decode(errors='replace').lower()
    markers=['requested format is not available','http error 403','http error 404','unable to download','unable to extract','unsupported url','impersonat','proxy','file size limit','too many open files']
    report['error_markers']=[x for x in markers if x in text];return 'source_failed'
   try:
    await run_process(client._base(proxy,source,max_bytes=2*1024*1024)+['--test','--impersonate','','--concurrent-fragments','1','--no-keep-fragments','--format',selected or 'best[protocol*=m3u8][height<=720]/best[protocol=https][height<=720]','--output',str(Path(tmp)/'partial.bin'),'--',url],30,env={'PATH':os.environ.get('PATH','')},failure_code=error)
    report['status']='partial_success';report['bytes_on_disk']=sum(p.stat().st_size for p in Path(tmp).rglob('*') if p.is_file())
   except MediaError as exc:report['status']=exc.code
  for i in (2,4):
   c=choices[i];source=download_source(c['url'])
   try:
    async with _proxy(source) as proxy:
     async with httpx.AsyncClient(proxy=proxy,trust_env=False,timeout=6,follow_redirects=False) as h:
      async with h.stream('GET',c['thumbnail_url']) as r:report['thumbnail_http'].append({'number':i+1,'http':r.status_code,'redirect':bool(r.headers.get('location')),'content_type':r.headers.get('content-type')})
   except httpx.HTTPError:report['thumbnail_http'].append({'number':i+1,'error':'http_error'})
 (ROOT/'docs/evidencia/CORRECCION_VIDEO_20261107/extractor.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':asyncio.run(main())
