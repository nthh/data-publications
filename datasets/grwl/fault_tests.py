#!/usr/bin/env python3
"""Inject meaningful attribute, null, unit and coordinate faults; require detection."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,tempfile
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq,shapely
from validate import validate,float64_values_equal
HERE=Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_release_fault(release, mutate, name, source, expected_error):
 with tempfile.TemporaryDirectory(prefix='grwl-fault-') as td:
  root=Path(td)/'release';root.mkdir()
  manifest=json.loads((release/'manifest.json').read_text())
  for src in release.rglob('*'):
   rel=src.relative_to(release); dst=root/rel
   if src.is_dir(): dst.mkdir(exist_ok=True)
   elif rel.as_posix()=='manifest.json': pass
   else:
    dst.parent.mkdir(parents=True,exist_ok=True)
    try: os.link(src,dst)
    except OSError: shutil.copy2(src,dst)
  rel=name; target=root/rel; target.unlink(); shutil.copy2(release/rel,target)
  mutate(root)
  target=root/rel; manifest['assets'][rel]['size_bytes']=target.stat().st_size; manifest['assets'][rel]['sha256']=sha(target)
  (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
  try: validate(root,source,False)
  except ValueError as e:
   if expected_error not in str(e):raise AssertionError(f'Fault failed for the wrong reason: {e}; expected {expected_error}') from e
   return str(e)
  raise AssertionError(f'fault escaped validator: {name}')
def change_parquet(path, column, mutate):
 t=pq.read_table(path); i=t.schema.get_field_index(column); field=t.schema.field(i); values=t[column].to_pylist(); mutate(values); t=t.set_column(i,field,pa.array(values,type=field.type)); pq.write_table(t,path,compression='zstd',compression_level=9,row_group_size=8192,write_statistics=True,version='2.6')
def run(release,source):
 cases=[]
 cases.append(('identifier','grwl/grwl-summary-v0102.parquet',lambda r:change_parquet(r/'grwl/grwl-summary-v0102.parquet','ID',lambda v:v.__setitem__(0,v[0]+1))))
 def null(v): v[0]=None
 cases.append(('null','grwl/grwl-summary-v0102.parquet',lambda r:change_parquet(r/'grwl/grwl-summary-v0102.parquet','width_min_',null)))
 def lost_row(r):
  p=r/'grwl/grwl-summary-v0102.parquet';t=pq.read_table(p);pq.write_table(t.slice(1),p,compression='zstd',compression_level=9,row_group_size=8192,write_statistics=True,version='2.6')
 cases.append(('lost-row','grwl/grwl-summary-v0102.parquet',lost_row))
 cases.append(('duplicate-source-row','grwl/grwl-summary-v0102.parquet',lambda r:change_parquet(r/'grwl/grwl-summary-v0102.parquet','source_row',lambda v:v.__setitem__(1,v[0]))))

 def unit(r):
  p=r/'grwl/schema.json'; a=json.loads(p.read_text()); next(x for x in a if x['name']=='Shape_Leng')['unit']='m'; p.write_text(json.dumps(a,indent=2,ensure_ascii=False)+'\n')
 cases.append(('units','grwl/schema.json',unit))
 def geometry(r):
  p=r/'grwl/grwl-summary-v0102.parquet';t=pq.read_table(p); vals=t['geometry'].to_pylist();g=shapely.from_wkb(vals[0]);xy=shapely.get_coordinates(g);xy[0,0]+=1e-5;vals[0]=shapely.to_wkb(shapely.set_coordinates(g,xy),byte_order=1,output_dimension=2);i=t.schema.get_field_index('geometry');t=t.set_column(i,t.schema.field(i),pa.array(vals,type=pa.binary()));pq.write_table(t,p,compression='zstd',compression_level=9,row_group_size=8192,write_statistics=True,version='2.6')
 cases.append(('geometry-vertex','grwl/grwl-summary-v0102.parquet',geometry))
 def repartition(r):
  p=r/'grwl/grwl-summary-v0102.parquet';t=pq.read_table(p);vals=t['geometry'].to_pylist();changed=False
  for i,raw in enumerate(vals):
   g=shapely.from_wkb(raw);parts=[list(part.coords) for part in g.geoms]
   if len(parts)>=2 and len(parts[0])>=3 and len(parts[1])>=3:
    original=[v for part in parts for v in part];parts[1]=[parts[0][-1],*parts[1]];parts[0]=parts[0][:-1];flattened=[v for part in parts for v in part]
    if original!=flattened or len(parts)!=len(g.geoms):raise AssertionError('Multipart fixture did not preserve flattened coordinates/part count')
    vals[i]=shapely.to_wkb(shapely.MultiLineString(parts),byte_order=1,output_dimension=2);changed=True;break
  if not changed:raise AssertionError('No multipart feature suitable for boundary fixture')
  idx=t.schema.get_field_index('geometry');t=t.set_column(idx,t.schema.field(idx),pa.array(vals,type=pa.binary()));pq.write_table(t,p,compression='zstd',compression_level=9,row_group_size=8192,write_statistics=True,version='2.6')
 cases.append(('multipart-boundary','grwl/grwl-summary-v0102.parquet',repartition))
 result=[]
 for label,asset,fn in cases:
  expected={'lost-row':'analytic row count mismatch','duplicate-source-row':'source row ordinal mismatch','identifier':'DBF field mismatch: ID','null':'DBF field mismatch: width_min_','units':'field unit mismatch: Shape_Leng','geometry-vertex':'SHP part vertices or binary float64 values changed','multipart-boundary':'SHP part vertices or binary float64 values changed'}[label]
  err=write_release_fault(release,fn,asset,source,expected)
  result.append({'fault':label,'status':'detected','validator_error':err})
 if float64_values_equal([[0.0,1.0]],[[-0.0,1.0]]): raise AssertionError('Signed-zero bit fixture escaped comparator')
 result.append({'fault':'signed-zero-bit-comparison','status':'detected','validator_error':'IEEE-754 uint64 bit comparison distinguishes +0.0 from -0.0'})
 return {'status':'passed','cases':result,'release_manifest_sha256':sha(release/'manifest.json')}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('release',type=Path);ap.add_argument('--source',type=Path,default=HERE.parents[1]/'.local/grwl/GRWL_summaryStats_V01.02.zip');ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();r=run(a.release,a.source);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
