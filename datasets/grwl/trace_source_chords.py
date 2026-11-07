#!/usr/bin/env python3
"""Read-only source/PMTiles investigation of long axis-aligned GRWL edges.

Thresholds and selected IDs are frozen in the referenced research criteria.
This screen identifies candidates, not certified errors, and never repairs data.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pyarrow.parquet as pq
from pyproj import Geod
import shapely
from shapely.geometry import LineString

sys.dont_write_bytecode = True
from validate_display_wrap import (Archive, TRANSFORM, bbox_tiles, comparison_components,
                                   core, matching, sha256)

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / 'research/grwl-source-chords-20261102/criteria.json'
GEOD = Geod(ellps='WGS84')
AXIS_EPS = 0.0001
MIN_LENGTH_M = 1000


def raw_records(path, ids):
    with zipfile.ZipFile(path) as z:
        shp, shx, dbf, xml = [z.read('GRWL_summaryStats.' + suffix) for suffix in ('shp', 'shx', 'dbf', 'shp.xml')]
    header_len, record_len = struct.unpack_from('<HH', dbf, 8)
    fields, offset = [], 1
    for start in range(32, header_len - 1, 32):
        descriptor = dbf[start:start + 32]
        fields.append((descriptor[:11].split(b'\0')[0].decode('ascii'), offset, descriptor[16]))
        offset += descriptor[16]
    selected = {}
    for fid in ids:
        offset_words, _ = struct.unpack_from('>ii', shx, 100 + 8 * (fid - 1))
        start = offset_words * 2 + 8
        if struct.unpack_from('<i', shp, start)[0] != 3:
            raise ValueError('Expected SHP PolyLine')
        part_count, count = struct.unpack_from('<ii', shp, start + 36)
        starts = struct.unpack_from('<' + 'i' * part_count, shp, start + 44)
        xy = np.frombuffer(shp, dtype='<f8', count=count * 2, offset=start + 44 + 4 * part_count).reshape(-1, 2)
        record = dbf[header_len + (fid - 1) * record_len:header_len + fid * record_len]
        values = {}
        for name, offset, width in fields:
            text = record[offset:offset + width].strip().decode('ascii')
            values[name] = Decimal(text) if text and set(text) != {'*'} else None
        selected[fid] = {'parts': [xy[a:b] for a, b in zip(starts, starts[1:] + (count,))], 'values': values}
    tree = ET.fromstring(xml)
    metadata = {'xml_sha256': hashlib.sha256(xml).hexdigest(),
                'resource_titles': [e.text for e in tree.iter('resTitle')],
                'processes': [{'attributes': e.attrib, 'text': e.text} for e in tree.iter('Process')],
                'member_sha256': {suffix: hashlib.sha256(data).hexdigest() for suffix, data in [('shp', shp), ('shx', shx), ('dbf', dbf)]}}
    return selected, metadata


def edge_info(fid, part, edge, a, b, metres):
    delta = np.abs(b - a)
    orientation = 'horizontal' if delta[1] <= delta[0] else 'vertical'
    axis = 1 if orientation == 'horizontal' else 0
    step = 4 if orientation == 'horizontal' else 6
    midpoint = (a[axis] + b[axis]) / 2
    grid = round(midpoint / step) * step
    return {'source_row': fid, 'part': part, 'edge': edge, 'coordinates': [a.tolist(), b.tolist()],
            'geodesic_metres': float(metres), 'delta_lon': float(b[0] - a[0]), 'delta_lat': float(b[1] - a[1]),
            'orientation': orientation, 'nearest_grid_coordinate': grid,
            'max_endpoint_grid_distance_degrees': float(max(abs(a[axis] - grid), abs(b[axis] - grid))),
            'near_provisional_4lat_6lon_grid': bool(max(abs(a[axis] - grid), abs(b[axis] - grid)) <= AXIS_EPS)}


def source_screen(rows, selected):
    flagged, records, edge_count = [], [], 0
    for row in rows:
        fid = row['source_row']
        parts = list(shapely.from_wkb(row['geometry']).geoms)
        longest = []
        for j, part in enumerate(parts):
            xy = np.asarray(part.coords, dtype='<f8')
            a, b = xy[:-1], xy[1:]
            if not len(a):
                continue
            lengths = GEOD.inv(a[:, 0], a[:, 1], b[:, 0], b[:, 1])[2]
            delta = np.abs(b - a)
            eligible = (lengths >= MIN_LENGTH_M) & (delta.min(axis=1) <= AXIS_EPS) & (delta[:, 0] <= 180)
            for index in np.flatnonzero(eligible):
                flagged.append(edge_info(fid, j, int(index), a[index], b[index], lengths[index]))
            if fid in selected:
                for index in np.argsort(lengths)[-10:]:
                    longest.append(edge_info(fid, j, int(index), a[index], b[index], lengths[index]))
            edge_count += len(a)
        if fid in selected:
            raw = selected[fid]
            equal = len(parts) == len(raw['parts']) and all(
                np.array_equal(np.asarray(p.coords, dtype='<f8').view('<u8'), q.view('<u8'))
                for p, q in zip(parts, raw['parts']))
            records.append({'source_row': fid, 'OBJECTID': str(row['OBJECTID']), 'producer_ID': str(row['ID']),
                            'width_mean_metres': str(row['width_mean']), 'bbox': list(shapely.from_wkb(row['geometry']).bounds),
                            'parts': len(parts), 'vertices': sum(len(p.coords) for p in parts),
                            'all_coordinate_bits_and_parts_equal': equal,
                            'all_ten_dbf_values_equal': all(row[k] == v for k, v in raw['values'].items()),
                            'original_dbf_values': {k: str(v) if v is not None else None for k, v in raw['values'].items()},
                            'longest_edges': sorted(longest, key=lambda x: x['geodesic_metres'], reverse=True)[:10]})
    counts = Counter((e['orientation'], e['nearest_grid_coordinate']) for e in flagged if e['near_provisional_4lat_6lon_grid'])
    return {'rows_scanned': len(rows), 'edges_scanned': edge_count, 'screened_edges': len(flagged),
            'screened_feature_count': len({e['source_row'] for e in flagged}),
            'near_grid_edges': sum(e['near_provisional_4lat_6lon_grid'] for e in flagged),
            'near_grid_feature_count': len({e['source_row'] for e in flagged if e['near_provisional_4lat_6lon_grid']}),
            'grid_counts': [{'orientation': o, 'coordinate': c, 'edges': n} for (o, c), n in sorted(counts.items())],
            'warning': 'Exploratory screen only. It includes possible real straight reaches and is not a list of confirmed errors.',
            'flagged_edges': flagged}, records


def tile_trace(path, rows, flagged, ids):
    archive = Archive(path)
    report = []
    try:
        for row in rows:
            fid = row['source_row']
            if fid not in ids:
                continue
            source = shapely.transform(shapely.from_wkb(row['geometry']), lambda xy: np.column_stack(TRANSFORM.transform(xy[:, 0], xy[:, 1])))
            edges = [e for e in flagged if e['source_row'] == fid]
            for z in range(11):
                components, occurrences = [], 0
                tiles = bbox_tiles(source.bounds, z)
                for x, y in sorted(tiles):
                    for geom in matching(archive, z, x, y, fid):
                        occurrences += 1
                        components.extend(comparison_components(geom.intersection(core(x, y, z))))
                union = shapely.union_all(components)
                edge_distances = []
                for edge in edges:
                    projected = LineString([TRANSFORM.transform(*p) for p in edge['coordinates']])
                    points = shapely.line_interpolate_point(projected, np.linspace(0, 1, 101), normalized=True)
                    dist = float(np.max(shapely.distance(points, union))) if not union.is_empty else None
                    edge_distances.append({'part': edge['part'], 'edge': edge['edge'], 'max_sample_distance_mercator_m': dist,
                                           'z10_within_30m': dist is not None and dist <= 30 if z == 10 else None})
                report.append({'source_row': fid, 'zoom': z, 'tiles_probed': len(tiles), 'feature_occurrences': occurrences,
                               'edge_distances': edge_distances})
    finally:
        archive.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite a diagnostic report')
    criteria = json.loads(CRITERIA.read_text())
    ids = criteria['selection']['user_selected_source_rows']
    paths = {'source_zip': args.data_root / 'next-two-sources/GRWL_summaryStats_V01.02.zip',
             'analytical_parquet': args.data_root / 'grwl/summary-v01.02-local-r1/grwl/grwl-summary-v0102.parquet',
             'current_pmtiles': args.data_root / 'grwl/display/display-v1/assets/grwl.pmtiles',
             'original_pmtiles': args.data_root / 'grwl/summary-v01.02-local-r1/grwl/grwl-display.pmtiles'}
    pins = {key: sha256(path) for key, path in paths.items()}
    if any(value != criteria['pins'][key + '_sha256'] for key, value in pins.items()):
        raise SystemExit('Input checksum differs from frozen criteria')
    selected, metadata = raw_records(paths['source_zip'], ids)
    rows = pq.read_table(paths['analytical_parquet']).to_pylist()
    screened, records = source_screen(rows, selected)
    traces = {kind: tile_trace(paths[kind], rows, screened['flagged_edges'], ids) for kind in ('original_pmtiles', 'current_pmtiles')}
    report = {'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'criteria_sha256': sha256(CRITERIA), 'script_sha256': sha256(__file__), 'input_sha256': pins,
              'source_metadata': metadata, 'selected_records': records, 'global_screen': screened, 'tile_traces': traces,
              'source_unchanged': True, 'scientific_validity_claimed': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({'selected_records': records, 'screen_summary': {k:v for k,v in screened.items() if k not in ('flagged_edges','grid_counts')},
                      'current_z10': [r for r in traces['current_pmtiles'] if r['zoom'] == 10]}, indent=2))


if __name__ == '__main__':
    main()
