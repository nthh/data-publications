#!/usr/bin/env python3
"""Freeze source-only GRWL holdout anchors, then extract immutable inputs.

Run `freeze` and commit this selector plus its JSON before running `extract`.
The detail sample is geographic tiles containing all features in those tiles;
it is not a filter to only the eight heldout source identifiers.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import mmap
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely
from pmtiles.reader import Reader
from pmtiles.tile import TileType, zxy_to_tileid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CRITERIA = HERE / 'criteria.json'
PARQUET_SHA256 = 'd37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb'
DETAIL_SHA256 = 'a1a7787c7ba28ffc271819bddc54339f9bc741aa9ed44ca619d93e809cbad4f5'
HELDOUT = ('NH11', 'NA18', 'NA32', 'NI37', 'NA47', 'SA49', 'NR01', 'SB54')
DEFAULT_SOURCE = Path('/Users/nathan/projects/data-publications/.local/grwl-raw/global-rebuild-v1/grwl-raw.parquet')
DEFAULT_DETAIL = Path('/Users/nathan/projects/data-publications/.local/grwl-raw/global-display-v1/assets/grwl-raw.pmtiles')
DEFAULT_OUTPUT = Path('/Users/nathan/projects/data-publications/.local/grwl-multiscale/heldout-inputs-r1')
GIB = 1024 ** 3


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def descriptor(path):
    return {'path': str(Path(path).resolve()), 'bytes': Path(path).stat().st_size, 'sha256': sha256(path)}


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def selected_groups(parquet, tiles=HELDOUT):
    index = parquet.schema_arrow.get_field_index('source_tile')
    if index < 0:
        raise ValueError('Missing source_tile')
    result = []
    for index_rg in range(parquet.num_row_groups):
        stats = parquet.metadata.row_group(index_rg).column(index).statistics
        if stats is None or not stats.has_min_max or stats.null_count:
            raise ValueError('Every source_tile row group needs nonnull min/max statistics')
        if any(stats.min <= tile <= stats.max for tile in tiles):
            result.append(index_rg)
    return result


def periodic_center(wkb):
    xy = shapely.get_coordinates(shapely.from_wkb(wkb))
    if not len(xy) or not np.isfinite(xy).all():
        raise ValueError('Anchor geometry must have finite coordinates')
    xs = xy[:, 0]
    if xs.max() - xs.min() > 180:
        xs = np.where(xs < 0, xs + 360, xs)
    lon = (float(xs.min() + xs.max()) / 2 + 180) % 360 - 180
    lat = float(xy[:, 1].min() + xy[:, 1].max()) / 2
    return lon, lat


def anchor_tile(lon, lat):
    limit = math.degrees(math.atan(math.sinh(math.pi)))
    lat = min(limit, max(-limit, lat))
    return 8, min(255, max(0, math.floor((lon + 180) / 360 * 256))), min(255, max(0, math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 256)))


def freeze(source, source_manifest, destination):
    if destination.exists():
        raise FileExistsError('Refusing to overwrite frozen source-only selection')
    criteria = json.loads(CRITERIA.read_text())
    if tuple(criteria['heldout_source_tiles']) != HELDOUT or criteria['source']['parquet_sha256'] != PARQUET_SHA256:
        raise ValueError('Frozen split or source pin changed')
    if sha256(source) != PARQUET_SHA256:
        raise ValueError('Source differs from sealed global GeoParquet')
    manifest = json.loads(source_manifest.read_text())
    if manifest['parquet_sha256'] != PARQUET_SHA256:
        raise ValueError('Global manifest is not bound to sealed GeoParquet')
    parquet = pq.ParquetFile(source)
    groups = selected_groups(parquet)
    # Find each tile's first row using source columns only. There is no PMTiles
    # access, extraction, or candidate measurement during the freeze phase.
    anchors = {}
    columns = ['source_tile', 'source_row', 'feature_id', 'bbox', 'geometry']
    for batch in parquet.iter_batches(batch_size=65536, row_groups=groups, columns=columns, use_threads=False):
        for tile in HELDOUT:
            rows = pa.Table.from_batches([batch]).filter(pc.equal(batch['source_tile'], tile))
            if not len(rows):
                continue
            source_rows = rows['source_row'].to_numpy()
            index = int(np.argmin(source_rows))
            row = rows.slice(index, 1).to_pylist()[0]
            if tile in anchors and row['source_row'] >= anchors[tile]['source_row']:
                continue
            lon, lat = periodic_center(row['geometry'])
            xyz = anchor_tile(lon, lat)
            xs = {xyz[1]}
            if xyz[1] in (0, 255) or tile == 'NR01':
                xs.update((0, 255))
            anchors[tile] = {'source_tile': tile, 'source_row': row['source_row'],
                'feature_id': row['feature_id'], 'bbox': row['bbox'],
                'geometry_wkb_sha256': hashlib.sha256(row['geometry']).hexdigest(),
                'center_lon_lat': [lon, lat], 'anchor_zxy': list(xyz),
                'included_z8_anchors': [[8, x, xyz[2]] for x in sorted(xs)]}
    if set(anchors) != set(HELDOUT):
        raise ValueError('Not every heldout tile has a source anchor')
    value = {'schema_version': 1, 'status': 'frozen_source_only_before_heldout_extraction_or_display_metrics',
        'source': descriptor(source), 'source_manifest': descriptor(source_manifest),
        'detail_source_sha256': DETAIL_SHA256, 'criteria': descriptor(CRITERIA),
        'selector': descriptor(Path(__file__)), 'heldout_source_tiles': list(HELDOUT),
        'anchor_rule': 'Minimum source_row within each fixed heldout source tile; midpoint of geometry coordinate bbox after mapping negative longitudes to 0..360 if longitude span exceeds180 degrees; wrap midpoint to [-180,180). Clamp latitude only for Web Mercator tile addressing.',
        'dateline_rule': 'Add both x0 and x255 at anchor y if anchor is on either edge, and always for NR01.',
        'detail_scope': 'Every existing sealed detail tile at z8..12 descended from any included z8 anchor, retaining all layers/features/bytes. Nonexistent tile coordinates stay absent. Geographic sample includes observations from other source tiles.',
        'source_scope': 'All rows from the eight heldout source_tile values, preserving source order, full Arrow schema/metadata, typed attributes and WKB bytes; subset-derived, not a global or newly independent source release.',
        'input_limits': {'maximum_heldout_inputs_bytes': GIB, 'maximum_pilot_artifacts_bytes': 4 * GIB},
        'anchors': [anchors[tile] for tile in HELDOUT]}
    write_json(destination, value)
    return value


def selected_detail(xyz, selection):
    z, x, y = xyz
    if not 8 <= z <= 12:
        return False
    shift = z - 8
    return any((x >> shift, y >> shift) == (anchor[1], anchor[2])
        for row in selection['anchors'] for anchor in row['included_z8_anchors'])


def requested_detail(selection):
    """Finite exact address set; never scan/copy unrelated global tile bytes."""
    result = set()
    for row in selection['anchors']:
        for _, x, y in row['included_z8_anchors']:
            for z in range(8, 13):
                side = 1 << (z - 8)
                result.update((z, xx, yy) for xx in range(x * side, (x + 1) * side)
                              for yy in range(y * side, (y + 1) * side))
    return sorted(result, key=lambda xyz: zxy_to_tileid(*xyz))


def guard(output, pilot_root, *, start=False):
    free = shutil.disk_usage(pilot_root).free
    heldout_bytes = sum(p.stat().st_size for p in output.rglob('*') if p.is_file() and not p.is_symlink()) if output.exists() else 0
    pilot_bytes = sum(p.stat().st_size for p in pilot_root.rglob('*') if p.is_file() and not p.is_symlink() and 'global' not in p.relative_to(pilot_root).parts[0])
    if free < (40 if start else 15) * GIB or heldout_bytes > GIB or pilot_bytes > 4 * GIB:
        raise RuntimeError(f'Heldout resource ceiling/floor exceeded: {free=}, {heldout_bytes=}, {pilot_bytes=}')
    return {'free_bytes': free, 'heldout_bytes': heldout_bytes, 'pilot_artifacts_bytes': pilot_bytes}


def require_committed(selection_path):
    for path in (Path(__file__), selection_path):
        relative = str(path.resolve().relative_to(ROOT))
        result = subprocess.run(['git', 'ls-files', '--error-unmatch', relative], cwd=ROOT, capture_output=True)
        diff = subprocess.run(['git', 'diff', 'HEAD', '--', relative], cwd=ROOT, capture_output=True)
        if result.returncode or diff.returncode or diff.stdout:
            raise ValueError('Commit selector and frozen selection before extraction')


def extract(source, source_manifest, detail, selection_path, output, pilot_root):
    if output.exists():
        raise FileExistsError('Refusing to overwrite immutable heldout inputs')
    output.resolve().relative_to(pilot_root.resolve())
    require_committed(selection_path)
    selection = json.loads(selection_path.read_text())
    if selection['selector']['sha256'] != sha256(Path(__file__)) or selection['criteria']['sha256'] != sha256(CRITERIA):
        raise ValueError('Selector or criteria changed after source-only freeze')
    if selection['source']['sha256'] != PARQUET_SHA256 or sha256(source) != PARQUET_SHA256 or sha256(detail) != DETAIL_SHA256:
        raise ValueError('Sealed source checksum differs')
    if selection['source_manifest']['sha256'] != sha256(source_manifest):
        raise ValueError('Source manifest changed after freeze')
    active_lock = Path(sys.prefix).resolve().parent / 'uv.lock'
    if sha256(active_lock) != sha256(ROOT / 'scripts/display_tools/uv.lock'):
        raise ValueError('Use committed display_tools environment')
    pilot_root.mkdir(parents=True, exist_ok=True)
    resource_start = guard(output, pilot_root, start=True)
    output.mkdir()
    (output / '.scratch').mkdir()
    # Writer's temporary tile stream must be accounted within the heldout cap.
    tempfile.tempdir = str((output / '.scratch').resolve())
    source_meta = json.loads(source_manifest.read_text())
    parquet = pq.ParquetFile(source)
    groups = selected_groups(parquet)
    counts = {tile: 0 for tile in HELDOUT}
    rows = 0
    try:
        with pq.ParquetWriter(output / 'source.parquet', parquet.schema_arrow, compression='zstd', write_statistics=True) as writer:
            for batch in parquet.iter_batches(batch_size=65536, row_groups=groups, use_threads=False):
                table = pa.Table.from_batches([batch])
                selected = table.filter(pc.is_in(table['source_tile'], value_set=pa.array(HELDOUT)))
                if not len(selected):
                    continue
                if not selected.schema.equals(parquet.schema_arrow, check_metadata=True):
                    raise ValueError('Subset Arrow schema/metadata changed')
                writer.write_table(selected)
                rows += len(selected)
                for tile in HELDOUT:
                    counts[tile] += int(pc.sum(pc.cast(pc.equal(selected['source_tile'], tile), pa.int64())).as_py() or 0)
                guard(output, pilot_root)
        original_tiles = [tile for tile in source_meta['tiles'] if tile['tile'] in HELDOUT]
        if counts != {tile['tile']: tile['records'] for tile in original_tiles}:
            raise ValueError('Subset record counts disagree with original source manifest')
        manifest = {key: source_meta[key] for key in ('schema_version', 'source_product', 'archive', 'geometry', 'feature_id', 'width_valid', 'numeric_schema')}
        manifest.update({'status': 'subset_derived_heldout_input', 'usable_release': False,
            'parquet_sha256': sha256(output / 'source.parquet'), 'rows': rows,
            'parts': sum(tile['parts'] for tile in original_tiles), 'tiles': original_tiles,
            'subset_of': selection['source'], 'original_manifest': selection['source_manifest'],
            'selection': descriptor(selection_path), 'row_order': 'Original global Parquet row-group and row order; filter source_tile membership only.'})
        write_json(output / 'source-manifest.json', manifest)
        spec = importlib.util.spec_from_file_location('heldout_overview_writer', ROOT / 'datasets/grwl-raw/build_overview.py')
        overview = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(overview)
        selected_tiles = []
        with detail.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
            get = lambda offset, length: mapping[offset:offset + length]
            reader = Reader(get)
            header, metadata = reader.header(), reader.metadata()
            if header['tile_type'] != TileType.MVT:
                raise ValueError('Sealed detail archive is not MVT')
            with (output / 'detail.pmtiles').open('xb') as dest:
                writer = overview.ExactWriter(dest)
                for xyz in requested_detail(selection):
                    data = reader.get(*xyz)
                    if data is not None:
                        writer.write_tile(zxy_to_tileid(*xyz), data)
                        selected_tiles.append(list(xyz))
                        guard(output, pilot_root)
                if not selected_tiles:
                    raise ValueError('Frozen detail scope contains no tiles')
                writer.finalize(dict(header), metadata)
        write_json(output / 'detail-scope.json', {'source': descriptor(detail), 'selection': descriptor(selection_path),
            'scope': selection['detail_scope'], 'tiles': selected_tiles,
            'archive': descriptor(output / 'detail.pmtiles'), 'metadata_policy': 'Retained sealed source metadata and layer identifiers unchanged; subset scope in this sidecar.'})
        report = {'status': 'prepared_subset_inputs_not_candidate_benchmark', 'selector': descriptor(Path(__file__)),
            'selection': descriptor(selection_path), 'environment_lock': descriptor(active_lock),
            'source_rows': rows, 'source_counts': counts, 'detail_tiles': len(selected_tiles),
            'artifacts': {name: descriptor(output / name) for name in ('source.parquet', 'source-manifest.json', 'detail.pmtiles', 'detail-scope.json')},
            'resources_start': resource_start, 'resources_end': guard(output, pilot_root)}
        write_json(output / 'report.json', report)
        return report
    except BaseException as exc:
        write_json(output / 'failure.json', {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}', 'rows': rows})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'extract'))
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--detail', type=Path, default=DEFAULT_DETAIL)
    parser.add_argument('--selection', type=Path, default=HERE / 'heldout-selection.json')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--pilot-root', type=Path, default=DEFAULT_OUTPUT.parent)
    args = parser.parse_args()
    manifest = args.source_manifest or args.source.parent / 'manifest.json'
    if args.command == 'freeze':
        value = freeze(args.source, manifest, args.selection)
    else:
        value = extract(args.source, manifest, args.detail, args.selection, args.output, args.pilot_root)
    print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    main()
