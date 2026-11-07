#!/usr/bin/env python3
"""Explicit source-edge and nearby-source follow-up to the frozen GRWL screen."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import numpy as np
import pyarrow.parquet as pq
import shapely
from trace_source_chords import ROOT, GEOD, edge_info, raw_records, source_screen, tile_trace, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    criteria_path = ROOT / 'research/grwl-source-chords-20261102/followup-criteria.json'
    criteria = json.loads(criteria_path.read_text())
    pins = json.loads((criteria_path.parent / 'criteria.json').read_text())['pins']
    paths = {'source_zip': args.data_root / 'next-two-sources/GRWL_summaryStats_V01.02.zip',
             'analytical_parquet': args.data_root / 'grwl/summary-v01.02-local-r1/grwl/grwl-summary-v0102.parquet',
             'current_pmtiles': args.data_root / 'grwl/display/display-v1/assets/grwl.pmtiles',
             'original_pmtiles': args.data_root / 'grwl/summary-v01.02-local-r1/grwl/grwl-display.pmtiles'}
    hashes = {k:sha256(v) for k,v in paths.items()}
    assert all(pins[k + '_sha256'] == v for k,v in hashes.items())
    rows = pq.read_table(paths['analytical_parquet']).to_pylist()
    by_id = {r['source_row']: r for r in rows}
    edges = []
    for e in criteria['selected_edges']:
        xy = np.asarray(list(shapely.from_wkb(by_id[e['source_row']]['geometry']).geoms)[e['part']].coords)
        a,b = xy[e['edge']:e['edge']+2]
        edges.append(edge_info(e['source_row'], e['part'], e['edge'], a, b, GEOD.inv(*a,*b)[2]))
    nearby = []
    region = shapely.box(*criteria['nearby_source_search']['bbox'])
    for row in rows:
        geometry = shapely.from_wkb(row['geometry'])
        if not geometry.intersects(region):
            continue
        for j,part in enumerate(geometry.geoms):
            xy = np.asarray(part.coords)
            a,b = xy[:-1],xy[1:]
            lengths = GEOD.inv(a[:,0],a[:,1],b[:,0],b[:,1])[2]
            for k in np.flatnonzero(lengths >= criteria['nearby_source_search']['minimum_geodesic_edge_metres']):
                # Limit the edge itself, not merely its parent feature, to this region.
                if shapely.LineString([a[k],b[k]]).intersects(region):
                    nearby.append(edge_info(row['source_row'],j,int(k),a[k],b[k],lengths[k]))
    ids = sorted({e['source_row'] for e in edges + nearby})
    raw, metadata = raw_records(paths['source_zip'], ids)
    _, records = source_screen([by_id[i] for i in ids], raw)
    all_edges = {(e['source_row'],e['part'],e['edge']):e for e in edges + nearby}
    traces = {kind:tile_trace(paths[kind], [by_id[i] for i in ids], list(all_edges.values()), ids)
              for kind in ('original_pmtiles','current_pmtiles')}
    z10 = [e for r in traces['current_pmtiles'] if r['zoom']==10 for e in r['edge_distances']]
    parity = all(r['all_coordinate_bits_and_parts_equal'] and r['all_ten_dbf_values_equal'] for r in records)
    report = {'schema_version':1,'recorded_at':datetime.now(timezone.utc).isoformat(),
              'criteria_sha256':sha256(criteria_path),'script_sha256':sha256(__file__),
              'helper_sha256':sha256(Path(__file__).with_name('trace_source_chords.py')), 'input_sha256':hashes,
              'explicit_edges':edges,'nearby_edges_over_10km':nearby,'source_records':records,
              'tile_traces':traces,'all_source_parity_checks_pass':parity,
              'all_current_z10_edge_checks_pass':bool(z10) and all(e['z10_within_30m'] for e in z10),
              'upstream_processing_stage_established':False}
    with args.output.open('x') as f:
        json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'nearby_edges':nearby,'source_ids':ids,'parity':parity,
                      'z10_current':[r for r in traces['current_pmtiles'] if r['zoom']==10]},indent=2))


if __name__ == '__main__':
    main()
