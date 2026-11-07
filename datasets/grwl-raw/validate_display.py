#!/usr/bin/env python3
"""Independent, bounded-memory GRWL raw PMTiles fidelity oracle.

All z12 feature occurrences are checked.  Source rows are represented by one
bit each; only eight Parquet row groups of selected attributes are cached.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import OrderedDict, Counter
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np
import pyarrow.parquet as pq
import shapely
from pmtiles.reader import Reader, MmapSource, all_tiles
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[2]
CONTROL_POLICY_PATH = ROOT/'research/grwl-raw-release-20261102/global-display-diagnostics-r1/control-policy-r2.json'
_quantizer_spec = importlib.util.spec_from_file_location('grwl_raw_native_quantization', Path(__file__).with_name('native_quantization.py'))
native_quantizer = importlib.util.module_from_spec(_quantizer_spec)
_quantizer_spec.loader.exec_module(native_quantizer)
LAYER = 'grwl_raw'
BBOX = ('xmin', 'ymin', 'xmax', 'ymax')
MAX_ERRORS = 40
PILOT_TILES = ['NI15', 'NI16', 'NJ12', 'NK12', 'NL10', 'NL11', 'NL12', 'NL13', 'NM11']


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tile_code(tile):
    if len(tile) != 4 or not tile[:2].isupper() or not tile[:2].isalpha() or not tile[2:].isdigit():
        raise ValueError(f'invalid source tile {tile!r}')
    return ((ord(tile[0])-65)*26 + ord(tile[1])-65)*100 + int(tile[2:])


def varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError('truncated MVT varint')
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, pos
    raise ValueError('overlong MVT varint')


def wire(data):
    pos = 0
    while pos < len(data):
        key, pos = varint(data, pos)
        field, kind = key >> 3, key & 7
        if kind == 0:
            value, pos = varint(data, pos)
        elif kind == 1:
            value = data[pos:pos+8]
            pos += 8
        elif kind == 2:
            length, pos = varint(data, pos)
            value = data[pos:pos+length]
            pos += length
        elif kind == 5:
            value = data[pos:pos+4]
            pos += 4
        else:
            raise ValueError(f'unsupported MVT wire type {kind}')
        if pos > len(data):
            raise ValueError('truncated MVT field')
        yield field, kind, value


def mvt_value(data):
    for field, kind, value in wire(data):
        if field == 1 and kind == 2:
            return value.decode()
        if field == 2 and kind == 5:
            return struct.unpack('<f', value)[0]
        if field == 3 and kind == 1:
            return struct.unpack('<d', value)[0]
        if field in (4, 5) and kind == 0:
            return value
        if field == 6 and kind == 0:
            return (value >> 1) ^ -(value & 1)
        if field == 7 and kind == 0:
            return bool(value)
    raise ValueError('empty or invalid MVT value')


def decode_features(raw):
    """Yield native ID and selected properties without constructing geometries."""
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    layer_count = 0
    for field, kind, layer in wire(raw):
        if (field, kind) != (3, 2):
            continue
        name, extent = None, None
        features, keys, values = [], [], []
        for lf, lk, value in wire(layer):
            if (lf, lk) == (1, 2):
                name = value.decode()
            elif (lf, lk) == (2, 2):
                features.append(value)
            elif (lf, lk) == (3, 2):
                keys.append(value.decode())
            elif (lf, lk) == (4, 2):
                values.append(mvt_value(value))
            elif (lf, lk) == (5, 0):
                extent = value
        if name != LAYER:
            raise ValueError(f'unexpected MVT layer {name!r}')
        layer_count += 1
        if extent != 4096:
            raise ValueError(f'unexpected MVT extent {extent}')
        for feature in features:
            fid, tags = None, []
            for ff, fk, fv in wire(feature):
                if (ff, fk) == (1, 0):
                    fid = fv
                elif (ff, fk) == (2, 2):
                    pos = 0
                    while pos < len(fv):
                        tag, pos = varint(fv, pos)
                        tags.append(tag)
            if fid is None or len(tags) % 2:
                raise ValueError('missing native ID or malformed MVT tags')
            try:
                props = {keys[tags[i]]: values[tags[i+1]] for i in range(0, len(tags), 2)}
            except IndexError as exc:
                raise ValueError('invalid MVT tag index') from exc
            yield fid, props
    if layer_count != 1:
        raise ValueError(f'expected one {LAYER} layer, found {layer_count}')


class SourceIndex:
    def __init__(self, parquet, manifest):
        self.pf = pq.ParquetFile(parquet)
        self.tiles = manifest['tiles']
        self.codes = {tile_code(t['tile']): i for i, t in enumerate(self.tiles)}
        if len(self.codes) != len(self.tiles):
            raise ValueError('duplicate source tile codes')
        self.bits = [bytearray((t['records'] + 7)//8) for t in self.tiles]
        self.cache = OrderedDict()
        self.starts = []
        self.groups = []
        tile_ends = []
        total = 0
        for tile in self.tiles:
            total += tile['records']
            tile_ends.append(total)
        cursor, tile_index = 0, 0
        for group_index in range(self.pf.num_row_groups):
            group = self.pf.metadata.row_group(group_index)
            while tile_index < len(self.tiles) and cursor == tile_ends[tile_index]:
                tile_index += 1
            if tile_index == len(self.tiles):
                raise ValueError('Parquet has extra row groups')
            end = cursor + group.num_rows
            tile_end = tile_ends[tile_index]
            if end > tile_end:
                raise ValueError('Parquet row group mixes source tiles')
            self.starts.append(cursor)
            self.groups.append((end, tile_index))
            cursor = end
        if cursor != manifest['rows'] or cursor != self.pf.metadata.num_rows:
            raise ValueError('Parquet/manifest row count mismatch')
        self.tile_starts = []
        cursor = 0
        for tile in self.tiles:
            self.tile_starts.append(cursor)
            cursor += tile['records']
        # Metadata statistics prove the assumed contiguous tile and row layout.
        names = self.pf.schema_arrow.names
        for gi, (start, (end, ti)) in enumerate(zip(self.starts, self.groups)):
            group = self.pf.metadata.row_group(gi)
            for name, expected in (('source_tile', self.tiles[ti]['tile']),
                                   ('source_row', start-self.tile_starts[ti]+1)):
                stats = group.column(names.index(name)).statistics
                if stats is None or not stats.has_min_max or stats.min != expected:
                    raise ValueError(f'row group {gi} lacks expected {name} minimum')
            row_stats = group.column(names.index('source_row')).statistics
            if row_stats.max != end-self.tile_starts[ti]:
                raise ValueError(f'row group {gi} source_row maximum mismatch')
            tile_stats = group.column(names.index('source_tile')).statistics
            if tile_stats.max != self.tiles[ti]['tile']:
                raise ValueError(f'row group {gi} source_tile maximum mismatch')

    def locate(self, fid):
        ti = self.codes.get(fid >> 32)
        row = fid & 0xffffffff
        if ti is None or not 1 <= row <= self.tiles[ti]['records']:
            return None
        absolute = self.tile_starts[ti] + row-1
        group = bisect_right(self.starts, absolute)-1
        if group < 0 or absolute >= self.groups[group][0] or self.groups[group][1] != ti:
            raise ValueError('source row group mapping failed')
        return ti, row-1, group, absolute-self.starts[group]

    def attrs(self, group):
        if group in self.cache:
            self.cache.move_to_end(group)
            return self.cache[group]
        names = ['source_row', 'feature_id', 'width_m', 'width_valid', 'bbox']
        table = self.pf.read_row_group(group, columns=names, use_threads=False)
        result = {name: table[name].to_pylist() for name in names}
        self.cache[group] = result
        if len(self.cache) > 8:
            self.cache.popitem(last=False)
        return result

    def mark(self, ti, row0):
        byte, mask = row0 >> 3, 1 << (row0 & 7)
        was_seen = bool(self.bits[ti][byte] & mask)
        self.bits[ti][byte] |= mask
        return not was_seen

    def missing(self):
        for ti, tile in enumerate(self.tiles):
            for row0 in range(tile['records']):
                if not self.bits[ti][row0 >> 3] & (1 << (row0 & 7)):
                    yield (tile_code(tile['tile']) << 32) | (row0+1), ti, row0

    def dateline_candidates(self, seam_margin_degrees=None):
        """Find crossing records and optional source-selected seam strips."""
        for gi, (start, (_, ti)) in enumerate(zip(self.starts, self.groups)):
            group = self.pf.metadata.row_group(gi)
            xmin, xmax = None, None
            for ci in range(group.num_columns):
                path = group.column(ci).path_in_schema
                if path == 'bbox.xmin':
                    xmin = group.column(ci).statistics
                elif path == 'bbox.xmax':
                    xmax = group.column(ci).statistics
            if (xmin is not None and xmax is not None and xmin.has_min_max and xmax.has_min_max
                    and xmax.max - xmin.min <= 180
                    and (seam_margin_degrees is None or
                         (xmin.min > -180 + seam_margin_degrees and xmax.max < 180 - seam_margin_degrees))):
                continue
            boxes = self.pf.read_row_group(gi, columns=['bbox'], use_threads=False)['bbox'].to_pylist()
            first_row = start - self.tile_starts[ti] + 1
            code = tile_code(self.tiles[ti]['tile'])
            for offset, box in enumerate(boxes):
                if (box['xmax'] - box['xmin'] > 180 or
                        (seam_margin_degrees is not None and
                         (box['xmin'] <= -180 + seam_margin_degrees or box['xmax'] >= 180 - seam_margin_degrees))):
                    yield (code << 32) | (first_row + offset)


def expected_properties(attrs, offset):
    box = attrs['bbox'][offset]
    props = {'width_valid': attrs['width_valid'][offset]}
    if attrs['width_m'][offset] is not None:
        props['width_m'] = attrs['width_m'][offset]
    props.update({'_src_'+k: box[k] for k in BBOX})
    return props


def classify_geometry(wkb, wrap):
    geom = shapely.from_wkb(wkb)
    if geom.is_empty:
        return 'source_empty'
    if geom.length == 0:
        return 'zero_length'
    for part in geom.geoms:
        xy = np.asarray(part.coords)
        if len(xy) < 2:
            continue
        # Missing crossing parts require their own split/interpolation proof;
        # never use a length threshold to excuse an unexplained native loss.
        if np.any(np.abs(np.diff(xy[:, 0])) > 180):
            return 'unexpected_loss'
        grid = native_quantizer.quantized_world_grid(xy)
        if np.any(grid[1:] != grid[:-1]):
            return 'unexpected_loss'
    return 'quantization_collapse'


def missing_evidence(wkb, wrap):
    """Describe source bytes, the old diagnostic grid and exact native no-op grid."""
    geom = shapely.from_wkb(wkb)
    geod = Geod(ellps='WGS84')
    scale = (1 << 12) * 4096
    parts = []
    length = 0.0
    for part in geom.geoms:
        xy = np.asarray(part.coords)
        length += abs(geod.line_length(xy[:, 0], xy[:, 1]))
        px, py = wrap.TRANSFORM.transform(xy[:, 0], xy[:, 1])
        grid = np.column_stack(((np.asarray(px)+wrap.HALF)/wrap.WORLD*scale,
                                (wrap.HALF-np.asarray(py))/wrap.WORLD*scale))
        if len(xy) <= 32:
            parts.append({'original_xy': xy.tolist(), 'global_grid_xy': grid.tolist(),
                          'nearest_grid_xy_diagnostic': np.rint(grid).astype(np.int64).tolist(),
                          'zoom32_world_xy': native_quantizer.project_epsg4326_zoom32(xy).tolist(),
                          'rounded_grid_xy': native_quantizer.quantized_world_grid(xy).tolist(),
                          'vertex_count': len(xy), 'coordinates_truncated': False})
        else:
            parts.append({'vertex_count': len(xy), 'coordinates_truncated': True,
                          'first_original_xy': xy[0].tolist(), 'last_original_xy': xy[-1].tolist()})
    return {'source_geometry_sha256': hashlib.sha256(wkb).hexdigest(),
            'source_geometry_bytes': len(wkb), 'source_geodesic_length_m': length,
            'global_grid': 'Tippecanoe 2.79.0 EPSG:4326 zoom32 projection then world-coordinate z12/detail12 no-op std::round, half ties away from zero',
            'parts': parts}


def load_wrap():
    spec = importlib.util.spec_from_file_location('grwl_raw_independent_wrap', ROOT / 'datasets/grwl/validate_display_wrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_frozen_samples(manifest, fidelity, source):
    """Check frozen sample policy, counts, first IDs, and source membership before MVT scanning.

    The source-fidelity report selects longest parts from the original source before display
    processing. This check independently verifies their IDs, part membership and recorded length
    against Parquet, but does not recompute the global longest-part ranking.
    """
    tile_names = [item['tile'] for item in manifest['tiles']]
    pilot = tile_names == PILOT_TILES
    expected_policy = {
        'kind': 'frozen_pilot' if pilot else 'global_controls',
        'first_records_per_tile': 32 if pilot else 8,
        'longest_parts_per_tile': 32 if pilot else 8,
    }
    if fidelity.get('sample_policy') != expected_policy:
        raise ValueError(f'frozen sample policy differs from the required rule: expected {expected_policy!r}')
    if len(fidelity.get('tiles', [])) != len(manifest['tiles']):
        raise ValueError('frozen sample tile inventory count differs from source manifest')

    selected = set()
    longest_by_id = {}
    checks = []
    geod = Geod(ellps='WGS84')
    codes = {tile_code(t['tile']): i for i, t in enumerate(source.tiles)}
    for ti, (tile, evidence) in enumerate(zip(manifest['tiles'], fidelity['tiles'])):
        tile_name = tile['tile']
        if evidence.get('tile') != tile_name:
            raise ValueError(f'frozen sample tile order differs at {tile_name}')
        row_count = tile.get('records')
        manifest_parts = tile.get('parts')
        source_rows = evidence.get('source_rows')
        parts_count = evidence.get('parts')
        if not isinstance(row_count, int) or row_count < 0 or source_rows != row_count:
            raise ValueError(f'frozen sample source-row count differs from manifest for {tile_name}')
        if not isinstance(manifest_parts, int) or manifest_parts < 0 or parts_count != manifest_parts:
            raise ValueError(f'frozen sample part count differs from manifest for {tile_name}')
        if (row_count and manifest_parts < row_count) or (not row_count and manifest_parts != 0):
            raise ValueError(f'manifest part count is inconsistent with source rows for {tile_name}')
        first_limit = expected_policy['first_records_per_tile']
        part_limit = expected_policy['longest_parts_per_tile']
        first = evidence.get('first_records')
        longest = evidence.get('longest_parts')
        expected_first = min(first_limit, row_count)
        expected_longest = min(part_limit, parts_count)
        if not isinstance(first, list) or len(first) != expected_first:
            raise ValueError(f'frozen first-record sample count differs for {tile_name}: expected {expected_first}')
        if not isinstance(longest, list) or len(longest) != expected_longest:
            raise ValueError(f'frozen longest-part sample count differs for {tile_name}: expected {expected_longest}')

        code = tile_code(tile_name)
        if codes.get(code) != ti:
            raise ValueError(f'frozen sample tile is not bound to the source Parquet tile index: {tile_name}')

        def check_identity(item, expected_row=None):
            if not isinstance(item, dict) or item.get('source_tile') != tile_name:
                raise ValueError(f'frozen sample has wrong source tile membership for {tile_name}')
            row = item.get('source_row')
            fid = item.get('feature_id')
            if not isinstance(row, int) or not 1 <= row <= row_count:
                raise ValueError(f'frozen sample has invalid source row for {tile_name}')
            if expected_row is not None and row != expected_row:
                raise ValueError(f'frozen first-record IDs are not the original ordered prefix for {tile_name}')
            expected_id = (code << 32) | row
            if fid != expected_id:
                raise ValueError(f'frozen sample feature ID does not encode {tile_name} source row {row}')
            location = source.locate(fid)
            if location is None or location[0] != ti or location[1] != row - 1:
                raise ValueError(f'frozen sample source ID is absent or belongs to another tile: {fid}')
            attrs = source.attrs(location[2])
            offset = location[3]
            if attrs['source_row'][offset] != row or attrs['feature_id'][offset] != fid:
                raise ValueError(f'frozen sample identity differs from Parquet for {fid}')
            selected.add(fid)
            return fid, location

        for expected_row, item in enumerate(first, 1):
            check_identity(item, expected_row)

        tile_longest_seen = set()
        longest_order_keys = []
        for item in longest:
            fid, location = check_identity(item)
            part = item.get('part')
            length = item.get('length_m')
            if not isinstance(part, int) or part < 1 or not isinstance(length, (int, float)) or not math.isfinite(length) or length < 0:
                raise ValueError(f'frozen longest-part sample has invalid part or length for {fid}')
            key = (fid, part)
            if key in tile_longest_seen:
                raise ValueError(f'duplicate frozen longest-part sample {key}')
            tile_longest_seen.add(key)
            longest_order_keys.append((float(length), -item['source_row'], -part))
            longest_by_id.setdefault(fid, []).append((part, float(length), location[2], location[3]))
        if longest_order_keys != sorted(longest_order_keys, reverse=True):
            raise ValueError(f'frozen longest-part sample order differs from descending length and deterministic tie order for {tile_name}')

        checks.append({'tile': tile_name, 'expected_first_records': expected_first,
                       'validated_first_records': len(first), 'expected_longest_parts': expected_longest,
                       'validated_longest_parts': len(longest)})

    if not selected:
        raise ValueError('no frozen geometry samples are available; empty samples cannot establish display fidelity')

    by_group = {}
    for fid, samples in longest_by_id.items():
        group, offset = samples[0][2], samples[0][3]
        by_group.setdefault(group, []).append((fid, offset, samples))
    for group, requested in by_group.items():
        geometries = source.pf.read_row_group(group, columns=['geometry'], use_threads=False)['geometry'].to_pylist()
        for fid, offset, samples in requested:
            try:
                geometry = shapely.from_wkb(geometries[offset])
                if geometry.geom_type != 'MultiLineString':
                    raise ValueError('not a MultiLineString')
                for part, recorded_length, _, _ in samples:
                    if part > len(geometry.geoms):
                        raise ValueError(f'part {part} exceeds {len(geometry.geoms)} source parts')
                    coords = np.asarray(geometry.geoms[part-1].coords)
                    actual_length = float(geod.line_length(coords[:, 0], coords[:, 1]))
                    if not math.isclose(actual_length, recorded_length, rel_tol=1e-10, abs_tol=1e-6):
                        raise ValueError(f'part {part} length differs from source Parquet')
            except Exception as exc:
                raise ValueError(f'frozen longest-part sample is not a valid source part for {fid}: {exc}') from exc
    return expected_policy, checks, selected


def source_frame_anchor(wkb, wrap, reference=None):
    """Compare compact raw observations in the first source vertex's world copy.

    Tile buffers can contribute an opposite-seam core Point even when the source
    does not cross the seam. Preserve every core component, translating only by
    whole world widths. Refuse an ambiguous extensive reference instead of
    claiming this compact-observation metric supports arbitrary global features.
    """
    geometry = shapely.from_wkb(wkb)
    first = next((part.coords[0] for part in geometry.geoms if len(part.coords)), None)
    if first is None:
        raise ValueError('source geometry has no vertex for a periodic comparison frame')
    anchor = wrap.TRANSFORM.transform(*first)[0]
    reference = wrap.wrapped_reference(wkb) if reference is None else reference
    framed = wrap.comparison_geometry(wrap.comparison_components(reference), anchor)
    if not framed.is_empty and framed.bounds[2] - framed.bounds[0] >= wrap.WORLD / 2:
        raise ValueError('source reference spans half a world or more; compact periodic frame is ambiguous')
    return anchor


def sample_geometry(archive, source, ids, occurrence_tiles, missing_causes, wrap, tolerance):
    rows = {}
    by_group = {}
    for fid in ids:
        location = source.locate(fid)
        if location is None:
            raise ValueError(f'frozen sample source ID absent: {fid}')
        by_group.setdefault(location[2], []).append((fid, location[3]))
    for group, wanted in by_group.items():
        wkbs = source.pf.read_row_group(group, columns=['geometry'], use_threads=False)['geometry'].to_pylist()
        rows.update({fid: wkbs[offset] for fid, offset in wanted})
    results = []
    for fid in sorted(ids):
        wkb = rows[fid]
        reference = wrap.wrapped_reference(wkb)
        tiles = wrap.reference_tiles(reference, 12) | occurrence_tiles[fid]
        if not tiles:
            results.append({'id': fid, 'passed': False, 'reason': 'empty reference'})
            continue
        expected, observed = [], []
        for x, y in sorted(tiles):
            tile_core = wrap.core(x, y, 12)
            expected.extend(wrap.comparison_components(reference.intersection(tile_core)))
            decoded = archive.tile(12, x, y)
            if decoded:
                layer = decoded.get(LAYER)
                if layer is None or layer.get('extent') != 4096:
                    raise ValueError(f'unexpected sample tile layer or extent at 12/{x}/{y}')
                for feature in layer['features']:
                    if feature.get('id') == fid:
                        geom = wrap.decoded_geometry(feature, x, y, 12, 4096)
                        observed.extend(wrap.comparison_components(geom.intersection(tile_core)))
        anchor = source_frame_anchor(wkb, wrap, reference)
        expected_geom = wrap.comparison_geometry(expected, anchor)
        observed_geom = wrap.comparison_geometry(observed, anchor)
        distance = (float(shapely.hausdorff_distance(expected_geom, observed_geom, densify=.25))
                    if expected and observed else None)
        exception = missing_causes.get(fid) if distance is None and not observed else None
        results.append({'id': fid, 'tiles': len(tiles), 'hausdorff_metres': distance,
                        'passed': distance is not None and distance <= tolerance,
                        'missing_geometry_exception': exception})
    return results


def validate(parquet, source_manifest, fidelity_path, pmtiles, report, scratch=None):
    parquet, source_manifest, fidelity_path, pmtiles, report = map(Path, (parquet, source_manifest, fidelity_path, pmtiles, report))
    missing_path = report.with_name(report.stem + ".maxzoom-missing.jsonl")
    if report.exists() or missing_path.exists():
        raise FileExistsError("Refusing to overwrite a display validation report or missing-ID evidence")
    report.parent.mkdir(parents=True, exist_ok=True)
    manifest, fidelity = json.loads(source_manifest.read_text()), json.loads(fidelity_path.read_text())
    policy = json.loads((ROOT/'research/grwl-raw-release-20261102/display-policy.json').read_text())
    criteria = json.loads((ROOT/'research/grwl-raw-release-20261102/criteria.json').read_text())
    control_policy = json.loads(CONTROL_POLICY_PATH.read_text())
    wrap = load_wrap()
    seam_metres = control_policy['dateline_supplement']['seam_margin_mercator_metres']
    if seam_metres != criteria['validation']['display_geometry_maximum_mercator_metres']:
        raise ValueError('supplemental seam margin differs from the frozen 30 m tolerance')
    errors = []
    def fail(message):
        if len(errors) < MAX_ERRORS:
            errors.append(message)
    source_hash = sha256(parquet)
    if source_hash != manifest['parquet_sha256']:
        fail('source Parquet SHA differs from immutable manifest')
    if (fidelity['status'] != 'passed' or fidelity['manifest_sha256'] != sha256(source_manifest)
            or fidelity.get('parquet_sha256') != source_hash):
        fail('source fidelity status, manifest binding, or Parquet SHA binding failed')
    if fidelity['progress']['source_rows'] != manifest['rows']:
        fail('source fidelity row count mismatch')
    if sum(tile.get('parts', 0) for tile in fidelity['tiles']) != fidelity['progress'].get('parts'):
        fail('source fidelity part counts do not sum to progress metadata')
    if [t['tile'] for t in fidelity['tiles']] != [t['tile'] for t in manifest['tiles']]:
        fail('fidelity and manifest tile inventory mismatch')
    if errors:
        raise ValueError('; '.join(errors))
    if manifest.get('rows') == 0:
        raise ValueError('no frozen geometry samples are available; empty samples cannot establish display fidelity')
    source = SourceIndex(parquet, manifest)
    sample_policy_checked, sample_counts_checked, selected = validate_frozen_samples(manifest, fidelity, source)
    crossing_candidates = set(source.dateline_candidates())
    seam_margin = seam_metres / wrap.HALF * 180
    dateline_candidates = set(source.dateline_candidates(seam_margin))
    seam_candidates = dateline_candidates - crossing_candidates
    selected |= dateline_candidates
    occurrence_tiles = {fid: set() for fid in selected}
    missing_path = report.with_name(report.stem + '.maxzoom-missing.jsonl')
    archive_hash = sha256(pmtiles)
    tiles = occurrences = unique = attributes = 0
    with pmtiles.open('rb') as stream:
        mmap = MmapSource(stream)
        reader = Reader(mmap)
        header = reader.header()
        if header['min_zoom'] != policy['min_zoom'] or header['max_zoom'] != policy['max_zoom']:
            fail('PMTiles zoom range differs from frozen policy')
        for (z, x, y), raw in all_tiles(mmap):
            if z != policy['max_zoom']:
                continue
            tiles += 1
            try:
                features = decode_features(raw)
                for fid, props in features:
                    occurrences += 1
                    location = source.locate(fid)
                    if location is None:
                        fail(f'unknown native ID {fid} at {z}/{x}/{y}')
                        continue
                    if fid in occurrence_tiles:
                        occurrence_tiles[fid].add((x, y))
                    ti, row0, group, offset = location
                    attrs = source.attrs(group)
                    if attrs['source_row'][offset] != row0+1 or attrs['feature_id'][offset] != fid:
                        fail(f'source row/ID mismatch for {fid}')
                        continue
                    want = expected_properties(attrs, offset)
                    if props != want or props.get('width_valid') is not want['width_valid']:
                        fail(f'attribute mismatch for {fid} at {z}/{x}/{y}: {props!r} vs {want!r}')
                    else:
                        attributes += 1
                    if source.mark(ti, row0):
                        unique += 1
            except (ValueError, KeyError, TypeError) as exc:
                fail(f'MVT decode failed at {z}/{x}/{y}: {exc}')
            if tiles % 20000 == 0:
                print(f'GRWL raw z12: {tiles} tiles, {occurrences} occurrences', file=sys.stderr, flush=True)
        missing_counts = Counter()
        sampled_missing = {}
        missing_count = 0
        with missing_path.open('x') as out:
            last_group, wkbs = None, None
            for fid, ti, row0 in source.missing():
                missing_count += 1
                location = source.locate(fid)
                group, offset = location[2:]
                if group != last_group:
                    wkbs = source.pf.read_row_group(group, columns=['geometry'], use_threads=False)['geometry'].to_pylist()
                    last_group = group
                cause = classify_geometry(wkbs[offset], wrap)
                missing_counts[cause] += 1
                if fid in selected:
                    sampled_missing[fid] = cause
                detail = {'id': fid, 'cause': cause, 'source_tile': source.tiles[ti]['tile'],
                          'source_row': row0+1, **missing_evidence(wkbs[offset], wrap)}
                out.write(json.dumps(detail, separators=(',', ':'), allow_nan=False) + '\n')
            if missing_counts['unexpected_loss']:
                fail(f"{missing_counts['unexpected_loss']} unclassified source IDs absent at z12")
        archive = wrap.Archive(pmtiles)
        try:
            samples = sample_geometry(archive, source, selected, occurrence_tiles, sampled_missing, wrap,
                                      criteria['validation']['display_geometry_maximum_mercator_metres'])
        finally:
            archive.close()
        if any(not result['passed'] and result['missing_geometry_exception'] not in
               {'source_empty', 'zero_length', 'quantization_collapse'} for result in samples):
            fail('frozen sample geometry exceeds tolerance or is absent')
    if unique + missing_count != manifest['rows']:
        fail('source ID accounting does not sum to manifest rows')
    result = {'schema_version': 1, 'status': 'passed' if not errors else 'failed',
              'source_sha256': source_hash, 'source_manifest_sha256': sha256(source_manifest),
              'source_fidelity_sha256': sha256(fidelity_path), 'pmtiles_sha256': archive_hash,
              'source_rows': manifest['rows'], 'maxzoom': policy['max_zoom'], 'maxzoom_tiles': tiles,
              'maxzoom_feature_occurrences': occurrences, 'maxzoom_unique_ids': unique,
              'maxzoom_attribute_occurrences_checked': attributes, 'maxzoom_missing_ids': missing_count,
              'maxzoom_missing_classification': dict(missing_counts),
              'maxzoom_missing_path': missing_path.name, 'maxzoom_missing_sha256': sha256(missing_path),
              'dateline_bbox_candidate_ids': len(dateline_candidates),
              'dateline_bbox_candidate_feature_ids': sorted(dateline_candidates),
              'dateline_crossing_feature_ids': sorted(crossing_candidates),
              'dateline_seam_feature_ids': sorted(seam_candidates),
              'dateline_control_policy': control_policy['dateline_supplement'],
              'control_policy_sha256': sha256(CONTROL_POLICY_PATH),
              'native_quantizer_sha256': sha256(Path(native_quantizer.__file__)),
              'frozen_sample_policy': sample_policy_checked,
              'frozen_sample_counts': sample_counts_checked,
              'longest_part_rank_independently_recomputed': False,
              'longest_part_selection_note': 'First-record counts use manifest rows; longest-part counts use the bound source-fidelity part counts. Sample IDs, part membership, and recorded lengths were checked against source Parquet, but longest-part ranking is inherited from the bound source-fidelity report selected before display processing.',
              'frozen_geometry_samples': samples,
              'geometry_samples_passed': sum(item['passed'] for item in samples),
              'geometry_samples_missing_exceptions': sum(item['missing_geometry_exception'] is not None for item in samples),
              'errors': errors,
              'errors_truncated': len(errors) == MAX_ERRORS,
              'validator_sha256': sha256(Path(__file__)),
              'wrap_validator_sha256': sha256(Path(wrap.__file__)),
              'environment_lock_sha256': sha256(ROOT/'scripts/display_tools/uv.lock'),
              'scope': 'format and display fidelity; not independent scientific accuracy'}
    with report.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parquet', 'source-manifest', 'fidelity', 'pmtiles', 'report'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--scratch', type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.parquet, args.source_manifest, args.fidelity, args.pmtiles, args.report, args.scratch)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        result = {'schema_version': 1, 'status': 'failed', 'errors': [f'{type(exc).__name__}: {exc}']}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'report': str(args.report)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
