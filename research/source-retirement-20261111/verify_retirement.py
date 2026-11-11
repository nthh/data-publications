"""Read-only verification of the completed exact Source retirement."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import urllib.error
import urllib.request
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/source_publish'), str(ROOT/'scripts')]
from retire import pinned, check_live_catalog
from upload import S3Session, ALLOWED_PRODUCTS

BASE = ROOT/'research/source-retirement-20261111'
execution_bytes = (BASE/'execution-plan-r2.json').read_bytes()
assert hashlib.sha256(execution_bytes).hexdigest() == '8df2a5db615027a97226673a61ef1572b1737a6159c3ddef10461435b3bd1396'
execution = json.loads(execution_bytes)
retention = pinned(ROOT, execution['retention_plan'])
receipt = json.loads((BASE/'retirement-execution-r2.json').read_bytes())
assert receipt['status'] == 'complete'
assert receipt['execution_plan_sha256'] == hashlib.sha256(execution_bytes).hexdigest()
assert set(receipt['deleted']) == {o['key'] for o in retention['objects']}
expected = {}
for pin in execution['destination_receipts']:
    proof = pinned(ROOT, pin)
    for o in proof.get('objects', [proof]):
        if o.get('status') == 'verified':
            expected[o['object_key']] = o
readmes = pinned(ROOT, execution['readme_plan'])['mutable_metadata']
for row in readmes:
    expected[row['object_key']] = row
client = S3Session(Path('/Users/nathan/.cargo/bin/source-coop')).client()
actual = {}; products = []
for product in sorted(ALLOWED_PRODUCTS):
    files = []
    for page in client.get_paginator('list_objects_v2').paginate(Bucket='nthh', Prefix=product+'/'):
        for obj in page.get('Contents', []):
            assert '/' not in obj['Key'][len(product)+1:], obj['Key']
            files.append({'key': obj['Key'], 'size_bytes': obj['Size'], 'etag': obj['ETag']})
            actual[obj['Key']] = obj
    products.append({'product': product, 'files': files, 'subdirectories': [], 'status': 'passed'})
assert set(actual) == set(expected), {'unexpected': sorted(set(actual)-set(expected)), 'missing': sorted(set(expected)-set(actual))}
checks = []
for key, proof in sorted(expected.items()):
    obj = actual[key]
    assert obj['Size'] == proof['size_bytes'], key
    if 'etag' in proof:
        assert obj['ETag'] == proof['etag'], key
    url = 'https://data.source.coop/nthh/' + key
    with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30) as response:
        assert int(response.headers['Content-Length']) == proof['size_bytes'], url
        assert response.headers.get('Access-Control-Allow-Origin') == '*', url
        etag = response.headers['ETag']
        if 'etag' in proof:
            assert etag == proof['etag'], url
    item = {'url': url, 'size_bytes': proof['size_bytes'], 'etag': etag, 'head_cors': 'passed'}
    if key.endswith(('.parquet', '.pmtiles')):
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Range':'bytes=0-126'}), timeout=30) as response:
            assert response.status == 206
            assert response.headers['Content-Range'] == f"bytes 0-126/{proof['size_bytes']}"
            assert response.headers.get('Access-Control-Allow-Origin') == '*'
            assert len(response.read(128)) == 127
        item['range_request'] = 'passed'
    if key.endswith('/README.md'):
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(proof['size_bytes'] + 1)
        assert len(data) == proof['size_bytes'] and hashlib.sha256(data).hexdigest() == proof['sha256']
        assert b'folia' not in data.lower()
        item['full_readback_sha256'] = proof['sha256']
    checks.append(item)
prefixes = ['https://data.source.coop/nthh/'+product+'/'+folder+'/' for product in ALLOWED_PRODUCTS for folder in ('releases','display','metadata')]
check_live_catalog(pinned(ROOT, execution['catalog_plan']), prefixes)
report = {'schema_version': 1, 'status': 'passed', 'checked_at': datetime.now(timezone.utc).isoformat(),
          'execution_plan_sha256': hashlib.sha256(execution_bytes).hexdigest(),
          'deleted_objects': len(receipt['deleted']), 'deleted_bytes': sum(o['size_bytes'] for o in retention['objects']),
          'remaining_objects': len(actual), 'products': products, 'http_checks': checks,
          'live_catalog_readback': 'passed', 'scope': 'All five complete Source inventories are flat and exact; unchanged replacement ETags/lengths and anonymous HTTP/CORS/ranges, full README readback, exact live catalog and Git support checks. No scientific or GEE revalidation.'}
output = BASE/'post-retirement-verification.json'
with output.open('x') as stream:
    json.dump(report, stream, sort_keys=True, indent=2);stream.write('\n')
print(json.dumps({'status':'passed','deleted_objects':len(receipt['deleted']),'remaining_objects':len(actual),'product_file_counts':{p['product']:len(p['files']) for p in products}}))
