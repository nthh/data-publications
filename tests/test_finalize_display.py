from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "display_tools"))
import finalize


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FinalizeDisplayTests(unittest.TestCase):
    @staticmethod
    def refresh_files(package: Path) -> None:
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        files = {}
        for path in sorted(package.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                data = path.read_bytes()
                files[path.relative_to(package).as_posix()] = {"size_bytes": len(data), "sha256": digest(data)}
        manifest["files"] = files
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    def fixture(self, base: Path):
        package = base / "package"
        (package / "assets").mkdir(parents=True)
        (package / "styles").mkdir()
        (package / "reports").mkdir()
        tile = b"PMTiles archive fixture"
        style = json.dumps({
            "version": 8,
            "sources": {"data": {"type": "vector", "url": "../assets/sample.pmtiles"}},
            "layers": [{"id": "sample", "type": "fill", "source": "data", "source-layer": "sample-layer"}],
        }, sort_keys=True).encode() + b"\n"
        missing_ids = b""
        (package / "assets" / "sample.pmtiles").write_bytes(tile)
        (package / "styles" / "sample.json").write_bytes(style)
        (package / "sample.maxzoom-missing-ids.txt").write_bytes(missing_ids)
        source_sha = "1" * 64
        source_path = "assets/source.parquet"
        asset = {
            "id": "sample-1", "title": "Sample", "path": "assets/sample.pmtiles",
            "size_bytes": len(tile), "sha256": digest(tile), "source_layer": "sample-layer",
            "geometry_type": "polygon", "min_zoom": 0, "max_zoom": 12,
            "id_field": "source_id", "source_rows": 100, "attribute_fields": ["source_id", "name"],
            "source_asset": {"path": source_path, "size_bytes": 9876, "sha256": source_sha},
            "style_path": "styles/sample.json", "id_encoding": "mvt_feature_id_and_property",
        }
        build_report = {
            "dataset_key": "sample", "source_path": "sample/releases/r1/assets/source.parquet",
            "source_sha256": source_sha, "source_rows": 100, "unique_source_ids": 100,
            "id_field": "source_id", "id_encoding": "mvt_feature_id_and_property",
            "attribute_fields": ["source_id", "name"], "geometry_type": "polygon", "layer": "sample-layer",
            "pmtiles_path": "assets/sample.pmtiles", "pmtiles_sha256": digest(tile),
            "pmtiles_size_bytes": len(tile), "min_zoom": 0, "max_zoom": 12,
            "maxzoom_tiles": 10, "maxzoom_ids_decoded": 100, "maxzoom_ids_accounted": 100,
            "maxzoom_ids_attribute_checked": 100, "maxzoom_missing_id_count": 0,
            "maxzoom_missing_ids_sha256": digest(missing_ids),
            "maxzoom_missing_ids_path": "sample.maxzoom-missing-ids.txt",
            "maxzoom_missing_classification_path": "sample.maxzoom-missing-classification.jsonl",
            "maxzoom_missing_classification_counts": {}, "pmtiles_bounds": [-10, -10, 10, 10],
        }
        (package / "reports" / "sample-layer.build-report.json").write_text(json.dumps(build_report))
        (package / "README.md").write_text("# Sample\n\nProvisional.\n")
        inventory = {}
        for path in sorted(package.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                data = path.read_bytes()
                inventory[path.relative_to(package).as_posix()] = {"size_bytes": len(data), "sha256": digest(data)}
        manifest = {"schema_version": 1, "dataset_id": "sample", "display_release": "display-v1",
                    "analytic_release": "r1", "status": "provisional", "attribution": "Sample producer; CC BY 4.0",
                    "assets": [asset], "files": inventory}
        (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

        regions = {"global": 32, "north_america": 8, "southwest_europe": 8,
                   "south_america": 8, "asia": 8, "oceania": 8}
        groups = {}
        n = 1
        for region, count in regions.items():
            groups[region] = list(range(n, n + count))
            n += count
        sample_ids = sorted({fid for values in groups.values() for fid in values})
        geometry = {
            "asset_id": asset["id"], "source_asset_path": source_path,
            "source_size_bytes": asset["source_asset"]["size_bytes"], "source_sha256": source_sha,
            "pmtiles_asset_path": asset["path"], "pmtiles_size_bytes": len(tile), "pmtiles_sha256": digest(tile),
            "id_encoding": "mvt_feature_id_and_property", "sample_rule": {"selection": "lowest eligible IDs after <=64 bbox tiles cap",
                "global_ids": 32, "ids_per_region": 8, "regional_filter": "source bbox intersects frozen window", "max_bbox_tiles": 64},
            "tolerance_m": 30, "failures": [], "passed": True, "sample_groups": groups,
            "samples": [{"id": fid, "distance_m": 0.5, "failures": []} for fid in sample_ids],
            "sampled_unique_ids": len(sample_ids), "source_rows_scanned": 100, "max_distance_m": 0.5,
        }
        geometry_path = base / "geometry.json"
        geometry_path.write_text(json.dumps(geometry))
        browser = {"schema_version": 1, "dataset_id": "sample", "status": "passed",
                   "transfer_ceiling_bytes": 128 * 1024 * 1024, "cases": []}
        for region in ("global", "north_america"):
            browser["cases"].append({
                "dataset_id": "sample", "layer_id": asset["id"], "format": "pmtiles",
                "source_sha256": digest(tile), "source_size_bytes": len(tile), "region": region,
                "status": "passed", "viewer": {"phase": "ready", "feature_count": 1},
                "all_attributes_note": "All source attributes loaded", "all_attribute_count": 2,
                "expected_source_attribute_count": 2,
                "response_body_bytes": 5,
                "requests": [{"method": "GET", "status": 206, "completed": True, "range": "bytes=0-4",
                              "content_range": f"bytes 0-4/{len(tile)}", "content_length": 5,
                              "object_size_bytes": len(tile), "cors": "*"}],
                "page_errors": [], "external_requests": [],
            })
        browser_path = base / "browser.json"
        browser_path.write_text(json.dumps(browser))
        repo_root = base / "repo"
        return package, geometry_path, browser_path, repo_root

    def finalize(self, fixture):
        package, geometry, browser, repo_root = fixture
        asset_id = json.loads((package / "manifest.json").read_text())["assets"][0]["id"]
        def verify(asset, archive_path):
            return {"schema_version": 1, "asset_id": asset["id"], "command": ["pmtiles", "verify", str(archive_path)],
                    "executable_size_bytes": 10, "executable_sha256": "2" * 64, "exit_code": 0,
                    "archive_path": asset["path"], "archive_size_bytes": asset["size_bytes"],
                    "archive_sha256": asset["sha256"], "stdout": "verified", "stderr": ""}
        with patch.object(finalize, "_verify_archive", side_effect=verify):
            return finalize.finalize_package(package, {asset_id: geometry}, browser, repo_root)

    def test_finalizes_only_after_bound_evidence_and_inventories_reports(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            repo_root = fixture[3]
            oracle = repo_root / ".local" / "oracle-reports" / "sample-oracle-r3.json"
            oracle.parent.mkdir(parents=True)
            oracle.write_text(json.dumps({"asset_id": "sample-1", "source_asset_path": "assets/source.parquet", "source_sha256": "1" * 64,
                "source_size_bytes": 9876, "pmtiles_sha256": digest(b"PMTiles archive fixture"),
                "pmtiles_size_bytes": len(b"PMTiles archive fixture"), "passed": True, "failures": []}))
            manifest = self.finalize(fixture)
            self.assertEqual(manifest["status"], "prepared")
            self.assertIn("reports/finalization/geometry/sample-1.json", manifest["files"])
            self.assertIn("reports/finalization/browser-validation.json", manifest["files"])
            self.assertIn("reports/finalization/pmtiles-verify/sample-1.json", manifest["files"])
            self.assertNotIn("reports/finalization/oracles/sample-oracle-r3.json", manifest["files"])
            actual = {path.relative_to(fixture[0]).as_posix() for path in fixture[0].rglob("*")
                      if path.is_file() and path.name != "manifest.json"}
            self.assertEqual(set(manifest["files"]), actual)
            readme = (fixture[0] / "README.md").read_text()
            self.assertIn("does not claim new GEE checks", readme)
            self.assertIn("geometry/sample-1.json", readme)
            self.assertIn("Attribution: Sample producer; CC BY 4.0", readme)
            self.assertIn("../../releases/r1/manifest.json", readme)
            with self.assertRaisesRegex(finalize.FinalizeError, "already prepared"):
                self.finalize(fixture)

    def test_rejects_tampered_archive_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            package = fixture[0]
            old_manifest = (package / "manifest.json").read_bytes()
            old_readme = (package / "README.md").read_bytes()
            (package / "assets" / "sample.pmtiles").write_bytes(b"altered")
            with self.assertRaisesRegex(finalize.FinalizeError, "hash/size mismatch"):
                self.finalize(fixture)
            self.assertEqual((package / "manifest.json").read_bytes(), old_manifest)
            self.assertEqual((package / "README.md").read_bytes(), old_readme)
            self.assertFalse((package / "reports" / "finalization").exists())

    def test_pmtiles_verify_failure_keeps_package_provisional(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            package = fixture[0]
            old_manifest = (package / "manifest.json").read_bytes()
            old_readme = (package / "README.md").read_bytes()
            with patch.object(finalize, "_verify_archive", side_effect=finalize.FinalizeError("pmtiles verify failed")):
                with self.assertRaisesRegex(finalize.FinalizeError, "pmtiles verify failed"):
                    finalize.finalize_package(package, {"sample-1": fixture[1]}, fixture[2], fixture[3])
            self.assertEqual((package / "manifest.json").read_bytes(), old_manifest)
            self.assertEqual((package / "README.md").read_bytes(), old_readme)
            self.assertFalse((package / "reports" / "finalization").exists())

    def test_pmtiles_verification_evidence_is_portable_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / "pmtiles"
            archive = root / "package" / "assets" / "sample.pmtiles"
            binary.write_bytes(b"pmtiles binary")
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"verified archive")
            asset = {"id": "sample-1", "path": "assets/sample.pmtiles",
                     "size_bytes": archive.stat().st_size, "sha256": digest(archive.read_bytes())}
            result = SimpleNamespace(returncode=0, stdout=f"verified {archive}\n", stderr=f"checked {archive}\n")
            with patch.object(finalize.shutil, "which", return_value=str(binary)), patch.object(
                finalize.subprocess, "run", return_value=result
            ) as run:
                evidence = finalize._verify_archive(asset, archive)
            self.assertEqual(run.call_args.args[0][1:], ["verify", str(archive)])
            self.assertEqual(evidence["command"], ["pmtiles", "verify", "assets/sample.pmtiles"])
            self.assertEqual(evidence["binary_label"], "pmtiles CLI")
            self.assertEqual(evidence["executable_sha256"], digest(binary.read_bytes()))
            self.assertEqual(evidence["archive_sha256"], asset["sha256"])
            self.assertNotIn(str(archive), json.dumps(evidence))

    def test_rejects_missing_layer_browser_case_and_failed_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            with self.assertRaisesRegex(finalize.FinalizeError, "cover every asset"):
                finalize.finalize_package(fixture[0], {}, fixture[2], fixture[3])
        for mutation, expected in [
            (lambda report: report["cases"].pop(), "missing sample-1/north_america"),
            (lambda report: report["cases"][0].update(status="failed"), "did not pass"),
            (lambda report: report["cases"][0].update(response_body_bytes=128 * 1024 * 1024 + 1), "transfer ceiling"),
            (lambda report: report["cases"][0].update(response_body_bytes=len(b"PMTiles archive fixture"), requests=[{
                "method": "GET", "status": 206, "completed": True,
                "range": f"bytes=0-{len(b'PMTiles archive fixture') - 1}",
                "content_range": f"bytes 0-{len(b'PMTiles archive fixture') - 1}/{len(b'PMTiles archive fixture')}",
                "content_length": len(b"PMTiles archive fixture"), "object_size_bytes": len(b"PMTiles archive fixture"), "cors": "*",
            }]), "whole object"),
            (lambda report: report["cases"][0].pop("all_attributes_note"), "all-source-attributes lookup"),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                browser = json.loads(fixture[2].read_text())
                mutation(browser)
                fixture[2].write_text(json.dumps(browser))
                with self.assertRaisesRegex(finalize.FinalizeError, expected):
                    self.finalize(fixture)
        for mutation, expected in [
            (lambda report: report.update(passed=False), "did not pass"),
            (lambda report: report.update(max_distance_m=31), "maximum distance is inconsistent"),
            (lambda report: report["sample_groups"].update({"global": [1]}), "sample count is incomplete"),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                geometry = json.loads(fixture[1].read_text())
                mutation(geometry)
                fixture[1].write_text(json.dumps(geometry))
                with self.assertRaisesRegex(finalize.FinalizeError, expected):
                    self.finalize(fixture)

    def test_rejects_mismatched_builder_report_and_classification(self):
        for mutate, expected in [
            (lambda report: report.update(pmtiles_sha256="0" * 64), "build report pmtiles_sha256 mismatch"),
            (lambda report: report.update(maxzoom_ids_attribute_checked=99), "ID accounting is incomplete"),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                package = fixture[0]
                build_path = package / "reports" / "sample-layer.build-report.json"
                build_report = json.loads(build_path.read_text())
                mutate(build_report)
                build_path.write_text(json.dumps(build_report))
                manifest = json.loads((package / "manifest.json").read_text())
                data = build_path.read_bytes()
                manifest["files"]["reports/sample-layer.build-report.json"] = {"size_bytes": len(data), "sha256": digest(data)}
                (package / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(finalize.FinalizeError, expected):
                    self.finalize(fixture)

    def test_hydrolakes_native_mvt_id_report_shape_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            package = fixture[0]
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            asset = manifest["assets"][0]
            asset.update({
                "id": "hydrolakes-1", "source_layer": "hydrolakes-polygons", "id_field": "Hylak_id",
                "source_rows": 1427688, "id_encoding": "mvt_feature_id",
                "attribute_fields": ["Lake_area", "Lake_name", "Country", "Continent",
                                     "_src_xmin", "_src_ymin", "_src_xmax", "_src_ymax"],
                "source_asset": {"path": "assets/hydrolakes-polygons.parquet", "size_bytes": 949598607,
                                 "sha256": "6f588d97c14651eb23bea2d74fdf2a85f218a00ff11519c81efa5512b916b7f8"},
            })
            manifest_path.write_text(json.dumps(manifest))
            build_path = package / "reports" / "sample-layer.build-report.json"
            build = json.loads(build_path.read_text())
            build.update({
                "source_path": "hydrolakes/releases/v1-local-r3/assets/hydrolakes-polygons.parquet",
                "source_sha256": asset["source_asset"]["sha256"], "source_rows": 1427688,
                "unique_source_ids": 1427688, "id_field": "Hylak_id", "id_encoding": "mvt_feature_id",
                "attribute_fields": asset["attribute_fields"], "layer": "hydrolakes-polygons",
                "maxzoom_ids_decoded": 1427688, "maxzoom_ids_accounted": 1427688,
                "maxzoom_ids_attribute_checked": 1427688, "maxzoom_missing_id_count": 0,
                "maxzoom_missing_ids_sha256": digest(b""), "maxzoom_missing_classification_counts": {},
            })
            build_path.write_text(json.dumps(build))
            self.refresh_files(package)
            manifest = json.loads(manifest_path.read_text())
            asset = manifest["assets"][0]
            build = json.loads(build_path.read_text())
            finalize._match_build_report(package, asset, build)
            geometry = json.loads(fixture[1].read_text())
            geometry.update({
                "asset_id": "hydrolakes-1", "source_asset_path": asset["source_asset"]["path"],
                "source_size_bytes": asset["source_asset"]["size_bytes"],
                "source_sha256": asset["source_asset"]["sha256"],
                "id_encoding": "mvt_feature_id", "source_rows_scanned": 1427688,
                "sample_rule": {**geometry["sample_rule"],
                                "selection": "lowest eligible IDs within each frozen geographic control after <=64 bbox tiles cap"},
            })
            finalize._validate_geometry_report(geometry, asset, build)
            geometry_path = fixture[1]
            geometry_path.write_text(json.dumps(geometry))
            browser_path = fixture[2]
            browser = json.loads(browser_path.read_text())
            for case in browser["cases"]:
                case["dataset_id"] = "hydrolakes"
                case["layer_id"] = "hydrolakes-1"
            browser_path.write_text(json.dumps(browser))
            manifest["dataset_id"] = "hydrolakes"
            manifest_path.write_text(json.dumps(manifest))
            old_report_path = package / "reports" / "sample-layer.build-report.json"
            new_report_path = package / "reports" / "hydrolakes-polygons.build-report.json"
            old_report_path.rename(new_report_path)
            self.refresh_files(package)
            finalized = self.finalize(fixture)
            self.assertEqual(finalized["status"], "prepared")

    def test_id_encoding_must_bind_report_and_attribute_fields(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            package = fixture[0]
            asset = json.loads((package / "manifest.json").read_text())["assets"][0]
            build = json.loads((package / "reports" / "sample-layer.build-report.json").read_text())
            asset["id_encoding"] = "unknown"
            with self.assertRaisesRegex(finalize.FinalizeError, "unsupported display asset id_encoding"):
                finalize._match_build_report(package, asset, build)
            asset["id_encoding"] = "mvt_feature_id"
            build["id_encoding"] = "mvt_feature_id"
            with self.assertRaisesRegex(finalize.FinalizeError, "conflicts with id_encoding"):
                finalize._match_build_report(package, asset, build)
            asset["id_encoding"] = "mvt_feature_id_and_property"
            build["id_encoding"] = "mvt_feature_id"
            with self.assertRaisesRegex(finalize.FinalizeError, "build report id_encoding mismatch"):
                finalize._match_build_report(package, asset, build)

    def test_accepts_only_fully_enumerated_classified_maxzoom_collapses(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            package = fixture[0]
            missing_data = b"100\n"
            classification_data = b'{"id":100,"cause":"quantization_collapse"}\n'
            (package / "sample.maxzoom-missing-ids.txt").write_bytes(missing_data)
            classification_path = package / "sample.maxzoom-missing-classification.jsonl"
            classification_path.write_bytes(classification_data)
            report_path = package / "reports" / "sample-layer.build-report.json"
            report = json.loads(report_path.read_text())
            report.update({"maxzoom_ids_decoded": 99, "maxzoom_ids_accounted": 99,
                           "maxzoom_ids_attribute_checked": 99, "maxzoom_missing_id_count": 1,
                           "maxzoom_missing_ids_sha256": digest(missing_data),
                           "maxzoom_missing_classification_counts": {"quantization_collapse": 1}})
            report_path.write_text(json.dumps(report))
            self.refresh_files(package)
            manifest = self.finalize(fixture)
            self.assertEqual(manifest["status"], "prepared")

        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            package = fixture[0]
            missing_data = b"100\n"
            (package / "sample.maxzoom-missing-ids.txt").write_bytes(missing_data)
            (package / "sample.maxzoom-missing-classification.jsonl").write_text('{"id":101,"cause":"quantization_collapse"}\n')
            report_path = package / "reports" / "sample-layer.build-report.json"
            report = json.loads(report_path.read_text())
            report.update({"maxzoom_ids_decoded": 99, "maxzoom_ids_accounted": 99,
                           "maxzoom_ids_attribute_checked": 99, "maxzoom_missing_id_count": 1,
                           "maxzoom_missing_ids_sha256": digest(missing_data),
                           "maxzoom_missing_classification_counts": {"quantization_collapse": 1}})
            report_path.write_text(json.dumps(report))
            self.refresh_files(package)
            with self.assertRaisesRegex(finalize.FinalizeError, "do not enumerate"):
                self.finalize(fixture)


if __name__ == "__main__":
    unittest.main()
