#!/usr/bin/env python3
"""Focused fail-closed tests for LakeATLAS portable evidence preparation."""
from __future__ import annotations
import unittest

from prepare_portable_evidence import REPORT_NAMES, validate_report_bundle


class PortableEvidenceTests(unittest.TestCase):
    def reports(self) -> dict[str, dict[str, object]]:
        values: dict[str, dict[str, object]] = {}
        for name in REPORT_NAMES:
            values[name] = {"status": "passed"}
        for name, checksum, size in (
            ("polygons-primary", "1" * 64, 100),
            ("pour-points-primary", "2" * 64, 200),
            ("polygons-clean", "1" * 64, 100),
            ("pour-points-clean", "2" * 64, 200),
        ):
            spatial = f"spatial-order-{name}.json"
            pruning = f"spatial-pruning-{name}.json"
            values[spatial]["output"] = {"sha256": checksum, "size_bytes": size}
            values[pruning].update({"sha256": checksum, "size_bytes": size})
        return values

    def test_passed_reports_and_bound_pruning_receipts_are_accepted(self) -> None:
        validate_report_bundle(self.reports())

    def test_failed_pruning_report_is_rejected(self) -> None:
        reports = self.reports()
        reports["spatial-pruning-polygons-primary.json"]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "not passed"):
            validate_report_bundle(reports)

    def test_pruning_hash_mismatch_is_rejected(self) -> None:
        reports = self.reports()
        reports["spatial-pruning-pour-points-clean.json"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "does not bind"):
            validate_report_bundle(reports)


if __name__ == "__main__":
    unittest.main()
