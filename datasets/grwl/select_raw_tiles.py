#!/usr/bin/env python3
"""Choose official tile-index footprints around the preselected source edges."""
import argparse, hashlib, json
from pathlib import Path
import geopandas as gpd
import shapely

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/grwl-raw-audit-20261102'

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--index',required=True,type=Path)
 p.add_argument('--output-dir',required=True,type=Path)
 a=p.parse_args()
 if a.output_dir.exists():raise SystemExit('Use a new selection directory')
 index_sha=hashlib.sha256(a.index.read_bytes()).hexdigest()
 if index_sha!=json.loads((BASE/'tile-index-fetch-r1.json').read_text())['sha256']:raise ValueError('Tile index checksum mismatch')
 g=gpd.read_file('zip://'+str(a.index)).to_crs(4326)
 edges=json.loads((BASE/'summary-selection.json').read_text())['selected_edges']
 selected={};by_edge=[]
 for edge in edges:
  bounds=shapely.LineString(edge['coordinates']).bounds
  roi=shapely.box(bounds[0]-.02,bounds[1]-.02,bounds[2]+.02,bounds[3]+.02)
  found=g[g.intersects(roi)]
  names=[]
  for _,r in found.iterrows():
   if not isinstance(r.TILE_ID,str):continue
   selected[r.TILE_ID]={'tile_id':r.TILE_ID,'bbox':list(r.geometry.bounds),'index_IMW_ID':int(r.IMW_ID)}
   names.append(r.TILE_ID)
  by_edge.append({'source_row':edge['source_row'],'part':edge['part'],'edge':edge['edge'],'roi_bbox':list(roi.bounds),'tiles':sorted(names)})
 result={'index_sha256':index_sha,'index_crs':'EPSG:4326','selection':'edge bbox padded by 0.02 degrees on each side','edges':by_edge,'tiles':[selected[k] for k in sorted(selected)]}
 a.output_dir.mkdir(parents=True)
 for kind in ('vector','mask'):
  inventory=json.loads((BASE/f'{kind}-inventory-r1.json').read_text())['members']
  suffixes=('.shp','.shx','.dbf','.prj','.cpg','.shp.xml') if kind=='vector' else ('.tif','.tfw','.tif.xml','.tif.aux.xml')
  members=[];missing=[]
  for tile in sorted(selected):
   files=[m for m in inventory if Path(m['name']).name.startswith(tile+'.') and any(m['name'].endswith(s) for s in suffixes)]
   if not any(m['name'].endswith('.shp' if kind=='vector' else '.tif') for m in files):missing.append(tile)
   members.extend(files)
  result[kind]={'selected_members':len(members),'compressed_bytes':sum(m['compressed_bytes'] for m in members),'uncompressed_bytes':sum(m['uncompressed_bytes'] for m in members),'missing_tiles':missing}
  (a.output_dir/f'{kind}-members.json').write_text(json.dumps([m['name'] for m in members],indent=2)+'\n')
  if kind=='vector':(a.output_dir/'vector-header-members.json').write_text(json.dumps([m['name'] for m in members if m['name'].endswith('.shp')],indent=2)+'\n')
 (a.output_dir/'selection.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))

if __name__=='__main__':main()
