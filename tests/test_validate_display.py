"""Independent PMTiles geometry validation regression fixtures."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mapbox_vector_tile
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from pyproj import Transformer
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_display as validator  # noqa: E402


class CoordinateTests(unittest.TestCase):
    def test_xyz_y_flip_and_tile_extent(self):
        x, y = 2048, 2048
        geom = validator.tile_geometry_mercator({"type": "Point", "coordinates": [0, 4096]}, x, y)
        self.assertAlmostEqual(geom.x, 0.0, places=6)
        self.assertAlmostEqual(geom.y, 0.0, places=6)
        south = validator.tile_geometry_mercator({"type": "Point", "coordinates": [0, 0]}, x, y)
        self.assertLess(south.y, 0)
        self.assertEqual(validator.tile_range((0, -0.1, 0.1, 0)), (2048, 2048, 2049, 2049))

    def test_exact_numeric_and_null_omission(self):
        self.assertEqual(validator.property_errors({"id": 3, "v": 1.25}, {"id": 3, "v": 1.25}), [])
        self.assertTrue(validator.property_errors({"id": 3}, {"id": 3, "v": 0}))
        self.assertTrue(validator.property_errors({"id": 3}, {"id": 4}))

    def test_clipped_line_fragments_join_across_tiles(self):
        left = validator.tile_geometry_mercator({"type": "LineString", "coordinates": [[4090, 2048], [4096, 2048]]}, 2048, 2048)
        right = validator.tile_geometry_mercator({"type": "LineString", "coordinates": [[0, 2048], [6, 2048]]}, 2049, 2048)
        inverse = Transformer.from_crs(3857, 4326, always_xy=True)
        source = LineString([inverse.transform(*left.coords[0]), inverse.transform(*right.coords[-1])])
        distance = shapely.hausdorff_distance(validator.source_geometry_mercator(shapely.to_wkb(source)),
                                              shapely.union_all([left, right]), densify=0.5)
        self.assertLess(distance, 1e-6)

    def test_buffer_margin_is_removed_before_union(self):
        buffer_polygon = validator.tile_geometry_mercator(
            {"type": "Polygon", "coordinates": [[[4000, -80], [4176, -80], [4176, 80], [4000, 80], [4000, -80]]]},
            2048, 2048)
        core = shapely.intersection(buffer_polygon, validator.tile_core_mercator(2048, 2048))
        self.assertLess(core.area, buffer_polygon.area)
        self.assertAlmostEqual(core.bounds[2], validator.tile_core_mercator(2048, 2048).bounds[2], places=6)

    def test_lowest_eligible_ids_after_cap_are_row_order_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            # More than the old 128-candidate shortcut: all low IDs span far
            # more than 64 z12 tiles, while the following 32 are eligible.
            records = ([{"OBJECTID": fid, "bbox": {"xmin": -10.0, "ymin": -10.0,
                                                   "xmax": 10.0, "ymax": 10.0}}
                        for fid in range(1, 161)] +
                       [{"OBJECTID": fid, "bbox": {"xmin": 1.0, "ymin": 1.0,
                                                   "xmax": 1.0, "ymax": 1.0}}
                        for fid in range(161, 193)])
            paths = [Path(directory) / "forward.parquet", Path(directory) / "reverse.parquet"]
            for path, order in zip(paths, (records, list(reversed(records)))):
                pq.write_table(pa.Table.from_pylist(order), path)
            with patch.object(validator, "REGIONS", {"global": [-170, -55, 175, 80]}):
                results = [validator.choose_ids(path, "OBJECTID") for path in paths]
            for selected, groups, rows in results:
                self.assertEqual(rows, 192)
                self.assertEqual(groups["global"], list(range(161, 193)))
                self.assertEqual(sorted(selected), groups["global"])

    def test_adjacent_core_bounds_dissolve_without_a_seam(self):
        # Both fragments include the usual 80-unit MVT buffer. Indexed core
        # bounds must be bit-identical at the shared XYZ edge; adding `side`
        # to a floating left bound produced a tiny gap and false km errors.
        def polygon(x0, x1):
            return {"type": "Polygon", "coordinates": [[[x0, 1000], [x1, 1000],
                                                            [x1, 2000], [x0, 2000], [x0, 1000]]]}

        left = validator.tile_geometry_mercator(polygon(4000, 4176), 2048, 2048)
        right = validator.tile_geometry_mercator(polygon(-80, 96), 2049, 2048)
        left_core = validator.tile_core_mercator(2048, 2048)
        right_core = validator.tile_core_mercator(2049, 2048)
        self.assertEqual(left_core.bounds[2], right_core.bounds[0])
        rendered = shapely.union_all([shapely.intersection(left, left_core),
                                      shapely.intersection(right, right_core)])
        self.assertEqual(rendered.geom_type, "Polygon")
        self.assertLess(shapely.hausdorff_distance(rendered, shapely.union_all([left, right]), densify=0.5), 1e-6)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.parquet"
        self.archive = self.root / "test.pmtiles"
        self.manifest = self.root / "manifest.json"
        # Build 32 distinct source IDs at integer tile coordinates. The fixed
        # global sample then has no dependence on selection mock behavior.
        to_lonlat = Transformer.from_crs(3857, 4326, always_xy=True)
        self.features = []
        records = []
        for fid in range(1, 33):
            u, v = 1800 + fid, 1900 + fid
            merc = validator.tile_geometry_mercator({"type": "Point", "coordinates": [u, v]}, 2048, 2048)
            lon, lat = to_lonlat.transform(merc.x, merc.y)
            bbox = {"xmin": lon, "ymin": lat, "xmax": lon, "ymax": lat}
            records.append({"OBJECTID": fid, "wkb_geometry": shapely.to_wkb(Point(lon, lat)), "bbox": bbox,
                            "metric": None if fid == 1 else float(fid)})
            properties = {"OBJECTID": fid, **{f"_src_{key}": value for key, value in bbox.items()}}
            if fid != 1:
                properties["metric"] = float(fid)
            self.features.append({"geometry": {"type": "Point", "coordinates": [u, v]},
                                  "properties": properties, "id": fid})
        pq.write_table(pa.Table.from_pylist(records), self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def write_archive(self, shift_first: int = 0, wrong_id: bool = False, wrong_attr: bool = False,
                      omit_id_property: bool = False, id_encoding: str | None = None,
                      conflicting_id_property: bool = False):
        features = json.loads(json.dumps(self.features))
        if shift_first:
            features[0]["geometry"]["coordinates"][0] += shift_first
        if wrong_id:
            features[0]["id"] = 999
        if wrong_attr:
            features[0]["properties"]["metric"] = 0.0
        if omit_id_property:
            for feature in features:
                del feature["properties"]["OBJECTID"]
        if conflicting_id_property:
            features[0]["properties"]["OBJECTID"] = 999
        raw = mapbox_vector_tile.encode({"name": "test-points", "features": features})
        with self.archive.open("wb") as stream:
            writer = Writer(stream)
            writer.write_tile(zxy_to_tileid(12, 2048, 2048), raw)
            writer.finalize({"tile_compression": Compression.NONE, "tile_type": TileType.MVT},
                            {"vector_layers": [{"id": "test-points", "fields": {}}]})
        asset = {"id": "test-1", "path": self.archive.name, "size_bytes": self.archive.stat().st_size,
                 "sha256": validator.sha256(self.archive), "source_layer": "test-points", "geometry_type": "point",
                 "min_zoom": 12, "max_zoom": 12, "id_field": "OBJECTID", "source_rows": 32,
                 "attribute_fields": ["OBJECTID", "metric", "_src_xmin", "_src_ymin", "_src_xmax", "_src_ymax"],
                 "source_asset": {"path": self.source.name, "size_bytes": self.source.stat().st_size,
                                  "sha256": validator.sha256(self.source)}}
        if id_encoding is not None:
            asset["id_encoding"] = id_encoding
        self.manifest.write_text(json.dumps({"assets": [asset]}))

    def check(self):
        with patch.object(validator, "REGIONS", {"global": [-180, -85, 180, 85]}):
            return validator.validate(self.manifest, "test-1", self.source)

    def test_roundtrip(self):
        self.write_archive()
        report = self.check()
        self.assertTrue(report["passed"], report["failures"][:5])
        self.assertEqual(report["sampled_unique_ids"], 32)
        self.assertLess(report["max_distance_m"], 1)
        self.assertEqual(report["source_sha256"], validator.sha256(self.source))
        self.assertEqual(report["source_size_bytes"], self.source.stat().st_size)
        self.assertEqual(report["pmtiles_sha256"], validator.sha256(self.archive))
        self.assertEqual(report["pmtiles_size_bytes"], self.archive.stat().st_size)
        self.assertEqual(report["validator_sha256"], validator.sha256(Path(validator.__file__)))
        self.assertEqual(report["source_asset_path"], self.source.name)
        self.assertEqual(report["pmtiles_asset_path"], self.archive.name)
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_shifted_geometry_fails_30m(self):
        self.write_archive(shift_first=25)
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("Hausdorff" in error for error in report["failures"]))

    def test_id_mismatch_fails(self):
        self.write_archive(wrong_id=True)
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("no z12 tile fragments" in error for error in report["failures"]))

    def test_null_attribute_mismatch_fails(self):
        self.write_archive(wrong_attr=True)
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("unexpected value" in error for error in report["failures"]))

    def test_changed_archive_bytes_fail_binding(self):
        self.write_archive()
        with self.archive.open("ab") as stream:
            stream.write(b"corrupt")
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("PMTiles SHA-256 mismatch" in error for error in report["failures"]))

    def test_explicit_mvt_feature_id_accepts_missing_property(self):
        self.write_archive(omit_id_property=True, id_encoding="mvt_feature_id")
        self.assertTrue(self.check()["passed"])

    def test_missing_id_property_without_flag_fails(self):
        self.write_archive(omit_id_property=True)
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("OBJECTID: expected" in error for error in report["failures"]))

    def test_explicit_both_representations_requires_property(self):
        self.write_archive(omit_id_property=True, id_encoding="mvt_feature_id_and_property")
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("OBJECTID: expected" in error for error in report["failures"]))

    def test_conflicting_id_property_with_flag_fails(self):
        self.write_archive(id_encoding="mvt_feature_id", conflicting_id_property=True)
        report = self.check()
        self.assertFalse(report["passed"])
        self.assertTrue(any("OBJECTID: expected" in error for error in report["failures"]))


if __name__ == "__main__":
    unittest.main()
