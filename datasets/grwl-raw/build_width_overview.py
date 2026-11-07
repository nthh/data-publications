#!/usr/bin/env python3
"""Select actual GRWL width observations for a zoom 0–7 point-symbol overview.

No line connections or width averages are synthesized. The analytical source is
unchanged. Every output point retains the winning original observation's ID and
width, anchored at its first vertex in its first nonempty source part.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
import threading
import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from mapbox_vector_tile.Mapbox import vector_tile_pb2 as mvt
from pmtiles.writer import Writer
from pmtiles.tile import Entry, TileType, Compression, zxy_to_tileid

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / 'research/grwl-width-overview-20261106/criteria.json'
Q_BITS = 28
Q = 1 << Q_BITS
CELLS = 1024
EXTENT = 4096
BUFFER = 32
LAYER = 'grwl_width_overview'
LAT_LIMIT = math.degrees(math.atan(math.sinh(math.pi)))
SCHEMA = pa.schema([('cell', pa.uint64()), ('feature_id', pa.uint64()),
    ('width_m', pa.int64()), ('width_valid', pa.bool_()), ('qx', pa.uint32()),
    ('qy', pa.uint32()), ('longitude', pa.float64()), ('latitude', pa.float64())])


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def guard(task_root, *, start=False):
    free = shutil.disk_usage(task_root).free
    used = 0
    for p in task_root.rglob('*'):
        try:
            if p.is_file() and not p.is_symlink():
                used += p.stat().st_size
        except FileNotFoundError:
            pass  # A sorter may remove its own temporary file during inspection.
    if free < (40 if start else 15) * 2**30 or used > 12 * 2**30:
        raise RuntimeError(f'Resource guard: free={free}, task_bytes={used}, start={start}')
    return {'free_bytes': free, 'task_bytes': used}


@contextmanager
def guarded_sort(connection, task_root):
    stop = threading.Event()
    failures = []
    def monitor():
        while not stop.wait(5):
            try:
                guard(task_root)
            except Exception as error:
                failures.append(error)
                connection.interrupt()
                return
    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    try:
        yield
        if failures:
            raise RuntimeError(str(failures[0]))
    except Exception as error:
        if failures:
            raise RuntimeError(str(failures[0])) from error
        raise
    finally:
        stop.set()
        worker.join()


def first_anchor(data):
    """Independent of GEOS: read the first nonempty original line part."""
    def visit(offset):
        if offset + 9 > len(data):
            raise ValueError('Truncated WKB')
        order = data[offset]
        if order not in (0, 1):
            raise ValueError('Invalid WKB byte order')
        endian = '<' if order else '>'
        kind, count = struct.unpack_from(endian + 'II', data, offset + 1)
        offset += 9
        if kind == 2:
            end = offset + 16 * count
            if end > len(data):
                raise ValueError('Truncated LineString')
            return (struct.unpack_from(endian + 'dd', data, offset) if count else None), end
        if kind == 5:
            for _ in range(count):
                anchor, offset = visit(offset)
                if anchor is not None:
                    return anchor, offset
            return None, offset
        raise ValueError(f'Expected 2D LineString/MultiLineString, got {kind}')
    anchor, _ = visit(0)
    if anchor is None:
        raise ValueError('Empty observation has no display anchor')
    return anchor


def project_anchors(longitude, latitude):
    longitude = np.asarray(longitude, dtype=np.float64)
    latitude = np.asarray(latitude, dtype=np.float64)
    if not np.isfinite(longitude).all() or not np.isfinite(latitude).all() or np.any(np.abs(longitude) > 180) or np.any(np.abs(latitude) > 90):
        raise ValueError('Nonfinite or out-of-range source coordinate')
    x = (longitude + 180.0) / 360.0
    y = (1 - np.arcsinh(np.tan(np.deg2rad(np.clip(latitude, -LAT_LIMIT, LAT_LIMIT)))) / np.pi) / 2
    qx = np.floor(x * Q + 0.5).astype(np.uint64) % Q
    qy = np.floor(np.clip(y, 0, 1) * Q + 0.5).astype(np.uint64)
    return qx.astype(np.uint32), qy.astype(np.uint32)


def cells_at_zoom(qx, qy, zoom):
    shift = Q_BITS - (10 + zoom)
    x = np.asarray(qx, dtype=np.uint64) >> shift
    y = np.minimum(np.asarray(qy, dtype=np.uint64), Q - 1) >> shift
    return y * (CELLS << zoom) + x


def candidate_batch(batch):
    xy = np.asarray([first_anchor(value) for value in batch['geometry'].to_pylist()], dtype=np.float64)
    qx, qy = project_anchors(xy[:, 0], xy[:, 1])
    cells = cells_at_zoom(qx, qy, 7)
    ids = batch['feature_id'].to_numpy(zero_copy_only=False)
    widths = batch['width_m'].fill_null(0).to_numpy(zero_copy_only=False)
    nulls = batch['width_m'].is_null().to_numpy(zero_copy_only=False)
    valid = batch['width_valid'].to_numpy(zero_copy_only=False)
    if batch['width_valid'].null_count or not np.array_equal(valid, ~nulls & (widths > 0) & (widths != 1)):
        raise ValueError('Source width_valid differs from documented sentinel rule')
    if np.any(ids < 0) or np.any(ids > 2**53 - 1):
        raise ValueError('Source IDs are not safe exact browser integers')
    priority = np.where(valid, -widths, 1)
    order = np.lexsort((ids, priority, cells))
    ordered_cells = cells[order]
    take = order[np.r_[True, ordered_cells[1:] != ordered_cells[:-1]]]
    idx = pa.array(take)
    return pa.Table.from_arrays([pa.array(cells[take], type=pa.uint64()),
        batch['feature_id'].take(idx).cast(pa.uint64()), batch['width_m'].take(idx),
        batch['width_valid'].take(idx), pa.array(qx[take]), pa.array(qy[take]),
        pa.array(xy[take, 0]), pa.array(xy[take, 1])], schema=SCHEMA)


def sql_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def select_winners(connection, source, target, *, previous_zoom=None):
    key = 'cell'
    if previous_zoom is not None:
        previous_n = CELLS << previous_zoom
        key = f'((cell // {previous_n}) // 2) * {previous_n // 2} + ((cell % {previous_n}) // 2)'
    # arg_min(struct, struct) keeps one wide hash-aggregate state per cell and
    # exhausted the frozen 1 GB budget on the complete source. An external sort
    # can spill; consume ordered cell groups without retaining a global map.
    query = f'''SELECT CAST({key} AS UBIGINT) AS cell, feature_id, width_m,
        width_valid, qx, qy, longitude, latitude
        FROM read_parquet({sql_string(source)})
        ORDER BY cell,
          CASE WHEN width_valid THEN -width_m ELSE 1 END,
          feature_id'''
    reader = connection.execute(query).fetch_record_batch(32768)
    previous_cell = None
    with pq.ParquetWriter(target, SCHEMA, compression='zstd', compression_level=3) as sink:
        for batch in reader:
            if not len(batch):
                continue
            values = batch['cell'].to_numpy()
            first = np.r_[previous_cell is None or int(values[0]) != previous_cell,
                          values[1:] != values[:-1]]
            previous_cell = int(values[-1])
            take = np.flatnonzero(first)
            if len(take):
                sink.write_table(pa.Table.from_batches([batch]).take(pa.array(take)).cast(SCHEMA),
                                 row_group_size=32768)


def point_copies(table, zoom):
    """Return tile coordinates and row indices; buffer after global selection."""
    shift = Q_BITS - (12 + zoom)
    world = EXTENT << zoom
    px = ((table['qx'].to_numpy().astype(np.uint64) + (1 << (shift - 1))) >> shift).astype(np.int64) % world
    py = ((table['qy'].to_numpy().astype(np.uint64) + (1 << (shift - 1))) >> shift).astype(np.int64)
    tx = px // EXTENT
    ty = np.minimum(py // EXTENT, (1 << zoom) - 1)
    records = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            xx = tx + dx
            yy = ty + dy
            lx, ly = px - xx * EXTENT, py - yy * EXTENT
            keep = (yy >= 0) & (yy < (1 << zoom)) & (lx >= -BUFFER) & (lx <= EXTENT + BUFFER) & (ly >= -BUFFER) & (ly <= EXTENT + BUFFER)
            indices = np.flatnonzero(keep)
            if not len(indices):
                continue
            records.append((yy[indices] * (1 << zoom) + (xx[indices] % (1 << zoom)), indices, lx[indices], ly[indices]))
    if not records:
        return tuple(np.empty(0, dtype=np.int64) for _ in range(4))
    columns = [np.concatenate([record[i] for record in records]) for i in range(4)]
    # Source ID stabilizes the encoded order; local coords distinguish z0 seam copies.
    ids = table['feature_id'].to_numpy()
    order = np.lexsort((columns[3], columns[2], ids[columns[1]], columns[0]))
    return tuple(column[order] for column in columns)


def zigzag(value):
    return (value << 1) ^ (value >> 31)


def encode_tile(ids, widths, valid, xx, yy):
    tile = mvt.tile()
    layer = tile.layers.add(); layer.name = LAYER; layer.version = 2; layer.extent = EXTENT
    layer.keys.extend(['width_m', 'width_valid'])
    layer.values.add().bool_value = False
    layer.values.add().bool_value = True
    width_indices = {}
    for width in sorted({int(value) for value in widths if value is not None}):
        width_indices[width] = len(layer.values)
        layer.values.add().int_value = width
    for fid, width, usable, x, y in zip(ids, widths, valid, xx, yy, strict=True):
        feature = layer.features.add(); feature.id = int(fid); feature.type = 1
        if width is not None:
            feature.tags.extend([0, width_indices[int(width)]])
        feature.tags.extend([1, 1 if usable else 0])
        feature.geometry.extend([9, zigzag(int(x)), zigzag(int(y))])
    return gzip.compress(tile.SerializeToString(deterministic=True), compresslevel=6, mtime=0)


class ExactWriter(Writer):
    def write_tile(self, tileid, data):
        if self.tile_entries and tileid <= self.tile_entries[-1].tile_id:
            raise ValueError('Tiles must be unique and ordered')
        self.tile_f.write(data)
        self.tile_entries.append(Entry(tileid, self.offset, len(data), 1))
        self.hash_to_offset[tileid] = self.offset
        self.offset += len(data); self.addressed_tiles += 1


def encode_overview(samples, output, task_root):
    """Bound memory to three tile rows, then assemble compressed tiles by ID."""
    stats, encoded_tiles = [], []
    with tempfile.TemporaryDirectory(prefix='encoded-tiles-', dir=output.parent) as temp:
        tile_root = Path(temp)
        for z in range(8):
            parquet = pq.ParquetFile(samples / f'z{z}.parquet')
            pending = {}
            total = maximum = occurrences = count = 0
            current_band = -1

            def flush(keys):
                nonlocal total, maximum, count
                for key in sorted(keys):
                    pieces = pending.pop(key)
                    ids = np.concatenate([p[0] for p in pieces])
                    widths = [value for p in pieces for value in p[1]]
                    valid = np.concatenate([p[2] for p in pieces])
                    xx = np.concatenate([p[3] for p in pieces])
                    yy = np.concatenate([p[4] for p in pieces])
                    order = np.lexsort((yy, xx, ids))
                    payload = encode_tile(ids[order], [widths[int(i)] for i in order], valid[order], xx[order], yy[order])
                    if len(payload) > 2 * 2**20:
                        raise ValueError('Overview tile exceeds frozen 2 MiB ceiling')
                    tileid = zxy_to_tileid(z, key % (1 << z), key // (1 << z))
                    tile_path = tile_root / str(tileid)
                    with tile_path.open('xb') as f:
                        f.write(payload)
                    encoded_tiles.append((tileid, tile_path))
                    total += len(payload); maximum = max(maximum, len(payload)); count += 1
                    if count % 100 == 0:
                        guard(task_root)

            for batch in parquet.iter_batches(batch_size=32768, use_threads=False):
                table = pa.Table.from_batches([batch])
                bands = np.minimum(table['qy'].to_numpy().astype(np.uint64), Q - 1) >> (Q_BITS - z)
                cuts = np.r_[0, np.flatnonzero(bands[1:] != bands[:-1]) + 1, len(bands)]
                for start, end in zip(cuts[:-1], cuts[1:]):
                    band = int(bands[start])
                    if band < current_band:
                        raise ValueError('Source samples are not sorted by tile row')
                    if band != current_band:
                        flush([key for key in pending if key // (1 << z) < band - 1])
                        current_band = band
                    block = table.slice(int(start), int(end - start))
                    keys, indices, xx, yy = point_copies(block, z)
                    splits = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1, len(keys)]
                    ids, widths, valid = block['feature_id'].to_numpy(), block['width_m'].to_pylist(), block['width_valid'].to_numpy()
                    for a, b in zip(splits[:-1], splits[1:]):
                        if a == b:
                            continue
                        index = indices[a:b]
                        pending.setdefault(int(keys[a]), []).append((ids[index], [widths[int(i)] for i in index], valid[index], xx[a:b], yy[a:b]))
                    occurrences += len(indices)
            flush(list(pending))
            stats.append({'zoom': z, 'selected_observations': parquet.metadata.num_rows,
                'encoded_occurrences_with_buffers': occurrences, 'tiles': count, 'tile_bytes': total,
                'maximum_tile_bytes': maximum})
            guard(task_root)
            print(json.dumps({'stage': 'encode', **stats[-1]}), flush=True)
        with output.open('xb') as stream:
            writer = ExactWriter(stream)
            for tileid, path in sorted(encoded_tiles):
                writer.write_tile(tileid, path.read_bytes())
            header = {'tile_type': TileType.MVT, 'tile_compression': Compression.GZIP,
                'min_lon_e7': -1800000000, 'max_lon_e7': 1800000000,
                'min_lat_e7': round(-LAT_LIMIT * 1e7), 'max_lat_e7': round(LAT_LIMIT * 1e7),
                'center_lon_e7': 0, 'center_lat_e7': 200000000, 'center_zoom': 0}
            metadata = {'name': 'GRWL selected width observations',
                'description': 'Selected original observations; widest valid measured width per screen-scale cell. Symbol diameter is exaggerated, not riverbanks.',
                'attribution': 'Allen and Pavelsky (2018), GRWL V01.01; CC BY 4.0',
                'vector_layers': [{'id': LAYER, 'minzoom': 0, 'maxzoom': 7,
                    'fields': {'width_m': 'Number', 'width_valid': 'Boolean'},
                    'description': 'Original source ID and measured width at a source geometry anchor; selected, not averaged.'}]}
            writer.finalize(header, metadata)
    return stats


def build(source, source_manifest, output, task_root, native_lock):
    source, source_manifest, output, task_root, native_lock = [Path(p).expanduser().resolve() for p in (source, source_manifest, output, task_root, native_lock)]
    if os.path.lexists(output):
        raise FileExistsError('Refusing existing output')
    output.relative_to(task_root)
    task_root.mkdir(parents=True, exist_ok=True)
    resources = guard(task_root, start=True)
    active_lock = Path(sys.prefix).resolve().parent / 'uv.lock'
    if sha256(active_lock) != sha256(ROOT / 'scripts/display_tools/uv.lock'):
        raise ValueError('Use the committed display_tools environment')
    meta = json.loads(source_manifest.read_text())
    source_hash = sha256(source)
    if source_hash != meta['parquet_sha256']:
        raise ValueError('Source manifest SHA-256 mismatch')
    with native_lock.open('a') as reservation:
        fcntl.flock(reservation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(); (output / 'samples').mkdir(); (output / 'workflow').mkdir()
        for p in (Path(__file__), CRITERIA, active_lock):
            shutil.copyfile(p, output / 'workflow' / p.name)
        start = time.monotonic(); rows = candidates = 0
        write_json(output / 'partial.json', {'status': 'building', 'usable_release': False})
        try:
            with tempfile.TemporaryDirectory(prefix='scratch-', dir=output) as scratch:
                scratch = Path(scratch)
                temporary_source = scratch / 'candidates.parquet'
                with pq.ParquetWriter(temporary_source, SCHEMA, compression='zstd', compression_level=3) as sink:
                    for index, batch in enumerate(pq.ParquetFile(source).iter_batches(batch_size=32768,
                            columns=['geometry', 'feature_id', 'width_m', 'width_valid'], use_threads=False)):
                        chosen = candidate_batch(batch)
                        sink.write_table(chosen, row_group_size=32768)
                        rows += len(batch); candidates += len(chosen)
                        if index % 100 == 0:
                            guard(task_root)
                            print(json.dumps({'stage': 'anchors', 'rows': rows, 'candidates': candidates, 'seconds': round(time.monotonic() - start, 2)}), flush=True)
                if rows != meta['rows']:
                    raise ValueError('Source row count mismatch')
                connection = duckdb.connect()
                try:
                    connection.execute("SET threads=2")
                    connection.execute("SET memory_limit='1GB'")
                    connection.execute('SET temp_directory=' + sql_string(scratch / 'duckdb'))
                    with guarded_sort(connection, task_root):
                        select_winners(connection, temporary_source, output / 'samples/z7.parquet')
                        for z in range(6, -1, -1):
                            select_winners(connection, output / f'samples/z{z+1}.parquet', output / f'samples/z{z}.parquet', previous_zoom=z+1)
                            guard(task_root)
                finally:
                    connection.close()
                previous_tempdir = tempfile.tempdir
                try:
                    tempfile.tempdir = str(scratch)
                    stats = encode_overview(output / 'samples', output / 'overview.pmtiles', task_root)
                finally:
                    tempfile.tempdir = previous_tempdir
            report = {'schema_version': 1, 'status': 'built_unvalidated', 'source_sha256': source_hash,
                'source_manifest_sha256': sha256(source_manifest), 'criteria_sha256': sha256(CRITERIA),
                'rows': rows, 'candidate_rows': candidates, 'per_zoom': stats,
                'seconds': time.monotonic() - start, 'resources_start': resources,
                'resources_end': guard(task_root),
                'packages': {p: importlib.metadata.version(p) for p in ('duckdb', 'numpy', 'pyarrow', 'pmtiles', 'mapbox-vector-tile')},
                'artifacts': {str(p.relative_to(output)): {'sha256': sha256(p), 'size_bytes': p.stat().st_size}
                    for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'partial.json'}}
            write_json(output / 'build.json', report)
            write_json(output / 'partial.json', {'status': 'built_unvalidated', 'usable_release': False})
            return report
        except BaseException as error:
            write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(error).__name__, 'error': str(error), 'rows': rows, 'seconds': time.monotonic() - start})
            raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'source-manifest', 'output', 'task-root', 'native-lock'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    result = build(a.source, a.source_manifest, a.output, a.task_root, a.native_lock)
    print(json.dumps({k: result[k] for k in ('status', 'rows', 'seconds')}))
