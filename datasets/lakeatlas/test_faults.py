"""Small deterministic mutation tests for the source fidelity validator."""
from __future__ import annotations

import unittest

import pyarrow as pa
import shapely

from build import BBOX_FIELDS, bbox_array, bounds_for

from validate_worker import compare_batches, validate_bbox_array, validate_geo_metadata, write_report


class SourceFidelityFaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = pa.record_batch({
            "OBJECTID": pa.array([1, 2, 3], type=pa.int64()),
            "Hylak_id": pa.array([11, 12, 13], type=pa.int32()),
            "value": pa.array([1.5, None, 3.5], type=pa.float32()),
            "geometry": pa.array([b"wkb-one", b"wkb-two", b"wkb-three"], type=pa.binary()),
        })

    def assert_rejected(self, altered: pa.RecordBatch) -> None:
        with self.assertRaisesRegex(ValueError, "mismatch"):
            compare_batches(self.source, altered)

    def test_remove_row_is_rejected(self) -> None:
        self.assert_rejected(self.source.slice(0, 2))

    def test_duplicate_row_is_rejected(self) -> None:
        duplicate = pa.record_batch({
            "OBJECTID": pa.array([1, 2, 2], type=pa.int64()),
            "Hylak_id": pa.array([11, 12, 12], type=pa.int32()),
            "value": pa.array([1.5, None, None], type=pa.float32()),
            "geometry": pa.array([b"wkb-one", b"wkb-two", b"wkb-two"], type=pa.binary()),
        })
        self.assert_rejected(duplicate)

    def test_changed_value_is_rejected(self) -> None:
        altered = self.source.set_column(2, self.source.schema.field(2), pa.array([1.5, None, 3.6], type=pa.float32()))
        self.assert_rejected(altered)

    def test_changed_null_is_rejected(self) -> None:
        altered = self.source.set_column(2, self.source.schema.field(2), pa.array([1.5, 2.5, 3.5], type=pa.float32()))
        self.assert_rejected(altered)

    def test_changed_native_hylak_id_is_rejected(self) -> None:
        altered = self.source.set_column(1, self.source.schema.field(1), pa.array([11, 22, 13], type=pa.int32()))
        self.assert_rejected(altered)

    def test_changed_objectid_fid_is_rejected(self) -> None:
        altered = self.source.set_column(0, self.source.schema.field(0), pa.array([1, 20, 3], type=pa.int64()))
        self.assert_rejected(altered)

    def test_changed_geometry_is_rejected(self) -> None:
        altered = self.source.set_column(3, self.source.schema.field(3), pa.array([b"wkb-one", b"wkb-altered", b"wkb-three"], type=pa.binary()))
        self.assert_rejected(altered)

    def test_wrong_schema_order_is_rejected(self) -> None:
        altered = pa.record_batch({
            "Hylak_id": self.source.column(1), "OBJECTID": self.source.column(0),
            "value": self.source.column(2), "geometry": self.source.column(3),
        })
        self.assert_rejected(altered)

    def test_failed_report_is_preserved_without_overwrite(self) -> None:
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_report(path, {"status": "failed_source_fidelity", "error": "fault injected"})
            with self.assertRaises(FileExistsError):
                write_report(path, {"status": "passed_source_fidelity"})
            self.assertEqual(json.loads(path.read_text())["status"], "failed_source_fidelity")

    def test_altered_bbox_child_is_rejected(self) -> None:
        points = shapely.points([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
        wkb = pa.array(shapely.to_wkb(points), type=pa.binary())
        bounds, usable, _ = bounds_for(wkb)
        expected = bbox_array(bounds, usable)
        children = [expected.field(name) for name in BBOX_FIELDS]
        children[0] = pa.array([9.0, 2.0, 3.0], type=pa.float64())
        altered = pa.StructArray.from_arrays(children, names=BBOX_FIELDS)
        with self.assertRaisesRegex(ValueError, "bbox child"):
            validate_bbox_array(wkb, altered, "fault")

    def test_missing_geoparquet_metadata_is_rejected(self) -> None:
        import tempfile
        from pathlib import Path
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.parquet"
            pq.write_table(pa.Table.from_batches([self.source]), path)
            with self.assertRaisesRegex(ValueError, "missing GeoParquet metadata"):
                validate_geo_metadata(path, "Point")


if __name__ == "__main__":
    unittest.main()
