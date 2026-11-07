import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

FINALIZER_PATH = Path(__file__).resolve().parents[1] / "datasets/grwl-raw/finalize_display.py"
SPEC = importlib.util.spec_from_file_location("grwl_raw_finalize_display", FINALIZER_PATH)
finalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finalizer)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def tile_code(tile):
    return ((ord(tile[0]) - 65) * 26 + ord(tile[1]) - 65) * 100 + int(tile[2:])


def descriptor(path):
    return {"size_bytes": Path(path).stat().st_size, "sha256": sha(path)}


class FinalizeFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.tile = "AA00"
        self.fids = [(tile_code(self.tile) << 32) | row for row in (1, 2)]
        self.source = self.root / "source.parquet"
        pq.write_table(pa.table({"feature_id": self.fids, "source_row": [1, 2]}), self.source)
        self.pmtiles_bytes = b"synthetic-pmtiles-archive-fixture"

        self.manifest_path = self.root / "source-manifest.json"
        self.manifest = {
            "source_product": "GRWL_vector_V01.01", "rows": 2, "parts": 3,
            "parquet_sha256": sha(self.source), "archive": {
                "filename": "GRWL_vector_V01.01.zip", "size_bytes": 3_104_998_836,
                "provider_md5": "40171f15c0fccd470db32446dda0480e",
                "sha256": finalizer.EXPECTED_ARCHIVE_SHA256,
            },
            "tiles": [{"tile": self.tile, "records": 2, "parts": 3,
                       "source_sha256": {"shp": "1" * 64, "shx": "2" * 64,
                                         "dbf": "3" * 64, "prj": "4" * 64}}],
        }
        write_json(self.manifest_path, self.manifest)

        self.raw_validation = {
            "status": "passed", "error_count": 0, "errors": [],
            "manifest_sha256": sha(self.manifest_path), "parquet_sha256": sha(self.source),
            "source_archive_identity_checked": True, "source_member_sha256_checked": 4,
            "manifest_tile_count": 1,
            "source_archive": self.manifest["archive"],
            "progress": {"source_rows": 2, "parquet_rows": 2, "tiles_completed": [self.tile], "parts": 3},
            "sample_policy": {"kind": "global_controls", "first_records_per_tile": 8,
                              "longest_parts_per_tile": 8},
            "tiles": [{"tile": self.tile, "source_rows": 2, "matched_rows": 2, "parts": 3,
                       "source_sha256": self.manifest["tiles"][0]["source_sha256"],
                       "first_records": [{"source_tile": self.tile, "source_row": row, "feature_id": fid}
                                         for row, fid in enumerate(self.fids, 1)],
                       "longest_parts": [{"source_tile": self.tile, "source_row": 1, "feature_id": self.fids[0]}
                                         for _ in range(3)]}],
        }
        self.raw_validation_path = self.root / "raw-source-validation.json"
        write_json(self.raw_validation_path, self.raw_validation)
        self.fidelity_path = self.root / "source-fidelity.normalized.json"
        self.fidelity = {"status": "passed", "assets": [{"asset_id": "grwl-raw-observations",
            "sha256": sha(self.source), "size_bytes": self.source.stat().st_size}],
            "evidence": {"source_report": self.raw_validation,
                         "original_manifest_sha256": sha(self.manifest_path),
                         "source_validation_sha256": sha(self.raw_validation_path)}}
        write_json(self.fidelity_path, self.fidelity)

        self.analytic = self.root / "analytic-package"
        (self.analytic / "assets").mkdir(parents=True)
        (self.analytic / "evidence").mkdir()
        (self.analytic / "source").mkdir()
        (self.analytic / "licenses").mkdir()
        (self.analytic / "verification/workflow").mkdir(parents=True)
        (self.analytic / "assets/grwl-raw-observations.parquet").write_bytes(self.source.read_bytes())
        provenance_paths = {
            "source_attribution": "source/attribution.json",
            "source_license": "licenses/source-license.json",
            "data_license": "licenses/data-license.json",
            "source_fidelity_report": "evidence/source-fidelity.json",
            "clean_rebuild_report": "evidence/clean-rebuild.json",
        }
        for key, rel in provenance_paths.items():
            if key == "source_fidelity_report":
                content = self.fidelity
            elif key == "source_attribution":
                content = {"url": "https://zenodo.org/records/18624542", "title": "GRWL V01.01",
                           "attribution": "Allen and Pavelsky (2018)"}
            elif key == "source_license":
                content = {"identifier": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}
            elif key == "data_license":
                content = {"license": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}
            else:
                content = {"status": "fixture-evidence", "kind": key}
            write_json(self.analytic / rel, content)
        workflow_rel = "verification/workflow/build.py"
        (self.analytic / workflow_rel).write_text("# pinned fixture workflow\n")
        analytic_manifest = {"dataset_id": "grwl-raw", "release_id": "raw-v01.01-local-r1",
            "status": "local-candidate", "publicly_published": False,
            "assets": [{"asset_id": "grwl-raw-observations", "href": "assets/grwl-raw-observations.parquet",
                        "sha256": sha(self.source), "size_bytes": self.source.stat().st_size, "row_count": 2}],
            "workflow_files": {"datasets/grwl-raw/build_global.py": {"sha256": sha(self.analytic / workflow_rel),
                "bytes": (self.analytic / workflow_rel).stat().st_size, "package_path": workflow_rel}},
            **{key: {"path": rel, "sha256": sha(self.analytic / rel)} for key, rel in provenance_paths.items()}}
        write_json(self.analytic / "manifest.json", analytic_manifest)
        write_json(self.analytic / "evidence/package-binding.json", {
            "manifest_sha256": sha(self.analytic / "manifest.json"),
            "asset_sha256": {"grwl-raw-observations": sha(self.source)},
            "workflow_sha256": {"datasets/grwl-raw/build_global.py": sha(self.analytic / workflow_rel)},
            "source_attribution_sha256": sha(self.analytic / provenance_paths["source_attribution"]),
            "source_fidelity_report_sha256": sha(self.analytic / provenance_paths["source_fidelity_report"]),
            "clean_rebuild_report_sha256": sha(self.analytic / provenance_paths["clean_rebuild_report"])})
        write_json(self.analytic / "evidence/final-package-verification.json", {"status": "passed"})
        write_json(self.analytic / "package-receipt.json", {
            "status": "packaged_locally_not_published", "dataset_id": "grwl-raw",
            "release_id": "raw-v01.01-local-r1", "manifest_sha256": sha(self.analytic / "manifest.json"),
            "publicly_published": False, "registry_submitted": False,
            "package_binding_sha256": sha(self.analytic / "evidence/package-binding.json"),
            "final_verification_sha256": sha(self.analytic / "evidence/final-package-verification.json")})

        self.provisional = self.root / "provisional-display"
        (self.provisional / "assets").mkdir(parents=True)
        (self.provisional / "workflow").mkdir()
        (self.provisional / "styles").mkdir()
        (self.provisional / "reports").mkdir()
        (self.provisional / "assets/grwl-raw.pmtiles").write_bytes(self.pmtiles_bytes)
        write_json(self.provisional / "styles/width.json", {"version": 8,
            "sources": {"data": {"type": "vector", "url": "../assets/grwl-raw.pmtiles"}},
            "layers": [{"id": "raw-width", "type": "line", "source": "data",
                        "source-layer": "grwl_raw", "paint": {"line-width": ["get", "width_m"]}}]})
        write_json(self.provisional / "workflow/source-fidelity.json", self.raw_validation)
        workflow_sources = {
            "build_display.py.txt": finalizer.ROOT / "datasets/grwl-raw/build_display.py",
            "dateline-helper.py.txt": finalizer.ROOT / "datasets/grwl/build_display.py",
            "uv.lock": finalizer.ROOT / "scripts/display_tools/uv.lock",
            "display-policy.json": finalizer.ROOT / "research/grwl-raw-release-20261102/display-policy.json",
            "criteria.json": finalizer.ROOT / "research/grwl-raw-release-20261102/global-criteria.json",
            "tippecanoe.lock.json": finalizer.ROOT / "datasets/grwl/tippecanoe.lock.json",
        }
        for filename, source_path in workflow_sources.items():
            (self.provisional / "workflow" / filename).write_bytes(source_path.read_bytes())
        (self.provisional / "workflow/source-manifest.json").write_bytes(self.manifest_path.read_bytes())
        provenance = {
            "source": descriptor(self.source), "source_manifest": descriptor(self.manifest_path),
            "source_fidelity": descriptor(self.provisional / "workflow/source-fidelity.json"),
            "policy": descriptor(self.provisional / "workflow/display-policy.json"),
            "criteria": descriptor(self.provisional / "workflow/criteria.json"),
            "builder": descriptor(self.provisional / "workflow/build_display.py.txt"),
            "dateline_helper": descriptor(self.provisional / "workflow/dateline-helper.py.txt"),
            "environment_lock": descriptor(self.provisional / "workflow/uv.lock"),
            "tippecanoe": {"size_bytes": 12345,
                            "sha256": json.loads((self.provisional / "workflow/tippecanoe.lock.json").read_text())["binary_sha256"]},
            "tippecanoe_version": json.loads((self.provisional / "workflow/tippecanoe.lock.json").read_text())["version"],
        }
        write_json(self.provisional / "reports/input-provenance.json", provenance)
        self.display_manifest = {"schema_version": 1, "dataset_id": "grwl-raw", "status": "provisional",
            "display_release": "global-display-v1", "source_rows": 2, "source_tiles": 1,
            "assets": [{"id": "grwl-raw-display", "path": "assets/grwl-raw.pmtiles",
                "source_layer": "grwl_raw", "geometry_type": "line", "id_field": "feature_id",
                "id_encoding": "mvt_feature_id", "min_zoom": 8, "max_zoom": 12,
                "attribute_fields": ["width_m", "width_valid", "_src_xmin", "_src_ymin", "_src_xmax", "_src_ymax"],
                "sha256": sha(self.provisional / "assets/grwl-raw.pmtiles"),
                "size_bytes": len(self.pmtiles_bytes), "source_asset": {"sha256": sha(self.source),
                    "size_bytes": self.source.stat().st_size}, "style_path": "styles/width.json"}]}
        write_json(self.provisional / "manifest.json", self.display_manifest)

        self.oracle_path = self.root / "oracle.json"
        self.missing_path = self.root / "independent-missing-enumeration.jsonl"
        self.missing_path.write_text(json.dumps({"id": self.fids[1], "cause": "quantization_collapse",
            "source_tile": self.tile, "source_row": 2}) + "\n")
        self.oracle = {"schema_version": 1, "status": "passed", "errors": [], "errors_truncated": False,
            "source_sha256": sha(self.source), "source_manifest_sha256": sha(self.manifest_path),
            "source_fidelity_sha256": sha(self.raw_validation_path),
            "validator_sha256": sha(finalizer.ROOT / "datasets/grwl-raw/validate_display.py"),
            "wrap_validator_sha256": sha(finalizer.ROOT / "datasets/grwl/validate_display_wrap.py"),
            "environment_lock_sha256": sha(finalizer.ROOT / "scripts/display_tools/uv.lock"),
            "pmtiles_sha256": sha(self.provisional / "assets/grwl-raw.pmtiles"), "source_rows": 2, "maxzoom": 12,
            "maxzoom_feature_occurrences": 1, "maxzoom_unique_ids": 1, "maxzoom_missing_ids": 1,
            "maxzoom_attribute_occurrences_checked": 1, "maxzoom_missing_classification": {"quantization_collapse": 1},
            "maxzoom_tiles": 1, "frozen_sample_policy": {"kind": "global_controls",
                "first_records_per_tile": 8, "longest_parts_per_tile": 8},
            "frozen_sample_counts": [{"tile": self.tile, "expected_first_records": 2,
                "validated_first_records": 2, "expected_longest_parts": 3, "validated_longest_parts": 3}],
            "frozen_geometry_samples": [{"id": self.fids[0], "tiles": 1, "passed": True,
                "hausdorff_metres": 0.0, "missing_geometry_exception": None},
                {"id": self.fids[1], "tiles": 1, "passed": False,
                 "hausdorff_metres": None, "missing_geometry_exception": "quantization_collapse"}],
            "dateline_bbox_candidate_ids": 0, "dateline_bbox_candidate_feature_ids": [],
            "dateline_crossing_feature_ids": [], "dateline_seam_feature_ids": [],
            "dateline_control_policy": json.loads(finalizer.CONTROL_POLICY_PATH.read_text())["dateline_supplement"],
            "control_policy_sha256": sha(finalizer.CONTROL_POLICY_PATH),
            "native_quantizer_sha256": sha(finalizer.ROOT / "datasets/grwl-raw/native_quantization.py"),
            "geometry_samples_passed": 1,
            "geometry_samples_missing_exceptions": 1, "maxzoom_missing_path": self.missing_path.name,
            "maxzoom_missing_sha256": sha(self.missing_path)}
        write_json(self.oracle_path, self.oracle)

        self.policy_path = finalizer.ROOT / "research/grwl-raw-release-20261102/global-browser-policy.json"
        self.controls_path = self.root / "browser-controls.json"
        self.controls_pin_path = self.root / "canonical-browser-controls.json"
        self.browser_path = self.root / "browser-report.json"
        self.policy_sha = sha(self.policy_path)
        fields = {"utm_east": "100", "utm_north": "200", "width_m": "1", "nchannels": "2",
                  "segmentID": "3", "segmentInd": "4", "lakeFlag": "0", "lon": "-100",
                  "lat": "40", "elev_m": "10", "source_tile": self.tile, "source_row": "1",
                  "feature_id": str(self.fids[0]), "width_valid": "false"}
        ids = sorted(finalizer.KNOWN_CASE_IDS | finalizer.GLOBAL_CASE_IDS)
        controls_cases, report_cases = [], []
        source_obj, pmtiles_obj = "local/source.parquet", "local/display.pmtiles"
        requests = []
        for path, data in ((source_obj, self.source.read_bytes()),
                           (pmtiles_obj, self.pmtiles_bytes)):
            size = len(data)
            end = min(3, size - 2)
            requests.append({"object_path": path, "object_size_bytes": size, "method": "GET", "range": f"bytes=1-{end}",
                "status": 206, "content_range": f"bytes 1-{end}/{size}", "content_length": end,
                "body_bytes": end, "cors": "*", "completed": True})
        each_requested = sum(req["content_length"] for req in requests)
        each_body = sum(req["body_bytes"] for req in requests)
        for index, case_id in enumerate(ids):
            control = {"case_id": case_id, "kind": "known" if case_id in finalizer.KNOWN_CASE_IDS else "global",
                "context_region": finalizer.KNOWN_CONTEXTS.get(case_id, "grwl_15450"), "source_tile": self.tile,
                "source_row": 1, "feature_id": self.fids[0], "detail_bbox": [0, 0, 1, 1],
                "expected_analytic_attributes": fields,
                "expected_width": {"width_m": 1, "width_valid": False,
                                   "label": "Observation width · Unknown (source sentinel 1)"}}
            if case_id in finalizer.KNOWN_CASE_IDS:
                control["summary_reference_id"] = int(case_id.removeprefix("known-summary-"))
            else:
                control.update({"window_id": case_id.removeprefix("global-"), "context_bbox": [0, 0, 1, 1],
                                "longest_part_m": 1.0, "source_part_bbox": [0, 0, 1, 1]})
            controls_cases.append(control)
            result = {**{key: value for key, value in control.items() if key != "expected_analytic_attributes"},
                "status": "passed", "detail_feature_inspected": True, "detail_rendered_features": 1,
                "raw_rendered_features": 1, "analytic_attributes_checked": 14,
                "analytic_attribute_field_count": 14, "attribute_mismatches": [],
                "analytic_attributes": fields, "width_checked": True,
                "tile_width": {"width_m": "1", "width_valid": False,
                               "label": control["expected_width"]["label"]},
                "requests": requests, "requested_range_bytes": each_requested,
                "response_body_bytes": each_body, "transfer_ceiling_bytes": finalizer.MAX_CASE_BYTES}
            report_cases.append(result)
        self.controls = {"schema_version": 1, "status": "frozen_controls", "source_rows": 2,
            "case_count": 11, "source_sha256": sha(self.source),
            "source_manifest_sha256": sha(self.manifest_path),
            "source_validation_sha256": sha(self.raw_validation_path),
            "browser_policy_sha256": self.policy_sha,
            "browser_limits": json.loads(self.policy_path.read_text())["browser_limits"],
            "cases": controls_cases}
        write_json(self.controls_path, self.controls)
        self.controls_pin_path.write_bytes(self.controls_path.read_bytes())
        self.browser = {"schema_version": 2, "status": "passed",
            "scope": "Local Chrome source lookup, rendering and bounded HTTP range/CORS checks; no remote publication or GEE claim",
            "errors": [],
            "inputs": {"controls": {"path": str(self.controls_path), "sha256": sha(self.controls_path)},
                "source_manifest_sha256": sha(self.manifest_path),
                "source_validation_sha256": sha(self.raw_validation_path), "browser_policy_sha256": self.policy_sha,
                "source": {"object_path": source_obj, "sha256": sha(self.source), "size_bytes": self.source.stat().st_size},
                "pmtiles": {"object_path": pmtiles_obj, "sha256": sha(self.provisional / "assets/grwl-raw.pmtiles"),
                            "size_bytes": len(self.pmtiles_bytes)}},
            "transfer_policy": {"bytes_per_case": finalizer.MAX_CASE_BYTES, "enforced": True,
                "aggregate_requested_range_bytes": True, "aggregate_response_body_bytes": True},
            "cases": report_cases}
        write_json(self.browser_path, self.browser)

    def run(self, output=None):
        output = output or self.root / "final-display"
        def verifier(asset, path):
            return {"status": "passed", "archive_sha256": sha(path), "archive_size_bytes": path.stat().st_size,
                    "binary_sha256": "c" * 64}
        return finalizer.finalize_display(self.manifest_path, self.fidelity_path, self.source,
            self.provisional, self.oracle_path, self.missing_path, self.controls_path, self.browser_path,
            self.analytic, output, expected_tiles=1, expected_rows=2, controls_pin_path=self.controls_pin_path,
            pmtiles_verifier=verifier)


