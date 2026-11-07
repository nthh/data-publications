#!/usr/bin/env python3
"""Add a verified raw GRWL build to a local viewer runtime, without publication."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import pyarrow as pa
import pyarrow.parquet as pq


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(base, source, source_manifest, display, validation, output, origin):
    if output.exists():
        raise FileExistsError('Refusing to replace a runtime manifest')
    source_meta = json.loads(source_manifest.read_text())
    display_meta = json.loads((display/'manifest.json').read_text())
    checked = json.loads(validation.read_text())
    if checked['status'] != 'passed':
        raise ValueError('Independent display validation must pass before viewing this release')
    asset = display_meta['assets'][0]
    pmtiles = display/asset['path']
    source_hash, display_hash = digest(source), digest(pmtiles)
    if (source_meta['parquet_sha256'] != source_hash or asset['source_asset']['sha256'] != source_hash
            or asset['sha256'] != display_hash or checked['source_sha256'] != source_hash
            or checked['pmtiles_sha256'] != display_hash
            or checked['source_manifest_sha256'] != digest(source_manifest)):
        raise ValueError('Source, display and independent validation checksums do not match')
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+',origin):
        raise ValueError('This preparation command is only for a loopback preview')
    runtime = json.loads(base.read_text())
    if any(d['id']=='grwl-raw' for d in runtime['viewer']['datasets']):
        raise ValueError('Base runtime already includes a raw GRWL layer')
    raw_route = '/nthh/grwl-raw/local-preview/'+source.parent.name+'/grwl-raw.parquet'
    display_route = '/nthh/grwl-raw/local-preview/'+display.name+'/grwl-raw.pmtiles'
    for route,path,sha,mime in [(raw_route,source,source_hash,'application/vnd.apache.parquet'),
            (display_route,pmtiles,display_hash,'application/vnd.pmtiles')]:
        runtime['objects'][route]={'path':str(path.resolve()),'size_bytes':path.stat().st_size,
                                  'sha256':sha,'content_type':mime}
    extents = [t['extent'] for t in source_meta['tiles'] if t['extent'] is not None]
    bounds = [min(b[0] for b in extents), min(b[1] for b in extents),
              max(b[2] for b in extents), max(b[3] for b in extents)]
    parquet = pq.ParquetFile(source)
    schema = parquet.schema_arrow
    analytic = {'format':'geoparquet','object_path':raw_route,'sha256':source_hash,
        'size_bytes':source.stat().st_size,'geometry_column':'geometry','geometry_type':'line',
        'id_field':'feature_id','fields':[f for f in schema.names if f not in ('bbox','geometry')],
        'decimal_fields':[f.name for f in schema if pa.types.is_decimal(f.type)],
        'row_count':source_meta['rows'],'bbox':bounds,
        'covering':{k:'bbox.'+k for k in ('xmin','ymin','xmax','ymax')}}
    scope = 'Global raw vectors' if len(source_meta['tiles'])==829 else f'Local pilot: {len(source_meta["tiles"])} of 829 raw tiles'
    dataset = {'id':'grwl-raw','title':'GRWL raw width observations','release':source.parent.name,
        'state':'prepared','unavailable_reason':None,'license':'CC-BY-4.0',
        'attribution':'Allen and Pavelsky (2018), GRWL vector V01.01; DOI 10.5281/zenodo.18624542',
        'summary':scope+'. '+f'{source_meta["rows"]:,} source observations, kept separate. '
                  'Detailed width varies along the river; value 1 means unknown. This is a local, unpublished preview.',
        'gee':{'status':'not_run','summary':'All supplied records match the original SHP/DBF source. No GEE comparison or independent scientific accuracy claim.'},
        'analytical_assets':[analytic],
        'layers':[{'id':'grwl-raw-display','title':'Raw width observations','format':'pmtiles',
            'object_path':display_route,'size_bytes':pmtiles.stat().st_size,'sha256':display_hash,
            'source_layer':asset['source_layer'],'geometry_type':'line','min_zoom':asset['min_zoom'],
            'max_zoom':asset['max_zoom'],'id_field':'feature_id','id_encoding':'mvt_feature_id',
            'attribute_fields':asset['attribute_fields'],'width_field':'width_m','default_region':'grwl_15450',
            'bbox':bounds,'analytic':analytic}]}
    runtime['viewer']['datasets'].insert(0,dataset)
    for old in runtime['viewer']['datasets']:
        if old['id']=='grwl':
            old['title']='GRWL summary — known geometry errors'
            old['summary']='Historical summary comparison. Confirmed straight connectors are present in the original summary and retained here; use GRWL raw width observations for the new conversion.'
    runtime['viewer']['object_origin']=origin
    regions=[('grwl_15450','GRWL 15450',[-108.25,44.25,-107.75,45.35]),
             ('grwl_11839','GRWL 11839',[-90.05,35.43,-89.95,35.55]),
             ('grwl_13164','GRWL 13164',[-109.9,39.9,-109.3,40.25]),
             ('grwl_15397','GRWL 15397',[-119.7,47.9,-118.9,48.3]),
             ('grwl_15394','GRWL 15394',[-120.25,46.95,-119.75,47.85])]
    known={r['id'] for r in runtime['viewer']['regions']}
    runtime['viewer']['regions'].extend({'id':i,'label':label,'bbox':box} for i,label,box in regions if i not in known)
    runtime['local_preview']={'dataset_id':'grwl-raw','scope':scope,'source_manifest_sha256':digest(source_manifest),
                              'display_validation_sha256':digest(validation),'publication':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(runtime,indent=2)+'\n')
    return {'datasets':len(runtime['viewer']['datasets']),'scope':scope,'rows':source_meta['rows'],'output':str(output)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','source','source-manifest','display','validation','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--origin',default='http://127.0.0.1:8913')
    args=parser.parse_args()
    print(json.dumps(prepare(args.base,args.source,args.source_manifest,args.display,args.validation,args.output,args.origin)))
