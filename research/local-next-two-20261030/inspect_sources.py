#!/usr/bin/env python3
"""Bounded source inspection for selection; no conversion, GEE or publication."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import struct
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent


def fetch_range(url, start, end, total):
    request = urllib.request.Request(url, headers={'Range':f'bytes={start}-{end}', 'Accept-Encoding':'identity'})
    with urllib.request.urlopen(request, timeout=45) as response:
        expected = f'bytes {start}-{end}/{total}'
        if response.status != 206 or response.headers.get('Content-Range') != expected:
            raise ValueError('Source did not honor bounded byte range; refusing bulk fallback')
        raw = response.read(end-start+2)
        if len(raw) != end-start+1:
            raise ValueError('Unexpected range length')
        return raw


class RemoteZip(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.requests = []
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position+offset if whence == 1 else self.size+offset
        if self.position < 0: raise ValueError('Negative offset')
        return self.position
    def read(self, count=-1):
        count = min(self.size-self.position, count if count >= 0 else self.size-self.position)
        if count <= 0: return b''
        if count > 2*1024*1024 or sum(r['bytes'] for r in self.requests)+count > 4*1024*1024:
            raise ValueError('Remote ZIP inspection exceeds bounded transfer budget')
        start=self.position;end=start+count-1
        raw=fetch_range(self.url,start,end,self.size)
        self.position += len(raw)
        self.requests.append({'start':start,'end':end,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        return raw


def inventory(archive):
    return [{'name':x.filename,'compressed_bytes':x.compress_size,'uncompressed_bytes':x.file_size,'crc32':f'{x.CRC:08x}'} for x in archive.infolist()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--grwl-record', type=Path, default=HERE/'upstream/grwl-latest-zenodo.json')
    parser.add_argument('--grwl-file', default='GRWL_summaryStats_V01.02.zip')
    args=parser.parse_args()
    if args.report.exists():raise SystemExit('Use a new report path; inspections are immutable')
    args.cache.mkdir(parents=True,exist_ok=True)
    summary={'retrieved_at':datetime.now(timezone.utc).isoformat(),'scope':'Source feasibility inspection only; no conversion or GEE parity claim.'}
    grwl=json.loads(args.grwl_record.read_text())
    item=next(x for x in grwl['files'] if x['key']==args.grwl_file)
    path=args.cache/item['key']
    if not path.exists():
        request=urllib.request.Request(item['links']['self'])
        with urllib.request.urlopen(request,timeout=60) as response:
            raw=response.read(item['size']+1)
        if len(raw)!=item['size']:raise ValueError('GRWL source length mismatch')
        if 'md5:'+hashlib.md5(raw).hexdigest()!=item['checksum']:raise ValueError('GRWL provider checksum mismatch')
        path.write_bytes(raw)
    raw=path.read_bytes()
    if len(raw)!=item['size'] or 'md5:'+hashlib.md5(raw).hexdigest()!=item['checksum']:
        raise ValueError('Cached GRWL differs from pinned source')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('GRWL ZIP CRC failed')
        members=inventory(z)
        dbf_name=next(n for n in z.namelist() if n.lower().endswith('.dbf') and '__MACOSX' not in n)
        dbf=z.read(dbf_name)
        rows=struct.unpack_from('<I',dbf,4)[0]
        header=struct.unpack_from('<H',dbf,8)[0]
        fields=[]
        for i in range(32,header-1,32):
            d=dbf[i:i+32]
            fields.append({'name':d[:11].split(b'\0')[0].decode(),'type':chr(d[11]),'width':d[16],'scale':d[17]})
        shp_name=next(n for n in z.namelist() if n.lower().endswith('.shp') and '__MACOSX' not in n)
        with z.open(shp_name) as f:shp=f.read(100)
        prj=z.read(next(n for n in z.namelist() if n.lower().endswith('.prj') and '__MACOSX' not in n)).decode()
        summary['grwl']={'source_doi':grwl['metadata']['doi'],'source_file':item['key'],'record_version_label':grwl['metadata'].get('version'),'source_url':item['links']['self'],'size_bytes':len(raw),'md5':hashlib.md5(raw).hexdigest(),
                         'sha256':hashlib.sha256(raw).hexdigest(),'provider_md5_verified':True,'zip_crc_verified':True,
                         'dbf_records':rows,'shape_type':struct.unpack_from('<I',shp,32)[0],'bbox':list(struct.unpack_from('<dddd',shp,36)),
                         'crs_wkt':prj,'fields':fields,'members':members,'uncompressed_bytes':sum(x['uncompressed_bytes'] for x in members),
                         'validation_limit':'Header/schema/ZIP inspection only; complete source-value and geometry validation pending.'}
    grip=json.loads((HERE/'upstream/grip-zenodo.json').read_text())
    item=next(x for x in grip['files'] if x['key']=='GRIP4_global_vector_fgdb.zip')
    reader=RemoteZip(item['links']['self'],item['size'])
    try:
        with zipfile.ZipFile(reader) as z:members=inventory(z)
        summary['grip']={'source_url':item['links']['self'],'size_bytes':item['size'],'provider_checksum':item['checksum'],
                         'provider_md5_verified':False,'sha256':None,'zip_crc_verified':False,'inspection':'Remote central directory only',
                         'members':members,'uncompressed_bytes':sum(x['uncompressed_bytes'] for x in members),'range_requests':reader.requests,
                         'downloaded_bytes':sum(x['bytes'] for x in reader.requests),
                         'validation_limit':'Whole-archive checksum, geodatabase feature count, schema and geometry remain unverified.'}
    except Exception as error:
        summary['grip']={'status':'range_inspection_unavailable','error_type':type(error).__name__,'error':str(error),
                         'source_url':item['links']['self'],'size_bytes':item['size'],'provider_checksum':item['checksum'],
                         'provider_md5_verified':False,'sha256':None,'range_requests':reader.requests}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({key:{k:v for k,v in value.items() if k not in ('members','fields','crs_wkt','range_requests')} if isinstance(value,dict) else value for key,value in summary.items()},indent=2))


if __name__=='__main__':main()
