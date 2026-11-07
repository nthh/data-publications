#!/usr/bin/env python3
"""Combine selected-width overview tiles with byte-identical GRWL r2 detail tiles.

This creates an unvalidated local candidate only. It does not inspect source rows;
the frozen independent overview receipt and the later browser/package gates do that.
"""
from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

from pmtiles.reader import MmapSource, Reader, all_tiles
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Entry, Writer

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / 'research/grwl-width-overview-20261106/criteria.json'
GLOBAL_BASELINE_SHA256 = '79389270fef94a8a6359f0b7a98b3505a82ee090a7827bd13280bf1f1c178830'
GLOBAL_BASELINE_TILES = 588_355
GLOBAL_BASELINE_ARCHIVE_TILES = 592_774
GLOBAL_BASELINE_OLD_OVERVIEW_TILES = GLOBAL_BASELINE_ARCHIVE_TILES - GLOBAL_BASELINE_TILES
ARCHIVE_REL = Path('assets/grwl-raw.pmtiles')
OVERVIEW_LAYER = 'grwl_width_overview'
OLD_OVERVIEW_LAYER = 'grwl_overview'
DETAIL_LAYER = 'grwl_raw'


class CombineError(RuntimeError):
    pass


class ExactWriter(Writer):
    """Writer that never deduplicates on Python's hash-only tile index."""

    def __init__(self, stream, tile_data_path):
        super().__init__(stream)
        self.tile_f.close()
        self.tile_f = Path(tile_data_path).open('x+b')
        self._content_count = 0

    def write_tile(self, tileid, data):
        if self.tile_entries and tileid <= self.tile_entries[-1].tile_id:
            raise CombineError('input tiles are not strictly increasing by tile ID')
        self.tile_f.write(data)
        self.tile_entries.append(Entry(tileid, self.offset, len(data), 1))
        self.hash_to_offset[self._content_count] = self.offset
        self._content_count += 1
        self.offset += len(data)
        self.addressed_tiles += 1


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path):
    path = regular(path)
    return {'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise CombineError(f'Expected a regular non-symlink file: {path}')
    return path


def read_json(path, label):
    regular(path)
    try:
        result = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CombineError(f'Invalid {label}: {exc}') from exc
    if not isinstance(result, dict):
        raise CombineError(f'{label} must be a JSON object')
    return result


def require_sha(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise CombineError(f'{label} SHA-256 is malformed')
    return value


def tile_reader(path):
    stream = regular(path).open('rb')
    source = MmapSource(stream)
    return stream, source, Reader(source)


def vector_layer(metadata, layer_id):
    layers = metadata.get('vector_layers')
    if not isinstance(layers, list):
        raise CombineError('PMTiles metadata lacks vector_layers')
    matches = [layer for layer in layers if isinstance(layer, dict) and layer.get('id') == layer_id]
    if len(matches) != 1:
        raise CombineError(f'Expected exactly one {layer_id} vector layer')
    return matches[0]


def check_tile_stream(reader, min_zoom, max_zoom, label, resource_guard=None, by_zoom=None):
    count = 0
    previous = -1
    for (z, x, y), raw in all_tiles(reader.get_bytes):
        if not min_zoom <= z <= max_zoom:
            raise CombineError(f'{label} contains tile outside z{min_zoom}-{max_zoom}: z{z}/{x}/{y}')
        tile_id = zxy_to_tileid(z, x, y)
        if tile_id <= previous:
            raise CombineError(f'{label} tile directory is not strictly sorted')
        previous = tile_id
        if not isinstance(raw, bytes) or not raw:
            raise CombineError(f'{label} contains an empty tile payload')
        count += 1
        if by_zoom is not None:
            by_zoom[z] = by_zoom.get(z, 0) + 1
        if resource_guard and count % 1000 == 0:
            resource_guard()
    return count


def report_receipt(overview_path, receipt_path, criteria):
    receipt = read_json(receipt_path, 'overview receipt')
    if receipt.get('status') != 'passed':
        raise CombineError('Overview receipt status is not passed')
    if receipt.get('scope') not in ('global', 'pilot', 'heldout'):
        raise CombineError('Overview receipt scope is not global, pilot or heldout')
    require_sha(receipt.get('source_sha256'), 'Overview source')
    require_sha(receipt.get('source_manifest_sha256'), 'Overview source manifest')
    require_sha(receipt.get('archive_sha256'), 'Overview archive')
    require_sha(receipt.get('criteria_sha256'), 'Overview criteria')
    require_sha(receipt.get('verifier_sha256'), 'Overview verifier')
    if receipt.get('criteria_sha256') != sha256(CRITERIA):
        raise CombineError('Overview receipt criteria hash differs from frozen criteria')
    verifier_path = ROOT / 'datasets/grwl-raw/validate_width_overview.py'
    if receipt.get('verifier_sha256') != sha256(verifier_path):
        raise CombineError('Overview receipt verifier hash differs from current oracle code')
    if receipt.get('scope') == 'global' and receipt.get('source_sha256') != criteria['source']['sha256']:
        raise CombineError('Global overview receipt source differs from frozen source pin')
    if receipt.get('scope') == 'global' and receipt.get('source_records') != criteria['source']['rows']:
        raise CombineError('Global overview receipt source record count differs from frozen source pin')
    if type(receipt.get('archive_size_bytes')) is not int or receipt['archive_size_bytes'] <= 0:
        raise CombineError('Overview receipt archive size is missing or invalid')
    reported = {'sha256': receipt['archive_sha256'], 'size_bytes': receipt['archive_size_bytes']}
    actual = file_identity(overview_path)
    if reported != actual:
        raise CombineError('Overview archive does not match its passed receipt')
    max_bytes = criteria['gates']['maximum_compressed_overview_tile_bytes']
    maximum = receipt.get('maximum_compressed_tile_bytes')
    counts = receipt.get('tiles_by_zoom')
    if type(maximum) is not int or not 0 < maximum <= max_bytes:
        raise CombineError('Passed overview receipt lacks an in-limit maximum compressed tile size')
    if not isinstance(counts, dict) or set(counts) != {str(z) for z in range(8)} or any(type(counts[str(z)]) is not int or counts[str(z)] <= 0 for z in range(8)):
        raise CombineError('Passed overview receipt must report positive tile counts for z0-z7')
    selected = receipt.get('selected_by_zoom')
    if not isinstance(selected, dict) or set(selected) != {str(z) for z in range(8)} or any(type(selected[str(z)]) is not int or selected[str(z)] <= 0 for z in range(8)):
        raise CombineError('Passed overview receipt must report positive selected winner counts for z0-z7')
    expected_points, actual_points = receipt.get('expected_point_occurrences'), receipt.get('point_occurrences')
    if type(expected_points) is not int or expected_points <= 0 or actual_points != expected_points:
        raise CombineError('Overview receipt expected/actual point occurrence counts differ')
    if type(receipt.get('source_records')) is not int or receipt['source_records'] <= 0:
        raise CombineError('Overview receipt source record count is missing or invalid')
    return receipt, actual, {str(k): counts[str(k)] for k in range(8)}, maximum


def bounds_from_headers(headers):
    keys = ('min_lon_e7', 'min_lat_e7', 'max_lon_e7', 'max_lat_e7')
    for key in keys:
        if any(type(h.get(key)) is not int for h in headers):
            raise CombineError(f'Input PMTiles header lacks integer {key}')
    return {key: min(h[key] for h in headers) if key.startswith('min_') else max(h[key] for h in headers) for key in keys}


def resource_snapshot(task_root, criteria, start=False):
    free = shutil.disk_usage(task_root).free
    floor_key = 'minimum_start_free_gib' if start else 'minimum_running_free_gib'
    floor = criteria['resources'][floor_key] * (1024 ** 3)
    if free < floor:
        label = 'start' if start else 'running'
        raise CombineError(f'Free disk below {label} floor: {free} < {floor}')
    used = sum(p.stat().st_size for p in task_root.rglob('*') if p.is_file() and not p.is_symlink())
    ceiling = criteria['resources']['maximum_new_artifacts_gib'] * (1024 ** 3)
    if used > ceiling:
        raise CombineError(f'Task artifacts exceed ceiling: {used} > {ceiling}')
    return {'free_bytes': free, 'task_bytes': used}


def _assert_metadata(reader, layer_id, minzoom, maxzoom, header_minzoom, header_maxzoom, expected_fields=None):
    header = reader.header()
    if header.get('tile_type') != TileType.MVT:
        raise CombineError('Input is not an MVT PMTiles archive')
    if header.get('tile_compression') != Compression.GZIP:
        raise CombineError('Input tile payloads must be gzip-compressed')
    if (header.get('min_zoom'), header.get('max_zoom')) != (header_minzoom, header_maxzoom):
        raise CombineError('Input header zoom range differs')
    metadata = reader.metadata()
    layer = vector_layer(metadata, layer_id)
    if (layer.get('minzoom'), layer.get('maxzoom')) != (minzoom, maxzoom):
        raise CombineError(f'{layer_id} vector-layer zoom metadata differs')
    if expected_fields is not None and set(layer.get('fields', {})) != set(expected_fields):
        raise CombineError(f'{layer_id} fields differ from required source attributes')
    return header, metadata, layer


def _append_source(writer, reader, min_zoom, max_zoom, label, largest_tile, counters, resource_guard=None,
                   skip_below_min=False):
    count = 0
    skipped = 0
    for (z, x, y), raw in all_tiles(reader.get_bytes):
        if z > max_zoom or (z < min_zoom and not skip_below_min):
            raise CombineError(f'{label} contains unexpected zoom {z}')
        if z < min_zoom:
            skipped += 1
            if resource_guard and skipped % 1000 == 0:
                resource_guard()
            continue
        if len(raw) > largest_tile and label == 'overview':
            raise CombineError(f'Overview tile exceeds frozen compressed-byte ceiling: {len(raw)}')
        writer.write_tile(zxy_to_tileid(z, x, y), raw)
        counters[f'{label}_tiles'] += 1
        counters[f'{label}_payload_bytes'] += len(raw)
        count += 1
        if resource_guard and count % 1000 == 0:
            resource_guard()
    return count, skipped


def _verify_combined(baseline, overview, combined, baseline_n, overview_n, resource_guard=None):
    """Stream input payloads and output together, proving every raw byte and coordinate."""
    def detail_tiles():
        read = 0
        for coord, raw in all_tiles(baseline.get_bytes):
            read += 1
            if resource_guard and read % 1000 == 0:
                resource_guard()
            if 8 <= coord[0] <= 12:
                yield coord, raw

    baseline_iter = iter(detail_tiles())
    overview_iter = iter(all_tiles(overview.get_bytes))
    output_iter = iter(all_tiles(combined.get_bytes))
    expected = []
    try:
        expected.append(next(overview_iter))
    except StopIteration:
        pass
    try:
        expected.append(next(baseline_iter))
    except StopIteration:
        pass
    # Streams are already in tile-ID order, and z0-7 precedes z8-12.
    prior = -1
    checked = {'overview': 0, 'detail': 0, 'payload_bytes': 0}
    while expected:
        expected.sort(key=lambda item: zxy_to_tileid(*item[0]))
        coord, raw = expected.pop(0)
        tile_id = zxy_to_tileid(*coord)
        if tile_id <= prior:
            raise CombineError('Input tile coordinates overlap or are not globally ordered')
        prior = tile_id
        try:
            actual_coord, actual_raw = next(output_iter)
        except StopIteration as exc:
            raise CombineError('Combined archive omitted an input tile') from exc
        if actual_coord != coord or actual_raw != raw:
            raise CombineError(f'Combined raw payload differs at {coord}')
        label = 'overview' if coord[0] <= 7 else 'detail'
        checked[label] += 1
        checked['payload_bytes'] += len(raw)
        if resource_guard and (checked['overview'] + checked['detail']) % 1000 == 0:
            resource_guard()
        source_iter = overview_iter if label == 'overview' else baseline_iter
        try:
            expected.append(next(source_iter))
        except StopIteration:
            pass
    try:
        extra = next(output_iter)
    except StopIteration:
        extra = None
    if extra is not None:
        raise CombineError(f'Combined archive has an extra tile: {extra[0]}')
    if checked['overview'] != overview_n or checked['detail'] != baseline_n:
        raise CombineError('Combined reread counts differ from source counts')
    return checked


def _failure_receipt(task_root, output, exc):
    safe_name = output.name if output.name else 'combined-display'
    receipt = task_root / f'{safe_name}.failure.json'
    try:
        with receipt.open('x') as stream:
            json.dump({'status': 'failed', 'error': str(exc), 'output': str(output)}, stream, indent=2)
            stream.write('\n')
    except FileExistsError:
        pass


def combine(baseline_path, baseline_sha256, overview_path, overview_report_path, output, task_root, native_lock=None, enforce_resources=True):
    baseline_path, overview_path = Path(baseline_path), Path(overview_path)
    output, task_root = Path(output), Path(task_root)
    lock_path = Path(native_lock) if native_lock else ROOT / '.local/grwl-raw/.native-build.lock'
    task_root.mkdir(parents=True, exist_ok=True)
    output_abs, task_abs = output.resolve(), task_root.resolve()
    try:
        output_abs.relative_to(task_abs)
    except ValueError as exc:
        raise CombineError('Output directory must be inside task root') from exc
    if output_abs == task_abs:
        raise CombineError('Output directory must be a new child of task root')
    output, task_root = output_abs, task_abs
    if output.exists():
        raise CombineError('Refusing unknown existing output directory')
    lock_path = regular(lock_path)
    lock_stream = lock_path.open('rb')
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CombineError('Shared native build lock is held') from exc
        criteria = read_json(CRITERIA, 'frozen criteria')
        if criteria.get('status') != 'frozen_before_build':
            raise CombineError('Criteria are not frozen')
        criteria_sha = sha256(CRITERIA)
        if enforce_resources:
            resource_start = resource_snapshot(task_root, criteria, start=True)
        else:
            resource_start = {'bypassed_for_fixture': True}
        if len(baseline_sha256) != 64 or any(c not in '0123456789abcdef' for c in baseline_sha256):
            raise CombineError('Baseline SHA-256 pin is malformed')
        actual_baseline = file_identity(baseline_path)
        if actual_baseline['sha256'] != baseline_sha256:
            raise CombineError('Baseline archive does not match explicit SHA-256 pin')
        receipt, overview_identity, receipt_counts, receipt_max = report_receipt(overview_path, overview_report_path, criteria)
        baseline_stream, baseline_source, baseline_reader = tile_reader(baseline_path)
        overview_stream, overview_source, overview_reader = tile_reader(overview_path)
        try:
            bh, bm, detail_layer = _assert_metadata(
                baseline_reader, DETAIL_LAYER, 8, 12, 0, 12, ('width_m', 'width_valid'))
            baseline_overview_layer = vector_layer(bm, OLD_OVERVIEW_LAYER)
            if (baseline_overview_layer.get('minzoom'), baseline_overview_layer.get('maxzoom')) != (0, 7):
                raise CombineError('Pinned r2 coverage layer zoom metadata differs')
            oh, om, overview_layer = _assert_metadata(
                overview_reader, OVERVIEW_LAYER, 0, 7, 0, 7, ('width_m', 'width_valid'))
            if (bh.get('tile_compression'), oh.get('tile_compression')) != (Compression.GZIP, Compression.GZIP):
                raise CombineError('Both inputs must use gzip tile compression')
            if detail_layer.get('fields', {}).get('width_m') != 'Number' or detail_layer.get('fields', {}).get('width_valid') != 'Boolean':
                raise CombineError('Detailed layer source width field types differ')
            if overview_layer.get('fields', {}).get('width_m') != 'Number' or overview_layer.get('fields', {}).get('width_valid') != 'Boolean':
                raise CombineError('Overview layer fields must expose width_m and width_valid')
            guard = (lambda: resource_snapshot(task_root, criteria)) if enforce_resources else None
            baseline_by_zoom = {}
            overview_by_zoom = {}
            baseline_archive_count = check_tile_stream(
                baseline_reader, 0, 12, 'baseline', guard, baseline_by_zoom)
            overview_count = check_tile_stream(
                overview_reader, 0, 7, 'overview', guard, overview_by_zoom)
            if baseline_archive_count != bh.get('addressed_tiles_count') or overview_count != oh.get('addressed_tiles_count'):
                raise CombineError('PMTiles header tile counts differ from directory contents')
            baseline_old_overview_count = sum(baseline_by_zoom.get(z, 0) for z in range(8))
            baseline_detail_count = sum(baseline_by_zoom.get(z, 0) for z in range(8, 13))
            if baseline_detail_count + baseline_old_overview_count != baseline_archive_count:
                raise CombineError('Baseline detail/overview split differs from archive count')
            expected_overview_counts = {str(z): overview_by_zoom.get(z, 0) for z in range(8)}
            if expected_overview_counts != receipt_counts:
                raise CombineError('Overview receipt tile counts differ from archive contents')
            if baseline_sha256 == GLOBAL_BASELINE_SHA256:
                if (baseline_detail_count != GLOBAL_BASELINE_TILES
                        or baseline_archive_count != GLOBAL_BASELINE_ARCHIVE_TILES
                        or baseline_old_overview_count != GLOBAL_BASELINE_OLD_OVERVIEW_TILES):
                    raise CombineError('Pinned global r2 baseline does not contain 588,355 detail tiles')
                if receipt['scope'] != 'global':
                    raise CombineError('Global baseline requires a global-scope overview receipt')
                scope = 'global'
            else:
                scope = 'pilot'
            if enforce_resources:
                resource_snapshot(task_root, criteria)
            output.mkdir(parents=True, exist_ok=False)
            asset_path = output / ARCHIVE_REL
            asset_path.parent.mkdir(parents=True)
            temp_path = output / '.combine-tile-data.tmp'
            counters = {'overview_tiles': 0, 'detail_tiles': 0, 'overview_payload_bytes': 0, 'detail_payload_bytes': 0}
            metadata = dict(bm)
            metadata['vector_layers'] = [dict(detail_layer), dict(overview_layer)]
            metadata['name'] = 'GRWL raw widths, overview and detail'
            metadata['description'] = 'Selected source width observations at z0-7 and original detailed observations at z8-12.'
            metadata['minzoom'] = 0
            metadata['maxzoom'] = 12
            metadata['attribution'] = bm.get('attribution') or om.get('attribution')
            header = bounds_from_headers([bh, oh])
            header.update({'tile_type': TileType.MVT, 'tile_compression': Compression.GZIP,
                           'center_zoom': 3,
                           'center_lon_e7': (header['min_lon_e7'] + header['max_lon_e7']) // 2,
                           'center_lat_e7': (header['min_lat_e7'] + header['max_lat_e7']) // 2})
            started = time.time()
            try:
                with asset_path.open('xb') as stream:
                    writer = ExactWriter(stream, temp_path)
                    written_overview, skipped_overview = _append_source(
                        writer, overview_reader, 0, 7, 'overview',
                        criteria['gates']['maximum_compressed_overview_tile_bytes'], counters, guard)
                    written_detail, skipped_baseline = _append_source(
                        writer, baseline_reader, 8, 12, 'detail', 0, counters, guard, skip_below_min=True)
                    if (written_overview != overview_count or written_detail != baseline_detail_count
                            or skipped_overview != 0 or skipped_baseline != baseline_old_overview_count):
                        raise CombineError('Tile counts changed while writing')
                    writer.finalize(header, metadata)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            output_stream, output_source, output_reader = tile_reader(asset_path)
            try:
                output_header = output_reader.header()
                output_metadata = output_reader.metadata()
                if (output_header.get('min_zoom'), output_header.get('max_zoom')) != (0, 12):
                    raise CombineError('Combined header zoom range is not z0-z12')
                total_tiles = overview_count + baseline_detail_count
                if any(output_header.get(key) != total_tiles for key in ('addressed_tiles_count', 'tile_entries_count', 'tile_contents_count')):
                    raise CombineError('Combined header tile count is wrong')
                if output_metadata.get('vector_layers') != [dict(detail_layer), dict(overview_layer)]:
                    raise CombineError('Combined vector layer order/identity differs')
                if any(output_header.get(key) != value for key, value in bounds_from_headers([bh, oh]).items()):
                    raise CombineError('Combined header bounds differ from the union of input bounds')
                verification = _verify_combined(
                    baseline_reader, overview_reader, output_reader, baseline_detail_count,
                    overview_count, guard)
            finally:
                output_stream.close()
            if asset_path.stat().st_size > criteria['gates']['maximum_combined_archive_bytes']:
                raise CombineError('Combined archive exceeds frozen byte ceiling')
            if enforce_resources:
                resource_end = resource_snapshot(task_root, criteria)
            else:
                resource_end = {'bypassed_for_fixture': True}
            report = {
                'schema_version': 1,
                'status': 'built_unvalidated',
                'combine_status': 'passed',
                'scope': scope,
                'dataset_id': 'grwl-raw',
                'display_release_candidate': 'raw-v01.01-display-r3',
                'baseline': {**actual_baseline, 'sha256_pin': baseline_sha256,
                             'archive_tiles': baseline_archive_count, 'detail_tiles': baseline_detail_count,
                             'discarded_old_overview_tiles': baseline_old_overview_count,
                             'release': 'raw-v01.01-display-r2' if scope == 'global' else 'pinned_pilot_baseline'},
                'overview': {**overview_identity, 'receipt_path': str(Path(overview_report_path)),
                             'receipt_sha256': sha256(overview_report_path), 'receipt_status': receipt['status'],
                             'scope': receipt['scope'], 'source_sha256': receipt['source_sha256'],
                             'source_manifest_sha256': receipt['source_manifest_sha256'],
                             'verifier_sha256': receipt['verifier_sha256'],
                             'source_records': receipt['source_records'],
                             'selected_by_zoom': receipt['selected_by_zoom'],
                             'expected_point_occurrences': receipt['expected_point_occurrences'],
                             'point_occurrences': receipt['point_occurrences'],
                             'tile_counts_by_zoom': receipt_counts, 'maximum_compressed_tile_bytes': receipt_max,
                             'tiles': overview_count},
                'combined': {**file_identity(asset_path), 'path': ARCHIVE_REL.as_posix(),
                             'tiles': overview_count + baseline_detail_count,
                             'detail_payload_bytes': counters['detail_payload_bytes'],
                             'overview_payload_bytes': counters['overview_payload_bytes']},
                'verification': {'status': 'passed', **verification,
                                 'detail_raw_payloads_byte_identical': True,
                                 'overview_raw_payloads_byte_identical': True,
                                 'no_extra_or_overlapping_coordinates': True},
                'layers': [{'id': DETAIL_LAYER, 'minzoom': 8, 'maxzoom': 12,
                            'fields': detail_layer['fields']},
                           {'id': OVERVIEW_LAYER, 'minzoom': 0, 'maxzoom': 7,
                            'fields': overview_layer['fields']}],
                'criteria': {'path': str(CRITERIA.relative_to(ROOT)), 'sha256': criteria_sha},
                'code': {'path': str(Path(__file__).relative_to(ROOT)), 'sha256': sha256(__file__)},
                'started_unix_seconds': started,
                'elapsed_seconds': time.time() - started,
                'resources_start': resource_start,
                'resources_end': resource_end,
                'limitations': ['Source-wide winner-priority and selected-ID checks are delegated to the independent overview oracle.',
                                'Browser, clean regional replay, package finalization, public hosting and scientific validation remain pending.'],
            }
            report_path = output / 'combine-report.json'
            with report_path.open('x') as stream:
                json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write('\n')
            return report
        finally:
            baseline_stream.close()
            overview_stream.close()
    finally:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
        finally:
            lock_stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--baseline-sha256', required=True)
    parser.add_argument('--overview', required=True)
    parser.add_argument('--overview-report', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--task-root', required=True)
    parser.add_argument('--native-lock')
    args = parser.parse_args(argv)
    output, task_root = Path(args.output), Path(args.task_root)
    try:
        result = combine(args.baseline, args.baseline_sha256, args.overview, args.overview_report,
                         output, task_root, args.native_lock)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        task_root.mkdir(parents=True, exist_ok=True)
        _failure_receipt(task_root, output, exc)
        print(f'combine failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
