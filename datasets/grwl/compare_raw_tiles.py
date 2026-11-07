#!/usr/bin/env python3
"""Compare frozen GRWL summary edges with complete neighboring raw tiles/masks.

This diagnoses source-summary artifacts; it neither repairs data nor certifies
independent scientific accuracy. The raw products share upstream provenance.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
from contextlib import ExitStack
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import CRS, Transformer
import rasterio
from rasterio.windows import Window, from_bounds, bounds as window_bounds
import shapely
from shapely.geometry import LineString, Point

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/grwl-raw-audit-20261102'
WATER={255,180,126,86}


def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def project(geometries,transformer):
 return shapely.transform(geometries,lambda xy:np.column_stack(transformer.transform(xy[:,0],xy[:,1])))


def mask_sample(datasets,lon,lat,local_xy,local_crs):
 center=[];near_values=[];valid_count=0
 reverse=Transformer.from_crs(local_crs,4326,always_xy=True)
 corners=np.array([(local_xy[0]+dx,local_xy[1]+dy) for dx in (-95,95) for dy in (-95,95)])
 ll=np.column_stack(reverse.transform(corners[:,0],corners[:,1]))
 for tile,ds in datasets:
  to_ds=Transformer.from_crs(4326,ds.crs,always_xy=True)
  to_local=Transformer.from_crs(ds.crs,local_crs,always_xy=True)
  x,y=to_ds.transform(lon,lat)
  if ds.bounds.left<=x<ds.bounds.right and ds.bounds.bottom<y<=ds.bounds.top:
   rr,cc=ds.index(x,y)
   if 0<=rr<ds.height and 0<=cc<ds.width:
    v=ds.read(1,window=Window(cc,rr,1,1),masked=True)
    center.append({'tile':tile,'value':None if bool(np.ma.getmaskarray(v)[0,0]) else int(v[0,0]),'masked':bool(np.ma.getmaskarray(v)[0,0])})
  xx,yy=to_ds.transform(ll[:,0],ll[:,1])
  box=(max(ds.bounds.left,min(xx)),max(ds.bounds.bottom,min(yy)),min(ds.bounds.right,max(xx)),min(ds.bounds.top,max(yy)))
  if box[0]>=box[2] or box[1]>=box[3]:continue
  w=from_bounds(*box,transform=ds.transform)
  c0=max(0,int(math.floor(w.col_off)));r0=max(0,int(math.floor(w.row_off)))
  c1=min(ds.width,int(math.ceil(w.col_off+w.width)));r1=min(ds.height,int(math.ceil(w.row_off+w.height)))
  if c0>=c1 or r0>=r1:continue
  values=ds.read(1,window=Window(c0,r0,c1-c0,r1-r0),masked=True)
  rr,cc=np.meshgrid(np.arange(r0,r1),np.arange(c0,c1),indexing='ij')
  px,py=rasterio.transform.xy(ds.transform,rr.ravel(),cc.ravel(),offset='center')
  mx,my=to_local.transform(px,py)
  inside=np.hypot(np.asarray(mx)-local_xy[0],np.asarray(my)-local_xy[1])<=90
  valid=inside & ~np.ma.getmaskarray(values).ravel()
  valid_count+=int(valid.sum())
  near_values.extend(int(v) for v in values.data.ravel()[valid])
 return {'center':center,'center_has_water':any(v['value'] in WATER for v in center),
         'neighborhood_valid_pixels':valid_count,'neighborhood_codes':sorted(set(near_values)),
         'water_within_90m':any(v in WATER for v in near_values)}


def plot_case(output,edge,source,raw,datasets,summary):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.colors import ListedColormap
 from matplotlib.lines import Line2D
 a,b=np.asarray(edge['coordinates']);center=(a+b)/2
 bounds=LineString([a,b]).bounds;dx=bounds[2]-bounds[0];dy=bounds[3]-bounds[1];cos=math.cos(math.radians(center[1]))
 padx=max(.06,dx*.15,dy*.55/cos);pady=max(.04,dy*.12,dx*cos*.55)
 boxes=[(bounds[0]-padx,bounds[1]-pady,bounds[2]+padx,bounds[3]+pady),
        (center[0]-.025/cos,center[1]-.025,center[0]+.025/cos,center[1]+.025)]
 fig,axes=plt.subplots(1,2,figsize=(13,6),layout='constrained')
 for ax,box,title in zip(axes,boxes,['River context','Middle of the reported connector']):
  ax.set_facecolor('#f4f3ed')
  for tile,ds in datasets:
   if ds.crs!=CRS.from_epsg(4326):raise ValueError('Plotting expects geographic producer masks; do not silently assign CRS')
   extent=(max(box[0],ds.bounds.left),max(box[1],ds.bounds.bottom),min(box[2],ds.bounds.right),min(box[3],ds.bounds.top))
   if extent[0]>=extent[2] or extent[1]>=extent[3]:continue
   window=from_bounds(*extent,transform=ds.transform)
   scale=min(1,1400/max(window.width,window.height))
   h,w=max(1,int(window.height*scale)),max(1,int(window.width*scale))
   values=ds.read(1,window=window,out_shape=(h,w),masked=True)
   water=np.ma.masked_where(~np.isin(values.data,list(WATER))|np.ma.getmaskarray(values),np.ones(values.shape))
   left,bottom,right,top=window_bounds(window,ds.transform)
   ax.imshow(water,extent=(left,right,bottom,top),origin='upper',cmap=ListedColormap(['#99d6df']),vmin=0,vmax=1,interpolation='nearest',zorder=1)
  subset=raw[raw.intersects(shapely.box(*box))]
  if len(subset):subset.plot(ax=ax,color='#14677b',linewidth=.8,zorder=3)
  for part in source.geoms:
   xy=np.asarray(part.coords);ax.plot(xy[:,0],xy[:,1],color='#d96a35',alpha=.6,linewidth=1,zorder=4)
  ax.plot([a[0],b[0]],[a[1],b[1]],color='#cf2137',linewidth=2.3,zorder=5)
  ax.set(xlim=(box[0],box[2]),ylim=(box[1],box[3]),title=title,xlabel='Longitude',ylabel='Latitude')
  ax.set_aspect(1/cos);ax.ticklabel_format(useOffset=False,style='plain')
  ax.grid(alpha=.15,zorder=0)
 fig.suptitle(f"GRWL feature {edge['source_row']} · {edge['geodesic_metres']/1000:.1f} km summary connector",fontsize=15)
 legend=[Line2D([0],[0],color='#cf2137',lw=2,label='Reported summary edge'),Line2D([0],[0],color='#d96a35',lw=1,label='Other summary geometry'),Line2D([0],[0],color='#14677b',lw=1.5,label='Raw centerline pieces'),Line2D([0],[0],color='#99d6df',lw=5,label='GRWL connected-water mask')]
 fig.legend(handles=legend,loc='outside lower center',ncol=2,frameon=False)
 fig.savefig(output,dpi=170);plt.close(fig)


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--cache',required=True,type=Path)
 p.add_argument('--data-root',required=True,type=Path)
 p.add_argument('--output-dir',required=True,type=Path)
 args=p.parse_args()
 if args.output_dir.exists():raise SystemExit('Use a new output directory')
 args.output_dir.mkdir(parents=True)
 os.environ.setdefault('MPLCONFIGDIR',str(args.cache/'matplotlib-cache'))
 criteria=json.loads((BASE/'criteria.json').read_text())
 selection=json.loads((BASE/'selection/selection.json').read_text())
 selected=json.loads((BASE/'summary-selection.json').read_text())
 extracted={}
 for kind in ('vector','mask'):
  record=json.loads((BASE/f'{kind}-extraction-r1.json').read_text())
  if record['status']!='passed':raise ValueError('Incomplete extraction')
  paths={}
  for item in record['members']:
   path=args.cache/item['cache_relative_path']
   if sha(path)!=item['sha256'] or not item['complete_member_crc_verified']:raise ValueError('Member checksum mismatch')
   paths[Path(item['name']).name]=path
  extracted[kind]=paths
 source=args.data_root/'grwl/summary-v01.02-local-r1/grwl/grwl-summary-v0102.parquet'
 if sha(source)!=criteria['pins']['analytical_parquet_sha256']:raise ValueError('Analytical source pin differs')
 rows={r['source_row']:r for r in pq.read_table(source,filters=[('source_row','in',[e['source_row'] for e in selected['selected_edges']])]).to_pylist()}
 report={'schema_version':1,'recorded_at':datetime.now(timezone.utc).isoformat(),'criteria_sha256':sha(BASE/'criteria.json'),'script_sha256':sha(__file__),
         'source_parquet_sha256':sha(source),'selection_sha256':sha(BASE/'selection/selection.json'),
         'versions':{m:importlib.metadata.version(m) for m in ['numpy','shapely','pyarrow','pyproj','rasterio','matplotlib','geopandas','pyogrio']},
         'sampling':'101 fractions from 0.01 to 0.99 along original coordinate-space edge; nearest raw geometry in local AEQD, dense long raw segments at <=0.01 degree before projection.',
         'mask_caveat':'Same-provenance connected-water mask is not independent optical truth. Codes follow producer docs; actual raster NoData metadata takes precedence.',
         'water_codes':sorted(WATER),'cases':[]}
 for edge in selected['selected_edges']:
  fid=edge['source_row'];s=next(e for e in selection['edges'] if (e['source_row'],e['part'],e['edge'])==(fid,edge['part'],edge['edge']))
  midpoint=np.mean(edge['coordinates'],axis=0)
  crs=CRS.from_proj4(f'+proj=aeqd +lat_0={midpoint[1]} +lon_0={midpoint[0]} +datum=WGS84 +units=m +no_defs')
  transform=Transformer.from_crs(4326,crs,always_xy=True)
  frames=[];tile_metadata=[]
  for tile in s['tiles']:
   g=gpd.read_file(extracted['vector'][tile+'.shp'],fid_as_index=True,use_arrow=True)
   if g.crs!=CRS.from_epsg(4326):raise ValueError('Unexpected raw vector CRS')
   g['raw_record_1based']=g.index+1;g['raw_tile']=tile
   tile_metadata.append({'tile':tile,'raw_records':len(g),'raw_crs':g.crs.to_string(),'raw_geometry_types':g.geom_type.value_counts().to_dict(),'raw_bounds':g.total_bounds.tolist()})
   frames.append(g)
  raw=gpd.GeoDataFrame(pd.concat(frames,ignore_index=True),crs=4326)
  geoms=project(shapely.segmentize(raw.geometry.to_numpy(),.01),transform)
  tree=shapely.STRtree(geoms)
  a,b=np.asarray(edge['coordinates']);fractions=np.linspace(.01,.99,101);ll=a[None,:]+fractions[:,None]*(b-a)[None,:]
  xy=np.column_stack(transform.transform(ll[:,0],ll[:,1]));points=shapely.points(xy)
  pair,distance=tree.query_nearest(points,all_matches=False,return_distance=True)
  indexes=np.empty(len(points),dtype=int);distances=np.empty(len(points))
  indexes[pair[0]]=pair[1];distances[pair[0]]=distance
  endpoint_pair,endpoint_distance=tree.query_nearest(shapely.points(np.column_stack(transform.transform([a[0],b[0]],[a[1],b[1]]))),all_matches=False,return_distance=True)
  endpoints=[]
  for point_idx,raw_idx,d in zip(endpoint_pair[0],endpoint_pair[1],endpoint_distance):
   rr=raw.iloc[int(raw_idx)]
   endpoints.append({'endpoint':int(point_idx),'raw_tile':rr.raw_tile,'raw_record_1based':int(rr.raw_record_1based),'segmentID':int(rr.segmentID),'segmentInd':int(rr.segmentInd),'distance_m':float(d),'raw_measurement_lon':float(rr.lon),'raw_measurement_lat':float(rr.lat)})
  datasets=[(tile,rasterio.open(extracted['mask'][tile+'.tif'])) for tile in s['tiles']]
  masks=[{'tile':tile,'crs':ds.crs.to_string(),'bounds':list(ds.bounds),'dtype':ds.dtypes[0],'nodata':ds.nodata,'width':ds.width,'height':ds.height,'resolution':list(ds.res)} for tile,ds in datasets]
  samples=[]
  try:
   for i,(lon,lat) in enumerate(ll):
    row=raw.iloc[int(indexes[i])]
    samples.append({'fraction':float(fractions[i]),'lon':float(lon),'lat':float(lat),'nearest_raw_distance_m':float(distances[i]),'nearest_raw_tile':row.raw_tile,'nearest_raw_record_1based':int(row.raw_record_1based),'nearest_raw_segmentID':int(row.segmentID),'raw_within_90m':bool(distances[i]<=90),**mask_sample(datasets,lon,lat,xy[i],crs)})
   case={'source_row':fid,'edge':edge,'local_metric_crs':crs.to_string(),'raw_tiles':tile_metadata,'masks':masks,'endpoints':endpoints,
         'raw_distance_m':{'minimum':float(min(distances)),'median':float(np.median(distances)),'p90':float(np.quantile(distances,.9)),'maximum':float(max(distances))},
         'samples':len(samples),'raw_within_90m':sum(v['raw_within_90m'] for v in samples),'water_at_sample':sum(v['center_has_water'] for v in samples),'water_within_90m':sum(v['water_within_90m'] for v in samples),
         'missing_center_coverage':sum(not any(x['value'] is not None for x in v['center']) for v in samples),'missing_neighborhood_coverage':sum(v['neighborhood_valid_pixels']==0 for v in samples),
         'raw_nearest_segment_keys':sorted({(v['nearest_raw_tile'],v['nearest_raw_segmentID']) for v in samples}),
         'center_value_counts':dict(Counter(str(x['value']) for v in samples for x in v['center'])),'sample_details':samples}
   with (args.output_dir/f'metrics-{fid}.json').open('x') as f:json.dump(case,f,indent=2,allow_nan=False);f.write('\n')
   with ExitStack() as stack:
    plot_masks=[(tile,stack.enter_context(rasterio.vrt.WarpedVRT(ds,crs='EPSG:4326',resampling=rasterio.enums.Resampling.nearest))) for tile,ds in datasets]
    plot_case(args.output_dir/f'feature-{fid}.png',edge,shapely.from_wkb(rows[fid]['geometry']),raw,plot_masks,case)
   report['cases'].append(case)
   print(json.dumps({k:v for k,v in case.items() if k in ['source_row','raw_distance_m','raw_within_90m','water_at_sample','water_within_90m','missing_center_coverage','missing_neighborhood_coverage','endpoints','center_value_counts']}),flush=True)
  finally:
   for _,ds in datasets:ds.close()
  del raw,frames,geoms,tree,g;gc.collect()
 report['status']='completed_diagnostic'
 with (args.output_dir/'comparison.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')

if __name__=='__main__':main()
