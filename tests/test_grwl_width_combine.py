import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'datasets/grwl-raw/combine_width_display.py'
SPEC = importlib.util.spec_from_file_location('grwl_width_combine', SCRIPT)
combine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(combine)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archive(path, tiles, layers):
    metadata = {
        'name': 'fixture',
        'vector_layers': layers,
    }
    with Path(path).open('wb') as stream:
        writer = Writer(stream)
        for z, x, y, payload in sorted(tiles, key=lambda item: zxy_to_tileid(*item[:3])):
            writer.write_tile(zxy_to_tileid(z, x, y), payload)
        writer.finalize({
            'tile_type': TileType.MVT, 'tile_compression': Compression.GZIP,
            'min_lon_e7': -1800000000, 'min_lat_e7': -850000000,
            'max_lon_e7': 1800000000, 'max_lat_e7': 850000000,
            'center_zoom': 1, 'center_lon_e7': 0, 'center_lat_e7': 0,
        }, metadata)


class WidthCombineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task = self.root / 'task'
        self.task.mkdir()
        self.lock = self.task / '.native-build.lock'
        self.lock.touch()
        self.baseline = self.root / 'baseline.pmtiles'
        self.overview = self.root / 'overview.pmtiles'
        self.receipt = self.root / 'overview-receipt.json'
        self.out = self.task / 'candidate'
        self.detail_tiles = [
            (8, 1, 2, gzip.compress(b'detail z8', mtime=0)),
            (12, 12, 34, gzip.compress(b'detail z12', mtime=0)),
        ]
        self.overview_tiles = [
            (z, 0, 0, gzip.compress(f'overview z{z}'.encode(), mtime=0)) for z in range(8)
        ]
        self.old_overview_tiles = [
            (z, 0, 0, gzip.compress(f'old coverage z{z}'.encode(), mtime=0)) for z in range(8)
        ]
        fields = {'width_m': 'Number', 'width_valid': 'Boolean'}
        archive(self.baseline, self.old_overview_tiles + self.detail_tiles, [
            {'id': 'grwl_overview', 'minzoom': 0, 'maxzoom': 7, 'fields': {}, 'description': 'old coverage'},
            {'id': 'grwl_raw', 'minzoom': 8, 'maxzoom': 12, 'fields': fields, 'description': 'detail'},
        ])
        archive(self.overview, self.overview_tiles, [
            {'id': 'grwl_width_overview', 'minzoom': 0, 'maxzoom': 7, 'fields': fields, 'description': 'selected widths'},
        ])
        self.write_receipt()

    def tearDown(self):
        self.temp.cleanup()

    def write_receipt(self, status='passed', tiles_by_zoom=None):
        value = {
            'status': status, 'scope': 'pilot',
            'source_sha256': '1' * 64, 'source_manifest_sha256': '2' * 64,
            'archive_sha256': digest(self.overview), 'archive_size_bytes': self.overview.stat().st_size,
            'criteria_sha256': digest(combine.CRITERIA),
            'verifier_sha256': digest(ROOT / 'datasets/grwl-raw/validate_width_overview.py'),
            'source_records': 9, 'selected_by_zoom': {str(z): 1 for z in range(8)},
            'expected_point_occurrences': 9, 'point_occurrences': 9,
            'tiles_by_zoom': tiles_by_zoom or {str(z): 1 for z in range(8)},
            'maximum_compressed_tile_bytes': max(len(tile[3]) for tile in self.overview_tiles),
        }
        self.receipt.write_text(json.dumps(value))

    def run_combine(self, baseline_pin=None):
        return combine.combine(
            self.baseline, baseline_pin or digest(self.baseline), self.overview, self.receipt,
            self.out, self.task, self.lock, enforce_resources=False,
        )

    def test_combines_exact_payloads_and_marks_candidate_unvalidated(self):
        report = self.run_combine()
        self.assertEqual(report['status'], 'built_unvalidated')
        self.assertEqual(report['scope'], 'pilot')
        self.assertEqual(report['verification']['status'], 'passed')
        self.assertEqual(report['verification']['overview'], 8)
        self.assertEqual(report['verification']['detail'], 2)
        self.assertEqual(report['combined']['tiles'], 10)
        self.assertTrue((self.out / 'assets/grwl-raw.pmtiles').is_file())
        saved = json.loads((self.out / 'combine-report.json').read_text())
        self.assertEqual(saved['status'], 'built_unvalidated')
        self.assertEqual(saved['baseline']['discarded_old_overview_tiles'], 8)
        stream = (self.out / 'assets/grwl-raw.pmtiles').open('rb')
        source = combine.MmapSource(stream)
        reader = combine.Reader(source)
        output_tiles = dict(combine.all_tiles(reader.get_bytes))
        self.assertEqual(len(output_tiles), 10)
        for z, x, y, payload in self.overview_tiles:
            self.assertEqual(output_tiles[(z, x, y)], payload)
            self.assertNotEqual(output_tiles[(z, x, y)], self.old_overview_tiles[z][3])
        self.assertEqual(set(layer['id'] for layer in reader.metadata()['vector_layers']),
                         {'grwl_raw', 'grwl_width_overview'})
        stream.close()

    def test_tampered_baseline_pin_is_rejected(self):
        with self.assertRaisesRegex(combine.CombineError, 'explicit SHA-256 pin'):
            self.run_combine('0' * 64)
        self.assertFalse(self.out.exists())

    def test_failed_overview_receipt_is_rejected(self):
        self.write_receipt(status='failed')
        with self.assertRaisesRegex(combine.CombineError, 'status is not passed'):
            self.run_combine()
        self.assertFalse(self.out.exists())

    def test_receipt_count_mismatch_is_rejected(self):
        counts = {str(z): 1 for z in range(8)}
        counts['0'] = 2
        self.write_receipt(tiles_by_zoom=counts)
        with self.assertRaisesRegex(combine.CombineError, 'tile counts differ'):
            self.run_combine()
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
