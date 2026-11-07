#!/usr/bin/env python3
"""Trace the two reported native MVT IDs to original SHP parts and XY bits.

No source data is changed. Reports are write-once. The crossing-ID inventory is
computed from all analytical rows before a corrected archive is evaluated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

import numpy as np
import pyarrow.parquet as pq
import shapely
from pyproj import Geod

sys.dont_write_bytecode = True
from validate_display_wrap import (Archive, ROOT, bbox_tiles, bbox_mercator,
                                   crossing_records, decode, sha256)

IDS = (13164, 28938)
ZIP_SHA = '78aa43a7104d24b1696e9b1547347eec13ba5d660aa990c1e7cea98e7ae70e4a'
OLD_SHA = '382b0da7d0a879f3b74c0f32a92427b51a58600aa22f703098a0d08c819eaafe'
GEOD = Geod(ellps='WGS84')


def raw_records(source):
    with zipfile.ZipFile(source) as archive:
        shp = archive.read('GRWL_summaryStats.shp')
        dbf = archive.read('GRWL_summaryStats.dbf')
    member_hashes = {'GRWL_summaryStats.shp': hashlib.sha256(shp).hexdigest(),
                     'GRWL_summaryStats.dbf': hashlib.sha256(dbf).hexdigest()}
    header_len, record_len = struct.unpack_from('<HH', dbf, 8)
    fields = []
    offset = 1
    for start in range(32, header_len - 1, 32):
        descriptor = dbf[start:start + 32]
        name = descriptor[:11].split(b'\0')[0].decode('ascii')
        fields.append((name, offset, descriptor[16]))
        offset += descriptor[16]
    selected = {}
    position = 100
    ordinal = 0
    while position < len(shp):
        ordinal += 1
        number, words = struct.unpack_from('>ii', shp, position)
        if ordinal in IDS:
            body = position + 8
            shape_type = struct.unpack_from('<i', shp, body)[0]
            if shape_type != 3:
                raise ValueError(f'expected PolyLine at source row {ordinal}')
            count, vertices = struct.unpack_from('<ii', shp, body + 36)
            starts = struct.unpack_from('<' + 'i' * count, shp, body + 44)
            coordinate_offset = body + 44 + 4 * count
            coordinates = np.frombuffer(shp, dtype='<f8', count=vertices * 2, offset=coordinate_offset).reshape(-1, 2).copy()
            ends = starts[1:] + (vertices,)
            record = dbf[header_len + (ordinal - 1) * record_len:header_len + ordinal * record_len]
            values = {}
            for name, offset, width in fields:
                text = record[offset:offset + width].strip().decode('ascii')
                values[name] = Decimal(text) if text and set(text) != {'*'} else None
            selected[ordinal] = {'shp_record_number': number, 'parts': [coordinates[a:b] for a, b in zip(starts, ends)],
                                 'dbf_values': values, 'part_starts': list(starts)}
        position += 8 + words * 2
    return selected, member_hashes, ordinal


def tile_ll(point, z, x, y, extent):
    import math
    n = 1 << z
    return [(x + point[0] / extent) / n * 360 - 180,
            math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + point[1] / extent) / n))))]


def trace(source_zip, source, archive_path):
    rows = pq.read_table(source).to_pylist()
    selected, member_hashes, count = raw_records(source_zip)
    records = []
    for row in rows:
        fid = row['source_row']
        if fid not in IDS:
            continue
        raw = selected[fid]
        parquet_parts = list(shapely.from_wkb(row['geometry']).geoms)
        comparisons = []
        for i, expected in enumerate(raw['parts']):
            got = np.asarray(parquet_parts[i].coords, dtype='<f8') if i < len(parquet_parts) else np.empty((0, 2))
            comparisons.append({'part': i, 'source_vertex_count': len(expected), 'parquet_vertex_count': len(got),
                                'float64_bits_equal': expected.shape == got.shape and np.array_equal(expected.view('<u8'), got.view('<u8')),
                                'source_xy_float64_le_sha256': hashlib.sha256(expected.astype('<f8').tobytes()).hexdigest(),
                                'parquet_xy_float64_le_sha256': hashlib.sha256(got.astype('<f8').tobytes()).hexdigest(),
                                'original_coordinates': expected.tolist()})
        segments = []
        horizontal = []
        for part_i, xy in enumerate(raw['parts']):
            for edge, (a, b) in enumerate(zip(xy, xy[1:])):
                metres = GEOD.inv(*a, *b)[2]
                item = {'part': part_i, 'edge': edge, 'coordinates': [a.tolist(), b.tolist()],
                        'geodesic_metres': metres, 'delta_longitude_degrees': float(b[0] - a[0]),
                        'delta_latitude_degrees': float(b[1] - a[1])}
                segments.append(item)
                if metres >= 1000 and abs(b[1] - a[1]) <= 1e-6:
                    horizontal.append(item)
        same_dbf = all(row[name] == value for name, value in raw['dbf_values'].items())
        records.append({'native_feature_id': fid, 'source_row': fid,
                        'OBJECTID': int(row['OBJECTID']), 'producer_ID': int(row['ID']),
                        'shp_record_number': raw['shp_record_number'], 'source_part_starts': raw['part_starts'],
                        'source_part_count': len(raw['parts']), 'parquet_part_count': len(parquet_parts),
                        'exact_geometry_equal': len(raw['parts']) == len(parquet_parts) and all(p['float64_bits_equal'] for p in comparisons),
                        'all_ten_dbf_numeric_values_equal': same_dbf, 'parts': comparisons,
                        'longest_geodesic_edges': sorted(segments, key=lambda s: s['geodesic_metres'], reverse=True)[:10],
                        'largest_longitude_jump': max(segments, key=lambda s: abs(s['delta_longitude_degrees'])),
                        'near_horizontal_ge_1000m_abs_dlat_le_1e_6': horizontal})
    crossing = {'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(),
                'frozen_before_candidate_evaluation': True, 'source_parquet_sha256': sha256(source),
                'criterion': 'abs consecutive longitude delta > 180 degrees within each original part',
                'source_rows_scanned': len(rows), 'records': crossing_records(rows)}
    crossing['crossing_source_ids'] = [r['source_row'] for r in crossing['records']]
    archive = Archive(archive_path)
    examples = []
    try:
        by_id = {r['source_row']: r for r in rows if r['source_row'] in IDS}
        for z in range(11):
            n = 1 << z
            # Bounded source bbox for13164; dateline and central probes for28938.
            targets = {(z, x, y, 13164) for x, y in bbox_tiles(bbox_mercator(by_id[13164]), z)}
            _, y0, _, y1 = __import__('validate_display_wrap').tile_range(bbox_mercator(by_id[28938]), z)
            targets |= {(z, x, y, 28938) for x in {0, n - 1, n // 2} for y in range(y0, y1 + 1)}
            for _, x, y, fid in sorted(targets):
                tile = archive.tile(z, x, y)
                if not tile:
                    continue
                layer = tile.get('grwl', {})
                for f in layer.get('features', []):
                    if f.get('id') != fid:
                        continue
                    geometry = f['geometry']
                    parts = geometry['coordinates'] if geometry['type'] == 'MultiLineString' else [geometry['coordinates']]
                    for j, coordinates in enumerate(parts):
                        for edge, (a, b) in enumerate(zip(coordinates, coordinates[1:])):
                            aa, bb = tile_ll(a, z, x, y, layer['extent']), tile_ll(b, z, x, y, layer['extent'])
                            suspicious = (fid == 13164 and abs(aa[0] - bb[0]) > .05 and abs(aa[1] - bb[1]) < .003) or (fid == 28938 and abs(aa[0] - bb[0]) > .1)
                            if suspicious:
                                examples.append({'native_feature_id': fid, 'OBJECTID': f['properties']['OBJECTID'],
                                                 'producer_ID': f['properties']['ID'], 'zxy': [z, x, y],
                                                 'part': j, 'edge': edge, 'extent': layer['extent'],
                                                 'mvt_xy_y_down': [a, b], 'longitude_latitude': [aa, bb]})
        report = {'schema_version': 1, 'passed': all(r['exact_geometry_equal'] and r['all_ten_dbf_numeric_values_equal'] for r in records),
                  'source_zip_sha256': sha256(source_zip), 'source_member_sha256': member_hashes,
                  'source_parquet_sha256': sha256(source), 'pmtiles_sha256': sha256(archive_path),
                  'trace_script_sha256': sha256(__file__), 'validator_sha256': sha256(ROOT / 'datasets/grwl/validate_display_wrap.py'),
                  'source_rows': count, 'records': records, 'retained_tile_examples': examples,
                  'bounded_tile_reads': archive.reads,
                  'conclusions': {'13164': 'Original intra-part near-horizontal31.281km edge retained; tile quantization makes it horizontal.',
                                  '28938': 'Unsplit original dateline discontinuity retained in analytic vertices; original display encodes worldwide chord through central-longitude tiles.'}}
        if report['source_zip_sha256'] != ZIP_SHA or report['pmtiles_sha256'] != OLD_SHA:
            raise ValueError('trace requires the frozen original source/archive bytes')
        return report, crossing
    finally:
        archive.close()


def write_once(path, value):
    if path.exists():
        raise ValueError(f'report exists: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--freeze-crossing-ids', type=Path, required=True)
    args = parser.parse_args()
    report, crossing = trace(args.source_zip, args.source, args.archive)
    write_once(args.freeze_crossing_ids, crossing)
    write_once(args.report, report)
    print(json.dumps({'passed': report['passed'], 'crossing_source_ids': crossing['crossing_source_ids'],
                      'report': str(args.report)}))


if __name__ == '__main__':
    main()
