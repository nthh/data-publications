import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import provenance_archive as archive


class ProvenanceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.commit = 'a' * 40
        self.path = 'scripts/example.py'

    def tearDown(self):
        self.tmp.cleanup()

    def write_snapshot(self, data, commit=None, path=None):
        commit = commit or self.commit
        path = path or self.path
        digest = hashlib.sha256(data).hexdigest()
        directory = self.root / archive.ARCHIVE_REL
        (directory / 'blobs').mkdir(parents=True, exist_ok=True)
        (directory / 'blobs' / digest).write_bytes(data)
        index = {'schema_version': 1, 'files': [{'git_revision': commit, 'path': path,
            'sha256': digest, 'bytes': len(data), 'blob': f'blobs/{digest}'}]}
        (directory / 'index.json').write_text(json.dumps(index))
        return digest

    def test_missing_commit_returns_exact_hash_bound_snapshot(self):
        expected = self.write_snapshot(b'archived exact bytes')
        with patch('provenance_archive.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(archive.resolve_blob(self.root, self.commit, self.path, expected),
                             b'archived exact bytes')

    def test_missing_commit_requires_exact_commit_and_path(self):
        self.write_snapshot(b'archived exact bytes')
        with patch('provenance_archive.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(ValueError):
                archive.resolve_blob(self.root, 'b' * 40, self.path)
            with self.assertRaises(ValueError):
                archive.resolve_blob(self.root, self.commit, 'scripts/other.py')

    def test_missing_or_corrupt_snapshot_is_refused(self):
        digest = self.write_snapshot(b'archived exact bytes')
        blob = self.root / archive.ARCHIVE_REL / 'blobs' / digest
        blob.write_bytes(b'corrupt')
        with patch('provenance_archive.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(ValueError):
                archive.resolve_blob(self.root, self.commit, self.path, digest)

    def test_available_git_mismatch_cannot_be_masked_by_archive(self):
        self.write_snapshot(b'archived bytes')
        results = [subprocess.CompletedProcess([], 0),
                   subprocess.CompletedProcess([], 0, stdout=b'different Git bytes')]
        with patch('provenance_archive.subprocess.run', side_effect=results):
            with self.assertRaises(ValueError):
                archive.resolve_blob(self.root, self.commit, self.path)

    def test_available_git_returns_git_bytes_and_checks_expected_hash(self):
        data = b'Git bytes'
        expected = hashlib.sha256(data).hexdigest()
        results = [subprocess.CompletedProcess([], 0),
                   subprocess.CompletedProcess([], 0, stdout=data)]
        with patch('provenance_archive.subprocess.run', side_effect=results):
            self.assertEqual(archive.resolve_blob(self.root, self.commit, self.path, expected), data)
        results = [subprocess.CompletedProcess([], 0),
                   subprocess.CompletedProcess([], 0, stdout=data)]
        with patch('provenance_archive.subprocess.run', side_effect=results):
            with self.assertRaises(ValueError):
                archive.resolve_blob(self.root, self.commit, self.path, 'f' * 64)

    def test_export_and_hash_bound_reopen(self):
        repo = self.root / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        subprocess.run(['git', 'config', 'user.email', 'archive-test@example.invalid'], cwd=repo, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Archive Test'], cwd=repo, check=True)
        source = repo / self.path
        source.parent.mkdir(parents=True)
        source.write_bytes(b'committed bytes')
        subprocess.run(['git', 'add', self.path], cwd=repo, check=True)
        subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=repo, check=True)
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
        result = archive.export_archive(repo, [(commit, self.path)])
        self.assertEqual(result['entries'], 1)
        expected = hashlib.sha256(b'committed bytes').hexdigest()
        isolated = self.root / 'isolated'
        isolated.mkdir()
        import shutil
        shutil.copytree(repo / archive.ARCHIVE_REL, isolated / archive.ARCHIVE_REL)
        with patch('provenance_archive.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(archive.resolve_blob(isolated, commit, self.path, expected), b'committed bytes')


if __name__ == '__main__':
    unittest.main()
