"""Canonical-record location, promotion and cross-root consumer regressions."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import catalog
import candidate_discovery
import publication_catalog
import source_products


class RecordLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def put(self, area, record_id, **extra):
        record = {'schema_version': 1, 'id': record_id, 'title': record_id,
                  'triage': {'decision': 'pending', 'priority': 'normal'},
                  'intake': {'kind': 'producer', 'reference_url': 'https://example.org/data',
                             'added_on': '2026-11-09'}, **extra}
        path = self.root / area / record_id / 'dataset.yaml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(record, sort_keys=False))
        return path, record

    def test_loads_records_from_both_locations(self):
        candidate, _ = self.put('candidates', 'future')
        dataset, _ = self.put('datasets', 'active')
        self.assertEqual(set(catalog.record_paths(self.root)), {candidate, dataset})
        self.assertEqual(set(catalog.load_records(self.root)), {'future', 'active'})

    def test_duplicate_id_across_locations_is_rejected_by_all_consumers(self):
        self.put('candidates', 'same', publication={'source_coop': {}})
        self.put('datasets', 'same', publication={'source_coop': {}})
        for loader in (catalog.load_records, publication_catalog.validated_records, source_products.load_records):
            with self.subTest(loader=loader.__module__), self.assertRaisesRegex(ValueError, 'Duplicate'):
                loader(self.root)

    def test_promotion_moves_identity_without_creating_a_second_record(self):
        path, record = self.put('candidates', 'future')
        before = json.loads(catalog.render_index(self.root))['datasets']
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]['record_path'], 'candidates/future/dataset.yaml')
        data = path.read_bytes()
        destination = self.root / 'datasets' / 'future'
        destination.parent.mkdir()
        path.parent.rename(destination)
        after = json.loads(catalog.render_index(self.root))['datasets']
        self.assertEqual((destination / 'dataset.yaml').read_bytes(), data)
        self.assertEqual(catalog.load_records(self.root), {'future': record})
        self.assertEqual(after[0].pop('record_path'), 'datasets/future/dataset.yaml')
        before[0].pop('record_path')
        self.assertEqual(after, before)

    def test_published_record_requires_promotion_out_of_candidates(self):
        self.put('candidates', 'future', publication={'status': 'published'})
        with self.assertRaisesRegex(ValueError, '[Pp]romot'):
            catalog.load_records(self.root)

    def test_publication_checks_duplicate_yaml_keys_in_candidate_records(self):
        path, _ = self.put('candidates', 'future')
        path.write_text(path.read_text() + 'title: silent overwrite\n')
        with self.assertRaisesRegex(ValueError, '[Dd]uplicate'):
            publication_catalog.validated_records(self.root)

    def test_generated_backlog_links_follow_actual_record_locations(self):
        _, candidate = self.put('candidates', 'future', review={'citation_assessment': {'geographic_scope': 'global'}})
        _, active = self.put('datasets', 'active', review={'citation_assessment': {'geographic_scope': 'global'}})
        rows = {r['id']: r for r in candidate_discovery.rows({'future': candidate, 'active': active}, self.root)}
        self.assertEqual(rows['future']['record_path'], 'candidates/future/dataset.yaml')
        self.assertEqual(rows['active']['record_path'], 'datasets/active/dataset.yaml')

    def test_related_readme_links_cross_roots_and_stay_beside_the_record(self):
        _, candidate = self.put('candidates', 'future')
        _, active = self.put('datasets', 'active')
        relation = {'id': 'related', 'title': 'Related data', 'relationship': 'complement',
                    'url': 'https://example.org/related', 'use_case': 'Context.', 'comparison': 'Distinct data.',
                    'reviewed_on': '2026-11-09', 'evidence': [{'title': 'Producer', 'url': 'https://example.org/docs'}]}
        for area, record, other in [('candidates', candidate, 'active'), ('datasets', active, 'future')]:
            record['related_datasets'] = [{**relation, 'record_id': other}]
            (self.root / area / record['id'] / 'dataset.yaml').write_text(yaml.safe_dump(record))
        updates = catalog.related_readme_updates(self.root)
        self.assertEqual(set(updates), {self.root/'candidates/future/README.md', self.root/'datasets/active/README.md'})
        self.assertIn('../../datasets/active/dataset.yaml', updates[self.root/'candidates/future/README.md'])
        self.assertIn('../../candidates/future/dataset.yaml', updates[self.root/'datasets/active/README.md'])

    def test_source_product_preparation_requires_promotion(self):
        self.put('candidates', 'future', publication={'source_coop': {}})
        with self.assertRaisesRegex(source_products.ProductError, '[Pp]romote'):
            source_products.load_records(self.root)

    def test_symlink_record_directory_is_rejected(self):
        original, _ = self.put('elsewhere', 'future')
        (self.root/'candidates').mkdir()
        (self.root/'candidates/future').symlink_to(original.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '[Ss]ymlink'):
            catalog.load_records(self.root)


if __name__ == '__main__':
    unittest.main()
