#!/usr/bin/env python3
"""Rebuild twice, validate, and optionally package a complete cached-GEE replay."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from dataset_config import load_config

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG = load_config()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path, help='New output directory, never overwritten')
    parser.add_argument('--source', required=True, type=Path, help='Checksum-pinned original ZIP')
    parser.add_argument('--gee-capture', type=Path, help='Existing immutable response capture; no network to GEE')
    args = parser.parse_args()
    work, source = args.work.resolve(), args.source.resolve()
    if work.exists():
        raise SystemExit('Choose a new work directory; completed or failed runs are retained.')
    if not source.is_file() or digest(source) != CONFIG['source_sha256']:
        raise SystemExit('Source missing or differs from the pinned original archive.')
    for command in ('tippecanoe', 'pmtiles', 'node'):
        if not shutil.which(command):
            raise SystemExit(f'Required native tool missing: {command}')
    stac = HERE / 'node_modules/.bin/stac-node-validator'
    if not stac.exists():
        raise SystemExit('Run npm ci --prefix datasets/river-plastic-inputs first.')
    if subprocess.check_output(['git', 'status', '--porcelain', '--', str(HERE)], cwd=ROOT, text=True).strip():
        raise SystemExit('Commit the dataset workflow before rehearsing a release.')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    work.mkdir(parents=True)
    reports = work / 'verification'; reports.mkdir()
    logs = work / 'logs'; logs.mkdir()
    release, rebuild = work / CONFIG['release'], work / 'rebuild'

    def run(stage, command, expected=0):
        print(f'{stage}: running', flush=True)
        result = subprocess.run([str(c) for c in command], cwd=ROOT, capture_output=True, text=True)
        output = result.stdout + result.stderr
        (logs / f'{stage}.log').write_text(output)
        if result.returncode != expected:
            raise RuntimeError(f'{stage} exited {result.returncode}; see {logs / (stage + ".log")}')
        print(f'{stage}: completed (exit {result.returncode})', flush=True)
        return result, output

    python = sys.executable
    run('build', [python, HERE/'build.py', '--source', source, '--output', release])
    run('validate', [python, HERE/'validate.py', release, '--source', source, '--http', '--report', reports/'validation.json'])
    manifest_path = release / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest_sha = digest(manifest_path)
    result, output = run('stac', [stac, release/'catalog.json', release/CONFIG['id']/'collection.json'])
    if not (re.search(r'Passed:\s*2\b', output) and re.search(r'Invalid:\s*0\b', output) and re.search(r'Skipped:\s*0\b', output)):
        raise RuntimeError('STAC validator did not validate both catalog and collection.')
    write(reports/'stac-validation.json', {'validator':'stac-node-validator','version':'2.0.0','exit_code':result.returncode,
          'release_manifest_sha256':manifest_sha,'output':output})
    run('publication', [python, HERE/'check_publication.py', release, '--report', reports/'publication-validation.json'])
    run('rebuild', [python, HERE/'build.py', '--source', source, '--output', rebuild])
    names = sorted(manifest['assets'])
    if manifest_path.read_bytes() != (rebuild/'manifest.json').read_bytes():
        raise RuntimeError('Independent rebuild manifest differs.')
    hashes = {name:digest(release/name) for name in names}
    if hashes != {name:digest(rebuild/name) for name in names}:
        raise RuntimeError('Independent rebuild assets differ.')
    previous = json.loads((HERE/'evidence/release-manifest.json').read_text())
    stable = {name:hashes[name] == previous['assets'][name]['sha256']
              for name in names if name.endswith(('.parquet', '.pmtiles'))}
    if not all(stable.values()):
        raise RuntimeError('Analytic/map data changed from the original release; review before packaging.')
    write(reports/'reproducibility.json', {'status':'passed', 'manifest_equal':True, 'manifest_sha256':manifest_sha,
          'conversion_git_commit':revision, 'assets_compared':len(names),'hashes':hashes,'unchanged_from_original_release':stable,
          'scope':'Two separate output directories, same committed source and locked environment on this machine; not cross-platform proof.'})
    tests, cases = [], 0
    for relative in ('test_publication.py', 'gee/test_compare.py', 'test_package.py'):
        command = [python, HERE/relative]
        if relative == 'test_publication.py':
            command += [release, '--report', reports/'publication-fault-checks.json']
        elif relative == 'gee/test_compare.py':
            command += ['--report', reports/'gee-fault-tests.json']
        result, output = run('faults-'+Path(relative).stem, command)
        if relative == 'test_publication.py':
            fault_report = json.loads((reports/'publication-fault-checks.json').read_text())
            if fault_report['status'] != 'passed' or any(c['status'] != 'detected' for c in fault_report['checks']):
                raise RuntimeError('Publication fault injection failed.')
            count = len(fault_report['checks'])
        else:
            match = re.search(r'Ran (\d+) tests?', output)
            if not match:
                raise RuntimeError(f'No test count found: {relative}')
            count = int(match[1])
        cases += count
        tests.append({'path':relative,'sha256':digest(HERE/relative),'exit_code':result.returncode,'cases':count})
    write(reports/'fault-tests.json', {'status':'passed','cases':cases,'tests':tests,'release_manifest_sha256':manifest_sha})
    gee_status = 'not_run_missing_capture'
    archive = None
    if args.gee_capture:
        capture = args.gee_capture.resolve()
        # Original criteria remain failed. Capture/hash problems must not be counted as the expected failure.
        run('gee-strict', [python, HERE/'gee/compare.py', release, capture, '--report', reports/'gee-strict-replay.json',
                          '--details', logs/'gee-strict-mismatches.jsonl'], expected=1)
        strict = json.loads((reports/'gee-strict-replay.json').read_text())
        if strict['status'] != 'failed' or strict['gee_features'] != CONFIG['expected_rows']:
            raise RuntimeError('Strict GEE replay failed unexpectedly.')
        run('gee-diagnostic', [python, HERE/'gee/diagnose_geometry.py', release, capture, '--coincident-groups',
                              '--report', reports/'gee-validation.json','--details', logs/'gee-diagnostic-mismatches.jsonl'])
        gee_status = json.loads((reports/'gee-validation.json').read_text())['status']
        archive = work / (CONFIG['id']+'-'+CONFIG['release']+'.zip')
        run('package', [python, HERE/'package.py', release, '--validation', reports/'validation.json',
                       '--stac-validation', reports/'stac-validation.json','--reproducibility', reports/'reproducibility.json',
                       '--publication-validation', reports/'publication-validation.json','--gee-validation', reports/'gee-validation.json',
                       '--fault-tests', reports/'fault-tests.json','--output', archive])
    summary = {'status':'passed_local_release' if archive else 'passed_conversion_only',
               'conversion_git_commit':revision, 'release':CONFIG['release'], 'manifest_sha256':manifest_sha,
               'source_sha256':digest(source), 'data_files_unchanged_from_original':stable,
               'assets_rebuilt_identically':len(names), 'fault_tests_passed':cases, 'gee':gee_status,
               'archive': {'name':archive.name,'sha256':digest(archive),'size_bytes':archive.stat().st_size} if archive else None,
               'limits':['No upload, public-host testing or registry submission.',
                         'Cached GEE responses were replayed; no new GEE requests.',
                         'Research comparisons establish published-summary consistency, not independent observational validation.',
                         'Without --gee-capture, GEE replay and packaging are not run.']}
    write(reports/'rehearsal.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
