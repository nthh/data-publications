"""Focused tests for the reviewed availability view and output accounting."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import dataset_availability as availability
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'research').mkdir()
        self.evidence_path = self.root / 'research' / 'obs.json'
        self._write_evidence()
        self.records = {'sample': self.record()}
        self.store_record(self.records['sample'])

    def store_record(self, record):
        path = self.root / "candidates" / record["id"] / "dataset.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(record))

    def tearDown(self):
        self.temp.cleanup()

    def _write_evidence(self, candidates=None):
        self.evidence_path.write_text(json.dumps({'candidates': candidates or [
            {'evidence_key': 'sample-head'}]}))

    def record(self, rank=1, *, precision='exact', size=2_500_000, reported=None,
               locations=None, manifest=None):
        return {
            'id': 'sample', 'title': 'Sample dataset', 'source': {'download_bytes': size},
            'review': {'availability': {
                'shortlist_id': 'gaps', 'rank': rank, 'reviewed_on': '2026-11-01',
                'label': 'Sample scope', 'scope': 'Global 2000–2020',
                'geographic_scope': 'global',
                'download': {'bytes': size, 'precision': precision, 'reported_size': reported,
                             'format': 'NetCDF', 'file_count': 1, 'basis': 'http_head',
                             'note': 'One file.', 'evidence_urls': ['https://example.org/data']},
                'locations': locations if locations is not None else [
                    {'service_id': 'producer', 'label': 'Producer archive', 'platform': 'external',
                     'relationship': 'matching_scope', 'access': 'download', 'formats': ['NetCDF'],
                     'urls': ['https://example.org/data'], 'asset_ids': [], 'note': 'Current files.'},
                    {'service_id': 'old-mirror', 'label': 'Older mirror', 'platform': 'external',
                     'relationship': 'other_version_or_subset', 'access': 'download', 'formats': ['NetCDF'],
                     'urls': ['https://example.org/old'], 'asset_ids': [], 'note': 'Earlier version.'},
                    {'service_id': 'earth_engine', 'label': 'Earth Engine', 'platform': 'gee',
                     'relationship': 'matching_scope', 'access': 'gee_collection', 'formats': ['ImageCollection'],
                     'urls': ['https://example.org/gee'], 'asset_ids': ['users/a/data', 'users/b/data'],
                     'note': 'Two assets from one service.'},
                ],
                'output_manifest': manifest,
                'evidence': [{'path': 'research/obs.json',
                              'sha256': hashlib.sha256(self.evidence_path.read_bytes()).hexdigest(),
                              'key': 'sample-head'}],
                'source_size_key': 'download_bytes',
            }}
        }

    def test_schema_rejects_invalid_size_relationship_and_unexpected_fields(self):
        schema = json.loads((ROOT / 'schemas/dataset.schema.json').read_text())
        validator = Draft202012Validator(
            {'$ref': '#/$defs/availability', '$defs': schema['$defs']},
            format_checker=FormatChecker())
        block = self.record()['review']['availability']
        validator.validate(block)
        for section, key, value in (
            ('download', 'bytes', -1), ('download', 'bytes', 'unknown'),
            ('download', 'precision', 'guess'),
            ('location', 'relationship', 'same_name'),
            ('root', 'untracked_count', 7),
        ):
            with self.subTest(section=section, key=key):
                block = self.record()['review']['availability']
                target = block if section == 'root' else (
                    block['locations'][0] if section == 'location' else block[section])
                target[key] = value
                with self.assertRaises(ValidationError):
                    validator.validate(block)

    def test_prepared_upload_review_does_not_become_published_in_views(self):
        record = self.records['sample']
        record['triage'] = {'decision': 'publish_conversion'}
        record['publication'] = {'status': 'prepared'}
        record['review']['publication_readiness'] = {'stage': 'prepared_for_upload_review'}
        views = availability.render_views(self.root, self.records)
        row = json.loads(views['shortlist.json'])['datasets'][0]
        self.assertEqual(row['publication_status'], 'prepared')
        self.assertEqual(row['preparation_stage'], 'prepared_for_upload_review')
        csv_row = next(csv.DictReader(views['shortlist.csv'].splitlines()))
        self.assertEqual(csv_row['publication_status'], 'prepared')
        self.assertIn('prepared for upload review', views['SHORTLIST.md'])

    def test_counts_distinguish_current_from_older_and_count_gee_once(self):
        availability.validate_availability(self.root, self.records)
        result = availability.summary(self.root, self.records['sample'])
        self.assertEqual(result['external_locations'], 2)
        self.assertEqual(result['external_matching_locations'], 1)
        self.assertEqual(result['gee_locations'], 1)
        self.assertEqual(result['gee_matching_locations'], 1)
        self.assertEqual(result['gee_asset_count'], 2)

    def test_unknown_size_stays_null_in_json_and_csv(self):
        self.records['sample'] = self.record(precision='unknown', size=None)
        self.records['sample']['source']['download_bytes'] = None
        self.records['sample']['review']['availability']['download']['reported_size'] = None
        views = availability.render_views(self.root, self.records)
        self.assertIsNone(json.loads(views['shortlist.json'])['datasets'][0]['summary']['source_download_bytes'])
        self.assertEqual(json.loads(views['shortlist.json'])['datasets'][0]['summary']['source_size_display'], 'Unknown')
        row = next(csv.DictReader(views['shortlist.csv'].splitlines()))
        self.assertEqual(row['source_size'], 'Unknown')
        self.assertEqual(row['source_download_bytes'], '')
        self.assertEqual(row['external_locations'], '2')
        self.assertIn('https://example.org/data', row['external_details'])
        self.assertIn('users/a/data', row['gee_details'])

    def test_markdown_has_all_table_rows_before_per_dataset_details(self):
        second = self.record(rank=2)
        second['id'] = 'second'
        self.store_record(second)
        records = {'sample': self.record(), 'second': second}
        markdown = availability.render_views(self.root, records)['SHORTLIST.md']
        table = markdown.split('### 1.', 1)[0]
        table_rows = [line for line in table.splitlines() if line.startswith('| 1 |') or line.startswith('| 2 |')]
        self.assertEqual(len(table_rows), 2)
        self.assertTrue(table_rows[0].startswith('| 1 |'))
        self.assertTrue(table_rows[1].startswith('| 2 |'))
        self.assertIn('GEE services (matching)', table)
        self.assertIn('GEE assets', table)
        self.assertIn('| **Sample scope** |', table)

    def test_duplicate_service_and_rank_rejected(self):
        broken = self.record()
        broken['review']['availability']['locations'].append(broken['review']['availability']['locations'][0].copy())
        with self.assertRaisesRegex(ValueError, 'Duplicate availability service'):
            availability.validate_availability(self.root, {'sample': broken})
        two = {'sample': self.record(), 'other': self.record()}
        two['other']['id'] = 'other'
        two['other']['review']['availability']['rank'] = 1
        with self.assertRaisesRegex(ValueError, 'ranks'):
            availability.validate_availability(self.root, two)

    def test_evidence_key_and_hash_are_pinned(self):
        self._write_evidence([{'evidence_key': 'sample-head'}, {'suggested_id': 'sample-head'}])
        self.records['sample'] = self.record()
        self.records['sample']['review']['availability']['evidence'][0]['sha256'] = hashlib.sha256(self.evidence_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            availability.validate_availability(self.root, self.records)
        self._write_evidence()
        self.records['sample'] = self.record()
        self.evidence_path.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            availability.validate_availability(self.root, self.records)

    def test_evidence_rejects_malformed_json_and_missing_candidates(self):
        for content, message in (('{not-json', 'valid JSON'), ('{"other": []}', 'candidates list')):
            with self.subTest(content=content):
                self.evidence_path.write_text(content)
                self.records['sample'] = self.record()
                with self.assertRaisesRegex(ValueError, message):
                    availability.validate_availability(self.root, self.records)

    def test_location_urls_reject_non_https_and_embedded_credentials(self):
        for url in ('http://example.org/data', 'https://user:pass@example.org/data'):
            with self.subTest(url=url):
                record = self.record()
                record['review']['availability']['locations'][0]['urls'] = [url]
                with self.assertRaisesRegex(ValueError, 'credential-free HTTPS'):
                    availability.validate_availability(self.root, {'sample': record})

    def _manifest(self, assets, *, legacy=False):
        manifest_path = self.root / 'manifest.json'
        if legacy:
            data = {'assets': assets}
        else:
            data = {'assets': assets}
        manifest_path.write_text(json.dumps(data))
        ref = {'path': 'manifest.json', 'sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
        self.records['sample'] = self.record(manifest=ref)
        return manifest_path

    def test_modern_manifest_splits_analytic_display_and_ignores_docs_and_zip(self):
        self._manifest([
            {'href': 'out/a.parquet', 'size_bytes': 100, 'media_type': 'application/vnd.apache.parquet'},
            {'href': 'out/map.pmtiles', 'size_bytes': 40, 'media_type': 'application/vnd.pmtiles'},
            {'href': 'README.md', 'size_bytes': 900, 'media_type': 'text/markdown'},
            {'href': 'package.zip', 'size_bytes': 800, 'media_type': 'application/zip'},
        ])
        result = availability.summary(self.root, self.records['sample'])
        self.assertEqual(result['prepared_analytic_bytes'], 100)
        self.assertEqual(result['prepared_display_bytes'], 40)
        self.assertEqual(result['prepared_data_bytes'], 140)

    def test_legacy_manifest_counts_only_parquet_and_rejects_changed_hash(self):
        path = self._manifest({'a.parquet': {'size_bytes': 11, 'sha256': 'a' * 64},
                               'readme.txt': {'size_bytes': 999}}, legacy=True)
        result = availability.summary(self.root, self.records['sample'])
        self.assertEqual(result['prepared_analytic_bytes'], 11)
        path.write_text('{"assets":{}}')
        with self.assertRaisesRegex(ValueError, 'manifest checksum mismatch'):
            availability.summary(self.root, self.records['sample'])

    def test_manifest_without_parquet_rejected(self):
        self._manifest([{'href': 'map.pmtiles', 'size_bytes': 7}], legacy=False)
        with self.assertRaisesRegex(ValueError, 'no analytic Parquet'):
            availability.summary(self.root, self.records['sample'])

    def test_zero_byte_parquet_rejected(self):
        self._manifest([{'href': 'empty.parquet', 'size_bytes': 0}])
        with self.assertRaisesRegex(ValueError, 'positive size'):
            availability.summary(self.root, self.records['sample'])

    def test_oversized_manifest_rejected_before_parsing(self):
        path = self.root / 'manifest.json'
        path.write_bytes(b' ' * 10_000_000)
        ref = {'path': 'manifest.json', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.records['sample'] = self.record(manifest=ref)
        with self.assertRaisesRegex(ValueError, 'smaller than 10000000'):
            availability.summary(self.root, self.records['sample'])

    def test_source_size_key_mismatch_rejected(self):
        record = self.record()
        record['source']['download_bytes'] = 7
        with self.assertRaisesRegex(ValueError, 'Source size key mismatch'):
            availability.validate_availability(self.root, {'sample': record})


if __name__ == '__main__':
    unittest.main()
