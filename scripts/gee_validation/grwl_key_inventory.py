#!/usr/bin/env python3
"""Check complete local multiplicity for the GRWL sample's compound keys."""
from collections import defaultdict
from decimal import Decimal
import argparse
import json
from pathlib import Path
import duckdb
import pyarrow as pa
from capture import sha


def key(row):
    return (float(Decimal(str(row['lon']))),float(Decimal(str(row['lat']))),int(row['segmentID']),int(row['segmentInd']))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sample',required=True,type=Path)
    ap.add_argument('--parquet',required=True,type=Path)
    ap.add_argument('--report',required=True,type=Path)
    a=ap.parse_args()
    if a.report.exists():raise SystemExit('Choose a new report.')
    sample=json.loads(a.sample.read_text())
    if sha(a.parquet)!=sample['source']['parquet_sha256']:raise SystemExit('Parquet binding changed.')
    targets=defaultdict(list)
    for f in sample['features']:targets[key(f['properties'])].append(f['local_id'])
    pairs=sorted({(k[2],k[3]) for k in targets})
    con=duckdb.connect(config={'threads':2,'memory_limit':'1GB','preserve_insertion_order':False})
    con.register('target_pairs',pa.table({'segmentID':[x[0] for x in pairs],'segmentInd':[x[1] for x in pairs]}))
    query='SELECT p.feature_id,p.lon,p.lat,p.segmentID,p.segmentInd FROM read_parquet(?) p JOIN target_pairs t ON p.segmentID=t.segmentID AND p.segmentInd=t.segmentInd'
    found=defaultdict(list);candidate_rows=0
    reader=con.execute(query,[str(a.parquet)]).fetch_record_batch(8192)
    for batch in reader:
        for row in batch.to_pylist():
            candidate_rows+=1;k=key(row)
            if k in targets:found[k].append(str(row['feature_id']))
    missing=[i for k,ids in targets.items() for i in ids if i not in found[k]]
    duplicates=[{'key':list(k),'local_ids':ids,'selected_local_ids':targets[k]} for k,ids in found.items() if len(ids)>1]
    report={'schema_version':1,'status':'passed_unique_complete_local_keys' if not missing and not duplicates else 'requires_multiplicity_followup','source_row_count':sample['source']['row_count'],'parquet_sha256':sample['source']['parquet_sha256'],'sample_sha256':sha(a.sample),'script_sha256':sha(__file__),'selected_rows':len(sample['features']),'selected_keys':len(targets),'candidate_rows_examined':candidate_rows,'matched_keys':len(found),'missing_selected_ids':missing,'duplicate_keys':duplicates,'method':'Complete 64.6m-row scan of source segmentID/segmentInd with small target-pair join, then correctly rounded Decimal-to-binary64 lon/lat key matching in Python. No GEE values inspected.'}
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['duplicate_keys','missing_selected_ids']}),flush=True)
    return 0 if not missing and not duplicates else 1


if __name__=='__main__':raise SystemExit(main())
