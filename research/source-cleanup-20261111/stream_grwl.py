"""Resume this task's GRWL upload using bounded remote ranges and S3 part checksums."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import threading
from datetime import datetime,timezone
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/source_publish'))
import relocate
from upload import S3Session,CredentialTooNearExpiry,UploadError
STUDY=ROOT/'research/source-cleanup-20261111'
PLAN_SHA='3541f5cd6cb22be9b27873f860d2ff62d8ed568144d9e2d90933f2e75e18f871'
PRIOR_SHA='b2cf143a49fa080813ad6f73281b04aa91679afd83d9178be0b22741b594b372'
PART=16*1024*1024
WORKERS=8

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--resume-from',type=Path);parser.add_argument('--resume-sha256');parser.add_argument('--output-name',default='grwl-stream-r1');args=parser.parse_args()
 if not args.output_name.startswith('grwl-stream-') or '/' in args.output_name:raise ValueError('Invalid output name')
 plan=relocate.load_plan(STUDY/'flat-plan.json',PLAN_SHA,ROOT)
 row=next(r for r in plan['files'] if r['object_key']=='grwl-raw/grwl-raw-v01.01.parquet')
 prior_bytes=(STUDY/'flat-copy-r2/receipt.json').read_bytes();assert sha(prior_bytes)==PRIOR_SHA
 prior=next(r for r in json.loads(prior_bytes)['objects'] if r['object_key']==row['object_key'])
 assert prior['status']=='failed' and prior['multipart']['state']=='abort_failed' and not prior['multipart']['parts']
 upload_id=prior['multipart']['upload_id']
 session=S3Session(Path('/Users/nathan/.cargo/bin/source-coop'))
 client_lock=threading.Lock();cached=[None,None]
 def client():
  # Serialize refresh attempts; wait for a new CLI login without losing parts.
  with client_lock:
   for attempt in range(21):
    if cached[0] is not None and (cached[1]-datetime.now(timezone.utc)).total_seconds()>90:return cached[0]
    try:
     cached[0]=session.client();cached[1]=session.last_expiration;return cached[0]
    except CredentialTooNearExpiry:pass
    except UploadError as exc:
     if exc.operation != 'CredentialHelper':raise
    if attempt%2==0:print(json.dumps({'status':'waiting_for_source_credentials','waited_seconds':attempt*30}),flush=True)
    if attempt<20:time.sleep(30)
  raise ValueError('Credential refresh did not complete within 10 minutes')
 source=client().head_object(Bucket='nthh',Key=row['source_key'])
 assert source['ContentLength']==row['size_bytes']
 source_etag=source['ETag']
 assert relocate._head(client(),row['object_key']) is None
 resumed={}
 if args.resume_from:
  old=args.resume_from.read_bytes()
  assert sha(old)==args.resume_sha256
  old=json.loads(old)
  assert old['upload_id']==upload_id and old['plan_sha256']==PLAN_SHA and old['source_etag']==source_etag and old['part_bytes']==PART
  resumed={p['PartNumber']:p for p in old['parts']}
 output=STUDY/args.output_name;output.mkdir()
 report={'schema_version':1,'status':'running','plan_sha256':PLAN_SHA,'prior_receipt_sha256':PRIOR_SHA,'object_key':row['object_key'],'upload_id':upload_id,'started_at':datetime.now(timezone.utc).isoformat(),'part_bytes':PART,'workers':WORKERS,'source_etag':source_etag,'parts':[],'resumed_receipt_sha256':args.resume_sha256,'script_sha256':sha(Path(__file__).read_bytes())}
 def save():(output/'receipt.json').write_bytes(relocate.json_bytes(report))
 save()
 def part(number,start,end):
  request=urllib.request.Request(row['source_href'],headers={'Range':f'bytes={start}-{end}','If-Match':source_etag})
  for attempt in range(3):
   try:
    with urllib.request.urlopen(request,timeout=60) as response:
     assert response.status==206 and response.headers['Content-Range']==f"bytes {start}-{end}/{row['size_bytes']}"
     data=response.read(end-start+2)
    assert len(data)==end-start+1
    break
   except (OSError,TimeoutError):
    if attempt==2:raise
  checksum=base64.b64encode(hashlib.sha256(data).digest()).decode()
  if number in resumed:
   proof=resumed[number]
   assert proof['start']==start and proof['end']==end and proof['sha256']==sha(data) and proof['ChecksumSHA256']==checksum
   return data,{**proof,'reused_verified_part':True}
  for attempt in range(3):
   try:
    result=client().upload_part(Bucket='nthh',Key=row['object_key'],UploadId=upload_id,PartNumber=number,Body=data,ChecksumSHA256=checksum)
    assert result.get('ChecksumSHA256')==checksum
    return data,{'PartNumber':number,'ETag':result['ETag'],'ChecksumSHA256':checksum,'start':start,'end':end,'size_bytes':len(data),'sha256':sha(data)}
   except Exception as exc:
    code=getattr(exc,'response',{}).get('Error',{}).get('Code')
    if code not in ('ExpiredToken','InvalidToken','SlowDown','ServiceUnavailable') or attempt==2:raise
    time.sleep(5)
 total=hashlib.sha256(); starts=list(range(0,row['size_bytes'],PART))
 try:
  with ThreadPoolExecutor(max_workers=WORKERS) as pool:
   pending={i:pool.submit(part,i+1,start,min(start+PART,row['size_bytes'])-1) for i,start in enumerate(starts[:WORKERS])}
   for i,start in enumerate(starts):
    data,proof=pending.pop(i).result();total.update(data);report['parts'].append(proof);save()
    if (i+1)%16==0:print(json.dumps({'parts':i+1,'total_parts':len(starts),'bytes_uploaded_through':proof['end']+1}),flush=True)
    next_index=i+WORKERS
    if next_index<len(starts):
     offset=starts[next_index];pending[next_index]=pool.submit(part,next_index+1,offset,min(offset+PART,row['size_bytes'])-1)
  assert total.hexdigest()==row['sha256']
  report['source_full_sha256']=total.hexdigest();report['status']='parts_verified';save()
  parts=[{k:p[k] for k in ['PartNumber','ETag','ChecksumSHA256']} for p in report['parts']]
  completed=client().complete_multipart_upload(Bucket='nthh',Key=row['object_key'],UploadId=upload_id,MultipartUpload={'Parts':parts},IfNoneMatch='*')
  report['multipart_state']='completed';report['completed_etag']=completed.get('ETag');save()
  expected_composite=base64.b64encode(hashlib.sha256(b''.join(bytes.fromhex(p['sha256']) for p in report['parts'])).digest()).decode()+'-'+str(len(parts))
  actual_composite=completed.get('ChecksumSHA256')
  report['expected_composite_sha256']=expected_composite;report['returned_composite_sha256']=actual_composite
  head=client().head_object(Bucket='nthh',Key=row['object_key'],ChecksumMode='ENABLED')
  assert head['ContentLength']==row['size_bytes'] and head.get('ContentType')==row['media_type'] and head['ETag']==completed['ETag']
  if actual_composite==expected_composite:
   verification={'sha256':total.hexdigest(),'size_bytes':row['size_bytes'],'etag':head['ETag'],'checksum_method':'full_source_sha256_and_server_verified_ordered_multipart_sha256_chain'}
  else:
   verification=relocate.verify(session,row)
  report.update(verification);report['status']='verified';report['completed_at']=datetime.now(timezone.utc).isoformat();save()
  print(json.dumps({'status':'verified','object_key':row['object_key'],'sha256':report['sha256'],'checksum_method':report['checksum_method']}),flush=True)
 except Exception as exc:
  error=getattr(exc,'response',{})
  report['status']='failed';report['error_type']=type(exc).__name__;report['error_code']=error.get('Error',{}).get('Code');report['http_status']=error.get('ResponseMetadata',{}).get('HTTPStatusCode');save()
  print(json.dumps({'status':'failed','parts':len(report['parts']),'error_type':report['error_type'],'error_code':report['error_code']}),flush=True);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
