#!/usr/bin/env python3
"""Bind fixed samples and bounded GEE request plans to immutable local releases."""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import shapely
from shapely.geometry import mapping
import yaml
from capture import sha, validate_plan

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / 'research/gee-release-validation-20261106/metadata-plan.json'
CRITERIA = ROOT / 'research/gee-release-validation-20261106/criteria.json'
LAYERS = [
    ('hydrolakes', 'hydrolakes', 'hydrolakes-polygons', ['Hylak_id']),
    ('lakeatlas-polygons', 'lakeatlas', 'lakeatlas-polygons', ['Hylak_id']),
    ('lakeatlas-points', 'lakeatlas', 'lakeatlas-pour-points', ['Hylak_id']),
    ('free-flowing-rivers', 'free-flowing-rivers', 'ffr-reach-network-v1', ['GOID']),
    ('grwl-raw', 'grwl-raw', 'grwl-raw-observations', ['lon', 'lat', 'segmentID', 'segmentInd']),
]
DERIVED = {'source_row','source_tile','feature_id','width_valid'}
ALIASES = {'lakeFlag':['lakeFlag','lakeflag'], 'elev_m':['elev_m','elev'], 'Shape_Length':['Shape_Length','Shape_Leng','SHAPE_LENG'], 'Shape_Area':['Shape_Area','SHAPE_AREA']}


