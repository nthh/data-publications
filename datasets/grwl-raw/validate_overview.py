#!/usr/bin/env python3
"""Independent PROJ/GEOS source occupancy and decoded MVT rectangle oracles."""
from __future__ import annotations
import gzip
import hashlib
import json
import math
from pathlib import Path
import mapbox_vector_tile
import numpy as np
import shapely
from pmtiles.reader import MmapSource, Reader, all_tiles
from pmtiles.tile import Compression
from mapbox_vector_tile.Mapbox import vector_tile_pb2 as mvt
from pyproj import Transformer

PROJECT = Transformer.from_crs(4326, 3857, always_xy=True, force_over=True)
HALF_WORLD = math.pi * 6378137.0
LAYER = 'grwl_overview'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _line_parts(geometry):
    """Scalar traversal independent of production's component-index extraction."""
    if geometry.is_empty:
        raise ValueError('empty source geometry')
    if geometry.geom_type == 'LineString':
        yield geometry
    elif geometry.geom_type in ('MultiLineString', 'GeometryCollection'):
        for part in geometry.geoms:
            yield from _line_parts(part)
    else:
        raise ValueError(f'non-line source component {geometry.geom_type}')


def oracle_segments(geometries, grid_size):
    """Continuous PROJ Mercator; independent parts; shortest periodic segments."""
    output = []
    for geometry in geometries:
        for part in _line_parts(geometry):
            coordinates = np.asarray(part.coords, dtype=np.float64)
            if coordinates.shape[1] != 2 or not np.isfinite(coordinates).all():
                raise ValueError('source coordinates must be finite 2D')
            if np.any(np.abs(coordinates[:, 0]) > 180) or np.any(np.abs(coordinates[:, 1]) > 90):
                raise ValueError('source coordinates outside lon/lat bounds')
            latitude = np.clip(coordinates[:, 1], -math.degrees(math.atan(math.sinh(math.pi))), math.degrees(math.atan(math.sinh(math.pi))))
            px, py = PROJECT.transform(coordinates[:, 0], latitude, errcheck=True)
            x = (np.asarray(px) / HALF_WORLD + 1) * (grid_size / 2)
            y = np.clip((1 - np.asarray(py) / HALF_WORLD) * (grid_size / 2), 0, grid_size)
            for index in range(len(coordinates) - 1):
                ax, bx = float(x[index]), float(x[index + 1])
                if bx - ax > grid_size / 2:
                    bx -= grid_size
                elif bx - ax < -grid_size / 2:
                    bx += grid_size
                output.append((ax, float(y[index]), bx, float(y[index + 1])))
    result = np.asarray(output, dtype=np.float64).reshape((-1, 4))
    if not np.isfinite(result).all():
        raise ValueError('nonfinite projected segment')
    return result


