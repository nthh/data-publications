"""Offline checks for JRC metadata-only range budgets and immutable evidence."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "research/hydro-releases-20261031/jrc/qualify_occurrence_ranges.py"
spec = importlib.util.spec_from_file_location("qualify", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Response:
    def __init__(self, status=206, chunks=(b"ab", b"cd"), fail=False):
        self.status_code = status
        self.headers = {"Content-Range": "bytes 0-3/100", "Content-Length": "4"}
        self.chunks, self.fail, self.consumed = chunks, fail, False
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size):
        self.consumed = True
        for chunk in self.chunks: yield chunk
        if self.fail: raise TimeoutError("injected interrupted range")


class QualificationTests(unittest.TestCase):
    def test_ignored_range_is_not_consumed(self):
        response = Response(status=200)
        with patch.object(probe.requests, "get", return_value=response):
            budget = probe.Budget(4)
            data, report = budget.read("https://example.invalid", 0, 4, (1, 1))
        self.assertEqual(data, b"")
        self.assertFalse(response.consumed)
        self.assertEqual(budget.used, 0)
        self.assertFalse(report["range_honored"])

    def test_success_and_aggregate_cap(self):
        with patch.object(probe.requests, "get", return_value=Response()):
            budget = probe.Budget(4)
            data, report = budget.read("https://example.invalid", 0, 4, (1, 1))
            self.assertEqual(data, b"abcd")
            self.assertTrue(report["complete_requested_range"])
            self.assertEqual(budget.used, 4)
            with self.assertRaisesRegex(RuntimeError, "budget would exceed"):
                budget.read("https://example.invalid", 0, 1, (1, 1))

    def test_interrupted_bytes_still_count(self):
        with patch.object(probe.requests, "get", return_value=Response(chunks=(b"ab",), fail=True)):
            budget = probe.Budget(4)
            _, report = budget.read("https://example.invalid", 0, 4, (1, 1))
        self.assertEqual(budget.used, 2)
        self.assertEqual(report["response_bytes_read"], 2)
        self.assertIn("TimeoutError", report["error"])

    def test_prior_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "original.json"
            output.write_text("preserved")
            result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertEqual(output.read_text(), "preserved")


if __name__ == "__main__": unittest.main()
