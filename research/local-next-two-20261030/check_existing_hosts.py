#!/usr/bin/env python3
"""Repeat bounded name/DOI searches over a saved Source Cooperative metadata snapshot."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

QUERIES={
 'grwl':r'\bgrwl\b|global river widths? from landsat|1297434|18624542|aat0636',
 'grip':r'\bgrip4?\b|global roads inventory|6420961|aabd42',
}


def inspect(path):
    raw=path.read_bytes()
    rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
    results={}
    for slug,pattern in QUERIES.items():
        matches=[{'id':r.get('id'),'title':r.get('title'),'url':next((x.get('href') for x in r.get('links',[]) if x.get('rel')=='via'),None)}
                 for r in rows if re.search(pattern,json.dumps(r),re.I)]
        results[slug]={'regex':pattern,'matched_records':matches,'match_count':len(matches),
                       'interpretation':'No exact-name/DOI match identified in this snapshot.' if not matches else 'Matches need product/version/content review; keyword match alone does not establish equivalence.'}
    return {'source_url':'https://data.source.coop/source/metadata-catalog/catalog.jsonl',
            'source_sha256':hashlib.sha256(raw).hexdigest(),'source_bytes':len(raw),'records_searched':len(rows),
            'latest_record_cataloged_at':max(r.get('cataloged_at') or '' for r in rows),
            'results':results,'limitations':['Search covers this public metadata snapshot, not every hosted object or external provider.',
            'Names/DOIs may be absent or stale; zero matches is not proof of absence.',
            'Targeted web searches also found no exact native copy; SWORD, WaterNet, OSM and Overture are different products.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();result=inspect(args.catalog)
    if args.check:
        recorded=json.loads(args.report.read_text());recorded.pop('checked_at',None)
        if recorded!=result:raise SystemExit('Snapshot or query result differs from the recorded evidence')
    else:
        if args.report.exists():raise SystemExit('Use a new dated report; do not replace historical checks')
        args.report.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),**result},indent=2)+'\n')
    print(json.dumps({'records_searched':result['records_searched'],'matches':{k:v['match_count'] for k,v in result['results'].items()}},indent=2))


if __name__=='__main__':main()
