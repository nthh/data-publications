#!/usr/bin/env python3
"""Fetch, checksum, safely extract and inspect the pinned GRIP4 producer inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import xml.etree.ElementTree as ET

FILES = {
 'GRIP4_global_vector_fgdb.zip': (2334355294, '526db5eb478f4c990e27fcbc471abf4b'),
 'GRIP4_AttributeDescription.xlsx': (23947, '6b4a44035fc90036398cd9d5fe260d60'),
}
BASE = 'https://zenodo.org/api/records/6420961/files/'

def hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8*1024*1024), b''):
            md5.update(data); sha.update(data)
    return {'size_bytes': path.stat().st_size, 'md5': md5.hexdigest(), 'sha256': sha.hexdigest()}

def spreadsheet(path):
    ns = {'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        strings = [''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        result = {}
        for name in archive.namelist():
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                rows = []
                for row in ET.fromstring(archive.read(name)).findall('.//x:row', ns):
                    cells = []
                    for cell in row.findall('x:c', ns):
                        val = cell.find('x:v',ns)
                        text = val.text if val is not None else ''
                        if cell.get('t') == 's': text = strings[int(text)]
                        cells.append({'cell':cell.get('r'), 'value':text})
                    rows.append(cells)
                result[name] = rows
        return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--download',action='store_true')
    a=p.parse_args()
    if a.report.exists(): raise SystemExit('Report exists; choose a new path to preserve evidence.')
    a.cache.mkdir(parents=True,exist_ok=True)
    receipt={'source_doi':'10.5281/zenodo.6420961','files':{}}
    for name,(size,md5) in FILES.items():
        path=a.cache/name
        if not path.exists() and a.download:
            partial=path.with_suffix(path.suffix+'.part')
            subprocess.run(['curl','--fail','--location','--retry','5','--retry-delay','3',
                '--continue-at','-','--output',str(partial),BASE+name+'/content'],check=True)
            pin=hashes(partial)
            if pin['size_bytes']!=size or pin['md5']!=md5: raise ValueError(f'Invalid source: {name}: {pin}')
            partial.rename(path)
        pin=hashes(path)
        if pin['size_bytes']!=size or pin['md5']!=md5: raise ValueError(f'Invalid source: {name}: {pin}')
        receipt['files'][name]={**pin,'url':BASE+name+'/content'}
        print(name, json.dumps(pin), flush=True)
    source=a.cache/'GRIP4_global_vector_fgdb.zip'
    extracted=a.cache/'extracted'
    marker=extracted/'.complete.json'
    with zipfile.ZipFile(source) as archive:
        bad=archive.testzip()
        if bad: raise ValueError(f'Bad CRC: {bad}')
        receipt['zip_entries']=len(archive.infolist())
        receipt['zip_uncompressed_bytes']=sum(x.file_size for x in archive.infolist())
        receipt['zip_crc']='passed'
        if not marker.exists():
            extracted.mkdir(exist_ok=True)
            for member in archive.infolist():
                target=(extracted/member.filename).resolve()
                if not target.is_relative_to(extracted.resolve()): raise ValueError('Unsafe ZIP member')
                archive.extract(member, extracted)
            marker.write_text(json.dumps(receipt['files']['GRIP4_global_vector_fgdb.zip']))
    receipt['attribute_dictionary']=spreadsheet(a.cache/'GRIP4_AttributeDescription.xlsx')
    import pyogrio
    gdb=next(extracted.rglob('*.gdb'))
    receipt['layers']=pyogrio.list_layers(gdb).tolist()
    receipt['layer_info']={}
    receipt['arrow_schemas']={}
    for name,_ in receipt['layers']:
        info=pyogrio.read_info(gdb,layer=name,force_feature_count=True,force_total_bounds=True)
        receipt['layer_info'][name]={k:(v.tolist() if hasattr(v,'tolist') else v) for k,v in info.items()}
        with pyogrio.open_arrow(gdb,layer=name,use_pyarrow=True,return_fids=True,batch_size=4) as (meta,stream):
            receipt['arrow_schemas'][name]={'schema':str(stream.schema),'sample':stream.read_next_batch().drop_columns([meta['geometry_name'] or 'wkb_geometry']).to_pylist()}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'layers':receipt['layers'],'layer_info':receipt['layer_info'],'arrow_schemas':receipt['arrow_schemas']},indent=2))
if __name__=='__main__': main()
