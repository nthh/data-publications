#!/usr/bin/env python3
"""Bounded, cached HTTP-range acquisition of selected official GRWL ZIP members.

No whole-archive fallback. Extracted members are CRC-checked, SHA-256 recorded.
Full archive MD5 is deliberately not claimed. Reports are write-once.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
CRITERIA=ROOT/'research/grwl-raw-audit-20261102/criteria.json'
META=ROOT/'research/local-next-two-20261030/upstream/grwl-latest-zenodo.json'
LIMIT=json.loads(CRITERIA.read_text())['acquisition_limits']


def digest(data):return hashlib.sha256(data).hexdigest()


class RangeZip(io.RawIOBase):
    def __init__(self,item,cache):
        self.item=item;self.size=item['size'];self.position=0;self.cache=cache
        self.directory=cache/'ranges'/item['key'];self.directory.mkdir(parents=True,exist_ok=True)
        self.requests=[]
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if self.position<0:raise ValueError('Negative offset')
        return self.position
    def read(self,count=-1):
        count=min(self.size-self.position,count if count>=0 else self.size-self.position)
        if count<=0:return b''
        pieces=[]
        while count:
            n=min(count,LIMIT['max_range_request_bytes']);start=self.position;end=start+n-1
            name=self.directory/f'{start}-{end}';binary=name.with_suffix('.bin');meta=name.with_suffix('.json')
            if binary.exists() and meta.exists():
                data=binary.read_bytes();record=json.loads(meta.read_text())
                if len(data)!=n or digest(data)!=record['sha256']:raise ValueError('Cached range checksum mismatch')
                self.requests.append({**record,'cache_hit':True})
            else:
                used=sum(p.stat().st_size for p in (self.cache/'ranges').rglob('*.bin'))
                if used+n>LIMIT['max_http_body_bytes']:raise ValueError('HTTP transfer cap exceeded')
                if shutil.disk_usage(self.cache).free<LIMIT['minimum_free_disk_bytes']:raise ValueError('Disk reserve not met')
                url=self.item['links']['self']
                req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
                record={'requested_at':datetime.now(timezone.utc).isoformat(),'url':url,'start':start,'end':end,'total':self.size}
                try:
                    with urllib.request.urlopen(req,timeout=30) as response:
                        record.update(status=response.status,content_range=response.headers.get('Content-Range'),etag=response.headers.get('ETag'))
                        if response.status!=206 or record['content_range']!=f'bytes {start}-{end}/{self.size}':
                            raise ValueError('Refused nonmatching range response; no bulk fallback')
                        data=response.read(n+1)
                    if len(data)!=n:raise ValueError('Range length mismatch')
                    record.update(bytes=len(data),sha256=digest(data))
                    with binary.open('xb') as f:f.write(data)
                    with meta.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
                    self.requests.append({**record,'cache_hit':False})
                except Exception as e:
                    record.update(error_type=type(e).__name__,error=str(e))
                    with (self.cache/'retrieval-failures.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
                    self.requests.append(record);raise
            pieces.append(data);self.position+=n;count-=n
        return b''.join(pieces)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['inventory','headers','extract'])
    p.add_argument('--kind',choices=['vector','mask'],required=True)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--selection',type=Path,help='JSON list of exact member names for headers/extract')
    args=p.parse_args()
    if args.report.exists():raise SystemExit('Refusing to overwrite report')
    args.cache.mkdir(parents=True,exist_ok=True)
    name=f'GRWL_{args.kind}_V01.01.zip'
    item=next(x for x in json.loads(META.read_text())['files'] if x['key']==name)
    remote=RangeZip(item,args.cache)
    report={'schema_version':1,'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':args.mode,'source_file':name,
            'source_url':item['links']['self'],'archive_size_bytes':item['size'],'provider_archive_checksum':item['checksum'],
            'whole_archive_checksum_verified':False,'criteria_sha256':digest(CRITERIA.read_bytes()),'script_sha256':digest(Path(__file__).read_bytes()),
            'members':[],'status':'running'}
    try:
        with zipfile.ZipFile(remote) as z:
            if args.mode=='inventory':
                report['members']=[{'name':i.filename,'compressed_bytes':i.compress_size,'uncompressed_bytes':i.file_size,'crc32':f'{i.CRC:08x}','header_offset':i.header_offset} for i in z.infolist()]
            else:
                selection=json.loads(args.selection.read_text())
                for member in selection:
                    info=z.getinfo(member)
                    row={'name':member,'compressed_bytes':info.compress_size,'uncompressed_bytes':info.file_size,'crc32':f'{info.CRC:08x}'}
                    if args.mode=='headers':
                        if not member.endswith('.shp'):raise ValueError('Header mode expects SHP')
                        with z.open(member) as f:header=f.read(100)
                        row.update(header_sha256=digest(header),shape_type=struct.unpack_from('<i',header,32)[0],bbox=list(struct.unpack_from('<dddd',header,36)),complete_member_crc_verified=False)
                    else:
                        path=PurePosixPath(member)
                        if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe member path')
                        if info.file_size>LIMIT['max_member_uncompressed_bytes']:raise ValueError('Member too large')
                        target=args.cache/'members'/name/path
                        used=sum(f.stat().st_size for f in (args.cache/'members').rglob('*') if f.is_file()) if (args.cache/'members').exists() else 0
                        if not target.exists() and used+info.file_size>LIMIT['max_total_extracted_bytes']:raise ValueError('Extraction cap exceeded')
                        if target.exists():data=target.read_bytes()
                        else:
                            data=z.read(member) # zipfile checks full-member CRC during read
                            target.parent.mkdir(parents=True,exist_ok=True)
                            with target.open('xb') as f:f.write(data)
                        import zlib
                        if len(data)!=info.file_size or (zlib.crc32(data)&0xffffffff)!=info.CRC:raise ValueError('Member CRC/length mismatch')
                        row.update(sha256=digest(data),complete_member_crc_verified=True,cache_relative_path=str(target.relative_to(args.cache)))
                    report['members'].append(row)
        report['status']='passed'
    except Exception as e:
        report.update(status='failed',error_type=type(e).__name__,error=str(e))
    finally:
        report['range_requests']=remote.requests
        report['new_http_body_bytes']=sum(r.get('bytes',0) for r in remote.requests if not r.get('cache_hit'))
        report['total_cached_range_bytes']=sum(f.stat().st_size for f in (args.cache/'ranges').rglob('*.bin'))
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('members','range_requests')},indent=2))
    print('First members:',[x['name'] for x in report['members'][:30]])
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
