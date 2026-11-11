"""Extend the frozen retention inventory with exact canonical metadata supplements.

Read and verify only. This script neither uploads nor deletes Source objects.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import quote
import urllib.request
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/source_publish')]
from source_retirement import canonical_metadata, dump
from upload import S3Session

BASE = ROOT/'research/source-retirement-20261111'
REVISION = 'c0ad1cc5c18d69d3915f01bda478cb300d13b12f'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pin(path):
    return {'path':path.relative_to(ROOT).as_posix(), 'sha256':sha(path.read_bytes())}

client = S3Session(Path('/Users/nathan/.cargo/bin/source-coop')).client()
canonical = canonical_metadata(ROOT, {'lakeatlas'})
extras = json.loads((BASE/'lakeatlas-extra-metadata-inventory.json').read_bytes())['objects']
assert {o['key'] for o in extras} == set(canonical)
rows, checks = [], []
for obj in extras:
    declared = canonical[obj['key']]
    local = (ROOT/declared['path']).read_bytes()
    committed = subprocess.check_output(['git','show',REVISION+':'+declared['path']],cwd=ROOT)
    assert local == committed and sha(local) == declared['sha256']
    head = client.head_object(Bucket='nthh', Key=obj['key'])
    assert head['ETag'] == obj['etag'] and head['ContentLength'] == obj['size_bytes'] == len(local)
    source_url = 'https://data.source.coop/nthh/' + quote(obj['key'],safe='/')
    git_url = 'https://raw.githubusercontent.com/nthh/data-publications/' + REVISION + '/' + quote(declared['path'],safe='/')
    for url in [source_url,git_url]:
        with urllib.request.urlopen(url,timeout=60) as response:
            data = response.read(len(local)+1)
        assert data == local
    row = {**obj,'last_modified':head['LastModified'].isoformat(),'sha256':sha(local),
           'retained':{'kind':'git','path':declared['path'],'encoding':'identity','stored_sha256':sha(local),
                       'stored_size_bytes':len(local),'sha256':sha(local),'size_bytes':len(local)}}
    rows.append(row)
    checks.append({'key':obj['key'],'git_url':git_url,'sha256':sha(local),'size_bytes':len(local),'status':'passed'})
inventory=json.loads((BASE/'remote-inventory.json').read_bytes())
inventory['objects'] += [{k:o[k] for k in ('key','etag','size_bytes','last_modified')} for o in rows]
inventory['captured_at']=datetime.now(timezone.utc).isoformat()
dump(BASE/'remote-inventory-r2.json',inventory)
retention=json.loads((BASE/'retention-plan.json').read_bytes())
retention['objects']+=rows;retention['inventory']=pin(BASE/'remote-inventory-r2.json')
dump(BASE/'retention-plan-r2.json',retention)
execution=json.loads((BASE/'execution-plan.json').read_bytes())
execution['retention_plan']=pin(BASE/'retention-plan-r2.json')
execution['readme_plan']=pin(BASE/'readme-plan-r3.json')
execution['scope']='Retire exactly 606 inventoried legacy objects after live catalog cutover, including three exact canonical LakeATLAS metadata supplements.'
dump(BASE/'execution-plan-r2.json',execution)
dump(BASE/'supplement-live-verification.json',{'schema_version':1,'status':'passed','git_revision':REVISION,'objects':checks,
     'scope':'Exact full-byte equality among canonical files, committed Git files, live Git raw URLs and the old Source objects. No deletion.'})
print(json.dumps({'objects':len(retention['objects']),'bytes':sum(o['size_bytes'] for o in retention['objects']),
                  'execution_plan_sha256':sha((BASE/'execution-plan-r2.json').read_bytes())}))
