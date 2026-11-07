import asyncio,json,sys
from pathlib import Path
import httpx
from types import SimpleNamespace
from botsky.adapters.cloudflare_interpreter import read_credentials,MODEL
from botsky.frontend.service import FrontendService
from dataclasses import asdict
root=Path(__file__).resolve().parents[1]
class Probe:
 async def propose(self,messages,tools):
  defs=[t['function'] for t in tools]
  messages[0]['content']+='\nPROTOCOLO JSON: Devuelve un solo objeto JSON con exactamente name y arguments. name es uno de reply,clarify,select_action,no_action. arguments cumple el schema de esa función. No produzcas XML, etiquetas ni llamadas de herramientas. Definiciones: '+json.dumps(defs,ensure_ascii=False)
  c=read_credentials(root/'private/cloudflare-toolcall.json')
  async with httpx.AsyncClient(trust_env=False,follow_redirects=False) as http:
   r=await http.post('https://api.cloudflare.com/client/v4/accounts/'+c['account_id']+'/ai/v1/chat/completions',headers={'Authorization':'Bearer '+c['api_token']},json={'model':MODEL,'messages':messages,'response_format':{'type':'json_object'},'stream':False,'temperature':0,'max_completion_tokens':1024},timeout=40)
   data=r.json()
   if r.status_code!=200:
    print(json.dumps({'status':r.status_code,'errors':data.get('errors')},ensure_ascii=False));raise ValueError('http_failure')
   item=data['choices'][0];content=item.get('message',{}).get('content')
   obj=json.loads(content)
   evidence={'status':r.status_code,'finish_reason':item['finish_reason'],'decision':obj,'usage':data.get('usage')}
   (root/'docs/evidencia/REMODELACION/F7-json-probe.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
   print(json.dumps(evidence,ensure_ascii=False))
   return {'choices':[{'finish_reason':item['finish_reason'],'message':{'tool_calls':[{'function':obj}]}}]}
async def main():
 case=next(c for c in json.loads((root/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())['cases'] if c['id']=='09-continuar')
 service=FrontendService(Probe());service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
 try:print(asdict(await service.decide(case['message'],case['context'])))
 except Exception as e:print(type(e).__name__)
if __name__ == '__main__':
 import argparse
 parser=argparse.ArgumentParser()
 parser.add_argument('--live',action='store_true')
 options=parser.parse_args()
 if options.live:
  asyncio.run(main())
 else:
  print(json.dumps({'network':False,'case':'09-continuar'}))
