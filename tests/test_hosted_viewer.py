"""Offline checks for the exact-plan hosted viewer handoff."""

from __future__ import annotations

import copy
import importlib.util
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "prepare_hosted_viewer", ROOT / "scripts/source_publish/prepare_hosted_viewer.py"
)
assert spec and spec.loader
hosted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)


def fixture():
    product_ids = hosted.DATASET_IDS
    layers_by_id = {name: [name + "-display"] for name in product_ids}
    layers_by_id["lakeatlas"] = ["lakeatlas-polygons", "lakeatlas-points"]
    objects, files, datasets, products, records = {}, [], [], [], {}
    for dataset_id in product_ids:
        release = "release-r1"
        display_release = "display-r1"
        records[dataset_id] = {"publication": {"source_coop": {
            "product_id": dataset_id, "title": dataset_id + " title", "attribution": dataset_id + " attribution",
            "limitations": ["Live GEE sampled strict parity fails."]},
            "display": {"release": display_release}}}
        products.append({"dataset_id": dataset_id, "owner": "nthh", "product_id": dataset_id, "release": release})
        layers = []
        for layer_id in layers_by_id[dataset_id]:
            display_route = f"{dataset_id}/display/{display_release}/assets/{layer_id}.pmtiles"
            analytic_route = f"{dataset_id}/releases/{release}/assets/{layer_id}.parquet"
            display_path = "/nthh/" + display_route
            analytic_path = "/nthh/" + analytic_route
            display_hash, analytic_hash = "a" * 64, "b" * 64
            for route, digest, size, kind in (
                (display_route, display_hash, 100, "application/vnd.pmtiles"),
                (analytic_route, analytic_hash, 200, "application/vnd.apache.parquet"),
            ):
                path = "/nthh/" + route
                objects[path] = {"path": "/private/staged/" + route, "sha256": digest,
                                 "size_bytes": size, "content_type": kind}
                files.append({"object_key": route, "endpoint": hosted.ORIGIN,
                              "raw_url_proposed": hosted.ORIGIN + path,
                              "bucket": "nthh", "sha256": digest, "size_bytes": size,
                              "content_type": kind})
            analytic = {"object_path": analytic_path, "sha256": analytic_hash, "size_bytes": 200,
                        "id_field": "feature_id", "fields": ["feature_id", "width_m", "width_valid"],
                        "geometry_column": "geometry"}
            layers.append({"id": layer_id, "object_path": display_path, "sha256": display_hash,
                           "size_bytes": 100, "source_layer": "grwl_raw" if dataset_id == "grwl-raw" else layer_id,
                           "id_field": "feature_id", "analytic": analytic})
        datasets.append({"id": dataset_id, "state": "prepared", "title": dataset_id,
                         "summary": "stale local-only description", "attribution": None,
                         "layers": layers, "gee": {"status": "not_audited"}})
    manifest = {"dataset_id": "grwl-raw", "assets": [{"sha256": "a" * 64, "size_bytes": 100,
        "source_layer": "grwl_raw", "overview": {"mode": "width_samples", "source_layer": "grwl_width_overview",
                                            "attribute_fields": ["width_m", "width_valid"]},
        "detail_min_zoom": 8, "attribute_fields": ["width_m", "width_valid"],
        "id_encoding": "mvt_feature_id"}]}
    base = {"objects": objects, "viewer": {"object_origin": None, "title": "local viewer",
        "regions": [{"id": name} for name in ("global", "north_america", "atlantic_coast")],
        "datasets": datasets}}
    return base, {"products": products, "files": files}, records, manifest


class HostedViewerTest(unittest.TestCase):
    def test_planned_head_response_faults(self):
        if shutil.which("node") is None:
            self.skipTest("Node is unavailable")
        result = subprocess.run(
            ["node", str(ROOT / "scripts/cloud_viewer/hosted-browser-check.mjs"), "--self-test-head"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_plan_and_frozen_case_coverage(self):
        config, cases = hosted.adapt_config(*fixture())
        self.assertEqual(config["object_origin"], "https://data.source.coop")
        self.assertEqual(len(cases["cases"]), 30)
        self.assertEqual(len(cases["objects"]), 12)
        self.assertEqual(sum(len(row["layers"]) for row in config["datasets"]), 6)
        raw = next(row for row in config["datasets"] if row["id"] == "grwl-raw")
        layer = raw["layers"][0]
        self.assertEqual(layer["overview"]["source_layer"], "grwl_width_overview")
        self.assertEqual(layer["detail_min_zoom"], 8)
        self.assertEqual(layer["analytic"]["lookup_mode"], "exact_id")
        self.assertEqual(raw["gee"]["status"], "sampled_fail")
        self.assertEqual([case["view"]["zoom"] for case in cases["cases"]
                          if case.get("view", {}).get("name") == "mississippi"], list(range(13)))
        self.assertNotIn("/private/staged", hosted.canonical_json(config).decode())

    def test_off_plan_destination_is_refused(self):
        base, plan, records, manifest = fixture()
        plan["files"][0]["raw_url_proposed"] = "https://elsewhere.example/nthh/file"
        with self.assertRaisesRegex(hosted.HostedError, "hosted URL differs"):
            hosted.adapt_config(base, plan, records, manifest)

    def test_staged_hash_difference_is_refused(self):
        base, plan, records, manifest = fixture()
        path = "/nthh/" + plan["files"][0]["object_key"]
        base["objects"][path]["sha256"] = "c" * 64
        with self.assertRaisesRegex(hosted.HostedError, "identity differs"):
            hosted.adapt_config(base, plan, records, manifest)

    def test_raw_overview_and_exact_id_are_required(self):
        base, plan, records, manifest = fixture()
        broken = copy.deepcopy(manifest)
        broken["assets"][0]["overview"] = {"mode": "coverage"}
        with self.assertRaisesRegex(hosted.HostedError, "width overview"):
            hosted.adapt_config(base, plan, records, broken)
        base["viewer"]["datasets"][-1]["layers"][0]["analytic"]["fields"].remove("feature_id")
        with self.assertRaisesRegex(hosted.HostedError, "lacks feature_id"):
            hosted.adapt_config(base, plan, records, manifest)

    def test_product_scope_is_exact(self):
        base, plan, records, manifest = fixture()
        plan["products"][0]["owner"] = "other"
        with self.assertRaisesRegex(hosted.HostedError, "product identity differs"):
            hosted.adapt_config(base, plan, records, manifest)
        base, plan, records, manifest = fixture()
        plan["files"].append(dict(plan["files"][0], object_key="unexpected/extra.txt"))
        with self.assertRaisesRegex(hosted.HostedError, "exact immutable upload plan"):
            hosted.adapt_config(base, plan, records, manifest)


if __name__ == "__main__":
    unittest.main()
