#!/usr/bin/env python3
"""Check or rewrite only the frozen 50-group selection; never writes reviewed.json."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/'research/catalog-citations-20261030/groups-combined-active-global.json'
OUT=Path(__file__).resolve().parent/'selected-groups.json'
expected=json.loads(SRC.read_text())[:50]
assert len(expected)==50
assert all(not e.get('deprecated',False) for g in expected for e in g['entries'] if e['catalog']=='official')
ap=argparse.ArgumentParser(); mode=ap.add_mutually_exclusive_group(); mode.add_argument('--write',action='store_true',help='rewrite selected-groups.json only'); mode.add_argument('--check',action='store_true',help='compare without writing (default)'); args=ap.parse_args()
if args.write:
    OUT.write_text(json.dumps(expected,indent=2,ensure_ascii=False)+'\n')
else:
    if not OUT.exists() or json.loads(OUT.read_text())!=expected:
        print('FAIL: selected-groups.json differs from frozen first-50 source; use --write only to refresh that selection file',file=sys.stderr); sys.exit(1)
    print('OK: selected-groups.json exactly matches frozen first 50 groups; no files written')
