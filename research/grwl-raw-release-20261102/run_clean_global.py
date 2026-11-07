#!/usr/bin/env python3
"""Run a full raw GRWL rebuild and retain observed Git/input/output evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args], text=True).strip()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def run(checkout, python, archive, output, receipt):
    # Keep the venv interpreter path: resolving its symlink would bypass the venv.
    python = python.expanduser().absolute()
    checkout, archive, output, receipt = [p.expanduser().resolve() for p in (checkout, archive, output, receipt)]
    started_path = receipt.with_name(receipt.stem + '.started.json')
    if output.exists() or receipt.exists() or started_path.exists():
        raise FileExistsError('Output and both receipt paths must be new')
    before = git(checkout, 'status', '--porcelain', '--untracked-files=normal')
    if before:
        raise RuntimeError('Rebuild checkout must be clean before execution')
    revision = git(checkout, 'rev-parse', 'HEAD')
    paths = {'builder_sha256': checkout/'datasets/grwl-raw/build_global.py',
             'converter_sha256': checkout/'datasets/grwl-raw/convert.py',
             'environment_lock_sha256': checkout/'scripts/display_tools/uv.lock'}
    pins = {key: sha(path) for key, path in paths.items()}
    command = [str(python), str(paths['builder_sha256']), '--archive', str(archive), '--output', str(output),
               '--criteria', str(checkout/'research/grwl-raw-release-20261102/global-criteria.json')]
    result = {'schema_version': 1, 'status': 'running', 'git_revision': revision,
              'working_tree_before': {'status': 'clean', 'observed': True, 'porcelain': before},
              'input_hashes': pins, 'runner_sha256': sha(Path(__file__)),
              'command': ['<LOCKED_PYTHON>', 'datasets/grwl-raw/build_global.py', '--archive', '<PINNED_ARCHIVE>',
                          '--output', '<NEW_OUTPUT>', '--criteria', 'research/grwl-raw-release-20261102/global-criteria.json']}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    write_new(started_path, result)
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=checkout)
        result['exit_status'] = completed.returncode
        after = git(checkout, 'status', '--porcelain', '--untracked-files=normal')
        result['working_tree_after'] = {'status': 'clean' if not after else 'dirty', 'observed': True, 'porcelain': after}
        if completed.returncode or after or git(checkout, 'rev-parse', 'HEAD') != revision:
            raise RuntimeError('Rebuild failed or checkout changed during execution')
        if {key: sha(path) for key, path in paths.items()} != pins:
            raise RuntimeError('Relevant input bytes changed during rebuild')
        manifest_path = output/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        if any(manifest['build_inputs'].get(key) != value for key, value in pins.items()):
            raise RuntimeError('Build manifest input hashes differ from observed checkout')
        parquet = output/'grwl-raw.parquet'
        actual = sha(parquet)
        if actual != manifest['parquet_sha256']:
            raise RuntimeError('Completed rebuild bytes differ from manifest')
        result.update({'status': 'passed', 'rebuild_manifest_sha256': sha(manifest_path),
                       'parquet_sha256': actual, 'parquet_size_bytes': parquet.stat().st_size,
                       'source_archive_sha256': manifest['archive']['sha256'],
                       'rows': manifest['rows'], 'tiles': len(manifest['tiles'])})
    except BaseException as exc:
        result.update({'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
        raise
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        write_new(receipt, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('checkout', 'python', 'archive', 'output', 'receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.checkout, args.python, args.archive, args.output, args.receipt)
    print(json.dumps({'status': result['status'], 'receipt': str(args.receipt), 'parquet_sha256': result['parquet_sha256']}))
