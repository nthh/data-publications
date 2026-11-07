#!/usr/bin/env python3
"""Trace source vertices responsible for one-sided large-lake discrepancies."""
import argparse
import json
from pathlib import Path
from pyproj import Geod
from diagnose_geometry import line_parts
from compare import sha


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['sample','diagnostic','report']:ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args()
    if a.report.exists():raise SystemExit('Choose a new report.')
    sample=json.loads(a.sample.read_text());diagnostic=json.loads(a.diagnostic.read_text())
    if diagnostic['sample_sha256']!=sha(a.sample):raise SystemExit('Sample binding mismatch.')
    local={str(r['local_id']):r for r in sample['features']};geod=Geod(ellps='WGS84');rows=[]
    for r in diagnostic['results']:
        if r.get('discrete_within_one_meter') is not False:continue
        witness=r['local_to_gee']['witness_projected']
        if witness['query_kind']!='original_vertex':continue
        feature=local[r['local_id']];_,parts=line_parts(feature['geometry']);offset=witness['query_point_index']
        for part_index,part in enumerate(parts):
            if offset>=len(part):offset-=len(part);continue
            tip=part[offset];prev=part[offset-1] if offset else part[-2];nxt=part[offset+1] if offset<len(part)-1 else part[1]
            distance=lambda x,y:float(geod.inv(float(x[0]),float(x[1]),float(y[0]),float(y[1]))[2])
            area=abs(float(geod.polygon_area_perimeter([prev[0],tip[0],nxt[0]],[prev[1],tip[1],nxt[1]])[0]))
            rows.append({'local_id':r['local_id'],'lake_name':feature['properties'].get('Lake_name'),'source_part_index':part_index,'source_vertex_index_in_part':offset,'previous_lonlat':prev.tolist(),'tip_lonlat':tip.tolist(),'next_lonlat':nxt.tolist(),'base_width_m':distance(prev,nxt),'previous_to_tip_m':distance(prev,tip),'next_to_tip_m':distance(nxt,tip),'triangle_geodesic_area_m2':area,'local_minus_gee_vertex_count':r['local_vertices']-r['gee_vertices'],'source_to_gee_distance_m':r['local_to_gee']['maximum_m'],'gee_to_source_distance_m':r['gee_to_local']['maximum_m'],'source_geometry_valid':r['local_geometry_valid'],'interpretation':'Neighboring source vertices surround a long thin feature. Its base width and missing vertices are observations; GEE ingestion/normalization as the cause remains an inference without the original ingestion manifest.'})
            break
    report={'schema_version':1,'status':'source_vertex_traces_recorded','sample_sha256':sha(a.sample),'diagnostic_sha256':sha(a.diagnostic),'script_sha256':sha(Path(__file__)),'data_modified':False,'strict_parity_unchanged':True,'cases':rows}
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(rows),flush=True)

if __name__=='__main__':main()
