from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).with_name("bind_fidelity.py")
spec = importlib.util.spec_from_file_location("bind_fidelity", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class BindFidelityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bind-fidelity-fixture-")
        self.root = Path(self.temp.name)
        self.spec_path = self.root / "input.json"
        self.output = self.root / "normalized"

    def tearDown(self):
        self.temp.cleanup()

    def fp(self, path: Path):
        return {"sha256": mod.sha256(path), "size_bytes": path.stat().st_size}

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def prepare(self, dataset_id: str, *, mutate: str | None = None):
        record = yaml.safe_load((mod.ROOT / "datasets" / dataset_id / "dataset.yaml").read_text())
        pinned = record["source"]["sha256" if dataset_id == "lakeatlas" else "source_sha256"]
        source_report = {"status": "passed_source_fidelity" if dataset_id == "lakeatlas" else "passed"}
        assets = []
        if dataset_id == "hydrolakes":
            entries = [("hydrolakes-polygons", b"hydro raw", b"hydro with bbox")]
            source_report.update(source_sha256=pinned, source_bytes=record["source"]["source_size"],
                rows=record["source"]["expected_rows"], wkb="all original decoded bytes bound")
        elif dataset_id == "free-flowing-rivers":
            entries = [("ffr-rivers", b"ffr raw", b"ffr with bbox")]
            expected = record["source"]["source_record_count"]
            source_report.update(source_sha256=pinned, records=expected,
                source_fid_records_compared=expected, geometry_wkb_records_compared=expected)
        else:
            entries = [("lakeatlas-polygons", b"lake polygon raw", None),
                       ("lakeatlas-pour-points", b"lake points raw", None)]
            source_report.update(source={"sha256": pinned, "size_bytes": record["source"]["size_bytes"]}, layers={})
        lake_spatial = dataset_id == "lakeatlas" and mutate in {"lake-spatial", "lake-spatial-unverified"}
        if lake_spatial:
            entries = [(asset_id, raw_bytes, raw_bytes + b" sorted") for asset_id, raw_bytes, _ in entries]
        augment_reports = []
        for ix, (asset_id, raw_bytes, final_bytes) in enumerate(entries):
            raw = self.write(f"{asset_id}-raw.parquet", raw_bytes)
            rebuilt_raw = self.write(f"{asset_id}-rebuilt-raw.parquet", raw_bytes)
            if mutate == "raw" and ix == 0:
                rebuilt_raw.write_bytes(b"altered rebuild raw")
            final_data = raw_bytes if final_bytes is None else final_bytes
            final = self.write(f"{asset_id}-final.parquet", final_data)
            rebuilt_final = self.write(f"{asset_id}-rebuilt-final.parquet", final_data)
            if mutate == "final" and ix == 0:
                rebuilt_final.write_bytes(b"altered rebuild final")
            raw_fp, final_fp = self.fp(raw), self.fp(final)
            if dataset_id == "hydrolakes":
                source_report.update(output_sha256=raw_fp["sha256"], output_bytes=raw_fp["size_bytes"])
            elif dataset_id == "free-flowing-rivers":
                source_report["geoparquet_sha256"] = raw_fp["sha256"]
            else:
                layer = record["source"]["source_layers"][ix]["name"]
                source_report["layers"][layer] = {"asset_sha256": raw_fp["sha256"],
                    "asset_bytes": raw_fp["size_bytes"], "source_equal_rows": record["source"]["source_layers"][ix]["expected_rows"],
                    "source_equal_wkb_rows": record["source"]["source_layers"][ix]["expected_rows"],
                    "source_equal_native_fields": record["source"]["source_layers"][ix]["output_source_fields"],
                    "source_reread": "passed_exact_column_arrays_in_source_order"}
            item = {"asset_id": asset_id, "raw_asset_path": raw.name,
                    "rebuilt_raw_asset_path": rebuilt_raw.name, "final_asset_path": final.name,
                    "rebuilt_final_asset_path": rebuilt_final.name}
            if dataset_id != "lakeatlas" or lake_spatial:
                first_report = self.write(f"{asset_id}-augmentation.json", b"")
                rebuilt_report = self.write(f"{asset_id}-rebuilt-augmentation.json", b"")
                report = {"status": "passed", "input": {"sha256": raw_fp["sha256"], "size_bytes": raw_fp["size_bytes"]},
                    "output": {"sha256": final_fp["sha256"], "size_bytes": final_fp["size_bytes"]},
                    "source_rows": 3, "geometry_types": {"Point": 3}, "global_bbox": [-2, -1, 3, 4],
                    "source_values_nulls_and_raw_wkb_compared": True,
                    "derived_bbox_values_recomputed_and_compared": True}
                if lake_spatial:
                    report.update(transformation="spatial_order",
                        source_order_reconstructed_and_compared=mutate != "lake-spatial-unverified",
                        source_rows=record["source"]["source_layers"][ix]["expected_rows"])
                if mutate == "augmentation" and ix == 0:
                    report["output"]["sha256"] = "0" * 64
                first_report.write_text(json.dumps(report))
                rebuilt_report.write_text(json.dumps({**report, "output": final_fp}))
                item.update(augmentation_report_path=first_report.name,
                            rebuilt_augmentation_report_path=rebuilt_report.name)
                augment_reports.append((first_report, rebuilt_report))
            assets.append(item)
        if mutate == "pending": source_report["status"] = "pending"
        if mutate == "lake-extra-layer" and dataset_id == "lakeatlas":
            source_report["layers"]["unexpected"] = dict(next(iter(source_report["layers"].values())))
        source_path = self.root / "source-validation.json"
        source_path.write_text(json.dumps(source_report))
        spec_data = {"dataset_id": dataset_id, "source_validation_path": source_path.name,
            "rebuild_context": {"raw_code_revision": "abc123", "spatial_code_revision": "def456" if dataset_id != "lakeatlas" or lake_spatial else None,
                "clean_checkout": {"method": "clean worktree receipt", "checkout_path": str(self.root / "checkout"),
                    "reported_status": "clean"}},
            "assets": assets}
        if lake_spatial:
            spec_data["final_transform"] = "spatial_order"
        self.spec_path.write_text(json.dumps(spec_data))
        return source_path, assets

    def normalize(self, dataset_id: str, mutate: str | None = None):
        self.prepare(dataset_id, mutate=mutate)
        return mod.normalize(self.spec_path, self.output)

    def test_valid_source_and_rebuild_chains_for_each_dataset(self):
        for dataset in ("hydrolakes", "free-flowing-rivers", "lakeatlas"):
            with self.subTest(dataset=dataset):
                self.tearDown()
                self.setUp()
                result = self.normalize(dataset)
                self.assertEqual(result["status"], "passed")
                source = json.loads((self.output / "source-fidelity.json").read_text())
                rebuild = json.loads((self.output / "clean-rebuild.json").read_text())
                self.assertEqual(source["status"], "passed")
                self.assertEqual(rebuild["status"], "passed")
                self.assertEqual(len(source["assets"]), 2 if dataset == "lakeatlas" else 1)
                self.assertFalse(rebuild["evidence"]["clean_checkout_independently_verified"])
                self.assertEqual(rebuild["evidence"]["clean_checkout_evidence"]["checkout_path"], "<local-path>/checkout")
                self.tearDown()

    def test_changed_raw_rebuild_is_rejected(self):
        self.prepare("hydrolakes", mutate="raw")
        with self.assertRaisesRegex(mod.FidelityError, "clean rebuild raw asset SHA/size differs"):
            mod.normalize(self.spec_path, self.output)
        self.assertFalse(self.output.exists())

    def test_changed_final_rebuild_is_rejected(self):
        self.prepare("free-flowing-rivers", mutate="final")
        with self.assertRaisesRegex(mod.FidelityError, "clean rebuild final asset SHA/size differs"):
            mod.normalize(self.spec_path, self.output)
        self.assertFalse(self.output.exists())

    def test_pending_source_report_is_rejected(self):
        self.prepare("hydrolakes", mutate="pending")
        with self.assertRaisesRegex(mod.FidelityError, "status must be 'passed'"):
            mod.normalize(self.spec_path, self.output)
        self.assertFalse(self.output.exists())

    def test_augmentation_must_bind_exact_raw_and_final(self):
        self.prepare("hydrolakes", mutate="augmentation")
        with self.assertRaisesRegex(mod.FidelityError, "output SHA does not match final"):
            mod.normalize(self.spec_path, self.output)
        self.assertFalse(self.output.exists())

    def test_lakeatlas_must_cover_exact_source_layers(self):
        self.prepare("lakeatlas", mutate="lake-extra-layer")
        with self.assertRaisesRegex(mod.FidelityError, "exactly the canonical source layers"):
            mod.normalize(self.spec_path, self.output)
        self.assertFalse(self.output.exists())

    def test_spatially_ordered_lakeatlas_requires_complete_restored_order_check(self):
        self.prepare("lakeatlas", mutate="lake-spatial-unverified")
        with self.assertRaisesRegex(mod.FidelityError, "restored-source-order comparison"):
            mod.normalize(self.spec_path, self.output)
        self.assertFalse(self.output.exists())
        self.prepare("lakeatlas", mutate="lake-spatial")
        result = mod.normalize(self.spec_path, self.output)
        self.assertEqual(result["status"], "passed")
        source = json.loads((self.output / "source-fidelity.json").read_text())
        self.assertEqual(source["evidence"]["final_transform"], "spatial_order")
        self.assertEqual(len(source["evidence"]["augmentation"]), 2)

    def test_spatially_ordered_hydrolakes_binds_raw_and_sorted_assets(self):
        self.prepare("hydrolakes")
        spec = json.loads(self.spec_path.read_text())
        spec["final_transform"] = "spatial_order"
        self.spec_path.write_text(json.dumps(spec))
        for field in ("augmentation_report_path", "rebuilt_augmentation_report_path"):
            path = self.root / spec["assets"][0][field]
            report = json.loads(path.read_text())
            report.update(transformation="spatial_order", source_order_reconstructed_and_compared=True,
                          source_rows=1427688)
            path.write_text(json.dumps(report))
        self.assertEqual(mod.normalize(self.spec_path, self.output)["status"], "passed")

    def test_existing_output_directory_is_refused(self):
        self.prepare("hydrolakes")
        self.output.mkdir()
        with self.assertRaisesRegex(mod.FidelityError, "refuse existing output directory"):
            mod.normalize(self.spec_path, self.output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
