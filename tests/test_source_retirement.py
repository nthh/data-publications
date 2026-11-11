import copy
from pathlib import Path
import sys
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts/source_publish'), str(Path(__file__).resolve().parents[1] / 'scripts')]
from retire import check_inventory, validate_retention, check_live_catalog
from source_retirement import checked_key

class Client:
    def __init__(self, rows):
        self.rows = rows
    def get_paginator(self, name):
        assert name == 'list_objects_v2'
        return self
    def paginate(self, Bucket, Prefix):
        assert Bucket == 'nthh'
        yield {'Contents': [r for r in self.rows if r['Key'].startswith(Prefix)]}

class RetirementGuards(unittest.TestCase):
    def setUp(self):
        self.obj = {'key': 'hydrolakes/releases/r1/data.parquet', 'etag': 'old', 'size_bytes': 5,
                    'sha256': '1' * 64, 'retained': {'kind': 'flat', 'url': 'https://data.source.coop/nthh/hydrolakes/data.parquet',
                    'sha256': '1' * 64, 'size_bytes': 5, 'operation': 'copy'}}
        self.plan = {'bucket': 'nthh', 'endpoint': 'https://data.source.coop', 'objects': [self.obj]}
        self.remote = {'Key': self.obj['key'], 'ETag': 'old', 'Size': 5}

    def test_flat_target_is_same_product_and_outside_retired_prefix(self):
        validate_retention(Path.cwd(), self.plan, 'a' * 40)
        for url in ['https://data.source.coop/nthh/hydrolakes/releases/r1/data.parquet',
                    'https://data.source.coop/nthh/lakeatlas/data.parquet',
                    'https://example.test/data.parquet']:
            with self.subTest(url=url):
                self.obj['retained']['url'] = url
                with self.assertRaises(ValueError):
                    validate_retention(Path.cwd(), self.plan, 'a' * 40)

    def test_rejects_duplicate_keys_and_changed_copy_bytes(self):
        self.plan['objects'].append(copy.deepcopy(self.obj))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_retention(Path.cwd(), self.plan, 'a' * 40)
        self.plan['objects'].pop()
        self.obj['retained']['sha256'] = '2' * 64
        with self.assertRaisesRegex(ValueError, 'preserve'):
            validate_retention(Path.cwd(), self.plan, 'a' * 40)

    def test_changed_or_unplanned_remote_object_blocks_deletion(self):
        check_inventory(Client([self.remote]), [self.obj], set())
        for rows in [[], [{**self.remote, 'ETag': 'changed'}],
                     [self.remote, {**self.remote, 'Key': 'hydrolakes/display/r1/unplanned.json'}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                check_inventory(Client(rows), [self.obj], set())

    def test_resume_only_accepts_previously_deleted_missing_objects(self):
        check_inventory(Client([]), [self.obj], {self.obj['key']})
        with self.assertRaises(ValueError):
            check_inventory(Client([self.remote]), [self.obj], {self.obj['key']})

    def test_metadata_retirement_requires_exact_declared_keys(self):
        key = 'lakeatlas/metadata/field-semantics-v1/field-semantics.json'
        with self.assertRaises(ValueError):
            checked_key(key, {'lakeatlas'})
        self.assertEqual(checked_key(key, {'lakeatlas'}, {key}), key)
        with self.assertRaises(ValueError):
            checked_key('lakeatlas/metadata/another.json', {'lakeatlas'}, {key})
        remote = {'Key': key, 'ETag': 'old', 'Size': 5}
        obj = {'key': key, 'etag': 'old', 'size_bytes': 5}
        check_inventory(Client([remote]), [obj], set())
        with self.assertRaises(ValueError):
            check_inventory(Client([remote, {**remote, 'Key': 'lakeatlas/metadata/unplanned.json'}]), [obj], set())

    def test_cannot_substitute_another_public_catalog(self):
        with self.assertRaisesRegex(ValueError, 'catalog destination'):
            check_live_catalog({'destination': 'https://example.test/'}, [])

if __name__ == '__main__':
    unittest.main()