def oracle_cells(segments, grid_size, maximum_candidates=2_000_000):
    """Closed GEOS segment/box intersections with bounded vectorized candidates.

    ceil(min)-1 includes the preceding cell at exact edges. x wraps modulo N;
    only y clamps. The implementation shares no production slab-clipping code.
    """
    segments = np.asarray(segments, dtype=np.float64).reshape((-1, 4))
    if not np.isfinite(segments).all() or grid_size < 1:
        raise ValueError('invalid segments or grid size')
    pieces = []
    for start in range(0, len(segments), 8192):
        chunk = segments[start:start + 8192]
        lo_x = np.ceil(np.minimum(chunk[:, 0], chunk[:, 2])).astype(np.int64) - 1
        hi_x = np.floor(np.maximum(chunk[:, 0], chunk[:, 2])).astype(np.int64)
        lo_y = np.maximum(0, np.ceil(np.minimum(chunk[:, 1], chunk[:, 3])).astype(np.int64) - 1)
        hi_y = np.minimum(grid_size - 1, np.floor(np.maximum(chunk[:, 1], chunk[:, 3])).astype(np.int64))
        widths = hi_x - lo_x + 1
        counts = widths * np.maximum(0, hi_y - lo_y + 1)
        total = int(counts.sum())
        if total > maximum_candidates:
            if len(chunk) == 1:
                ax, ay, bx, by = chunk[0]
                mx, my = (ax + bx) / 2, (ay + by) / 2
                if (mx == ax and my == ay) or (mx == bx and my == by):
                    raise ValueError('cannot subdivide oracle segment further')
                pieces.append(oracle_cells([[ax, ay, mx, my], [mx, my, bx, by]], grid_size, maximum_candidates))
                continue
            middle = len(chunk) // 2
            pieces.extend((oracle_cells(chunk[:middle], grid_size, maximum_candidates),
                           oracle_cells(chunk[middle:], grid_size, maximum_candidates)))
            continue
        if not total:
            continue
        owners = np.repeat(np.arange(len(chunk)), counts)
        offsets = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
        cx = lo_x[owners] + offsets % widths[owners]
        cy = lo_y[owners] + offsets // widths[owners]
        boxes = shapely.box(cx, cy, cx + 1, cy + 1)
        lines = shapely.linestrings(chunk.reshape((-1, 2, 2)))
        touched = shapely.intersects(lines[owners], boxes)
        pieces.append(cy[touched].astype(np.uint64) * np.uint64(grid_size)
                      + (cx[touched] % grid_size).astype(np.uint64))
    return np.unique(np.concatenate(pieces)) if pieces else np.empty(0, dtype=np.uint64)


def compare_source_subset(geometries, production_module, grid_size):
    geometries = list(geometries)
    expected = oracle_cells(oracle_segments(geometries, grid_size), grid_size)
    actual = np.unique(np.asarray(production_module.cells_for_segments(
        production_module.project_segments(geometries, grid_size), grid_size), dtype=np.uint64))
    missing, extra = np.setdiff1d(expected, actual), np.setdiff1d(actual, expected)
    return {'passed': not len(missing) and not len(extra), 'source_records': len(geometries),
            'expected_cells': len(expected), 'actual_cells': len(actual),
            'missing_cells': len(missing), 'extra_cells': len(extra),
            'missing_examples': missing[:16].tolist(), 'extra_examples': extra[:16].tolist()}


