"""publication.catalog.primary_geometry: name a GeoParquet asset's geometry column."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_catalog as pc


def collection():
    return {
        "assets": {
            "lakes": {"href": "lakes.parquet", "type": "application/vnd.apache.parquet", "roles": ["data"]},
            "tiles": {"href": "lakes.pmtiles", "type": "application/vnd.pmtiles", "roles": ["visual"]},
        },
        "table:columns": [{"name": "id", "type": "int64", "asset": "lakes"},
                          {"name": "wkb_geometry", "type": "binary", "asset": "lakes"}],
    }


def record(names):
    return {"publication": {"catalog": {"primary_geometry": names}}}


class PrimaryGeometryTest(unittest.TestCase):
    def test_sets_column_on_asset(self):
        out = collection()
        pc._set_primary_geometry(out, "p", record({"lakes": "wkb_geometry"}))
        self.assertEqual(out["assets"]["lakes"]["table:primary_geometry"], "wkb_geometry")
        self.assertNotIn("table:primary_geometry", out["assets"]["tiles"])

    def test_no_setting_changes_nothing(self):
        out = collection()
        pc._set_primary_geometry(out, "p", {"publication": {"catalog": {}}})
        self.assertEqual(out, collection())

    def test_refuses_non_geoparquet_asset(self):
        with self.assertRaisesRegex(ValueError, "no GeoParquet data asset"):
            pc._set_primary_geometry(collection(), "p", record({"tiles": "wkb_geometry"}))

    def test_refuses_unlisted_column(self):
        with self.assertRaisesRegex(ValueError, "not listed"):
            pc._set_primary_geometry(collection(), "p", record({"lakes": "Shape"}))


if __name__ == "__main__":
    unittest.main()
