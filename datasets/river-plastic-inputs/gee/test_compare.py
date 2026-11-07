#!/usr/bin/env python3
"""Fault tests for geometry, numeric, coincident-group and capture-integrity gates."""
import argparse
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

import pyarrow as pa
from pyproj import Geod

from compare import (HERE, PRODUCT, allowance, compare, digest, read_capture,
                     verify_capture_source)


def fixture(points=None, estimates=None):
    points = points or [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
    estimates = estimates or [Decimal('1'), Decimal('2'), None]
    areas = [Decimal('20000000000000.123456'), Decimal('100'), Decimal('200')]
    table = pa.table({
        'source_row': pa.array([1, 2, 3], type=pa.int32()),
        'i_mid': pa.array(estimates, type=pa.decimal128(28, 6)),
        'area': pa.array(areas, type=pa.decimal128(28, 6)),
        'geometry': pa.array([struct.pack('<BIdd', 1, 1, *point) for point in points]),
    })
    features = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': list(point)},
                 'properties': {'i_mid': estimates[i], 'area': areas[i]}} for i, point in enumerate(points)]
    contract = {'expected_fields': 2, 'expected_rows': 3, 'coverage': 'Synthetic adversarial fixture',
                'matching': {'coordinate_absolute_tolerance_degrees': '0.00000001'}}
    diagnostic = {'candidate_lookup': {'bin_width_degrees': '0.0001', 'maximum_absolute_latitude': 61},
                  'matching_radius_meters': 1}
    return table, features, contract, diagnostic


