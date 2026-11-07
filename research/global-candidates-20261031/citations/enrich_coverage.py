#!/usr/bin/env python3
"""Check/add frozen official GEE bboxes without regenerating or replacing candidate review fields."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent
entries=json.loads((ROOT/'research/catalog-citations-20261030/official-entries.json').read_text())
by={e['id']:e for e in entries}
p=OUT/'reviewed.json'; data=json.loads(p.read_text())
ap=argparse.ArgumentParser(); mode=ap.add_mutually_exclusive_group(); mode.add_argument('--write',action='store_true',help='add/update only source bbox, bbox evidence, and computed latitude_limit fields'); mode.add_argument('--check',action='store_true',help='compare without writing (default)'); args=ap.parse_args()
errors=[]
for c in data['candidates']:
    all_b=[]
    for s in c['sources']:
        if s['provider']!='Google Earth Engine official catalog': continue
        b=by.get(s['entry_id'],{}).get('bbox') or []
        if args.write: s['bbox']=b
        elif s.get('bbox')!=b: errors.append(f"{c['suggested_id']}: bbox mismatch for {s['entry_id']}")
        all_b.extend(x for x in b if isinstance(x,list) and len(x)==4)
    expected=[min(b[1] for b in all_b),max(b[3] for b in all_b)] if all_b else None
    if args.write:
        c['latitude_limit']=expected
        c['bbox_evidence']='research/catalog-citations-20261030/official-entries.json; entry bbox' if expected else None
    elif c.get('latitude_limit')!=expected:
        errors.append(f"{c['suggested_id']}: latitude_limit expected {expected}, got {c.get('latitude_limit')}")
if args.write:
    p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    print('Updated only source bbox, bbox_evidence, and latitude_limit fields; candidate scope/title/review text preserved')
elif errors:
    print('\n'.join(errors),file=sys.stderr); sys.exit(1)
else: print('OK: frozen official bboxes and derived latitude limits match; no files written')
