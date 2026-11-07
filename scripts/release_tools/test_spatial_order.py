#!/usr/bin/env python3
"""Focused fixtures for bounded spatial ordering and exact reversible fidelity."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyproj
import shapely

import spatial_order as so


def fixture_table(with_bbox: bool = False, rows: int = 40) -> pa.Table:
    # Interleave broad geographic positions so the source order fails Rashid's
    # locality metric, while the Hilbert order groups nearby features.
    xs = [float((i * 37) % 360) - 180 for i in range(rows)]
    ys = [float((i * 19) % 180) - 90 for i in range(rows)]
    geometries = [shapely.Point(x, y) for x, y in zip(xs, ys, strict=True)]
    wkb = pa.array(shapely.to_wkb(geometries, byte_order=1), type=pa.binary())
    note_values = [None if i % 7 == 0 else f"n{i}" for i in range(rows)]
    schema = pa.schema([
        pa.field("OBJECTID", pa.int64(), nullable=False),
        pa.field("payload", pa.int32(), nullable=False),
        pa.field("note", pa.string()),
        pa.field("geometry", pa.binary()),
    ])
    arrays = [pa.array(range(1, rows + 1), type=pa.int64()),
              pa.array([i * 3 for i in range(rows)], type=pa.int32()),
              pa.array(note_values, type=pa.string()), wkb]
    fields = list(schema)
    if with_bbox:
        bounds = np.asarray(shapely.bounds(np.asarray(geometries, dtype=object)), dtype=np.float64)
        bbox = pa.StructArray.from_arrays(
            [pa.array(bounds[:, i], type=pa.float64()) for i in range(4)],
            names=list(so.BBOX_FIELDS),
        )
        arrays.append(bbox)
        fields.append(pa.field("bbox", bbox.type))
    crs = pyproj.CRS.from_user_input("OGC:CRS84").to_json_dict()
    geo = {
        "version": "1.1.0", "primary_column": "geometry",
        "columns": {"geometry": {"encoding": "WKB", "geometry_types": ["Point"], "crs": crs}},
    }
    if with_bbox:
        geo["columns"]["geometry"]["bbox"] = [min(xs), min(ys), max(xs), max(ys)]
    metadata = {b"geo": json.dumps(geo, sort_keys=True, separators=(",", ":")).encode(), b"fixture": b"preserved"}
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields, metadata=metadata))


class SpatialOrderTests(unittest.TestCase):
    def _stage_fixture(self, root: Path, name: str = "stage"):
        case = root / name
        case.mkdir()
        source_path = case / "raw.parquet"
        output_path = case / "ordered.parquet"
        report_path = case / "final.json"
        checkpoint_path = case / "stage-checkpoint.json"
        pq.write_table(fixture_table(), source_path, row_group_size=9)
        result = so.spatial_order(
            source_path, output_path, report_path, "OBJECTID", "geometry",
            bucket_count=4, batch_rows=7, buffer_rows=6, row_group_size=5,
            max_rss_bytes=1_000_000_000, enforce_guards=False,
            defer_validation=True, checkpoint_path=checkpoint_path,
        )
        return source_path, output_path, report_path, checkpoint_path, result

    @staticmethod
    def _complete(checkpoint: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(Path(so.__file__).resolve()), "--complete-stage", str(checkpoint)],
            check=False, capture_output=True, text=True, timeout=60,
        )

    def test_hilbert_mapping_is_stable_and_local(self):
        table = fixture_table()
        wkb = table["geometry"].combine_chunks()
        bounds, valid, _ = so._geometry_bounds(wkb)
        keys = so.hilbert_keys(bounds, valid)
        self.assertEqual(keys.tolist(), so.hilbert_keys(bounds, valid).tolist())
        sorted_keys = keys[np.argsort(keys)]
        self.assertTrue(np.all(sorted_keys[:-1] <= sorted_keys[1:]))

    def test_builds_bbox_when_missing_and_restores_all_source_cells(self):
        self._run_fixture(with_bbox=False)

    def test_preserves_existing_bbox_and_geo_metadata(self):
        self._run_fixture(with_bbox=True)

    def _run_fixture(self, with_bbox: bool):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path, output_path, report_path = root / "source.parquet", root / "ordered.parquet", root / "report.json"
            table = fixture_table(with_bbox=with_bbox)
            pq.write_table(table, source_path, compression="zstd", row_group_size=9)
            report = so.spatial_order(
                source_path, output_path, report_path, "OBJECTID", "geometry",
                bucket_count=4, batch_rows=7, buffer_rows=6, row_group_size=5,
                max_rss_bytes=1_000_000_000, enforce_guards=False,
            )
            self.assertEqual(report["status"], "passed")
            self.assertTrue(report["source_order_reconstructed_and_compared"])
            self.assertTrue(report["source_values_nulls_and_raw_wkb_compared"])
            self.assertTrue(report["derived_bbox_values_recomputed_and_compared"])
            self.assertEqual(report["bbox_was_added"], not with_bbox)
            self.assertTrue(report["validation"]["rashid_order_metrics"]["passed"])
            output = pq.read_table(output_path)
            self.assertEqual(output.schema.metadata[b"fixture"], b"preserved")
            output_bounds, output_valid, _ = so._geometry_bounds(output.column("geometry").combine_chunks())
            output_keys = so.hilbert_keys(output_bounds, output_valid)
            expected_ids = output.column("OBJECTID").to_numpy()[np.lexsort((output.column("OBJECTID").to_numpy(), output_keys))]
            self.assertEqual(output.column("OBJECTID").to_pylist(), expected_ids.tolist())
            expected = table
            if not with_bbox:
                bounds, valid, _ = so._geometry_bounds(expected.column("geometry").combine_chunks())
                expected = expected.append_column("bbox", so._bbox_struct(bounds, valid))
            source_schema = table.schema
            order = pa.compute.sort_indices(output, sort_keys=[("OBJECTID", "ascending")])
            restored = output.take(order)
            so.compare_source_tables(expected, restored, source_schema)

    def test_source_compare_detects_values_nulls_wkb_and_multiplicity(self):
        source = fixture_table(rows=6)
        schema = source.schema
        mutations = [
            ("payload", pa.array([0, 3, 6, 10, 12, 15], type=pa.int32())),
            ("note", pa.array([None, "n1", None, "n3", "n4", "n5"], type=pa.string())),
            ("geometry", pa.array([source["geometry"][0].as_py(), source["geometry"][1].as_py()[:-1] + b"\x00", *source["geometry"].slice(2).to_pylist()], type=pa.binary())),
        ]
        for name, array in mutations:
            with self.subTest(column=name), self.assertRaises(so.SpatialOrderError):
                so.compare_source_tables(source, source.set_column(source.schema.get_field_index(name), name, array), schema)
        with self.assertRaisesRegex(so.SpatialOrderError, "multiplicity"):
            so.compare_source_tables(source, source.slice(0, 5), schema)
        bad_ids = source.set_column(0, "OBJECTID", pa.array([1, 2, 2, 4, 5, 6], type=pa.int64()))
        with self.assertRaisesRegex(so.SpatialOrderError, "OBJECTID"):
            so.compare_source_tables(source, bad_ids, schema)

    def test_bbox_comparison_detects_child_mutation(self):
        source = fixture_table(with_bbox=True)
        box = source["bbox"].combine_chunks()
        bounds, valid = so._bounds_from_bbox(box)
        bounds[0, 0] += 0.25
        altered = so._bbox_struct(bounds, valid)
        self.assertFalse(so._bbox_arrays_equal(altered, box))
        partial_children = [pa.array([None if i == 0 else box.field(name)[i].as_py() for i in range(len(box))], type=pa.float64())
                            if name == "xmin" else box.field(name) for name in so.BBOX_FIELDS]
        partial = pa.StructArray.from_arrays(partial_children, names=list(so.BBOX_FIELDS))
        self.assertFalse(so._bbox_arrays_equal(partial, box))
        mixed_wkb = pa.array([None, shapely.to_wkb(shapely.Point(1, 2))], type=pa.binary())
        mixed_bounds, mixed_valid, _ = so._geometry_bounds(mixed_wkb)
        mixed_bbox = so._bbox_struct(mixed_bounds, mixed_valid)
        self.assertEqual(mixed_bbox.is_valid().to_pylist(), [False, True])

    def test_rejects_3d_geometries_and_projected_crs(self):
        three_d = pa.array([shapely.to_wkb(shapely.Point(1, 2, 3))], type=pa.binary())
        with self.assertRaisesRegex(so.SpatialOrderError, "3D WKB"):
            so._geometry_bounds(three_d)
        table = fixture_table(rows=4)
        geo = json.loads(table.schema.metadata[b"geo"])
        geo["columns"]["geometry"]["crs"] = pyproj.CRS.from_epsg(3857).to_json_dict()
        schema = table.schema.with_metadata({**table.schema.metadata, b"geo": json.dumps(geo).encode()})
        with self.assertRaisesRegex(so.SpatialOrderError, "requires WGS 84"):
            so._geo_info(schema, "geometry", None, ["Point"], [-1.0, -1.0, 1.0, 1.0])

    def test_full_validator_rejects_per_feature_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path, ordered_path = root / "raw.parquet", root / "ordered.parquet"
            original = fixture_table()
            pq.write_table(original, source_path)
            report = so.spatial_order(source_path, ordered_path, root / "report.json", "OBJECTID", "geometry",
                                      bucket_count=4, batch_rows=7, buffer_rows=6, row_group_size=5,
                                      enforce_guards=False)
            baseline = pq.read_table(ordered_path)
            changes = []
            values = baseline["payload"].to_pylist(); values[0] += 1
            changes.append(("payload", baseline.set_column(1, baseline.schema.field("payload"), pa.array(values, type=pa.int32())), "payload"))
            values = baseline["note"].to_pylist(); values[next(i for i, value in enumerate(values) if value is not None)] = None
            changes.append(("null", baseline.set_column(2, baseline.schema.field("note"), pa.array(values, type=pa.string())), "note"))
            values = baseline["geometry"].to_pylist(); values[0] = values[1]
            changes.append(("wkb", baseline.set_column(3, baseline.schema.field("geometry"), pa.array(values, type=pa.binary())), "WKB SHA-256"))
            values = baseline["OBJECTID"].to_pylist(); values[0] = values[1]
            changes.append(("id", baseline.set_column(0, baseline.schema.field("OBJECTID"), pa.array(values, type=pa.int64())), "identifiers"))
            box = baseline["bbox"].combine_chunks()
            bounds, valid = so._bounds_from_bbox(box); bounds[0, 0] += 1
            changes.append(("bbox", baseline.set_column(4, baseline.schema.field("bbox"), so._bbox_struct(bounds, valid)), "derived bbox"))
            changes.append(("missing", baseline.slice(0, 39), "multiplicity"))
            for name, altered, reason in changes:
                with self.subTest(name=name):
                    path = root / (name + ".parquet")
                    pq.write_table(altered, path)
                    guard = so.DiskGuard(root / "unused", path, root / "unused-final", 0, 0, 0, 0, enabled=False)
                    with self.assertRaisesRegex(so.SpatialOrderError, reason):
                        so._restore_and_validate(source_path, path, "OBJECTID", "geometry", original.schema,
                            baseline.schema, False, 40, 40, report["global_bbox"], so.Counter({"Point": 40}),
                            4, 7, 6, 1_000_000_000, root / "unused", guard)

    def test_deferred_stage_then_fresh_process_matches_default_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.parquet"
            pq.write_table(fixture_table(), source, row_group_size=9)
            default_output, default_report = root / "default.parquet", root / "default.json"
            default = so.spatial_order(
                source, default_output, default_report, "OBJECTID", "geometry",
                bucket_count=4, batch_rows=7, buffer_rows=6, row_group_size=5,
                max_rss_bytes=1_000_000_000, enforce_guards=False,
            )
            output = root / "deferred.parquet"
            report = root / "deferred.json"
            checkpoint = root / "deferred-checkpoint.json"
            staged = so.spatial_order(
                source, output, report, "OBJECTID", "geometry",
                bucket_count=4, batch_rows=7, buffer_rows=6, row_group_size=5,
                max_rss_bytes=1_000_000_000, enforce_guards=False,
                defer_validation=True, checkpoint_path=checkpoint,
            )
            self.assertEqual(staged["status"], "pending_validation")
            self.assertFalse(output.exists())
            self.assertFalse(report.exists())
            checkpoint_data = json.loads(checkpoint.read_text())
            self.assertEqual(checkpoint_data["status"], "pending_validation")
            self.assertEqual(checkpoint_data["stage"]["sha256"], so.sha256(Path(checkpoint_data["stage"]["path"])))

            completed = self._complete(checkpoint)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            final = json.loads(report.read_text())
            self.assertEqual(final["status"], "passed")
            self.assertEqual(so.sha256(output), so.sha256(default_output))
            self.assertEqual(final["output"]["sha256"], default["output"]["sha256"])
            self.assertEqual(final["process_execution"], {"mode": "sequential_processes", "processes_sequential": True})
            peaks = final["phase_peak_rss_bytes"]
            self.assertEqual(final["peak_rss_bytes"], max(peaks.values()))
            self.assertEqual(final["validation"]["source_attribute_values_nulls_compared"], 40 * 3)
            self.assertEqual(final["validation"]["wkb_rows_compared"], 40)

    def test_deferred_completion_rejects_input_stage_and_code_pin_corruption(self):
        for corruption in ("input", "stage", "code_pin", "sort_peak_cap"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, output, report, checkpoint, _ = self._stage_fixture(root, corruption)
                data = json.loads(checkpoint.read_text())
                if corruption == "input":
                    table = pq.read_table(source)
                    values = table["payload"].to_pylist(); values[0] += 1
                    pq.write_table(table.set_column(1, table.schema.field("payload"), pa.array(values, type=pa.int32())), source)
                elif corruption == "stage":
                    stage = Path(data["stage"]["path"])
                    stage.chmod(0o644)
                    table = pq.read_table(stage)
                    values = table["payload"].to_pylist(); values[0] += 1
                    pq.write_table(table.set_column(1, table.schema.field("payload"), pa.array(values, type=pa.int32())), stage)
                else:
                    checkpoint.chmod(0o644)
                    if corruption == "code_pin":
                        data["helper_sha256"] = "0" * 64
                    else:
                        data["parameters"]["max_rss_bytes"] = data["sort_peak_rss_bytes"]
                    data["checkpoint_payload_sha256"] = so._checkpoint_digest(data)
                    checkpoint.write_bytes(so._canonical_json_bytes(data))
                    checkpoint.chmod(0o444)

                completed = self._complete(checkpoint)
                self.assertNotEqual(completed.returncode, 0)
                self.assertFalse(output.exists())
                failure = json.loads(report.read_text())
                self.assertEqual(failure["status"], "failed")
                if corruption == "input":
                    self.assertIn("input identity changed", failure["error"])
                elif corruption == "stage":
                    self.assertIn("staged Parquet identity changed", failure["error"])
                elif corruption == "code_pin":
                    self.assertIn("helper checksum differs", failure["error"])
                else:
                    self.assertIn("sort peak is at or above", failure["error"])

    def test_deferred_completion_rejects_schema_tampering_and_refuses_recompletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _source, output, report, checkpoint, _ = self._stage_fixture(root, "schema")
            data = json.loads(checkpoint.read_text())
            input_schema = so._schema_from_b64(data["input_schema_b64"], "test input")
            checkpoint.chmod(0o644)
            data["output_schema_b64"] = so._schema_b64(input_schema)
            data["checkpoint_payload_sha256"] = so._checkpoint_digest(data)
            checkpoint.write_bytes(so._canonical_json_bytes(data))
            checkpoint.chmod(0o444)
            completed = self._complete(checkpoint)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())
            self.assertIn("checkpoint output schema differs", json.loads(report.read_text())["error"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _source, output, report, checkpoint, _ = self._stage_fixture(root, "overwrite")
            completed = self._complete(checkpoint)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output_hash = so.sha256(output)
            report_bytes = report.read_bytes()
            second = self._complete(checkpoint)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("refuse overwrite existing immutable output", second.stderr)
            self.assertEqual(so.sha256(output), output_hash)
            self.assertEqual(report.read_bytes(), report_bytes)

    def test_complete_stage_rejects_every_build_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _source, output, report, checkpoint, _ = self._stage_fixture(root, "options")
            result = subprocess.run(
                [sys.executable, str(Path(so.__file__).resolve()), "--complete-stage", str(checkpoint),
                 "--buckets", "4"],
                check=False, capture_output=True, text=True, timeout=60,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertFalse(report.exists())
            completed = self._complete(checkpoint)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_identifier_must_be_one_based_contiguous_source_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "bad.parquet"
            pq.write_table(fixture_table().set_column(0, "OBJECTID", pa.array([2, *range(2, 41)], type=pa.int64())), source_path)
            report_path = root / "report.json"
            with self.assertRaisesRegex(so.SpatialOrderError, "one-based source-order"):
                so.spatial_order(source_path, root / "out.parquet", report_path, "OBJECTID", "geometry",
                                 bucket_count=4, enforce_guards=False)
            self.assertEqual(json.loads(report_path.read_text())["status"], "failed")
            with self.assertRaises(so.SpatialOrderError):
                so.spatial_order(source_path, root / "out.parquet", report_path, "OBJECTID", "geometry",
                                 bucket_count=4, enforce_guards=False)

    def test_failed_stage_is_retained_with_hash_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path, output_path, report_path = root / "source.parquet", root / "ordered.parquet", root / "failed.json"
            pq.write_table(fixture_table(), source_path, row_group_size=9)
            with mock.patch.object(so, "_restore_and_validate", side_effect=so.SpatialOrderError("injected validation fault")):
                with self.assertRaisesRegex(so.SpatialOrderError, "injected validation fault"):
                    so.spatial_order(source_path, output_path, report_path, "OBJECTID", "geometry",
                                     bucket_count=4, batch_rows=7, buffer_rows=6,
                                     row_group_size=5, enforce_guards=False)
            failure = json.loads(report_path.read_text())
            self.assertEqual(failure["status"], "failed")
            self.assertFalse(failure["source_written_by_transform"])
            artifacts = failure["retained_partial_artifacts"]
            stage = next(Path(item["path"]) for item in artifacts if ".partial-" in item["path"])
            stage_record = next(item for item in artifacts if item["path"] == str(stage))
            self.assertGreater(stage.stat().st_size, 0)
            self.assertEqual(stage.stat().st_size, stage_record["size_bytes"])
            self.assertEqual(so.sha256(stage), stage_record["sha256"])
            work = next(Path(item["path"]) for item in artifacts if ".work-" in item["path"])
            self.assertTrue(work.is_dir())

    def test_disk_guard_checks_free_floor_and_owned_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, stage, output = root / "work", root / "stage", root / "output"
            work.mkdir()
            usage = type("Usage", (), {"free": 1})()
            guard = so.DiskGuard(work, stage, output, 0, 0, 100, 10)
            with mock.patch.object(so.shutil, "disk_usage", return_value=usage):
                with self.assertRaisesRegex(so.SpatialOrderError, "free disk"):
                    guard.check_free()
            retained = work / "data.arrow"
            retained.write_bytes(b"12345")
            guard = so.DiskGuard(work, stage, output, 0, 0, 4, 0)
            with self.assertRaisesRegex(so.SpatialOrderError, "allocated bytes"):
                guard.check()


if __name__ == "__main__":
    unittest.main()
