#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import shapely

SCRIPT = Path(__file__).with_name("add_spatial_bounds.py")
spec = importlib.util.spec_from_file_location("add_spatial_bounds", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class SpatialBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spatial-bounds-fixture-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source.parquet"
        geoms = [shapely.Point(-123.2, 45.4), shapely.LineString([(1, 2), (3, 4)]), None,
                 shapely.Polygon([(4, 5), (6, 5), (6, 7), (4, 5)])]
        table = pa.table({"fid": [10, 11, 12, 13], "label": ["a", None, "c", "d"],
                          "geometry": pa.array(shapely.to_wkb(geoms), type=pa.binary())})
        pq.write_table(table, self.source, row_group_size=2)

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        output, report = self.root / "augmented.parquet", self.root / "report.json"
        data = mod.add_spatial_bounds(self.source, output, report, "geometry", "EPSG:4326",
                                      batch_rows=2, max_rss_bytes=2**31,
                                      minimum_remaining_free_bytes=0, minimum_start_free_bytes=0)
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["source_rows"], 4)
        self.assertEqual(data["geometry_types"], {"LineString": 1, "Point": 1, "Polygon": 1})
        self.assertEqual(data["global_bbox"], [-123.2, 2.0, 6.0, 45.4])
        self.assertFalse(output.stat().st_mode & 0o222)
        self.assertFalse(report.stat().st_mode & 0o222)
        parsed = json.loads(report.read_text())
        self.assertEqual(parsed["output"]["sha256"], mod.sha256(output))
        return output

    def test_streaming_addition_preserves_source_and_emits_covering(self):
        output = self.build()
        result = mod.validate_pair(self.source, output, "geometry", "EPSG:4326", 2,
                                   [-123.2, 2.0, 6.0, 45.4], ["LineString", "Point", "Polygon"])
        self.assertEqual(result["source_rows"], 4)
        geo = json.loads(pq.ParquetFile(output).schema_arrow.metadata[b"geo"])
        self.assertEqual(geo["columns"]["geometry"]["covering"]["bbox"]["xmin"], ["bbox", "xmin"])
        self.assertEqual(pq.ParquetFile(output).metadata.num_row_groups, 2)

    def test_attribute_corruption_is_rejected(self):
        output = self.build()
        pf = pq.ParquetFile(output)
        table = pf.read()
        table = table.set_column(table.schema.get_field_index("fid"), "fid", pa.array([10, 999, 12, 13]))
        corrupt = self.root / "bad-attribute.parquet"
        pq.write_table(table, corrupt, compression="zstd")
        with self.assertRaisesRegex(mod.SpatialBoundsError, "source field/value/null/raw-WKB mismatch: fid"):
            mod.validate_pair(self.source, corrupt, "geometry", "EPSG:4326", 2,
                              [-123.2, 2.0, 6.0, 45.4], ["LineString", "Point", "Polygon"])

    def test_bbox_corruption_is_rejected(self):
        output = self.build()
        table = pq.read_table(output)
        bbox = table["bbox"].combine_chunks()
        children = [bbox.field(i) for i in range(4)]
        children[0] = pa.array([-123.2, 2.0, 999.0, 4.0], type=pa.float64())
        replacement = pa.StructArray.from_arrays(children, names=["xmin", "ymin", "xmax", "ymax"])
        table = table.set_column(table.schema.get_field_index("bbox"), "bbox", replacement)
        corrupt = self.root / "bad-bbox.parquet"
        pq.write_table(table, corrupt, compression="zstd")
        with self.assertRaisesRegex(mod.SpatialBoundsError, "derived per-row bbox mismatch"):
            mod.validate_pair(self.source, corrupt, "geometry", "EPSG:4326", 2,
                              [-123.2, 2.0, 6.0, 45.4], ["LineString", "Point", "Polygon"])

    def test_crs_metadata_corruption_is_rejected(self):
        output = self.build()
        table = pq.read_table(output)
        metadata = dict(table.schema.metadata or {})
        geo = json.loads(metadata[b"geo"])
        geo["columns"]["geometry"]["crs"] = __import__("pyproj").CRS.from_epsg(3857).to_json_dict()
        metadata[b"geo"] = json.dumps(geo).encode()
        table = table.replace_schema_metadata(metadata)
        corrupt = self.root / "bad-crs.parquet"
        pq.write_table(table, corrupt, compression="zstd")
        with self.assertRaisesRegex(mod.SpatialBoundsError, "output CRS does not semantically match source CRS"):
            mod.validate_pair(self.source, corrupt, "geometry", "EPSG:4326", 2,
                              [-123.2, 2.0, 6.0, 45.4], ["LineString", "Point", "Polygon"])

    def test_explicit_null_crs_requires_user_identification(self):
        table = pq.read_table(self.source)
        metadata = dict(table.schema.metadata or {})
        geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {
            "geometry": {"encoding": "WKB", "crs": None}}}
        metadata[b"geo"] = json.dumps(geo).encode()
        unknown = self.root / "unknown-crs.parquet"
        pq.write_table(table.replace_schema_metadata(metadata), unknown)
        with self.assertRaisesRegex(mod.SpatialBoundsError, "explicitly declares null CRS"):
            mod.add_spatial_bounds(unknown, self.root / "unknown-out.parquet", self.root / "unknown.json",
                                   "geometry", None, minimum_remaining_free_bytes=0, minimum_start_free_bytes=0)

    def test_omitted_crs_defaults_to_crs84_and_cannot_be_relabelled(self):
        table = pq.read_table(self.source)
        geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {
            "geometry": {"encoding": "WKB"}}}
        schema = table.schema.with_metadata({b"geo": json.dumps(geo).encode()})
        with self.assertRaisesRegex(mod.SpatialBoundsError, "conflicts with GeoParquet CRS"):
            mod._crs_json(schema, "geometry", "EPSG:3857")
        selected = mod._crs_json(schema, "geometry", "EPSG:4326")
        self.assertEqual(selected["id"], {"authority": "EPSG", "code": 4326})

    def test_z_geometry_is_explicitly_rejected(self):
        geoms = pa.array([shapely.to_wkb(shapely.Point(1, 2, 3))], type=pa.binary())
        with self.assertRaisesRegex(mod.SpatialBoundsError, "refuses Z/M"):
            mod._geometry_array(geoms)

    def test_refuses_overwrite(self):
        output = self.build()
        with self.assertRaisesRegex(mod.SpatialBoundsError, "refuse overwrite"):
            mod.add_spatial_bounds(self.source, output, self.root / "second.json", "geometry", "EPSG:4326",
                                   minimum_remaining_free_bytes=0, minimum_start_free_bytes=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
