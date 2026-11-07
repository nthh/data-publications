#!/usr/bin/env python3
"""Independent GRWL display oracle, with explicit z10 and antimeridian references.

Run --wrap-only against the historical archive to preserve its failing regression.
The default additionally checks every z10 feature/attribute and frozen samples.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import OrderedDict
from pathlib import Path

import mapbox_vector_tile
import numpy as np
import pyarrow.parquet as pq
import shapely
from pmtiles.reader import Reader, MmapSource, all_tiles
from pyproj import Transformer
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, shape

ROOT = Path(__file__).resolve().parents[2]
ZOOM = 10
HALF = 20037508.342789244
WORLD = HALF * 2
TOLERANCE = 30.0
REGIONS = json.loads((ROOT / 'research/pmtiles-all-20261102/criteria.json').read_text())['geographic_controls']
SOURCE_SHA = '82ac4eeac2168b1aad6e5c9ae53c0c228ffcc7c8cd3f8d795493d939e626fa9c'
TRANSFORM = Transformer.from_crs(4326, 3857, always_xy=True, force_over=True)


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def crossing_records(rows):
    found = []
    for row in rows:
        jumps = []
        for j, part in enumerate(shapely.from_wkb(row['geometry']).geoms):
            coords = list(part.coords)
            for i, (a, b) in enumerate(zip(coords, coords[1:])):
                if abs(b[0] - a[0]) > 180:
                    jumps.append({'part': j, 'edge': i, 'coordinates': [list(a), list(b)]})
        if jumps:
            found.append({'source_row': row['source_row'], 'jumps': jumps})
    return found


def lines(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == 'LineString':
        return [geom]
    if hasattr(geom, 'geoms'):
        return [part for child in geom.geoms for part in lines(child)]
    return []


def comparison_components(geom):
    """Preserve line/point core intersections, including quantized tiny tails."""
    if geom.is_empty:
        return []
    if geom.geom_type in ('Point', 'LineString'):
        return [geom]
    if hasattr(geom, 'geoms'):
        return [part for child in geom.geoms for part in comparison_components(child)]
    return []


def periodic_anchor(wkb):
    """Choose an unwrapped frame from the first vertex of a crossing source part."""
    for part in shapely.from_wkb(wkb).geoms:
        coords = list(part.coords)
        if any(abs(b[0] - a[0]) > 180 for a, b in zip(coords, coords[1:])):
            return TRANSFORM.transform(*coords[0])[0]
    return None


def comparison_geometry(components, anchor_x=None):
    """Translate whole components into the source's periodic comparison frame.

    Components are already clipped to tile cores. Translation changes neither
    their shape nor their vertices relative to each other; it only chooses the
    longitude copy. Independent central-world chord checks still use canonical
    geometry and do not call this function.
    """
    framed = []
    for part in components:
        if anchor_x is not None:
            center_x = (part.bounds[0] + part.bounds[2]) / 2
            part = affinity.translate(part, xoff=round((anchor_x - center_x) / WORLD) * WORLD)
        framed.append(part)
    return shapely.union_all(framed)


def wrapped_reference(wkb):
    """Unwrap each original part independently, then clip into canonical worlds.

    This is an independent geographic reference, not the builder's implementation.
    Adjacent >180 degree jumps take the shorter longitudinal arc; multipart
    boundaries remain independent. No arbitrary edge-length filter is applied.
    """
    result = []
    for part in shapely.from_wkb(wkb).geoms:
        xy = np.asarray(part.coords).copy()
        xy[:, 0] = np.rad2deg(np.unwrap(np.deg2rad(xy[:, 0])))
        projected = LineString(np.column_stack(TRANSFORM.transform(xy[:, 0], xy[:, 1])))
        low = math.floor((projected.bounds[0] + HALF) / WORLD)
        high = math.floor((projected.bounds[2] + HALF) / WORLD)
        for world in range(low, high + 1):
            cut = projected.intersection(shapely.box(-HALF + world * WORLD, -HALF,
                                                     HALF + world * WORLD, HALF))
            result.extend(lines(affinity.translate(cut, xoff=-world * WORLD)))
    return MultiLineString(result)


def tile_range(bounds, z):
    x0, y0, x1, y1 = bounds
    side = WORLD / (1 << z)
    clamp = lambda v: max(0, min((1 << z) - 1, math.floor(v)))
    return clamp((x0 + HALF) / side), clamp((HALF - y1) / side), clamp((x1 + HALF) / side), clamp((HALF - y0) / side)


def bbox_tiles(bounds, z):
    x0, y0, x1, y1 = tile_range(bounds, z)
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def reference_tiles(reference, z):
    return set().union(*(bbox_tiles(part.bounds, z) for part in reference.geoms))


def core(x, y, z):
    side = WORLD / (1 << z)
    return shapely.box(-HALF + x * side, HALF - (y + 1) * side,
                       -HALF + (x + 1) * side, HALF - y * side)


def decoded_geometry(feature, x, y, z, extent=4096):
    if extent != 4096:
        raise ValueError(f'unexpected tile extent {extent}')
    side = WORLD / (1 << z)
    return shapely.transform(shape(feature['geometry']), lambda xy: np.column_stack((
        -HALF + (x + xy[:, 0] / extent) * side,
        HALF - (y + xy[:, 1] / extent) * side)))


class Archive:
    def __init__(self, path):
        self.file = Path(path).open('rb')
        self.source = MmapSource(self.file)
        self.reader = Reader(self.source)
        self.cache = OrderedDict()
        self.reads = 0

    def tile(self, z, x, y):
        key = (z, x, y)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        raw = self.reader.get(z, x, y)
        self.reads += 1
        decoded = decode(raw) if raw else None
        self.cache[key] = decoded
        if len(self.cache) > 64:
            self.cache.popitem(last=False)
        return decoded

    def close(self):
        self.cache.clear()
        self.file.close()


def decode(raw):
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return mapbox_vector_tile.decode(raw, default_options={'y_coord_down': True})


def matching(archive, z, x, y, fid):
    tile = archive.tile(z, x, y)
    if not tile:
        return []
    layer = tile.get('grwl', {})
    return [decoded_geometry(f, x, y, z, layer.get('extent'))
            for f in layer.get('features', []) if f.get('id') == fid]


def check_wrap(archive, rows, ids):
    results = []
    by_id = {r['source_row']: r for r in rows}
    # Central-world area is intentionally far from either dateline. Buffers at
    # map edges do not count as chords; z0 must inspect geometry within the tile.
    central = shapely.box(-HALF / 2, -HALF, HALF / 2, HALF)
    for fid in ids:
        reference = wrapped_reference(by_id[fid]['geometry'])
        for z in range(11):
            n = 1 << z
            edge_tiles = reference_tiles(reference, z)
            ys = {y for _, y in edge_tiles}
            probes = edge_tiles | {(x, y) for x in {max(0, n // 2 - 1), n // 2} for y in ys}
            pieces = []
            edge_sides = set()
            edge_core_lengths = {'east': 0.0, 'west': 0.0}
            chord_tiles = []
            for x, y in sorted(probes):
                geometries = matching(archive, z, x, y, fid)
                for geom in geometries:
                    clipped = geom.intersection(core(x, y, z))
                    if clipped.is_empty:
                        continue
                    pieces.extend(lines(clipped))
                    if clipped.intersection(central).length > 1:
                        chord_tiles.append([z, x, y])
                    west_core = clipped.intersection(shapely.box(-HALF, -HALF, -HALF + WORLD / 128, HALF))
                    east_core = clipped.intersection(shapely.box(HALF - WORLD / 128, -HALF, HALF, HALF))
                    if not west_core.is_empty:
                        edge_sides.add('west')
                        edge_core_lengths['west'] += west_core.length
                    if not east_core.is_empty:
                        edge_sides.add('east')
                        edge_core_lengths['east'] += east_core.length
            results.append({'source_row': fid, 'zoom': z, 'tiles_probed': len(probes),
                            'present_sides': sorted(edge_sides), 'central_chord_tiles': chord_tiles,
                            'edge_core_length_metres': edge_core_lengths,
                            'passed': not chord_tiles and edge_sides == {'east', 'west'}})
    return results


def source_bbox(row):
    b = row['bbox']
    return b['xmin'], b['ymin'], b['xmax'], b['ymax']


def bbox_mercator(row):
    a, b, c, d = source_bbox(row)
    x0, y0 = TRANSFORM.transform(a, b)
    x1, y1 = TRANSFORM.transform(c, d)
    return x0, y0, x1, y1


def choose_samples(rows):
    groups = {}
    for name, window in REGIONS.items():
        a, b, c, d = window
        eligible = []
        for row in rows:
            x0, y0, x1, y1 = source_bbox(row)
            if x1 < a or x0 > c or y1 < b or y0 > d:
                continue
            tx0, ty0, tx1, ty1 = tile_range(bbox_mercator(row), ZOOM)
            if (tx1 - tx0 + 1) * (ty1 - ty0 + 1) <= 64:
                eligible.append(row['source_row'])
        groups[name] = sorted(eligible)[:32 if name == 'global' else 8]
    chosen = set().union(*map(set, groups.values()), {13164, 28938})
    return chosen, groups


def check_geometry(archive, rows):
    selected, groups = choose_samples(rows)
    out = []
    for row in rows:
        fid = row['source_row']
        if fid not in selected:
            continue
        reference = wrapped_reference(row['geometry'])
        tiles = reference_tiles(reference, ZOOM) if fid == 28938 else bbox_tiles(bbox_mercator(row), ZOOM)
        got = []
        expected = []
        for x, y in sorted(tiles):
            tile_core = core(x, y, ZOOM)
            expected.extend(comparison_components(reference.intersection(tile_core)))
            for geom in matching(archive, ZOOM, x, y, fid):
                got.extend(comparison_components(geom.intersection(tile_core)))
        anchor = periodic_anchor(row['geometry'])
        expected_geom = comparison_geometry(expected, anchor)
        actual_geom = comparison_geometry(got, anchor)
        distance = float(shapely.hausdorff_distance(expected_geom, actual_geom, densify=0.25)) if got and expected else None
        out.append({'source_row': fid, 'tile_count': len(tiles), 'hausdorff_metres': distance,
                    'periodic_anchor_x_metres': anchor,
                    'source_point_intersections': sum(p.geom_type == 'Point' for p in expected),
                    'display_point_intersections': sum(p.geom_type == 'Point' for p in got),
                    'passed': distance is not None and distance <= TOLERANCE})
    return {'zoom': ZOOM, 'tolerance_metres': TOLERANCE, 'ordinary_bbox_tile_cap': 64,
            'dateline_metric': 'source-anchored periodic frame; whole-component world translation after tile-core clipping; Point intersections retained',
            'groups': groups, 'mandatory_ids': [13164, 28938], 'samples': out,
            'passed': all(r['passed'] for r in out) and len(out) == len(selected)}


def check_upstream_edge(archive, row):
    part = list(shapely.from_wkb(row['geometry']).geoms[0].coords)
    projected = LineString([TRANSFORM.transform(*part[117]), TRANSFORM.transform(*part[118])])
    observed = []
    for x, y in bbox_tiles(projected.bounds, ZOOM):
        for geom in matching(archive, ZOOM, x, y, 13164):
            observed.extend(lines(geom.intersection(core(x, y, ZOOM))))
    union = shapely.union_all(observed)
    # Directed reference coverage: this archive feature also contains its whole
    # river, so symmetric distance to this one edge would be inappropriate.
    samples = [projected.interpolate(i / 100, normalized=True) for i in range(101)]
    max_distance = max((point.distance(union) for point in samples), default=math.inf)
    return {'source_row': 13164, 'source_part': 0, 'source_edge': 117,
            'max_reference_edge_distance_metres': max_distance,
            'passed': not union.is_empty and max_distance <= TOLERANCE}


def expected_properties(row, numeric_fields):
    props = {name: float(row[name]) for name in numeric_fields if row[name] is not None}
    props.update({'_src_' + name: value for name, value in row['bbox'].items()})
    return props


def check_accounting(archive, rows):
    numeric_fields = [k for k in rows[0] if k not in {'source_row', 'bbox', 'geometry'}]
    expected = {row['source_row']: expected_properties(row, numeric_fields) for row in rows}
    seen = set()
    failures = []
    errors = tiles = features = attributes = 0
    for (z, x, y), raw in all_tiles(archive.source):
        if z != ZOOM:
            continue
        tiles += 1
        tile = decode(raw)
        if set(tile) != {'grwl'} or tile['grwl']['extent'] != 4096:
            raise ValueError(f'unexpected layer/extent at {z}/{x}/{y}')
        for feature in tile['grwl']['features']:
            features += 1
            fid = feature.get('id')
            actual = dict(feature.get('properties', {}))
            duplicate_id = actual.pop('source_row', fid)
            want = expected.get(fid)
            if want is None or duplicate_id != fid or isinstance(fid, bool):
                problem = f'invalid native source_row ID {fid!r} at {z}/{x}/{y}'
            elif actual != want:
                problem = f'attribute mismatch for {fid} at {z}/{x}/{y}: ' + repr({k: [want.get(k), actual.get(k)] for k in set(want) | set(actual) if want.get(k) != actual.get(k)})
            else:
                problem = None
                attributes += len(want)
                seen.add(fid)
            if problem:
                errors += 1
                if len(failures) < 30:
                    failures.append(problem)
        if tiles % 20000 == 0:
            print(f'GRWL z10 accounting: {tiles} tiles, {len(seen)} IDs', file=sys.stderr, flush=True)
    missing = sorted(set(expected) - seen)
    return {'zoom': ZOOM, 'tiles_decoded': tiles, 'feature_occurrences_checked': features,
            'numeric_fields': numeric_fields, 'source_bbox_fields': ['_src_' + k for k in rows[0]['bbox']],
            'attributes_checked': attributes, 'maxzoom_ids_accounted': len(seen),
            'missing_ids': missing, 'attribute_failure_count': errors, 'failures': failures,
            'passed': not missing and not errors and len(seen) == 42077 and len(numeric_fields) == 10}


def validate(source, archive_path, crossing_path, wrap_only=False):
    source = Path(source)
    rows = pq.read_table(source).to_pylist()
    frozen = json.loads(Path(crossing_path).read_text())
    records = crossing_records(rows)
    ids = [r['source_row'] for r in records]
    source_hash = sha256(source)
    failures = []
    if source_hash != SOURCE_SHA or frozen['source_parquet_sha256'] != source_hash:
        failures.append('source Parquet pin mismatch')
    if records != frozen['records'] or ids != frozen['crossing_source_ids']:
        failures.append('crossing source set differs from pre-candidate freeze')
    archive = Archive(archive_path)
    try:
        header = archive.reader.header()
        if header['min_zoom'] != 0 or header['max_zoom'] != 10:
            failures.append('archive zoom range differs from 0..10')
        wrap = check_wrap(archive, rows, ids)
        if not all(r['passed'] for r in wrap):
            failures.append('antimeridian world chord or missing edge feature')
        edge = check_upstream_edge(archive, next(r for r in rows if r['source_row'] == 13164))
        if not edge['passed']:
            failures.append('upstream feature13164 edge is missing or displaced')
        accounting = geometry = None
        if not wrap_only:
            accounting = check_accounting(archive, rows)
            geometry = check_geometry(archive, rows)
            if not accounting['passed']:
                failures.append('complete z10 ID/attribute accounting failed')
            if not geometry['passed']:
                failures.append('independent sampled source geometry failed')
        return {'schema_version': 1, 'passed': not failures, 'failures': failures,
                'mode': 'wrap-regression-only' if wrap_only else 'full',
                'source_path': 'grwl/grwl-summary-v0102.parquet', 'source_filename': source.name,
                'source_sha256': source_hash,
                'pmtiles_path': 'assets/grwl.pmtiles', 'pmtiles_filename': Path(archive_path).name,
                'pmtiles_sha256': sha256(archive_path),
                'validator_sha256': sha256(__file__), 'crossing_freeze_sha256': sha256(crossing_path),
                'source_rows': len(rows), 'crossing_source_ids': ids, 'crossing_zoom_checks': wrap,
                'upstream_edge_control': edge, 'accounting': accounting,
                'maxzoom_ids_accounted': accounting['maxzoom_ids_accounted'] if accounting else None,
                'geometry': geometry, 'bounded_tile_reads': archive.reads}
    finally:
        archive.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--crossing-ids', type=Path, default=ROOT / 'research/grwl-straight-segments-20261102/crossing-source-ids.json')
    parser.add_argument('--wrap-only', action='store_true')
    args = parser.parse_args()
    if args.report.exists():
        parser.error('report exists; evidence reports are write-once')
    report = validate(args.source, args.archive, args.crossing_ids, args.wrap_only)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'passed': report['passed'], 'failures': report['failures'], 'report': str(args.report)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
