#!/usr/bin/env python3
"""Stream the pinned GRIP4 FGDB to complete spatial GeoParquet and display PMTiles."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyogrio
from pyproj import CRS
import shapely
from dataset_config import load_config, config_sha256
from source import hashes, spreadsheet

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BBOX_NAMES=['xmin','ymin','xmax','ymax']
CODE_FILES=['build.py','source.py','dataset_config.py','catalog.py','validate.py','tiles.py',
 'serve.py','check_catalog.py','package.py','reproduce.py','test_validation.py','test_package.py',
 'test_catalog_release.py','pyproject.toml','uv.lock','package.json','package-lock.json','CONTRACT.md']

def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def sha256(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def check_space(path,minimum=40_000_000_000):
    if shutil.disk_usage(path).free < minimum: raise RuntimeError('Less than 40 GB free: stop before consuming shared disk headroom.')

def connect(scratch):
    con=duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET memory_limit='1GB'")
    con.execute('SET temp_directory=?',[str(scratch)])
    con.execute('SET preserve_insertion_order=false')
    return con

def morton(bounds):
    center=(bounds[:,:2]+bounds[:,2:])/2
    x=np.clip((center[:,0]+180)/360*65535,0,65535).astype(np.uint64)
    y=np.clip((center[:,1]+90)/180*65535,0,65535).astype(np.uint64)
    def spread(v):
        v=(v|(v<<8))&0x00ff00ff
        v=(v|(v<<4))&0x0f0f0f0f
        v=(v|(v<<2))&0x33333333
        return (v|(v<<1))&0x55555555
    return spread(x)|(spread(y)<<1)

def analytic_batch(batch,geom_name):
    names=['geometry' if name==geom_name else name for name in batch.schema.names]
    table=pa.Table.from_arrays([batch.column(i) for i in range(batch.num_columns)],names=names)
    geometry=shapely.from_wkb(table['geometry'].to_numpy())
    bounds=shapely.bounds(geometry)
    if not np.isfinite(bounds).all(): raise ValueError('Null, empty or nonfinite source geometry requires an explicit new contract.')
    bbox=pa.StructArray.from_arrays([pa.array(bounds[:,i]) for i in range(4)],names=BBOX_NAMES)
    table=table.append_column('bbox',bbox)
    return table,geometry,bounds

def metadata(schema,bbox,types,config):
    geo={'version':'1.1.0','primary_column':'geometry','columns':{'geometry':{
        'encoding':'WKB','geometry_types':types,'crs':CRS.from_user_input('OGC:CRS84').to_json_dict(),
        'bbox':bbox,'covering':{'bbox':{name:['bbox',name] for name in BBOX_NAMES}}}}}
    return schema.with_metadata({b'geo':json.dumps(geo,separators=(',',':')).encode(),
        b'folia:source_doi':config['source_doi'].encode(),b'folia:source_sha256':config['source_sha256'].encode()})

def dictionary(path):
    rows=next(iter(spreadsheet(path).values()))
    fields={}; current=None;countries={}
    for row in rows:
        cells={''.join(c for c in x['cell'] if not c.isdigit()):x['value'] for x in row}
        if cells.get('J') and cells.get('K','').isdigit(): countries[cells['K']]=cells['J']
        code=cells.get('C','')
        if code.startswith('gp_'):
            current=code
            fields[current]={'description':cells.get('A',code),'source_field':code if code=='gp_gripreg' else code.upper(),'values':{}}
        if current and cells.get('D'):
            if cells['D'].isdigit():fields[current]['values'][cells['D']]=cells.get('E','')
            else:fields[current]['value_format']={'pattern':cells['D'],'description':cells.get('E','')}
    if len(countries)<220 or countries.get('4')!='Afghanistan' or countries.get('0')!='Undefined':
        raise ValueError('Producer country-code dictionary missing or changed')
    fields['gp_rcy']['values']=countries
    return fields

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); config=load_config()
    pa.set_cpu_count(2);pa.set_io_thread_count(2)
    if a.output.exists(): raise SystemExit('Use a new output directory; prior runs remain immutable.')
    if subprocess.check_output(['git','status','--porcelain','--',str(HERE)],cwd=ROOT,text=True).strip():
        raise SystemExit('Commit the dataset workflow before building a release.')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    version=subprocess.run(['tippecanoe','--version'],capture_output=True,text=True,check=True)
    if (version.stdout+version.stderr).strip()!=config['tippecanoe_version']: raise ValueError('Unpinned tippecanoe version')
    source=a.source_cache/config['source_name']; pin=hashes(source)
    if pin!={'size_bytes':config['source_size'],'md5':config['source_md5'],'sha256':config['source_sha256']}:
        raise ValueError('Source bytes differ from canonical pins')
    # Verify extraction against compressed original on every build, not just a mutable cache marker.
    import zipfile,zlib
    with zipfile.ZipFile(source) as z:
        for item in z.infolist():
            if item.is_dir(): continue
            path=(a.source_cache/'extracted'/item.filename).resolve()
            if not path.is_relative_to((a.source_cache/'extracted').resolve()): raise ValueError('Unsafe archive path')
            crc=0; length=0
            with path.open('rb') as f:
                for data in iter(lambda:f.read(8*1024*1024),b''): crc=zlib.crc32(data,crc);length+=len(data)
            if length!=item.file_size or crc!=item.CRC: raise ValueError('Extracted source differs: '+item.filename)
    gdb=next((a.source_cache/'extracted').rglob('*.gdb'))
    info=pyogrio.read_info(gdb,layer=config['source_layer'])
    if info['features']!=config['expected_rows'] or not CRS(info['crs']).equals(CRS(4326),ignore_axis_order=True):
        raise ValueError('Source count or CRS changed')
    check_space(a.output.parent)
    a.output.mkdir(parents=True)
    scratch=a.output/'scratch';scratch.mkdir()
    folder=a.output/'grip';folder.mkdir();(folder/'data').mkdir()
    shutil.copyfile(HERE/'dataset.yaml',a.output/'dataset.yaml')
    dict_path=a.source_cache/'GRIP4_AttributeDescription.xlsx'
    if sha256(dict_path)!=config['attribute_dictionary_sha256']: raise ValueError('Attribute dictionary changed')
    codebook=dictionary(dict_path)
    shutil.copyfile(dict_path,folder/'original-attribute-dictionary.xlsx')
    write_json(folder/'attribute-codes.json',codebook)
    raw=scratch/'source-order.parquet'; geojson=scratch/'tiles.geojsonl'
    rows=0; nulls=Counter();regions=Counter();classes=Counter();types=Counter();invalid=0;vertices=0
    lo=np.array([np.inf,np.inf]);hi=np.array([-np.inf,-np.inf]);preview=[]
    raw_writer=None;previous_fid=0
    fid_name=config['fid_column'];region_name=config['region_field'];class_name=config['road_type_field']
    with pyogrio.open_arrow(gdb,layer=config['source_layer'],use_pyarrow=True,return_fids=True,batch_size=config['batch_size']) as (meta,reader), geojson.open('w') as js:
        if reader.schema.names!=config['source_columns'] or [str(f.type) for f in reader.schema]!=config['source_arrow_types']: raise ValueError('Source field names/order/types changed')
        for batch_no,batch in enumerate(reader):
            table,geom,bounds=analytic_batch(batch,meta['geometry_name'] or 'wkb_geometry')
            ids=table[fid_name].to_numpy(); regions_array=table[region_name].to_numpy();class_array=table[class_name].to_numpy()
            if ids[0]<=previous_fid or not (np.diff(ids)>0).all(): raise ValueError('Source IDs are not unique and increasing')
            previous_fid=int(ids[-1])
            if not np.isin(regions_array,np.arange(1,8)).all(): raise ValueError('Unexpected or missing region code')
            if table[region_name].null_count or table[class_name].null_count: raise ValueError('Null region/class needs explicit display mapping')
            for field in table.schema: nulls[field.name]+=table[field.name].null_count
            regions.update(int(v) for v in regions_array); classes.update(int(v) for v in class_array)
            unique,count=np.unique(shapely.get_type_id(geom),return_counts=True)
            for kind,n in zip(unique,count): types[str(int(kind))]+=int(n)
            invalid+=int(np.sum(~shapely.is_valid(geom))); vertices+=int(np.sum(shapely.get_num_coordinates(geom)))
            lo=np.minimum(lo,bounds[:,:2].min(axis=0));hi=np.maximum(hi,bounds[:,2:].max(axis=0))
            table=table.append_column('_spatial_order',pa.array(morton(bounds)))
            if raw_writer is None: raw_writer=pq.ParquetWriter(raw,table.schema,compression='zstd',compression_level=3)
            raw_writer.write_table(table,row_group_size=config['batch_size'])
            # All source features enter the display builder. Thinning is declared and audited separately.
            geometries=shapely.to_geojson(geom)
            for identity,region,road_type,geometry in zip(ids,regions_array,class_array,geometries):
                js.write('{"type":"Feature","id":'+str(identity)+',"properties":{'+json.dumps(region_name)+':'+str(region)+','+json.dumps(class_name)+':'+str(road_type)+'},"geometry":'+geometry+'}\n')
            if batch_no%8==0:
                for g in geom[::max(1,len(geom)//8)]:
                    parts=shapely.get_parts(g)
                    if len(parts): preview.append(shapely.get_coordinates(parts[0])[::max(1,shapely.get_num_coordinates(parts[0])//20)].tolist())
            rows+=table.num_rows
            if batch_no%20==0: print(f'source: {rows:,} rows',flush=True);check_space(a.output)
    raw_writer.close()
    if rows!=config['expected_rows']: raise ValueError('Source row count changed')
    if set(types)-{'1','5'}: raise ValueError('Unexpected non-line source geometry')
    geometry_types=[{'1':'LineString','5':'MultiLineString'}[x] for x in sorted(types)]
    bbox=[*lo.tolist(),*hi.tolist()]
    data_schema=pq.read_schema(raw).remove(pq.read_schema(raw).get_field_index('_spatial_order'))
    data_schema=metadata(data_schema,bbox,geometry_types,config)
    print('sorting into seven spatially ordered regional files',flush=True)
    with connect(scratch/'duckdb') as con:
        query=f'SELECT * EXCLUDE (_spatial_order) FROM read_parquet(?) ORDER BY "{region_name}", _spatial_order, "{fid_name}"'
        stream=con.execute(query,[str(raw)]).to_arrow_reader(batch_size=config['batch_size'])
        writer=None;current=None
        for batch in stream:
            table=pa.Table.from_batches([batch]); codes=table[region_name].to_numpy()
            for region in np.unique(codes):
                if current!=int(region):
                    if writer: writer.close()
                    current=int(region)
                    writer=pq.ParquetWriter(folder/'data'/f'region-{current}.parquet',data_schema,compression='zstd',compression_level=9,version='2.6',write_statistics=True)
                selected=table.filter(pa.array(codes==region)).cast(data_schema)
                writer.write_table(selected,row_group_size=config['batch_size'])
        if writer: writer.close()
    raw.unlink()
    print('building display tiles',flush=True);check_space(a.output)
    command=['tippecanoe','--quiet','--output','grip/grip.pmtiles','--layer','roads','--name',config['title'],
      '--description','GRIP4 2018 roads; simplified and thinned at all zooms. Use complete GeoParquet for analysis.',
      '--attribution','Meijer et al. (2018), CC BY 4.0; conversion by Folia','--minimum-zoom','0',
      '--maximum-zoom',str(config['pmtiles_maxzoom']),'--simplification','1','--buffer','5',
      '--drop-densest-as-needed','--full-detail','12','--low-detail','12','--minimum-detail','12','--maximum-tile-bytes','500000','--maximum-tile-features','200000',
      '--temporary-directory','scratch','scratch/tiles.geojsonl']
    subprocess.run(command,cwd=a.output,env={**os.environ,'TIPPECANOE_MAX_THREADS':'2'},check=True)
    shutil.rmtree(scratch)
    descriptions={name:entry['description']+'; producer codes retained (0 is unspecified, not null).' for name,entry in codebook.items()}
    descriptions.update({fid_name:'Original File Geodatabase feature identifier, unique within this pinned source.',
        'geometry':'Unchanged source WKB coordinates and line parts; OGC:CRS84 longitude/latitude.',
        'bbox':'Per-feature xmin, ymin, xmax, ymax in source longitude/latitude, for spatial filtering.',
        'Shape_Length':'Original File Geodatabase shape-length value in the source coordinate system; not a newly calculated geodesic length or a metre measurement.'})
    summary={'rows':rows,'bbox':bbox,'regions':dict(sorted(regions.items())), 'road_classes':dict(sorted(classes.items())),
      'fields':[{'name':f.name,'type':str(f.type),'description':descriptions.get(f.name,descriptions.get(f.name.lower(),'Original producer field, preserved without reinterpretation.'))} for f in data_schema],
      'null_counts':dict(nulls),'geometry_types':geometry_types,'geometry_type_counts':dict(types),
      'invalid_source_geometries_preserved':invalid,'vertices':vertices,'max_source_fid':previous_fid,
      'preview_lines':preview,'source_reader':f'pyogrio {pyogrio.__version__}, GDAL {pyogrio.__gdal_version_string__}',
      'display':{'minimum_zoom':0,'maximum_zoom':config['pmtiles_maxzoom'],'simplification':1,'tile_extent':4096,
        'max_tile_bytes':500000,'max_tile_features':200000,'thinning':'drop-densest-as-needed at every zoom',
        'input_features':rows,'layer':'roads','id_field':fid_name,'attributes':[region_name,class_name],
        'limits':'Not a complete network at any zoom; source IDs/retention and deterministic geometry samples validated separately. Quantization, clipping and simplification apply.'}}
    from catalog import build_catalog
    build_catalog(a.output,summary,config,revision)
    assets={p.relative_to(a.output).as_posix():{'size_bytes':p.stat().st_size,'sha256':sha256(p)} for p in sorted(a.output.rglob('*')) if p.is_file()}
    manifest={'schema_version':1,'source':config,'effective_config_sha256':config_sha256(config),
      'dataset_record_sha256_at_build':sha256(a.output/'dataset.yaml'),'conversion_git_commit':revision,
      'build_input_sha256':{name:sha256(HERE/name) for name in CODE_FILES},'assets':assets,
      'source_quality':{k:v for k,v in summary.items() if k!='preview_lines'},
      'software':{'python':platform.python_version(),'packages':{n:importlib.metadata.version(n) for n in ['pyarrow','pyogrio','duckdb','shapely','pyproj']},
        'tippecanoe':config['tippecanoe_version'],'tippecanoe_sha256':sha256(shutil.which('tippecanoe'))},
      'tile_command':command,'publication_status':'local_only'}
    write_json(a.output/'manifest.json',manifest)
    print(json.dumps({'rows':rows,'assets':len(assets),'manifest_sha256':sha256(a.output/'manifest.json')}),flush=True)
if __name__=='__main__': main()
