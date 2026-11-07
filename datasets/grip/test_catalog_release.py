"""Focused checks for the portable GRIP4 catalog release contract."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import build_catalog, _stac_bbox, resolve_style_pmtiles  # noqa: E402
from check_catalog import check_catalog  # noqa: E402


class CatalogReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = self.root / "grip"
        (folder / "data").mkdir(parents=True)
        (folder / "data" / "region=1.parquet").write_bytes(b"small test parquet placeholder")
        (folder / "grip.pmtiles").write_bytes(b"PMTiles\x03small test tile payload")
        (folder / "attribute-codes.json").write_text("{}\n")
        (folder / "original-attribute-dictionary.xlsx").write_bytes(b"tiny test workbook placeholder")
        self.config = {
            "id": "grip", "title": "GRIP4 global roads — 2018",
            "source_doi": "10.5281/zenodo.6420961",
            "source_url": "https://zenodo.org/api/records/6420961/files/GRIP4_global_vector_fgdb.zip/content",
            "source_sha256": "a" * 64, "source_size": 2334355294,
            "license": "CC-BY-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "paper_doi": "10.1088/1748-9326/aabd42", "release": "grip4-2018-local-r1",
            "metadata_timestamp": "2026-10-30T00:00:00Z",
            "portolan_schema": "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json",
        }
        self.summary = {
            "rows": 3, "bbox": [-1.0, -2.0, 3.0, 4.0],
            "fields": [{"name": "road_id", "type": "int64", "description": "Source road identifier"}],
            "regions": {"1": 3}, "null_counts": {"road_id": 0},
            "geometry_types": ["MultiLineString"],
            "display": {"configuration": {"minzoom": 0, "maxzoom": 14}, "counts": {"features": 2}, "limits": ["Thinned"], "layer": "roads"},
            "road_classes": {"1": 2}, "invalid_source_geometries_preserved": 0, "vertices": 6,
            "preview_lines": [[[0, 0], [1, 1]]],
        }
        build_catalog(self.root, self.summary, self.config, "testrevision")

    def tearDown(self):
        self.temp.cleanup()

    def _collection(self):
        path = self.root / "grip" / "collection.json"
        return path, json.loads(path.read_text())

    def _save_collection(self, path, collection):
        path.write_text(json.dumps(collection, indent=2) + "\n")

    def test_built_release_passes_and_preserves_required_metadata(self):
        result = check_catalog(self.root)
        self.assertEqual(result["status"], "passed")
        collection = json.loads((self.root / "grip" / "collection.json").read_text())
        self.assertEqual(collection["providers"][-1]["name"], "Folia")
        self.assertEqual(collection["providers"][-1]["roles"], ["processor", "host"])
        self.assertIn("style", collection["assets"])
        self.assertIn("attribute-codes", collection["assets"])
        self.assertIn("original-attribute-dictionary", collection["assets"])
        self.assertEqual(collection["assets"]["thumbnail"]["type"], "image/png")
        self.assertTrue((self.root / "grip" / "thumbnail.png").is_file())
        catalog = json.loads((self.root / "catalog.json").read_text())
        links = {(link["rel"], link["href"], link.get("type")) for link in catalog["links"]}
        self.assertIn(("agents", "AGENTS.md", "text/markdown"), links)
        self.assertIn(("describedby", "README.md", "text/markdown"), links)
        self.assertEqual(catalog["stac_extensions"], ["https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"])
        self.assertEqual(len(collection["providers"]), 2)
        self.assertIn("licensor", collection["providers"][0]["roles"])
        self.assertIn("producer", collection["providers"][0]["roles"])

    def test_rejects_unsafe_relative_asset_path(self):
        path, collection = self._collection()
        collection["assets"]["data-001"]["href"] = "../../outside.parquet"
        self._save_collection(path, collection)
        with self.assertRaisesRegex(ValueError, "escapes release root"):
            check_catalog(self.root)

    def test_rejects_missing_local_link(self):
        path, collection = self._collection()
        collection["links"].append({"rel": "describedby", "href": "missing.md", "type": "text/markdown"})
        self._save_collection(path, collection)
        with self.assertRaisesRegex(ValueError, "Missing linked file"):
            check_catalog(self.root)

    def test_rejects_wrong_asset_hash(self):
        path, collection = self._collection()
        collection["assets"]["data-001"]["file:checksum"] = "1220" + "0" * 64
        self._save_collection(path, collection)
        with self.assertRaisesRegex(ValueError, "Wrong file:checksum"):
            check_catalog(self.root)

    def test_rejects_nonfinal_or_ambiguous_host_provider(self):
        path, collection = self._collection()
        folia = collection["providers"].pop()
        collection["providers"].insert(0, folia)
        self._save_collection(path, collection)
        with self.assertRaisesRegex(ValueError, "host provider must appear last"):
            check_catalog(self.root)

    def test_bbox_roundoff_is_clamped_only_for_stac_extent(self):
        raw_bbox = [-180.0000000000001, -90.0, 180.0000000000001, 90.0]
        self.assertEqual(_stac_bbox(raw_bbox), [-180.0, -90.0, 180.0, 90.0])
        self.summary["bbox"] = raw_bbox
        build_catalog(self.root, self.summary, self.config, "testrevision")
        quality = json.loads((self.root / "grip" / "quality.json").read_text())
        collection = json.loads((self.root / "grip" / "collection.json").read_text())
        self.assertEqual(quality["bbox"], raw_bbox)
        self.assertEqual(quality["stac_extent_bbox"], [-180.0, -90.0, 180.0, 90.0])
        self.assertEqual(collection["extent"]["spatial"]["bbox"], [[-180.0, -90.0, 180.0, 90.0]])
        self.assertIn("analytic coordinates", quality["bbox_extent_note"])

    def test_bbox_overshoot_above_tolerance_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "geographic limits"):
            _stac_bbox([-180.00000002, -90.0, 180.0, 90.0])

    def test_relative_style_source_resolves_to_checked_pmtiles_asset(self):
        style_path = self.root / "grip" / "styles" / "grip.json"
        style = json.loads(style_path.read_text())
        self.assertEqual(style["sources"]["grip"]["url"], "../grip.pmtiles")
        resolved = resolve_style_pmtiles(style_path, style["sources"]["grip"]["url"], self.root)
        self.assertEqual(resolved, (self.root / "grip" / "grip.pmtiles").resolve())
        self.assertTrue(resolved.read_bytes().startswith(b"PMTiles\x03"))
        with self.assertRaisesRegex(ValueError, "escapes release root"):
            resolve_style_pmtiles(style_path, "../../../outside.pmtiles", self.root)


if __name__ == "__main__":
    unittest.main()
