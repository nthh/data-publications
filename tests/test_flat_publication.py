import copy
import hashlib
import json
import tempfile
import unittest

from scripts.flat_publication import HOSTING_CHECKS, apply_flat_layout, load_flat_layout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def multihash(data: bytes) -> str:
    return "1220" + sha(data)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"
    path.write_bytes(data)
    return data


def fixture(tmp_path, *, extra_file=False):
    dataset_id = "demo"
    owner, product, release = "nthh", "demo-product", "r1"
    parquet = b"PAR1fixture parquet bytes"
    pmtiles = b"PMTilesfixture old bytes"
    revised_pmtiles = b"PMTilesfixture revised metadata bytes"
    old_style = {
        "version": 8,
        "name": "demo style",
        "sources": {"data": {"type": "vector", "url": "https://legacy.test/d1/assets/demo.pmtiles",
                               "attribution": "Original producer; conversion by Folia"}},
        "layers": [{"id": "demo", "type": "fill", "source": "data", "source-layer": "demo", "paint": {"fill-color": "#123456"}}],
    }
    old_style_bytes = json.dumps(old_style, sort_keys=True, indent=2).encode() + b"\n"
    new_style = copy.deepcopy(old_style)
    new_style["sources"]["data"]["url"] = "pmtiles://https://data.source.coop/nthh/demo-product/demo.pmtiles"
    new_style["sources"]["data"]["attribution"] = "Corrected source attribution CC BY 4.0"
    new_style_bytes = json.dumps(new_style, sort_keys=True, indent=2).encode() + b"\n"
    (tmp_path / "catalog/demo/display/d1/styles/demo.json").parent.mkdir(parents=True)
    (tmp_path / "catalog/demo/display/d1/styles/demo.json").write_bytes(new_style_bytes)
    proof = {
        "status": "passed", "source_sha256": sha(pmtiles), "target_sha256": sha(revised_pmtiles),
        "source_size_bytes": len(pmtiles), "target_size_bytes": len(revised_pmtiles),
        "geometry_payload_unchanged": True,
        "encoded_sections": {name: {"bytes": 1, "identical": True, "sha256": sha(b"x")}
                             for name in ("root", "leaf", "tile_data")},
    }
    proof_bytes = dump(tmp_path / "research/demo-pmtiles-proof.json", proof)
    files = [
        {"filename": "demo.parquet", "asset_id": "data", "source_href": "https://legacy.test/r1/assets/demo.parquet",
         "source_sha256": sha(parquet), "source_size_bytes": len(parquet), "sha256": sha(parquet),
         "size_bytes": len(parquet), "media_type": "application/vnd.apache.parquet", "roles": ["data"],
         "title": "Demo data", "operation": "copy"},
        {"filename": "demo.pmtiles", "asset_id": "tiles", "source_href": "https://legacy.test/d1/assets/demo.pmtiles",
         "source_sha256": sha(pmtiles), "source_size_bytes": len(pmtiles), "sha256": sha(revised_pmtiles),
         "size_bytes": len(revised_pmtiles), "media_type": "application/vnd.pmtiles", "roles": ["visual"],
         "title": "Demo tiles", "operation": "pmtiles_attribution",
         "transformation_proof": {"path": "research/demo-pmtiles-proof.json", "sha256": sha(proof_bytes)}},
        {"filename": "demo-style.json", "asset_id": "style", "source_href": "display/d1/styles/demo.json",
         "source_sha256": sha(old_style_bytes), "source_size_bytes": len(old_style_bytes),
         "sha256": sha(new_style_bytes), "size_bytes": len(new_style_bytes),
         "media_type": "application/vnd.mapbox.style+json", "roles": ["style", "default"],
         "title": "Demo style", "operation": "rewrite_style", "local_path": "catalog/demo/display/d1/styles/demo.json"},
    ]
    if extra_file:
        generated = b"# compact README\n"
        (tmp_path / "datasets/demo/flat-readme.md").parent.mkdir(parents=True)
        (tmp_path / "datasets/demo/flat-readme.md").write_bytes(generated)
        files.append({"filename": "README.md", "asset_id": None, "source_href": None,
                      "source_sha256": None, "source_size_bytes": None, "sha256": sha(generated),
                      "size_bytes": len(generated), "media_type": "text/markdown", "roles": ["documentation"],
                      "title": "Consumer README", "operation": "generated", "local_path": "datasets/demo/flat-readme.md"})
    layout_id = "flat-20261111"
    manifest = {"schema_version": 1, "dataset_id": dataset_id, "layout_id": layout_id,
                "owner": owner, "product_id": product, "source_release": release,
                "updated": "2026-11-11T12:00:00Z", "files": files}
    manifest_bytes = dump(tmp_path / "research/demo-flat-layout.json", manifest)
    report = {"schema_version": 1, "dataset_id": dataset_id, "layout_id": layout_id,
              "manifest_sha256": sha(manifest_bytes), "status": "passed",
              "checks": {check: "passed" for check in HOSTING_CHECKS},
              "files": [{"filename": item["filename"], "sha256": item["sha256"],
                         "size_bytes": item["size_bytes"], "status": "verified"} for item in files]}
    report_bytes = dump(tmp_path / "research/demo-flat-hosting.json", report)
    record = {"id": dataset_id, "publication": {"release": release, "source_coop": {
        "owner": owner, "product_id": product, "attribution": "Corrected source attribution", "license_note": "CC BY 4.0",
        "flat_layout": {"manifest_path": "research/demo-flat-layout.json", "manifest_sha256": sha(manifest_bytes),
                        "hosting_report_path": "research/demo-flat-hosting.json", "hosting_report_sha256": sha(report_bytes)},
    }}}
    collection = {"id": dataset_id, "updated": "2026-11-01T00:00:00Z", "assets": {
        "data": {"href": files[0]["source_href"], "type": files[0]["media_type"], "roles": files[0]["roles"],
                 "title": files[0]["title"], "file:checksum": multihash(parquet), "file:size": len(parquet)},
        "tiles": {"href": files[1]["source_href"], "type": files[1]["media_type"], "roles": files[1]["roles"],
                  "title": files[1]["title"], "file:checksum": multihash(pmtiles), "file:size": len(pmtiles)},
        "style": {"href": files[2]["source_href"], "type": files[2]["media_type"], "roles": files[2]["roles"],
                  "title": files[2]["title"], "file:checksum": multihash(old_style_bytes), "file:size": len(old_style_bytes)},
        "support": {"href": "https://legacy.test/r1/provenance.json", "type": "application/json", "roles": ["metadata"],
                    "title": "Provenance", "file:checksum": multihash(b"proof"), "file:size": 5},
    }, "links": [
        {"rel": "pmtiles", "href": files[1]["source_href"], "type": "application/vnd.pmtiles"},
        {"rel": "style", "href": files[2]["source_href"], "type": "application/vnd.mapbox.style+json"},
        {"rel": "via", "href": "https://legacy.test/r1/collection.json"},
    ]}
    tree = {"demo/display/d1/styles/demo.json": old_style_bytes}
    return record, collection, tree, manifest


class FlatPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        from pathlib import Path
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_applies_flat_parquet_pmtiles_and_style_but_preserves_version_and_provenance(self):
        record, collection, tree, manifest = fixture(self.root, extra_file=True)
        before = copy.deepcopy(collection)
        result = apply_flat_layout(self.root, record, collection, tree)
        self.assertEqual(result, manifest)
        self.assertEqual(collection["updated"], manifest["updated"])
        self.assertEqual(collection["assets"]["data"]["href"], "https://data.source.coop/nthh/demo-product/demo.parquet")
        self.assertEqual(collection["assets"]["tiles"]["href"], "https://data.source.coop/nthh/demo-product/demo.pmtiles")
        self.assertEqual(collection["assets"]["tiles"]["file:checksum"], "1220" + manifest["files"][1]["sha256"])
        self.assertEqual(collection["assets"]["tiles"]["file:size"], manifest["files"][1]["size_bytes"])
        self.assertEqual(collection["assets"]["style"]["href"], before["assets"]["style"]["href"])
        self.assertNotEqual(collection["assets"]["style"]["file:checksum"], before["assets"]["style"]["file:checksum"])
        self.assertEqual(collection["assets"]["support"], before["assets"]["support"])
        self.assertEqual(collection["links"][0]["href"], "https://data.source.coop/nthh/demo-product/demo.pmtiles")
        self.assertEqual(collection["links"][1]["href"], before["links"][1]["href"])
        self.assertEqual(collection["links"][2], before["links"][2])
        self.assertEqual(tree["demo/display/d1/styles/demo.json"], (self.root / "catalog/demo/display/d1/styles/demo.json").read_bytes())
        self.assertIn("pmtiles://https://data.source.coop/nthh/demo-product/demo.pmtiles", tree["demo/display/d1/styles/demo.json"].decode())
        self.assertNotIn("demo/demo-style.json", tree)
        self.assertNotIn("demo/README.md", tree)
        self.assertEqual(record["publication"]["release"], "r1")

    def test_unpinned_record_has_no_flat_layout(self):
        self.assertIsNone(load_flat_layout(self.root, {"id": "demo", "publication": {"source_coop": {}}}))

    def test_rejects_bad_manifest_pin_and_release(self):
        record, collection, tree, _ = fixture(self.root)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
            apply_flat_layout(self.root, record, collection, tree)
        self.tearDown()
        self.setUp()
        record, collection, tree, _ = fixture(self.root)
        record["publication"]["release"] = "r2"
        with self.assertRaisesRegex(ValueError, "identity/release mismatch"):
            apply_flat_layout(self.root, record, collection, tree)
        self.tearDown()
        self.setUp()
        record, collection, tree, manifest = fixture(self.root)
        manifest["files"][0]["source_href"] = "https://wrong.test/data.parquet"
        manifest_bytes = dump(self.root / "research/demo-flat-layout.json", manifest)
        layout_pin = record["publication"]["source_coop"]["flat_layout"]
        layout_pin["manifest_sha256"] = sha(manifest_bytes)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["manifest_sha256"] = sha(manifest_bytes)
        report_bytes = dump(report_path, report)
        layout_pin["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "source href changed"):
            apply_flat_layout(self.root, record, collection, tree)

    def test_rejects_traversal_flat_names_and_unverified_hosting_file(self):
        record, collection, tree, manifest = fixture(self.root)
        manifest["files"][0]["filename"] = "../escape.parquet"
        data = dump(self.root / "research/demo-flat-layout.json", manifest)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = sha(data)
        with self.assertRaisesRegex(ValueError, "Unsafe flat filename"):
            load_flat_layout(self.root, record)
        self.tearDown()
        self.setUp()
        record, collection, tree, _ = fixture(self.root)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["files"][0]["status"] = "pending"
        report_bytes = dump(report_path, report)
        record["publication"]["source_coop"]["flat_layout"]["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "hosted proof mismatch"):
            apply_flat_layout(self.root, record, collection, tree)

    def test_rejects_unmapped_assets_and_nonidentity_copy(self):
        record, collection, tree, manifest = fixture(self.root)
        manifest["files"].pop(0)
        data = dump(self.root / "research/demo-flat-layout.json", manifest)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = sha(data)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["manifest_sha256"] = sha(data)
        report["files"] = [item for item in report["files"] if item["filename"] != "demo.parquet"]
        report_bytes = dump(report_path, report)
        record["publication"]["source_coop"]["flat_layout"]["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "omits Collection assets"):
            apply_flat_layout(self.root, record, collection, tree)
        self.tearDown()
        self.setUp()
        record, collection, tree, manifest = fixture(self.root)
        manifest["files"][0]["sha256"] = "a" * 64
        data = dump(self.root / "research/demo-flat-layout.json", manifest)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = sha(data)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["manifest_sha256"] = sha(data)
        report["files"][0]["sha256"] = "a" * 64
        report_bytes = dump(report_path, report)
        record["publication"]["source_coop"]["flat_layout"]["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "copy operation must preserve bytes"):
            apply_flat_layout(self.root, record, collection, tree)

    def test_rejects_style_rendering_change(self):
        record, collection, tree, manifest = fixture(self.root)
        rewritten = json.loads((self.root / "catalog/demo/display/d1/styles/demo.json").read_text())
        rewritten["layers"][0]["paint"]["fill-color"] = "#ffffff"
        rewritten_bytes = dump(self.root / "catalog/demo/display/d1/styles/demo.json", rewritten)
        manifest["files"][2]["sha256"] = sha(rewritten_bytes)
        manifest["files"][2]["size_bytes"] = len(rewritten_bytes)
        data = dump(self.root / "research/demo-flat-layout.json", manifest)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = sha(data)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["manifest_sha256"] = sha(data)
        report["files"][2].update(sha256=sha(rewritten_bytes), size_bytes=len(rewritten_bytes))
        report_bytes = dump(report_path, report)
        record["publication"]["source_coop"]["flat_layout"]["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "changes rendering fields"):
            apply_flat_layout(self.root, record, collection, tree)

    def test_rejects_pmtiles_transform_proof_that_does_not_bind_target(self):
        record, _, _, manifest = fixture(self.root)
        proof_path = self.root / "research/demo-pmtiles-proof.json"
        proof = json.loads(proof_path.read_text())
        proof["geometry_payload_unchanged"] = False
        proof_bytes = dump(proof_path, proof)
        manifest["files"][1]["transformation_proof"]["sha256"] = sha(proof_bytes)
        data = dump(self.root / "research/demo-flat-layout.json", manifest)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = sha(data)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["manifest_sha256"] = sha(data)
        report_bytes = dump(report_path, report)
        record["publication"]["source_coop"]["flat_layout"]["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "transformation proof does not bind"):
            load_flat_layout(self.root, record)

    def test_rejects_pmtiles_proof_without_actual_section_comparison(self):
        record, _, _, manifest = fixture(self.root)
        proof_path = self.root / "research/demo-pmtiles-proof.json"
        proof = json.loads(proof_path.read_text())
        proof["encoded_sections"]["tile_data"]["identical"] = False
        proof_bytes = dump(proof_path, proof)
        manifest["files"][1]["transformation_proof"]["sha256"] = sha(proof_bytes)
        data = dump(self.root / "research/demo-flat-layout.json", manifest)
        record["publication"]["source_coop"]["flat_layout"]["manifest_sha256"] = sha(data)
        report_path = self.root / "research/demo-flat-hosting.json"
        report = json.loads(report_path.read_text())
        report["manifest_sha256"] = sha(data)
        report_bytes = dump(report_path, report)
        record["publication"]["source_coop"]["flat_layout"]["hosting_report_sha256"] = sha(report_bytes)
        with self.assertRaisesRegex(ValueError, "no verified tile_data bytes"):
            load_flat_layout(self.root, record)


if __name__ == "__main__":
    unittest.main()
