import hashlib
import importlib.util
import json
from email.message import Message
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import urllib.error
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('grwl_raw_acquire', ROOT / 'datasets/grwl-raw/acquire.py')
acquire = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acquire)


class Response:
    def __init__(self, status, content_range, data, encoding='identity'):
        self.status = status
        self.headers = {'Content-Range': content_range, 'Content-Encoding': encoding}
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit=-1):
        return self.data[:limit]


class AcquisitionTests(unittest.TestCase):
    data = b'abcdefghijkl'

    def run_patched(self, directory, urlopen, *, size=None, md5=None, resume=False, connections=4):
        size = len(self.data) if size is None else size
        md5 = hashlib.md5(self.data).hexdigest() if md5 is None else md5
        with mock.patch.multiple(acquire, URL='https://example.test/archive', NAME='archive.zip',
                                 SIZE=size, MD5=md5, RANGE_BYTES=4, START_FLOOR=0, STOP_FLOOR=0), \
             mock.patch.object(acquire.shutil, 'disk_usage', return_value=SimpleNamespace(free=1_000_000)), \
             mock.patch.object(acquire.urllib.request, 'urlopen', side_effect=urlopen):
            return acquire.acquire(directory, resume=resume, connections=connections)

    def test_out_of_order_http_results_are_appended_and_receipted_in_order(self):
        lock = threading.Lock()
        active = 0
        maximum_active = 0
        completion_order = []

        def urlopen(request, timeout):
            nonlocal active, maximum_active
            self.assertEqual(timeout, 90)
            self.assertEqual(request.get_header('Accept-encoding'), 'identity')
            start, stop = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.06 if start == 0 else 0.004)
            body = self.data[start:stop + 1]
            with lock:
                active -= 1
                completion_order.append(start)
            return Response(206, f'bytes {start}-{stop}/{len(self.data)}', body)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            result = self.run_patched(directory, urlopen)
            receipt = json.loads((directory / 'acquisition.json').read_text())
            self.assertEqual((directory / 'archive.zip').read_bytes(), self.data)
            self.assertEqual([item['start'] for item in receipt['ranges']], [0, 4, 8])
            self.assertEqual([item['end'] for item in receipt['ranges']], [3, 7, 11])
            self.assertEqual(receipt['status'], 'verified')
            self.assertEqual(receipt['source_sha256'], hashlib.sha256(self.data).hexdigest())
            self.assertEqual(result['status'], 'verified')
            self.assertLess(completion_order.index(4), completion_order.index(0))
            self.assertLessEqual(maximum_active, 4)

    def test_resume_verifies_old_prefix_and_keeps_original_script_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            partial = directory / 'archive.zip.partial'
            prefix = self.data[:4]
            partial.write_bytes(prefix)
            old_hash = 'a' * 64
            receipt = {
                'schema_version': 1, 'url': 'https://example.test/archive', 'filename': 'archive.zip',
                'size_bytes': len(self.data), 'provider_md5': hashlib.md5(self.data).hexdigest(),
                'status': 'failed_partial', 'script_sha256': old_hash, 'received_bytes': 4,
                'ranges': [{'start': 0, 'end': 3, 'bytes': 4, 'sha256': hashlib.sha256(prefix).hexdigest()}],
            }
            (directory / 'acquisition.json').write_text(json.dumps(receipt))
            requested = []

            def urlopen(request, timeout):
                start, stop = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
                requested.append((start, stop))
                return Response(206, f'bytes {start}-{stop}/{len(self.data)}', self.data[start:stop + 1])

            result = self.run_patched(directory, urlopen, resume=True)
            saved = json.loads((directory / 'acquisition.json').read_text())
            self.assertEqual(requested, [(4, 7), (8, 11)])
            self.assertEqual((directory / 'archive.zip').read_bytes(), self.data)
            self.assertEqual(saved['script_sha256'], old_hash)
            self.assertEqual(saved['code_version_history'][0]['script_sha256'], acquire.script_hash())
            self.assertEqual(len(saved['code_version_history']), 1)
            self.assertEqual([item['start'] for item in saved['ranges']], [0, 4, 8])
            self.assertEqual(result['status'], 'verified')

    def test_bad_range_response_preserves_only_receipted_ordered_prefix(self):
        def urlopen(request, timeout):
            start, stop = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            body = self.data[start:stop + 1]
            content_range = f'bytes {start}-{stop}/{len(self.data)}'
            if start == 4:
                time.sleep(0.03)
                content_range = f'bytes {start + 1}-{stop + 1}/{len(self.data)}'
            return Response(206, content_range, body)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'exact requested range'):
                self.run_patched(directory, urlopen)
            receipt = json.loads((directory / 'acquisition.json').read_text())
            self.assertEqual(receipt['status'], 'failed_partial')
            self.assertEqual(receipt['received_bytes'], 4)
            self.assertEqual([item['start'] for item in receipt['ranges']], [0])
            self.assertEqual((directory / 'archive.zip.partial').read_bytes(), self.data[:4])
            self.assertFalse((directory / 'archive.zip').exists())
            self.assertTrue((directory / 'failures.jsonl').exists())

    def test_whole_archive_checksum_failure_keeps_partial_and_failure_receipt(self):
        corrupt = self.data[:8] + b'XXXX'

        def urlopen(request, timeout):
            start, stop = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            return Response(206, f'bytes {start}-{stop}/{len(self.data)}', corrupt[start:stop + 1])

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'provider MD5 mismatch'):
                self.run_patched(directory, urlopen)
            receipt = json.loads((directory / 'acquisition.json').read_text())
            self.assertEqual(receipt['status'], 'failed_partial')
            self.assertEqual(receipt['received_bytes'], len(self.data))
            self.assertEqual((directory / 'archive.zip.partial').read_bytes(), corrupt)
            self.assertFalse((directory / 'archive.zip').exists())
            self.assertNotIn('whole_archive_checksum_verified', receipt)
            self.assertTrue((directory / 'failures.jsonl').exists())

    def test_retry_after_is_capped_and_retry_budget_is_three(self):
        headers = Message()
        headers['Retry-After'] = '300'
        too_many = urllib.error.HTTPError('https://example.test/archive', 429, 'busy', headers, None)
        good = Response(206, f'bytes 0-3/{len(self.data)}', self.data[:4])
        with mock.patch.multiple(acquire, URL='https://example.test/archive', SIZE=len(self.data)), \
             mock.patch.object(acquire.urllib.request, 'urlopen', side_effect=[too_many, good]) as opener, \
             mock.patch.object(acquire.time, 'sleep') as sleep:
            self.assertEqual(acquire._download_range(0, 3), self.data[:4])
            self.assertEqual(opener.call_count, 2)
            sleep.assert_called_once_with(30)

        with mock.patch.multiple(acquire, URL='https://example.test/archive', SIZE=len(self.data)), \
             mock.patch.object(acquire.urllib.request, 'urlopen', side_effect=urllib.error.URLError('offline')) as opener:
            with self.assertRaises(urllib.error.URLError):
                acquire._download_range(0, 3)
            self.assertEqual(opener.call_count, 4)


if __name__ == '__main__':
    unittest.main()
