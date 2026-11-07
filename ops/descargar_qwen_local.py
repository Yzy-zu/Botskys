"""Descarga explícita al daemon aislado de laboratorio; no inicia servicios productivos."""
import json
import os
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'private/ollama-lab'


def main():
    os.umask(0o077)
    report={'models':[],'phase':'pulling'}
    with httpx.Client(trust_env=False,timeout=httpx.Timeout(60,read=1200)) as http:
        for model in ('qwen3.5:2b','qwen3.5:4b'):
            start=time.monotonic();last=0
            row={'model':model,'status':'pulling'};report['models'].append(row)
            print(json.dumps({'model':model,'status':'starting'}),flush=True)
            with http.stream('POST','http://127.0.0.1:11435/api/pull',json={'model':model,'stream':True}) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:continue
                    data=json.loads(line)
                    if data.get('error'):raise RuntimeError(data['error'])
                    row.update({k:v for k,v in data.items() if k in ('status','digest','total','completed')})
                    if time.monotonic()-last>1:
                        (OUT/'downloads.json').write_text(json.dumps(report,indent=2)+'\n');last=time.monotonic()
            row['duration_seconds']=round(time.monotonic()-start,3)
            (OUT/'downloads.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(row),flush=True)
        report['phase']='finished'
        (OUT/'downloads.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'phase':'finished','models':2}),flush=True)


if __name__=='__main__':main()
