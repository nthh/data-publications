#!/usr/bin/env python3
"""Focused offline tests for the canonical catalog contract."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import yaml
import catalog

SOURCE = Path(__file__).resolve().parents[1]

class CatalogChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for path in ('datasets', 'research/gee-community-audit-20261029', 'research/citations', 'schemas'):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        original = catalog.load_records(SOURCE)
        record_id, record = next(iter(original.items()))
        record = copy.deepcopy(record)
        record['publication'] = {'status': 'fixture_review'}
        record.pop('discovery', None)  # This fixture exercises the frozen intake independently.
        slug = record['audit']['family_key']
        (self.root / 'datasets' / record_id).mkdir()
        self.record_path = self.root / 'datasets' / record_id / 'dataset.yaml'
        self.record_path.write_text(yaml.safe_dump(record, sort_keys=False))
        source_audit = SOURCE / 'research/gee-community-audit-20261029'
        families = json.loads((source_audit / 'families.json').read_text())
        family = next(row for row in families if row['slug'] == slug)
        (self.root / 'research/gee-community-audit-20261029/families.json').write_text(json.dumps([family]))
        with (source_audit / 'crosswalk.csv').open(newline='') as src:
            reader = csv.DictReader(src); fields = reader.fieldnames
            row = next(r for r in reader if r['catalog_slug'] == slug)
        with (self.root / 'research/gee-community-audit-20261029/crosswalk.csv').open('w', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=fields, lineterminator='\n'); writer.writeheader(); writer.writerow(row)
        (self.root / 'research/gee-community-audit-20261029/summary.json').write_text('{}\n')
        ranked_rows = json.loads((SOURCE / 'research/citations/rankings.json').read_text())
        ranked = next(item for item in ranked_rows if item['slug'] == slug)
        (self.root / 'research/citations/rankings.json').write_text(json.dumps([ranked]))
        intake = json.loads((SOURCE / 'intake.json').read_text())
        intake.update(family_count=1, audit_directory='research/gee-community-audit-20261029',
                      initial_queues={record['audit']['initial_queue']:1}, decision_counts={record['triage']['decision']:1})
        intake['input_sha256'] = {name:hashlib.sha256((self.root/'research/gee-community-audit-20261029'/name).read_bytes()).hexdigest() for name in ('families.json','crosswalk.csv','summary.json')}
        intake['citation_snapshot'].update(rankings_path='research/citations/rankings.json',methodology_path='research/citations/methodology.json')
        (self.root/'intake.json').write_text(json.dumps(intake))
        (self.root/'schemas/dataset.schema.json').write_bytes((SOURCE/'schemas/dataset.schema.json').read_bytes())
    def tearDown(self): self.tmp.cleanup()
    def test_valid_fixture_and_index(self):
        self.assertEqual(catalog.validate(self.root)['family_keys_checked'], 1)
        index = catalog.render_index(self.root); (self.root/'index.json').write_text(index)
        catalog.check_index(self.root)
        entry = json.loads(index)['datasets'][0]
        self.assertEqual(entry['record_path'], f"datasets/{entry['id']}/dataset.yaml")
        self.assertEqual(entry['publication_status'], 'fixture_review')
        record = yaml.safe_load(self.record_path.read_text())
        old_decision = record['triage']['decision']
        record['triage']['decision'] = 'defer' if old_decision != 'defer' else 'reuse_existing'
        self.record_path.write_text(yaml.safe_dump(record, sort_keys=False))
        self.assertEqual(catalog.validate(self.root)['family_keys_checked'], 1)
        regenerated = catalog.render_index(self.root)
        (self.root/'index.json').write_text(regenerated)
        catalog.check_index(self.root)
        self.assertNotEqual(json.loads(regenerated)['datasets'][0]['decision'], old_decision)
        record = yaml.safe_load(self.record_path.read_text())
        record['triage']['priority'] = 'pilot_review' if record['triage']['priority'] == 'normal' else 'normal'
        self.record_path.write_text(yaml.safe_dump(record, sort_keys=False))
        with self.assertRaisesRegex(ValueError, 'stale'):
            catalog.check_index(self.root)
    def _supplement(self):
        path=self.root/'datasets'/'official-example'/'dataset.yaml'
        path.parent.mkdir()
        record={'schema_version':1,'id':'official-example','title':'Producer fixture',
                'intake':{'kind':'producer','reference_url':'https://example.org/dataset','added_on':'2026-10-31'},
                'triage':{'decision':'publish_conversion','priority':'pilot_review'}}
        path.write_text(yaml.safe_dump(record))
        return path,record
    def test_supplement_keeps_frozen_population_and_appears_in_index(self):
        path,record=self._supplement()
        result=catalog.validate(self.root)
        self.assertEqual(result['records_checked'],2)
        self.assertEqual(result['family_keys_checked'],1)
        self.assertEqual(result['supplemental_records_checked'],1)
        row=next(r for r in json.loads(catalog.render_index(self.root))['datasets'] if r['id']=='official-example')
        self.assertIsNone(row['community_url'])
        self.assertIsNone(row['family_key'])
        self.assertEqual(row['intake'],record['intake'])
    def test_supplement_cannot_replace_a_frozen_family(self):
        self._supplement();self.record_path.unlink()
        with self.assertRaisesRegex(ValueError,'exactly once'):
            catalog.validate(self.root)
    def test_supplement_requires_valid_source_provenance(self):
        from jsonschema import ValidationError
        path,record=self._supplement();record['intake']['reference_url']='not a url'
        path.write_text(yaml.safe_dump(record))
        with self.assertRaisesRegex(ValueError, 'reference URL'):catalog.validate(self.root)
        record['intake']['reference_url']='https://example.org/dataset'
        record['intake']['related_family']='unrecognized'
        path.write_text(yaml.safe_dump(record))
        with self.assertRaisesRegex(ValueError,'Unknown related'):catalog.validate(self.root)
    def test_record_cannot_mix_frozen_and_supplemental_provenance(self):
        from jsonschema import ValidationError
        record=yaml.safe_load(self.record_path.read_text())
        record['intake']={'kind':'producer','reference_url':'https://example.org/dataset','added_on':'2026-10-31'}
        self.record_path.write_text(yaml.safe_dump(record))
        with self.assertRaises(ValidationError):catalog.validate(self.root)
    def test_lost_family_key_rejected(self):
        path=self.record_path; record=yaml.safe_load(path.read_text()); record['audit']['family_key']='missing'; path.write_text(yaml.safe_dump(record))
        with self.assertRaisesRegex(ValueError,'Unknown audit family'):
            catalog.validate(self.root)
    def test_duplicate_family_keys_rejected(self):
        path=self.root/'research/gee-community-audit-20261029/families.json'; families=json.loads(path.read_text()); families.append(copy.deepcopy(families[0])); path.write_text(json.dumps(families))
        intake=json.loads((self.root/'intake.json').read_text()); intake['input_sha256']['families.json']=hashlib.sha256(path.read_bytes()).hexdigest(); (self.root/'intake.json').write_text(json.dumps(intake))
        # Duplicate family definitions cannot be collapsed silently.
        with self.assertRaisesRegex(ValueError,'duplicate|Duplicate|exactly once'):
            catalog.validate(self.root)
    def test_frozen_input_drift_rejected(self):
        path=self.root/'research/gee-community-audit-20261029/summary.json'; path.write_text('{"changed":true}\n')
        with self.assertRaisesRegex(ValueError,'Pinned audit input changed'):
            catalog.validate(self.root)
    def test_invalid_id_or_path_rejected(self):
        path=self.record_path; record=yaml.safe_load(path.read_text()); record['id']='plastic'; path.write_text(yaml.safe_dump(record))
        with self.assertRaisesRegex(ValueError,'ID/path'):
            catalog.load_records(self.root)

    def _with_related(self):
        path, record = self._supplement()
        record['related_datasets'] = [{
            'id': 'recent-water', 'title': 'Recent water observations',
            'relationship': 'complement', 'url': 'https://example.org/recent-water',
            'use_case': 'Recent water monitoring.',
            'comparison': 'Different period and method; equivalence not established.',
            'reviewed_on': '2026-10-31',
            'evidence': [{'title': 'Producer documentation', 'url': 'https://example.org/docs'}],
        }]
        path.write_text(yaml.safe_dump(record))
        return path, record

    def test_related_references_do_not_create_records_or_change_selection(self):
        path, record = self._with_related()
        before = catalog.validate(self.root)
        record['related_datasets'][0]['record_id'] = self.record_path.parent.name
        path.write_text(yaml.safe_dump(record))
        self.assertEqual(catalog.validate(self.root), before)
        index = json.loads(catalog.render_index(self.root))['datasets']
        self.assertEqual(len(index), 2)
        row = next(item for item in index if item['id'] == 'official-example')
        self.assertEqual(row['decision'], record['triage']['decision'])
        self.assertEqual(row['publication_status'], 'candidate')
        self.assertEqual(row['related_datasets'], record['related_datasets'])
        self.assertIn('../' + self.record_path.parent.name + '/dataset.yaml', catalog.render_related(record))

    def test_related_requires_dated_evidence_and_valid_relationship(self):
        from jsonschema import ValidationError
        path, record = self._with_related()
        changes = [
            ('relationship', 'automatically_publish'),
            ('reviewed_on', '2026-13-40'),
            ('evidence', []),
            ('url', 'file:///private/local-data'),
            ('evidence', [{'title': 'Bad source', 'url': 'javascript:alert(1)'}]),
        ]
        for key, value in changes:
            with self.subTest(field=key, value=value):
                broken = copy.deepcopy(record)
                broken['related_datasets'][0][key] = value
                path.write_text(yaml.safe_dump(broken))
                with self.assertRaises(ValidationError):
                    catalog.validate(self.root)
        broken = copy.deepcopy(record)
        del broken['related_datasets'][0]['comparison']
        path.write_text(yaml.safe_dump(broken))
        with self.assertRaises(ValidationError):
            catalog.validate(self.root)

    def test_related_duplicate_and_invalid_local_links_rejected(self):
        path, record = self._with_related()
        broken = copy.deepcopy(record)
        broken['related_datasets'].append(copy.deepcopy(broken['related_datasets'][0]))
        path.write_text(yaml.safe_dump(broken))
        with self.assertRaisesRegex(ValueError, 'Duplicate related dataset ID'):
            catalog.validate(self.root)
        for target in ('absent-record', record['id']):
            with self.subTest(target=target):
                broken = copy.deepcopy(record)
                broken['related_datasets'][0]['record_id'] = target
                path.write_text(yaml.safe_dump(broken))
                with self.assertRaisesRegex(ValueError, 'Invalid related record_id'):
                    catalog.validate(self.root)

    def test_related_readme_regeneration_preserves_prose_and_detects_drift(self):
        path, record = self._with_related()
        readme = path.with_name('README.md')
        prefix = '# Handwritten title\n\nKeep these source notes.\n\n'
        suffix = '\n\n## Other notes\nKeep these release notes.\n'
        readme.write_text(prefix)
        updates = catalog.related_readme_updates(self.root)
        self.assertEqual(set(updates), {readme})
        readme.write_text(updates[readme] + suffix)
        catalog.check_related_readmes(self.root)
        self.assertEqual(catalog.related_readme_updates(self.root), {})
        record['related_datasets'][0]['comparison'] = 'A revised, documented comparison.'
        path.write_text(yaml.safe_dump(record))
        with self.assertRaisesRegex(ValueError, 'README section is stale'):
            catalog.check_related_readmes(self.root)
        updated = catalog.related_readme_updates(self.root)[readme]
        self.assertTrue(updated.startswith(prefix))
        self.assertTrue(updated.endswith(suffix))
        self.assertIn('A revised, documented comparison', updated)
        readme.write_text(updated)
        catalog.check_related_readmes(self.root)
        record['related_datasets'] = []
        path.write_text(yaml.safe_dump(record))
        updated = catalog.related_readme_updates(self.root)[readme]
        self.assertNotIn(catalog.RELATED_START, updated)
        self.assertNotIn('Recent water observations', updated)
        self.assertTrue(updated.startswith(prefix))
        self.assertTrue(updated.endswith(suffix))
        readme.write_text(updated)
        catalog.check_related_readmes(self.root)

    def test_related_readme_creates_only_needed_readme(self):
        path, record = self._with_related()
        updates = catalog.related_readme_updates(self.root)
        self.assertEqual(set(updates), {path.with_name('README.md')})
        self.assertTrue(updates[path.with_name('README.md')].startswith('# Producer fixture\n'))

    def test_related_malformed_markers_refuse_instead_of_overwriting(self):
        path, record = self._with_related()
        readme = path.with_name('README.md')
        invalid = [catalog.RELATED_START, catalog.RELATED_END,
                   catalog.RELATED_END + '\n' + catalog.RELATED_START,
                   catalog.RELATED_START + catalog.RELATED_START + catalog.RELATED_END]
        for contents in invalid:
            with self.subTest(contents=contents):
                readme.write_text(contents)
                with self.assertRaisesRegex(ValueError, 'Malformed related dataset markers'):
                    catalog.related_readme_updates(self.root)
                self.assertEqual(readme.read_text(), contents)

    def test_related_prose_cannot_introduce_markdown_links_or_html(self):
        path, record = self._with_related()
        record['related_datasets'][0]['comparison'] = '[fake](https://wrong.example) <script>bad</script>'
        rendered = catalog.render_related(record)
        self.assertNotIn('[fake](https://wrong.example)', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)


    def test_catalog_snapshot_contract_is_optional_and_prepared_accepts_no_urls(self):
        record = yaml.safe_load(self.record_path.read_text())
        record['publication'] = {'status': 'prepared', 'release': 'r1', 'manifest_path': 'datasets/example/manifest.json', 'manifest_sha256': 'b' * 64, 'catalog': {
            'snapshot_path': 'datasets/example/releases/r1/catalog-input/snapshot.json',
            'snapshot_sha256': 'a' * 64,
            'package_base_url': None,
            'hosting_report_path': None,
            'hosting_report_sha256': None,
        }}
        self.record_path.write_text(yaml.safe_dump(record))
        self.assertEqual(catalog.validate(self.root)['records_checked'], 1)

    def test_published_requires_bound_catalog_and_hosting_contract(self):
        from jsonschema import ValidationError
        record = yaml.safe_load(self.record_path.read_text())
        record['publication'] = {'status': 'published', 'release': 'r1', 'manifest_path': 'datasets/example/manifest.json', 'manifest_sha256': 'b' * 64}
        self.record_path.write_text(yaml.safe_dump(record))
        with self.assertRaises(ValidationError): catalog.validate(self.root)
        record['publication']['catalog'] = {
            'snapshot_path': 'datasets/example/snapshot.json', 'snapshot_sha256': 'a' * 64,
            'package_base_url': 'https://data.example.org/example/r1/',
            'hosting_report_path': 'datasets/example/hosting.json', 'hosting_report_sha256': 'c' * 64,
        }
        self.record_path.write_text(yaml.safe_dump(record))
        catalog.validate(self.root)
        for key in ('package_base_url', 'hosting_report_path', 'hosting_report_sha256'):
            with self.subTest(field=key):
                broken = copy.deepcopy(record)
                broken['publication']['catalog'][key] = None
                self.record_path.write_text(yaml.safe_dump(broken))
                with self.assertRaises(ValidationError): catalog.validate(self.root)

    def test_catalog_contract_rejects_unsafe_paths_urls_hashes_and_unknown_fields(self):
        from jsonschema import ValidationError
        base = yaml.safe_load(self.record_path.read_text())
        base['publication'] = {'status': 'prepared', 'release': 'r1', 'manifest_path': 'datasets/example/manifest.json', 'manifest_sha256': 'b' * 64, 'catalog': {
            'snapshot_path': 'datasets/example/snapshot.json', 'snapshot_sha256': 'a' * 64,
        }}
        for key, value in [('snapshot_path', '../outside.json'), ('snapshot_path', '/private/local.json'),
                           ('snapshot_sha256', 'not-a-hash'), ('package_base_url', 'file:///data/'),
                           ('unrecognized', True)]:
            with self.subTest(field=key, value=value):
                record = copy.deepcopy(base)
                record['publication']['catalog'][key] = value
                self.record_path.write_text(yaml.safe_dump(record))
                with self.assertRaises(ValidationError): catalog.validate(self.root)


if __name__ == '__main__': unittest.main(verbosity=2)
