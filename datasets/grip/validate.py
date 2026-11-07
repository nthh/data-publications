#!/usr/bin/env python3
"""Validate every source feature and field, cloud formats, catalog and local HTTP."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import urllib.request
import yaml
import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyogrio
import shapely
from pyproj import CRS
from dataset_config import load_config,config_sha256
from build import sha256,write_json,connect,BBOX_NAMES
from source import hashes

HERE=Path(__file__).resolve().parent

def require(condition,message):
    if not condition: raise ValueError(message)

def compare_columns(expected,actual):
    require(expected.column_names==actual.column_names,'Missing/renamed/unexpected analytic source columns')
    require(expected.num_rows==actual.num_rows,'Lost or extra rows')
    for field in expected.schema:
        left,right=expected[field.name].combine_chunks(),actual[field.name].combine_chunks()
        require(left.type==right.type,f'Source field type changed: {field.name}')
        require(left.is_null().equals(right.is_null()),f'Source null mask changed: {field.name}')
        if pa.types.is_floating(left.type):
            # Compare all non-null IEEE754 bits, including signed zero and NaN payloads.
            valid=pc.invert(left.is_null())
            a=pc.filter(left,valid).to_numpy();b=pc.filter(right,valid).to_numpy()
            require(np.array_equal(a.view(np.uint8),b.view(np.uint8)),f'Source floating bits changed: {field.name}')
        else: require(left.equals(right),f'Source values changed: {field.name}')
    return expected.num_rows*len(expected.column_names)

def check_assets(root,manifest):
    for name,pin in manifest['assets'].items():
        p=(root/name).resolve()
        require(p.is_relative_to(root) and p.is_file(),'Unsafe or missing manifest asset: '+name)
        require(p.stat().st_size==pin['size_bytes'] and sha256(p)==pin['sha256'],'Asset size/hash mismatch: '+name)
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    require(actual==set(manifest['assets']),'Manifest asset inventory differs from release files')

def http_check(root,config):
    from serve import server
    files=sorted((root/'grip/data').glob('*.parquet'))
    with server(root) as httpd:
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{httpd.server_port}/'
        try:
            for relative,magic in [(files[0].relative_to(root).as_posix(),b'PAR1'),('grip/grip.pmtiles',b'PMTiles\x03')]:
                request=urllib.request.Request(base+relative,headers={'Range':f'bytes=0-{len(magic)-1}','Origin':'https://example.org'})
                with urllib.request.urlopen(request) as r:
                    require(r.status==206 and r.read()==magic,'HTTP range bytes differ')
                    require(r.headers.get('Access-Control-Allow-Origin')=='*','Missing CORS')
            # Same bounded geographic predicate against all seven files, both local and HTTP.
            urls=[base+p.relative_to(root).as_posix() for p in files]
            with duckdb.connect() as con:
                con.execute('SET threads=2');con.execute("SET memory_limit='1GB'");con.execute('LOAD httpfs')
                fid=config['fid_column'];roadtype=config['road_type_field']
                sql=f'SELECT "{fid}","{roadtype}",geometry FROM read_parquet(?) WHERE bbox.xmin>=-1 AND bbox.xmax<=1 AND bbox.ymin>=50 AND bbox.ymax<=52 ORDER BY "{fid}"'
                expected=con.execute(sql,[[str(p) for p in files]]).fetchall()
                actual=con.execute(sql,[urls]).fetchall()
                require(len(actual)>0 and actual==expected,'HTTP spatial subset differs')
            return {'status':'passed','range_and_cors':True,'duckdb_spatial_subset_rows':len(actual),'partitions_read':len(files),
               'scope':'Loopback server only. Source Cooperative hosting remains untested.'}
        finally: httpd.shutdown();thread.join()

def validate(root,cache,http=False):
    root=root.resolve();config=load_config();manifest=json.loads((root/'manifest.json').read_text())
    pa.set_cpu_count(2);pa.set_io_thread_count(2)
    require(manifest['source']==config and manifest['effective_config_sha256']==config_sha256(config),'Canonical source/build config changed')
    snapshot=root/'dataset.yaml';require(sha256(snapshot)==manifest['dataset_record_sha256_at_build'],'Snapshot changed')
    record=yaml.safe_load(snapshot.read_text())
    require({'id':record['id'],'title':record['title'],**record['source'],**record['build']}==config,'Snapshot configuration mismatch')
    source=cache/config['source_name'];pin=hashes(source)
    require(pin=={'size_bytes':config['source_size'],'sha256':config['source_sha256'],'md5':config['source_md5']},'Wrong source archive')
    check_assets(root,manifest)
    for name,digest in manifest['build_input_sha256'].items(): require(sha256(HERE/name)==digest,'Workflow input changed: '+name)
    files=sorted((root/'grip/data').glob('*.parquet'));require(len(files)==7,'Expected seven regional partitions')
    fid=config['fid_column'];region=config['region_field'];total=0;nulls=Counter();regions=Counter();groups=0;invalid=0;vertices=0
    bbox=np.array([np.inf,np.inf,-np.inf,-np.inf]);schema=None
    for index,path in enumerate(files,1):
        parquet=pq.ParquetFile(path);geo=json.loads(parquet.schema_arrow.metadata[b'geo']);column=geo['columns']['geometry']
        require(geo['version']=='1.1.0' and geo['primary_column']=='geometry' and column['encoding']=='WKB','Invalid GeoParquet metadata')
        require(CRS.from_json_dict(column['crs']).equals(CRS('OGC:CRS84')),'GeoParquet CRS mismatch')
        require(column['covering']['bbox']=={name:['bbox',name] for name in BBOX_NAMES},'Incorrect bbox covering')
        require(column['bbox']==manifest['source_quality']['bbox'],'File envelope differs')
        if schema is None:schema=parquet.schema_arrow.remove_metadata()
        require(schema.equals(parquet.schema_arrow.remove_metadata()),'Partition schema differs')
        for j in range(parquet.metadata.num_row_groups):
            group=parquet.metadata.row_group(j);groups+=1
            require(group.num_rows<=config['batch_size'],'Oversized row group')
            stats={group.column(k).path_in_schema:group.column(k).statistics for k in range(group.num_columns)}
            require(all(stats.get('bbox.'+n) and stats['bbox.'+n].has_min_max for n in BBOX_NAMES),'Missing bbox statistics')
        last_order=-1
        for batch in parquet.iter_batches(batch_size=config['batch_size']):
            table=pa.Table.from_batches([batch]);geometries=shapely.from_wkb(table['geometry'].to_numpy());bounds=shapely.bounds(geometries)
            require(np.isfinite(bounds).all(),'Empty/null/nonfinite geometry')
            for k,name in enumerate(BBOX_NAMES):require(np.array_equal(pc.struct_field(table['bbox'],name).to_numpy(),bounds[:,k]),'Wrong per-feature bbox')
            # Independently compute the Morton key using bit positions, unlike the builder's mask expansion.
            cx=np.clip(((bounds[:,0]+bounds[:,2])/2+180)/360*65535,0,65535).astype(np.uint64)
            cy=np.clip(((bounds[:,1]+bounds[:,3])/2+90)/180*65535,0,65535).astype(np.uint64)
            order=np.zeros(len(bounds),dtype=np.uint64)
            for bit in range(16):order|=((cx>>bit)&1)<<(2*bit);order|=((cy>>bit)&1)<<(2*bit+1)
            require(order[0]>=last_order and (order[1:]>=order[:-1]).all(),'Partition not spatially ordered')
            last_order=int(order[-1]);require(pc.all(pc.equal(table[region],index)).as_py(),'Wrong region partition')
            bbox[:2]=np.minimum(bbox[:2],bounds[:,:2].min(axis=0));bbox[2:]=np.maximum(bbox[2:],bounds[:,2:].max(axis=0))
            total+=table.num_rows;invalid+=int(np.count_nonzero(~shapely.is_valid(geometries)));vertices+=int(np.sum(shapely.get_num_coordinates(geometries)))
            regions[str(index)]+=table.num_rows
            for name in table.column_names:nulls[name]+=table[name].null_count
    require(total==config['expected_rows'],'Lost or duplicated output features')
    require(bbox.tolist()==manifest['source_quality']['bbox'],'Global bounds differ')
    require(dict(nulls)==manifest['source_quality']['null_counts'],'Null summary differs')
    require(dict(regions)=={str(k):v for k,v in manifest['source_quality']['regions'].items()},'Regional summary differs')
    require(vertices==manifest['source_quality']['vertices'] and invalid==manifest['source_quality']['invalid_source_geometries_preserved'],'Geometry quality differs')
    print('GeoParquet structure passed; comparing every source row',flush=True)
    gdb=next((cache/'extracted').rglob('*.gdb'));comparisons=0;source_rows=0
    scratch=root.parent/(root.name+'-validation-scratch');scratch.mkdir(exist_ok=False)
    try:
        with connect(scratch) as con,pyogrio.open_arrow(gdb,layer=config['source_layer'],use_pyarrow=True,return_fids=True,batch_size=32768) as (meta,source_reader):
            query=f'SELECT * EXCLUDE (bbox) FROM read_parquet(?) ORDER BY "{fid}"'
            # RecordBatchReader boundaries differ from GDAL's; consume exactly each source batch size.
            reader=con.execute(query,[str(root/'grip/data/*.parquet')]).to_arrow_reader(batch_size=32768)
            pending=None
            def take(n):
                nonlocal pending
                parts=[]
                while n:
                    if pending is None or not pending.num_rows:
                        try:pending=pa.Table.from_batches([reader.read_next_batch()])
                        except StopIteration:raise ValueError('Output ended before source')
                    count=min(n,pending.num_rows);parts.append(pending.slice(0,count));pending=pending.slice(count);n-=count
                return pa.concat_tables(parts)
            for batch_no,batch in enumerate(source_reader):
                names=['geometry' if name==(meta['geometry_name'] or 'wkb_geometry') else name for name in batch.schema.names]
                expected=pa.Table.from_arrays([batch.column(i) for i in range(batch.num_columns)],names=names)
                actual=take(batch.num_rows)
                comparisons+=compare_columns(expected,actual)
                source_rows+=batch.num_rows
                if batch_no%40==0:print(f'parity: {source_rows:,} rows',flush=True)
            require(pending is None or pending.num_rows==0,'Output has extra rows')
            try:reader.read_next_batch();raise ValueError('Output has trailing extra rows')
            except StopIteration:pass
    finally:
        import shutil
        shutil.rmtree(scratch)
    require(source_rows==total,'Source/output counts differ')
    from check_catalog import check_catalog
    catalog=check_catalog(root);require(catalog['status']=='passed','Catalog links/assets failed: '+str(catalog))
    from tiles import validate_tiles
    tiles=validate_tiles(root,config,manifest['source_quality'])
    result={'status':'passed','release_manifest_sha256':sha256(root/'manifest.json'),'source_sha256':pin['sha256'],
      'source_rows':source_rows,'exact_cells_compared_including_fid_and_wkb':comparisons,'exact_geometry_records':source_rows,
      'geoparquet':{'status':'passed','partitions':len(files),'row_groups':groups,'rows':total,'morton_ordered_within_region':True,'bbox_statistics':True},
      'null_counts':dict(nulls),'regions':dict(regions),'vertices':vertices,'invalid_source_geometries_preserved':invalid,
      'catalog':catalog,'pmtiles':tiles,'http':http_check(root,config) if http else {'status':'not_run'},
      'limits':['Independent source reread and explicit per-feature comparison, but build and validator share the GDAL OpenFileGDB decoder.',
        'No GEE requests, independent observational research validation, public hosting test or registry submission.']}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--source-cache',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--http',action='store_true');a=p.parse_args()
    if a.report.exists():raise SystemExit('Report exists; keep prior evidence and choose a new path.')
    try:result=validate(a.directory,a.source_cache,a.http)
    except Exception as e:
        a.report.parent.mkdir(parents=True,exist_ok=True);write_json(a.report,{'status':'failed','error':str(e)});raise
    a.report.parent.mkdir(parents=True,exist_ok=True);write_json(a.report,result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
