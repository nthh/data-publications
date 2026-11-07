#!/usr/bin/env python3
"""Pinned native repack; provisional output requires compare_detail.py.

Upstream tile-join.cpp writes SQLite at the output path, then
pmtiles_file.cpp writes a sibling tile stream before replacing the SQLite
with final PMTiles. All named temporaries stay inside the output directory.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / 'research/grwl-multiscale-20261103/criteria.json'
BINARY = Path('/opt/homebrew/bin/tile-join')
BINARY_SHA256 = 'da56cb1a2ddf59b2f03798b5314db665dad87bc03cab6f86a03e630e420173fa'
UPSTREAM = '68ab8dcc229f95b8b25877697d5e8d66783af503'
DROP = ('_src_xmin', '_src_ymin', '_src_xmax', '_src_ymax')
GIB = 1024 ** 3


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def descriptor(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': sha256(path)}


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def resource_check(output, start_free=None, *, start=False, maximum_gib=24):
    free = shutil.disk_usage(output if output.exists() else output.parent).free
    minimum = (40 if start else 15) * GIB
    named = sum(p.stat().st_size for p in output.rglob('*') if p.is_file() and not p.is_symlink()) if output.exists() else 0
    # Volume delta also bounds unlinked SQLite temporaries, conservatively
    # counting simultaneous allocations from other users of the same volume.
    allocation = max(0, start_free - free) if start_free is not None else 0
    if free < minimum:
        raise RuntimeError(f'Free space {free} below {minimum}')
    if max(named, allocation) > maximum_gib * GIB:
        raise RuntimeError('New artifact/temporary storage ceiling exceeded')
    return {'free_bytes': free, 'named_output_bytes': named, 'volume_allocation_delta': allocation}


def command(detail, overview=None):
    argv = ['tile-join', '--no-tile-size-limit', '-o', 'assets/grwl-raw.pmtiles']
    for key in DROP:
        argv.extend(['-x', key])
    argv.append('inputs/detail.pmtiles')
    if overview is not None:
        argv.append('inputs/overview.pmtiles')
    return argv


def preflight(detail, output, task_root, source_sha256, overview=None, overview_sha256=None):
    if output.exists():
        raise FileExistsError('Refusing to overwrite immutable candidate directory')
    output.resolve().relative_to(task_root.resolve())
    if source_sha256 != sha256(detail):
        raise ValueError('Detail archive differs from supplied sealed checksum')
    if overview is not None and (not overview_sha256 or sha256(overview) != overview_sha256):
        raise ValueError('Overview archive differs from supplied checksum')
    if sha256(BINARY) != BINARY_SHA256:
        raise ValueError('tile-join binary differs from pinned executable')
    # tile-join lacks --version; its exact binary hash binds version 2.79.0.
    lock = Path(sys.prefix).resolve().parent / 'uv.lock'
    if sha256(lock) != sha256(ROOT / 'scripts/display_tools/uv.lock'):
        raise ValueError('Use committed display_tools locked Python environment')
    return lock


def build(detail, output, task_root, source_sha256, *, overview=None,
          overview_sha256=None, criteria_path=CRITERIA, maximum_gib=24, native_lock=None):
    detail, output, task_root = map(Path, (detail, output, task_root))
    if maximum_gib <= 0 or maximum_gib > 24:
        raise ValueError('maximum_gib must be positive and at most frozen 24 GiB')
    task_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = preflight(detail, output, task_root, source_sha256, overview, overview_sha256)
    native_lock = Path(native_lock) if native_lock else task_root / '.native-build.lock'
    with native_lock.open('a') as reservation:
        fcntl.flock(reservation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ('tippecanoe', 'tile-join'):
            active = subprocess.run(['pgrep', '-x', name], capture_output=True, text=True)
            if active.returncode != 1:
                raise RuntimeError(f'Native process active or inspection failed: {name}')
        initial = resource_check(output, start=True, maximum_gib=maximum_gib)
        output.mkdir()
        for name in ('assets', 'reports', 'workflow', '.scratch', 'inputs'):
            (output / name).mkdir()
        (output / 'inputs/detail.pmtiles').symlink_to(detail.resolve())
        if overview:
            (output / 'inputs/overview.pmtiles').symlink_to(Path(overview).resolve())
        argv = command(detail, overview)
        provenance = {'schema_version': 1, 'detail': descriptor(detail),
            'overview': descriptor(overview) if overview else None,
            'builder': descriptor(Path(__file__)), 'criteria': descriptor(criteria_path),
            'environment_lock': descriptor(lock), 'python': platform.python_version(),
            'packages': {n: importlib.metadata.version(n) for n in ('pmtiles', 'mapbox-vector-tile', 'protobuf')},
            'binary': descriptor(BINARY), 'version': '2.79.0', 'upstream_commit': UPSTREAM,
            'workers': 2, 'command': argv,
            'environment': {'TIPPECANOE_MAX_THREADS': '2', 'TMPDIR': '<OUTPUT>/.scratch',
                            'SQLITE_TMPDIR': '<OUTPUT>/.scratch', 'LC_ALL': 'C'},
            'resource_start': initial, 'maximum_new_artifacts_gib': maximum_gib,
            'native_lock': str(native_lock.resolve()),
            'remove_properties': list(DROP), 'status': 'provisional_requires_independent_comparison'}
        for src, name in ((Path(__file__), 'repack_detail.py.txt'), (lock, 'uv.lock'), (criteria_path, 'criteria.json')):
            shutil.copyfile(src, output / 'workflow' / name)
        write_json(output / 'reports/input-provenance.json', provenance)
        process = None
        started = time.monotonic()
        peak = {'named_output_bytes': 0, 'volume_allocation_delta': 0}
        try:
            scratch = str((output / '.scratch').resolve())
            with (output / 'reports/tile-join.stderr.txt').open('x') as log:
                process = subprocess.Popen(argv, executable=str(BINARY), cwd=output.resolve(),
                    stdout=log, stderr=log, env={**os.environ, 'TIPPECANOE_MAX_THREADS': '2',
                    'TMPDIR': scratch, 'SQLITE_TMPDIR': scratch, 'LC_ALL': 'C'})
                while True:
                    state = resource_check(output, initial['free_bytes'], maximum_gib=maximum_gib)
                    for name in peak:
                        peak[name] = max(peak[name], state[name])
                    if process.poll() is not None:
                        break
                    time.sleep(1)
            if process.returncode:
                raise RuntimeError(f'tile-join exited {process.returncode}; inspect retained stderr')
            if sha256(detail) != source_sha256 or (overview and sha256(overview) != overview_sha256):
                raise ValueError('Input archive changed during native conversion')
            report = {'schema_version': 1, 'status': 'provisional',
                'archive': descriptor(output / 'assets/grwl-raw.pmtiles'),
                'input_provenance': descriptor(output / 'reports/input-provenance.json'),
                'elapsed_seconds': round(time.monotonic() - started, 3),
                'resource_end': state, 'resource_peak_sampled': peak}
            write_json(output / 'manifest.json', report)
            return report
        except BaseException as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            write_json(output / 'failure.json', {'status': 'failed', 'usable_release': False,
                'error': f'{type(exc).__name__}: {exc}', 'elapsed_seconds': round(time.monotonic() - started, 3)})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('detail', 'output', 'task-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--overview', type=Path)
    parser.add_argument('--overview-sha256')
    parser.add_argument('--criteria', type=Path, default=CRITERIA)
    parser.add_argument('--maximum-gib', type=float, default=24)
    parser.add_argument('--native-lock', type=Path,
        help='Shared native slot; pass grwl-raw/.native-build.lock when task-root differs')
    args = parser.parse_args()
    print(json.dumps(build(args.detail, args.output, args.task_root, args.source_sha256,
        overview=args.overview, overview_sha256=args.overview_sha256,
        criteria_path=args.criteria, maximum_gib=args.maximum_gib, native_lock=args.native_lock), sort_keys=True))


if __name__ == '__main__':
    main()
