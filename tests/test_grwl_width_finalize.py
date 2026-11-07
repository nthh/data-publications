"""R3 finalizer gates reject unbound width, camera, replay, and archive evidence."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grwl_width_finalize", ROOT / "datasets/grwl-raw/finalize_width_display.py")
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


def criteria():
    return json.loads(finalizer.CRITERIA.read_text())


def browser_fixture():
    result = {"schema_version": 1, "status": "passed", "viewer_build_sha256": "viewer",
              "app_js_sha256": "app", "archive_sha256": "archive",
              "source_sha256": finalizer.SOURCE_SHA,
              "transfer_ceiling_bytes": 32 * 1024 * 1024, "cases": []}
    for view in criteria()["gates"]["browser_fixed_views"]:
        for zoom in view["zooms"]:
            detail = zoom >= 8
            case = {"status": "passed", "view": view["name"], "requested_zoom": zoom,
                    "requested_center": view["center"], "actual_zoom": zoom,
                    "actual_center": view["center"], "archive_sha256": "archive",
                    "legend_visible": True, "source_layer": "grwl_width_overview",
                    "style_layers": ["release-lines" if detail else "release-width-samples"],
                    "expected_layer": "release-lines" if detail else "release-width-samples",
                    "rendered_source_layers": ["grwl_raw" if detail else "grwl_width_overview"],
                    "transferred_bytes": 128, "page_errors": [], "external_requests": [],
                    "requests": [{"method": "GET", "status": 206, "cors": "*", "completed": True,
                                  "range": "bytes=0-127", "content_range": "bytes 0-127/1000",
                                  "body_bytes": 128, "content_length": 128, "object_size_bytes": 1000}]}
            if not detail:
                case["sample"] = {"featureID": 123, "sourceLayer": "grwl_width_overview",
                                  "properties": {"width_m": 200, "width_valid": True},
                                  "diameter_px": 4.2, "expected_diameter_px": 4.2}
            if view["name"] == "mississippi" and zoom == 7:
                case["exact_id_lookup"] = {"featureID": 123, "attribute_count": 14,
                                           "note": "All source attributes for this ID.",
                                           "displayed_width": "200", "overview_width": 200,
                                           "source_feature_id": 123,
                                           "source_width_valid": True,
                                           "overview_width_valid": True}
                case["click_zoom"] = 7
            result["cases"].append(case)
    return result


def replay_fixture(log_dir):
    stages = []
    for name in ("width-overview", "combine", "viewer"):
        path = log_dir / f"{name}.log"
        path.write_text("passed\n")
        stages.append({"name": name, "exit_code": 0,
                       "log": {"path": str(path), **finalizer.identity(path)}})
    return {"schema_version": 1, "status": "passed", "source_sha256": finalizer.PILOT_SHA,
            "source_rows": finalizer.PILOT_ROWS,
            "clean_checkout": {"commit": "a" * 40, "before": "", "after": "", "after_commit": "a" * 40},
            "byte_equal": {"samples": True, "overview_archive": True,
                           "combined_archive": True, "viewer_build": True, "viewer_files": True},
            "reference_viewer_build_sha256": "viewer",
            "code_pins": {relative: finalizer.identity(ROOT / relative) for relative in finalizer.WORKFLOW},
            "stages": stages}


class WidthFinalizerTests(unittest.TestCase):
    def test_browser_accepts_all_fixed_cases_then_rejects_camera_and_width_evidence(self):
        original = browser_fixture()
        finalizer.validate_browser(original, {"sha256": "viewer"},
                                   {"files": {"app.js": {"sha256": "app"}}},
                                   {"sha256": "archive"}, criteria())
        for name, edit in [
            ("camera", lambda b: b["cases"][7].update(actual_zoom=7.01)),
            ("center", lambda b: b["cases"][0].update(actual_center=[0, 0])),
            ("legend", lambda b: b["cases"][1].update(legend_visible=False)),
            ("width", lambda b: b["cases"][0]["sample"].update(diameter_px=10)),
            ("lookup", lambda b: b["cases"][7]["exact_id_lookup"].update(attribute_count=13)),
            ("lookup-source-id", lambda b: b["cases"][7]["exact_id_lookup"].update(source_feature_id=124)),
            ("lookup-source-validity", lambda b: b["cases"][7]["exact_id_lookup"].update(source_width_valid=False)),
            ("bytes", lambda b: b["cases"][0]["requests"][0].update(body_bytes=127)),
            ("archive", lambda b: b.update(archive_sha256="wrong")),
            ("missing", lambda b: b["cases"].pop()),
            ("failed", lambda b: b.update(status="failed")),
        ]:
            with self.subTest(name=name):
                bad = copy.deepcopy(original)
                edit(bad)
                with self.assertRaises(finalizer.FinalizeError):
                    finalizer.validate_browser(bad, {"sha256": "viewer"},
                                               {"files": {"app.js": {"sha256": "app"}}},
                                               {"sha256": "archive"}, criteria())

    def test_clean_replay_requires_clean_checkout_exact_bytes_and_all_code_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            original = replay_fixture(Path(directory))
            finalizer.validate_replay(original, {"sha256": "viewer"})
            for name, edit in [
            ("dirty", lambda r: r["clean_checkout"].update(before=" M app.js")),
            ("after-commit", lambda r: r["clean_checkout"].update(after_commit="b" * 40)),
            ("source", lambda r: r.update(source_sha256="other")),
            ("byte-equality", lambda r: r["byte_equal"].update(samples=False)),
            ("viewer", lambda r: r.update(reference_viewer_build_sha256="other")),
            ("code", lambda r: r["code_pins"].pop(finalizer.WORKFLOW[0])),
            ("failed", lambda r: r.update(status="failed")),
            ]:
                with self.subTest(name=name):
                    bad = copy.deepcopy(original)
                    edit(bad)
                    with self.assertRaises(finalizer.FinalizeError):
                        finalizer.validate_replay(bad, {"sha256": "viewer"})

    def test_combine_requires_exact_payloads_and_current_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "oracle.json"
            report_path.write_text("{}\n")
            archive = {"sha256": "new", "size_bytes": 3_000_000_000}
            overview = {"overview_archive": {"sha256": "overview", "size_bytes": 1234},
                        "source_manifest_sha256": "manifest"}
            base = {"status": "built_unvalidated", "combine_status": "passed", "scope": "global",
                    "baseline": {"sha256": finalizer.BASELINE_ARCHIVE_SHA,
                                 "sha256_pin": finalizer.BASELINE_ARCHIVE_SHA,
                                 "size_bytes": finalizer.BASELINE_ARCHIVE_SIZE,
                                 "detail_tiles": finalizer.DETAIL_TILES,
                                 "archive_tiles": 592774, "discarded_old_overview_tiles": 4419},
                    "overview": {"sha256": "overview", "size_bytes": 1234,
                                 "receipt_sha256": finalizer.digest(report_path),
                                 "receipt_status": "passed", "scope": "global",
                                 "verifier_sha256": finalizer.digest(ROOT / "datasets/grwl-raw/validate_width_overview.py"),
                                 "source_sha256": finalizer.SOURCE_SHA,
                                 "source_manifest_sha256": "manifest",
                                 "tile_counts_by_zoom": {str(z): 1 for z in range(8)}},
                    "combined": {**archive, "tiles": finalizer.DETAIL_TILES + 8},
                    "verification": {"status": "passed", "detail": finalizer.DETAIL_TILES,
                                     "overview": 8, "detail_raw_payloads_byte_identical": True,
                                     "overview_raw_payloads_byte_identical": True,
                                     "no_extra_or_overlapping_coordinates": True},
                    "criteria": {"sha256": finalizer.digest(finalizer.CRITERIA)},
                    "code": {"sha256": finalizer.digest(ROOT / "datasets/grwl-raw/combine_width_display.py")}}
            finalizer.validate_combine(base, report_path, report_path, overview, archive, criteria())
            for name, edit in [
                ("detail", lambda r: r["verification"].update(detail_raw_payloads_byte_identical=False)),
                ("overview", lambda r: r["verification"].update(overview_raw_payloads_byte_identical=False)),
                ("archive", lambda r: r["combined"].update(sha256="wrong")),
                ("receipt", lambda r: r["overview"].update(receipt_sha256="wrong")),
                ("failed", lambda r: r.update(combine_status="failed")),
            ]:
                with self.subTest(name=name):
                    bad = copy.deepcopy(base)
                    edit(bad)
                    with self.assertRaises(finalizer.FinalizeError):
                        finalizer.validate_combine(bad, report_path, report_path, overview, archive, criteria())

    def test_style_is_exported_from_shared_viewer_width_factory(self):
        style = json.loads(finalizer.export_style())
        self.assertEqual(style["layers"][0]["source-layer"], "grwl_width_overview")
        self.assertEqual(style["layers"][1]["source-layer"], "grwl_raw")
        self.assertEqual(style["layers"][0]["type"], "circle")
        self.assertNotIn("circle-stroke-width", style["layers"][0]["paint"])


if __name__ == "__main__":
    unittest.main()
