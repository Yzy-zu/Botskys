"""Resumen descriptivo de comparación; no reanuda inferencias ni modifica runtime."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidencia/CATALOGO_AB_20261107'


def median(values):
    return statistics.median(values) if values else None


def summarize(source):
    data=json.loads(source.read_text())
    rows=data['results']
    paired=[]
    cases=list(dict.fromkeys(r['case'] for r in rows))
    for case in cases:
        pair={r['arm']:r for r in rows if r['case']==case}
        if set(pair)=={'actual','compacto'}:
            paired.append({'case':case,'both_inferred':all(r.get('metrics') is not None for r in pair.values()),
                           'both_correct':all(r['pass'] for r in pair.values()),
                           **{arm:{'pass':r['pass'],'duration_seconds':r['duration_seconds'],'error':r.get('error')} for arm,r in pair.items()}})
    arms={}
    for arm in ('actual','compacto'):
        subset=[r for r in rows if r['arm']==arm]
        inferred=[r for r in subset if r.get('metrics') is not None]
        usages=[r['metrics']['usage'] for r in inferred if isinstance(r['metrics'].get('usage'),dict)]
        arms[arm]={'attempts':len(subset),'inferences_with_metrics':len(inferred),'oracle_matches':sum(r['pass'] for r in subset),
                   'median_seconds':median([r['duration_seconds'] for r in subset]),
                   'max_seconds':max((r['duration_seconds'] for r in subset),default=None),
                   'inferred_median_seconds':median([r['duration_seconds'] for r in inferred]),
                   'median_prompt_tokens':median([u['prompt_tokens'] for u in usages]),
                   'median_completion_tokens':median([u['completion_tokens'] for u in usages]),
                   'reported_neurons':sum(u.get('neurons',0) for u in usages)}
    shared=[p for p in paired if p['both_correct']]
    summary={'scope':'DESCRIPTIVO_SINTETICO_SIN_EFECTOS','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'status':data['status'],'catalog_bytes':data['catalog_bytes'],
             'catalog_byte_reduction_percent':100*(1-data['catalog_bytes']['compacto']/data['catalog_bytes']['actual']),
             'arms':arms,'pairs':paired,'pairs_both_correct':len(shared),
             'paired_correct_median_seconds':{arm:median([p[arm]['duration_seconds'] for p in shared]) for arm in ('actual','compacto')},
             'production_changes':0,'backend_effects':0,'automatic_resume':False}
    (EVIDENCE/'results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (EVIDENCE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);summarize(p.parse_args().source)