class RawDisplayFinalizationTests(unittest.TestCase):
    def test_finalizes_new_package_and_keeps_provisional_input_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            manifest_before = (fixture.provisional / "manifest.json").read_bytes()
            archive_before = (fixture.provisional / "assets/grwl-raw.pmtiles").read_bytes()
            result = fixture.run()
            output = Path(result["output_dir"])
            packaged = json.loads((output / "manifest.json").read_text())
            final_report = json.loads((output / "reports/finalization/report.json").read_text())
            self.assertEqual("prepared", result["status"])
            self.assertEqual("raw-v01.01-local-r1", packaged["analytic_release"])
            self.assertEqual("raw-v01.01-display-r1", packaged["display_release"])
            self.assertEqual("global-display-v1", final_report["provisional_display_run_id"])
            self.assertEqual(sha(fixture.provisional / "manifest.json"),
                             final_report["provisional_display_manifest_sha256"])
            self.assertEqual("assets/grwl-raw-observations.parquet", packaged["assets"][0]["source_asset"]["path"])
            self.assertIn("reports/finalization/report.json", packaged["files"])
            workflow = packaged["files"]
            self.assertIn("reports/finalization/verification-workflow/datasets/grwl-raw/validate_display.py", workflow)
            self.assertIn("reports/finalization/verification-workflow/scripts/cloud_viewer/package-lock.json", workflow)
            self.assertIn("reports/finalization/verification-workflow/scripts/cloud_viewer/src/app.js", workflow)
            self.assertIn("reports/finalization/verification-workflow/scripts/cloud_viewer/src/parquet.worker.js", workflow)
            self.assertEqual(sha(FINALIZER_PATH), final_report["verification_workflow"]["files"][
                "datasets/grwl-raw/finalize_display.py"]["sha256"])
            self.assertEqual(fixture.missing_path.read_bytes(),
                (output / "reports/finalization/raw-display-missing-ids.jsonl").read_bytes())
            self.assertEqual(manifest_before, (fixture.provisional / "manifest.json").read_bytes())
            self.assertEqual(archive_before, (fixture.provisional / "assets/grwl-raw.pmtiles").read_bytes())
            self.assertFalse((output / "partial.json").exists())

    def test_wrong_oracle_source_hash_retains_explicit_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.oracle["source_sha256"] = "0" * 64
            write_json(fixture.oracle_path, fixture.oracle)
            output = Path(temp) / "failed-output"
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run(output)
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual("failed_partial", failure["status"])
            self.assertFalse(failure["usable_release"])
            self.assertTrue((output / "partial.json").exists())

    def test_wrong_oracle_validator_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.oracle["validator_sha256"] = "0" * 64
            write_json(fixture.oracle_path, fixture.oracle)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run()

    def test_unsafe_provisional_run_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.display_manifest["display_release"] = "../mutable"
            write_json(fixture.provisional / "manifest.json", fixture.display_manifest)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run()

    def test_missing_browser_case_and_attribute_mismatch_are_rejected(self):
        for mutation in ("remove_case", "change_attribute"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                fixture = FinalizeFixture(temp)
                if mutation == "remove_case":
                    fixture.browser["cases"].pop()
                else:
                    fixture.browser["cases"][0]["analytic_attributes"]["field_0"] = "wrong"
                write_json(fixture.browser_path, fixture.browser)
                with self.assertRaises(finalizer.FinalizeError):
                    fixture.run()

    def test_browser_report_hash_binding_and_detail_inspection_are_required(self):
        for mutation in ("report_pin", "inspection"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                fixture = FinalizeFixture(temp)
                if mutation == "report_pin":
                    fixture.browser["inputs"]["source_validation_sha256"] = "0" * 64
                else:
                    fixture.browser["cases"][0]["detail_feature_inspected"] = False
                write_json(fixture.browser_path, fixture.browser)
                with self.assertRaises(finalizer.FinalizeError):
                    fixture.run()

    def test_browser_metadata_head_probes_are_accepted_but_not_counted_as_transfer(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            source_obj = fixture.browser["inputs"]["source"]["object_path"]
            size = fixture.browser["inputs"]["source"]["size_bytes"]
            head_requests = [
                {"object_path": source_obj, "object_size_bytes": size, "method": "HEAD", "range": None,
                 "status": 200, "content_range": None, "content_length": size, "body_bytes": size,
                 "cors": "*", "completed": True},
                {"object_path": source_obj, "object_size_bytes": size, "method": "HEAD",
                 "range": "bytes=0-", "status": 206,
                 "content_range": f"bytes 0-{size - 1}/{size}", "content_length": size,
                 "body_bytes": size, "cors": "*", "completed": True},
            ]
            fixture.browser["cases"][0]["requests"].extend(head_requests)
            write_json(fixture.browser_path, fixture.browser)
            fixture.run()

    def test_malformed_browser_head_probe_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            source_obj = fixture.browser["inputs"]["source"]["object_path"]
            size = fixture.browser["inputs"]["source"]["size_bytes"]
            fixture.browser["cases"][0]["requests"].append({
                "object_path": source_obj, "object_size_bytes": size, "method": "HEAD", "range": None,
                "status": 500, "content_range": None, "content_length": size, "body_bytes": size,
                "cors": "*", "completed": True})
            write_json(fixture.browser_path, fixture.browser)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run()

    def test_browser_controls_must_match_frozen_case_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.controls["cases"][0]["detail_bbox"] = [1, 1, 2, 2]
            write_json(fixture.controls_path, fixture.controls)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run()

    def test_empty_geometry_pass_and_missing_accounting_are_rejected(self):
        for mutation in ("empty", "accounting"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                fixture = FinalizeFixture(temp)
                if mutation == "empty":
                    fixture.oracle["frozen_geometry_samples"][0]["tiles"] = 0
                else:
                    fixture.oracle["maxzoom_unique_ids"] = 2
                write_json(fixture.oracle_path, fixture.oracle)
                with self.assertRaises(finalizer.FinalizeError):
                    fixture.run()

    def test_visible_ids_cannot_exceed_tile_occurrences(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.oracle["maxzoom_feature_occurrences"] = 0
            fixture.oracle["maxzoom_attribute_occurrences_checked"] = 0
            write_json(fixture.oracle_path, fixture.oracle)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run()

    def test_existing_output_is_never_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            output = Path(temp) / "exists"
            output.mkdir()
            marker = output / "keep"
            marker.write_text("untouched")
            with self.assertRaises(FileExistsError):
                fixture.run(output)
            self.assertEqual("untouched", marker.read_text())

    def test_symlinked_output_parent_cannot_alias_an_input_package(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            alias = Path(temp) / "display-alias"
            alias.symlink_to(fixture.provisional, target_is_directory=True)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run(alias / "nested-output")
            self.assertFalse((fixture.provisional / "nested-output").exists())

    def test_zero_missing_ids_still_requires_and_binds_empty_enumeration(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.missing_path.write_bytes(b"")
            fixture.oracle.update({"maxzoom_feature_occurrences": 2, "maxzoom_unique_ids": 2,
                "maxzoom_missing_ids": 0, "maxzoom_attribute_occurrences_checked": 2,
                "maxzoom_missing_classification": {}, "maxzoom_missing_path": fixture.missing_path.name,
                "maxzoom_missing_sha256": sha(fixture.missing_path)})
            fixture.oracle["frozen_geometry_samples"][1].update({"passed": True,
                "hausdorff_metres": 0.0, "missing_geometry_exception": None})
            fixture.oracle["geometry_samples_passed"] = 2
            fixture.oracle["geometry_samples_missing_exceptions"] = 0
            write_json(fixture.oracle_path, fixture.oracle)
            result = fixture.run()
            copied = Path(result["output_dir"]) / "reports/finalization/raw-display-missing-ids.jsonl"
            self.assertEqual(b"", copied.read_bytes())

    def test_seam_supplement_overlap_with_frozen_samples_is_valid_but_inventory_is_bound(self):
        for corrupted in (False, True):
            with self.subTest(corrupted=corrupted), tempfile.TemporaryDirectory() as temp:
                fixture = FinalizeFixture(temp)
                fid = fixture.fids[0]
                fixture.oracle.update({"dateline_bbox_candidate_ids": 1,
                    "dateline_bbox_candidate_feature_ids": [fid], "dateline_seam_feature_ids": [fid]})
                if corrupted:
                    fixture.oracle["dateline_seam_feature_ids"] = []
                write_json(fixture.oracle_path, fixture.oracle)
                if corrupted:
                    with self.assertRaisesRegex(finalizer.FinalizeError, "supplemental seam ID union"):
                        fixture.run()
                else:
                    self.assertEqual(fixture.run()["status"], "prepared")

    def test_native_evidence_and_fixture_bytes_are_checked(self):
        policy = json.loads(finalizer.CONTROL_POLICY_PATH.read_text())
        evidence_rel = policy["native_collapse_classifier"]["evidence_path"]
        evidence = json.loads((finalizer.ROOT / evidence_rel).read_text())
        paths = [evidence_rel, "datasets/grwl/tippecanoe.lock.json"]
        paths.extend(item["path"] for item in evidence["diagnostic_files"].values())
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp)
            for relative in paths:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((finalizer.ROOT / relative).read_bytes())
            with mock.patch.object(finalizer, "ROOT", destination):
                finalizer._validate_native_evidence(policy)
                relative = evidence["diagnostic_files"]["native-threshold-controls.pmtiles"]["path"]
                target = destination / relative
                original = target.read_bytes()
                target.write_bytes(original + b"changed")
                with self.assertRaisesRegex(finalizer.FinalizeError, "fixture checksum/size"):
                    finalizer._validate_native_evidence(policy)
                target.write_bytes(original)
                broken = json.loads(json.dumps(policy))
                broken["native_collapse_classifier"]["evidence_sha256"] = "0" * 64
                with self.assertRaisesRegex(finalizer.FinalizeError, "policy checksum"):
                    finalizer._validate_native_evidence(broken)

    def test_changed_native_quantizer_or_seam_policy_pin_is_rejected(self):
        for field in ("native_quantizer_sha256", "control_policy_sha256"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                fixture = FinalizeFixture(temp)
                fixture.oracle[field] = "0" * 64
                write_json(fixture.oracle_path, fixture.oracle)
                with self.assertRaises(finalizer.FinalizeError):
                    fixture.run()

    def test_missing_id_source_row_disagreement_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = FinalizeFixture(temp)
            fixture.missing_path.write_text(json.dumps({"id": fixture.fids[1],
                "cause": "quantization_collapse", "source_tile": fixture.tile, "source_row": 1}) + "\n")
            fixture.oracle["maxzoom_missing_sha256"] = sha(fixture.missing_path)
            write_json(fixture.oracle_path, fixture.oracle)
            with self.assertRaises(finalizer.FinalizeError):
                fixture.run()


if __name__ == "__main__":
    unittest.main()
