"""Reject incomplete/mismatched evidence before preparing a GRWL display package."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grwl_finalizer', ROOT / 'datasets/grwl/build_display.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FinalizationEvidenceTests(unittest.TestCase):
    def test_incomplete_or_mismatched_evidence_cannot_prepare_package(self):
        baseline = {
            'passed': True, 'failures': [], 'mode': 'full', 'source_sha256': m.SOURCE_SHA,
            'source_rows': 42077, 'maxzoom_ids_accounted': 42077,
            'accounting': {'passed': True, 'attribute_failure_count': 0, 'missing_ids': [],
                           'numeric_fields': m.ATTRS, 'source_bbox_fields': m.BBOX_ATTRS},
            'geometry': {'passed': True, 'tolerance_metres': 30.0, 'samples': [{}] * 74},
            'upstream_edge_control': {'passed': True}, 'crossing_source_ids': [28938],
            'crossing_zoom_checks': [{'passed': True} for _ in range(11)],
            'crossing_freeze_sha256': m.digest(ROOT / 'research/grwl-straight-segments-20261102/crossing-source-ids.json'),
            'validator_sha256': m.digest(ROOT / 'datasets/grwl/validate_display_wrap.py'),
        }
        corruptions = [
            ('source hash', lambda d: d.update(source_sha256='0' * 64), 'source/archive identity'),
            ('only wrap checked', lambda d: d.update(mode='wrap-regression-only'), 'Complete independent'),
            ('missing source ID', lambda d: d.update(maxzoom_ids_accounted=42076), 'full source-ID'),
            ('attribute mismatch', lambda d: d['accounting'].update(attribute_failure_count=1), 'Complete independent'),
            ('geometry failed', lambda d: d['geometry'].update(passed=False), 'Independent geometry'),
            ('missing zoom', lambda d: d['crossing_zoom_checks'].pop(), 'Frozen antimeridian'),
            ('changed validator', lambda d: d.update(validator_sha256='0' * 64), 'validator code identity'),
        ]
        for name, mutate, error in corruptions:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                package = Path(directory) / 'package'; (package / 'assets').mkdir(parents=True)
                archive = package / 'assets/grwl.pmtiles'; archive.write_bytes(b'test archive')
                asset = {'id': 'grwl-display', 'path': 'assets/grwl.pmtiles', **m.descriptor(archive)}
                manifest = {'dataset_id': 'grwl', 'status': 'provisional', 'assets': [asset], 'files': m.inventory(package)}
                m.write_json(package / 'manifest.json', manifest)
                value = copy.deepcopy(baseline); value['pmtiles_sha256'] = asset['sha256']; mutate(value)
                report = Path(directory) / 'validation.json'; m.write_json(report, value)
                with self.assertRaisesRegex(ValueError, error):
                    m.finalize(package, report, Path(directory) / 'absent-browser.json')
                self.assertEqual(json.loads((package / 'manifest.json').read_text())['status'], 'provisional')


if __name__ == '__main__':
    unittest.main()
