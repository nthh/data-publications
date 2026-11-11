import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from support_publication import apply_support_layout, load_support_layout, assert_no_legacy_urls
from source_retirement import checked_key


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SupportRelocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = b'{"validation":"passed"}\n'
        (self.root / 'report.json').write_bytes(self.report)
        self.old = 'https://data.source.coop/nthh/demo/releases/r1/report.json'
        self.revision = '1' * 40
        self.record = {'id': 'demo', 'publication': {'release': 'r1', 'source_coop': {
            'owner': 'nthh', 'product_id': 'demo', 'flat_layout': {}, 'support_layout': {'manifest_path': 'support.json'}}}}
        self.asset = {'href': self.old, 'type': 'application/json', 'roles': ['metadata'],
                      'title': 'Original report', 'file:size': len(self.report), 'file:checksum': '1220' + sha(self.report)}
        self.collection = {'assets': {'support': copy.deepcopy(self.asset)}, 'links': [{'rel': 'via', 'href': self.old}]}
        self.manifest = {'schema_version': 1, 'dataset_id': 'demo', 'owner': 'nthh', 'product_id': 'demo',
                         'source_release': 'r1', 'git_revision': self.revision, 'files': [{
                             'asset_id': 'support', 'source_href': self.old, 'media_type': 'application/json',
                             'roles': ['metadata'], 'title': 'Original report', 'sha256': sha(self.report),
                             'size_bytes': len(self.report), 'retained': {'kind': 'git', 'path': 'report.json',
                             'encoding': 'identity', 'sha256': sha(self.report), 'size_bytes': len(self.report),
                             'url': f'https://raw.githubusercontent.com/nthh/data-publications/{self.revision}/report.json'}}]}
        self.save()

    def save(self):
        data = json.dumps(self.manifest).encode()
        (self.root / 'support.json').write_bytes(data)
        self.record['publication']['source_coop']['support_layout']['manifest_sha256'] = sha(data)

    def test_relocates_without_changing_identity_or_bytes(self):
        before = copy.deepcopy(self.collection['assets']['support'])
        apply_support_layout(self.root, self.record, self.collection)
        after = self.collection['assets']['support']
        self.assertEqual({k: v for k, v in before.items() if k != 'href'}, {k: v for k, v in after.items() if k != 'href'})
        self.assertEqual(after['href'], self.collection['links'][0]['href'])
        self.assertIn(self.revision, after['href'])

    def test_rejects_changed_retained_file(self):
        (self.root / 'report.json').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            load_support_layout(self.root, self.record)

    def test_rejects_wrong_git_url(self):
        self.manifest['files'][0]['retained']['url'] = 'https://example.test/report.json'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Git URL'):
            load_support_layout(self.root, self.record)

    def test_rejects_missing_mapping(self):
        self.manifest['files'] = []
        self.save()
        with self.assertRaisesRegex(ValueError, 'retired Source prefix'):
            apply_support_layout(self.root, self.record, self.collection)

    def test_rejects_changed_asset_identity(self):
        self.collection['assets']['support']['title'] = 'A different report'
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            apply_support_layout(self.root, self.record, self.collection)

    def test_rejects_unsupported_and_traversal_paths(self):
        for key in ('demo/README.md', 'other/releases/r1/a', 'demo/releases/../a', 'demo/releases//a'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                checked_key(key, {'demo'})
        self.assertEqual(checked_key('demo/releases/r1/a', {'demo'}), 'demo/releases/r1/a')
        self.manifest['files'][0]['retained']['path'] = '../report.json'
        self.save()
        with self.assertRaises(ValueError):
            load_support_layout(self.root, self.record)

    def test_rejects_unverified_document(self):
        item = self.manifest['files'][0]
        item['retained'] = {'kind': 'flat_document', 'object_key': 'demo/manual.pdf',
                            'url': 'https://data.source.coop/nthh/demo/manual.pdf',
                            'sha256': item['sha256'], 'size_bytes': item['size_bytes']}
        self.save()
        with self.assertRaisesRegex(ValueError, 'hosted verification'):
            load_support_layout(self.root, self.record)

    def test_rejects_old_urls_in_nested_style(self):
        with self.assertRaisesRegex(ValueError, 'retired Source prefix'):
            assert_no_legacy_urls({'sources': {'river': {'url': 'pmtiles://' + self.old}}},
                                  ['https://data.source.coop/nthh/demo/releases/'])

if __name__ == '__main__':
    unittest.main()
