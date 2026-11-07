#!/usr/bin/env python3
"""Bind a validated multiscale candidate to a new local viewer runtime."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import pyarrow.parquet as pq


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(base,source,source_manifest,archive,detail,overview,source_check,output,origin):
    if output.exists():raise FileExistsError('Runtime output already exists')
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+',origin):raise ValueError('Loopback preview only')
    source_hash,archive_hash=digest(source),digest(archive)
    meta=json.loads(source_manifest.read_text())
    d,o,s=[json.loads(p.read_text()) for p in (detail,overview,source_check)]
    if any(r.get('status')!='passed' for r in (d,o,s)):raise ValueError('All independent gates must pass before preview')
    if meta['parquet_sha256']!=source_hash:raise ValueError('Source hash mismatch')
    if d['candidate']['sha256']!=archive_hash or not d['semantic_preservation'] or not d['tile_byte_gate']:raise ValueError('Detail comparison mismatch')
    if o['archive_sha256']!=archive_hash:raise ValueError('Overview archive check does not bind this archive')
    if s['source_sha256']!=source_hash or s.get('finest_mask_sha256')!=o['finest_mask_sha256']:raise ValueError('Source coverage check mismatch')
    if s['source_manifest_sha256']!=digest(source_manifest):raise ValueError('Source manifest check mismatch')
    f=pq.ParquetFile(source);ci=f.schema.names.index('feature_id');previous=-1
    for i in range(f.metadata.num_row_groups):
        stats=f.metadata.row_group(i).column(ci).statistics
        if stats is None or not stats.has_min_max or stats.null_count or stats.min<=previous:
            raise ValueError('Exact ID lookup requires complete, disjoint ordered row-group ID statistics')
        if stats.max>2**53-1:raise ValueError('Feature ID exceeds exact browser integer range')
        previous=stats.max
    runtime=json.loads(base.read_text())
    current=next(d for d in runtime['viewer']['datasets'] if d['id']=='grwl-raw')
    dataset=deepcopy(current);layer=dataset['layers'][0];analytic=layer['analytic']
    for path in (layer['object_path'],analytic['object_path']):runtime['objects'].pop(path,None)
    raw_route='/nthh/grwl-raw/local-preview/'+source.parent.name+'/grwl-raw.parquet'
    display_route='/nthh/grwl-raw/local-preview/'+archive.parent.parent.name+'/grwl-multiscale.pmtiles'
    for route,path,sha,mime in ((raw_route,source,source_hash,'application/vnd.apache.parquet'),(display_route,archive,archive_hash,'application/vnd.pmtiles')):
        runtime['objects'][route]={'path':str(path.resolve()),'size_bytes':path.stat().st_size,'sha256':sha,'content_type':mime}
    extents=[t['extent'] for t in meta['tiles'] if t['extent']]
    bounds=[min(b[0] for b in extents),min(b[1] for b in extents),max(b[2] for b in extents),max(b[3] for b in extents)]
    analytic.update(object_path=raw_route,sha256=source_hash,size_bytes=source.stat().st_size,row_count=meta['rows'],bbox=bounds,lookup_mode='exact_id')
    dataset['analytical_assets']=[analytic]
    layer.update(object_path=display_route,sha256=archive_hash,size_bytes=archive.stat().st_size,min_zoom=0,max_zoom=12,detail_min_zoom=8,
                 attribute_fields=['width_m','width_valid'],overview={'source_layer':'grwl_overview','min_zoom':0,'max_zoom':7,'cells_per_tile':512,'meaning':'Source observation coverage; no width or feature lookup'},bbox=bounds,default_region='global')
    dataset.update(release='raw-v01.01-display-r2-preview',summary=f'{meta["rows"]:,} original observations. Coverage is visible at zooms 0–7; individual source widths appear from zoom 8. Coverage cells are not riverbanks. Local unpublished preview.')
    runtime['viewer']['datasets']=[dataset if d['id']=='grwl-raw' else d for d in runtime['viewer']['datasets']]
    runtime['viewer']['object_origin']=origin
    runtime['local_preview']={'dataset_id':'grwl-raw','publication':False,'source_manifest_sha256':digest(source_manifest),
       'detail_comparison_sha256':digest(detail),'overview_validation_sha256':digest(overview),'source_coverage_validation_sha256':digest(source_check),
       'exact_id_statistics':{'row_groups':f.metadata.num_row_groups,'ordered_nonoverlapping':True,'nulls':0,'maximum_id':previous}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:stream.write(json.dumps(runtime,indent=2)+'\n')
    return {'status':'prepared_local_preview','source_sha256':source_hash,'archive_sha256':archive_hash,'runtime':str(output)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','source','source-manifest','archive','detail','overview','source-check','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--origin',default='http://127.0.0.1:8917')
    a=p.parse_args();print(json.dumps(prepare(a.base,a.source,a.source_manifest,a.archive,a.detail,a.overview,a.source_check,a.output,a.origin)))
