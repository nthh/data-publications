"""Live transport/query checks and evidence assembly for the frozen flat layout."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
STUDY=ROOT/'research/source-cleanup-20261111'

def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,value):
 with path.open('x') as stream:stream.write(json.dumps(value,sort_keys=True,indent=2)+'\n')
def read(path):return json.loads(path.read_text())
def current_time():return datetime.now(timezone.utc).isoformat()

def http_checks(plan):
 checks=[]
 for row in plan['files']:
  with urllib.request.urlopen(urllib.request.Request(row['url'],method='HEAD',headers={'Origin':'http://localhost:8765'}),timeout=30) as response:
   headers=response.headers
   item={'dataset_id':row['dataset_id'],'filename':row['filename'],'url':row['url'],'status_code':response.status,'size_bytes':int(headers['Content-Length']),'content_type':headers.get('Content-Type'),'cors':headers.get('Access-Control-Allow-Origin'),'etag':headers.get('ETag')}
  assert item['status_code']==200 and item['size_bytes']==row['size_bytes']
  assert item['content_type']==row['media_type']
  assert item['cors'] in ('*','http://localhost:8765')
  if row['filename'].endswith(('.parquet','.pmtiles')):
   with urllib.request.urlopen(urllib.request.Request(row['url'],headers={'Range':'bytes=0-126','Origin':'http://localhost:8765'}),timeout=30) as response:
    data=response.read(128)
    assert response.status==206 and response.headers['Content-Range']==f"bytes 0-126/{row['size_bytes']}"
    assert len(data)==127 and response.headers.get('Access-Control-Allow-Origin') in ('*','http://localhost:8765')
    assert data.startswith(b'PAR1' if row['filename'].endswith('.parquet') else b'PMTiles\x03')
    item['range']={'status':206,'content_range':response.headers['Content-Range'],'bytes':len(data),'sha256':sha(data),'magic_verified':True}
  item['status']='passed';checks.append(item)
  print(json.dumps({'filename':row['filename'],'http':'passed'}),flush=True)
 return {'schema_version':1,'status':'passed','checked_at':current_time(),'files':checks}

def query_checks(plan):
 import duckdb
 database=duckdb.connect()
 database.execute('SET threads=2')
 database.execute('SET memory_limit=\'1GB\'')
 database.execute('LOAD httpfs')
 queries=[]
 sql='SELECT bbox.xmin, bbox.ymin FROM read_parquet(?) WHERE bbox.xmin BETWEEN -91 AND -89 AND bbox.ymin BETWEEN 34 AND 37 ORDER BY bbox.xmin, bbox.ymin LIMIT 5'
 for row in plan['files']:
  if not row['filename'].endswith('.parquet'):continue
  selected_sql=('SELECT source_row, i_mid AS annual_input_tonnes FROM read_parquet(?) WHERE i_mid IS NOT NULL ORDER BY i_mid DESC, source_row LIMIT 5' if row['dataset_id']=='river-plastic-inputs' else sql)
  old=database.execute(selected_sql,[row['source_href']]).fetchall()
  new=database.execute(selected_sql,[row['url']]).fetchall()
  assert old==new and len(new)==5
  queries.append({'dataset_id':row['dataset_id'],'filename':row['filename'],'status':'passed','original_url':row['source_href'],'flat_url':row['url'],'rows':new,'same_as_original':True,'sql':selected_sql})
  print(json.dumps({'filename':row['filename'],'subset_query':'passed'}),flush=True)
 return {'schema_version':1,'status':'passed','checked_at':current_time(),'duckdb_version':duckdb.__version__,'files':queries}

def verified_copies(plan, receipt_paths):
 expected = {row['object_key']: row for row in plan['files']}
 receipt_index = {}
 for path in STUDY.glob('*/receipt.json'):
  raw = path.read_bytes()
  receipt_index[sha(raw)] = (path, json.loads(raw))
 evidence = set()
 def check(row, proof, seen):
  assert proof['status'] == 'verified'
  assert proof['sha256'] == row['sha256'] and proof['size_bytes'] == row['size_bytes']
  assert isinstance(proof['etag'], str) and proof['etag']
  method = proof['checksum_method']
  if method == 'prior_full_readback_unchanged_object':
   pin = proof['prior_receipt_sha256']
   assert pin not in seen and pin in receipt_index
   path, parent = receipt_index[pin]
   assert parent['plan_sha256'] == sha((STUDY/'flat-plan.json').read_bytes())
   matches = [r for r in parent['objects'] if r['object_key'] == row['object_key']]
   assert len(matches) == 1 and matches[0]['etag'] == proof['etag']
   evidence.add(path)
   check(row, matches[0], seen | {pin})
  elif method == 'full_source_sha256_and_server_verified_ordered_multipart_sha256_chain':
   assert proof['multipart_state'] == 'completed' and proof['source_full_sha256'] == row['sha256']
   parts = proof['parts']; offset = 0; hashes = []
   for number, part in enumerate(parts, 1):
    assert part['PartNumber'] == number and part['start'] == offset
    assert part['end'] + 1 - offset == part['size_bytes']
    binary = bytes.fromhex(part['sha256']); assert len(binary) == 32
    assert part['ChecksumSHA256'] == base64.b64encode(binary).decode()
    hashes.append(binary); offset = part['end'] + 1
   assert offset == row['size_bytes']
   composite = base64.b64encode(hashlib.sha256(b''.join(hashes)).digest()).decode() + '-' + str(len(parts))
   assert composite == proof['expected_composite_sha256'] == proof['returned_composite_sha256']
  else:
   assert method in ('full_anonymous_readback_sha256', 'server_full_object_sha256')
 copied = {}
 for value in receipt_paths:
  path = value.resolve(strict=True)
  assert path.is_relative_to(STUDY.resolve())
  receipt = read(path)
  assert receipt['plan_sha256'] == sha((STUDY/'flat-plan.json').read_bytes())
  assert receipt['status'] in ('complete', 'verified')
  rows = receipt['objects'] if 'objects' in receipt else [receipt]
  evidence.add(path)
  for proof in rows:
   key = proof['object_key']; assert key in expected and key not in copied
   check(expected[key], proof, {sha(path.read_bytes())})
   copied[key] = proof
 assert set(copied) == set(expected)
 return copied, evidence

def reports(plan,args):
 http_path=STUDY/'flat-http-r1.json';query_path=STUDY/'flat-query-r1.json';browser_path=STUDY/'flat-browser-report.json'
 assert args.receipt, 'Provide the completed copy and stream receipts explicitly'
 copied, copy_paths = verified_copies(plan, args.receipt)
 http=read(http_path);query=read(query_path);browser=read(browser_path)
 assert http['status']==query['status']==browser['status']=='passed'
 observed_http = {(r['dataset_id'], r['filename']): r for r in http['files']}
 assert len(observed_http) == len(http['files']) == len(plan['files'])
 for row in plan['files']:
  observed = observed_http[(row['dataset_id'], row['filename'])]
  assert observed['status'] == 'passed' and observed['etag'] == copied[row['object_key']]['etag']
  assert observed['url'] == row['url'] and observed['size_bytes'] == row['size_bytes']
 report_dir=STUDY/'flat-hosting';report_dir.mkdir(exist_ok=True)
 for dataset_id in sorted({r['dataset_id'] for r in plan['files']}):
  manifest_path=ROOT/f'datasets/{dataset_id}/source-coop/flat-20261111/manifest.json';manifest=read(manifest_path)
  files=[r for r in plan['files'] if r['dataset_id']==dataset_id]
  assert len([r for r in http['files'] if r['dataset_id']==dataset_id and r['status']=='passed'])==len(files)
  parquet=[r for r in files if r['filename'].endswith('.parquet')]
  assert len([r for r in query['files'] if r['dataset_id']==dataset_id and r['status']=='passed'])==len(parquet)
  styles=[r for r in files if r['operation']=='rewrite_style']
  cases=[r for r in browser['cases'] if r['dataset_id']==dataset_id]
  assert len(cases)==len(styles)+(1 if dataset_id=='grwl-raw' else 0) and all(r['status']=='passed' for r in cases)
  urls={r['source_href']:r['url'] for r in files if r['filename'].endswith('.pmtiles')}
  for style in styles:
   d=read(ROOT/style['local_path'])
   for source in d['sources'].values():
    assert source['url'].removeprefix('pmtiles://') in urls.values()
  observed=[]
  for row in files:
   proof=copied[row['object_key']]
   assert proof['status']=='verified' and proof['sha256']==row['sha256'] and proof['size_bytes']==row['size_bytes']
   observed.append({'filename':row['filename'],'sha256':row['sha256'],'size_bytes':row['size_bytes'],'status':'verified','checksum_method':proof['checksum_method']})
  report={'schema_version':1,'dataset_id':dataset_id,'layout_id':'flat-20261111','manifest_sha256':sha(manifest_path.read_bytes()),'status':'passed','checked_at':current_time(),
   'checks':{k:'passed' for k in ['anonymous_access','range_requests','cors','asset_checksums','subset_query','catalog_links','browser_render']},'files':observed,
   'evidence':[{ 'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p.read_bytes())} for p in [*sorted(copy_paths),http_path,query_path,browser_path,STUDY/'flat-validation-criteria.json',STUDY/'flat-validation-criteria-r2.json']],
   'scope':'Flat Source URLs verified. Browser checks use live MapLibre/PMTiles; no new scientific or GEE validation. Original package links retained.'}
  write(report_dir/f'{dataset_id}.json',report)
 return {'status':'passed','reports':5}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['http','query','reports']);parser.add_argument('--receipt',type=Path,action='append');args=parser.parse_args()
 plan=read(STUDY/'flat-plan.json')
 if args.phase=='http':result=http_checks(plan);write(STUDY/'flat-http-r1.json',result)
 elif args.phase=='query':result=query_checks(plan);write(STUDY/'flat-query-r1.json',result)
 else:result=reports(plan,args)
 print(json.dumps({'status':result['status'],'phase':args.phase}))
if __name__=='__main__':main()
