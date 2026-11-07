#!/usr/bin/env python3
"""Separate, discrete geometry-distance diagnostic; never changes strict parity."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import subprocess
import time
import numpy as np
from pyproj import CRS, Transformer
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree
from compare import read_json,sha,verify_capture,resolve_field
from provenance import verify_provenance

ROOT=Path(__file__).resolve().parents[2]


def line_parts(geometry):
    g=shape(geometry)
    def visit(part):
        if part.geom_type=='Polygon':
            return [np.asarray(part.exterior.coords,dtype=float)[:,:2]]+[np.asarray(r.coords,dtype=float)[:,:2] for r in part.interiors]
        if part.geom_type in ['LineString','LinearRing','Point']:
            return [np.asarray(part.coords,dtype=float)[:,:2]]
        return [arr for child in part.geoms for arr in visit(child)]
    arrays=visit(g)
    if not arrays or any(len(x)==0 or not np.isfinite(x).all() for x in arrays):raise ValueError('Missing/empty/nonfinite geometry')
    if sum(len(x) for x in arrays)>1_000_000:raise ValueError('Vertex limit exceeded')
    return g,arrays


def projected_arrays(arrays,transformer):
    return [np.column_stack(transformer.transform(x[:,0],x[:,1])) for x in arrays]


def primitives(arrays):
    starts=[];ends=[];singles=[]
    for a in arrays:
        if len(a)>1:starts.append(a[:-1]);ends.append(a[1:])
        else:singles.append(a)
    a=np.concatenate(starts) if starts else np.empty((0,2))
    b=np.concatenate(ends) if ends else np.empty((0,2))
    objects=[]
    if len(a):
        pairs=np.stack([a,b],axis=1);nonzero=np.any(a!=b,axis=1)
        objects.extend(shapely.linestrings(pairs[nonzero]))
        objects.extend(shapely.points(a[~nonzero]))
    if singles:objects.extend(shapely.points(np.concatenate(singles)))
    vertices=np.concatenate(arrays)
    points=np.concatenate([vertices,(a+b)/2]) if len(a) else vertices
    longest=float(np.linalg.norm(b-a,axis=1).max()) if len(a) else 0.0
    return objects,points,longest


def directed(points,objects):
    tree=STRtree(objects);distances=[];witness=None;largest=-1.0
    for offset in range(0,len(points),8192):
        batch=shapely.points(points[offset:offset+8192])
        indices,values=tree.query_nearest(batch,all_matches=False,return_distance=True)
        if len(values)!=len(batch) or not np.isfinite(values).all():raise ValueError('Incomplete/nonfinite nearest-segment query')
        distances.append(values)
        position=int(np.argmax(values))
        if float(values[position])>largest:
            largest=float(values[position])
            point_index=offset+int(indices[0,position]);object_index=int(indices[1,position])
            witness={'query_point_index':point_index,'query_xy':points[point_index].tolist(),'nearest_segment_xy':shapely.get_coordinates(objects[object_index]).tolist()}
    d=np.concatenate(distances)
    return {'sampled_points':len(d),'maximum_m':float(d.max()),'p95_m':float(np.quantile(d,.95)),'witness_projected':witness}


def geometry_diagnostic(local,gee):
    a,aa=line_parts(local);b,bb=line_parts(gee)
    all_xy=np.concatenate(aa+bb)
    angles=np.radians(all_xy[:,0]);lon0=math.degrees(math.atan2(float(np.sin(angles).mean()),float(np.cos(angles).mean())))
    lat0=float(all_xy[:,1].mean())
    projection=CRS.from_proj4(f'+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs')
    tx=Transformer.from_crs('EPSG:4326',projection,always_xy=True)
    ap=projected_arrays(aa,tx);bp=projected_arrays(bb,tx)
    if not all(np.isfinite(x).all() for x in ap+bp):raise ValueError('Projection produced nonfinite values')
    aobjects,apoints,alongest=primitives(ap);bobjects,bpoints,blongest=primitives(bp)
    ab=directed(apoints,bobjects);ba=directed(bpoints,aobjects)
    maximum=max(ab['maximum_m'],ba['maximum_m'])
    inverse=Transformer.from_crs(projection,'EPSG:4326',always_xy=True)
    for result,vertex_count in [(ab,sum(len(x) for x in aa)),(ba,sum(len(x) for x in bb))]:
        witness=result['witness_projected']
        witness['query_kind']='original_vertex' if witness['query_point_index']<vertex_count else 'projected_segment_midpoint'
        witness['query_lonlat']=list(inverse.transform(*witness['query_xy']))
        witness['nearest_segment_lonlat']=[list(inverse.transform(*xy)) for xy in witness['nearest_segment_xy']]
    return {'status':'completed','discrete_within_one_meter':maximum<=1.0,'maximum_sampled_distance_m':maximum,'local_to_gee':ab,'gee_to_local':ba,'local_vertices':sum(len(x) for x in aa),'gee_vertices':sum(len(x) for x in bb),'local_line_or_ring_parts':len(aa),'gee_line_or_ring_parts':len(bb),'local_geometry_type':a.geom_type,'gee_geometry_type':b.geom_type,'local_geometry_valid':bool(a.is_valid),'gee_geometry_valid':bool(b.is_valid),'maximum_projected_segment_length_m':max(alongest,blongest),'projection_center':[lon0,lat0],'claim':'Both directions of every vertex and segment midpoint to opposite line/ring segments. Discrete diagnostic, not continuous Hausdorff or strict parity. No segments join separate parts.'}


def raw_key(properties):
    return (float(properties['lon']),float(properties['lat']),int(properties['segmentID']),int(properties['segmentInd']))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['sample','capture','plan','criteria','followup','comparison','report']:ap.add_argument('--'+n,required=True,type=Path)
    args=ap.parse_args()
    if args.report.exists():raise SystemExit('Choose a new diagnostic report.')
    owned=[str(Path(__file__).resolve()),str(args.followup.resolve())]
    if subprocess.check_output(['git','status','--porcelain','--',*owned],cwd=ROOT,text=True).strip():raise SystemExit('Commit diagnostic code and followup criteria before evaluation.')
    sample,plan,criteria=read_json(args.sample),read_json(args.plan),read_json(args.criteria)
    independent=verify_provenance(args.sample,args.capture,args.plan)
    issues,payloads,_=verify_capture(args.sample,sample,args.capture,args.plan,plan,args.criteria,criteria)
    if issues or independent['status']!='passed':raise SystemExit('Invalid capture/source provenance.')
    report=read_json(args.comparison)
    if report['provenance']['sample_sha256']!=sha(args.sample) or report['provenance']['plan_sha256']!=sha(args.plan):raise SystemExit('Comparison input binding mismatch.')
    layer=sample['dataset_id'];query_features={};index=defaultdict(list);target_query={}
    for req in plan['requests']:
        if '-features-' not in req['id']:continue
        fs=[f for _,body in payloads[req['id']] for f in body.get('features',[])]
        query_features[req['id']]=fs
        for id in req.get('selected_local_ids',[]):target_query[str(id)]=req['id']
        if layer!='grwl-raw':
            for f in fs:index[f['properties'][sample['key_fields'][0]]].append(f)
    results=[];started=time.monotonic()
    for local,previous in zip(sample['features'],report['geometry']['results']):
        if previous.get('diagnostic_pass') is True:continue
        if time.monotonic()-started>1200:raise SystemExit('Diagnostic runtime bound exceeded.')
        if layer=='grwl-raw':
            targets=[f for f in query_features[target_query[str(local['local_id'])]] if raw_key(f['properties'])==raw_key(local['properties'])]
        else:targets=index[local['properties'][sample['key_fields'][0]]]
        row={'local_id':local['local_id'],'previous_diagnostic':previous}
        if len(targets)!=1:row.update(status='incomplete_ambiguous_match',matches=len(targets))
        else:
            try:row.update(geometry_diagnostic(local['geometry'],targets[0]['geometry']))
            except Exception as e:row.update(status='incomplete',error_type=type(e).__name__,error=str(e))
        results.append(row)
        print(json.dumps({'layer':layer,'local_id':local['local_id'],'status':row['status'],'maximum_m':row.get('maximum_sampled_distance_m')}),flush=True)
    output={'schema_version':1,'dataset_id':layer,'status':'completed_explanatory_diagnostic','strict_parity_unchanged':True,'sample_sha256':sha(args.sample),'plan_sha256':sha(args.plan),'comparison_sha256':sha(args.comparison),'criteria_sha256':sha(args.criteria),'followup_criteria_sha256':sha(args.followup),'script_sha256':sha(Path(__file__)),'lock_sha256':sha(Path(__file__).with_name('uv.lock')),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'cases':len(results),'discrete_within_one_meter':sum(r.get('discrete_within_one_meter') is True for r in results),'discrete_over_one_meter':sum(r.get('discrete_within_one_meter') is False for r in results),'incomplete':sum(r['status']!='completed' for r in results),'maximum_sampled_distance_m':max((r.get('maximum_sampled_distance_m',0) for r in results),default=None),'results':results,'claim':'Posthoc diagnostic of previously failed or incomplete geometry metrics only. Strict comparisons unchanged; no exhaustive or scientific-accuracy claim.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__':main()
