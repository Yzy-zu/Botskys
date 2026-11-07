"""A/B aislado, una inferencia por brazo/caso; nunca importa el ejecutor."""
import argparse
import asyncio
import hashlib
import json
import os
import statistics
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter, MODEL, read_credentials
from botsky.frontend.catalog import Catalog
from botsky.commands.editorial import FAMILIES
from botsky.frontend.editorial import VARIANTS, field_description
from botsky.frontend.service import FrontendService
from evaluar_frontend_f7 import evaluate

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidencia/CATALOGO_AB_20261107'


class CompactCatalog(Catalog):
    def describe(self):
        actions=[]
        field_notes={}
        for key,spec in self.specs.items():
            fields=self.fields(spec)
            from botsky.frontend.catalog import field_schema
            properties={}
            for f in fields:
                schema=field_schema(f)
                schema.pop('description',None)
                properties[f.name]=schema
                field_notes[f.name]=field_description(f)
            entry={'action_key':key,'intent':spec.summary or spec.original_action.replace('_',' '),
                   'parameters':{'properties':properties,'required':[f.name for f in fields if f.required]}}
            if spec.constants:entry['constants']=dict(spec.constants)
            if spec.attachment:entry['attachment']=True
            if spec.confirmation!='none':entry['confirmation']=spec.confirmation
            if spec.operation in VARIANTS:entry['variant_note']=spec.operation
            actions.append(entry)
        return {'contract':'Cada parameters es object con additionalProperties=false. Constantes no editables. Validación y permisos corresponden al backend.',
                'families':{k:v[1] for k,v in FAMILIES.items()},
                'field_notes':field_notes,'variant_notes':VARIANTS,
                'downloads':{'search_sources':self.search_sources,'url_sources':self.url_sources},
                'availability':self.availability,'actions':actions}


def create_manifest():
    corpus=json.loads((ROOT/'docs/evidencia/REMODELACION/F7-casos-v2.json').read_text())
    ids=['01-saludo','03-nota-markdown','04-nota-hostil','06-convertir','08-sin-formato','09-continuar','11-video','12-adulto','15-dos-listas','17-confirmar','18-recordatorio','24-gemini']
    cases=[c for c in corpus['cases'] if c['id'] in ids]
    return {'model':MODEL,'cases':cases,'rounds':1,'alternating_order':True,'deadline_seconds':40,'max_completion_tokens':2048,'backend_effects':0,'production_changes':0,'automatic_resume':False,
            'decision_rule':'No desplegar por una muestra pequeña. Comparar decisiones/argumentos, errores, latencia y usage por pares; caso sin ambos brazos no permite contraste.'}


async def main(live):
    manifest=json.loads((EVIDENCE/'manifest.json').read_text())
    catalogs={'actual':Catalog(),'compacto':CompactCatalog()}
    for catalog in catalogs.values():catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
    sizes={name:len(json.dumps(c.describe(),ensure_ascii=False,separators=(',',':')).encode()) for name,c in catalogs.items()}
    if not live:
        print(json.dumps({'network':False,'cases':len(manifest['cases']),'catalog_bytes':sizes}));return
    os.umask(0o077)
    out=ROOT/'private'/('catalog-ab-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(mode=0o700)
    rows=[];requests=[]
    async def sent(request):requests.append(True)
    report={'manifest_sha256':hashlib.sha256((EVIDENCE/'manifest.json').read_bytes()).hexdigest(),'catalog_bytes':sizes,'results':rows,'automatic_resume':False,'backend_effects':0,'status':'running'}
    def save():
        (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False,event_hooks={'request':[sent]}) as http:
        provider=CloudflareInterpreter(http,read_credentials(ROOT/'private/cloudflare-toolcall.json'))
        services={name:FrontendService(provider,catalog) for name,catalog in catalogs.items()}
        save()
        for index,case in enumerate(manifest['cases']):
            order=['actual','compacto'] if index%2==0 else ['compacto','actual']
            for arm in order:
                before=len(requests);started=asyncio.get_running_loop().time();provider.last_metrics=None
                try:
                    decision=await services[arm].decide(case['message'],case['context'])
                    row={'case':case['id'],'arm':arm,'pass':evaluate(decision,case['expected']),'decision':asdict(decision),'decision_type':type(decision).__name__}
                except Exception as exc:
                    row={'case':case['id'],'arm':arm,'pass':False,'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
                row.update(requests=len(requests)-before,duration_seconds=round(asyncio.get_running_loop().time()-started,3),metrics=provider.last_metrics)
                rows.append(row);save();print(json.dumps(row,ensure_ascii=False),flush=True)
                if provider.paused_until:
                    report['status']='provider_daily_quota';save();break
            if provider.paused_until:break
        else:report['status']='finished'
    report['complete_pairs']=sum(all(any(r['case']==c['id'] and r['arm']==a for r in rows) for a in catalogs) for c in manifest['cases'])
    save();print(json.dumps({'directory':str(out),'status':report['status'],'complete_pairs':report['complete_pairs']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
    if args.freeze:
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        with (EVIDENCE/'manifest.json').open('x') as stream:json.dump(create_manifest(),stream,ensure_ascii=False,indent=2);stream.write('\n')
    asyncio.run(main(args.live))