def decoded_tile_mask(layer, cells_per_tile=512, extent=4096):
    """Require clockwise horizontal cell runs, exact grid, no interior overlap."""
    if layer.get('extent') != extent or extent % cells_per_tile:
        raise ValueError('unexpected overview extent')
    step = extent // cells_per_tile
    mask = np.zeros((cells_per_tile, cells_per_tile), dtype=bool)
    for feature in layer.get('features', []):
        if feature.get('properties'):
            raise ValueError('overview contains attributes')
        geometry = feature.get('geometry', {})
        rings = geometry.get('coordinates', [])
        if geometry.get('type') != 'Polygon' or len(rings) != 1:
            raise ValueError('overview feature is not one single-ring polygon')
        ring = np.asarray(rings[0])
        if ring.shape != (5, 2) or not np.isfinite(ring).all() or not np.array_equal(ring[0], ring[-1]):
            raise ValueError('overview run is not a closed four-corner ring')
        if np.any(ring != np.round(ring)) or np.any(ring % step) or np.any(ring < 0) or np.any(ring > extent):
            raise ValueError('overview vertices lie outside the exact cell grid')
        polygon = shapely.Polygon(ring)
        x0, y0 = ring.min(axis=0).astype(int)
        x1, y1 = ring.max(axis=0).astype(int)
        corners = {(x0, y0), (x0, y1), (x1, y0), (x1, y1)}
        signed_area = np.sum(ring[:-1, 0] * ring[1:, 1] - ring[1:, 0] * ring[:-1, 1])
        if (not polygon.is_valid or polygon.area != (x1 - x0) * (y1 - y0)
                or y1 - y0 != step or x1 <= x0
                or set(map(tuple, ring[:-1])) != corners or signed_area <= 0):
            raise ValueError('overview run is not a valid clockwise horizontal cell rectangle')
        region = mask[y0 // step:y1 // step, x0 // step:x1 // step]
        if region.any():
            raise ValueError('overview polygon interiors overlap')
        region[:] = True
    return mask


def expected_tile_mask(packed, zoom, x, y, cells_per_tile=512, max_zoom=7, bitorder='little'):
    """Independently reduce this tile from the packed finest source mask."""
    fine_n = cells_per_tile * (1 << max_zoom)
    scale = 1 << (max_zoom - zoom)
    width = cells_per_tile * scale
    left, top = x * width, y * width
    rows = np.asarray(packed).reshape((fine_n, fine_n // 8))[top:top + width, left // 8:(left + width) // 8]
    if scale >= 8:
        return rows.reshape(cells_per_tile, scale, cells_per_tile, scale // 8).any(axis=(1, 3))
    cells = np.unpackbits(rows, axis=1, bitorder=bitorder)
    return cells.reshape(cells_per_tile, scale, cells_per_tile, scale).any(axis=(1, 3))


def validate_archive(archive, packed_mask_path, report, criteria, bitorder='little'):
    """Stream every overview tile, recover cells, compare OR-reduced sealed mask.

    Receipts are exclusive. This establishes encoding fidelity; source-to-mask
    correctness is established separately by compare_source_subset. Packed rows
    use little-bit-first order by default and are content-bound in the receipt.
    """
    archive, packed_mask_path, report = map(Path, (archive, packed_mask_path, report))
    if report.exists():
        raise FileExistsError('refusing to overwrite overview validation receipt')
    overview = criteria['overview']
    min_zoom, max_zoom = overview['zooms']
    cells_per_tile = overview['cells_per_tile']
    n = cells_per_tile * (1 << max_zoom)
    if packed_mask_path.stat().st_size != n * n // 8:
        raise ValueError('finest packed mask has wrong size')
    packed = np.memmap(packed_mask_path, dtype=np.uint8, mode='r')
    bindings = {'archive_sha256':sha256(archive),'finest_mask_sha256':sha256(packed_mask_path),
                'mask_bitorder':bitorder,'oracle_sha256':sha256(__file__),
                'criteria_json_sha256':hashlib.sha256(json.dumps(criteria,sort_keys=True).encode()).hexdigest()}
    seen = set()
    counts = {z: 0 for z in range(min_zoom, max_zoom + 1)}
    largest = 0
    try:
        with archive.open('rb') as stream:
            source = MmapSource(stream)
            if Reader(source).header()['tile_compression'] != Compression.GZIP:
                raise ValueError('overview archive must declare gzip tile compression')
            for (z, x, y), raw in all_tiles(source):
                if z > max_zoom:
                    continue
                if z < min_zoom or (z, x, y) in seen:
                    raise ValueError('unexpected or duplicate overview tile coordinate')
                seen.add((z, x, y))
                largest = max(largest, len(raw))
                if len(raw) > overview['maximum_gzip_tile_bytes']:
                    raise ValueError('overview tile exceeds frozen byte ceiling')
                payload = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
                native = mvt.tile()
                native.ParseFromString(payload)
                if (len(native.layers) != 1 or native.layers[0].name != overview['layer']
                        or native.layers[0].version != 2 or native.layers[0].keys or native.layers[0].values):
                    raise ValueError('unexpected native overview layer declarations')
                layers = mapbox_vector_tile.decode(payload, default_options={'y_coord_down': True})
                if set(layers) != {overview['layer']}:
                    raise ValueError('unexpected overview layer set')
                mask = decoded_tile_mask(layers[overview['layer']], cells_per_tile, overview['extent'])
                expected = expected_tile_mask(packed, z, x, y, cells_per_tile, max_zoom, bitorder)
                if not mask.any() or not np.array_equal(mask, expected):
                    raise ValueError(f'overview mask mismatch at {z}/{x}/{y}')
                counts[z] += 1
            for z in counts:
                if not counts[z]:
                    raise ValueError(f'empty overview zoom {z}')
                for y in range(1 << z):
                    for x in range(1 << z):
                        if (z, x, y) not in seen and expected_tile_mask(packed, z, x, y, cells_per_tile, max_zoom, bitorder).any():
                            raise ValueError(f'missing occupied overview tile {z}/{x}/{y}')
        result = {'status': 'passed', **bindings,
                  'tiles_by_zoom': counts, 'largest_gzip_tile_bytes': largest,
                  'scope': 'all decoded overview masks; independent source subset is a separate gate'}
    except Exception as exc:
        with report.open('x') as output:
            output.write(json.dumps({'status': 'failed', **bindings, 'error': f'{type(exc).__name__}: {exc}'}, indent=2) + '\n')
        raise
    with report.open('x') as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def validate_source_subset(parquet, source_manifest, criteria, production_module, report, packed_mask_path=None):
    """All frozen heldout rows plus first32 elsewhere, pruned by source stats.

    Compare each row-group subset exactly, and optionally require every oracle
    cell present in the global packed mask. The latter is only an inclusion
    check; it cannot establish absence of false positives outside this subset.
    """
    import pyarrow.parquet as pq
    parquet, source_manifest, report = map(Path, (parquet, source_manifest, report))
    if report.exists():
        raise FileExistsError('refusing to overwrite source oracle receipt')
    controls = criteria['overview']['independent_source_controls']
    heldout = set(criteria['heldout_source_tiles'])
    if not controls['all_records_in_heldout_source_tiles']:
        raise ValueError('all heldout records must be frozen controls')
    first = controls['first_records_per_other_source_tile']
    n = criteria['overview']['cells_per_tile'] * (1 << criteria['overview']['zooms'][1])
    manifest = json.loads(source_manifest.read_text())
    if sha256(parquet) != criteria['source']['parquet_sha256'] or manifest['parquet_sha256'] != criteria['source']['parquet_sha256']:
        raise ValueError('source differs from frozen source pin')
    expected = {tile['tile']: tile['records'] if tile['tile'] in heldout else min(first,tile['records']) for tile in manifest['tiles']}
    if not heldout <= expected.keys():
        raise ValueError('heldout tile absent from source manifest')
    counts = {tile: 0 for tile in expected}
    result = {'status': 'running', 'source_sha256': criteria['source']['parquet_sha256'],
              'source_manifest_sha256': sha256(source_manifest),
              'criteria_json_sha256': hashlib.sha256(json.dumps(criteria,sort_keys=True).encode()).hexdigest(),
              'oracle_sha256': sha256(__file__),
              'production_module_sha256': sha256(production_module.__file__),
              'selection': controls, 'heldout_tiles': sorted(heldout),
              'row_groups_read': 0, 'records': 0, 'subset_missing_cells': 0,
              'subset_extra_cells': 0, 'global_missing_cells': 0, 'failures': []}
    packed = None
    if packed_mask_path is not None:
        if Path(packed_mask_path).stat().st_size != n*n//8:
            raise ValueError('packed global mask has wrong size')
        packed = np.memmap(packed_mask_path,mode='r',dtype=np.uint8)
    try:
        pf = pq.ParquetFile(parquet)
        tile_col, row_col = pf.schema.names.index('source_tile'), pf.schema.names.index('source_row')
        for group in range(pf.num_row_groups):
            tile_stats = pf.metadata.row_group(group).column(tile_col).statistics
            row_stats = pf.metadata.row_group(group).column(row_col).statistics
            if (tile_stats is None or row_stats is None or not tile_stats.has_min_max
                    or not row_stats.has_min_max):
                raise ValueError('source oracle requires source tile/row pruning statistics')
            possible = {tile for tile in expected if tile_stats.min <= tile <= tile_stats.max}
            if not possible:
                raise ValueError('row-group tile range absent from source manifest')
            if not (possible & heldout) and row_stats.min > first:
                continue
            batch = pf.read_row_group(group,columns=['source_tile','source_row','geometry'],use_threads=False)
            tiles, rows = batch['source_tile'].to_pylist(), np.asarray(batch['source_row'])
            if any(value not in possible for value in tiles):
                raise ValueError('source tile rows differ from their pruning statistics or manifest')
            selected = np.array([tile in heldout or row <= first for tile,row in zip(tiles,rows,strict=True)])
            geometries = shapely.from_wkb(batch['geometry'].to_pylist())[selected]
            oracle = oracle_cells(oracle_segments(geometries,n),n)
            actual = np.unique(production_module.cells_for_segments(production_module.project_segments(geometries,n),n))
            missing, extra = np.setdiff1d(oracle,actual), np.setdiff1d(actual,oracle)
            global_missing = np.empty(0,dtype=np.uint64)
            if packed is not None:
                present = ((packed[oracle//8] >> (oracle%8).astype(np.uint8)) & 1).astype(bool)
                global_missing = oracle[~present]
            result['row_groups_read'] += 1
            result['records'] += len(geometries)
            for tile in set(tiles):
                counts[tile] += sum(bool(selected[i]) for i,value in enumerate(tiles) if value == tile)
            result['subset_missing_cells'] += len(missing)
            result['subset_extra_cells'] += len(extra)
            result['global_missing_cells'] += len(global_missing)
            if (len(missing) or len(extra) or len(global_missing)) and len(result['failures']) < 40:
                result['failures'].append({'row_group':group,'source_tiles':sorted(set(tiles)),
                    'missing_examples':missing[:16].tolist(),'extra_examples':extra[:16].tolist(),
                    'global_missing_examples':global_missing[:16].tolist()})
            if result['row_groups_read'] % 100 == 0:
                print(json.dumps({key:result[key] for key in ('row_groups_read','records','subset_missing_cells','subset_extra_cells','global_missing_cells')}),flush=True)
        if counts != expected:
            raise ValueError('source control counts differ from frozen manifest selection')
        result['records_by_tile'] = counts
        if packed is not None:
            result['finest_mask_sha256'] = sha256(packed_mask_path)
        result['status'] = 'passed' if not any(result[key] for key in ('subset_missing_cells','subset_extra_cells','global_missing_cells')) else 'failed'
    except Exception as exc:
        result['status'] = 'failed'
        result['error'] = f'{type(exc).__name__}: {exc}'
        with report.open('x') as stream:
            stream.write(json.dumps(result,indent=2,sort_keys=True) + '\n')
        raise
    with report.open('x') as stream:
        stream.write(json.dumps(result,indent=2,sort_keys=True) + '\n')
    if result['status'] != 'passed':
        raise ValueError('independent source occupancy oracle failed; see immutable receipt')
    return result


if __name__ == '__main__':
    import argparse
    import importlib.util
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['source','archive'])
    parser.add_argument('--criteria',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--mask',type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--source-manifest',type=Path)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--production-module',type=Path,default=Path(__file__).with_name('build_overview.py'))
    args = parser.parse_args()
    criteria = json.loads(args.criteria.read_text())
    if args.mode == 'source':
        if args.source is None or args.source_manifest is None:
            parser.error('source mode requires --source and --source-manifest')
        spec = importlib.util.spec_from_file_location('grwl_production_overview',args.production_module)
        production = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(production)
        result = validate_source_subset(args.source,args.source_manifest,criteria,production,args.report,args.mask)
    else:
        if args.archive is None or args.mask is None:
            parser.error('archive mode requires --archive and --mask')
        result = validate_archive(args.archive,args.mask,args.report,criteria)
    print(json.dumps({'status':result['status']}))
