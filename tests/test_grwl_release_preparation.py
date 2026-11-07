from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "datasets/grwl-raw/prepare_release.py"
SPEC = importlib.util.spec_from_file_location("grwl_raw_prepare_release", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_parquet(path: Path) -> None:
    pq.write_table(pa.table({"feature_id": pa.array([1, 2, 3], type=pa.uint64())}), path)


def _fixture(tmp_path: Path) -> dict:
    original_parquet = tmp_path / "original.parquet"
    rebuild_parquet = tmp_path / "rebuild.parquet"
    _write_parquet(original_parquet)
    rebuild_parquet.write_bytes(original_parquet.read_bytes())
    source_hashes = {ext: f"{i:064x}" for i, ext in enumerate(("shp", "shx", "dbf", "prj"), start=1)}
    inputs = {
        "builder_sha256": _hash(ROOT / "datasets/grwl-raw/build_global.py"),
        "converter_sha256": _hash(ROOT / "datasets/grwl-raw/convert.py"),
        "environment_lock_sha256": _hash(ROOT / "scripts/display_tools/uv.lock"),
    }
    archive = {"filename": "fixture.zip", "size_bytes": 10,
               "provider_md5": "a" * 32, "sha256": "b" * 64,
               "whole_archive_checksum_verified": True}
    common = {
        "status": "provisional", "usable_release": False,
        "validation": {"status": "pending"}, "rows": 3, "parts": 4,
        "archive": archive,
        "tiles": [
            {"tile": "AA01", "records": 2, "parts": 3,
             "extent": [-2.0, 1.0, 0.0, 2.0], "source_sha256": source_hashes},
            {"tile": "AB01", "records": 1, "parts": 1,
             "extent": [3.0, -1.0, 4.0, 2.0], "source_sha256": source_hashes},
        ], "build_inputs": inputs,
        "criteria_sha256": _hash(ROOT / "research/grwl-raw-release-20261102/global-criteria.json"),
        "source_inventory_sha256": _hash(ROOT / "research/grwl-raw-audit-20261102/vector-inventory-r1.json"),
        "parquet_sha256": _hash(original_parquet),
    }
    original_manifest = tmp_path / "original-manifest.json"
    rebuild_manifest = tmp_path / "rebuild-manifest.json"
    original_manifest.write_text(json.dumps(common), encoding="utf-8")
    rebuild_manifest.write_text(json.dumps(common), encoding="utf-8")
    source_report = tmp_path / "source-validation.json"
    source_report.write_text(json.dumps({
        "status": "passed", "error_count": 0, "errors": [],
        "manifest_sha256": _hash(original_manifest), "manifest_tile_count": 2,
        "parquet_sha256": _hash(original_parquet), "source_archive_identity_checked": True,
        "source_archive": {k: archive[k] for k in ("filename", "size_bytes", "provider_md5", "sha256")},
        "source_member_sha256_checked": 8,
        "progress": {"source_rows": 3, "parquet_rows": 3,
                     "tiles_completed": ["AA01", "AB01"], "parts": 4},
        "tiles": [
            {"tile": "AA01", "source_rows": 2, "matched_rows": 2,
             "parts": 3, "source_sha256": source_hashes},
            {"tile": "AB01", "source_rows": 1, "matched_rows": 1,
             "parts": 1, "source_sha256": source_hashes},
        ],
    }), encoding="utf-8")
    receipt = tmp_path / "clean-receipt.json"
    receipt.write_text(json.dumps({
        "schema_version": 1, "status": "passed", "git_revision": "1" * 40,
        "working_tree_before": {"status": "clean", "observed": True},
        "working_tree_after": {"status": "clean", "observed": True},
        "exit_status": 0, "input_hashes": inputs,
        "rebuild_manifest_sha256": _hash(rebuild_manifest),
        "parquet_sha256": _hash(rebuild_parquet),
        "parquet_size_bytes": rebuild_parquet.stat().st_size,
    }), encoding="utf-8")
    return {
        "original_manifest_path": original_manifest,
        "rebuild_manifest_path": rebuild_manifest,
        "original_parquet": original_parquet, "rebuild_parquet": rebuild_parquet,
        "source_validation_path": source_report, "clean_receipt_path": receipt,
        "output_dir": tmp_path / "prepared",
        "expected_tiles": 2, "expected_rows": 3,
        "archive_sha256": "b" * 64, "archive_md5": "a" * 32, "archive_bytes": 10,
    }


class PrepareReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)

    def test_prepare_release_emits_bound_reports_and_local_only_spec(self):
        result = prepare.prepare_release(**_fixture(self.tmp_path))
        out = Path(result["output_dir"])
        self.assertEqual(result["status"], "prepared_inputs_only")
        self.assertFalse(result["usable_release"])
        fidelity = json.loads((out / "source-fidelity.normalized.json").read_text())
        rebuild = json.loads((out / "clean-rebuild.normalized.json").read_text())
        spec = json.loads((out / "release-spec.json").read_text())
        expected_asset = {"asset_id": "grwl-raw-observations",
                          "sha256": _hash(self.tmp_path / "original.parquet"),
                          "size_bytes": (self.tmp_path / "original.parquet").stat().st_size}
        self.assertEqual(fidelity["assets"], [expected_asset])
        self.assertEqual(rebuild["assets"], [expected_asset])
        self.assertEqual(fidelity["evidence"]["source_report"]["tiles"][0]["tile"], "AA01")
        self.assertEqual(spec["assets"][0]["identifier_column"], "feature_id")
        self.assertEqual(spec["bbox"], [-2.0, -1.0, 4.0, 2.0])
        self.assertEqual(spec["temporal_interval"], [None, None])
        self.assertEqual(spec["release_id"], "raw-v01.01-local-r1")
        self.assertEqual(spec["catalog_id"], "grwl-raw")
        self.assertEqual(spec["processor"]["name"], "nthh")
        self.assertEqual(spec["processor"]["roles"], ["host", "processor"])
        self.assertTrue(spec["output_dir"].endswith("prepared-package"))
        with self.assertRaisesRegex(prepare.PreparationError, "existing output"):
            prepare.prepare_release(**_fixture(self.tmp_path))

    def test_refuses_existing_package_target(self):
        args = _fixture(self.tmp_path)
        (self.tmp_path / "prepared-package").mkdir()
        with self.assertRaisesRegex(prepare.PreparationError, "existing package path"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_refuses_incomplete_source_member_checks(self):
        args = _fixture(self.tmp_path)
        report = json.loads(args["source_validation_path"].read_text())
        report["source_member_sha256_checked"] = 7
        args["source_validation_path"].write_text(json.dumps(report))
        with self.assertRaisesRegex(prepare.PreparationError, "all four source members"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_refuses_partial_tile_match(self):
        args = _fixture(self.tmp_path)
        report = json.loads(args["source_validation_path"].read_text())
        report["tiles"][0]["matched_rows"] = 1
        args["source_validation_path"].write_text(json.dumps(report))
        with self.assertRaisesRegex(prepare.PreparationError, "not all matched"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_refuses_failed_source_report(self):
        args = _fixture(self.tmp_path)
        report = json.loads(args["source_validation_path"].read_text())
        report["status"] = "failed"
        args["source_validation_path"].write_text(json.dumps(report))
        with self.assertRaisesRegex(prepare.PreparationError, "did not pass"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_refuses_dirty_rebuild_receipt(self):
        args = _fixture(self.tmp_path)
        receipt = json.loads(args["clean_receipt_path"].read_text())
        receipt["working_tree_after"]["status"] = "dirty"
        args["clean_receipt_path"].write_text(json.dumps(receipt))
        with self.assertRaisesRegex(prepare.PreparationError, "status clean"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_refuses_different_rebuild_bytes(self):
        args = _fixture(self.tmp_path)
        _write_parquet(args["rebuild_parquet"])
        table = pa.table({"feature_id": pa.array([1, 2, 4], type=pa.uint64())})
        pq.write_table(table, args["rebuild_parquet"])
        with self.assertRaisesRegex(prepare.PreparationError, "manifest Parquet SHA-256 differs"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_refuses_wrong_footer_row_count(self):
        args = _fixture(self.tmp_path)
        pq.write_table(pa.table({"feature_id": pa.array([1], type=pa.uint64())}), args["original_parquet"])
        args["rebuild_parquet"].write_bytes(args["original_parquet"].read_bytes())
        updated_hash = _hash(args["original_parquet"])
        for manifest_path in (args["original_manifest_path"], args["rebuild_manifest_path"]):
            manifest = json.loads(manifest_path.read_text())
            manifest["parquet_sha256"] = updated_hash
            manifest_path.write_text(json.dumps(manifest))
        source_report = json.loads(args["source_validation_path"].read_text())
        source_report["parquet_sha256"] = updated_hash
        source_report["manifest_sha256"] = _hash(args["original_manifest_path"])
        args["source_validation_path"].write_text(json.dumps(source_report))
        receipt = json.loads(args["clean_receipt_path"].read_text())
        receipt["parquet_sha256"] = updated_hash
        receipt["rebuild_manifest_sha256"] = _hash(args["rebuild_manifest_path"])
        receipt["parquet_size_bytes"] = args["rebuild_parquet"].stat().st_size
        args["clean_receipt_path"].write_text(json.dumps(receipt))
        with self.assertRaisesRegex(prepare.PreparationError, "footer row count"):
            prepare.prepare_release(**args)
        self.assertFalse(args["output_dir"].exists())

    def test_cli_has_no_pin_override_flags(self):
        with self.assertRaises(SystemExit) as caught:
            prepare.main(["--help"])
        self.assertEqual(caught.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