class ContentChecks(unittest.TestCase):
    def test_order_independence(self):
        table, features, contract, _ = fixture()
        result = compare(table, features[::-1], contract)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['attribute_cells_compared'], 6)

    def test_null_moved_with_count_and_sum_preserved(self):
        table, features, contract, _ = fixture()
        features[0]['properties']['i_mid'], features[2]['properties']['i_mid'] = None, Decimal(1)
        result = compare(table, features, contract)
        self.assertTrue(result['null_counts_match'])
        self.assertEqual(result['emission_totals']['i_mid']['status'], 'passed')
        self.assertEqual(result['mismatch_counts']['null_mismatch'], 2)
        self.assertEqual(result['status'], 'failed')

    def test_balanced_wrong_values_cannot_hide_in_totals(self):
        table, features, contract, _ = fixture()
        features[0]['properties']['i_mid'] += 1
        features[1]['properties']['i_mid'] -= 1
        result = compare(table, features, contract)
        self.assertEqual(result['emission_totals']['i_mid']['status'], 'passed')
        self.assertEqual(result['mismatch_counts']['value_mismatch'], 2)
        self.assertEqual(result['status'], 'failed')

    def test_invalid_numeric_representations(self):
        for value in (True, '1', float('nan'), float('inf')):
            with self.subTest(value=str(value)):
                table, features, contract, _ = fixture()
                features[0]['properties']['i_mid'] = value
                self.assertEqual(compare(table, features, contract)['status'], 'failed')

    def test_decimal_tolerance_boundary(self):
        for delta, expected in ((Decimal('0.0000005'), 'passed'), (Decimal('0.000000500001'), 'failed')):
            with self.subTest(delta=delta):
                table, features, contract, _ = fixture()
                features[0]['properties']['i_mid'] += delta
                self.assertEqual(compare(table, features, contract)['status'], expected)

    def test_large_value_binary64_boundary(self):
        for extra, expected in ((Decimal(0), 'passed'), (Decimal('0.000001'), 'failed')):
            table, features, contract, _ = fixture()
            original = features[0]['properties']['area']
            features[0]['properties']['area'] += allowance(original, 6) + extra
            self.assertEqual(compare(table, features, contract)['status'], expected)
        with self.assertRaises(ValueError):
            allowance(Decimal('1e400'), 6)

    def test_duplicate_feature_cannot_replace_missing_point(self):
        table, features, contract, _ = fixture()
        features[1] = copy.deepcopy(features[0])
        result = compare(table, features, contract)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['mismatch_counts']['duplicate_geometry_assignment'], 1)
        self.assertEqual(result['unmatched_source_rows'], [2])

    def test_strict_geometry_boundary(self):
        for delta, expected in ((1e-8, 'passed'), (1.01e-8, 'failed')):
            table, features, contract, _ = fixture()
            features[0]['geometry']['coordinates'][0] += delta
            self.assertEqual(compare(table, features, contract)['status'], expected)

    def test_geodesic_bound_and_preserved_strict_failure(self):
        for meters, expected in ((0.4, 'passed'), (1.1, 'failed')):
            table, features, contract, diagnostic = fixture()
            x, y, _ = Geod(ellps='WGS84').fwd(0, 0, 90, meters)
            features[0]['geometry']['coordinates'] = [x, y]
            self.assertEqual(compare(table, features, contract)['status'], 'failed')
            result = compare(table, features, contract, geometry_diagnostic=diagnostic)
            self.assertEqual(result['status'], expected)
            if expected == 'passed':
                self.assertAlmostEqual(result['geodesic_displacement_meters']['maximum'], meters, places=6)

    def test_exact_coincident_group_preserves_multiplicity(self):
        table, features, contract, diagnostic = fixture([(0, 0), (0, 0), (2, 2)])
        self.assertEqual(compare(table, features, contract, geometry_diagnostic=diagnostic)['status'], 'failed')
        result = compare(table, features[::-1], contract, geometry_diagnostic=diagnostic, coincident_groups=True)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['uniquely_matched_points'], 1)
        self.assertEqual(result['coincident_records_verified'], 2)
        features[1] = copy.deepcopy(features[0])
        self.assertEqual(compare(table, features, contract, geometry_diagnostic=diagnostic, coincident_groups=True)['status'], 'failed')

    def test_changed_group_tuple_and_null_to_zero_fail(self):
        for name, value in (('area', Decimal(1)), ('i_mid', Decimal(0))):
            table, features, contract, diagnostic = fixture([(0, 0), (0, 0), (2, 2)], [Decimal(1), None, Decimal(2)])
            features[1]['properties'][name] = value
            result = compare(table, features, contract, geometry_diagnostic=diagnostic, coincident_groups=True)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('coincident_group_multiset_mismatch', result['mismatch_counts'])

    def test_distinct_nearby_coordinates_remain_ambiguous(self):
        table, features, contract, diagnostic = fixture([(0, 0), (0.000004, 0), (2, 2)])
        result = compare(table, features, contract, geometry_diagnostic=diagnostic, coincident_groups=True)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['coincident_groups_verified'], 0)
        self.assertEqual(result['mismatch_counts']['ambiguous_geometry'], 2)

    def test_group_invalid_types_and_extra_records_fail(self):
        for fault in ('boolean', 'extra'):
            table, features, contract, diagnostic = fixture([(0, 0), (0, 0), (2, 2)])
            if fault == 'boolean':
                features[0]['properties']['i_mid'] = True
            else:
                features.append(copy.deepcopy(features[0]))
            self.assertEqual(compare(table, features, contract, geometry_diagnostic=diagnostic, coincident_groups=True)['status'], 'failed')


class CaptureChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='folia-gee-validation-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.contract = {'asset_id': 'fixture', 'rest_asset_name': 'projects/test/assets/fixture', 'quota_project': 'test',
                         'api': 'https://example.invalid/', 'request_limits': {'maximum_feature_pages': 3, 'maximum_total_response_bytes': 100000,
                                                                             'page_size': 1000, 'maximum_rows': 10}}
        url = self.contract['api'] + self.contract['rest_asset_name']
        metadata = {'type': 'TABLE', 'name': self.contract['rest_asset_name']}
        self.bodies = [metadata, {'type': 'FeatureCollection', 'features': [{}], 'nextPageToken': 'next'},
                       {'type': 'FeatureCollection', 'features': [{}]}, dict(metadata)]
        self.receipt = {'status': 'complete', 'contract_sha256': 'contract', 'asset_id': 'fixture',
                        'rest_asset_name': self.contract['rest_asset_name'], 'quota_project': 'test', 'requests': [],
                        'metadata_stable': True, 'total_rows': 2, 'feature_pages': 2}
        for name, params in [('metadata-before.json', {}), ('features-001.json', {'pageSize': 1000}),
                             ('features-002.json', {'pageSize': 1000, 'pageToken': 'next'}), ('metadata-after.json', {})]:
            self.receipt['requests'].append({'response_path': name, 'method': 'GET', 'http_status': 200,
                                            'url': url + (':listFeatures' if name.startswith('features') else ''), 'params': params})
        self.save()

    def save(self):
        size = 0
        for body, request in zip(self.bodies, self.receipt['requests']):
            path = self.folder / request['response_path']
            path.write_text(json.dumps(body))
            request['response_sha256'] = digest(path)
            request['response_bytes'] = path.stat().st_size
            size += path.stat().st_size
        self.receipt['total_response_bytes'] = size
        (self.folder / 'capture.json').write_text(json.dumps(self.receipt))

    def load(self):
        return read_capture(self.folder, self.contract, 'contract')

    def test_complete_capture(self):
        _, _, features = self.load()
        self.assertEqual(len(list(features)), 2)

    def test_tampered_bytes(self):
        with (self.folder / 'features-001.json').open('a') as stream:
            stream.write(' ')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.load()

    def test_skipped_page_token(self):
        self.receipt['requests'][2]['params']['pageToken'] = 'wrong'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Pagination'):
            self.load()

    def test_unterminated_page_chain(self):
        self.bodies[2]['nextPageToken'] = 'more'
        self.save()
        with self.assertRaisesRegex(ValueError, 'continuation token'):
            self.load()

    def test_changed_asset_metadata(self):
        self.bodies[-1]['updateTime'] = 'changed'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Asset changed'):
            self.load()

    def test_incomplete_capture(self):
        self.receipt['status'] = 'incomplete'
        self.save()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.load()


