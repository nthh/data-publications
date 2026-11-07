#!/usr/bin/env python3
"""Independent source-fidelity, format, tile and loopback HTTP validation."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,struct,threading,urllib.request,urllib.error
from collections import Counter
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
import yaml,subprocess
import duckdb,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq,shapely
from pmtiles.reader import Reader,all_tiles
from pmtiles.tile import Compression
import mapbox_vector_tile
import numpy as np
from pyproj import Transformer
from dataset_config import load_config,config_sha256
from serve import Handler
HERE=Path(__file__).resolve().parent; C=load_config()
def need(x,m):
 if not x: raise ValueError(m)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def float64_values_equal(actual,expected):
 a=np.asarray(actual,dtype=np.float64); e=np.asarray(expected,dtype=np.float64)
 return a.shape==e.shape and np.array_equal(a.view(np.uint64),e.view(np.uint64))
def geometry_parts_equal(actual_parts,expected_parts):
 return len(actual_parts)==len(expected_parts) and all(float64_values_equal(np.asarray(a.coords,dtype=np.float64),np.asarray(e,dtype=np.float64)) for a,e in zip(actual_parts,expected_parts))
def source_read(path):
 with __import__('zipfile').ZipFile(path) as z:
  dbf=z.read('GRWL_summaryStats.dbf'); shp=z.read('GRWL_summaryStats.shp'); z.testzip()
 n=struct.unpack_from('<I',dbf,4)[0]; h,rs=struct.unpack_from('<HH',dbf,8); fields=[]; off=1
 for p in range(32,h-1,32):
  d=dbf[p:p+32]; name=d[:11].split(b'\0')[0].decode(); width,scale=d[16],d[17]; fields.append((name,width,scale,off)); off+=width
 vals={name:[] for name,_,_,_ in fields}
 for i in range(n):
  r=dbf[h+i*rs:h+(i+1)*rs]; need(r[0:1]==b' ','inactive DBF record')
  for name,w,s,o in fields:
   t=r[o:o+w].strip().decode('ascii'); vals[name].append(Decimal(t) if t and set(t)!={'*'} else None)
 shapes=[]; parts_total=verts_total=0; pos=100
 while pos<len(shp):
  rec,words=struct.unpack_from('>ii',shp,pos); d=pos+8; typ=struct.unpack_from('<i',shp,d)[0]; need(typ==3,'not PolyLine')
  nparts,npts=struct.unpack_from('<ii',shp,d+36); starts=struct.unpack_from('<'+'i'*nparts,shp,d+44); coords=list(struct.iter_unpack('<dd',shp[d+44+4*nparts:d+44+4*nparts+16*npts])); ends=starts[1:]+(npts,)
  shapes.append((rec,starts,ends,coords)); parts_total+=nparts; verts_total+=npts; pos+=8+words*2
 need(len(shapes)==n and pos==len(shp),'SHP/DBF counts differ')
 header_bbox=struct.unpack_from('<4d',shp,36)
 return fields,vals,shapes,parts_total,verts_total,header_bbox

def validate(root,source,http=False):
 root=Path(root).resolve(); m=json.loads((root/'manifest.json').read_text()); need(sha(source)==C['source_sha256'] and hashlib.md5(Path(source).read_bytes()).hexdigest()==C['source_md5'] and Path(source).stat().st_size==C['source_size'],'source pin mismatch')
 need(m['source']==C and m.get('effective_config_sha256')==config_sha256(C),'manifest source/config mismatch')
 snapshot=yaml.safe_load((root/'dataset.yaml').read_text()); snapshot_config={'id':snapshot['id'],'title':snapshot['title'],**snapshot['source']}
 need(snapshot_config==m['source'],'release dataset snapshot source config differs from build manifest')
 need(m['records']==C['expected_rows'],'manifest expected record count mismatch')
 for name,a in m['assets'].items(): need((root/name).stat().st_size==a['size_bytes'] and sha(root/name)==a['sha256'],f'asset hash mismatch: {name}')
 need(sha(root/'dataset.yaml')==m['dataset_record_sha256'],'release dataset.yaml snapshot hash mismatch')
 for name,expected in m['build_input_sha256'].items(): need(sha(HERE/name)==expected,f'build input changed: {name}')
 fields,vals,shapes,part_count,vertex_count,header_bbox=source_read(source); p=root/'grwl/grwl-summary-v0102.parquet'; pf=pq.ParquetFile(p); tab=pq.read_table(p).sort_by('source_row')
 need(tab.num_rows==C['expected_rows'],'analytic row count mismatch'); need(tab.column_names==['source_row']+[f[0] for f in fields]+['geometry','bbox'],'analytic fields changed')
 need(tab['source_row'].to_pylist()==list(range(1,tab.num_rows+1)),'source row ordinal mismatch')
 compared=0
 for name,w,s,o in fields:
  expected_scale=max(s,max((max(0,-v.as_tuple().exponent) for v in vals[name] if v is not None),default=0))
  need(tab[name].to_pylist()==vals[name],f'DBF field mismatch: {name}'); need(tab.schema.field(name).type.scale==expected_scale and tab.schema.field(name).type.precision==w,f'DBF numeric width/storage scale mismatch {name}'); compared+=len(vals[name])
 wkb=tab['geometry'].to_pylist(); xy_total=0
 for i,((rec,starts,ends,coords),b) in enumerate(zip(shapes,tab['bbox'].to_pylist())):
  geom=shapely.from_wkb(wkb[i]); output_parts=list(geom.geoms)
  expected_parts=[coords[a:z] for a,z in zip(starts,ends)]
  need(len(output_parts)==len(starts),f'SHP part count changed at row {i+1}')
  for part_idx,(out_part,expected_part) in enumerate(zip(output_parts,expected_parts)):
   need(float64_values_equal(np.asarray(out_part.coords,dtype=np.float64),np.asarray(expected_part,dtype=np.float64)),f'SHP part vertices or binary float64 values changed at row {i+1} part {part_idx+1}')
  got=shapely.get_coordinates(geom); expected=[v for part in expected_parts for v in part]; xy_total+=len(got)
  need(all(math.isfinite(x) and math.isfinite(y) and -180.0<=x<=180.0 and -90.0<=y<=90.0 for x,y in expected),f'invalid source vertex at row {i+1}')
  xy=[q[0] for q in expected]; yy=[q[1] for q in expected]; eb={'xmin':min(xy),'xmax':max(xy),'ymin':min(yy),'ymax':max(yy)}
  need(all(b[k]==v for k,v in eb.items()),f'bbox changed row {i+1}')
 need(part_count==m['quality']['shape_parts'] and vertex_count==m['quality']['shape_vertices'],'shape structure count mismatch')
 need(list(header_bbox)==m['quality']['shp_header_bbox'],'SHP source header bbox changed')
 need(m['quality']['feature_coordinate_bbox'][2]<180.0 and m['quality']['longitude_overshoot_rows']==[],'unexpected feature longitude overshoot or missing report')
 geo=json.loads(pf.metadata.metadata[b'geo']); need(geo['version']=='1.1.0' and geo['columns']['geometry']['crs']['id']['authority']=='EPSG' and geo['columns']['geometry']['crs']['id']['code']==4326,'GeoParquet CRS/version mismatch')
 need(pf.metadata.num_rows==C['expected_rows'] and pf.metadata.num_row_groups>1,'Parquet row group layout invalid')
 for i in range(pf.metadata.num_row_groups):
  g=pf.metadata.row_group(i); need(g.num_rows<=8192,'oversized row group')
  for j in range(g.num_columns):
   col=g.column(j)
   if col.path_in_schema.startswith('bbox.'):
    need(col.statistics is not None and col.statistics.has_min_max,'missing bbox statistics')
 db=duckdb.connect(config={'threads':2}); query=f"SELECT count(*) n FROM read_parquet('{p}') WHERE bbox.xmin BETWEEN -125 AND -65 AND bbox.ymin BETWEEN 24 AND 50"; subset=db.execute(query).fetchone()[0]; need(subset>0,'DuckDB bbox subset empty')
 subprocess.run(['pmtiles','verify',str(root/'grwl/grwl-display.pmtiles')],check=True,capture_output=True,text=True)
 pm=(root/'grwl/grwl-display.pmtiles').read_bytes(); need(pm[:8]==b'PMTiles\x03','not PMTiles v3'); get=lambda o,n:pm[o:o+n]; rd=Reader(get); head=rd.header(); meta=rd.metadata(); need(head['max_zoom']==10 and head['min_zoom']==0,'unexpected PMTiles zoom range'); need(any(l['id']=='grwl' for l in meta['vector_layers']),'missing grwl tile layer')
 ids=set(); tile_count=feature_count=0; bad_bounds=0; zoom_counts=Counter()
 for (z,x,y),raw in all_tiles(get):
  zoom_counts[z]+=1
  if z!=10: continue
  tile_count+=1
  if head['tile_compression']==Compression.GZIP: raw=gzip.decompress(raw)
  decoded=mapbox_vector_tile.decode(raw)
  layer=decoded.get('grwl',{})
  need(set(decoded)=={'grwl'} and layer.get('extent')==4096,'Unexpected tile layer or extent')
  for f in layer.get('features',[]):
   need(f['geometry']['type'] in ('LineString','MultiLineString'),'Unexpected non-line display geometry')
   feature_count+=1; fid=f.get('id',f.get('properties',{}).get('source_row')); ids.add(int(fid))
   need(1<=int(fid)<=C['expected_rows'],'Invalid tile source-row ID')
   prop=f.get('properties',{}); need(int(prop.get('source_row',fid))==int(fid),'tile source_row property differs from feature ID')
   for field,_,_,_ in fields:
    original=vals[field][int(fid)-1]; observed=prop.get(field)
    need((original is None and observed is None) or (original is not None and observed is not None and float(original)==observed),f'Tile attribute differs from source float conversion: {fid}/{field}')
   for xx,yy in shapely.get_coordinates(shapely.geometry.shape(f['geometry'])):
    if not (-100<=xx<=4196 and -100<=yy<=4196): bad_bounds+=1
 expected=set(range(1,C['expected_rows']+1)); need(ids==expected,f'PMTiles z10 source row coverage mismatch: missing {len(expected-ids)}, extra {len(ids-expected)}')
 sample_rows=[]
 for row,(rec,starts,ends,coords) in enumerate(shapes,1):
  if sum(b-a for a,b in zip(starts,ends))<=32:
   sample_rows.append(row)
   if len(sample_rows)==32: break
 need(len(sample_rows)==32,'not enough short source features for geometry sample')
 sample=set(sample_rows); tile_lines={i:[] for i in sample}; transformer=Transformer.from_crs(4326,3857,always_xy=True); world=40075016.68557849; extent=meta['vector_layers'][0].get('extent',4096)
 for (z,tx,ty),raw in all_tiles(get):
  if z!=10: continue
  if head['tile_compression']==Compression.GZIP: raw=gzip.decompress(raw)
  layer=mapbox_vector_tile.decode(raw).get('grwl',{})
  for f in layer.get('features',[]):
   fid=int(f.get('id',f.get('properties',{}).get('source_row',0)))
   if fid not in sample: continue
   tile_geom=shapely.geometry.shape(f['geometry']); uvs=shapely.get_coordinates(tile_geom);
   mx=((tx+uvs[:,0]/extent)/(2**z))*world-world/2; my=world/2-((ty+(extent-uvs[:,1])/extent)/(2**z))*world; merc=shapely.set_coordinates(tile_geom, __import__('numpy').column_stack([mx,my])); tile_lines[fid].append(merc)
 distances=[]
 for row in sample_rows:
  _,starts,ends,coords=shapes[row-1]; parts_src=[coords[a:b] for a,b in zip(starts,ends)]; source_geom=shapely.MultiLineString(parts_src); source_merc=shapely.transform(source_geom,lambda x:__import__('numpy').column_stack(transformer.transform(x[:,0],x[:,1])))
  need(tile_lines[row],f'sampled feature {row} absent from z10 tiles'); rendered=shapely.union_all(tile_lines[row]); distances.append(float(shapely.hausdorff_distance(source_merc,rendered,densify=0.5)))
 tolerance=2.71*world/(2**10*extent); need(max(distances)<=tolerance,f'z10 sample geometry displacement {max(distances):.6f} exceeds {tolerance:.6f}m')
 need(set(zoom_counts)==set(range(0,11)) and all(zoom_counts[z]>0 for z in range(11)),'PMTiles missing one or more declared overview zoom levels')
 need(tile_count>0 and bad_bounds==0,'PMTiles tile bounds invalid')
 schema=json.loads((root/'grwl/schema.json').read_text()); units={'OBJECTID':None,'ID':None,'width_min_':'m','width_med_':'m','width_mean':'m','width_max_':'m','width_sd_m':'m','lakeFlag':None,'nSegPx':None,'Shape_Leng':'km'}
 for col in schema:
  if col['name'] in units: need(col['unit']==units[col['name']],f"field unit mismatch: {col['name']}")
 stac=json.loads((root/'grwl/collection.json').read_text()); cat=json.loads((root/'catalog.json').read_text())
 need(stac['stac_version']=='1.1.0' and stac['license']=='CC-BY-4.0','STAC version/license mismatch'); need(stac['extent']['spatial']['bbox']==[m['quality']['stac_bbox']] and m['quality']['stac_bbox']==[-180.0,max(-90,m['bbox'][1]),180.0,min(90,m['bbox'][3])],'invalid STAC geographic bbox/quality mapping'); need(stac['providers'][-1]['name']=='Folia' and 'host' in stac['providers'][-1]['roles'],'Folia host must be last provider')
 need(cat['type']=='Catalog' and cat['stac_version']=='1.1.0' and cat['id']=='folia-grwl','invalid STAC root catalog')
 need(any('portolan/v0.2.0' in x for x in stac['stac_extensions']) and any('portolan/v0.2.0' in x for x in cat['stac_extensions']),'Portolan v0.2 missing')
 style_path=root/'grwl/styles/grwl.json'; style=json.loads(style_path.read_text()); need(any(x.get('source-layer')=='grwl' for x in style['layers']),'MapLibre style lacks GRWL layer')
 need(any(x['rel']=='agents' for x in cat['links']) and any(x['rel']=='describedby' for x in cat['links']),'root Catalog missing agents/describedby links')
 need(any(x['rel']=='thumbnail' and x['type']=='image/png' for x in cat['links']),'root Catalog missing PNG thumbnail link')
 need(stac['sci:doi']==C['source_doi'] and any(x.get('href')==C['license_url'] for x in stac['links']),'STAC DOI or license link missing')
 expected_cols={x['name']:x for x in schema}; need({x['name'] for x in stac['table:columns']}==set(expected_cols),'STAC table field list differs from schema')
 for asset_name,asset in stac['assets'].items():
  href=asset['href']
  if asset_name=='source': need(href==C['source_url'] and asset['file:checksum']=='1220'+C['source_sha256'],'STAC source asset mismatch')
  else:
   resolved=(root/'grwl'/href).resolve(); need(resolved.is_relative_to(root) and resolved.is_file(),f'STAC asset missing/unsafe: {asset_name}')
   need(asset['file:checksum']=='1220'+sha(resolved),f'STAC asset checksum mismatch: {asset_name}')
 for item in stac['links']:
  if item['rel'] in ('root','parent','describedby','license','via','pmtiles') and item['href'].startswith('../'):
   need((root/'grwl'/item['href']).resolve().is_relative_to(root),f'unsafe STAC link: {item["href"]}')
 style_path=root/'grwl/styles/grwl.json';style=json.loads(style_path.read_text());style_href=style['sources']['grwl']['url']
 need(style_href=='../grwl-display.pmtiles' and (style_path.parent/style_href).resolve()==(root/'grwl/grwl-display.pmtiles').resolve(),'Style source does not resolve to declared PMTiles asset')
 need(style['layers'][-1]['source-layer']=='grwl','Style layer differs from tile layer')
 http_result=None
 if http:
  server=ThreadingHTTPServer(('127.0.0.1',0),lambda *args,**kw:Handler(*args,directory=str(root),**kw)); thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start(); base=f'http://127.0.0.1:{server.server_port}'
  url=base+'/grwl/grwl-summary-v0102.parquet'; expected_bytes=p.read_bytes(); range_cases=[]
  for header,expected,status in [('bytes=0-31',expected_bytes[:32],206),('bytes=128-159',expected_bytes[128:160],206),('bytes=-16',expected_bytes[-16:],206),(f'bytes={len(expected_bytes)+1}-{len(expected_bytes)+9}',b'',416)]:
   req=urllib.request.Request(url,headers={'Range':header})
   try: resp=urllib.request.urlopen(req); payload=resp.read(); code=resp.status; headers=resp.headers
   except urllib.error.HTTPError as error: payload=error.read();code=error.code;headers=error.headers
   need(code==status and headers.get('Access-Control-Allow-Origin')=='*',f'HTTP range/CORS failure for {header}: {code}')
   if status==206: need(payload==expected,f'HTTP range bytes differ for {header}')
   range_cases.append({'range':header,'status':code,'bytes':len(payload)})
  remote=db.execute(f"SELECT count(*) FROM read_parquet('{url}') WHERE bbox.xmin BETWEEN -125 AND -65 AND bbox.ymin BETWEEN 24 AND 50").fetchone()[0]; need(remote==subset,'HTTP DuckDB subset mismatch'); server.shutdown(); http_result={'range_cases':range_cases,'cors':'*','duckdb_subset_rows':remote,'handler':'datasets/grwl/serve.py'}
 return {'status':'passed','release_manifest_sha256':sha(root/'manifest.json'),'records':tab.num_rows,'numeric_field_comparisons':compared,'polyline_parts':part_count,'vertices':vertex_count,'duckdb_bbox_subset_rows':subset,'pmtiles_structure_verified':True,'pmtiles_numeric_comparisons':feature_count*len(fields),'pmtiles_minzoom':0,'pmtiles_maxzoom':10,'pmtiles_tiles_by_zoom':dict(sorted(zoom_counts.items())),'pmtiles_z10_tiles':tile_count,'pmtiles_z10_features':feature_count,'pmtiles_z10_distinct_ids':len(ids),'pmtiles_z10_sample_rows':sample_rows,'pmtiles_z10_max_hausdorff_m':max(distances),'pmtiles_z10_hausdorff_limit_m':tolerance,'pmtiles_z10_geometry_metric':'symmetric discrete Hausdorff with vertices and segment midpoints (densify=0.5); diagnostic only','catalog_structure':'passed','http':http_result}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('release',type=Path); ap.add_argument('--source',type=Path,default=HERE.parents[1]/'.local/grwl/GRWL_summaryStats_V01.02.zip'); ap.add_argument('--http',action='store_true'); ap.add_argument('--report',type=Path); a=ap.parse_args(); r=validate(a.release,a.source,a.http); print(json.dumps(r,indent=2));
 if a.report: a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
