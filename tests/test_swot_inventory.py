"""Focused tests for bounded SWOT PLD metadata capture and inventory projection."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research' / 'gdw-swot-preparation-20261101'))
import capture_swot


def feature(item_id, filename, size=16, checksum='d50110' + '0' * 32):
    return {
        'id': item_id,
        'properties': {'datetime': '2026-10-20T00:00:00Z'},
        'assets': {'data': {
            'title': filename,
            'href': 'https://hydroweb.next.theia-land.fr/api/v1/rs-catalog/downloads/urn/files/hash?scope=hysope2',
            'roles': ['data'], 'file:size': size, 'file:checksum': checksum,
            'description': 'File size: 16 bytes\nChecksum MD5: ' + '0' * 32,
        }},
    }


class SwotInventoryTests(unittest.TestCase):
    def test_filters_v203_and_counts_older_items(self):
        result = capture_swot.project_inventory([
            feature('v203-au55', 'SWOT_LakeDatabaseSci_AU_55_20260902_v203.sqlite'),
            feature('v202-au55', 'SWOT_LakeDatabaseSci_AU_55_20250331_v202.sqlite', 12),
        ])
        self.assertEqual(result['v203_item_count'], 1)
        self.assertEqual(result['v202_older_item_count'], 1)
        self.assertEqual(result['v203_provider_file_size_bytes_exact_sum'], 16)
        self.assertEqual(result['v203_items'][0]['tile_identifier'], 'AU_55')
        self.assertEqual(result['v203_items'][0]['provider_file_checksum_md5'], '0' * 32)
        self.assertEqual(result['v203_region_counts'], {'AU': 1})

    def test_rejects_duplicate_item_ids(self):
        item = feature('same-id', 'SWOT_LakeDatabaseSci_AU_55_v203.sqlite')
        with self.assertRaisesRegex(ValueError, 'duplicate item IDs'):
            capture_swot.project_inventory([item, item])

    def test_unknown_v203_size_prevents_exact_sum(self):
        result = capture_swot.project_inventory([
            feature('known', 'SWOT_LakeDatabaseSci_AU_55_v203.sqlite', 16),
            feature('unknown', 'SWOT_LakeDatabaseSci_EU_21_v203.sqlite', None),
        ])
        self.assertIsNone(result['v203_provider_file_size_bytes_exact_sum'])
        self.assertEqual(result['v203_provider_file_size_bytes_known_sum'], 16)
        self.assertEqual(result['v203_unknown_size_item_ids'], ['unknown'])

    def test_duplicate_tiles_and_conflicting_editions_are_rejected(self):
        first = feature('one', 'SWOT_LakeDatabaseSci_AU_55_v203.sqlite')
        second = feature('two', 'SWOT_LakeDatabaseSci_AU_55_other_v203.sqlite')
        with self.assertRaisesRegex(ValueError, 'duplicate v2.03 tile'):
            capture_swot.project_inventory([first, second])
        bad = feature('SWOT_AU_55_v202@provider', 'SWOT_LakeDatabaseSci_AU_55_v203.sqlite')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            capture_swot.project_inventory([bad])

    def test_zero_or_boolean_size_cannot_establish_exact_bytes(self):
        for size in (0, True):
            with self.subTest(size=size):
                result = capture_swot.project_inventory([
                    feature('item', 'SWOT_LakeDatabaseSci_AU_55_v203.sqlite', size)])
                self.assertIsNone(result['v203_provider_file_size_bytes_exact_sum'])

    def test_existing_output_refuses_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capture.json'
            path.write_text('{}')
            with patch.object(capture_swot, 'fetch_pages') as fetch:
                with self.assertRaises(FileExistsError):
                    capture_swot.capture_to_path(path)
                fetch.assert_not_called()
            self.assertEqual(json.loads(path.read_text()), {})


if __name__ == '__main__':
    unittest.main()
