#!/usr/bin/env python3
"""Build/finalize a GRWL display-only dateline correction from pinned GeoParquet."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

import pyarrow.parquet as pq
import shapely

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REL = 'grwl/summary-v01.02-local-r1/grwl/grwl-summary-v0102.parquet'
SOURCE_SHA = '82ac4eeac2168b1aad6e5c9ae53c0c228ffcc7c8cd3f8d795493d939e626fa9c'
ATTRS = ['OBJECTID', 'ID', 'width_min_', 'width_med_', 'width_mean', 'width_max_',
         'width_sd_m', 'lakeFlag', 'nSegPx', 'Shape_Leng']
BBOX_ATTRS = ['_src_xmin', '_src_ymin', '_src_xmax', '_src_ymax']
ATTRIBUTION = 'Allen and Pavelsky (2018), GRWL summary V01.02; CC BY 4.0'
CRITERIA = ROOT / 'research/grwl-straight-segments-20261102/correction-criteria-r2.json'


def split_dateline(geometry):
    """Split display-only line parts at the dateline in projected segment space.

    The source WKB is never mutated. Each input part is independent; a boundary
    crossing ends at one world edge and restarts at the other. Noncrossing input
    vertices retain their exact coordinates.
    """
    if geometry.geom_type not in ('LineString', 'MultiLineString'):
        raise ValueError('GRWL display requires line geometry')
    lines = [geometry] if geometry.geom_type == 'LineString' else geometry.geoms
    output = []
    for line in lines:
        coords = list(line.coords)
        if len(coords) < 2:
            raise ValueError('Line has fewer than two source vertices')
        current = [coords[0]]
        for a, b in zip(coords, coords[1:]):
            delta = b[0] - a[0]
            if abs(delta) <= 180:
                current.append(b)
                continue
            end_x = b[0] - 360 if delta > 180 else b[0] + 360
            edge = -180.0 if delta > 180 else 180.0
            if end_x == a[0]:
                # +180 and -180 name the same meridian. Retain any vertical
                # segment before continuing from the equivalent opposite edge.
                latitude = b[1]
            else:
                fraction = (edge - a[0]) / (end_x - a[0])
                if not 0 <= fraction <= 1:
                    raise ValueError('Source dateline crossing is outside the geographic domain')
                y0, y1 = (math.asinh(math.tan(math.radians(point[1]))) for point in (a, b))
                latitude = math.degrees(math.atan(math.sinh(y0 + fraction * (y1 - y0))))
            stop, start = (edge, latitude), (-edge, latitude)
            if current[-1] != stop:
                current.append(stop)
            if len(current) >= 2:
                output.append(current)
            current = [start]
            if start != b:
                current.append(b)
        if len(current) >= 2:
            output.append(current)
    return shapely.MultiLineString(output)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as src:
        for block in iter(lambda: src.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def descriptor(path):
    return {'size_bytes': path.stat().st_size, 'sha256': digest(path)}


def inventory(package):
    files = {}
    for path in sorted(package.rglob('*')):
        if path.is_symlink():
            raise ValueError('Package symlinks are forbidden')
        if path.is_file() and path != package / 'manifest.json':
            files[path.relative_to(package).as_posix()] = descriptor(path)
    return files


def guard(package, start=False):
    free = shutil.disk_usage(package.parent).free
    minimum = (40 if start else 15) * 1024 ** 3
    if free < minimum:
        raise ValueError(f'Insufficient free disk: {free} bytes; require {minimum}')
    size = sum(p.stat().st_size for p in package.rglob('*') if p.is_file()) if package.exists() else 0
    if size > 1024 ** 3:
        raise ValueError('GRWL correction exceeded its 1 GiB extra disk budget')
    return {'free_bytes': free, 'package_bytes': size}


def build(data_root, output):
    source = data_root / SOURCE_REL
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite a display package')
    output.relative_to(data_root)
    if digest(source) != SOURCE_SHA:
        raise ValueError('Pinned GeoParquet source checksum differs')
    output.parent.mkdir(parents=True, exist_ok=True)
    resources = guard(output, start=True)
    tip = Path(shutil.which('tippecanoe') or '')
    lock = json.loads((ROOT / 'datasets/grwl/tippecanoe.lock.json').read_text())
    if not tip.is_file() or digest(tip) != lock['binary_sha256']:
        raise ValueError('Tippecanoe binary differs from the source release lock')
    version = subprocess.run([str(tip), '--version'], capture_output=True, text=True, check=True)
    if (version.stdout + version.stderr).strip() != 'tippecanoe v' + lock['version']:
        raise ValueError('Tippecanoe version differs from the lock')
    packages = {name: importlib.metadata.version(name) for name in ('pyarrow', 'shapely', 'numpy', 'pmtiles', 'pyproj', 'mapbox-vector-tile')}
    expected = {'pyarrow':'23.0.1', 'shapely':'2.1.2', 'numpy':'2.5.4', 'pmtiles':'3.8.1', 'pyproj':'3.8.0', 'mapbox-vector-tile':'2.2.0'}
    if packages != expected:
        raise ValueError('Use the locked scripts/display_tools Python environment')
    environment_lock = Path(sys.prefix).resolve().parent / 'uv.lock'
    if digest(environment_lock) != digest(ROOT / 'scripts/display_tools/uv.lock'):
        raise ValueError('Active environment lock differs from committed display lock')
    for name in ['assets', 'styles', 'reports', 'workflow']:
        (output / name).mkdir(parents=True, exist_ok=True)
    for src, name in [(Path(__file__), 'build_display.py.txt'), (environment_lock, 'uv.lock'),
                      (ROOT / 'datasets/grwl/tippecanoe.lock.json', 'tippecanoe.lock.json'),
                      (CRITERIA, 'correction-criteria.json')]:
        shutil.copyfile(src, output / 'workflow' / name)
    archive = output / 'assets/grwl.pmtiles'
    argv = ['--quiet', '--output', str(archive), '--layer', 'grwl', '--name', 'GRWL mean-width display',
            '--description', 'Display derivative with longitude wraparound; source geometry is unchanged.',
            '--attribution', ATTRIBUTION, '--minimum-zoom', '0', '--maximum-zoom', '10',
            '--simplification', '2', '--no-feature-limit', '--no-tile-size-limit',
            '--use-attribute-for-id', 'source_row', '--detect-longitude-wraparound',
            '--temporary-directory', str(output / '.scratch'), '/dev/stdin']
    portable = ['tippecanoe'] + [arg.replace(str(output), '<OUTPUT>') for arg in argv]
    provenance = {'schema_version':1, 'source_path':SOURCE_REL, 'source_sha256':SOURCE_SHA,
                  'source_size_bytes':source.stat().st_size, 'builder_sha256':digest(Path(__file__)),
                  'environment_lock_sha256':digest(environment_lock), 'python':platform.python_version(),
                  'python_packages':packages, 'platform':platform.platform(),
                  'tippecanoe_sha256':digest(tip), 'tippecanoe_version':(version.stdout + version.stderr).strip(),
                  'tippecanoe_threads':2, 'command':portable, 'resource_start':resources,
                  'source_geometry_handling':'Unchanged original SHP and source WKB; only display GeoJSON is split at the dateline.',
                  'display_geometry_handling':'Independent line parts split at +/-180 with Mercator-interpolated boundary vertices; noncrossing vertices unchanged.',
                  'numeric_display_handling':'Producer Decimal fields converted to float as in the original GRWL tiles; analytical decimals unchanged.'}
    write_json(output / 'reports/input-provenance.json', provenance)
    rows = 0
    with tempfile.TemporaryDirectory(prefix='native-', dir=output) as temporary:
        argv[argv.index(str(output / '.scratch'))] = temporary
        with (output / 'reports/tippecanoe.stderr.txt').open('w') as stderr:
            process = subprocess.Popen([str(tip), *argv], stdin=subprocess.PIPE, stdout=stderr, stderr=stderr,
                                       env={**os.environ, 'TIPPECANOE_MAX_THREADS':'2'})
            try:
                for batch in pq.ParquetFile(source).iter_batches(batch_size=512, use_threads=False):
                    for row in batch.to_pylist():
                        fid = row['source_row']
                        if fid != rows + 1:
                            raise ValueError('Unexpected source row order or identity')
                        props = {'source_row':fid, **{name:None if row[name] is None else float(row[name]) for name in ATTRS}}
                        props.update({'_src_' + key:value for key,value in row['bbox'].items()})
                        feature = {'type':'Feature', 'id':fid, 'properties':props,
                                   'geometry':json.loads(shapely.to_geojson(split_dateline(shapely.from_wkb(row['geometry']))))}
                        process.stdin.write(json.dumps(feature, separators=(',', ':'), allow_nan=False).encode() + b'\n')
                        rows += 1
                    guard(output)
                process.stdin.close()
                if process.wait() != 0:
                    raise ValueError('Tippecanoe failed; retained stderr and provisional files')
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
                raise
    if rows != 42077:
        raise ValueError('Incorrect source row count')
    style = json.loads((ROOT / 'datasets/grwl/styles/width-v1.json').read_text())
    style['sources']['data']['url'] = '../assets/grwl.pmtiles'
    style['metadata'].pop('data-publications:storage-path', None)
    style['metadata']['data-publications:display-geometry'] = 'Dateline crossings wrap locally; authoritative GeoParquet geometry is unchanged.'
    write_json(output / 'styles/grwl-width.json', style)
    asset = {'id':'grwl-display', 'title':'GRWL river network', 'path':'assets/grwl.pmtiles', **descriptor(archive),
             'source_layer':'grwl', 'geometry_type':'line', 'min_zoom':0, 'max_zoom':10, 'id_field':'source_row',
             'id_encoding':'mvt_feature_id', 'source_rows':rows, 'attribute_fields':ATTRS + BBOX_ATTRS,
             'source_asset':{'path':'grwl/grwl-summary-v0102.parquet', **descriptor(source)},
             'style_path':'styles/grwl-width.json'}
    (output / 'README.md').write_text('# GRWL display correction\n\n' + ATTRIBUTION + '\n\nProvisional display package; validation and finalization are required.\n')
    manifest = {'schema_version':1, 'dataset_id':'grwl', 'display_release':'display-v1',
                'analytic_release':'summary-v01.02-local-r1', 'status':'provisional',
                'attribution':ATTRIBUTION, 'assets':[asset], 'files':inventory(output)}
    write_json(output / 'manifest.json', manifest)
    print(json.dumps({'status':'provisional', 'source_rows':rows, 'archive':descriptor(archive)}))


def finalize(package, validation_path, browser_path):
    path = package / 'manifest.json'
    manifest = json.loads(path.read_text())
    if manifest['status'] != 'provisional' or manifest['dataset_id'] != 'grwl':
        raise ValueError('Only a provisional GRWL display can be finalized')
    if manifest['files'] != inventory(package):
        raise ValueError('Provisional inventory no longer matches package files')
    asset = manifest['assets'][0]
    validation = json.loads(validation_path.read_text())
    if validation.get('passed') is not True or validation.get('failures') != []:
        raise ValueError('Independent display validation did not pass')
    if validation.get('source_sha256') != SOURCE_SHA or validation.get('pmtiles_sha256') != asset['sha256']:
        raise ValueError('Independent validation source/archive identity differs')
    if validation.get('source_rows') != 42077 or validation.get('maxzoom_ids_accounted') != 42077:
        raise ValueError('Independent validation lacks full source-ID accounting')
    accounting, geometry = validation.get('accounting') or {}, validation.get('geometry') or {}
    crossings = validation.get('crossing_zoom_checks') or []
    frozen_path = ROOT / 'research/grwl-straight-segments-20261102/crossing-source-ids.json'
    if (validation.get('mode') != 'full' or accounting.get('passed') is not True
            or accounting.get('attribute_failure_count') != 0 or accounting.get('missing_ids') != []
            or len(accounting.get('numeric_fields', [])) != 10
            or len(accounting.get('source_bbox_fields', [])) != 4):
        raise ValueError('Complete independent ID and attribute accounting is required')
    if (geometry.get('passed') is not True or geometry.get('tolerance_metres') != 30.0
            or len(geometry.get('samples', [])) != 74
            or validation.get('upstream_edge_control', {}).get('passed') is not True):
        raise ValueError('Independent geometry and retained upstream edge controls are required')
    if (validation.get('crossing_source_ids') != [28938] or len(crossings) != 11
            or any(item.get('passed') is not True for item in crossings)
            or validation.get('crossing_freeze_sha256') != digest(frozen_path)):
        raise ValueError('Frozen antimeridian regression must pass at every zoom')
    validator = ROOT / 'datasets/grwl/validate_display_wrap.py'
    if validation.get('validator_sha256') != digest(validator):
        raise ValueError('Independent validator code identity differs')
    browser = json.loads(browser_path.read_text())
    cases = [case for case in browser.get('cases', []) if case.get('layer_id') == 'grwl-display']
    if browser.get('status') != 'passed' or {c['region'] for c in cases} != {'global', 'north_america', 'dateline'}:
        raise ValueError('GRWL global/regional/dateline browser checks must pass')
    if next(c for c in cases if c['region'] == 'dateline').get('inspected_source_id') != 28938:
        raise ValueError('Dateline browser case did not inspect source row28938')
    for case in cases:
        if case.get('status') != 'passed' or case.get('source_sha256') != asset['sha256']:
            raise ValueError('Browser did not inspect the exact corrected archive')
        if not case.get('all_attributes_note', '').startswith('All source attributes'):
            raise ValueError('Browser did not verify analytical attribute lookup')
        if 'width_mean' not in json.dumps(case.get('active_width_expression')):
            raise ValueError('Browser did not verify measured-width styling')
        if (case.get('decimal_width_matches') is not True
                or case.get('tile_mean_width') != case.get('analytic_mean_width')):
            raise ValueError('Browser did not verify Decimal source width against tile width')
        if case['region'] == 'dateline' and case.get('analytic_mean_width') != 97:
            raise ValueError('Dateline feature28938 must retain its measured97m mean width')
    verify = subprocess.run(['pmtiles', 'verify', str(package / asset['path'])], text=True, capture_output=True, check=True)
    write_json(package / 'reports/pmtiles-verify.json', {'command':['pmtiles','verify',asset['path']],
               'archive_sha256':asset['sha256'], 'executable_sha256':digest(Path(shutil.which('pmtiles'))),
               'exit_code':verify.returncode,'stdout':verify.stdout,'stderr':verify.stderr})
    shutil.copyfile(validation_path, package / 'reports/independent-validation.json')
    shutil.copyfile(browser_path, package / 'reports/browser-validation.json')
    shutil.copyfile(validator, package / 'workflow/validate_display_wrap.py.txt')
    shutil.copyfile(Path(__file__), package / 'workflow/finalize_display.py.txt')
    shutil.copyfile(ROOT / 'research/grwl-straight-segments-20261102/browser-controls.json', package / 'workflow/browser-controls.json')
    shutil.copyfile(frozen_path, package / 'workflow/crossing-source-ids.json')
    shutil.copyfile(ROOT / 'research/pmtiles-all-20261102/criteria.json', package / 'workflow/geometry-controls.json')
    (package / 'README.md').write_text('# GRWL display correction\n\n' + ATTRIBUTION + '\n\n'
        'Versioned PMTiles for the unchanged summary-v01.02-local-r1 analytical release. '
        'Explicit display-only dateline splitting prevents a 523 m dateline crossing in source row 28938 '
        'from rendering across the world. Source row 13164 retains its upstream 31.28 km straight segment. '
        'Use the original GeoParquet for exact geometry and all attributes.\n\n'
        'All source IDs and selected tile fields are checked against the source. Independent sampled '
        'geometry, antimeridian regressions, native archive verification and local browser reads are '
        'recorded in reports/. This package has not been uploaded or independently rebuilt twice.\n')
    manifest['files'] = inventory(package)
    manifest['status'] = 'prepared'
    temporary = path.with_suffix('.tmp')
    write_json(temporary, manifest)
    temporary.replace(path)
    print(json.dumps({'status':'prepared', 'manifest':descriptor(path)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    b = subs.add_parser('build'); b.add_argument('--data-root', type=Path, required=True); b.add_argument('--output', type=Path, required=True)
    f = subs.add_parser('finalize'); f.add_argument('--package', type=Path, required=True); f.add_argument('--validation', type=Path, required=True); f.add_argument('--browser', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'build':
        build(args.data_root.resolve(), args.output.resolve())
    else:
        finalize(args.package.resolve(), args.validation.resolve(), args.browser.resolve())


if __name__ == '__main__':
    main()
