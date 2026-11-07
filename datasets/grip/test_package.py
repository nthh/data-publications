"""Offline fault tests for GRIP immutable release packaging."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("grip_package_under_test", HERE / "package.py")
package_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_module)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class GripPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.here = self.project / "datasets" / "grip"
        self.here.mkdir(parents=True)
        (self.project / "LICENSE").write_text("Apache License test notice\n")
        (self.project / "NOTICE").write_text("Folia notices\n")
        self.record = {
            "schema_version": 1,
            "id": "grip",
            "title": "GRIP4 global roads — 2018",
            "source": {
                "source_doi": "10.5281/zenodo.6420961",
                "source_sha256": "a" * 64,
                "expected_rows": 42,
                "source_url": "https://example.invalid/source.zip",
            },
            "build": {"release": "fixture-r1", "batch_size": 100},
        }
        self.record_bytes = (
            "schema_version: 1\n"
            "id: grip\n"
            "title: GRIP4 global roads — 2018\n"
            "source:\n"
            "  source_doi: 10.5281/zenodo.6420961\n"
            f"  source_sha256: {'a' * 64}\n"
            "  expected_rows: 42\n"
            "  source_url: https://example.invalid/source.zip\n"
            "build:\n"
            "  release: fixture-r1\n"
            "  batch_size: 100\n"
        ).encode()
        (self.here / "dataset.yaml").write_bytes(self.record_bytes)
        self.workflow_path = self.here / "build.py"
        self.workflow_path.write_text("print('fixture builder')\n")

        self.release = self.root / "release"
        (self.release / "grip" / "data").mkdir(parents=True)
        (self.release / "dataset.yaml").write_bytes(self.record_bytes)
        files = {
            "catalog.json": b'{"type":"Catalog"}\n',
            "grip/collection.json": b'{"type":"Collection"}\n',
            "grip/data/region-1.parquet": b"small parquet fixture",
            "grip/grip.pmtiles": b"PMTiles\x03small pmtiles fixture",
            "grip/schema.json": b'{"fields":[]}\n',
            "grip/original-attribute-dictionary.xlsx": b"tiny workbook fixture",
        }
        for rel, payload in files.items():
            path = self.release / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

        self.config = {"id": self.record["id"], "title": self.record["title"],
                       **self.record["source"], **self.record["build"]}
        self.assets = {
            rel: {"size_bytes": len(payload), "sha256": sha(payload)}
            for rel, payload in files.items()
        }
        self.assets["dataset.yaml"] = {"size_bytes": len(self.record_bytes), "sha256": sha(self.record_bytes)}
        self.manifest = {
            "schema_version": 1,
            "dataset": "grip",
            "release": "fixture-r1",
            "source": self.config,
            "effective_config_sha256": package_module._effective_config_sha(self.config),
            "dataset_record_sha256_at_build": sha(self.record_bytes),
            "conversion_git_commit": "c" * 40,
            "build_input_sha256": {"build.py": sha(self.workflow_path.read_bytes())},
            "assets": self.assets,
        }
        self._write_manifest()
        self.reports = self.root / "reports"
        self.reports.mkdir()
        self._write_reports()

        self.old_here = package_module.HERE
        self.old_repo = package_module.REPO_ROOT
        package_module.HERE = self.here
        package_module.REPO_ROOT = self.project

    def tearDown(self):
        package_module.HERE = self.old_here
        package_module.REPO_ROOT = self.old_repo
        self.temp.cleanup()

    def _write_manifest(self):
        raw = (json.dumps(self.manifest, indent=2, sort_keys=True) + "\n").encode()
        (self.release / "manifest.json").write_bytes(raw)
        self.manifest_bytes = raw
        self.manifest_sha = sha(raw)

    def _write_reports(self):
        common = {"release_manifest_sha256": self.manifest_sha}
        report_data = {
            "validation.json": {**common, "status": "passed", "source_rows": 42, "source_sha256": "a" * 64,
                "exact_geometry_records": 42,
                "http": {"status": "passed", "range_and_cors": True, "duckdb_spatial_subset_rows": 1, "partitions_read": 7}, "catalog": {"status": "passed"},
                "pmtiles": {"status": "passed", "structure_verified": True,
                    "all_tile_ids_and_attributes_checked": True, "geometry_features_checked": 1,
                    "maximum_sampled_error_tile_units": 0.6, "maximum_allowed_error_tile_units": 4.0},
                "geoparquet": {"status": "passed", "rows": 42, "partitions": 7}},
            "stac-validation.json": {**common, "status": "passed", "validated_documents": 2, "invalid": 0, "skipped": 0},
            "portolan-validation.json": {**common, "status": "passed", "exit_code": 0, "rawresult": {"passed": True, "error_count": 0, "files_checked": 2}},
            "reproducibility.json": {**common, "status": "passed", "manifest_equal": True,
                "conversion_git_commit": self.manifest["conversion_git_commit"], "assets_compared": len(self.assets),
                "hashes": {name: item["sha256"] for name, item in self.assets.items()}},
            "fault-tests.json": {**common, "status": "passed", "cases": 4,
                "tests": [{"id": f"case-{i}", "status": "passed", "detail": "deliberate fixture fault rejected"} for i in range(4)]},
        }
        for name, report in report_data.items():
            (self.reports / name).write_text(json.dumps(report, indent=2) + "\n")

    def _refresh_reports(self):
        self._write_manifest()
        self._write_reports()

    def test_packages_complete_bundle_with_deterministic_archive(self):
        output1 = self.root / "first.zip"
        output2 = self.root / "second.zip"
        package_module.package(self.release, self.reports, output1)
        package_module.package(self.release, self.reports, output2)
        self.assertEqual(sha(output1.read_bytes()), sha(output2.read_bytes()))
        self.assertEqual(package_module.check_archive(output1)["status"], "passed")
        with zipfile.ZipFile(output1) as archive:
            names = set(archive.namelist())
            self.assertIn("dataset.yaml", names)
            self.assertIn("workflow/datasets/grip/build.py", names)
            self.assertIn("workflow/datasets/grip/dataset.yaml", names)
            self.assertIn("workflow/README.md", names)
            self.assertIn("workflow/LICENSE", names)
            self.assertIn("workflow/NOTICE", names)
            self.assertIn("reports/validation.json", names)
            package_manifest = json.loads(archive.read("package-manifest.json"))
            self.assertEqual(package_manifest["license"], "CC-BY-4.0")
            self.assertEqual(package_manifest["workflow_code_license"], "Apache-2.0")
            self.assertIn("prose", package_manifest["license_note"])
            self.assertEqual(len(package_manifest["reports"]), 5)

    def test_missing_data_asset_is_rejected(self):
        (self.release / "grip/data/region-1.parquet").unlink()
        with self.assertRaisesRegex(ValueError, "inventory differs|Expected a regular file"):
            package_module.package(self.release, self.reports, self.root / "missing.zip")

    def test_wrong_asset_hash_is_rejected(self):
        (self.release / "grip/data/region-1.parquet").write_bytes(b"changed parquet")
        with self.assertRaisesRegex(ValueError, "asset bytes differ"):
            package_module.package(self.release, self.reports, self.root / "wronghash.zip")

    def test_stale_report_and_failed_report_are_rejected(self):
        path = self.reports / "validation.json"
        report = json.loads(path.read_text())
        report["release_manifest_sha256"] = "0" * 64
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "stale"):
            package_module.package(self.release, self.reports, self.root / "stale.zip")
        self._write_reports()
        path = self.reports / "portolan-validation.json"
        report = json.loads(path.read_text())
        report["status"] = "failed"
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "Portolan validation did not pass"):
            package_module.package(self.release, self.reports, self.root / "failed.zip")

    def test_unrun_http_and_failed_tile_gates_are_rejected(self):
        path = self.reports / "validation.json"
        report = json.loads(path.read_text())
        report["http"]["status"] = "not_run"
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "HTTP range and spatial subset"):
            package_module.package(self.release, self.reports, self.root / "http-not-run.zip")
        self._write_reports()
        report = json.loads(path.read_text())
        report["pmtiles"]["status"] = "failed"
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "PMTiles validation"):
            package_module.package(self.release, self.reports, self.root / "tiles-failed.zip")
        self._write_reports()
        report = json.loads(path.read_text())
        report["pmtiles"]["geometry_features_checked"] = 0
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "did not check any display geometries"):
            package_module.package(self.release, self.reports, self.root / "tiles-no-samples.zip")

    def test_contradictory_portolan_raw_result_is_rejected(self):
        path = self.reports / "portolan-validation.json"
        report = json.loads(path.read_text())
        report["rawresult"]["passed"] = False
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "Portolan raw result"):
            package_module.package(self.release, self.reports, self.root / "contradictory.zip")

    def test_changed_workflow_input_and_unsafe_path_are_rejected(self):
        self.workflow_path.write_text("print('changed builder')\n")
        with self.assertRaisesRegex(ValueError, "workflow input differs"):
            package_module.package(self.release, self.reports, self.root / "changed-code.zip")
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            package_module.safe_relative("../escape.parquet")

    def test_wrong_workflow_code_path_is_rejected(self):
        self.manifest["build_input_sha256"] = {"../build.py": sha(self.workflow_path.read_bytes())}
        self._refresh_reports()
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            package_module.package(self.release, self.reports, self.root / "wrong-code-path.zip")

    def test_escaping_manifest_asset_is_rejected(self):
        payload = self.assets.pop("grip/data/region-1.parquet")
        self.assets["../escape.parquet"] = payload
        self.manifest["assets"] = self.assets
        self._refresh_reports()
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            package_module.package(self.release, self.reports, self.root / "escape.zip")

    def test_existing_archive_is_never_overwritten(self):
        output = self.root / "immutable.zip"
        package_module.package(self.release, self.reports, output)
        before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            package_module.package(self.release, self.reports, output)
        self.assertEqual(output.read_bytes(), before)

    def test_package_manifest_hash_tampering_is_rejected(self):
        output = self.root / "tamper.zip"
        package_module.package(self.release, self.reports, output)
        altered = self.root / "tamper-altered.zip"
        with zipfile.ZipFile(output) as original, zipfile.ZipFile(altered, "w", compression=zipfile.ZIP_STORED) as changed:
            for info in original.infolist():
                raw = original.read(info.filename)
                if info.filename == "grip/data/region-1.parquet":
                    raw += b"bad"
                changed.writestr(info, raw)
        with self.assertRaisesRegex(ValueError, "Package member hash mismatch"):
            package_module.check_archive(altered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
