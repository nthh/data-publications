"""Refuse altered/unbound GRWL r2 gates and preserve inventory safety."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grwl_multiscale_finalizer', ROOT / 'datasets/grwl-raw/finalize_multiscale.py')
final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final)


def pin(digest='a' * 64, size=1000):
    return {'sha256': digest, 'size_bytes': size}


def detail_report():
    return {'status': 'passed', 'semantic_preservation': True, 'tile_byte_gate': True, 'protobuf_implementation': 'upb',
        'source': pin(final.BASELINE_ARCHIVE_SHA, final.BASELINE_ARCHIVE_SIZE), 'candidate': pin(),
        'criteria': pin('c' * 64, 100), 'comparator': final.identity(ROOT / 'datasets/grwl-raw/compare_detail.py'),
        'counts': {'detail_tiles': 588355, 'by_zoom': dict(final.DETAIL_COUNTS), 'detail_features': 123456789,
            'detail_tiles_over_byte_limit': 0, 'maximum_gzip_tile_bytes': 65536}}


def source_report():
    bbox = [-180.0, 71.19728974037749, -179.99929548238572, 71.1973010125156]
    return {'status': 'passed', 'parquet_sha256': final.SOURCE_SHA, 'manifest_sha256': final.SOURCE_MANIFEST_SHA,
        'tiles': [{'tile': 'NR01', 'first_records': [{'source_tile': 'NR01', 'source_row': 1,
            'feature_id': (final.old._tile_code('NR01') << 32) | 1, 'bbox': bbox}]}]}


def browser_report():
    bbox = source_report()['tiles'][0]['first_records'][0]['bbox']
    center = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    nr01_id = (final.old._tile_code('NR01') << 32) | 1
    report = {'schema_version': 1, 'status': 'passed', 'errors': [],
        'runtime': {**pin(), 'dataset_id': 'grwl-raw', 'overview_source_layer': 'grwl_overview',
            'detail_min_zoom': 8, 'object_path': '/grwl.pmtiles'},
        'source_anchor': {'sha256': 'v' * 64, 'parquet_sha256': final.SOURCE_SHA,
            'tile': 'NR01', 'source_row': 1, 'feature_id': nr01_id, 'bbox': bbox, 'center': center},
        'transfer_policy': {'bytes_per_case': final.CASE_BYTES, 'enforced': True,
            'requested_range_bytes': True, 'response_body_bytes': True}, 'cases': []}
    fixed = [('global-z0', [0, 20], 0), ('amazon-z3', [-60, -3], 3),
        ('known-raw-15450-z7', [-108, 44.8], 7), ('overview-to-detail', [-108, 44.8], 7),
        ('nr01-first-record-z7', center, 7)]
    for name, center, zoom in fixed:
        checkpoints = [{'view': 'overview', 'zoom': zoom, 'center': center, 'actual_center': list(center),
            'rendered_layers': ['grwl_overview'], 'width_legend_hidden': True,
            'map_status': 'Source observation coverage'}]
        if name == 'overview-to-detail':
            checkpoints.append({'view': 'detail', 'zoom': 8, 'center': center, 'actual_center': list(center), 'rendered_layers': ['grwl_raw'],
                'width_legend_hidden': False, 'width_expression': ['get', 'width_m']})
        case = {'case_id': name, 'center': center, 'zoom': zoom, 'status': 'passed', 'checkpoints': checkpoints,
            'requests': [{'object_path': '/grwl.pmtiles', 'method': 'GET', 'status': 206,
                'range': 'bytes=0-99', 'content_range': 'bytes 0-99/1000', 'cors': '*', 'completed': True, 'body_bytes': 100}],
            'requested_range_bytes': 100, 'response_body_bytes': 100, 'transfer_ceiling_bytes': final.CASE_BYTES}
        if name == 'nr01-first-record-z7':
            case.update({'source_tile': 'NR01', 'source_row': 1, 'feature_id': nr01_id})
        report['cases'].append(case)
    return report


class GateTests(unittest.TestCase):
    def test_overview_identity_has_no_invented_source_ids(self):
        import gzip
        from unittest.mock import patch
        from mapbox_vector_tile.Mapbox import vector_tile_pb2 as mvt
        tile=mvt.tile();layer=tile.layers.add();layer.name='grwl_overview';layer.version=2;layer.extent=4096
        feature=layer.features.add();feature.type=3;feature.geometry.extend([9,0,0,26,16,0,0,16,15,0,15])
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'fake.pmtiles';archive.write_bytes(b'fixture')
            def tiles(_):return iter([((z,0,0),gzip.compress(tile.SerializeToString())) for z in range(8)])
            with patch('pmtiles.reader.MmapSource',return_value=None),patch('pmtiles.reader.all_tiles',side_effect=tiles):
                self.assertEqual(final.verify_overview_identity(archive)['ids_present'],0)
                feature.id=123
                with self.assertRaises(final.FinalizeError):final.verify_overview_identity(archive)
                feature.ClearField('id');feature.tags.extend([0,0])
                with self.assertRaises(final.FinalizeError):final.verify_overview_identity(archive)

    def test_fast_receipt_full_native_branch_and_changed_binary_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            binary = base / 'native-oracle'
            binary.write_bytes(b'Fixture binary identity; no execution')
            snapshot = base / 'detail_oracle.cpp'
            snapshot.write_bytes((ROOT / 'datasets/grwl-raw/detail_oracle.cpp').read_bytes())
            def native_descriptor(path):
                value = final.identity(path)
                return {'path': str(path), 'bytes': value['size_bytes'], 'sha256': value['sha256']}
            report = detail_report()
            report.update({'protobuf_implementation': 'independent_cpp_wire_v1',
                'comparator': native_descriptor(ROOT / 'datasets/grwl-raw/compare_detail_fast.py'),
                'directory_reader': native_descriptor(ROOT / 'datasets/grwl-raw/compare_detail.py'),
                'native_oracle': {'source': native_descriptor(ROOT / 'datasets/grwl-raw/detail_oracle.cpp'),
                    'source_snapshot': native_descriptor(snapshot), 'binary': native_descriptor(binary)}})
            final.validate_detail(report, pin(), pin('c' * 64, 100))
            binary.write_bytes(b'Changed after native comparison')
            with self.assertRaises(final.FinalizeError):
                final.validate_detail(report, pin(), pin('c' * 64, 100))

    def test_native_fast_bytes_descriptors_and_strict_identity_shapes(self):
        # compare_detail_fast's actual receipt uses bytes; finalizer inventory
        # uses size_bytes. Both sides must support both descriptor shapes.
        actual = final.identity(ROOT / 'datasets/grwl-raw/detail_oracle.cpp')
        native_pin = {'path': '/native/source_snapshot.cpp', 'bytes': actual['size_bytes'], 'sha256': actual['sha256']}
        final.bound(actual, native_pin, 'fast source snapshot')
        final.bound(native_pin, actual, 'fast binary')
        for bad in [{'sha256': actual['sha256'], 'bytes': True},
                    {'sha256': 'unbound', 'bytes': actual['size_bytes']},
                    {**native_pin, 'size_bytes': native_pin['bytes'] + 1}]:
            with self.assertRaises(final.FinalizeError):
                final.bound(actual, bad, 'malformed fast receipt')

    def test_actual_served_viewer_build_binding_refused_when_missing_or_changed(self):
        detail = {'inputs': {'viewer_build_sha256': pin()['sha256']}}
        multiscale = {'runtime': {'viewer_build_sha256': pin()['sha256']}}
        final.validate_viewer_binding(detail, multiscale, pin())
        for report in (detail['inputs'], multiscale['runtime']):
            saved = report['viewer_build_sha256']
            report['viewer_build_sha256'] = 'changed'
            with self.assertRaises(final.FinalizeError):
                final.validate_viewer_binding(detail, multiscale, pin())
            report['viewer_build_sha256'] = saved

    def test_detail_exact_global_passes(self):
        final.validate_detail(detail_report(), pin(), pin('c' * 64, 100))

    def test_detail_mutation_refusals(self):
        changes = [lambda r: r.update(semantic_preservation=False), lambda r: r['candidate'].update(sha256='bad'),
            lambda r: r['source'].update(sha256='bad'), lambda r: r['criteria'].update(sha256='bad'),
            lambda r: r['counts'].update(detail_tiles=588354), lambda r: r['counts']['by_zoom'].update({'12': 333537}),
            lambda r: r['counts'].update(maximum_gzip_tile_bytes=1048577), lambda r: r['comparator'].update(sha256='bad')]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                report = detail_report()
                mutate(report)
                with self.assertRaises(final.FinalizeError):
                    final.validate_detail(report, pin(), pin('c' * 64, 100))

    def test_detail_implementation_cannot_skip_native_bindings(self):
        for comparator, implementation in [('compare_detail.py', None),
                ('compare_detail.py', 'unexpected'), ('compare_detail.py', 'independent_cpp_wire_v1'),
                ('compare_detail_fast.py', None), ('compare_detail_fast.py', 'unexpected'),
                ('compare_detail_fast.py', 'upb'), ('compare_detail_fast.py', ['upb'])]:
            with self.subTest(comparator=comparator, implementation=implementation):
                report = detail_report()
                report['comparator'] = final.identity(ROOT / 'datasets/grwl-raw' / comparator)
                if implementation is None:
                    report.pop('protobuf_implementation')
                else:
                    report['protobuf_implementation'] = implementation
                with self.assertRaises(final.FinalizeError):
                    final.validate_detail(report, pin(), pin('c' * 64, 100))
        report = detail_report()
        report.update({'comparator': final.identity(ROOT / 'datasets/grwl-raw/compare_detail_fast.py'),
            'protobuf_implementation': 'independent_cpp_wire_v1'})
        with self.assertRaises(final.FinalizeError):
            final.validate_detail(report, pin(), pin('c' * 64, 100))

    def test_multiscale_browser_passes(self):
        final.validate_multiscale_browser(browser_report(), pin(), 'v' * 64, source_report())

    def test_multiscale_browser_identity_case_and_range_refusals(self):
        changes = [lambda r: r['runtime'].update(sha256='bad'), lambda r: r['source_anchor'].update(feature_id=1),
            lambda r: r['cases'][-1].update(feature_id=1), lambda r: r['cases'].pop(),
            lambda r: r['cases'][0].update(zoom=7), lambda r: r['cases'][0]['checkpoints'][0].update(zoom=7),
            lambda r: r['cases'][0]['requests'][0].update(status=200),
            lambda r: r['cases'][0]['requests'][0].update(content_range='bytes 0-99/999'),
            lambda r: r['cases'][0].update(response_body_bytes=99),
            lambda r: r['cases'][3]['checkpoints'].pop(), lambda r: r.update(errors=['page failure'])]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                report = browser_report()
                mutate(report)
                with self.assertRaises(final.FinalizeError):
                    final.validate_multiscale_browser(report, pin(), 'v' * 64, source_report())

    def test_actual_browser_center_required_for_every_checkpoint(self):
        for case_index, checkpoint_index in [(0, 0), (3, 0), (3, 1), (4, 0)]:
            for actual_center in (None, [], [0], [0, 20, 1], ['0', 20], [False, 20],
                    [float('nan'), 20], [0, float('inf')], [0, 0]):
                with self.subTest(case=case_index, checkpoint=checkpoint_index, actual_center=actual_center):
                    report = browser_report()
                    checkpoint = report['cases'][case_index]['checkpoints'][checkpoint_index]
                    if actual_center is None:
                        checkpoint.pop('actual_center')
                    else:
                        checkpoint['actual_center'] = actual_center
                    with self.assertRaisesRegex(final.FinalizeError, 'actual center'):
                        final.validate_multiscale_browser(report, pin(), 'v' * 64, source_report())
        report = browser_report()
        report['cases'][0]['checkpoints'][0]['actual_center'][0] += 2e-8
        with self.assertRaises(final.FinalizeError):
            final.validate_multiscale_browser(report, pin(), 'v' * 64, source_report())

    def test_actual_browser_center_allows_only_the_frozen_tolerance(self):
        report = browser_report()
        report['cases'][0]['checkpoints'][0]['actual_center'][0] = 1e-8
        report['cases'][0]['checkpoints'][0]['actual_center'][1] -= 0.5e-8
        final.validate_multiscale_browser(report, pin(), 'v' * 64, source_report())

    def test_nr01_anchor_cannot_move_with_its_reported_checkpoints(self):
        report = browser_report()
        report['source_anchor'].update({'bbox': [0, 0, 0, 0], 'center': [0, 0]})
        report['cases'][-1]['center'] = [0, 0]
        for checkpoint in report['cases'][-1]['checkpoints']:
            checkpoint['center'] = [0, 0]
        with self.assertRaisesRegex(final.FinalizeError, 'source identity/bbox/center'):
            final.validate_multiscale_browser(report, pin(), 'v' * 64, source_report())
        report = browser_report()
        report['source_anchor']['bbox'][0] += 0.001
        with self.assertRaises(final.FinalizeError):
            final.validate_multiscale_browser(report, pin(), 'v' * 64, source_report())

    def test_nr01_source_evidence_is_required_and_real_schema_works(self):
        evidence = source_report()
        for mutate in [lambda r: r.update(parquet_sha256='bad'), lambda r: r.update(manifest_sha256='bad'),
                lambda r: r['tiles'].clear(), lambda r: r['tiles'].append(deepcopy(r['tiles'][0])),
                lambda r: r['tiles'][0]['first_records'].clear(),
                lambda r: r['tiles'][0]['first_records'][0].update(source_row=2),
                lambda r: r['tiles'][0]['first_records'][0].update(bbox=[0, 0, float('nan'), 0])]:
            with self.subTest(mutate=mutate):
                changed = deepcopy(evidence)
                mutate(changed)
                with self.assertRaises(final.FinalizeError):
                    final.validate_multiscale_browser(browser_report(), pin(), 'v' * 64, changed)
        # Actual frozen producer-report shape and exact floating-point bounds.
        real = final.old._json(ROOT / 'research/grwl-raw-release-20261102/global-source-validation-r1.json', 'frozen source report')
        final.validate_multiscale_browser(browser_report(), pin(), 'v' * 64, real)

    def test_archive_size_checked_before_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'too-big.pmtiles'
            with archive.open('wb') as stream:
                stream.truncate(final.MAX_ARCHIVE_BYTES + 1)
            with patch.object(final, 'identity', side_effect=AssertionError('Must refuse before hashing')):
                with self.assertRaises(final.FinalizeError):
                    final.archive_identity(archive)

    def test_asset_keeps_native_detail_primary_and_one_analytic_binding(self):
        asset = final.make_asset(pin())
        self.assertEqual((asset['source_layer'], asset['geometry_type'], asset['id_encoding']), ('grwl_raw', 'line', 'mvt_feature_id'))
        self.assertEqual((asset['min_zoom'], asset['max_zoom'], asset['detail_min_zoom']), (0, 12, 8))
        self.assertEqual(asset['attribute_fields'], ['width_m', 'width_valid'])
        self.assertEqual(asset['source_asset']['path'], 'assets/grwl-raw-observations.parquet')
        self.assertEqual(asset['overview']['max_zoom'], 7)
        self.assertFalse(asset['overview']['has_feature_ids'])

    def test_primary_style_order_and_relative_archive(self):
        style = final.make_style(final.old._json(ROOT / 'datasets/grwl-raw/display/raw-v01.01-display-r1/styles/width.json', 'fixture style'))
        self.assertEqual(style['layers'][0]['type'], 'line')
        self.assertEqual(style['layers'][0]['minzoom'], 8)
        self.assertEqual(style['layers'][1]['type'], 'fill')
        self.assertEqual(style['layers'][1]['maxzoom'], 8)
        self.assertEqual(style['sources']['data']['url'], '../assets/grwl-raw.pmtiles')


class OverviewGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source_manifest = Path(self.tmp.name) / 'manifest.json'
        self.criteria = final.old._json(final.RESEARCH / 'criteria.json', 'fixture criteria')
        tiles = [{'tile': tile, 'records': 3} for tile in self.criteria['heldout_source_tiles']]
        tiles += [{'tile': 'AA01', 'records': 100}, {'tile': 'AA02', 'records': 100}]
        self.source_manifest.write_text(json.dumps({'parquet_sha256': final.SOURCE_SHA, 'rows': 224, 'tiles': tiles}))
        self.source_manifest_sha = final.old._sha256(self.source_manifest)
        self.expected = {tile['tile']: min(32, tile['records']) for tile in tiles}
        self.mask = pin('d' * 64, 536870912)
        self.criteria_pin = final.identity(final.RESEARCH / 'criteria.json')
        chash = final.canonical_criteria_hash(self.criteria)
        per_zoom = [{'zoom': z, 'tiles': 1, 'maximum_tile_bytes': 100} for z in range(8)]
        self.build = {'status': 'built_unvalidated', 'source_sha256': final.SOURCE_SHA,
            'source_manifest_sha256': self.source_manifest_sha, 'rows': 224,
            'criteria_sha256': self.criteria_pin['sha256'], 'extent': 4096, 'cells_per_tile': 512,
            'artifacts': {'masks/z7.bin': self.mask}, 'per_zoom': per_zoom}
        oracle_sha = final.old._sha256(ROOT / 'datasets/grwl-raw/validate_overview.py')
        self.archive_oracle = {'status': 'passed', 'archive_sha256': pin()['sha256'],
            'finest_mask_sha256': self.mask['sha256'], 'mask_bitorder': 'little',
            'criteria_json_sha256': chash, 'largest_gzip_tile_bytes': 100,
            'tiles_by_zoom': {str(z): 1 for z in range(8)}, 'oracle_sha256': oracle_sha}
        self.source_oracle = {'status': 'passed', 'source_sha256': final.SOURCE_SHA,
            'source_manifest_sha256': self.source_manifest_sha, 'criteria_json_sha256': chash,
            'finest_mask_sha256': self.mask['sha256'], 'records': 88, 'records_by_tile': self.expected,
            'heldout_tiles': sorted(self.criteria['heldout_source_tiles']),
            'selection': self.criteria['overview']['independent_source_controls'],
            'subset_missing_cells': 0, 'subset_extra_cells': 0, 'global_missing_cells': 0, 'failures': [],
            'oracle_sha256': oracle_sha,
            'production_module_sha256': final.old._sha256(ROOT / 'datasets/grwl-raw/build_overview.py')}

    def check(self):
        with patch.multiple(final, ROWS=224, SOURCE_TILES=10, SOURCE_ORACLE_RECORDS=88, SOURCE_MANIFEST_SHA=self.source_manifest_sha):
            final.validate_overview(self.build, self.archive_oracle, self.source_oracle, pin(), self.mask,
                self.source_manifest, self.criteria, self.criteria_pin)

    def test_source_and_archive_bound_to_same_mask_pass(self):
        self.check()

    def test_mask_source_sampling_and_tile_coverage_refused(self):
        for key, value in [('finest_mask_sha256', 'bad'), ('source_sha256', 'bad'), ('records', 87),
                           ('global_missing_cells', 1), ('production_module_sha256', 'bad')]:
            with self.subTest(key=key):
                saved = deepcopy(self.source_oracle)
                self.source_oracle[key] = value
                with self.assertRaises(final.FinalizeError):
                    self.check()
                self.source_oracle = saved
        self.source_oracle['records_by_tile']['NH11'] = 2
        with self.assertRaises(final.FinalizeError):
            self.check()


class InventoryTests(unittest.TestCase):
    def test_failed_staging_kept_without_prepared_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            source.write_text('{}')
            baseline = root / 'baseline'
            baseline.mkdir()
            (baseline / 'manifest.json').write_text('{}')
            analytic = root / 'analytic'
            analytic.mkdir()
            keys = ('archive', 'detail_report', 'overview_build', 'overview_archive_report',
                    'overview_source_report', 'finest_mask', 'browser_detail_report', 'browser_multiscale_report', 'viewer_build', 'clean_replay_report')
            mapping = root / 'inputs.json'
            mapping.write_text(json.dumps({**{key: str(source) for key in keys}, 'baseline': str(baseline), 'analytic_package': str(analytic)}))
            output = root / 'failed-output'
            class Disk:
                free = 50 * 1024 ** 3
            with patch.object(final.shutil, 'disk_usage', return_value=Disk()):
                with self.assertRaises(final.FinalizeError):
                    final.finalize(mapping, output)
            self.assertEqual(json.loads((output / 'failure.json').read_text())['status'], 'failed_partial')
            self.assertTrue((output / 'partial.json').exists())
            self.assertFalse((output / 'manifest.json').exists())

    def test_inventory_binds_all_files_except_manifest_and_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text('{}')
            (root / 'evidence.json').write_text('bound bytes')
            inventory = final.old._inventory(root)
            self.assertEqual(set(inventory), {'evidence.json'})
            self.assertEqual(inventory['evidence.json'], final.identity(root / 'evidence.json'))
            (root / 'alias').symlink_to(root / 'evidence.json')
            with self.assertRaises(final.FinalizeError):
                final.old._inventory(root)

    def test_existing_output_and_invalid_mapping_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping = root / 'inputs.json'
            mapping.write_text('{}')
            with self.assertRaises(final.FinalizeError):
                final.finalize(mapping, root)
            with self.assertRaises(final.FinalizeError):
                final.finalize(mapping, root / 'new')
            self.assertFalse((root / 'new').exists())


class CleanReplayGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        actual_contract = final.load_module('replay_test_contract', final.RESEARCH / 'run_clean_replay.py')
        def file_pin(name, content):
            path = self.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return {'path': str(path), **final.identity(path)}
        references = {key: file_pin('reference/' + key, key.encode()) for key in
            ('source', 'source_manifest', 'detail', 'overview_archive', 'combined_archive', 'overview_build',
             'display_manifest', 'display_provenance', 'overview_oracle', 'detail_oracle', 'viewer_build')}
        references['overview_masks'] = {f'masks/z{z}.bin': file_pin(f'reference/masks/z{z}.bin', str(z).encode()) for z in range(8)}
        references['viewer_files'] = {'app.js': file_pin('reference/app.js', b'served UI fixture')}
        artifacts = {}
        for key in ('overview_archive', 'combined_archive', 'overview_build', 'display_manifest', 'display_provenance', 'viewer_build'):
            artifacts[key] = file_pin('new/' + key, Path(references[key]['path']).read_bytes())
        for key in ('overview_masks', 'viewer_files'):
            artifacts[key] = {rel: file_pin('new/' + rel, Path(value['path']).read_bytes()) for rel, value in references[key].items()}
        self.viewer = references['viewer_build']
        self.contract = SimpleNamespace(SOURCE_SHA=references['source']['sha256'], SOURCE_MANIFEST_SHA=references['source_manifest']['sha256'],
            DETAIL_SHA=references['detail']['sha256'], OVERVIEW_SHA=references['overview_archive']['sha256'], COMBINED_SHA=references['combined_archive']['sha256'],
            SOURCE_ROWS=actual_contract.SOURCE_ROWS, SOURCE_TILES=actual_contract.SOURCE_TILES,
            MASK_SHAS={rel: value['sha256'] for rel, value in references['overview_masks'].items()}, code_pins=actual_contract.code_pins)
        self.report = {'schema_version': 1, 'status': 'passed', 'clean_checkout': {'commit': 'a' * 40,
            'before': '', 'after': '', 'after_commit': 'a' * 40}, 'source_rows': self.contract.SOURCE_ROWS,
            'source_tiles': self.contract.SOURCE_TILES, 'code_files': self.contract.code_pins(),
            'byte_equal': {key: True for key in ('overview_archive', 'combined_archive', 'viewer_build', 'overview_masks', 'viewer_files')},
            'viewer_build_sha256': self.viewer['sha256'], 'references': references, 'artifacts': artifacts,
            'stages': [{'name': name, 'returncode': 0, 'log': file_pin(name + '.log', b'completed fixture stage')}
                for name in ('overview', 'native-repack', 'viewer')]}

    def check(self):
        # Replace only frozen source/reference pins with tiny fixture pins;
        # current code hashes and all file-byte checks remain real.
        with patch.object(final, 'load_module', return_value=self.contract):
            final.validate_clean_replay(self.report, self.viewer)

    def test_bound_clean_byte_equal_replay_passes(self):
        self.check()

    def test_changed_ui_code_cleanliness_and_equality_refused(self):
        changes = [lambda r: r.update(viewer_build_sha256='bad'),
            lambda r: r['clean_checkout'].update(before=' M changed.py\n'),
            lambda r: r['clean_checkout'].update(after='?? new-file\n'),
            lambda r: r['clean_checkout'].update(after_commit='b' * 40),
            lambda r: r['byte_equal'].update(viewer_files=False),
            lambda r: r['code_files'].update({'datasets/grwl-raw/finalize_multiscale.py': 'bad'}),
            lambda r: r['references']['source'].update(sha256='0' * 64),
            lambda r: r['artifacts']['overview_masks'].pop('masks/z7.bin'),
            lambda r: r['stages'].pop()]
        original = deepcopy(self.report)
        for mutate in changes:
            with self.subTest(mutate=mutate):
                self.report = deepcopy(original)
                mutate(self.report)
                with self.assertRaises(final.FinalizeError):
                    self.check()
        self.report = original
        Path(self.report['artifacts']['viewer_files']['app.js']['path']).write_bytes(b'Changed after replay')
        with self.assertRaises(final.FinalizeError):
            self.check()

    def test_missing_replay_input_is_mandatory(self):
        path = self.base / 'mapping.json'
        path.write_text(json.dumps({key: self.report['references']['source']['path'] for key in
            ('archive', 'baseline', 'analytic_package', 'detail_report', 'overview_build', 'overview_archive_report',
             'overview_source_report', 'finest_mask', 'browser_detail_report', 'browser_multiscale_report', 'viewer_build')}))
        with self.assertRaisesRegex(final.FinalizeError, 'Missing explicit finalizer input paths'):
            final.finalize(path, self.base / 'new-output')
        self.assertFalse((self.base / 'new-output').exists())


if __name__ == '__main__':
    unittest.main()
