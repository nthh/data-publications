"""Offline fault tests for the GEE sample comparator."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'gee_validation'))
import compare


def dump(path, value):
    path.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')
    return path


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, *, dataset='hydrolakes', locals_=None, gees=None, fields=None):
        case = Path(tempfile.mkdtemp(dir=self.tmp))
        if locals_ is None:
            locals_ = [{'local_id': 1, 'properties': {'Hylak_id': 1, 'area': 3.5, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1., 2.]}, 'row_group': 0, 'row_offset': 0}]
        if fields is None:
            fields = {'Hylak_id': {'type': 'int64', 'role': 'source', 'gee_aliases': []}, 'area': {'type': 'double', 'role': 'source', 'gee_aliases': []}, 'name': {'type': 'string', 'role': 'source', 'gee_aliases': []}, 'source_row': {'type': 'int64', 'role': 'derived', 'gee_aliases': []}}
        if gees is None:
            gees = [{'type': 'Feature', 'id': 'stable-1', 'properties': {'Hylak_id': 1, 'area': 3.5, 'name': None, 'extra': 'ok'}, 'geometry': {'type': 'MultiPoint', 'coordinates': [[1., 2.]]}}]
        source = {'parquet_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64, 'row_count': 2 if dataset == 'grwl-raw' else 1}
        keys = ['lon', 'lat', 'segmentID', 'segmentInd'] if dataset == 'grwl-raw' else ['Hylak_id']
        sample = {'schema_version': 1, 'dataset_id': dataset, 'source': source, 'key_fields': keys, 'fields': fields, 'features': locals_}
        sample_path = dump(case / 'sample.json', sample)
        criteria_path = dump(case / 'criteria.json', {'schema_version': 1, 'matching': {'frozen': True}})
        sample['criteria_sha256'] = hashlib.sha256(criteria_path.read_bytes()).hexdigest()
        sample_path = dump(case / 'sample.json', sample)
        requests = []
        for qid, resource, params, paginate in [(f'{dataset}-before', 'asset', {}, False), (f'{dataset}-count', 'asset', {}, False), (f'{dataset}-features-000', 'asset:listFeatures', {'region': 'region'}, True), (f'{dataset}-after', 'asset', {}, False)]:
            req = {'id': qid, 'resource': resource, 'params': params, 'paginate': paginate}
            if qid.endswith('-count'):
                req['operation'] = 'count'
            if dataset == 'grwl-raw' and 'features' in qid:
                req['selected_local_ids'] = [str(f['local_id']) for f in locals_]
            requests.append(req)
        plan = {'schema_version': 1, 'dataset_id': dataset, 'quota_project': 'test-project', 'sample_sha256': hashlib.sha256(sample_path.read_bytes()).hexdigest(), 'criteria_sha256': hashlib.sha256(criteria_path.read_bytes()).hexdigest(), 'requests': requests}
        plan_path = dump(case / 'plan.json', plan)
        plan['sample_sha256'] = hashlib.sha256(sample_path.read_bytes()).hexdigest()
        plan_path = dump(case / 'plan.json', plan)
        cap = case / 'capture'
        cap.mkdir()
        responses = {f'{dataset}-before': {'id': 'asset', 'properties': {'version': 1}}, f'{dataset}-count': {'result': source['row_count']}, f'{dataset}-features-000': {'features': gees}, f'{dataset}-after': {'id': 'asset', 'properties': {'version': 1}}}
        receipt_requests, receipt_queries = [], []
        for qid, payload in responses.items():
            data = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()
            name = f'{qid}-001.json'
            (cap / name).write_bytes(data)
            req = next(x for x in requests if x['id'] == qid)
            item = {'query': qid, 'method': 'POST' if req.get('operation') == 'count' else 'GET', 'resource': req['resource'], 'params': req['params'], 'response_path': name, 'http_status': 200, 'response_bytes': len(data), 'response_sha256': hashlib.sha256(data).hexdigest()}
            if req.get('operation') == 'count':
                item['endpoint_resource'] = 'projects/test-project/value:compute'
                item['body'] = {'expression': {'result': '0', 'values': {'0': {'functionInvocationValue': {'functionName': 'Collection.size', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'Collection.loadTable', 'arguments': {'tableId': {'constantValue': req['resource']}}}}}}}}}}
            receipt_requests.append(item)
            receipt_queries.append({'id': qid, 'pagination_terminated': True, 'complete_enumeration': True})
        dump(cap / 'capture.json', {'schema_version': 1, 'status': 'complete', 'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(), 'requests': receipt_requests, 'queries': receipt_queries})
        return sample_path, sample, cap, plan_path, criteria_path, plan

    def compare_fixture(self, **kwargs):
        sample_path, sample, cap, plan_path, criteria_path, plan = self.fixture(**kwargs)
        criteria = json.loads(criteria_path.read_text())
        return compare.build_report(sample_path, sample, cap, plan_path, plan, criteria_path, criteria)

    def test_valid_binding_and_singleton_multipart_geometry_passes(self):
        report = self.compare_fixture()
        self.assertEqual(report['status'], 'sampled_pass')
        self.assertEqual(report['geometry']['strict_pass'], 1)
        self.assertIn('source_row', report['fields']['excluded'])
        self.assertEqual(report['fields']['source']['area']['coverage'], 1)

    def test_tampered_capture_hash_and_sample_binding_fail(self):
        sp, sample, cap, pp, cp, plan = self.fixture()
        (cap / 'hydrolakes-count-001.json').write_text('{"result":2}')
        plan['sample_sha256'] = '0' * 64
        dump(pp, plan)
        report = compare.build_report(sp, sample, cap, pp, plan, cp, json.loads(cp.read_text()))
        issues = ' '.join(report['capture_validation']['issues'])
        self.assertIn('hash/size mismatch', issues)
        self.assertIn('sample SHA-256', issues)
        self.assertEqual(report['status'], 'invalid_capture_or_binding')

    def test_missing_selected_id_and_conflicting_duplicate_gee_id_fail(self):
        local = [{'local_id': 1, 'properties': {'Hylak_id': 1, 'area': 3.5, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}, 'row_group': 0, 'row_offset': 0}]
        gee = [{'type': 'Feature', 'id': 'same', 'properties': {'Hylak_id': 2, 'area': 3.5, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}}, {'type': 'Feature', 'id': 'same', 'properties': {'Hylak_id': 1, 'area': 3.5, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}}]
        report = self.compare_fixture(locals_=local, gees=gee)
        issues = ' '.join(report['capture_validation']['issues'])
        self.assertIn('conflicting duplicate GEE feature id same', issues)
        self.assertIn('missing selected Hylak_id 1', issues)
        self.assertEqual(report['identity']['missing_sample_count'], 1)

    def test_null_zero_bool_and_numeric_string_are_not_coerced(self):
        for gee in (0, False, '3.5'):
            with self.subTest(gee=gee):
                local = [{'local_id': 1, 'properties': {'Hylak_id': 1, 'area': None, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}, 'row_group': 0, 'row_offset': 0}]
                features = [{'type': 'Feature', 'id': 'stable-1', 'properties': {'Hylak_id': 1, 'area': gee, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}}]
                report = self.compare_fixture(locals_=local, gees=features)
                self.assertFalse(report['attributes']['pass'])
                self.assertEqual(report['attributes']['mismatch_count'], 1)

    def test_integer_precision_float32_and_decimal_rules(self):
        self.assertFalse(compare.compare_value(2**53 + 1, float(2**53 + 1), 'int64')[0])
        self.assertTrue(compare.compare_value(1.2000000476837158, 1.2, 'float32')[0])
        self.assertFalse(compare.compare_value(1.2, 1.2001, 'float32')[0])
        self.assertFalse(compare.compare_value(1.234567890123, '1.234567890123', 'double')[0])
        self.assertTrue(compare.compare_value('1.000000000000000001', 1.0, 'decimal128(38,18)')[0])

    def test_changed_width_and_geometry_strict_failure_with_diagnostic(self):
        local = [{'local_id': 1, 'properties': {'Hylak_id': 1, 'area': 3.5, 'name': None, 'Shape_Length': 10.0}, 'geometry': {'type': 'LineString', 'coordinates': [[0, 0], [1, 0]]}, 'row_group': 0, 'row_offset': 0}]
        fields = {'Hylak_id': {'type': 'int64', 'role': 'source'}, 'area': {'type': 'double', 'role': 'source'}, 'name': {'type': 'string', 'role': 'source'}, 'Shape_Length': {'type': 'double', 'role': 'geometry_derived', 'gee_aliases': ['Shape_Leng']}}
        gee = [{'type': 'Feature', 'id': 'stable-1', 'properties': {'Hylak_id': 1, 'area': 9.5, 'name': None, 'Shape_Leng': 11.0}, 'geometry': {'type': 'LineString', 'coordinates': [[0, 0], [1.01, 0]]}}]
        report = self.compare_fixture(locals_=local, gees=gee, fields=fields)
        self.assertEqual(report['attributes']['mismatch_count'], 2)
        self.assertEqual(report['geometry']['strict_fail'], 1)
        self.assertEqual(report['geometry']['diagnostic_fail'], 1)

    def test_geometry_rejects_unexpected_z_dimension(self):
        result = compare.geometry_result({'type': 'Point', 'coordinates': [0, 0, 100]}, {'type': 'Point', 'coordinates': [0, 0]})
        self.assertFalse(result['strict'])

    def test_missing_source_field_and_geometry_derived_gap_are_coverage_gaps(self):
        local = [{'local_id': 1, 'properties': {'Hylak_id': 1, 'area': 3.5, 'name': None, 'Shape_Length': 10.0}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}, 'row_group': 0, 'row_offset': 0}]
        fields = {'Hylak_id': {'type': 'int64', 'role': 'source'}, 'area': {'type': 'double', 'role': 'source'}, 'name': {'type': 'string', 'role': 'source'}, 'Shape_Length': {'type': 'double', 'role': 'geometry_derived', 'gee_aliases': ['Shape_Leng']}}
        gee = [{'type': 'Feature', 'id': 'stable-1', 'properties': {'Hylak_id': 1, 'name': None}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}}]
        report = self.compare_fixture(locals_=local, gees=gee, fields=fields)
        self.assertEqual(report['fields']['source']['area']['missing'], 1)
        self.assertEqual(report['fields']['geometry_derived']['Shape_Length']['missing'], 1)
        self.assertFalse(report['attributes']['pass'])

    def test_raw_compound_key_multiplicity_and_nonidentity_disclosure(self):
        local = lambda i: {'local_id': str(i), 'properties': {'lon': 1.0, 'lat': 2.0, 'segmentID': 4, 'segmentInd': 7, 'width': 8.0}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}, 'row_group': 0, 'row_offset': i}
        locals_ = [local(1), local(2)]
        fields = {'lon': {'type': 'double', 'role': 'source'}, 'lat': {'type': 'double', 'role': 'source'}, 'segmentID': {'type': 'int64', 'role': 'source'}, 'segmentInd': {'type': 'int64', 'role': 'source'}, 'width': {'type': 'double', 'role': 'source'}}
        gee = {'type': 'Feature', 'properties': {'lon': 1.0, 'lat': 2.0, 'segmentID': 4, 'segmentInd': 7, 'width': 8.0}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}}
        report = self.compare_fixture(dataset='grwl-raw', locals_=locals_, gees=[gee, dict(gee)], fields=fields)
        self.assertTrue(report['identity']['matching'].startswith('raw compound-key multiset'))
        self.assertTrue(all(r.get('individual_identity_asserted') is False for r in report['examples'] if 'key_multiplicity_local' in r))

    def test_valid_multipage_capture_follows_unique_token_chain(self):
        sp, sample, cap, pp, cp, plan = self.fixture()
        receipt_path = cap / 'capture.json'
        receipt = json.loads(receipt_path.read_text())
        page1 = cap / 'hydrolakes-features-000-001.json'
        first = json.loads(page1.read_text())
        first['nextPageToken'] = 'next-page'
        data1 = json.dumps(first, separators=(',', ':'), allow_nan=False).encode()
        page1.write_bytes(data1)
        item1 = next(x for x in receipt['requests'] if x['query'] == 'hydrolakes-features-000')
        item1.update(response_bytes=len(data1), response_sha256=hashlib.sha256(data1).hexdigest())
        page2 = cap / 'hydrolakes-features-000-002.json'
        data2 = b'{"features":[]}'
        page2.write_bytes(data2)
        item2 = dict(item1, params={'region': 'region', 'pageToken': 'next-page'}, response_path=page2.name, response_bytes=len(data2), response_sha256=hashlib.sha256(data2).hexdigest())
        receipt['requests'].append(item2)
        dump(receipt_path, receipt)
        report = compare.build_report(sp, sample, cap, pp, plan, cp, json.loads(cp.read_text()))
        self.assertTrue(report['capture_validation']['pass'], report['capture_validation']['issues'])
        # A matching token chain that repeats a server token is still invalid.
        repeated = {'features': [], 'nextPageToken': 'next-page'}
        data2 = json.dumps(repeated).encode()
        page2.write_bytes(data2)
        item2.update(response_bytes=len(data2), response_sha256=hashlib.sha256(data2).hexdigest())
        page3 = cap / 'hydrolakes-features-000-003.json'
        data3 = b'{"features":[]}'
        page3.write_bytes(data3)
        receipt['requests'].append(dict(item2, response_path=page3.name, response_bytes=len(data3), response_sha256=hashlib.sha256(data3).hexdigest()))
        dump(receipt_path, receipt)
        report = compare.build_report(sp, sample, cap, pp, plan, cp, json.loads(cp.read_text()))
        self.assertFalse(report['capture_validation']['pass'])
        self.assertTrue(any('repeated pagination token' in x for x in report['capture_validation']['issues']))


if __name__ == '__main__':
    unittest.main()
