#!/usr/bin/env python3
"""Offline, immutable regional replay from a clean committed checkout.

Dependencies must already be installed. Build source coverage, repack native
detail, and rebuild the served UI; compare actual bytes with pinned regional
references. No dependency setup, download, publication, or native compilation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = '1c7177cc55b732dc7e609ed22ae50c46d677548da98c4b39e4f1ab76996ca509'
SOURCE_MANIFEST_SHA = 'a817a649959dc38eca80bac9e6f7f50eb2676e8bd7ddeeca018ff4fe0660ae0b'
DETAIL_SHA = 'c3867e547ada2877405993569b7ae4f3553777d063408cb9b45c8a59c6a028d9'
OVERVIEW_SHA = '3d3d27d1f5de6ba958cf644a980f1ef6ee4e604d0e9afcd0672c82cabd098f63'
COMBINED_SHA = '662aae13f02ba0766f832d8c2f48c36d846383a6a4d71271258629276ccc6a64'
SOURCE_ROWS = 919832
SOURCE_TILES = ['NI15', 'NI16', 'NJ12', 'NK12', 'NL10', 'NL11', 'NL12', 'NL13', 'NM11']
MASK_SHAS = dict(zip((f'masks/z{z}.bin' for z in range(8)), (
    'b73d0b85b077fc8a211370c823462536a298f6362a8b907d3e2894dbd63137ca',
    'f8fe6c6f18fd341c670157fcfd4569e451347588876dfdef5379c67581e946ee',
    '596b9a334542ea909046ca54b7f8c5380e1dafff4141e1b96ee1ee2f128a19df',
    '32ce50b19592788b8a59726d9e7d533878293f3e2640ecd6dba34183adee40d6',
    '05960fca3fcae29bcc8bd949eecf2d6b5126f949335d8a567898c2f154418575',
    '3eab92991f7c2827fa684d7d48d09e2fda245c8ab9d469cd9e5cab8df8d7d45e',
    'bdc88172728997d78988fe8e8e3aafeaafd186223caf9e7727dda08035212981',
    '0b03d639f864cf686d18a1d4326d6345fe0a902a9c987fe553824263c2ae8795')))
CODE_FILES = (
    'research/grwl-multiscale-20261103/run_clean_replay.py',
    'research/grwl-multiscale-20261103/criteria.json',
    'research/grwl-multiscale-20261103/browser-controls-r1.json',
    'research/grwl-multiscale-20261103/browser-policy-r1.json',
    'datasets/grwl-raw/build_overview.py', 'datasets/grwl-raw/repack_detail.py',
    'datasets/grwl-raw/compare_detail.py', 'datasets/grwl-raw/compare_detail_fast.py',
    'datasets/grwl-raw/detail_oracle.cpp', 'datasets/grwl-raw/validate_overview.py',
    'datasets/grwl-raw/finalize_multiscale.py', 'datasets/grwl-raw/finalize_display.py',
    'datasets/grwl-raw/prepare_multiscale_preview.py', 'scripts/source_products.py',
    'scripts/display_tools/uv.lock', 'scripts/display_tools/pyproject.toml',
    'scripts/cloud_viewer/build.mjs', 'scripts/cloud_viewer/fetch-assets.mjs',
    'scripts/cloud_viewer/raw-browser-check.mjs', 'scripts/cloud_viewer/multiscale-browser-check.mjs',
    'scripts/cloud_viewer/camera-browser-check.mjs',
    'scripts/cloud_viewer/package-lock.json', 'scripts/cloud_viewer/package.json',
    'scripts/cloud_viewer/runtime-assets.json', 'scripts/cloud_viewer/src/app.js',
    'scripts/cloud_viewer/src/core.js', 'scripts/cloud_viewer/src/parquet.worker.js',
    'scripts/cloud_viewer/src/index.html', 'scripts/cloud_viewer/src/style.css',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f'Unsafe/missing regular file: {path}')
    return {'path': str(path.resolve()), 'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def json_file(path):
    identity(path)
    value = json.loads(Path(path).read_text())
    require(isinstance(value, dict), 'JSON input must be an object')
    return value


def git_state():
    def git(*args):
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return git('rev-parse', 'HEAD').strip(), git('status', '--porcelain', '--untracked-files=all')


def code_pins():
    return {rel: sha256(ROOT / rel) for rel in CODE_FILES}


def verified_viewer(build_path):
    build = json_file(build_path)
    require(build.get('package_lock_sha256') == sha256(ROOT / 'scripts/cloud_viewer/package-lock.json'), 'Reference viewer package lock differs')
    require(isinstance(build.get('files'), dict) and 'app.js' in build['files'], 'Viewer build inventory missing')
    result = {}
    for rel, pin in build['files'].items():
        require(not Path(rel).is_absolute() and all(part not in ('', '.', '..') for part in rel.split('/')) and '\\' not in rel, 'Unsafe viewer inventory path')
        actual = identity(Path(build_path).parent / rel)
        require(actual['sha256'] == pin.get('sha256') and actual['size_bytes'] == pin.get('size_bytes'), 'Viewer bytes differ from build inventory')
        result[rel] = actual
    return identity(build_path), result


def guard(output, *, start=False):
    free = shutil.disk_usage(output if output.exists() else output.parent).free
    used = sum(p.stat().st_size for p in output.rglob('*') if p.is_file() and not p.is_symlink()) if output.exists() else 0
    require(free >= (40 if start else 15) * 1024 ** 3 and used <= 4 * 1024 ** 3, 'Replay disk floor/4 GiB artifact ceiling exceeded')
    return {'free_bytes': free, 'new_replay_bytes': used}


def run(source, source_manifest, detail, reference_overview, reference_display,
        reference_viewer_build, task_root, output, native_lock):
    source, source_manifest, detail, reference_overview, reference_display, reference_viewer_build, task_root, output, native_lock = map(Path,
        (source, source_manifest, detail, reference_overview, reference_display, reference_viewer_build, task_root, output, native_lock))
    require(not os.path.lexists(output), 'Refusing existing immutable replay output')
    source, source_manifest, detail, reference_overview, reference_display, reference_viewer_build, task_root, output, native_lock = (
        path.expanduser().resolve() for path in (source, source_manifest, detail, reference_overview, reference_display, reference_viewer_build, task_root, output, native_lock))
    output.resolve().relative_to(task_root.resolve())
    require(not output.resolve().is_relative_to(ROOT), 'Replay output must be outside the clean checkout')
    for protected in (source, source_manifest, detail, reference_overview, reference_display, reference_viewer_build):
        require(not protected.resolve().is_relative_to(output.resolve()) and not output.resolve().is_relative_to(protected.resolve()), 'Replay output overlaps a read-only input')
    commit, before = git_state()
    require(before == '', 'Replay requires a clean committed checkout before building')
    pins = code_pins()
    active_lock = Path(sys.prefix).resolve().parent / 'uv.lock'
    require(sha256(active_lock) == sha256(ROOT / 'scripts/display_tools/uv.lock'), 'Use locked display_tools Python')
    node = shutil.which('node')
    require(node is not None, 'Installed node required; no dependency setup is performed')
    for dependency in ('esbuild/package.json', '@duckdb/duckdb-wasm/package.json', 'maplibre-gl/package.json'):
        require((ROOT / 'scripts/cloud_viewer/node_modules' / dependency).is_file(), 'Install viewer dependencies before starting a clean replay')
    for asset in json_file(ROOT / 'scripts/cloud_viewer/runtime-assets.json')['assets']:
        cached = ROOT / 'scripts/cloud_viewer/node_modules/.cache/viewer' / asset['cache_name']
        require(identity(cached)['sha256'] == asset['sha256'] and cached.stat().st_size == asset['size_bytes'], 'Pinned runtime cache must exist before replay; no download is performed')
    task_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    resource_start = guard(output, start=True)
    output.mkdir()
    (output / 'logs').mkdir()
    result = {'schema_version': 1, 'status': 'running', 'scope': 'Clean-checkout regional byte replay; no global fidelity, upload, or hosted-publication claim',
        'clean_checkout': {'commit': commit, 'before': before}, 'code_files': pins,
        'source_rows': SOURCE_ROWS, 'source_tiles': SOURCE_TILES, 'resources_start': resource_start,
        'environment_lock': identity(active_lock), 'python': str(Path(sys.executable).resolve()), 'stages': []}
    try:
        references = {'source': identity(source), 'source_manifest': identity(source_manifest), 'detail': identity(detail),
            'overview_archive': identity(reference_overview / 'overview.pmtiles'),
            'combined_archive': identity(reference_display / 'assets/grwl-raw.pmtiles'),
            'overview_build': identity(reference_overview / 'build.json'), 'display_manifest': identity(reference_display / 'manifest.json'),
            'display_provenance': identity(reference_display / 'reports/input-provenance.json'),
            'overview_masks': {rel: identity(reference_overview / rel) for rel in MASK_SHAS}}
        for key, digest in (('source', SOURCE_SHA), ('source_manifest', SOURCE_MANIFEST_SHA), ('detail', DETAIL_SHA), ('overview_archive', OVERVIEW_SHA), ('combined_archive', COMBINED_SHA)):
            require(references[key]['sha256'] == digest, f'Fixed regional reference differs: {key}')
        manifest = json_file(source_manifest)
        require(manifest.get('rows') == SOURCE_ROWS and [tile['tile'] for tile in manifest['tiles']] == SOURCE_TILES, 'Fixed nine-tile source scope differs')
        build = json_file(reference_overview / 'build.json')
        require(build.get('status') == 'built_unvalidated' and build.get('source_sha256') == SOURCE_SHA and build.get('source_manifest_sha256') == SOURCE_MANIFEST_SHA and build.get('rows') == SOURCE_ROWS, 'Reference overview has different source inputs')
        for rel, actual in references['overview_masks'].items():
            require(actual['sha256'] == MASK_SHAS[rel] == build['artifacts'][rel]['sha256'] and actual['size_bytes'] == build['artifacts'][rel]['size_bytes'], 'Reference coverage mask differs')
        provenance = json_file(reference_display / 'reports/input-provenance.json')
        display_manifest = json_file(reference_display / 'manifest.json')
        require(display_manifest.get('status') == 'provisional' and display_manifest.get('archive', {}).get('sha256') == COMBINED_SHA, 'Reference display manifest is incomplete/unbound')
        require(provenance.get('detail', {}).get('sha256') == DETAIL_SHA and provenance.get('overview', {}).get('sha256') == OVERVIEW_SHA, 'Reference combined inputs differ')
        archive_oracle = json_file(reference_overview / 'archive-validation-r1.json')
        require(archive_oracle.get('status') == 'passed' and archive_oracle.get('archive_sha256') == OVERVIEW_SHA and archive_oracle.get('finest_mask_sha256') == MASK_SHAS['masks/z7.bin'], 'Reference overview oracle is unbound/failed')
        comparison_path = reference_display / 'detail-comparison-fast.json'
        if not comparison_path.exists():
            comparison_path = reference_display / 'detail-comparison.json'
        comparison = json_file(comparison_path)
        require(comparison.get('status') == 'passed' and comparison.get('semantic_preservation') is True and comparison.get('tile_byte_gate') is True
            and comparison.get('source', {}).get('sha256') == DETAIL_SHA and comparison.get('candidate', {}).get('sha256') == COMBINED_SHA, 'Reference detail oracle is unbound/failed')
        references.update({'overview_oracle': identity(reference_overview / 'archive-validation-r1.json'), 'detail_oracle': identity(comparison_path)})
        references['viewer_build'], references['viewer_files'] = verified_viewer(reference_viewer_build)
        result['references'] = references
        write_json(output / 'inputs.json', result)
        def stage(name, command):
            with (output / 'logs' / (name + '.log')).open('x') as log:
                completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            result['stages'].append({'name': name, 'command': command, 'returncode': completed.returncode,
                'log': identity(output / 'logs' / (name + '.log'))})
            require(completed.returncode == 0, f'Replay stage failed: {name}; inspect retained log')
            guard(output)
        stage('overview', [sys.executable, '-B', str(ROOT / 'datasets/grwl-raw/build_overview.py'),
            '--source', str(source), '--source-manifest', str(source_manifest), '--output', str(output / 'overview'), '--task-root', str(task_root)])
        stage('native-repack', [sys.executable, '-B', str(ROOT / 'datasets/grwl-raw/repack_detail.py'),
            '--detail', str(detail), '--source-sha256', DETAIL_SHA, '--overview', str(output / 'overview/overview.pmtiles'),
            '--overview-sha256', OVERVIEW_SHA, '--output', str(output / 'combined'), '--task-root', str(task_root),
            '--native-lock', str(native_lock), '--maximum-gib', '4'])
        stage('viewer', [node, str(ROOT / 'scripts/cloud_viewer/build.mjs'), '--out', str(output / 'ui')])
        artifacts = {'overview_archive': identity(output / 'overview/overview.pmtiles'),
            'combined_archive': identity(output / 'combined/assets/grwl-raw.pmtiles'),
            'overview_masks': {rel: identity(output / 'overview' / rel) for rel in MASK_SHAS},
            'overview_build': identity(output / 'overview/build.json'), 'display_manifest': identity(output / 'combined/manifest.json'),
            'display_provenance': identity(output / 'combined/reports/input-provenance.json')}
        artifacts['viewer_build'], artifacts['viewer_files'] = verified_viewer(output / 'ui/build.json')
        def same(a, b):
            return (a['sha256'], a['size_bytes']) == (b['sha256'], b['size_bytes'])
        result['artifacts'] = artifacts
        result['byte_equal'] = {key: same(artifacts[key], references[key]) for key in ('overview_archive', 'combined_archive', 'viewer_build')}
        result['byte_equal']['overview_masks'] = all(same(artifacts['overview_masks'][rel], references['overview_masks'][rel]) for rel in MASK_SHAS)
        result['byte_equal']['viewer_files'] = set(artifacts['viewer_files']) == set(references['viewer_files']) and all(same(value, references['viewer_files'][rel]) for rel, value in artifacts['viewer_files'].items())
        require(all(result['byte_equal'].values()), 'Clean replay artifact bytes differ from fixed passing regional references')
        after_commit, after = git_state()
        result['clean_checkout'].update({'after': after, 'after_commit': after_commit})
        require(after == '' and after_commit == commit and code_pins() == pins, 'Clean checkout/code changed during replay')
        # Rehash all original source and reference bytes before claiming replay.
        for group in (references, artifacts):
            for key, value in group.items():
                if key in ('overview_masks', 'viewer_files'):
                    for info in value.values():
                        require(identity(info['path']) == info, 'Referenced artifact changed during replay')
                else:
                    require(identity(value['path']) == value, 'Referenced artifact changed during replay')
        result['viewer_build_sha256'] = artifacts['viewer_build']['sha256']
        result['resources_end'] = guard(output)
        result['status'] = 'passed'
        write_json(output / 'report.json', result)
        return result
    except BaseException as exc:
        result['status'] = 'failed'
        result['error'] = f'{type(exc).__name__}: {exc}'
        try:
            after_commit, after = git_state()
            result['clean_checkout'].update({'after': after, 'after_commit': after_commit})
        except Exception as inspection_error:
            result['checkout_inspection_error'] = str(inspection_error)
        write_json(output / 'failure.json', result)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'source-manifest', 'detail', 'reference-overview', 'reference-display', 'reference-viewer-build', 'task-root', 'output', 'native-lock'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source, args.source_manifest, args.detail, args.reference_overview,
        args.reference_display, args.reference_viewer_build, args.task_root, args.output, args.native_lock)
    print(json.dumps({'status': result['status'], 'report': str(args.output / 'report.json')}))


if __name__ == '__main__':
    main()