class CaptureSourceProvenanceChecks(unittest.TestCase):
    historical_path = 'commons/publish/gee-community/products/river-plastic-inputs/gee/fetch.py'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='folia-gee-provenance-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.provenance = self.root / 'provenance'
        (self.provenance / 'blobs').mkdir(parents=True)
        self.index = self.provenance / 'index.json'
        self.payload = b'historical capture script\n'
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.blob = self.provenance / 'blobs' / self.sha
        self.blob.write_bytes(self.payload)
        self.entry = {'path': self.historical_path, 'role': 'python', 'bytes': len(self.payload),
                      'sha256': self.sha, 'snapshot': 'test', 'git_revision': 'test-revision',
                      'blob': f'blobs/{self.sha}'}
        self.save_index()

    def save_index(self):
        self.index.write_text(json.dumps({'schema_version': 1, 'files': [self.entry]}))

    def resolve(self):
        return verify_capture_source(self.sha, HERE / 'fetch.py', self.historical_path,
                                     'python', self.index)

    def test_current_source_is_verified_directly(self):
        result = verify_capture_source(digest(HERE / 'fetch.py'), HERE / 'fetch.py',
                                       self.historical_path, 'python', self.index)
        self.assertEqual(result['source'], 'current')

    def test_indexed_historical_blob_is_verified(self):
        result = self.resolve()
        self.assertEqual(result['source'], 'historical-provenance-blob')
        self.assertEqual(result['sha256'], self.sha)

    def test_missing_inventory_entry_fails_closed(self):
        self.index.write_text(json.dumps({'schema_version': 1, 'files': []}))
        with self.assertRaisesRegex(ValueError, 'neither current nor in provenance inventory'):
            self.resolve()

    def test_corrupt_historical_blob_fails_closed(self):
        self.blob.write_bytes(b'corrupted historical script')
        with self.assertRaisesRegex(ValueError, 'byte count mismatch|SHA-256 mismatch'):
            self.resolve()

    def test_inventory_cannot_redirect_blob(self):
        self.entry['blob'] = 'blobs/other'
        self.save_index()
        with self.assertRaisesRegex(ValueError, 'blob path does not match'):
            self.resolve()

    def test_wrong_role_or_original_path_fails_closed(self):
        self.entry['role'] = 'environment'
        self.save_index()
        with self.assertRaisesRegex(ValueError, 'neither current nor in provenance inventory'):
            self.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case) for case in (
        ContentChecks, CaptureChecks, CaptureSourceProvenanceChecks))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'status': 'passed' if result.wasSuccessful() else 'failed', 'tests_run': result.testsRun,
              'failures': [str(case) for case, _ in result.failures], 'errors': [str(case) for case, _ in result.errors],
              'scope': 'Offline synthetic fault cases; no network or cloud calls.',
              'provenance': {'comparator_sha256': digest(HERE / 'compare.py'),
                             'test_script_sha256': digest(Path(__file__)), 'environment_lock_sha256': digest(PRODUCT / 'uv.lock')}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
