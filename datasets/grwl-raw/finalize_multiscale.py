#!/usr/bin/env python3
"""Prepare an immutable local GRWL r2 display after all bound gates pass.

`--inputs` names regular report files and read-only input packages. The final
archive is copied with APFS clone support; the historical r1 archive is an
explicit external binary reference, while every r1 nonbulk file is retained.
This tool does not update canonical publication metadata or publish anything.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / 'research/grwl-multiscale-20261103'
BASELINE_SHA = '0c241cd3e955ca5431380f86cd1a6ffe274c91073e10c919b60c8e5e3d220524'
SOURCE_SHA = 'd37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb'
SOURCE_MANIFEST_SHA = '160dfaf91ede202da57172ff16492601ca349d43e0b629819a7e4eb82222acda'
BASELINE_ARCHIVE_SHA = 'a1a7787c7ba28ffc271819bddc54339f9bc741aa9ed44ca619d93e809cbad4f5'
SOURCE_SIZE = MAX_ARCHIVE_BYTES = 5_529_859_809
BASELINE_ARCHIVE_SIZE = 11_498_067_077
ROWS, SOURCE_TILES = 64_572_998, 829
DETAIL_COUNTS = {'8': 9375, '9': 26570, '10': 66676, '11': 152196, '12': 333538}
SOURCE_ORACLE_RECORDS = 1_158_798
ARCHIVE_REL = 'assets/grwl-raw.pmtiles'
SOURCE_REL = 'assets/grwl-raw-observations.parquet'
RELEASE = 'raw-v01.01-display-r2'
CASE_BYTES = 32 * 1024 ** 2
MULTISCALE_CASES = {'global-z0', 'amazon-z3', 'known-raw-15450-z7', 'overview-to-detail', 'nr01-first-record-z7'}
WORKFLOW = (
    'datasets/grwl-raw/finalize_multiscale.py', 'datasets/grwl-raw/finalize_display.py',
    'datasets/grwl-raw/build_overview.py', 'datasets/grwl-raw/validate_overview.py',
    'datasets/grwl-raw/repack_detail.py', 'datasets/grwl-raw/compare_detail.py',
    'datasets/grwl-raw/compare_detail_fast.py', 'datasets/grwl-raw/detail_oracle.cpp',
    'datasets/grwl-raw/prepare_multiscale_preview.py', 'scripts/source_products.py',
    'scripts/display_tools/uv.lock', 'scripts/display_tools/pyproject.toml',
    'scripts/cloud_viewer/build.mjs', 'scripts/cloud_viewer/raw-browser-check.mjs',
    'scripts/cloud_viewer/multiscale-browser-check.mjs', 'scripts/cloud_viewer/prepare.py',
    'scripts/cloud_viewer/run.py', 'scripts/cloud_viewer/serve.py',
    'scripts/cloud_viewer/package-lock.json', 'scripts/cloud_viewer/package.json',
    'scripts/cloud_viewer/camera-browser-check.mjs',
    'scripts/cloud_viewer/runtime-assets.json', 'scripts/cloud_viewer/src/app.js',
    'scripts/cloud_viewer/src/core.js', 'scripts/cloud_viewer/src/parquet.worker.js',
    'scripts/cloud_viewer/src/index.html', 'scripts/cloud_viewer/src/style.css',
    'research/grwl-multiscale-20261103/criteria.json',
    'research/grwl-multiscale-20261103/browser-controls-r1.json',
    'research/grwl-multiscale-20261103/browser-policy-r1.json',
    'research/grwl-multiscale-20261103/prepare_holdout.py',
    'research/grwl-multiscale-20261103/heldout-selection.json',
    'research/grwl-multiscale-20261103/run_clean_replay.py',
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


old = load_module('grwl_r1_finalization', ROOT / 'datasets/grwl-raw/finalize_display.py')
FinalizeError = old.FinalizeError


def require(condition, message):
    if not condition:
        raise FinalizeError(message)


def regular(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f'Missing/unsafe regular input: {path}')
    return path


def identity(path):
    path = regular(path)
    return {'sha256': old._sha256(path), 'size_bytes': path.stat().st_size}


def bound(info, expected, label):
    def normalized(value):
        require(isinstance(value, dict), f'Malformed {label} identity')
        size = value.get('size_bytes', value.get('bytes'))
        digest = value.get('sha256')
        require(type(size) is int and size >= 0 and isinstance(digest, str)
            and re.fullmatch(r'[0-9a-f]{64}', digest) is not None, f'Malformed {label} hash/size')
        require(not ('size_bytes' in value and 'bytes' in value) or value['size_bytes'] == value['bytes'], f'Conflicting {label} sizes')
        return size, digest
    require(normalized(info) == normalized(expected), f'Unbound {label}')


def canonical_criteria_hash(criteria):
    return hashlib.sha256(json.dumps(criteria, sort_keys=True).encode()).hexdigest()


def archive_identity(path):
    path = regular(path)
    require(0 < path.stat().st_size <= MAX_ARCHIVE_BYTES, 'R2 archive exceeds frozen global archive limit')
    return identity(path)


def resources(output):
    free = shutil.disk_usage(output).free
    used = sum(p.stat().st_size for p in output.rglob('*') if p.is_file() and not p.is_symlink())
    require(free >= 15 * 1024 ** 3 and used <= 24 * 1024 ** 3, 'Finalization resource floor/ceiling exceeded')
    return {'free_bytes': free, 'new_package_bytes': used}


def baseline_chain(baseline):
    require(not baseline.is_symlink() and baseline.is_dir(), 'Unsafe baseline package')
    manifest_path = baseline / 'manifest.json'
    require(identity(manifest_path)['sha256'] == BASELINE_SHA, 'Baseline r1 manifest differs from sealed pin')
    manifest = old._json(manifest_path, 'baseline manifest')
    require((manifest.get('status'), manifest.get('dataset_id'), manifest.get('display_release'), manifest.get('source_rows'), manifest.get('source_tiles'))
        == ('prepared', 'grwl-raw', 'raw-v01.01-display-r1', ROWS, SOURCE_TILES), 'Unexpected baseline identity')
    files = manifest.get('files')
    require(isinstance(files, dict) and ARCHIVE_REL in files, 'Missing baseline inventory')
    actual = set()
    for directory, dirs, names in os.walk(baseline, followlinks=False):
        for name in dirs:
            require(not (Path(directory) / name).is_symlink(), 'Baseline directory symlink')
        for name in names:
            path = Path(directory) / name
            rel = path.relative_to(baseline).as_posix()
            old._safe_relative(rel, 'baseline inventory')
            regular(path)
            if rel != 'manifest.json':
                actual.add(rel)
    require(actual == set(files), 'Baseline files differ from sealed inventory')
    for rel, pin in files.items():
        old._safe_relative(rel, 'baseline inventory')
        bound(identity(baseline / rel), pin, f'baseline file {rel}')
    bound(files[ARCHIVE_REL], {'sha256': BASELINE_ARCHIVE_SHA, 'size_bytes': BASELINE_ARCHIVE_SIZE}, 'historical r1 archive')
    report = old._json(baseline / 'reports/finalization/report.json', 'baseline report')
    require(report.get('status') == 'passed' and report.get('oracle', {}).get('missing_classification') == {'quantization_collapse': 304}, 'Baseline finalization/omission evidence differs')
    return manifest, report


def validate_detail(report, archive, criteria_pin):
    require(report.get('status') == 'passed' and report.get('semantic_preservation') is True
        and report.get('tile_byte_gate') is True, 'Detail exact semantic/byte gates did not pass')
    bound(report.get('source'), {'sha256': BASELINE_ARCHIVE_SHA, 'size_bytes': BASELINE_ARCHIVE_SIZE}, 'detail baseline')
    bound(report.get('candidate'), archive, 'detail candidate')
    bound(report.get('criteria'), criteria_pin, 'detail criteria')
    counts = report.get('counts', {})
    require(counts.get('detail_tiles') == 588355 and counts.get('by_zoom') == DETAIL_COUNTS
        and counts.get('detail_tiles_over_byte_limit') == 0
        and 0 < counts.get('maximum_gzip_tile_bytes', 0) <= 1048576
        and counts.get('detail_features', 0) > 0, 'Detail report omits global tiles or violates byte gate')
    comparator = report.get('comparator', {})
    implementations = {
        'upb': old._sha256(ROOT / 'datasets/grwl-raw/compare_detail.py'),
        'independent_cpp_wire_v1': old._sha256(ROOT / 'datasets/grwl-raw/compare_detail_fast.py'),
    }
    implementation = report.get('protobuf_implementation')
    require(isinstance(implementation, str) and implementation in implementations
        and comparator.get('sha256') == implementations[implementation],
        'Detail implementation does not match current comparator code')
    if implementation == 'independent_cpp_wire_v1':
        native = report.get('native_oracle', {})
        require(native.get('source', {}).get('sha256') == old._sha256(ROOT / 'datasets/grwl-raw/detail_oracle.cpp'), 'Native oracle source is unbound')
        binary = native.get('binary', {})
        require(isinstance(binary.get('path'), str), 'Native oracle binary path missing')
        bound(identity(Path(binary['path'])), binary, 'native oracle binary')
        snapshot = native.get('source_snapshot', {})
        require(isinstance(snapshot.get('path'), str), 'Native oracle source snapshot path missing')
        bound(identity(Path(snapshot['path'])), snapshot, 'native oracle source snapshot')
        bound(snapshot, native['source'], 'native source/snapshot')
        require(report.get('directory_reader', {}).get('sha256') == old._sha256(ROOT / 'datasets/grwl-raw/compare_detail.py'), 'Native directory reader code is unbound')


def validate_overview(build, tile_oracle, source_oracle, archive, mask, source_manifest, criteria, criteria_pin):
    criteria_json_sha = canonical_criteria_hash(criteria)
    source_manifest_sha = old._sha256(source_manifest)
    require(source_manifest_sha == SOURCE_MANIFEST_SHA, 'Overview source manifest differs from sealed r1 source inventory')
    require(build.get('status') == 'built_unvalidated' and build.get('source_sha256') == SOURCE_SHA
        and build.get('source_manifest_sha256') == source_manifest_sha and build.get('rows') == ROWS
        and build.get('criteria_sha256') == criteria_pin['sha256']
        and build.get('extent') == 4096 and build.get('cells_per_tile') == 512, 'Overview build source/geometry inputs are unbound')
    bound(build.get('artifacts', {}).get('masks/z7.bin'), mask, 'overview finest mask')
    per_zoom = build.get('per_zoom')
    require(isinstance(per_zoom, list) and [r.get('zoom') for r in per_zoom] == list(range(8))
        and all(r.get('tiles', 0) > 0 and 0 < r.get('maximum_tile_bytes', 0) <= 262144 for r in per_zoom), 'Overview build lacks zooms or exceeds tile limit')
    require(tile_oracle.get('status') == 'passed' and tile_oracle.get('archive_sha256') == archive['sha256']
        and tile_oracle.get('finest_mask_sha256') == mask['sha256'] and tile_oracle.get('mask_bitorder') == 'little'
        and tile_oracle.get('criteria_json_sha256') == criteria_json_sha
        and 0 < tile_oracle.get('largest_gzip_tile_bytes', 0) <= 262144, 'Overview archive oracle is unbound or failed')
    require(tile_oracle.get('tiles_by_zoom') == {str(r['zoom']): r['tiles'] for r in per_zoom}, 'Overview archive oracle tile counts differ from source mask build')
    source_meta = old._json(source_manifest, 'overview source manifest')
    require(source_meta.get('parquet_sha256') == SOURCE_SHA and source_meta.get('rows') == ROWS
        and len(source_meta.get('tiles', [])) == SOURCE_TILES, 'Overview source manifest is not global source')
    expected = {tile['tile']: tile['records'] if tile['tile'] in criteria['heldout_source_tiles'] else min(32, tile['records']) for tile in source_meta['tiles']}
    require(sum(expected.values()) == SOURCE_ORACLE_RECORDS, 'Unexpected frozen global source-oracle scope')
    require(source_oracle.get('status') == 'passed' and source_oracle.get('source_sha256') == SOURCE_SHA
        and source_oracle.get('source_manifest_sha256') == source_manifest_sha
        and source_oracle.get('criteria_json_sha256') == criteria_json_sha
        and source_oracle.get('finest_mask_sha256') == mask['sha256']
        and source_oracle.get('records') == SOURCE_ORACLE_RECORDS and source_oracle.get('records_by_tile') == expected
        and source_oracle.get('heldout_tiles') == sorted(criteria['heldout_source_tiles'])
        and source_oracle.get('selection') == criteria['overview']['independent_source_controls']
        and all(source_oracle.get(key) == 0 for key in ('subset_missing_cells', 'subset_extra_cells', 'global_missing_cells'))
        and source_oracle.get('failures') == [], 'Independent overview source oracle is incomplete, failed or unbound')
    oracle_sha = old._sha256(ROOT / 'datasets/grwl-raw/validate_overview.py')
    require(tile_oracle.get('oracle_sha256') == source_oracle.get('oracle_sha256') == oracle_sha
        and source_oracle.get('production_module_sha256') == old._sha256(ROOT / 'datasets/grwl-raw/build_overview.py'), 'Overview oracle/producer code bindings differ')


def validate_multiscale_browser(report, archive, source_validation_sha, source_report):
    """Validate against the source report already bound by _validate_fidelity."""
    require(source_report.get('status') == 'passed' and source_report.get('parquet_sha256') == SOURCE_SHA
        and source_report.get('manifest_sha256') == SOURCE_MANIFEST_SHA, 'Browser anchor source evidence is not the sealed source report')
    source_tiles = source_report.get('tiles')
    require(isinstance(source_tiles, list), 'Browser anchor source tile evidence is missing')
    nr01 = [tile for tile in source_tiles if isinstance(tile, dict) and tile.get('tile') == 'NR01']
    require(len(nr01) == 1, 'Browser anchor source evidence must contain one NR01 tile')
    first_records = nr01[0].get('first_records')
    require(isinstance(first_records, list) and first_records and isinstance(first_records[0], dict), 'NR01 first source record is missing')
    first = first_records[0]
    source_id = (old._tile_code('NR01') << 32) | 1
    require(first.get('source_tile') == 'NR01' and first.get('source_row') == 1
        and first.get('feature_id') == source_id, 'NR01 first source record identity differs')
    source_bbox = first.get('bbox')
    require(isinstance(source_bbox, list) and len(source_bbox) == 4
        and all(type(value) in (int, float) and math.isfinite(value) for value in source_bbox), 'NR01 source bbox is malformed')
    source_center = [(source_bbox[0] + source_bbox[2]) / 2, (source_bbox[1] + source_bbox[3]) / 2]
    require(report.get('status') == 'passed' and report.get('schema_version') == 1 and report.get('errors') == [], 'Multiscale browser report did not pass cleanly')
    runtime = report.get('runtime', {})
    bound(runtime, archive, 'multiscale browser runtime archive')
    require(runtime.get('dataset_id') == 'grwl-raw' and runtime.get('overview_source_layer') == 'grwl_overview'
        and runtime.get('detail_min_zoom') == 8 and isinstance(runtime.get('object_path'), str), 'Multiscale browser runtime layer differs')
    policy = report.get('transfer_policy', {})
    require(policy.get('enforced') is True and policy.get('bytes_per_case') == CASE_BYTES
        and policy.get('requested_range_bytes') is True and policy.get('response_body_bytes') is True, 'Multiscale browser transfer policy differs')
    anchor = report.get('source_anchor', {})
    require(anchor.get('sha256') == source_validation_sha and anchor.get('parquet_sha256') == SOURCE_SHA
        and anchor.get('tile') == 'NR01' and anchor.get('source_row') == 1
        and anchor.get('feature_id') == source_id
        and anchor.get('bbox') == source_bbox and anchor.get('center') == source_center, 'Dateline browser source identity/bbox/center differs')
    cases = report.get('cases')
    require(isinstance(cases, list) and len(cases) == 5 and {c.get('case_id') for c in cases} == MULTISCALE_CASES, 'Multiscale browser case set differs')
    for case in cases:
        require(case.get('status') == 'passed' and not case.get('error'), 'Multiscale browser case failed')
        fixed = {'global-z0': ([0, 20], 0), 'amazon-z3': ([-60, -3], 3),
            'known-raw-15450-z7': ([-108, 44.8], 7), 'overview-to-detail': ([-108, 44.8], 7),
            'nr01-first-record-z7': (source_center, 7)}
        require((case.get('center'), case.get('zoom')) == fixed[case['case_id']], 'Browser case geographic view differs')
        if case['case_id'] == 'nr01-first-record-z7':
            require(case.get('source_tile') == 'NR01' and case.get('source_row') == anchor['source_row']
                and case.get('feature_id') == anchor['feature_id'], 'Dateline browser case changed source identity')
        checkpoints = case.get('checkpoints', [])
        expected_views = ['overview', 'detail'] if case['case_id'] == 'overview-to-detail' else ['overview']
        require([c.get('view') for c in checkpoints] == expected_views, 'Missing overview/detail browser checkpoint')
        for point in checkpoints:
            overview = point['view'] == 'overview'
            require(('grwl_overview' if overview else 'grwl_raw') in point.get('rendered_layers', [])
                and point.get('width_legend_hidden') is overview, 'Browser source layer/legend mismatch')
            require(type(point.get('zoom')) in (int, float)
                and abs(point['zoom'] - (case['zoom'] if overview else 8)) < 0.05
                and point.get('center') == case['center'], 'Browser checkpoint geographic view differs')
            actual_center = point.get('actual_center')
            require(isinstance(actual_center, list) and len(actual_center) == 2
                and all(type(value) in (int, float) and math.isfinite(value) for value in actual_center)
                and all(abs(value - expected) <= 1e-8 for value, expected in zip(actual_center, case['center'])),
                'Browser checkpoint actual center is missing, malformed or differs from the frozen view')
            if overview:
                require('coverage' in point.get('map_status', '').lower(), 'Overview lacks coverage meaning')
            else:
                expression = json.dumps(point.get('width_expression'))
                require('width_m' in expression and 'width_mean' not in expression, 'Detail width expression differs')
        total = requested = 0
        gets = []
        for request in case.get('requests', []):
            if request.get('method') != 'GET':
                continue
            gets.append(request)
            require(request.get('object_path') == runtime['object_path'] and request.get('status') == 206
                and request.get('cors') == '*' and request.get('completed') is True, 'Invalid multiscale HTTP response')
            match = re.fullmatch(r'bytes=(\d+)-(\d+)', request.get('range') or '')
            require(match is not None, 'Missing bounded browser byte range')
            first, last = map(int, match.groups())
            length = last - first + 1
            require(0 <= first <= last < archive['size_bytes']
                and request.get('content_range') == f'bytes {first}-{last}/{archive["size_bytes"]}'
                and request.get('body_bytes') == length, 'Browser range bounds/body mismatch')
            requested += length
            total += request['body_bytes']
        require(gets and total == case.get('response_body_bytes') and requested == case.get('requested_range_bytes')
            and max(total, requested) <= CASE_BYTES and case.get('transfer_ceiling_bytes') == CASE_BYTES, 'Multiscale browser range counters differ or exceed 32 MiB')


def validate_repack(manifest, provenance, archive, overview_build, criteria_pin):
    bound(manifest.get('archive'), archive, 'native repack output')
    require(manifest.get('status') == 'provisional', 'Native repack did not finish provisionally')
    bound(provenance.get('detail'), {'sha256': BASELINE_ARCHIVE_SHA, 'size_bytes': BASELINE_ARCHIVE_SIZE}, 'native detail input')
    overview = overview_build.get('artifacts', {}).get('overview.pmtiles')
    require(isinstance(overview, dict), 'Overview build lacks immutable archive identity')
    bound(provenance.get('overview'), overview, 'native overview input')
    bound(provenance.get('criteria'), criteria_pin, 'native criteria')
    require(provenance.get('binary', {}).get('sha256') == 'da56cb1a2ddf59b2f03798b5314db665dad87bc03cab6f86a03e630e420173fa'
        and provenance.get('version') == '2.79.0' and provenance.get('workers') == 2
        and provenance.get('remove_properties') == ['_src_xmin', '_src_ymin', '_src_xmax', '_src_ymax'], 'Native repack pin/property policy differs')
    expected_command = ['tile-join', '--no-tile-size-limit', '-o', 'assets/grwl-raw.pmtiles']
    for key in provenance['remove_properties']:
        expected_command.extend(['-x', key])
    expected_command.extend(['inputs/detail.pmtiles', 'inputs/overview.pmtiles'])
    require(provenance.get('command') == expected_command, 'Native repack used unexpected drop/skip/rescale options')
    require(provenance.get('builder', {}).get('sha256') == old._sha256(ROOT / 'datasets/grwl-raw/repack_detail.py')
        and provenance.get('environment_lock', {}).get('sha256') == old._sha256(ROOT / 'scripts/display_tools/uv.lock'), 'Native producer/environment is unbound')
    require(provenance.get('environment', {}).get('TIPPECANOE_MAX_THREADS') == '2', 'Native worker environment differs')


def validate_viewer_binding(detail, multiscale, viewer_pin):
    require(detail.get('inputs', {}).get('viewer_build_sha256') == viewer_pin['sha256']
        and multiscale.get('runtime', {}).get('viewer_build_sha256') == viewer_pin['sha256'],
        'Browser reports do not bind the actual served viewer build')


def validate_clean_replay(report, viewer_pin):
    replay = load_module('grwl_clean_replay_contract', RESEARCH / 'run_clean_replay.py')
    require(report.get('schema_version') == 1 and report.get('status') == 'passed', 'Clean regional replay did not pass')
    checkout = report.get('clean_checkout', {})
    require(isinstance(checkout.get('commit'), str) and re.fullmatch(r'[0-9a-f]{40}', checkout['commit']) is not None
        and checkout.get('before') == checkout.get('after') == '' and checkout.get('after_commit') == checkout['commit'], 'Regional replay checkout was not clean and unchanged')
    require(report.get('source_rows') == replay.SOURCE_ROWS and report.get('source_tiles') == replay.SOURCE_TILES, 'Replay source rows/tile split differs')
    expected_equal = {'overview_archive', 'combined_archive', 'viewer_build', 'overview_masks', 'viewer_files'}
    require(isinstance(report.get('byte_equal'), dict) and set(report['byte_equal']) == expected_equal
        and all(value is True for value in report['byte_equal'].values()), 'Replay did not establish byte equality for every artifact class')
    require(report.get('code_files') == replay.code_pins(), 'Replay code/criteria/locks differ from current verification checkout')
    require(report.get('viewer_build_sha256') == viewer_pin['sha256'], 'Replay used a different served UI build')
    references, artifacts = report.get('references', {}), report.get('artifacts', {})
    require(isinstance(references, dict) and {'source', 'source_manifest', 'detail', 'overview_archive', 'combined_archive',
        'overview_build', 'display_manifest', 'display_provenance', 'overview_masks', 'overview_oracle', 'detail_oracle', 'viewer_build', 'viewer_files'} <= set(references), 'Replay references are incomplete')
    require(isinstance(artifacts, dict) and {'overview_archive', 'combined_archive', 'overview_masks', 'overview_build',
        'display_manifest', 'display_provenance', 'viewer_build', 'viewer_files'} <= set(artifacts), 'Replay artifacts are incomplete')
    for key, digest in (('source', replay.SOURCE_SHA), ('source_manifest', replay.SOURCE_MANIFEST_SHA),
                        ('detail', replay.DETAIL_SHA), ('overview_archive', replay.OVERVIEW_SHA), ('combined_archive', replay.COMBINED_SHA)):
        require(references.get(key, {}).get('sha256') == digest, f'Replay regional reference identity differs: {key}')
    for key in ('overview_archive', 'combined_archive'):
        bound(artifacts.get(key), references[key], f'byte-equal replay {key}')
    bound(references.get('viewer_build'), viewer_pin, 'replay reference served UI')
    bound(artifacts.get('viewer_build'), viewer_pin, 'replayed served UI')
    for group in (references, artifacts):
        for key, info in group.items():
            if key in ('overview_masks', 'viewer_files'):
                require(isinstance(info, dict), 'Malformed replay nested inventory')
                for value in info.values():
                    require(isinstance(value, dict) and isinstance(value.get('path'), str), 'Missing replay artifact path')
                    bound(identity(Path(value['path'])), value, 'existing replay artifact')
            else:
                require(isinstance(info, dict) and isinstance(info.get('path'), str), 'Missing replay reference path')
                bound(identity(Path(info['path'])), info, 'existing replay reference/artifact')
    for group in (references, artifacts):
        require(set(group.get('overview_masks', {})) == set(replay.MASK_SHAS), 'Replay omits a source coverage mask')
        for rel, digest in replay.MASK_SHAS.items():
            require(group['overview_masks'][rel]['sha256'] == digest, 'Replayed coverage mask differs from frozen pilot')
    require(set(references.get('viewer_files', {})) == set(artifacts.get('viewer_files', {})) and 'app.js' in artifacts['viewer_files'], 'Replay viewer file inventory differs')
    for rel, info in references['viewer_files'].items():
        bound(artifacts['viewer_files'][rel], info, f'byte-equal replay UI {rel}')
    require([stage.get('name') for stage in report.get('stages', [])] == ['overview', 'native-repack', 'viewer']
        and all(stage.get('returncode') == 0 for stage in report['stages']), 'Replay stages are incomplete or failed')
    for stage in report['stages']:
        log = stage.get('log', {})
        require(isinstance(log.get('path'), str), 'Replay stage log path missing')
        bound(identity(Path(log['path'])), log, 'retained replay stage log')


def verify_overview_identity(archive):
    """Coverage polygons must not acquire IDs or analytical attributes."""
    import gzip
    from pmtiles.reader import all_tiles, MmapSource
    from mapbox_vector_tile.Mapbox import vector_tile_pb2 as mvt
    counts = {str(z): 0 for z in range(8)}
    with Path(archive).open('rb') as stream:
        for (z, x, y), data in all_tiles(MmapSource(stream)):
            if z > 7:
                break  # The exhaustive detail comparison already verifies directory order.
            tile = mvt.tile();tile.ParseFromString(gzip.decompress(data))
            require(len(tile.layers) == 1 and tile.layers[0].name == 'grwl_overview', 'Unexpected overview identity layer')
            for feature in tile.layers[0].features:
                require(not feature.HasField('id') and not feature.tags, 'Coverage polygon has an ID or analytical attributes')
                counts[str(z)] += 1
    require(all(counts.values()), 'Overview identity check lacks a zoom')
    return {'status': 'passed', 'ids_present': 0, 'attribute_tags_present': 0, 'features_by_zoom': counts}


def make_asset(archive):
    return {'id': 'grwl-raw-display', 'title': 'GRWL raw width observations and observation coverage',
        'path': ARCHIVE_REL, **archive, 'source_layer': 'grwl_raw', 'geometry_type': 'line',
        'id_field': 'feature_id', 'id_encoding': 'mvt_feature_id', 'attribute_fields': ['width_m', 'width_valid'],
        'min_zoom': 0, 'max_zoom': 12, 'detail_min_zoom': 8, 'style_path': 'styles/width.json',
        'source_asset': {'path': SOURCE_REL, 'sha256': SOURCE_SHA, 'size_bytes': SOURCE_SIZE},
        'overview': {'source_layer': 'grwl_overview', 'geometry_type': 'polygon', 'min_zoom': 0, 'max_zoom': 7,
            'extent': 4096, 'has_feature_ids': False, 'attribute_fields': [],
            'meaning': 'Cells touched by source width-observation geometry; coverage only, not riverbanks or measured width.'}}


def make_style(baseline_style):
    style = deepcopy(baseline_style)
    detail = style['layers'][0]
    require(detail.get('type') == 'line' and detail.get('source-layer') == 'grwl_raw', 'Unexpected baseline primary style')
    detail['minzoom'] = 8
    style['layers'] = [detail, {'id': 'raw-observation-coverage', 'type': 'fill', 'source': 'data',
        'source-layer': 'grwl_overview', 'maxzoom': 8, 'paint': {'fill-color': '#216d85', 'fill-opacity': 0.76, 'fill-antialias': False}}]
    style['sources']['data']['url'] = '../' + ARCHIVE_REL
    return style


def finalize(inputs_path, output):
    inputs_path, output = Path(inputs_path), Path(output)
    require(not os.path.lexists(output), 'Refusing existing immutable output')
    inputs = old._json(inputs_path, 'finalizer input mapping')
    required = ('archive', 'baseline', 'analytic_package', 'detail_report', 'overview_build',
        'overview_archive_report', 'overview_source_report', 'finest_mask', 'browser_detail_report',
        'browser_multiscale_report', 'viewer_build', 'clean_replay_report')
    require(all(isinstance(inputs.get(key), str) and inputs[key] for key in required), 'Missing explicit finalizer input paths')
    paths = {key: Path(inputs[key]).expanduser() for key in required}
    for key, path in paths.items():
        resolved = path.resolve(strict=True)
        require(not output.resolve().is_relative_to(resolved) and not resolved.is_relative_to(output.resolve()), f'Output overlaps protected input {key}')
    output.parent.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(output.parent).free >= 40 * 1024 ** 3, 'Finalization requires 40 GiB starting free space')
    output.mkdir()
    old._write_json(output / 'partial.json', {'status': 'partial', 'usable_release': False})
    try:
        baseline, baseline_report = baseline_chain(paths['baseline'])
        archive = archive_identity(paths['archive'])
        criteria_path = RESEARCH / 'criteria.json'
        criteria, criteria_pin = old._json(criteria_path, 'multiscale criteria'), identity(criteria_path)
        require(criteria['size']['global_maximum_archive_bytes'] == MAX_ARCHIVE_BYTES
            and criteria['source']['parquet_sha256'] == SOURCE_SHA, 'Frozen global source/size criteria changed')
        report_keys = ('detail_report', 'overview_build', 'overview_archive_report', 'overview_source_report', 'browser_detail_report', 'browser_multiscale_report', 'viewer_build', 'clean_replay_report')
        report_pins = {key: identity(paths[key]) for key in report_keys}
        reports = {key: old._json(paths[key], key) for key in report_keys}
        repack_root = paths['archive'].parent.parent
        for key, default in (('repack_manifest', repack_root / 'manifest.json'), ('repack_provenance', repack_root / 'reports/input-provenance.json')):
            paths[key] = Path(inputs.get(key, default))
            report_pins[key] = identity(paths[key])
            reports[key] = old._json(paths[key], key)
        for key in reports:
            bound(identity(paths[key]), report_pins[key], f'unchanged input report {key}')
        bound(reports['repack_manifest'].get('input_provenance'), identity(paths['repack_provenance']), 'native manifest provenance')
        validate_repack(reports['repack_manifest'], reports['repack_provenance'], archive, reports['overview_build'], criteria_pin)
        validate_detail(reports['detail_report'], archive, criteria_pin)
        source_manifest = Path(inputs.get('source_manifest', paths['baseline'] / 'reports/finalization/source-manifest.json'))
        mask = identity(paths['finest_mask'])
        require(mask['size_bytes'] == 536870912, 'Finest source mask is not 65536 squared packed bits')
        validate_overview(reports['overview_build'], reports['overview_archive_report'], reports['overview_source_report'], archive, mask, source_manifest, criteria, criteria_pin)
        base_reports = paths['baseline'] / 'reports/finalization'
        original_source_manifest = base_reports / 'source-manifest.json'
        source_meta = old._json(original_source_manifest, 'sealed source manifest')
        fidelity_path = base_reports / 'source-fidelity.normalized.json'
        fidelity = old._json(fidelity_path, 'sealed source fidelity')
        source_report = old._validate_fidelity(fidelity, original_source_manifest, source_meta, SOURCE_SHA, SOURCE_SIZE, SOURCE_TILES, ROWS)
        analytic = old._validate_analytic_package(paths['analytic_package'], SOURCE_SHA, SOURCE_SIZE, ROWS, old._sha256(fidelity_path))
        require(analytic['manifest_sha256'] == baseline['files']['reports/finalization/analytic-package/manifest.json']['sha256']
            and analytic['receipt_sha256'] == baseline['files']['reports/finalization/analytic-package/package-receipt.json']['sha256'],
            'Analytical package changed from the sealed r1 source binding')
        controls_path = RESEARCH / 'browser-controls-r1.json'
        controls = old._json(controls_path, 'frozen multiscale detail controls')
        baseline_controls = old._json(base_reports / 'global-browser-controls.json', 'sealed original controls')
        policy_path = RESEARCH / 'browser-policy-r1.json'
        policy = old._json(policy_path, 'multiscale browser policy')
        require(controls['cases'] == baseline_controls['cases'], 'Source-selected browser controls changed from sealed baseline')
        require(controls['browser_policy_sha256'] == old._sha256(policy_path)
            and policy['browser_limits'] == controls['browser_limits']
            and controls['browser_limits']['bytes_per_case'] == CASE_BYTES,
            'Browser controls do not bind the stricter multiscale transfer policy')
        old.MAX_CASE_BYTES = CASE_BYTES
        browser = old._validate_browser(controls, controls_path, reports['browser_detail_report'], SOURCE_SHA, SOURCE_SIZE,
            old._sha256(original_source_manifest), baseline_report['browser']['source_validation_sha256'], archive['sha256'], archive['size_bytes'],
            controls['browser_policy_sha256'], ROWS, source_meta['tiles'])
        require(sum(case['analytic_attribute_field_count'] for case in reports['browser_detail_report']['cases']) == 154, 'Detail browser did not check all 154 attributes')
        validate_multiscale_browser(reports['browser_multiscale_report'], archive, baseline_report['browser']['source_validation_sha256'], source_report)
        ui = reports['viewer_build']
        validate_viewer_binding(reports['browser_detail_report'], reports['browser_multiscale_report'], report_pins['viewer_build'])
        validate_clean_replay(reports['clean_replay_report'], report_pins['viewer_build'])
        require(ui.get('schema_version') == 1 and ui.get('package_lock_sha256') == old._sha256(ROOT / 'scripts/cloud_viewer/package-lock.json')
            and isinstance(ui.get('files'), dict) and 'app.js' in ui['files'], 'Viewer runtime build/lock is unbound')
        for rel, pin in ui['files'].items():
            old._safe_relative(rel, 'viewer runtime file')
            bound(identity(paths['viewer_build'].parent / rel), pin, f'viewer runtime {rel}')
        asset = make_asset(archive)
        overview_identity = verify_overview_identity(paths['archive'])
        require(overview_identity['features_by_zoom'] == {str(row['zoom']): row['polygons'] for row in reports['overview_build']['per_zoom']}, 'Overview polygon multiplicity changed')
        verify = old._verify_pmtiles(asset, paths['archive'])
        clone_mode = old._copy_file(paths['archive'], output / ARCHIVE_REL, clone=True)
        bound(identity(output / ARCHIVE_REL), archive, 'cloned r2 archive')
        resources(output)
        # Preserve every historical nonbulk byte and its original immutable
        # manifest; never include or clone the 11.5 GB historical archive.
        for rel in ['manifest.json', *baseline['files']]:
            if rel != ARCHIVE_REL:
                dest = output / 'reports/baseline-r1' / rel
                old._copy_file(paths['baseline'] / rel, dest)
                bound(identity(dest), {'sha256': BASELINE_SHA, 'size_bytes': (paths['baseline'] / rel).stat().st_size}
                    if rel == 'manifest.json' else baseline['files'][rel], f'copied baseline {rel}')
        for key in reports:
            dest = output / 'reports/multiscale' / (key.replace('_', '-') + '.json')
            old._copy_file(paths[key], dest)
            bound(identity(dest), report_pins[key], f'copied input report {key}')
        for stage in reports['clean_replay_report']['stages']:
            dest = output / 'reports/multiscale/clean-replay-logs' / (stage['name'] + '.log')
            old._copy_file(Path(stage['log']['path']), dest)
            bound(identity(dest), stage['log'], 'copied clean replay stage log')
        for rel in ui['files']:
            old._copy_file(paths['viewer_build'].parent / rel, output / 'reports/multiscale/viewer-runtime' / rel)
        old._copy_file(inputs_path, output / 'reports/multiscale/inputs.json')
        old._copy_file(source_manifest, output / 'reports/multiscale/overview-source-manifest.json')
        old._write_json(output / 'reports/multiscale/pmtiles-verify.json', verify)
        old._write_json(output / 'reports/multiscale/overview-identity.json', overview_identity)
        for rel in WORKFLOW:
            old._copy_file(regular(ROOT / rel), output / 'workflow' / rel)
        # Save producer snapshots referenced by the overview build, excluding
        # bulk masks/archive. Validate against the build's declared checksums.
        for rel, pin in reports['overview_build'].get('artifacts', {}).items():
            if rel.startswith('workflow/'):
                old._safe_relative(rel, 'overview workflow')
                src = paths['overview_build'].parent / rel
                bound(identity(src), pin, rel)
                old._copy_file(src, output / 'reports/multiscale/overview-build' / rel)
        for source in sorted((repack_root / 'workflow').rglob('*')):
            if source.is_file():
                rel = source.relative_to(repack_root / 'workflow').as_posix()
                old._safe_relative(rel, 'native workflow snapshot')
                old._copy_file(regular(source), output / 'reports/multiscale/native-build/workflow' / rel)
        native = reports['detail_report'].get('native_oracle')
        if native:
            for key in ('source_snapshot', 'binary'):
                pin = native[key]
                src = Path(pin['path'])
                bound(identity(src), pin, f'native oracle {key}')
                old._copy_file(src, output / 'workflow/native-oracle' / src.name)
        for rel, filename in inputs.get('evidence_files', {}).items():
            rel = old._safe_relative(rel, 'extra evidence path')
            old._copy_file(regular(Path(filename)), output / 'reports/extra' / rel)
        old._write_json(output / 'styles/width.json', make_style(old._json(paths['baseline'] / 'styles/width.json', 'baseline style')))
        finalization = {'schema_version': 1, 'status': 'passed', 'dataset_id': 'grwl-raw', 'display_release': RELEASE,
            'archive': archive, 'pmtiles_copy_mode': clone_mode, 'browser': browser,
            'source_asset': asset['source_asset'], 'source_fidelity_sha256': old._sha256(fidelity_path),
            'analytic_manifest_sha256': analytic['manifest_sha256'], 'criteria': criteria_pin,
            'finest_mask': {**mask, 'external_path': str(paths['finest_mask'].resolve()), 'bulk_mask_not_packaged': True},
            'historical_baseline': {'manifest_sha256': BASELINE_SHA,
                'archive_sha256': BASELINE_ARCHIVE_SHA, 'archive_size_bytes': BASELINE_ARCHIVE_SIZE,
                'external_binary_path': str((paths['baseline'] / ARCHIVE_REL).resolve()),
                'external_binary_not_packaged': True, 'nonbulk_chain': 'reports/baseline-r1'},
            'input_reports': report_pins, 'resources': resources(output),
            'publicly_published': False, 'hosted': False}
        old._write_json(output / 'reports/multiscale/finalization.json', finalization)
        (output / 'README.md').write_text('GRWL raw width observations and source-observation coverage\n\nLocal immutable display r2. Overview zooms 0–7 show occupied observation cells; detail zooms 8–12 retain native feature IDs, integer geometry and width values. Analytical GeoParquet is unchanged. The 304 documented r1 quantization collapses remain unchanged. No upload or public hosting is claimed.\n\nThe baseline r1 nonbulk evidence and manifest are retained under reports/baseline-r1. Its historical 11.5 GB PMTiles is external and is deliberately absent from this package; see reports/multiscale/finalization.json.\n')
        manifest = {'schema_version': 1, 'dataset_id': 'grwl-raw', 'display_release': RELEASE,
            'analytic_release': 'raw-v01.01-local-r1', 'source_rows': ROWS, 'source_tiles': SOURCE_TILES,
            'attribution': baseline['attribution'], 'source_license': baseline['source_license'],
            'assets': [asset], 'status': 'prepared'}
        (output / 'partial.json').unlink()
        manifest['files'] = old._inventory(output)
        old._atomic_json(output / 'manifest.json', manifest)
        return {'status': 'prepared', 'output': str(output.resolve()), 'manifest_sha256': old._sha256(output / 'manifest.json'), 'archive': archive}
    except BaseException as exc:
        old._write_json(output / 'failure.json', {'status': 'failed_partial', 'usable_release': False, 'error': f'{type(exc).__name__}: {exc}'})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.inputs, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
