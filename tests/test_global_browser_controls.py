import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research/grwl-raw-release-20261102'))
import prepare_global_browser_controls as controls


FIELDS = ['utm_east', 'utm_north', 'width_m', 'nchannels', 'segmentID', 'segmentInd',
          'lakeFlag', 'lon', 'lat', 'elev_m', 'source_tile', 'source_row', 'feature_id', 'width_valid']


class GlobalControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.production_policy = ROOT / 'research/grwl-raw-release-20261102/global-browser-policy.json'
        self.policy = self.root / 'policy.json'
        self.policy.write_bytes(self.production_policy.read_bytes())
        policy = json.loads(self.policy.read_text())
        records = []
        tile_evidence, manifest_tiles = [], []
        known = policy['known_error_cases']
        windows = policy['global_controls']
        points = [(-100, 40), (-60, -20), (10, 0), (10, 50), (100, 20), (130, -20)]
        samples = [(c['source_tile'], c['source_row'], c['summary_reference_id'], None) for c in known]
        samples += [(f'AA{i:02d}', i + 1, None, points[i]) for i in range(6)]
        for ix, (tile, row, ref, point) in enumerate(samples):
            lon, lat = point if point else (-105 + ix, 40 + ix / 10)
            feature = ((ord(tile[0])-65)*26 + ord(tile[1])-65)*100 + int(tile[2:])
            feature = (feature << 32) | row
            records.append({'utm_east': Decimal('12.340000000000000000'), 'utm_north': Decimal('23.000000000000000000'),
                'width_m': 1 if ref else 33, 'nchannels': Decimal('1.250000000000000000'), 'segmentID': 7,
                'segmentInd': 1, 'lakeFlag': Decimal('0.000000000000000000'), 'lon': Decimal(str(lon)),
                'lat': Decimal(str(lat)), 'elev_m': 5, 'source_tile': tile, 'source_row': row,
                'feature_id': feature, 'width_valid': not bool(ref)})
        schema = pa.schema([
            pa.field('utm_east', pa.decimal128(38,18)), pa.field('utm_north', pa.decimal128(38,18)),
            pa.field('width_m', pa.int64()), pa.field('nchannels', pa.decimal128(38,18)),
            pa.field('segmentID', pa.int64()), pa.field('segmentInd', pa.int64()),
            pa.field('lakeFlag', pa.decimal128(38,18)), pa.field('lon', pa.decimal128(38,18)),
            pa.field('lat', pa.decimal128(38,18)), pa.field('elev_m', pa.int64()),
            pa.field('source_tile', pa.string()), pa.field('source_row', pa.uint32()),
            pa.field('feature_id', pa.uint64()), pa.field('width_valid', pa.bool_())])
        self.parquet = self.root / 'source.parquet'
        pq.write_table(pa.Table.from_pylist(records, schema=schema), self.parquet)
        for ix, (tile, row, ref, point) in enumerate(samples):
            bbox = ([point[0]-.001, point[1]-.001, point[0]+.001, point[1]+.001] if point else [-105, 39, -104, 40])
            feature = records[ix]['feature_id']
            evidence = {'tile': tile, 'source_rows': 1, 'parts': 1,
                        'longest_parts': [{'source_tile': tile, 'source_row': row, 'feature_id': feature,
                                          'part': 1, 'length_m': 11000000 + ix, 'bbox': bbox}]}
            tile_evidence.append(evidence); manifest_tiles.append({'tile': tile, 'records': 1, 'parts': 1})
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'rows': len(records), 'parquet_sha256': controls.digest(self.parquet), 'tiles': manifest_tiles}))
        self.validation = self.root / 'validation.json'
        self.validation.write_text(json.dumps({'status': 'passed', 'manifest_sha256': controls.digest(self.manifest),
            'parquet_sha256': controls.digest(self.parquet), 'sample_policy': {'kind': 'global_controls'},
            'progress': {'source_rows': len(records)}, 'tiles': tile_evidence}))
        self.output = self.root / 'controls.json'

    def tearDown(self):
        self.temp.cleanup()

    def generate(self):
        return controls.generate(self.validation, self.manifest, self.parquet, self.output, self.policy)

    def test_deterministic_controls_and_exact_decimal_display(self):
        result = self.generate()
        self.assertEqual(result['case_count'], 11)
        self.assertEqual(result['cases'][0]['case_id'], 'known-summary-11839')
        self.assertEqual(result['cases'][0]['expected_analytic_attributes']['utm_east'], '12.340000000000000000')
        self.assertEqual(result['cases'][0]['expected_analytic_attributes']['width_valid'], 'false')
        self.assertEqual([c['window_id'] for c in result['cases'][5:]], [w['window_id'] for w in json.loads(self.policy.read_text())['global_controls']])
        self.assertEqual(result['cases'][5]['source_tile'], 'AA00')
        self.assertEqual(result['cases'][5]['context_region'], 'grwl_15450')
        self.assertEqual(result['cases'][5]['context_bbox'], [-102.001, 37.999, -97.999, 42.001])
        self.assertEqual(result['cases'][0]['expected_width']['label'], 'Observation width · Unknown (source sentinel 1)')
        self.assertEqual(result['cases'][5]['expected_width']['label'], 'Observation width · 33 m')
        self.assertEqual(json.loads(self.policy.read_text())['source_selection']['minimum_part_length_m'], 10)

    def test_rejects_unbound_input_and_existing_output(self):
        self.validation.write_text(self.validation.read_text().replace(controls.digest(self.manifest), '0' * 64))
        with self.assertRaisesRegex(ValueError, 'not bound'):
            self.generate()
        self.validation.write_text(json.dumps({'status': 'passed', 'manifest_sha256': controls.digest(self.manifest),
            'parquet_sha256': controls.digest(self.parquet), 'sample_policy': {'kind': 'global_controls'},
            'progress': {'source_rows': 11}, 'tiles': json.loads((self.root / 'validation.json').read_text()).get('tiles', [])}))
        self.output.write_text('{}')
        with self.assertRaisesRegex(FileExistsError, 'overwrite'):
            self.generate()

    def test_rejects_missing_window_sample(self):
        validation = json.loads(self.validation.read_text())
        validation['tiles'][-1]['longest_parts'] = []
        self.validation.write_text(json.dumps(validation))
        # Update hashes so this checks the policy gate, not the hash gate.
        validation['manifest_sha256'] = controls.digest(self.manifest)
        validation['parquet_sha256'] = controls.digest(self.parquet)
        self.validation.write_text(json.dumps(validation))
        with self.assertRaisesRegex(ValueError, 'Incomplete longest-part'):
            self.generate()


if __name__ == '__main__':
    unittest.main()
