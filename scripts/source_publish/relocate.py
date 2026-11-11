#!/usr/bin/env python3
"""Add checksum-bound flat Source objects without deleting or overwriting keys."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
import urllib.request

from upload import S3Session, UploadError, ALLOWED_PRODUCTS, _head, _remote_error

ENDPOINT='https://data.source.coop'
BUCKET='nthh'
PART_BYTES=512*1024*1024

def digest(data): return hashlib.sha256(data).hexdigest()
def json_bytes(value): return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def safe_file(root, rel):
 if not isinstance(rel,str) or not rel or '\\' in rel or PurePosixPath(rel).is_absolute() or any(p in ('','..','.') for p in rel.split('/')):
  raise ValueError('Unsafe local path')
 path=root/rel
 if path.resolve()!=path or not path.is_file() or not path.is_relative_to(root):
  raise ValueError('Invalid local source')
 return path

def load_plan(path,expected,root):
 raw=path.read_bytes()
 if digest(raw)!=expected: raise ValueError('Plan checksum differs')
 plan=json.loads(raw)
 if plan.get('schema_version')!=1 or plan.get('endpoint')!=ENDPOINT or plan.get('bucket')!=BUCKET:
  raise ValueError('Plan route differs')
 keys=set()
 for row in plan['files']:
  product=row['dataset_id']; name=row['filename']
  if product not in ALLOWED_PRODUCTS or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',name) or name=='README.md':
   raise ValueError('Invalid flat product filename')
  key=product+'/'+name
  if key in keys or row['object_key']!=key or row['url']!=ENDPOINT+'/'+BUCKET+'/'+key:
   raise ValueError('Duplicate or mismatched destination')
  keys.add(key)
  if type(row['size_bytes']) is not int or row['size_bytes']<0 or not re.fullmatch(r'[a-f0-9]{64}',row['sha256']):
   raise ValueError('Invalid byte binding')
  if row['operation']=='copy':
   source=row['source_key']
   if not (source.startswith(product+'/releases/') or source.startswith(product+'/display/')) or any(p in ('','..','.') for p in source.split('/')):
    raise ValueError('Source copy outside original product release')
   if row['source_href']!=ENDPOINT+'/'+BUCKET+'/'+source or row['source_sha256']!=row['sha256'] or row['source_size_bytes']!=row['size_bytes']:
    raise ValueError('Copy changes source identity')
  elif row['operation'] in ('rewrite_style','generated','pmtiles_attribution'):
   rel=row['local_path']
   if not (rel.startswith(f'datasets/{product}/source-coop/') or (row['operation']=='pmtiles_attribution' and rel.startswith('.local/source-cleanup-20261111/'))):
    raise ValueError('Local source crosses product boundary')
   data=safe_file(root,rel).read_bytes()
   if len(data)!=row['size_bytes'] or digest(data)!=row['sha256']: raise ValueError('Local source checksum differs')
  else: raise ValueError('Unsupported operation')
 if not keys or sum(row['size_bytes'] for row in plan['files'])>25_000_000_000:
  raise ValueError('Plan exceeds relocation scope')
 return plan

def full_checksum(head):
 value=head.get('ChecksumSHA256')
 if head.get('ChecksumType')=='COMPOSITE' or not value: return None
 try:
  decoded=base64.b64decode(value,validate=True)
  return decoded.hex() if len(decoded)==32 else None
 except ValueError: return None

def ordered_range_hash(fetch,size,chunk_bytes=16*1024*1024,workers=4):
 value=hashlib.sha256()
 starts=list(range(0,size,chunk_bytes))
 with ThreadPoolExecutor(max_workers=workers) as pool:
  pending={i:pool.submit(fetch,start,min(start+chunk_bytes,size)-1) for i,start in enumerate(starts[:workers])}
  for i,start in enumerate(starts):
   data=pending.pop(i).result()
   if len(data)!=min(chunk_bytes,size-start): raise ValueError('Remote range truncated')
   value.update(data)
   next_index=i+workers
   if next_index<len(starts):
    next_start=starts[next_index]
    pending[next_index]=pool.submit(fetch,next_start,min(next_start+chunk_bytes,size)-1)
 return value.hexdigest()

def verify(session,row):
 client=session.client()
 head=client.head_object(Bucket=BUCKET,Key=row['object_key'],ChecksumMode='ENABLED')
 if head['ContentLength']!=row['size_bytes'] or head.get('ContentType')!=row['media_type']:
  raise ValueError('Destination size or media type differs')
 sha=full_checksum(head)
 method='server_full_object_sha256'
 if sha is None:
  method='full_anonymous_readback_sha256'
  if row['size_bytes']>=64*1024*1024:
   def fetch(start,end):
    request=urllib.request.Request(row['url'],headers={'Range':f'bytes={start}-{end}','If-Match':head['ETag']})
    for attempt in range(3):
     try:
      with urllib.request.urlopen(request,timeout=60) as response:
       if response.status!=206 or response.headers.get('Content-Range')!=f"bytes {start}-{end}/{row['size_bytes']}":
        raise ValueError('Range response differs')
       return response.read(end-start+2)
     except (TimeoutError,OSError):
      if attempt==2: raise
   sha=ordered_range_hash(fetch,row['size_bytes'])
  else:
   with urllib.request.urlopen(row['url'],timeout=60) as response: data=response.read(row['size_bytes']+1)
   if len(data)!=row['size_bytes']: raise ValueError('Remote object size differs')
   sha=digest(data)
 if sha!=row['sha256']: raise ValueError('Destination SHA-256 differs')
 return {'sha256':sha,'size_bytes':head['ContentLength'],'etag':head.get('ETag'),'checksum_method':method}

def copy_object(session,row,save,record):
 client=session.client()
 source=client.head_object(Bucket=BUCKET,Key=row['source_key'])
 if source['ContentLength']!=row['source_size_bytes']: raise ValueError('Source size differs')
 identity=source['ETag']
 source_ref={'Bucket':BUCKET,'Key':row['source_key']}
 if row['size_bytes']<=5_000_000_000:
  client.copy_object(Bucket=BUCKET,Key=row['object_key'],CopySource=source_ref,
                     CopySourceIfMatch=identity,IfNoneMatch='*',ChecksumAlgorithm='SHA256',MetadataDirective='COPY')
  record['copy_method']='CopyObject'
 else:
  response=client.create_multipart_upload(Bucket=BUCKET,Key=row['object_key'],ContentType=row['media_type'],ChecksumAlgorithm='SHA256',ChecksumType='COMPOSITE')
  upload_id=response['UploadId']; record['multipart']={'upload_id':upload_id,'state':'started','parts':[]}; save()
  try:
   for index,start in enumerate(range(0,row['size_bytes'],PART_BYTES),1):
    end=min(start+PART_BYTES,row['size_bytes'])-1
    part=session.client().upload_part_copy(Bucket=BUCKET,Key=row['object_key'],UploadId=upload_id,PartNumber=index,
         CopySource=source_ref,CopySourceIfMatch=identity,CopySourceRange=f'bytes={start}-{end}')['CopyPartResult']
    item={'PartNumber':index,'ETag':part['ETag']}
    if part.get('ChecksumSHA256'): item['ChecksumSHA256']=part['ChecksumSHA256']
    record['multipart']['parts'].append(item); save()
   session.client().complete_multipart_upload(Bucket=BUCKET,Key=row['object_key'],UploadId=upload_id,
      MultipartUpload={'Parts':record['multipart']['parts']},IfNoneMatch='*')
   record['multipart']['state']='completed'; record['copy_method']='UploadPartCopy'
  except Exception:
   try:
    session.client().abort_multipart_upload(Bucket=BUCKET,Key=row['object_key'],UploadId=upload_id)
    record['multipart']['state']='aborted'
   except Exception: record['multipart']['state']='abort_failed'
   save(); raise

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--plan',required=True,type=Path)
 parser.add_argument('--expected-plan-sha256',required=True)
 parser.add_argument('--repo-root',required=True,type=Path)
 parser.add_argument('--output',required=True,type=Path)
 parser.add_argument('--only',help='An exact object key for a small initial operation')
 parser.add_argument('--exclude-dataset',action='append',default=[],choices=sorted(ALLOWED_PRODUCTS))
 parser.add_argument('--exclude-object',action='append',default=[])
 parser.add_argument('--credential-helper',type=Path)
 parser.add_argument('--execute',action='store_true')
 parser.add_argument('--resume-from',type=Path)
 parser.add_argument('--expected-resume-sha256')
 args=parser.parse_args(); root=args.repo_root.resolve(strict=True)
 plan=load_plan(args.plan,args.expected_plan_sha256,root)
 prior={}
 if args.resume_from:
  previous=args.resume_from.read_bytes()
  if digest(previous)!=args.expected_resume_sha256: raise ValueError('Resume receipt checksum differs')
  previous=json.loads(previous)
  if previous['plan_sha256']!=args.expected_plan_sha256: raise ValueError('Resume plan differs')
  prior={r['object_key']:r for r in previous['objects'] if r['status']=='verified'}
 rows=[r for r in plan['files'] if (args.only is None or r['object_key']==args.only) and r['dataset_id'] not in args.exclude_dataset and r['object_key'] not in args.exclude_object]
 if not rows: raise ValueError('No selected objects')
 if args.output.exists(): raise ValueError('Receipt output exists')
 args.output.mkdir(parents=True)
 receipt={'schema_version':1,'plan_sha256':args.expected_plan_sha256,'mode':'execute' if args.execute else 'dry_run',
          'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'objects':[]}
 def save(): (args.output/'receipt.json').write_bytes(json_bytes(receipt))
 save()
 session=S3Session(args.credential_helper) if args.execute else None
 for row in rows:
  record={k:row[k] for k in ['dataset_id','filename','object_key','url','sha256','size_bytes','operation']}
  record['status']='planned'; receipt['objects'].append(record); save()
  if not args.execute: continue
  started=time.monotonic()
  try:
   existing=_head(session.client(),row['object_key'])
   proof=prior.get(row['object_key'])
   if (existing is not None and proof is not None and proof['sha256']==row['sha256']
       and proof['size_bytes']==existing['ContentLength']==row['size_bytes']
       and proof['etag']==existing.get('ETag') and existing.get('ContentType')==row['media_type']):
    record.update(status='verified',etag=proof['etag'],checksum_method='prior_full_readback_unchanged_object',prior_receipt_sha256=args.expected_resume_sha256)
    save(); continue
   if existing is None:
    if row['operation']=='copy': copy_object(session,row,save,record)
    else:
     body=safe_file(root,row['local_path']).read_bytes()
     if len(body)!=row['size_bytes'] or digest(body)!=row['sha256']: raise ValueError('Local bytes changed after preflight')
     session.client().put_object(Bucket=BUCKET,Key=row['object_key'],Body=body,ContentType=row['media_type'],IfNoneMatch='*',
          ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode())
   else: record['existing_object']=True
   save()
   record.update(verify(session,row)); record['status']='verified'; record['elapsed_seconds']=round(time.monotonic()-started,3); save()
   print(json.dumps({'key':row['object_key'],'status':'verified','method':record['checksum_method']}),flush=True)
  except Exception as exc:
   record['status']='failed'
   if isinstance(exc,(ValueError,UploadError)): record['error']=str(exc)
   else:
    error=_remote_error('S3 relocation failed','Relocate',exc)
    record['error']=str(error); record['http_status']=error.http_status; record['error_code']=error.error_code
   receipt['status']='failed'; save(); print(json.dumps(record),flush=True); return 1
 receipt['status']='complete' if args.execute else 'dry_run_passed'
 receipt['completed_at']=datetime.now(timezone.utc).isoformat(); save()
 print(json.dumps({'status':receipt['status'],'objects':len(rows)}))
 return 0

if __name__=='__main__': raise SystemExit(main())
