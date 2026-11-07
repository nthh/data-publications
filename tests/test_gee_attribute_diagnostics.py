"""Small offline unit tests for descriptive GEE attribute diagnostics."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'gee_validation'))
import diagnose_attributes as diag


class AttributeDiagnosticTests(unittest.TestCase):
    def test_strict_categories_and_numeric_error_examples(self):
        meta = {'type': 'double', 'role': 'source'}
        rows = [('a', 1.0, 1.0, True), ('b', 1.0, 1.0000000000000002, True), ('c', 10.0, 11.0, True)]
        result = diag.diagnose_field('x', meta, rows, 'hydrolakes')
        self.assertEqual(result['counts'], {'exact': 1, 'representational': 1, 'mismatch': 1})
        self.assertEqual(result['numeric']['mismatch_pairs'], 1)
        self.assertEqual(result['numeric']['largest_absolute_error_examples'][0]['local_id'], 'c')
        self.assertEqual(result['numeric']['maximum_absolute_error'], 1.0)

    def test_precision_hypotheses_are_observational_and_zero_is_exception(self):
        ffr = diag.precision_hypothesis('free-flowing-rivers', 123.12345678901234, float(format(123.12345678901234, '.12g')), 123.12345678901234)
        self.assertTrue(ffr['tested'])
        self.assertTrue(ffr['match'])
        lake = diag.precision_hypothesis('lakeatlas-polygons', 123.456789, 123.45678, 123.456789)
        self.assertTrue(lake['match'])
        zero = diag.precision_hypothesis('lakeatlas-points', 0.0, 0.1, 0.0)
        self.assertEqual(zero['exception'], 'six_significant_digit_bound_undefined_for_zero')

    def test_null_empty_and_whitespace_patterns_are_distinct(self):
        self.assertTrue(diag.string_patterns(None, '')['null_to_empty'])
        self.assertTrue(diag.string_patterns('', None)['empty_to_null'])
        self.assertTrue(diag.string_patterns(' name ', 'name')['whitespace_only_difference'])
        field = diag.diagnose_field('s', {'type': 'string', 'role': 'source'}, [('1', ' name ', 'name', True)], 'hydrolakes')
        self.assertEqual(field['counts']['mismatch'], 1)
        self.assertEqual(field['string_null_and_type_patterns']['whitespace_only_difference'], 1)

    def test_ffr_alternate_mapping_is_separate_from_original_missing_field(self):
        with tempfile.TemporaryDirectory() as directory:
            sample_path = Path(directory) / 'sample.json'
            sample = {
                'dataset_id': 'free-flowing-rivers',
                'source': {'row_count': 1},
                'fields': {
                    'GOID': {'type': 'int32', 'role': 'source', 'gee_aliases': ['GOID']},
                    'ERO_YLD_TON': {'type': 'int64', 'role': 'source', 'gee_aliases': ['ERO_YLD_TON']},
                },
                    'features': [{'local_id': '7', 'properties': {'GOID': 7, 'ERO_YLD_TON': 123}, 'geometry': None}],
            }
            sample_path.write_text(json.dumps(sample))
            plan_path = Path(directory) / 'plan.json'
            plan_path.write_text('{}')
            payloads = {'free-flowing-rivers-features-000': [(None, {'features': [{'properties': {'GOID': 7, 'ERO_YLD_TO': 123.0}}]})]}
            strict = {'status': 'sampled_fail', 'attributes': {'pass': False}, 'geometry': {'strict_passed': False}}
            with patch.object(diag.compare, 'verify_capture', return_value=([], payloads, {})), \
                 patch.object(diag, 'verify_provenance', return_value={'status': 'passed', 'checks': {}}), \
                 patch.object(diag.compare, 'build_report', return_value=strict):
                result = diag.build_diagnostic(sample_path, Path(directory) / 'capture', plan_path)
            original = result['explicit_ffr_candidate_mapping']['original_strict_field_result_preserved']
            candidate = result['explicit_ffr_candidate_mapping']['candidate_mapping_diagnostic']
            self.assertEqual(original['missing_required_property'], 1)
            self.assertEqual(candidate['counts']['exact'], 1)
            self.assertFalse(result['explicit_ffr_candidate_mapping']['explicit_analysis_only_alias_added'])
            self.assertEqual(result['strict_comparison']['status'], 'sampled_fail')


if __name__ == '__main__':
    unittest.main()
