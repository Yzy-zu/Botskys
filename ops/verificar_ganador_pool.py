"""Saludo y aclaración sobre el pool propio; solo decisiones, sin dominio/entrega."""
import argparse
import asyncio
import json
import os
from dataclasses import asdict
from datetime import UTC,datetime
from pathlib import Path
from types import SimpleNamespace
import httpx
from botsky.adapters.cloudflare_pool import CloudflarePool
from botsky.frontend.service import FrontendService
from evaluar_frontend_f7 import evaluate

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidencia/POOL_CLOUDFLARE_20261107'


async def run(live):
    cases=json.loads((EVIDENCE/'smoke-cases.json').read_text())
    if not live:print(json.dumps({'network':False,'cases':len(cases)}));return
    os.umask(0o077)
    directory=ROOT/'private'/('pool-smoke-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'));directory.mkdir(mode=0o700)
    rows=[]
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False) as http:
        pool=CloudflarePool(http,ROOT,'private/cloudflare-pool/registry.json',model='@cf/qwen/qwen3.8-27b',reasoning_effort='low')
        service=FrontendService(pool);service.catalog.configure_downloads(SimpleNamespace(enabled=True,adult_sources_enabled=True))
        for case in cases:
            try:
                decision=await service.decide(case['message'],case['context'])
                row={'case':case['id'],'pass':evaluate(decision,case['expected']),'decision_type':type(decision).__name__,'decision':asdict(decision),'metrics':pool.last_metrics}
            except Exception as exc:
                row={'case':case['id'],'pass':False,'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'metrics':pool.last_metrics}
            rows.append(row);(directory/'summary.json').write_text(json.dumps({'results':rows,'backend_effects':0},ensure_ascii=False,indent=2)+'\n');print(json.dumps(row,ensure_ascii=False),flush=True)
            if row.get('error') in ('daily_quota','daily_quota_pool'):break
    print(json.dumps({'directory':str(directory),'passed':sum(r['pass'] for r in rows),'total':len(rows)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');asyncio.run(run(p.parse_args().live))