def encode(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


def group_indices(n):
    m = min(128, n)
    return [0] if m == 1 else sorted({i * (n - 1) // (m - 1) for i in range(m)})


def rectangles(x, y):
    x = (x + 180) % 360 - 180
    lo, hi = x - .0001, x + .0001
    spans = [(lo,hi)]
    if lo < -180:
        spans = [(lo+360,180),(-180,hi)]
    if hi > 180:
        spans = [(lo,180),(-180,hi-360)]
    a,b = max(-90,y-.0001),min(90,y+.0001)
    return [[[[l,a],[h,a],[h,b],[l,b],[l,a]]] for l,h in spans]


def sample_layer(layer, dataset_id, asset_id, keys, data_root, output, metadata):
    record_path = ROOT / 'datasets' / dataset_id / 'dataset.yaml'
    record = yaml.safe_load(record_path.read_text())
    pub = record['publication']; manifest_path = ROOT / pub['manifest_path']
    if sha(manifest_path) != pub['manifest_sha256']:
        raise ValueError('Canonical manifest checksum mismatch')
    manifest = json.loads(manifest_path.read_text())
    asset = next(a for a in manifest['assets'] if a['asset_id'] == asset_id)
    parquet = data_root / pub['local_bundle_directory'] / asset['href']
    observed = sha(parquet)
    if observed != asset['sha256'] or parquet.stat().st_size != asset['size_bytes']:
        raise ValueError('Immutable analytical asset checksum or size mismatch')
    pf = pq.ParquetFile(parquet)
    if pf.metadata.num_rows != asset['row_count']:
        raise ValueError('Parquet/manifest row count mismatch')
    geom = asset['geometry_column']
    fields = {}
    for field in pf.schema_arrow:
        if field.name in (geom, 'bbox'):
            continue
        role = 'source_fid' if field.name == 'OBJECTID' else 'derived' if field.name in DERIVED else 'geometry_derived' if field.name in ('Shape_Area','Shape_Length') else 'source'
        fields[field.name] = {'type':str(field.type),'role':role,'gee_aliases':ALIASES.get(field.name,[field.name])}
    cols = list(fields) + [geom]
    rows = {}
    def add(row, group, offset):
        local_id = row['feature_id'] if dataset_id == 'grwl-raw' else row[keys[0]]
        geometry = shapely.from_wkb(row[geom])
        if geometry.is_empty:
            raise ValueError('Sample has empty source geometry')
        rows[str(local_id)] = {'local_id':str(local_id),'properties':{k:encode(row[k]) for k in fields},'geometry':mapping(geometry),'row_group':group,'row_offset':offset}
    for g in group_indices(pf.metadata.num_row_groups):
        table = pf.read_row_group(g, columns=cols, use_threads=False)
        n = len(table)
        offsets = sorted({0,n//3,2*n//3,n-1})
        for offset,row in zip(offsets, table.take(pa.array(offsets)).to_pylist()):
            add(row,g,offset)
    absent_extra = []
    if dataset_id != 'grwl-raw':
        extras = ds.dataset(parquet,format='parquet').to_table(columns=cols,filter=ds.field(keys[0]).isin(list(range(1,11))),use_threads=False).to_pylist()
        extra_ids = {r[keys[0]] for r in extras}
        absent_extra = sorted(set(range(1,11))-extra_ids)
        for row in extras:
            # Keep original sampling coordinates if a control already exists.
            if str(row[keys[0]]) not in rows:
                add(row,None,None)
    selected = sorted(rows.values(),key=lambda r:int(r['local_id']))
    sample = {'schema_version':1,'dataset_id':layer,'source':{'dataset_id':dataset_id,'release':pub['release'],'manifest_path':pub['manifest_path'],'manifest_sha256':pub['manifest_sha256'],'asset_id':asset_id,'parquet_sha256':observed,'size_bytes':parquet.stat().st_size,'row_count':pf.metadata.num_rows},'criteria_sha256':sha(CRITERIA),'selection_script_sha256':sha(__file__),'lock_sha256':sha(Path(__file__).with_name('uv.lock')),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'key_fields':keys,'geometry_column':geom,'fields':fields,'features':selected,'absent_local_extra_ids':absent_extra}
    target = output / f'{layer}-sample.json'
    target.write_text(json.dumps(sample,separators=(',',':'),allow_nan=False)+'\n')
    resource = next(r['resource'] for r in metadata['requests'] if r['id']==layer)
    requests = [{'id':f'{layer}-before','resource':resource},{'id':f'{layer}-count','operation':'count','resource':resource}]
    batches = [selected[i:i+(8 if dataset_id=='grwl-raw' else 32)] for i in range(0,len(selected),8 if dataset_id=='grwl-raw' else 32)]
    for index,batch in enumerate(batches):
        params = {'pageSize':100}
        if dataset_id == 'grwl-raw':
            polys = []
            for row in batch:
                xy = shapely.get_coordinates(shapely.geometry.shape(row['geometry']))[0]
                polys.extend(rectangles(float(xy[0]),float(xy[1])))
            params['region'] = json.dumps({'type':'MultiPolygon','coordinates':polys},separators=(',',':'))
        else:
            params['filter'] = ' OR '.join(f'{keys[0]} = {int(row["properties"][keys[0]])}' for row in batch)
        request = {'id':f'{layer}-features-{index:03d}','resource':resource+':listFeatures','params':params,'paginate':True,'maximum_pages':8,'maximum_rows':800}
        if dataset_id == 'grwl-raw':
            request['selected_local_ids'] = [r['local_id'] for r in batch]
        requests.append(request)
    if dataset_id in {'grwl-raw', 'free-flowing-rivers'}:
        count = requests.pop(1)
        count['timeout_seconds'] = 180
        requests.append(count)
    requests.append({'id':f'{layer}-after','resource':resource})
    plan = {'schema_version':1,'dataset_id':layer,'sample_sha256':sha(target),'sample_filename':target.name,'criteria_sha256':sha(CRITERIA),'quota_project':metadata['quota_project'],'limits':{'maximum_requests':256,'maximum_total_bytes':512000000,'maximum_response_bytes':64000000,'timeout_seconds':45,'maximum_elapsed_seconds':7200},'requests':requests}
    validate_plan(plan)
    (output / f'{layer}-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    controls = {'sample_count':len(selected),'sample_sha256':sha(target),'asset_sha256':observed,'plan_sha256':sha(output/f'{layer}-plan.json'),'selected_local_ids':[r['local_id'] for r in selected],'row_groups':group_indices(pf.metadata.num_row_groups),'absent_local_extra_ids':absent_extra}
    for name in ['Continent','CONTINENT','Country','COUNTRY','source_tile']:
        if name in fields:
            controls[name] = sorted({str(r['properties'].get(name)) for r in selected})
    print(json.dumps({'dataset':layer,'sample_count':len(selected),'bytes':target.stat().st_size,'query_batches':len(batches)}),flush=True)
    return controls


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args()
    owned=[str(Path(__file__).resolve()),str(CRITERIA),str(Path(__file__).with_name('uv.lock'))]
    if subprocess.check_output(['git','status','--porcelain','--',*owned],cwd=ROOT,text=True).strip():
        raise SystemExit('Commit sampling code, criteria and environment before selection.')
    a.output.mkdir(parents=True,exist_ok=False)
    metadata=json.loads(META.read_text())
    summary={}
    for layer,dataset,asset,keys in LAYERS:
        summary[layer]=sample_layer(layer,dataset,asset,keys,a.data_root,a.output,metadata)
    (a.output/'sample-inventory.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':
    main()
