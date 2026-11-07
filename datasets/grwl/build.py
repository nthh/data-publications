#!/usr/bin/env python3
"""Build a deterministic local GRWL V01.02 GeoParquet and PMTiles release."""
from __future__ import annotations
import argparse, hashlib, json, math, os, platform, shutil, struct, subprocess, zipfile
from importlib.metadata import version as package_version
from collections import Counter
from decimal import Decimal
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pyproj import CRS
from dataset_config import load_config, config_sha256
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CONFIG=load_config()
CODE_FILES=['build.py','catalog.py','validate.py','serve.py','dataset_config.py','pyproject.toml','uv.lock','package.json','package-lock.json','tippecanoe.lock.json','fault_tests.py','test_serve.py','reproduce.py','README.md','VALIDATION.md']
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path,obj): Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def parse_source(path):
    raw=path.read_bytes()
    pin=CONFIG
    if (len(raw),hashlib.md5(raw).hexdigest(),sha(path)) != (pin['source_size'],pin['source_md5'],pin['source_sha256']): raise ValueError('Pinned ZIP size/MD5/SHA-256 mismatch')
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        if bad: raise ValueError('ZIP CRC failure: '+bad)
        dbf,shp,prj=(z.read('GRWL_summaryStats.'+ext) for ext in ('dbf','shp','prj'))
    if not CRS.from_wkt(prj.decode()).equals(CRS.from_epsg(4326),ignore_axis_order=True): raise ValueError('Unexpected CRS')
    rows=struct.unpack_from('<I',dbf,4)[0]; header,row_size=struct.unpack_from('<HH',dbf,8)
    fields=[]; offset=1
    for i in range(32,header-1,32):
        f=dbf[i:i+32]; name=f[:11].split(b'\0')[0].decode('ascii'); kind=chr(f[11]); width,scale=f[16],f[17]
        if kind not in 'NF': raise ValueError(f'Unexpected DBF type {name}/{kind}')
        fields.append({'name':name,'kind':kind,'width':width,'scale':scale,'offset':offset}); offset+=width
    if rows!=pin['expected_rows'] or len(fields)!=10 or offset!=row_size: raise ValueError('Unexpected DBF layout/count')
    values={f['name']:[] for f in fields}
    for i in range(rows):
        record=dbf[header+i*row_size:header+(i+1)*row_size]
        if len(record)!=row_size or record[0:1]!=b' ': raise ValueError(f'Deleted/truncated DBF row {i+1}')
        for f in fields:
            text=record[f['offset']:f['offset']+f['width']].strip().decode('ascii')
            values[f['name']].append(Decimal(text) if text and set(text)!={'*'} else None)
    if struct.unpack_from('>i',shp,0)[0]!=9994 or struct.unpack_from('<i',shp,32)[0]!=3: raise ValueError('Expected PolyLine shapefile')
    header_bbox=struct.unpack_from('<4d',shp,36)
    geom=[]; bboxes=[]; parts_per=[]; vertices_per=[]; cursor=100
    while cursor<len(shp):
        rec,words=struct.unpack_from('>ii',shp,cursor); size=words*2; data=cursor+8
        if rec!=len(geom)+1 or size<48: raise ValueError('Unexpected SHP record numbering/size')
        kind=struct.unpack_from('<i',shp,data)[0]
        if kind!=3: raise ValueError('Unexpected SHP record geometry type')
        box=struct.unpack_from('<4d',shp,data+4); nparts,npts=struct.unpack_from('<ii',shp,data+36)
        if nparts<1 or npts<2 or size!=44+4*nparts+16*npts: raise ValueError(f'Invalid part/point counts at row {rec}')
        starts=list(struct.unpack_from('<'+('i'*nparts),shp,data+44)); xy=list(struct.iter_unpack('<dd',shp[data+44+4*nparts:data+44+4*nparts+16*npts]))
        if starts[0]!=0 or starts!=sorted(starts) or starts[-1]>=npts: raise ValueError('Invalid part offsets')
        ends=starts[1:]+[npts]; lines=[xy[a:b] for a,b in zip(starts,ends)]
        if any(len(line)<2 for line in lines): raise ValueError('Polyline part shorter than two vertices')
        geom.append(shapely.to_wkb(shapely.MultiLineString(lines),byte_order=1,output_dimension=2)); bboxes.append(box); parts_per.append(nparts); vertices_per.append(npts)
        cursor+=8+size
    if cursor!=len(shp) or len(geom)!=rows: raise ValueError('SHP/DBF record count mismatch')
    return fields,values,geom,bboxes,parts_per,vertices_per,header_bbox

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--source',type=Path,default=ROOT/'.local/grwl/GRWL_summaryStats_V01.02.zip'); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args()
    if a.output.exists(): raise SystemExit('Output exists; immutable releases are never overwritten')
    packages={name:package_version(name) for name in ('pyarrow','pyproj','shapely','duckdb','PyYAML','pmtiles','mapbox-vector-tile','rashid')}
    pinned={'pyarrow':'23.0.1','pyproj':'3.8.0','shapely':'2.1.2','duckdb':'1.5.2','PyYAML':'6.0.3','pmtiles':'3.8.1','mapbox-vector-tile':'2.2.0','rashid':'0.1.8'}
    if packages != pinned: raise ValueError(f'Installed Python packages differ from the environment lock: {packages}')
    fields,values,geoms,boxes,parts,vertices,header_bbox=parse_source(a.source)
    ids=values['ID']; source_ids=list(range(1,len(ids)+1))
    cols={'source_row':pa.array(range(1,len(geoms)+1),type=pa.int32())}
    storage_scale={}
    for f in fields:
        storage_scale[f['name']]=max(f['scale'],max((max(0,-v.as_tuple().exponent) for v in values[f['name']] if v is not None),default=0))
        cols[f['name']]=pa.array(values[f['name']],type=pa.decimal128(max(1,f['width']),storage_scale[f['name']]))
    cols['geometry']=pa.array(geoms,type=pa.binary())
    cols['bbox']=pa.StructArray.from_arrays([pa.array([b[i] for b in boxes],type=pa.float64()) for i in range(4)],names=['xmin','ymin','xmax','ymax'])
    table=pa.table(cols)
    bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    geo={'version':'1.1.0','primary_column':'geometry','columns':{'geometry':{'encoding':'WKB','geometry_types':['MultiLineString'],'crs':CRS.from_epsg(4326).to_json_dict(),'bbox':bbox,'covering':{'bbox':{k:['bbox',k] for k in ['xmin','ymin','xmax','ymax']}}}}}
    table=table.replace_schema_metadata({b'geo':json.dumps(geo,separators=(',',':')).encode(),b'folia:source_doi':CONFIG['source_doi'].encode(),b'folia:source_sha256':CONFIG['source_sha256'].encode()})
    out=a.output; out.mkdir(parents=True); shutil.copyfile(HERE/'dataset.yaml',out/'dataset.yaml'); folder=out/'grwl'; folder.mkdir()
    pq.write_table(table,folder/'grwl-summary-v0102.parquet',compression='zstd',compression_level=9,row_group_size=8192,write_statistics=True,version='2.6')
    unit={'OBJECTID':('Esri-generated source feature number',None),'ID':('Producer feature identifier',None),'width_min_':('Minimum river width','m'),'width_med_':('Median river width','m'),'width_mean':('Mean river width','m'),'width_max_':('Maximum river width','m'),'width_sd_m':('Standard deviation of river width','m'),'lakeFlag':('Lake flag as stored by producer',None),'nSegPx':('Segment pixel count',None),'Shape_Leng':('Geodesic feature length; source metadata lineage records kilometers','km')}
    schema=[]
    for f in table.schema:
        if f.name=='geometry': desc,u='WGS84 polyline geometry with source multipart structure, in source vertex order','degrees';
        elif f.name=='bbox': desc,u='Per-feature xmin/ymin/xmax/ymax envelope in WGS84','degrees';
        elif f.name=='source_row': desc,u='One-based original SHP/DBF ordinal','1';
        else: desc,u=unit[f.name]
        item={'name':f.name,'type':str(f.type),'description':desc,'unit':u}
        source_field=next((x for x in fields if x['name']==f.name),None)
        if source_field: item.update({'dbf_type':source_field['kind'],'dbf_width':source_field['width'],'dbf_declared_scale':source_field['scale'],'stored_decimal_scale':storage_scale[f.name]})
        schema.append(item)
    write_json(folder/'schema.json',schema)
    nulls={n:sum(v is None for v in vals) for n,vals in values.items() if any(v is None for v in vals)}
    id_counts=Counter(ids)
    quality={'source_records':len(geoms),'shape_parts':sum(parts),'shape_vertices':sum(vertices),'producer_id_distinct_values':len(id_counts),'producer_id_duplicate_groups':sum(n>1 for n in id_counts.values()),'producer_id_records_in_repeated_groups':sum(n for n in id_counts.values() if n>1),'producer_id_excess_records':len(ids)-len(id_counts),'producer_id_max_multiplicity':max(id_counts.values()),'shp_header_bbox':header_bbox,'feature_coordinate_bbox':bbox,'stac_bbox':[-180.0,max(-90,bbox[1]),180.0,min(90,bbox[3])],'bbox_extent_note':'STAC spatial extent uses a conservative global longitude envelope; analytic feature bbox and coordinates are unchanged. The SHP header bbox alone has a tiny 180-degree overshoot; feature vertices are in range.','null_counts':nulls,'distinct_geometry_wkb':len(set(geoms)),'multiplicity':'Preserve every producer record, including coincident or identical geometries.','longitude_overshoot_rows':[i+1 for i,b in enumerate(boxes) if b[0]<-180 or b[2]>180],'max_longitude':bbox[2],'analytic_coordinate_handling':'No coordinate normalization; exact source XY float64 values and part order are preserved.','numeric_storage_scales':storage_scale,'numeric_scale_note':'Some scientific-notation DBF text exceeds its nominal field scale; Arrow Decimal scale expands to the maximum lexical decimal places observed per field so no numeric value is rounded.'}
    write_json(folder/'quality.json',quality)
    # Display coordinates alone clamp tiny source longitude overshoots to the valid map domain.
    gj=out/'display.geojsonl'
    with gj.open('w') as s:
        for i,wkb in enumerate(geoms):
            g=shapely.from_wkb(wkb); xy=shapely.get_coordinates(g); xy[:,0]=xy[:,0].clip(-180,180); g=shapely.set_coordinates(g,xy)
            props={'source_row':i+1,**{f['name']:None if values[f['name']][i] is None else float(values[f['name']][i]) for f in fields}}
            s.write(json.dumps({'type':'Feature','id':i+1,'properties':props,'geometry':shapely.geometry.mapping(g)},separators=(',',':'))+'\n')
    tip=shutil.which('tippecanoe')
    if not tip: raise SystemExit('tippecanoe required')
    ver=subprocess.run([tip,'--version'],text=True,capture_output=True,check=True); version=(ver.stdout+ver.stderr).strip()
    tool_lock=json.loads((HERE/'tippecanoe.lock.json').read_text())
    if version != f"tippecanoe v{tool_lock['version']}" or sha(tip) != tool_lock['binary_sha256']: raise ValueError('Tippecanoe version/binary differs from committed tool lock')
    subprocess.run([tip,'--quiet','--output','grwl/grwl-display.pmtiles','--layer','grwl','--name',CONFIG['title'],'--description','Display derivative; GeoParquet is the analytic source.','--attribution','GRWL producer; CC BY 4.0','--minimum-zoom','0','--maximum-zoom','10','--simplification','2','--no-feature-limit','--no-tile-size-limit','--use-attribute-for-id','source_row',gj.name],cwd=out,env={**os.environ,'TIPPECANOE_MAX_THREADS':'2'},check=True)
    gj.unlink()
    from catalog import build_catalog
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    build_catalog(out,table,schema,bbox,revision)
    assets={p.relative_to(out).as_posix():{'size_bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file()}
    manifest={'status':'local_prepared_not_published','dataset':'grwl','source':CONFIG,'source_archive':'GRWL_summaryStats_V01.02.zip','source_sha256':CONFIG['source_sha256'],'effective_config_sha256':config_sha256(CONFIG),'release':'summary-v01.02-local-r1','conversion_git_commit':revision,'dataset_record_sha256':sha(out/'dataset.yaml'),'build_input_sha256':{n:sha(HERE/n) for n in CODE_FILES},'environment':{'python':platform.python_version(),'packages':packages,'tippecanoe':version,'tippecanoe_sha256':sha(tip),'max_threads':2,'tool_lock':tool_lock},'records':len(geoms),'fields':len(fields),'bbox':bbox,'quality':quality,'assets':assets,'limitations':['No V01.01 GEE parity is claimed or tested.','This establishes conversion fidelity to the pinned summary archive, not scientific accuracy.','PMTiles is a display derivative with pixel simplification and quantized coordinates; use GeoParquet for analysis.']}
    write_json(out/'manifest.json',manifest)
    print(json.dumps({'records':len(geoms),'parts':sum(parts),'vertices':sum(vertices),'bbox':bbox,'output':str(out)},indent=2))
if __name__=='__main__': main()
