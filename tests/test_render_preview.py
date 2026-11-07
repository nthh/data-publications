import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pyarrow as pa
import pyarrow.parquet as pq
from shapely import from_wkb
from shapely.geometry import box, shape

from scripts.render_preview import server


class RenderPreviewTests(unittest.TestCase):
    def test_bbox_validation_rejects_malformed_and_out_of_range_queries(self):
        for bbox in ("1,2,3", "0,0,nan,1", "5,0,4,1", "-181,0,-180,1", "0,-91,1,-90"):
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                server.valid_bbox(bbox)
        self.assertEqual(server.valid_bbox("-93,47,-87,50"), [-93, 47, -87, 50])

    def test_inventory_binds_source_file_to_immutable_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / "a.parquet"
            asset.write_bytes(b"fixture")
            digest = hashlib.sha256(b"fixture").hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"assets": [{"asset_id": "fixture", "size_bytes": 7, "sha256": digest, "row_count": 1}]}))
            specs = {"fixture": {"path": asset, "manifest": manifest, "geometry": "geometry", "id": "id", "fields": [], "kind": "point", "label": "fixture"}}
            with mock.patch.object(server, "ASSETS", specs):
                inventory = server.source_inventory(verify_hashes=True)
                self.assertEqual(inventory["fixture"]["sha256"], digest)
                asset.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "sha256 differs"):
                    server.source_inventory(verify_hashes=True)

    def test_query_counts_all_bbox_matches_caps_by_stable_id_and_clips_display_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.parquet"
            inside = box(0, 0, 2, 2)
            touching = box(3, 0, 4, 1)
            outside = box(20, 20, 21, 21)
            geometries = [inside, touching, outside]
            bbox_type = pa.struct([("xmin", pa.float64()), ("ymin", pa.float64()), ("xmax", pa.float64()), ("ymax", pa.float64())])
            table = pa.table({
                "Hylak_id": pa.array([9, 2, 1], type=pa.int64()),
                "Lake_name": ["inside", "touching", "outside"],
                "Lake_area": pa.array([4.0, 1.0, 1.0]),
                "Country": ["A", "A", "B"],
                "wkb_geometry": [geometry.wkb for geometry in geometries],
                "bbox": pa.array([
                    {"xmin":g.bounds[0], "ymin":g.bounds[1], "xmax":g.bounds[2], "ymax":g.bounds[3]}
                    for g in geometries
                ], type=bbox_type),
            })
            pq.write_table(table, path)
            specs = {"fixture": {"path": path, "manifest": path, "geometry": "wkb_geometry", "id": "Hylak_id", "fields": ["Lake_name", "Lake_area", "Country"], "kind": "polygon", "label": "fixture"}}
            with mock.patch.object(server, "ASSETS", specs), mock.patch.object(server, "MAX_FEATURES", 1):
                result = server.query_asset("fixture", [0, 0, 5, 5], {"fixture": {"sha256": "bound-to-fixture"}})
                self.assertEqual(result["matched_rows"], 2)
                self.assertEqual(result["returned_rows"], 1)
                self.assertTrue(result["capped"])
                self.assertEqual(result["features"][0]["id"], "2")
                self.assertTrue(shape(result["features"][0]["geometry"]).equals(box(3, 0, 4, 1)))
                self.assertTrue(from_wkb(geometries[0].wkb).equals(inside))

                empty = server.query_asset("fixture", [30, 30, 31, 31], {"fixture": {"sha256": "bound-to-fixture"}})
                self.assertEqual(empty["matched_rows"], 0)
                self.assertEqual(empty["returned_rows"], 0)
                self.assertEqual(empty["features"], [])


if __name__ == "__main__":
    unittest.main()
