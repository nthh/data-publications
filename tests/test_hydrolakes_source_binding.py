"""Focused tests for HydroLAKES validator source-archive binding."""

from __future__ import annotations

import hashlib
import importlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import geopandas as gpd
from shapely.geometry import Polygon


ROOT = Path(__file__).resolve().parents[1]
HYDROLAKES_DIR = ROOT / "datasets" / "hydrolakes"
if str(HYDROLAKES_DIR) not in sys.path:
    sys.path.insert(0, str(HYDROLAKES_DIR))

converter = importlib.import_module("convert")
validator = importlib.import_module("validate")


class HydroLAKESSourceBindingTests(unittest.TestCase):
    def _write_shapefile(self, directory: Path) -> Path:
        geometry = [
            Polygon(
                [
                    (-90.0 + i * 0.02, 46.0),
                    (-89.99 + i * 0.02, 46.0),
                    (-89.99 + i * 0.02, 46.01),
                    (-90.0 + i * 0.02, 46.01),
                    (-90.0 + i * 0.02, 46.0),
                ]
            )
            for i in range(3)
        ]
        frame = gpd.GeoDataFrame(
            {
                "Hylak_id": [1, 2, 3],
                "Lake_name": ["Lake 1", None, "Lake 3"],
                "Lake_area": [0.25, 1.5, 7.0],
            },
            geometry=geometry,
            crs="EPSG:4326",
        )
        path = directory / "HydroLAKES_polys_v10.shp"
        frame.to_file(path, driver="ESRI Shapefile", engine="pyogrio")
        return path

    def _write_source_zip(self, directory: Path) -> Path:
        source_dir = directory / "source-members"
        source_dir.mkdir()
        self._write_shapefile(source_dir)
        archive = directory / "HydroLAKES_polys_v10_shp.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for member in sorted(source_dir.glob("HydroLAKES_polys_v10.*")):
                output.write(member, member.name)
        return archive

    def _convert(self, source: Path, root: Path) -> Path:
        output = root / "hydrolakes.parquet"
        converter.convert(
            source,
            output,
            root / "private-staging",
            expected_count=3,
            expected_min_id=1,
            expected_max_id=3,
            batch_size=2,
            stage_target_bytes=1,
            output_target_bytes=1,
        )
        return output

    def test_directory_source_is_rejected_before_source_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir = root / "extracted-source"
            source_dir.mkdir()
            self._write_shapefile(source_dir)
            data = self._convert(source_dir, root)

            with mock.patch.object(validator.pyogrio, "open_arrow", wraps=validator.pyogrio.open_arrow) as open_arrow:
                with self.assertRaisesRegex(ValueError, "pinned archive file"):
                    validator.validate(
                        source_dir,
                        data,
                        expected_count=3,
                        source_sha="0" * 64,
                        source_bytes=1,
                    )

            open_arrow.assert_not_called()

    def test_pinned_archive_file_is_hashed_and_validates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._write_source_zip(root)
            source_bytes = source.stat().st_size
            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            data = self._convert(source, root)

            report = validator.validate(
                source,
                data,
                expected_count=3,
                source_sha=source_sha,
                source_bytes=source_bytes,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["source_sha256"], source_sha)
            self.assertEqual(report["source_bytes"], source_bytes)
            self.assertEqual(report["rows"], 3)

    def test_archive_pin_mismatch_is_rejected_before_source_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._write_source_zip(root)

            with mock.patch.object(validator.pyogrio, "open_arrow", wraps=validator.pyogrio.open_arrow) as open_arrow:
                with self.assertRaisesRegex(ValueError, "Pinned source bytes changed"):
                    validator.validate(
                        source,
                        root / "not-opened.parquet",
                        expected_count=3,
                        source_sha="0" * 64,
                        source_bytes=source.stat().st_size,
                    )

            open_arrow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
