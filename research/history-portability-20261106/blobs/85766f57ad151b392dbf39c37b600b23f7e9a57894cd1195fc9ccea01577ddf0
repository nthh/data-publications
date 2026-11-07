"""Offline losslessness and indexing checks for the HydroLAKES converter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import duckdb
import geopandas as gpd
import pyarrow.parquet as pq
import pyogrio
from pyproj import CRS
import shapely
from shapely.geometry import Polygon


MODULE_PATH = Path(__file__).with_name("convert.py")
SPEC = importlib.util.spec_from_file_location("convert_hydrolakes", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


class HydroLAKESConverterTests(unittest.TestCase):
    def _source(self, root: Path, ids: list[int]) -> Path:
        shapes = [
            Polygon(
                [
                    (-90.0 + i * 0.02, 46.0),
                    (-89.99 + i * 0.02, 46.0),
                    (-89.99 + i * 0.02, 46.01),
                    (-90.0 + i * 0.02, 46.01),
                    (-90.0 + i * 0.02, 46.0),
                ],
                holes=[
                    [
                        (-89.998 + i * 0.02, 46.002),
                        (-89.998 + i * 0.02, 46.004),
                        (-89.996 + i * 0.02, 46.004),
                        (-89.996 + i * 0.02, 46.002),
                        (-89.998 + i * 0.02, 46.002),
                    ]
                ],
            )
            for i in range(len(ids))
        ]
        frame = gpd.GeoDataFrame(
            {
                "Hylak_id": ids,
                "Lake_name": [None if i == 1 else f"Lake {i}" for i in range(len(ids))],
                "Lake_area": [0.25 + i for i in range(len(ids))],
                "Lake_type": [1 for _ in ids],
            },
            geometry=shapes,
            crs="EPSG:4326",
        )
        path = root / "HydroLAKES_polys_v10.shp"
        frame.to_file(path, driver="ESRI Shapefile", engine="pyogrio")
        return path

    def _convert(self, source: Path, root: Path, ids: list[int]):
        output = root / "hydrolakes.parquet"
        staging = root / "private-staging"
        manifest = converter.convert(
            source,
            output,
            staging,
            expected_count=len(ids),
            expected_min_id=min(ids),
            expected_max_id=max(ids),
            batch_size=2,
            stage_target_bytes=1,
            output_target_bytes=1,
        )
        return output, manifest

    def test_shapefile_stream_preserves_attributes_coordinates_and_id_stats(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(root, [12, 10, 11])
            # Capture the source's actual GDAL WKB before conversion; this is
            # the geometry identity boundary the converter promises to retain.
            with pyogrio.open_arrow(source, use_pyarrow=True, batch_size=2) as opened:
                source_meta, source_reader = opened
                geometry_name = source_meta.get("geometry_name") or "wkb_geometry"
                source_rows = {}
                for batch in source_reader:
                    for row in range(batch.num_rows):
                        source_rows[int(batch["Hylak_id"][row].as_py())] = {
                            name: batch[name][row].as_py() for name in batch.schema.names
                        }

            output, manifest = self._convert(source, root, [10, 11, 12])
            parquet = pq.ParquetFile(output)
            self.assertEqual(parquet.metadata.num_rows, 3)
            self.assertEqual(manifest["hylak_id"], {"minimum": 10, "maximum": 12, "unique": True, "contiguous": True})
            for got, expected in zip(manifest["bbox"], [-90.0, 46.0, -89.95, 46.01], strict=True):
                self.assertAlmostEqual(got, expected, places=12)
            self.assertEqual(manifest["geometry_encoding"], "WKB; bytes preserved from GDAL Arrow source")
            self.assertEqual(manifest["preparation"]["duckdb_memory_limit_mib"], 1024)
            self.assertEqual(manifest["preparation"]["duckdb_threads"], 2)

            rows = pq.read_table(output).to_pylist()
            self.assertEqual([row["Hylak_id"] for row in rows], [10, 11, 12])
            for row in rows:
                source_row = source_rows[row["Hylak_id"]]
                self.assertEqual(row[geometry_name], source_row[geometry_name])
                for name in source_row:
                    if name != geometry_name:
                        self.assertEqual(row[name], source_row[name])
            self.assertIsNone(rows[0]["Lake_name"])
            self.assertTrue(shapely.from_wkb(rows[0][geometry_name]).interiors)

            row_groups = [parquet.metadata.row_group(i) for i in range(parquet.metadata.num_row_groups)]
            self.assertEqual(len(row_groups), 3)
            for group, expected_id in zip(row_groups, [10, 11, 12], strict=True):
                stats = group.column(parquet.schema.names.index("Hylak_id")).statistics
                self.assertEqual((stats.min, stats.max), (expected_id, expected_id))
            metadata = json.loads(parquet.schema_arrow.metadata[b"geo"])
            self.assertEqual(metadata["version"], "1.1.0")
            self.assertEqual(metadata["primary_column"], geometry_name)
            self.assertEqual(metadata["columns"][geometry_name]["encoding"], "WKB")
            crs_metadata = metadata["columns"][geometry_name]["crs"]
            self.assertEqual(CRS.from_json_dict(crs_metadata).to_epsg(), 4326)
            self.assertIn("coordinate_system", crs_metadata)
            self.assertEqual(metadata["columns"][geometry_name]["geometry_types"], ["Polygon"])

            # Two ID lookups exercise footer min/max statistics without a
            # global scan; both selected features retain their source values.
            connection = duckdb.connect()
            try:
                for lake_id in (10, 12):
                    fetched = connection.execute(
                        "SELECT Hylak_id, Lake_name FROM read_parquet(?) WHERE Hylak_id = ?",
                        [str(output), lake_id],
                    ).fetchall()
                    self.assertEqual(len(fetched), 1)
                    self.assertEqual(fetched[0][0], lake_id)
            finally:
                connection.close()

    def test_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(root, [10, 10, 12])
            with self.assertRaisesRegex(ValueError, "not unique"):
                self._convert(source, root, [10, 11, 12])

    def test_missing_id_is_rejected_after_streamed_sort(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(root, [10, 12])
            with self.assertRaisesRegex(ValueError, "ID range mismatch"):
                converter.convert(
                    source,
                    root / "hydrolakes.parquet",
                    root / "private-staging",
                    expected_count=2,
                    expected_min_id=10,
                    expected_max_id=11,
                    batch_size=2,
                    stage_target_bytes=1,
                    output_target_bytes=1,
                )

    def test_sort_configuration_is_bounded_before_input_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for kwargs, message in [
                ({"sort_memory_mib": 127}, "128 through 4096"),
                ({"sort_memory_mib": 4097}, "128 through 4096"),
                ({"sort_threads": 0}, "1 through 2"),
                ({"sort_threads": 3}, "1 through 2"),
            ]:
                with self.subTest(kwargs=kwargs):
                    with self.assertRaisesRegex(ValueError, message):
                        converter.convert(
                            root / "input-that-must-not-be-opened.zip",
                            root / "output.parquet",
                            root / "private-staging",
                            expected_count=1,
                            expected_min_id=1,
                            expected_max_id=1,
                            **kwargs,
                        )
            self.assertFalse((root / "private-staging").exists())


if __name__ == "__main__":
    unittest.main()
