#!/usr/bin/env python3
"""Bind passed source/overview and exact-payload gates to a new local viewer."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[2]
CRITERIA=ROOT/'research/grwl-width-overview-20261106/criteria.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def require(condition,message):
    if not condition:raise ValueError(message)


def prepare(base,source,source_manifest,archive,overview_report,combine_report,output,origin):
    require(not output.exists() and not output.is_symlink(),'Runtime output already exists')
    require(re.fullmatch(r'http://127\.0\.0\.1:[0-9]+',origin),'Loopback preview only')
    source_hash,archive_hash=digest(source),digest(archive)
    meta=json.loads(source_manifest.read_text())
    overview=json.loads(overview_report.read_text());combined=json.loads(combine_report.read_text())
    require(meta['parquet_sha256']==source_hash,'Source manifest does not bind Parquet')
    require(overview.get('status')=='passed' and overview.get('source_sha256')==source_hash
        and overview.get('source_manifest_sha256')==digest(source_manifest)
        and overview.get('criteria_sha256')==digest(CRITERIA),'Overview source gate is missing or unbound')
    require(combined.get('combine_status')=='passed' and combined.get('combined',{}).get('sha256')==archive_hash
        and combined.get('combined',{}).get('size_bytes')==archive.stat().st_size,'Combined archive gate is unbound')
    require(combined.get('overview',{}).get('receipt_sha256')==digest(overview_report)
        and combined.get('overview',{}).get('sha256')==overview.get('archive_sha256'),'Combination does not bind passed overview')
    require(all(combined.get('verification',{}).get(key) is True for key in (
        'detail_raw_payloads_byte_identical','overview_raw_payloads_byte_identical','no_extra_or_overlapping_coordinates')),
        'Exact payload checks did not pass')
    parquet=pq.ParquetFile(source);column=parquet.schema.names.index('feature_id');previous=-1
    for index in range(parquet.metadata.num_row_groups):
        stats=parquet.metadata.row_group(index).column(column).statistics
        require(stats and stats.has_min_max and not stats.null_count and stats.min>previous,
            'Exact-ID lookup needs disjoint ordered row-group statistics')
        require(stats.max<=2**53-1,'Source ID exceeds browser integer precision')
        previous=stats.max
    runtime=json.loads(base.read_text())
    dataset=deepcopy(next(d for d in runtime['viewer']['datasets'] if d['id']=='grwl-raw'))
    layer=dataset['layers'][0];analytic=layer['analytic']
    for route in (layer['object_path'],analytic['object_path']):runtime['objects'].pop(route,None)
    raw_route=f'/nthh/grwl-raw/local-preview/{source_hash[:12]}/observations.parquet'
    display_route=f'/nthh/grwl-raw/local-preview/{archive_hash[:12]}/widths.pmtiles'
    for route,path,sha,mime in ((raw_route,source,source_hash,'application/vnd.apache.parquet'),(display_route,archive,archive_hash,'application/vnd.pmtiles')):
        runtime['objects'][route]={'path':str(path.resolve()),'size_bytes':path.stat().st_size,'sha256':sha,'content_type':mime}
    extents=[tile['extent'] for tile in meta['tiles'] if tile['extent']]
    bounds=[min(v[0] for v in extents),min(v[1] for v in extents),max(v[2] for v in extents),max(v[3] for v in extents)]
    analytic.update(object_path=raw_route,sha256=source_hash,size_bytes=source.stat().st_size,
        row_count=meta['rows'],bbox=bounds,lookup_mode='exact_id')
    dataset['analytical_assets']=[analytic]
    layer.update(object_path=display_route,sha256=archive_hash,size_bytes=archive.stat().st_size,
        min_zoom=0,max_zoom=12,detail_min_zoom=8,attribute_fields=['width_m','width_valid'],
        overview={'source_layer':'grwl_width_overview','mode':'width_samples','min_zoom':0,'max_zoom':7,
            'cells_per_tile':1024,'selection':'Widest valid width; ties use smallest source ID',
            'meaning':'Selected observations; widest measured width per screen-scale cell.'},
        bbox=bounds,default_region='global')
    dataset.update(release='raw-v01.01-display-r3-preview',
        summary=f'{meta["rows"]:,} original observations. Source widths are visible at every zoom. Overview symbols select the widest valid source observation per screen-scale cell; detailed source segments appear from zoom 8. Symbols are exaggerated and capped, not riverbanks. Local unpublished preview.')
    runtime['viewer']['datasets']=[dataset if d['id']=='grwl-raw' else d for d in runtime['viewer']['datasets']]
    runtime['viewer']['object_origin']=origin
    runtime['local_preview']={'dataset_id':'grwl-raw','publication':False,'source_manifest_sha256':digest(source_manifest),
        'overview_validation_sha256':digest(overview_report),'combine_validation_sha256':digest(combine_report),
        'criteria_sha256':digest(CRITERIA),'exact_id_statistics':{'row_groups':parquet.metadata.num_row_groups,
            'ordered_nonoverlapping':True,'nulls':0,'maximum_id':previous}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:stream.write(json.dumps(runtime,indent=2)+'\n')
    return {'status':'prepared_local_preview','source_sha256':source_hash,'archive_sha256':archive_hash,'runtime':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','source','source-manifest','archive','overview-report','combine-report','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--origin',default='http://127.0.0.1:8919')
    args=parser.parse_args()
    print(json.dumps(prepare(args.base,args.source,args.source_manifest,args.archive,args.overview_report,args.combine_report,args.output,args.origin)))
