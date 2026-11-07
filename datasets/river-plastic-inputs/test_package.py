#!/usr/bin/env python3
"""Offline fault tests for release evidence binding and package integrity."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('package_under_test', HERE / 'package.py')
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PackageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.parquet = b'fixture parquet bytes'
        self.manifest = {
            'status': 'local_prepared_not_published', 'dataset': 'river-plastic-inputs',
            'source': {'metadata_timestamp': '2026-10-30T12:00:00Z'},
            'conversion_git_commit': 'a' * 40, 'records': 2,
            'assets': {'river-plastic-inputs/data.parquet': {'size_bytes': len(self.parquet), 'sha256': sha(self.parquet)}}
        }
        self.manifest_bytes = (json.dumps(self.manifest, indent=2) + '\n').encode()
        self.manifest_sha = sha(self.manifest_bytes)
        self.parquet_sha = self.manifest['assets']['river-plastic-inputs/data.parquet']['sha256']
        self.code = {'test_publication.py': b'print("fault cases")\n'}
        self.history = {f'verification/history/{name}': f'fixture:{name}'.encode()
                        for name in pkg.HISTORY_FILES}
        history_hashes = {Path(name).name: sha(raw) for name, raw in self.history.items()}
        self.evidence = {
            'validation': {'status': 'passed', 'http': {'status': 'passed'}, 'source_rows': 2,
                           'release_manifest_sha256': self.manifest_sha},
            'stac_validation': {'exit_code': 0, 'release_manifest_sha256': self.manifest_sha},
            'reproducibility': {'status': 'passed', 'manifest_equal': True,
                                'conversion_git_commit': self.manifest['conversion_git_commit'],
                                'manifest_sha256': self.manifest_sha,
                                'hashes': {'river-plastic-inputs/data.parquet': self.parquet_sha}},
            'publication_validation': {'status': 'passed', 'provenance': {
                'release_manifest_sha256': self.manifest_sha, 'geoparquet_sha256': self.parquet_sha,
                'benchmark_contract_sha256': history_hashes['publication-benchmarks.json']}},
            'gee_validation': {'status': 'passed_with_documented_geometry_difference',
                               'strict_coordinate_parity': 'failed',
                               'provenance': {'geoparquet_sha256': self.parquet_sha,
                                   'parent_contract_sha256': history_hashes['gee-parity-contract.json'],
                                   'diagnostic_contract_sha256': history_hashes['gee-geometry-diagnostic.json'],
                                   'coincident_contract_sha256': history_hashes['gee-coincident-diagnostic.json'],
                                   'capture_receipt_sha256': history_hashes['gee-capture.json']}},
            'fault_tests': {'status': 'passed', 'cases': 2, 'release_manifest_sha256': self.manifest_sha,
                            'tests': [{'path': 'test_publication.py', 'sha256': sha(self.code['test_publication.py']), 'exit_code': 0}]},
            'fault_test_file_bytes': self.code,
            'historical_file_bytes': self.history,
        }

    def test_valid_evidence(self):
        result = pkg.validate_evidence(self.manifest_bytes, self.evidence)
        self.assertEqual(result['manifest_sha256'], self.manifest_sha)
        self.assertEqual(result['geoparquet_sha256'], self.parquet_sha)

    def test_wrong_manifest_bindings_rejected(self):
        for key in ('validation', 'stac_validation', 'publication_validation', 'fault_tests'):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.evidence)
                target = bad[key]
                if key == 'publication_validation': target['provenance']['release_manifest_sha256'] = '0' * 64
                else: target['release_manifest_sha256'] = '0' * 64
                with self.assertRaises(ValueError): pkg.validate_evidence(self.manifest_bytes, bad)
        bad_manifest = copy.deepcopy(self.manifest); bad_manifest['records'] += 1
        with self.assertRaises(ValueError): pkg.validate_evidence((json.dumps(bad_manifest)).encode(), self.evidence)

    def test_wrong_publication_or_gee_data_hash_rejected(self):
        for key in ('publication_validation', 'gee_validation'):
            bad = copy.deepcopy(self.evidence)
            bad[key]['provenance']['geoparquet_sha256'] = '0' * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'GeoParquet|release data'):
                pkg.validate_evidence(self.manifest_bytes, bad)


    def test_checked_out_history_sources_exist(self):
        for source in pkg.HISTORY_FILES.values():
            with self.subTest(source=source):
                self.assertTrue((HERE / source).is_file(), source)

    def test_checked_out_historical_reports_bind_to_archived_bytes(self):
        manifest_bytes = (HERE / 'evidence/release-manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        manifest_sha = sha(manifest_bytes)
        parquet_sha = next(value['sha256'] for name, value in manifest['assets'].items() if name.endswith('.parquet'))
        history = {f'verification/history/{name}': (HERE / source).read_bytes()
                   for name, source in pkg.HISTORY_FILES.items()}
        evidence = copy.deepcopy(self.evidence)
        evidence['validation'].update(source_rows=manifest['records'], release_manifest_sha256=manifest_sha)
        evidence['stac_validation']['release_manifest_sha256'] = manifest_sha
        evidence['reproducibility'].update(manifest_sha256=manifest_sha,
            conversion_git_commit=manifest['conversion_git_commit'],
            hashes={name: item['sha256'] for name, item in manifest['assets'].items()})
        evidence['publication_validation'] = json.loads((HERE / 'evidence/publication-validation.json').read_text())
        evidence['gee_validation'] = json.loads((HERE / 'evidence/gee-validation.json').read_text())
        evidence['fault_tests'].update(release_manifest_sha256=manifest_sha,
            tests=[{'path': 'test_package.py', 'sha256': sha((HERE / 'test_package.py').read_bytes()), 'exit_code': 0}])
        evidence['fault_test_file_bytes'] = {'test_package.py': (HERE / 'test_package.py').read_bytes()}
        evidence['historical_file_bytes'] = history
        self.assertEqual(pkg.validate_evidence(manifest_bytes, evidence)['geoparquet_sha256'], parquet_sha)

    def test_historical_contract_and_capture_bindings_rejected(self):
        cases = [
            ('publication_validation', 'provenance', 'benchmark_contract_sha256'),
            ('gee_validation', 'provenance', 'parent_contract_sha256'),
            ('gee_validation', 'provenance', 'diagnostic_contract_sha256'),
            ('gee_validation', 'provenance', 'coincident_contract_sha256'),
            ('gee_validation', 'provenance', 'capture_receipt_sha256'),
        ]
        for receipt, nested, field in cases:
            bad = copy.deepcopy(self.evidence)
            bad[receipt][nested][field] = '0' * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'different|references'):
                pkg.validate_evidence(self.manifest_bytes, bad)

    def test_missing_failed_and_mismatched_checks_rejected(self):
        cases = []
        bad = copy.deepcopy(self.evidence); bad['validation']['status'] = 'failed'; cases.append(bad)
        bad = copy.deepcopy(self.evidence); bad['stac_validation']['exit_code'] = 1; cases.append(bad)
        bad = copy.deepcopy(self.evidence); bad['reproducibility']['manifest_equal'] = False; cases.append(bad)
        bad = copy.deepcopy(self.evidence); bad['reproducibility']['hashes']['extra.parquet'] = '1' * 64; cases.append(bad)
        bad = copy.deepcopy(self.evidence); bad['publication_validation']['status'] = 'failed'; cases.append(bad)
        bad = copy.deepcopy(self.evidence); bad['gee_validation']['strict_coordinate_parity'] = 'passed'; cases.append(bad)
        bad = copy.deepcopy(self.evidence); bad['fault_tests']['status'] = 'failed'; cases.append(bad)
        bad = copy.deepcopy(self.evidence); del bad['gee_validation']; cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pkg.validate_evidence(self.manifest_bytes, bad)

    def test_fault_script_hash_and_path_are_checked(self):
        bad = copy.deepcopy(self.evidence); bad['fault_tests']['tests'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'code hash'):
            pkg.validate_evidence(self.manifest_bytes, bad)
        bad = copy.deepcopy(self.evidence); bad['fault_tests']['tests'][0]['path'] = '../private.py'
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            pkg.validate_evidence(self.manifest_bytes, bad)
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            pkg.safe_relative('.')
        bad_manifest = copy.deepcopy(self.manifest); bad_manifest['assets'] = {'../escape.parquet': {'size_bytes': 1, 'sha256': '0'*64}}
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            pkg.validate_evidence(json.dumps(bad_manifest).encode(), self.evidence)

    def test_archive_integrity_and_mutation_detection(self):
        with tempfile.TemporaryDirectory(prefix='package-check-') as temp:
            archive = Path(temp) / 'release.zip'
            names = {
                'manifest.json': self.manifest_bytes,
                'river-plastic-inputs/data.parquet': self.parquet,
                'verification/receipt.json': b'{}\n',
            }
            binding = {'manifest_sha256': self.manifest_sha, 'verification_sha256': {}}
            names['verification/receipt.json'] = (json.dumps(binding)).encode()
            with zipfile.ZipFile(archive, 'w') as zf:
                for name, raw in names.items(): zf.writestr(name, raw)
            self.assertEqual(pkg.check_archive(archive)['status'], 'archive_hashes_verified')
            altered = Path(temp) / 'altered.zip'
            with zipfile.ZipFile(archive) as src, zipfile.ZipFile(altered, 'w') as dst:
                for info in src.infolist():
                    raw = src.read(info.filename)
                    if info.filename.endswith('.parquet'): raw += b'tampered'
                    dst.writestr(info.filename, raw)
            with self.assertRaisesRegex(ValueError, 'asset hash mismatch'):
                pkg.check_archive(altered)


if __name__ == '__main__':
    unittest.main(verbosity=2)
