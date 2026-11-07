#!/usr/bin/env python3
"""Build a detail-only GRWL PMTiles derivative without joining raw observations."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import pyarrow.parquet as pq
import shapely

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'research/grwl-raw-release-20261102/display-policy.json'
CRITERIA = ROOT / 'research/grwl-raw-release-20261102/criteria.json'
LAYER = 'grwl_raw'
BBOX = ('xmin', 'ymin', 'xmax', 'ymax')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wrap = load_module('grwl_display_wrap', ROOT / 'datasets/grwl/build_display.py')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def descriptor(path):
    return {'size_bytes': path.stat().st_size, 'sha256': sha256(path)}


def guard(task_root, criteria, start=False):
    limits = criteria['resources']
    free = shutil.disk_usage(task_root).free
    minimum = limits['native_start_free_bytes'] if start else limits['native_stop_free_bytes']
    used = sum(p.stat().st_size for p in task_root.rglob('*') if p.is_file())
    if free < minimum:
        raise RuntimeError(f'Free bytes {free} below required {minimum}')
    if used > limits['task_storage_ceiling_bytes']:
        raise RuntimeError(f'Task bytes {used} exceed ceiling {limits["task_storage_ceiling_bytes"]}')
    return {'free_bytes': free, 'task_bytes': used}


def display_feature(row):
    """Separate source records and parts survive; only dateline display cuts apply."""
    geometry = shapely.from_wkb(row['geometry'])
    # Avoid a Python vertex walk for the overwhelmingly common noncrossing case.
    if row['bbox']['xmax'] - row['bbox']['xmin'] > 180:
        geometry = wrap.split_dateline(geometry)
    props = {'width_valid': row['width_valid']}
    if row['width_m'] is not None:
        props['width_m'] = row['width_m']
    props.update({'_src_' + k: row['bbox'][k] for k in BBOX})
    return {'type': 'Feature', 'id': row['feature_id'], 'properties': props,
            'geometry': json.loads(shapely.to_geojson(geometry))}


def iter_feature_lines(batch):
    """Encode a source Arrow batch with vectorized WKB decoding/GeoJSON serialization.

    `display_feature` remains the scalar reference. Geometry JSON is inserted as
    raw compact JSON, avoiding a Python JSON parse/serialize cycle for each row.
    Dateline candidates still use the same scalar splitter and only those rows
    leave the vectorized geometry path.
    """
    index = batch.schema.get_field_index
    feature_ids = batch.column(index('feature_id')).to_pylist()
    widths = batch.column(index('width_m')).to_pylist()
    width_valid = batch.column(index('width_valid')).to_pylist()
    bbox = batch.column(index('bbox'))
    bounds = {name: bbox.field(name).to_pylist() for name in BBOX}
    geometries = shapely.from_wkb(batch.column(index('geometry')).to_pylist())
    crossing = [i for i, (xmin, xmax) in enumerate(zip(bounds['xmin'], bounds['xmax'], strict=True))
                if xmax - xmin > 180]
    for i in crossing:
        geometries[i] = wrap.split_dateline(geometries[i])
    geometry_json = shapely.to_geojson(geometries)

    for i, (feature_id, width, valid) in enumerate(zip(feature_ids, widths, width_valid, strict=True)):
        props = {'width_valid': valid}
        if width is not None:
            props['width_m'] = width
        props.update({'_src_' + key: bounds[key][i] for key in BBOX})
        feature_prefix = json.dumps({'type': 'Feature', 'id': feature_id, 'properties': props},
                                    separators=(',', ':'), allow_nan=False)
        yield (feature_prefix[:-1] + ',"geometry":' + geometry_json[i] + '}\n').encode()


def build(source, source_manifest, fidelity, output, task_root, criteria_path=CRITERIA):
    if output.exists():
        raise FileExistsError('Refusing to overwrite display output')
    output.resolve().relative_to(task_root.resolve())
    source.resolve().relative_to(task_root.resolve())
    criteria = json.loads(criteria_path.read_text())
    policy = json.loads(POLICY.read_text())
    source_meta = json.loads(source_manifest.read_text())
    verified = json.loads(fidelity.read_text())
    source_hash = sha256(source)
    if source_hash != source_meta['parquet_sha256']:
        raise ValueError('Source Parquet differs from its immutable manifest')
    if (verified['status'] != 'passed' or verified['manifest_sha256'] != sha256(source_manifest)
            or verified.get('parquet_sha256') != source_hash):
        raise ValueError('Matching independent source fidelity must pass before display building')
    if verified['progress']['source_rows'] != source_meta['rows']:
        raise ValueError('Source fidelity count differs from conversion manifest')
    task_root.mkdir(parents=True, exist_ok=True)
    resource_start = guard(task_root, criteria, start=True)
    packages = {name: importlib.metadata.version(name) for name in ('pyarrow', 'shapely', 'numpy', 'pmtiles', 'pyproj', 'mapbox-vector-tile')}
    if packages != {'pyarrow':'23.0.1','shapely':'2.1.2','numpy':'2.5.4','pmtiles':'3.8.1','pyproj':'3.8.0','mapbox-vector-tile':'2.2.0'}:
        raise ValueError('Use scripts/display_tools locked environment')
    lock = Path(sys.prefix).resolve().parent / 'uv.lock'
    if sha256(lock) != sha256(ROOT / 'scripts/display_tools/uv.lock'):
        raise ValueError('Active Python lock differs from committed display lock')
    tip = Path(shutil.which('tippecanoe') or '')
    pin = json.loads((ROOT / 'datasets/grwl/tippecanoe.lock.json').read_text())
    if not tip.is_file() or sha256(tip) != pin['binary_sha256']:
        raise ValueError('Tippecanoe does not match the pinned executable')
    version = subprocess.run([str(tip), '--version'], capture_output=True, text=True, check=True)
    if (version.stdout + version.stderr).strip() != 'tippecanoe v' + pin['version']:
        raise ValueError('Tippecanoe version differs from lock')
    # A shared lock coordinates this production builder's concurrent invocations.
    # Existing unrelated native processes are checked separately before launch.
    with (task_root / '.native-build.lock').open('a') as reservation:
        fcntl.flock(reservation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.run(['pgrep', '-x', 'tippecanoe'], capture_output=True, text=True)
        if active.returncode == 0:
            raise RuntimeError('Another Tippecanoe build is active; retry when it has completed')
        if active.returncode != 1:
            raise RuntimeError('Could not inspect the shared native build slot')
        output.mkdir(parents=True)
        for directory in ('assets', 'styles', 'reports', 'workflow', '.scratch'):
            (output / directory).mkdir()
        write_json(output / 'partial.json', {'status':'building', 'usable_release':False})
        for original, filename in ((Path(__file__), 'build_display.py.txt'),
                (ROOT / 'datasets/grwl/build_display.py', 'dateline-helper.py.txt'),
                (lock, 'uv.lock'), (POLICY, 'display-policy.json'),
                (criteria_path, 'criteria.json'), (source_manifest, 'source-manifest.json'),
                (fidelity, 'source-fidelity.json'),
                (ROOT / 'datasets/grwl/tippecanoe.lock.json', 'tippecanoe.lock.json')):
            shutil.copyfile(original, output / 'workflow' / filename)
        archive = output / 'assets/grwl-raw.pmtiles'
        # Tippecanoe records argv in PMTiles metadata. Use fixed relative paths
        # and argv[0], while executing the exact pinned binary, so machine and
        # output-directory names cannot alter the generated archive.
        argv = ['tippecanoe', '--quiet', '--output', 'assets/grwl-raw.pmtiles', '--layer', LAYER,
            '--name', 'GRWL raw width observations',
            '--description', 'Detailed raw observations at zoom 8 and above. GeoParquet retains the exact source records.',
            '--attribution', 'Allen and Pavelsky (2018), GRWL raw vectors V01.01; CC BY 4.0',
            '--minimum-zoom', str(policy['min_zoom']), '--maximum-zoom', str(policy['max_zoom']),
            '--base-zoom', str(policy['max_zoom']), '--full-detail', '12', '--low-detail', '12', '--minimum-detail', '12',
            '--simplification', '1', '--no-feature-limit', '--no-tile-size-limit',
            '--temporary-directory', '.scratch', '/dev/stdin']
        portable = [arg.replace(str(output), '<OUTPUT>') for arg in argv]
        write_json(output / 'reports/input-provenance.json', {
            'schema_version':1, 'source':descriptor(source), 'source_manifest':descriptor(source_manifest),
            'source_fidelity':descriptor(fidelity), 'policy':descriptor(POLICY), 'criteria':descriptor(criteria_path),
            'builder':descriptor(Path(__file__)), 'dateline_helper':descriptor(ROOT / 'datasets/grwl/build_display.py'),
            'environment_lock':descriptor(lock), 'python':platform.python_version(), 'python_packages':packages,
            'tippecanoe':descriptor(tip), 'tippecanoe_version':pin['version'], 'threads':2,
            'command':portable, 'working_directory':'<OUTPUT>', 'resource_start':resource_start,
            'scope':'all records in the supplied manifest; regional pilot does not imply global completion'})
        process = None
        rows = 0
        started = time.monotonic()
        try:
            with (output / 'reports/tippecanoe.stderr.txt').open('w') as log:
                process = subprocess.Popen(argv, executable=str(tip), cwd=output.resolve(),
                    stdin=subprocess.PIPE, stdout=log, stderr=log,
                    env={**os.environ, 'TIPPECANOE_MAX_THREADS':'2'})
                columns = ['feature_id','width_m','width_valid','bbox','geometry']
                for batch in pq.ParquetFile(source).iter_batches(batch_size=8192, columns=columns, use_threads=False):
                    process.stdin.write(b''.join(iter_feature_lines(batch)))
                    rows += batch.num_rows
                    guard(task_root, criteria)
                    if rows // 1000000 != (rows - batch.num_rows) // 1000000:
                        print(json.dumps({'source_rows_streamed':rows, 'elapsed_seconds':round(time.monotonic()-started)}), flush=True)
                process.stdin.close()
                while process.poll() is None:
                    guard(task_root, criteria)
                    time.sleep(1)
                if process.returncode != 0:
                    raise RuntimeError('Tippecanoe failed; see retained stderr')
            if rows != source_meta['rows']:
                raise ValueError('Streamed row count differs from source manifest')
            verify = subprocess.run(['pmtiles','verify',str(archive)], capture_output=True, text=True)
            write_json(output / 'reports/pmtiles-verify.json', {'returncode':verify.returncode,'stdout':verify.stdout,'stderr':verify.stderr})
            if verify.returncode:
                raise ValueError('PMTiles container verification failed')
            style = {'version':8,'sources':{'data':{'type':'vector','url':'../assets/grwl-raw.pmtiles'}},
                     'layers':[{'id':'raw-width','type':'line','source':'data','source-layer':LAYER,
                                'paint':{'line-color':'#216d85','line-width':['case',['get','width_valid'],['interpolate',['linear'],['get','width_m'],1,1.1,50,1.6,200,2.7,1000,6.2],0.9]}}]}
            write_json(output / 'styles/width.json', style)
            manifest = {'schema_version':1,'dataset_id':'grwl-raw','status':'provisional',
                'display_release':output.name,'source_rows':rows,'source_tiles':len(source_meta['tiles']),
                'assets':[{'id':'grwl-raw-display','title':'GRWL raw width observations','path':'assets/grwl-raw.pmtiles',
                    **descriptor(archive),'source_layer':LAYER,'geometry_type':'line',
                    'min_zoom':policy['min_zoom'],'max_zoom':policy['max_zoom'],'id_field':'feature_id','id_encoding':'mvt_feature_id',
                    'attribute_fields':['width_m','width_valid']+['_src_'+k for k in BBOX],
                    'source_asset':{'path':source.name,**descriptor(source)},'style_path':'styles/width.json'}],
                'elapsed_seconds':round(time.monotonic()-started,3),'resource_end':guard(task_root,criteria)}
            write_json(output / 'manifest.json', manifest)
            (output / 'partial.json').unlink()
            shutil.rmtree(output / '.scratch')
            print(json.dumps({'status':'provisional','rows':rows,'archive':descriptor(archive)}), flush=True)
            return manifest
        except BaseException as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            write_json(output / 'failure.json', {'status':'failed','usable_release':False,
                'error':f'{type(exc).__name__}: {exc}','rows_streamed':rows})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source','source-manifest','fidelity','output','task-root'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--criteria', type=Path, default=CRITERIA)
    args = parser.parse_args()
    build(args.source,args.source_manifest,args.fidelity,args.output,args.task_root,args.criteria)


if __name__ == '__main__':
    main()
