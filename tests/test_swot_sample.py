"""Tests for guarded one-tile SWOT source inspection."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research' / 'gdw-swot-preparation-20261101'))
import inspect_swot_sample as sample


class SwotSampleTests(unittest.TestCase):
    def test_checksum_mismatch_never_opens_sqlite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'AU_55.sqlite'
            path.write_bytes(b'not a matching database')
            transfer = {'file_path': str(path), 'size_matches_provider': True,
                        'md5_matches_provider': False}
            inspector = Mock()
            result = sample.verify_download(transfer, inspector=inspector)
            self.assertEqual(result['status'], 'not_inspected_checksum_or_size_mismatch')
            inspector.assert_not_called()

    def test_existing_report_refuses_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / 'existing.json'
            report.write_text('{}')
            with patch.object(sample, 'download_sample') as download:
                with self.assertRaises(FileExistsError):
                    sample.capture_sample(root / 'missing-inventory.json', report,
                                          storage_dir=root / 'storage')
                download.assert_not_called()
            self.assertEqual(json.loads(report.read_text()), {})

    def test_existing_sample_refuses_before_request(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'AU_55.sqlite'
            path.write_bytes(b'prior sample')
            opener = Mock()
            item = {'file_url': 'https://hydroweb.next.theia-land.fr/data',
                    'provider_file_size_bytes': 12, 'expected_md5': '0' * 32}
            with self.assertRaises(FileExistsError):
                sample.download_sample(item, path, opener=opener)
            opener.assert_not_called()

    def test_quick_check_failure_blocks_inspection_success(self):
        transfer = {'file_path': '/unused', 'size_matches_provider': True,
                    'md5_matches_provider': True}
        result = sample.verify_download(
            transfer, inspector=lambda _: {'quick_check': ['database disk image is malformed'],
                                           'errors': []})
        self.assertEqual(result['status'], 'failed_sqlite_validation')
        self.assertTrue(result['errors'])

    def test_download_reads_at_most_expected_size_plus_one_and_hashes_partial(self):
        body = b'abcde'

        class Response:
            status = 200
            headers = {}

            def __init__(self):
                self.stream = io.BytesIO(body)
                self.read_sizes = []

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, size):
                self.read_sizes.append(size)
                return self.stream.read(size)

        with tempfile.TemporaryDirectory() as temp:
            response = Response()
            item = {'file_url': 'https://hydroweb.next.theia-land.fr/asset',
                    'provider_file_size_bytes': 4,
                    'expected_md5': hashlib.md5(b'abcd').hexdigest()}
            destination = Path(temp) / 'AU_55.sqlite'
            with patch.object(sample, '_disk_status', return_value={'free_bytes': 50 * 1024**3}):
                result = sample.download_sample(item, destination,
                                                opener=lambda *_args, **_kwargs: response)
            partial = destination.with_name(destination.name + '.part')
            self.assertTrue(result['failure'].startswith('response exceeded provider-declared size'))
            self.assertEqual(response.read_sizes[0], 5)
            self.assertEqual(result['response_bytes_written'], 4)
            self.assertEqual(partial.read_bytes(), b'abcd')
            self.assertEqual(result['partial_md5'], hashlib.md5(b'abcd').hexdigest())
            self.assertEqual(result['partial_sha256'], hashlib.sha256(b'abcd').hexdigest())
            self.assertFalse(destination.exists())

    def test_low_initial_disk_space_writes_failure_without_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = {'tile_identifier': 'AU_55', 'filename': 'SWOT_LakeDatabaseSci_AU_55_20260902_v203.sqlite',
                    'file_url': 'https://hydroweb.next.theia-land.fr/asset',
                    'provider_file_size_bytes': sample.EXPECTED_BYTES,
                    'provider_file_checksum_md5': '0' * 32,
                    'provider_file_checksum_multihash': 'd50110' + '0' * 32}
            inventory = root / 'inventory.json'
            inventory.write_text(json.dumps({'status': 'metadata_qualified_provider_declared_bytes',
                                             'v203_items': [item]}))
            output = root / 'report.json'
            opener = Mock()
            with patch.object(sample, '_disk_status', return_value={
                    'free_bytes': sample.MIN_FREE_BYTES - 1,
                    'required_free_bytes': sample.MIN_FREE_BYTES,
                    'passes_40_gib_minimum': False}):
                result = sample.capture_sample(inventory, output, root / 'storage', opener=opener)
            opener.assert_not_called()
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(output.exists())

    def test_dangling_report_symlink_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / 'dangling.json'
            report.symlink_to(root / 'missing-target')
            with patch.object(sample, 'download_sample') as download:
                with self.assertRaises(FileExistsError):
                    sample.capture_sample(root / 'missing-inventory.json', report,
                                          storage_dir=root / 'storage')
                download.assert_not_called()

    def test_read_only_inspection_reports_schema_counts_pk_and_fk(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.sqlite'
            connection = sqlite3.connect(path)
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY, label TEXT)')
            connection.execute('CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))')
            connection.execute('INSERT INTO parent VALUES (1, "p")')
            connection.execute('INSERT INTO child VALUES (7, 1)')
            connection.commit()
            connection.close()
            result = sample.inspect_sqlite(path)
            self.assertEqual(result['quick_check'], ['ok'])
            parent = next(table for table in result['tables'] if table['name'] == 'parent')
            child = next(table for table in result['tables'] if table['name'] == 'child')
            self.assertEqual(parent['row_count'], 1)
            self.assertEqual(parent['columns'][0]['primary_key_position'], 1)
            self.assertEqual(child['foreign_keys'][0]['referenced_table'], 'parent')
            self.assertEqual(child['row_count'], 1)
            self.assertEqual(result['errors'], [])


if __name__ == '__main__':
    unittest.main()
