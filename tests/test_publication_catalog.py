"""Focused offline regressions for the publication metadata boundary."""
from __future__ import annotations

from argparse import Namespace
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import quote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_catalog as pc


PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    path.write_bytes(data)
    return data


class PublicationCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "datasets/demo").mkdir(parents=True)
        (self.root / "schemas").mkdir()
        (self.root / "schemas/dataset.schema.json").write_bytes((ROOT / "schemas/dataset.schema.json").read_bytes())
        self.record_path = self.root / "datasets/demo/dataset.yaml"
        self.record = {"schema_version": 1, "id": "demo", "title": "Demo dataset",
                       "triage": {"decision": "publish_conversion", "priority": "normal"},
                       "intake": {"kind": "producer", "reference_url": "https://example.org/demo", "added_on": "2026-10-31"},
                       "publication": {"status": "prepared", "release": "r1"}}
        self.config = {"schema_version": 1,
                       "catalog": {"id": "demo-catalog", "title": "Demo catalog", "description": "Demo."},
                       "navigation": {"repository_url": None, "issues_url": None, "hosting_url": None,
                                      "browser_url_template": None},
                       "publish": {"destination": None, "public_base": None, "region": None}}
        self.write_record()
        self.write_config()

    def tearDown(self):
        self.temp.cleanup()

    def write_record(self):
        self.record_path.write_text(yaml.safe_dump(self.record, sort_keys=False))

    def write_config(self):
        (self.root / "catalog.publish.yaml").write_text(yaml.safe_dump(self.config, sort_keys=False))

    def make_package(self, *, nested=False, style_name="map.json") -> Path:
        package = self.root / "package"
        package.mkdir()
        collection_rel = "grwl/collection.json" if nested else "collection.json"
        prefix = "grwl/" if nested else ""
        readme_rel = prefix + "README.md"
        agents_rel = prefix + "AGENTS.md"
        style_rel = prefix + "styles/" + style_name
        thumbnail_rel = prefix + "thumbnail.png"
        analytic_rel = prefix + "data.parquet"
        style_href = "styles/" + style_name
        (package / readme_rel).parent.mkdir(parents=True, exist_ok=True)
        (package / readme_rel).write_text("# Original package notes\n\nLicense: CC-BY-4.0.\n")
        (package / agents_rel).write_text("Original package instructions.\n")
        (package / thumbnail_rel).write_bytes(PNG)
        style = {"version": 8, "sources": {"one": {"url": "pmtiles://../tiles.pmtiles" if nested else "pmtiles://tiles.pmtiles"},
                                           "two": {"tiles": ["../tiles/{z}/{x}/{y}.pbf"]}},
                 "sprite": "../sprite", "glyphs": "../fonts/{fontstack}/{range}.pbf"}
        style_data = dump(package / style_rel, style)
        collection = {"stac_version": "1.1.0", "stac_extensions": [pc.PORTOLAN_SCHEMA,
                      "https://stac-extensions.github.io/file/v2.1.0/schema.json",
                      "https://stac-extensions.github.io/version/v1.2.0/schema.json"],
                      "type": "Collection", "id": "demo", "title": "Old title", "description": "Synthetic collection.",
                      "license": "CC-BY-4.0", "version": "r1", "created": "2026-10-31T00:00:00Z",
                      "updated": "2026-10-31T00:00:00Z",
                      "extent": {"spatial": {"bbox": [[0, 0, 0, 0]]}, "temporal": {"interval": [[None, None]]}},
                      "providers": [{"name": "Demo producer", "roles": ["producer", "licensor"], "url": "https://example.org/"},
                                    {"name": "Folia", "roles": ["host", "processor"], "url": "https://folia.sh"}],
                      "links": [{"rel": "root", "href": "../catalog.json" if nested else "catalog.json", "type": "application/json"},
                                {"rel": "parent", "href": "../catalog.json" if nested else "catalog.json", "type": "application/json"},
                                {"rel": "self", "href": "collection.json", "type": "application/json"},
                                {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
                                {"rel": "agents", "href": "AGENTS.md", "type": "text/markdown"},
                                {"rel": "style", "href": style_href, "type": "application/json"},
                                {"rel": "thumbnail", "href": "thumbnail.png", "type": "image/png"},
                                {"rel": "via", "href": "https://example.org/source", "type": "text/html"},
                                {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html"}],
                      "assets": {"data": {"href": "data.parquet", "type": "application/vnd.apache.parquet", "roles": ["data"],
                                          "file:size": 3, "file:checksum": "1220" + sha(b"abc")},
                                 "style": {"href": style_href, "type": "application/json", "roles": ["style"],
                                           "file:size": len(style_data), "file:checksum": "1220" + sha(style_data)},
                                 "thumbnail": {"href": "thumbnail.png", "type": "image/png", "roles": ["thumbnail"],
                                               "file:size": len(PNG), "file:checksum": "1220" + sha(PNG)}}}
        collection_data = dump(package / collection_rel, collection)
        if nested:
            dump(package / "catalog.json", {"type": "Catalog", "links": [{"rel": "child", "href": collection_rel}]})
        assets = {rel: {"sha256": sha((package / rel).read_bytes()), "size_bytes": (package / rel).stat().st_size}
                  for rel in (collection_rel, readme_rel, agents_rel, style_rel, thumbnail_rel)}
        if nested:
            assets["catalog.json"] = {"sha256": sha((package / "catalog.json").read_bytes()),
                                      "size_bytes": (package / "catalog.json").stat().st_size}
        assets[analytic_rel] = {"sha256": sha(b"abc"), "size_bytes": 3}
        manifest = {"dataset": "demo", "release": "r1", "assets": assets}
        manifest_data = dump(package / "manifest.json", manifest)
        dump(package / "receipt.json", {"manifest_sha256": sha(manifest_data)})
        self.record["publication"].update(manifest_path="package/manifest.json", manifest_sha256=sha(manifest_data),
                                          release_receipt_path="package/receipt.json")
        self.write_record()
        return package

    def export(self, package: Path, *, name="snapshot") -> Path:
        output = self.root / "datasets/demo" / name
        pc.export_metadata("demo", package, output, self.root)
        snap_data = (output / "snapshot.json").read_bytes()
        self.record["publication"]["catalog"] = {"snapshot_path": f"datasets/demo/{name}/snapshot.json",
                                                    "snapshot_sha256": sha(snap_data),
                                                    "package_base_url": "https://data.example.org/demo/r1/"}
        self.write_record()
        return output

    def publish(self):
        self.record["publication"]["status"] = "published"
        self.record["publication"]["source_coop"] = {
            "owner": "nthh", "owner_status": "confirmed", "product_id": "demo",
            "account_verification": None, "tags": [], "limitations": [], "supplements": [],
            "title": "Demo", "summary": "Demo product", "license_note": "CC0-1.0",
            "attribution": "Demo producer", "temporal_note": "Static test fixture",
        }
        report = {"schema_version": 1, "dataset_id": "demo", "release": "r1",
                  "package_manifest_sha256": self.record["publication"]["manifest_sha256"],
                  "package_base_url": "https://data.example.org/demo/r1/",
                  "checked_at": "2026-10-31T12:00:00Z", "status": "passed",
                  "checks": {key: "passed" for key in pc.PASSING_CHECKS}}
        raw = dump(self.root / "datasets/demo/hosting.json", report)
        self.record["publication"]["catalog"].update(hosting_report_path="datasets/demo/hosting.json",
                                                        hosting_report_sha256=sha(raw))
        self.config["navigation"] = {"repository_url": "https://code.example.org/repo",
                                      "issues_url": "https://code.example.org/repo/issues",
                                      "hosting_url": "https://data.example.org",
                                      "browser_url_template": "https://browser.example.org/?url={catalog_url}"}
        self.config["publish"] = {"destination": "s3://bucket/prefix/",
                                  "public_base": "https://catalog.example.org/root/", "region": "test-1"}
        self.write_record()
        self.write_config()

    def add_hosted_display(self, *, layer_count=1):
        display_release = "display-r1"
        package_dir = self.root / "datasets/demo/display" / display_release
        files = {}
        assets = []
        for index in range(layer_count):
            asset_id = f"demo-layer-{index + 1}"
            tile_path = f"assets/{asset_id}.pmtiles"
            style_path = f"styles/{asset_id}.json"
            style = {"version": 8,
                     "sources": {"data": {"type": "vector", "url": f"pmtiles://../{tile_path}"}},
                     "layers": [{"id": asset_id, "type": "fill", "source": "data",
                                 "source-layer": asset_id,
                                 "paint": {"fill-color": "#123456"}}]}
            style_data = dump(package_dir / style_path, style)
            tile_data = f"fixture-pmtiles-{asset_id}".encode()
            tile_hash = sha(tile_data)
            style_hash = sha(style_data)
            files[tile_path] = {"sha256": tile_hash, "size_bytes": len(tile_data)}
            files[style_path] = {"sha256": style_hash, "size_bytes": len(style_data)}
            assets.append({"id": asset_id, "title": f"Demo layer {index + 1}",
                           "path": tile_path, "sha256": tile_hash, "size_bytes": len(tile_data),
                           "style_path": style_path, "source_layer": asset_id})
        manifest = {"schema_version": 1, "dataset_id": "demo", "display_release": display_release,
                    "analytic_release": "r1", "status": "prepared", "files": files, "assets": assets}
        manifest_data = dump(package_dir / "manifest.json", manifest)
        self.record["publication"]["display"] = {
            "release": display_release,
            "manifest_path": f"datasets/demo/display/{display_release}/manifest.json",
            "manifest_sha256": sha(manifest_data),
            "package_base_url": "https://display.example.org/demo/display-r1/",
            "hosting_report_path": "datasets/demo/hosting.json",
        }
        report_path = self.root / "datasets/demo/hosting.json"
        report = json.loads(report_path.read_text())
        report.update({"display_release": display_release,
                       "display_manifest_sha256": sha(manifest_data),
                       "display_package_base_url": "https://display.example.org/demo/display-r1/"})
        report_data = dump(report_path, report)
        self.record["publication"]["display"]["hosting_report_sha256"] = sha(report_data)
        self.record["publication"]["catalog"]["hosting_report_sha256"] = sha(report_data)
        self.write_record()

    def test_duplicate_yaml_metadata_keys_are_rejected(self):
        original = self.record_path.read_text()
        self.record_path.write_text(original + "id: duplicated\n")
        with self.assertRaisesRegex(ValueError, "Duplicate YAML key"):
            pc.validated_records(self.root)
        self.record_path.write_text(original)
        config_path = self.root / "catalog.publish.yaml"
        config_path.write_text(config_path.read_text() + "schema_version: 1\n")
        with self.assertRaisesRegex(ValueError, "Duplicate YAML key"):
            pc.load_config(self.root)

    def test_empty_root_is_portolan_structural_and_root_sentinels_survive(self):
        for name in ("README.md", "AGENTS.md", "catalog.json"):
            (self.root / name).write_text("sentinel\n")
        pc._write(Namespace(root=self.root))
        root = json.loads((self.root / "catalog/catalog.json").read_text())
        self.assertIn(pc.PORTOLAN_SCHEMA, root["stac_extensions"])
        self.assertEqual([x["rel"] for x in root["links"]], ["root", "describedby", "agents"])
        self.assertIn("Published collections: 0", (self.root / "catalog/README.md").read_text())
        for name in ("README.md", "AGENTS.md", "catalog.json"):
            self.assertEqual((self.root / name).read_text(), "sentinel\n")
        pc._check(Namespace(root=self.root))
        (self.root / "catalog/extra.txt").write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            pc._check(Namespace(root=self.root))

    def test_export_repeats_and_prepared_snapshot_stays_private(self):
        package = self.make_package()
        one = self.export(package, name="one")
        two = self.root / "datasets/demo/two"
        pc.export_metadata("demo", package, two, self.root)
        self.assertEqual((one / "snapshot.json").read_bytes(), (two / "snapshot.json").read_bytes())
        with self.assertRaisesRegex(ValueError, "already exists"):
            pc.export_metadata("demo", package, one, self.root)
        tree = pc._generated(self.root, pc.load_config(self.root))
        self.assertEqual(set(tree), {"catalog.json", "README.md", "AGENTS.md"})
        self.assertFalse((one / "files/data.parquet").exists())

    def test_populated_nested_style_and_stage_urls(self):
        package = self.make_package(nested=True)
        self.export(package)
        self.publish()
        pc._write(Namespace(root=self.root))
        tree = self.root / "catalog"
        collection = json.loads((tree / "demo/collection.json").read_text())
        self.assertEqual([x["rel"] for x in collection["links"]].count("root"), 1)
        self.assertEqual([x["rel"] for x in collection["links"]].count("parent"), 1)
        self.assertFalse(any(x["rel"] == "self" for x in collection["links"]))
        self.assertTrue((tree / "demo/README.md").exists())
        self.assertFalse((tree / "demo/files/grwl/README.md").exists())
        style_rel = "demo/styles/map.json"
        style = json.loads((tree / style_rel).read_text())
        self.assertEqual(style["sources"]["one"]["url"], "pmtiles://https://data.example.org/demo/r1/grwl/tiles.pmtiles")
        self.assertEqual(collection["assets"]["style"]["file:checksum"], "1220" + sha((tree / style_rel).read_bytes()))
        browser = next(x["href"] for x in collection["links"] if x["rel"] == "alternate")
        self.assertEqual(browser, "https://browser.example.org/?url=" +
                         quote("https://catalog.example.org/root/demo/collection.json", safe=""))
        self.assertEqual(collection["assets"]["data"]["href"], "https://data.example.org/demo/r1/grwl/data.parquet")
        providers = collection["providers"]
        self.assertIn({"name": "nthh", "roles": ["host"],
                       "url": "https://source.coop/nthh/demo"}, providers)
        folia = next(provider for provider in providers if provider["name"] == "Folia")
        self.assertEqual(folia["roles"], ["processor"])
        self.assertIn("producer", next(provider for provider in providers if provider["name"] == "Demo producer")["roles"])
        pc._check(Namespace(root=self.root))
        stage = (self.root / "stage").resolve(strict=False)
        pc._stage(Namespace(root=self.root, output=stage))
        staged = json.loads((stage / "catalog/demo/collection.json").read_text())
        self.assertEqual(staged["assets"]["data"]["href"], "https://data.example.org/demo/r1/grwl/data.parquet")
        self.assertEqual(staged["assets"]["style"]["href"], "https://catalog.example.org/root/demo/styles/map.json")
        self.assertTrue(staged["assets"]["thumbnail"]["href"].startswith("https://catalog.example.org/root/demo/"))
        self.assertEqual(next(x["href"] for x in staged["links"] if x["rel"] == "self"),
                         "https://catalog.example.org/root/demo/collection.json")
        self.assertEqual(json.loads((stage / "publish-plan.json").read_text())["files"][0]["path"].startswith("catalog/"), True)
        self.assertFalse((stage / "catalog/demo/files/grwl/data.parquet").exists())

    def test_github_pages_destination_stages_only_metadata(self):
        package = self.make_package(nested=True)
        self.export(package)
        self.publish()
        self.config["publish"] = {"destination": pc.PAGES_DESTINATION,
                                  "public_base": pc.PAGES_PUBLIC_BASE, "region": None}
        self.write_config()
        pc._write(Namespace(root=self.root))
        stage = self.root / "pages-stage"
        pc._stage(Namespace(root=self.root, output=stage))
        plan = json.loads((stage / "publish-plan.json").read_text())
        self.assertEqual(plan["destination"], pc.PAGES_DESTINATION)
        self.assertIsNone(plan["region"])
        staged_files = {path.relative_to(stage / "catalog").as_posix()
                        for path in (stage / "catalog").rglob("*") if path.is_file()}
        self.assertEqual(staged_files, {row["path"].removeprefix("catalog/") for row in plan["files"]})
        self.assertTrue(all(row["target_uri"] == pc.PAGES_DESTINATION + row["path"].removeprefix("catalog/")
                            and row["target_url"] == pc.PAGES_PUBLIC_BASE + row["path"].removeprefix("catalog/")
                            and row["sha256"] == sha((stage / row["path"]).read_bytes())
                            and row["size_bytes"] == (stage / row["path"]).stat().st_size
                            for row in plan["files"]))
        self.assertFalse(any(path.endswith((".parquet", ".pmtiles", ".zip", ".tif")) for path in staged_files))
        collection = json.loads((stage / "catalog/demo/collection.json").read_text())
        self.assertEqual(next(link["href"] for link in collection["links"] if link["rel"] == "self"),
                         pc.PAGES_PUBLIC_BASE + "demo/collection.json")
        self.assertEqual(collection["assets"]["data"]["href"], "https://data.example.org/demo/r1/grwl/data.parquet")
        del self.config["publish"]["region"]
        self.write_config()
        no_region_stage = self.root / "pages-stage-no-region"
        pc._stage(Namespace(root=self.root, output=no_region_stage))
        self.assertIsNone(json.loads((no_region_stage / "publish-plan.json").read_text())["region"])

    def test_github_pages_destination_requires_exact_pair_and_null_region(self):
        self.config["publish"] = {"destination": pc.PAGES_DESTINATION,
                                  "public_base": pc.PAGES_PUBLIC_BASE, "region": None}
        self.write_config()
        self.assertEqual(pc.load_config(self.root)["publish"], self.config["publish"])
        invalid = [
            {"destination": "github-pages://other/data-publications/"},
            {"destination": "github-pages://nthh/other/"},
            {"destination": "github-pages://nthh/data-publications"},
            {"destination": "github-pages://nthh/data-publications/../"},
            {"destination": "github-pages://nthh/data-publications/?x=1"},
            {"public_base": "https://other.github.io/data-publications/"},
            {"public_base": "https://nthh.github.io/other/"},
            {"public_base": "https://nthh.github.io/data-publications/?x=1"},
            {"region": "us-west-2"},
        ]
        for replacement in invalid:
            with self.subTest(replacement=replacement):
                self.config["publish"] = {"destination": pc.PAGES_DESTINATION,
                                          "public_base": pc.PAGES_PUBLIC_BASE, "region": None,
                                          **replacement}
                self.write_config()
                with self.assertRaisesRegex(ValueError, "publish\\."):
                    pc.load_config(self.root)

    def test_pages_workflow_is_manual_and_artifact_scope_is_catalog_only(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/publish-catalog-pages.yml").read_text())
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        build = workflow["jobs"]["build"]
        deploy = workflow["jobs"]["deploy"]
        self.assertEqual(deploy["needs"], "build")
        self.assertEqual(deploy["permissions"], {"pages": "write", "id-token": "write"})
        self.assertEqual(deploy["environment"]["name"], "github-pages")
        upload_steps = [step for step in build["steps"] if step.get("uses", "").startswith("actions/upload-pages-artifact@")]
        self.assertEqual(len(upload_steps), 1)
        self.assertEqual(upload_steps[0]["with"], {"path": ".local/publication-stage/catalog"})
        actions = [step["uses"] for job in (build, deploy) for step in job["steps"] if "uses" in step]
        self.assertTrue(all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in actions))
        self.assertFalse(any("upload-artifact@" in action for action in actions))

    def test_pinned_display_assets_and_two_layer_styles_override_snapshot(self):
        package = self.make_package(nested=True)
        self.export(package)
        self.publish()
        self.add_hosted_display(layer_count=2)

        pc._write(Namespace(root=self.root))

        tree = self.root / "catalog/demo"
        collection = json.loads((tree / "collection.json").read_text())
        pmtiles_links = [link for link in collection["links"] if link["rel"] == "pmtiles"]
        self.assertEqual(collection["stac_extensions"].count(
            "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"), 1)
        self.assertIn(pc.PORTOLAN_SCHEMA, collection["stac_extensions"])
        self.assertIn("https://stac-extensions.github.io/file/v2.1.0/schema.json", collection["stac_extensions"])
        self.assertEqual(len(pmtiles_links), 2)
        self.assertEqual([link["pmtiles:layers"] for link in pmtiles_links],
                         [["demo-layer-1"], ["demo-layer-2"]])
        self.assertTrue(all(link["href"].startswith("https://display.example.org/demo/display-r1/assets/")
                            for link in pmtiles_links))
        display_styles = [(key, value) for key, value in collection["assets"].items()
                          if "style" in value.get("roles", []) and key.startswith("display_style_")]
        self.assertEqual(len(display_styles), 2)
        self.assertEqual(sum("default" in asset["roles"] for _, asset in display_styles), 1)
        for _, asset in display_styles:
            style_path = tree / asset["href"]
            style_data = style_path.read_bytes()
            self.assertEqual(asset["file:size"], len(style_data))
            self.assertEqual(asset["file:checksum"], "1220" + sha(style_data))
            style = json.loads(style_data)
            self.assertEqual(style["sources"]["data"]["url"],
                             "pmtiles://https://display.example.org/demo/display-r1/assets/"
                             + style_path.name.replace(".json", ".pmtiles"))

    def test_display_manifest_and_style_must_match_the_pinned_inventory(self):
        package = self.make_package()
        self.export(package)
        self.publish()
        self.add_hosted_display()
        display_dir = self.root / "datasets/demo/display/display-r1"
        style_path = display_dir / "styles/demo-layer-1.json"
        original_style = style_path.read_bytes()
        style_path.write_bytes(original_style + b" ")
        with self.assertRaisesRegex(ValueError, "Display style checksum/size mismatch"):
            pc._generated(self.root, pc.load_config(self.root))
        style_path.write_bytes(original_style)

        manifest_path = display_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["display_release"] = "stale"
        dump(manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, "Display manifest SHA-256 mismatch"):
            pc._generated(self.root, pc.load_config(self.root))

    def test_published_display_requires_report_bound_to_manifest_and_url(self):
        package = self.make_package()
        self.export(package)
        self.publish()
        self.add_hosted_display()
        display = self.record["publication"]["display"]
        hosting_report_path = display.pop("hosting_report_path")
        hosting_report_sha256 = display.pop("hosting_report_sha256")
        self.write_record()
        with self.assertRaisesRegex(ValueError, "Invalid canonical dataset record demo"):
            pc.validated_records(self.root)
        display["hosting_report_path"] = hosting_report_path
        display["hosting_report_sha256"] = hosting_report_sha256
        self.write_record()
        report_path = self.root / "datasets/demo/hosting.json"
        report = json.loads(report_path.read_text())
        report["display_manifest_sha256"] = "0" * 64
        raw = dump(report_path, report)
        self.record["publication"]["display"]["hosting_report_sha256"] = sha(raw)
        self.record["publication"]["catalog"]["hosting_report_sha256"] = sha(raw)
        self.write_record()
        with self.assertRaisesRegex(ValueError, "Display hosting report identity/status mismatch"):
            pc._generated(self.root, pc.load_config(self.root))

    def test_portolan_browser_host_path_route_encodes_catalog_path(self):
        config = {
            "navigation": {
                "repository_url": None,
                "issues_url": None,
                "hosting_url": None,
                "browser_url_template": "https://browser.portolan-sdi.org/#/external/{catalog_host_path}",
            },
            "publish": {"public_base": "https://data.source.coop/nthh/river%20plastic%23%3F/"},
        }
        node = {"links": []}

        pc._navigation_links(node, config, "catalog.json")

        browser = node["links"][0]["href"]
        self.assertEqual(
            browser,
            "https://browser.portolan-sdi.org/#/external/"
            "data.source.coop/nthh/river%20plastic%23%3F/catalog.json",
        )
        self.assertEqual(pc.portolan_browser_host_path(
            "https://data.source.coop/nthh/caf%C3%A9%20%23%3F/catalog.json"),
            "data.source.coop/nthh/caf%C3%A9%20%23%3F/catalog.json")
        self.assertEqual(urlsplit(browser).query, "")
        self.assertEqual(
            urlsplit(browser).fragment,
            "/external/data.source.coop/nthh/river%20plastic%23%3F/catalog.json",
        )

    def test_browser_template_rejects_malformed_or_mixed_placeholders(self):
        for template in (
            "https://browser.example.org/?url={unknown}",
            "https://browser.example.org/?url={catalog_url}&host={catalog_host_path}",
            "https://browser.example.org/?url={catalog_url}{catalog_url}",
            "https://browser.example.org/?url={catalog_url",
            "http://browser.example.org/?url={catalog_url}",
        ):
            with self.subTest(template=template):
                self.config["navigation"]["browser_url_template"] = template
                self.write_config()
                with self.assertRaisesRegex(ValueError, "browser_url_template"):
                    pc.load_config(self.root)

    def test_portolan_browser_location_rejects_url_injection(self):
        for catalog_url in (
            "https://user:password@data.source.coop/nthh/catalog.json",
            "https://data.source.coop/nthh/catalog.json?next=example",
            "https://data.source.coop/nthh/catalog.json#other",
            "https://data.source.coop/nthh/bad%escape/catalog.json",
        ):
            with self.subTest(catalog_url=catalog_url), self.assertRaises(ValueError):
                pc.portolan_browser_host_path(catalog_url)

    def test_export_refuses_unsafe_location_and_missing_file_without_writing(self):
        package = self.make_package()
        with self.assertRaisesRegex(ValueError, "immutable package"):
            pc.export_metadata("demo", package, package / "snapshot", self.root)
        self.assertFalse((package / "snapshot").exists())
        with self.assertRaisesRegex(ValueError, "generated catalog"):
            pc.export_metadata("demo", package, self.root / "catalog/snapshot", self.root)
        (package / "styles/map.json").unlink()
        output = self.root / "datasets/demo/broken"
        with self.assertRaises(FileNotFoundError):
            pc.export_metadata("demo", package, output, self.root)
        self.assertFalse(output.exists())

    def test_snapshot_rejects_bulk_unreferenced_tampering_and_asset_mismatch(self):
        package = self.make_package()
        output = self.export(package)
        snap_path = output / "snapshot.json"
        snap = json.loads(snap_path.read_text())
        (output / "files/data.parquet").write_bytes(b"PAR1")
        snap["files"].append({"path": "data.parquet", "sha256": sha(b"PAR1"), "size_bytes": 4})
        raw = dump(snap_path, snap)
        self.record["publication"]["catalog"]["snapshot_sha256"] = sha(raw)
        self.write_record()
        with self.assertRaisesRegex(ValueError, "non-metadata"):
            pc._generated(self.root, pc.load_config(self.root))
        snap["files"].pop()
        (output / "files/data.parquet").unlink()
        raw = dump(snap_path, snap)
        self.record["publication"]["catalog"]["snapshot_sha256"] = sha(raw)
        self.write_record()
        source = package / "collection.json"
        collection = json.loads(source.read_text())
        collection["assets"]["data"]["href"] = "unlisted.parquet"
        dump(output / "files/collection.json", collection)
        snap["files"] = [{**entry, "sha256": sha((output / "files" / entry["path"]).read_bytes()),
                          "size_bytes": (output / "files" / entry["path"]).stat().st_size} for entry in snap["files"]]
        raw = dump(snap_path, snap)
        self.record["publication"]["catalog"]["snapshot_sha256"] = sha(raw)
        self.write_record()
        with self.assertRaisesRegex(ValueError, "[Ii]mmutable package"):
            pc._generated(self.root, pc.load_config(self.root))

    def test_stage_refuses_symlink_ancestor_and_tracked_catalog(self):
        package = self.make_package()
        self.export(package)
        self.publish()
        pc._write(Namespace(root=self.root))
        with self.assertRaisesRegex(ValueError, "tracked catalog"):
            pc._stage(Namespace(root=self.root, output=self.root / "catalog/stage"))
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "alias").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            pc._stage(Namespace(root=self.root, output=self.root / "alias/stage"))
        self.assertFalse((outside / "stage").exists())

    def test_style_rejects_protocol_relative_and_absolute(self):
        for value in ("//evil.example/tiles", "/tiles", "../../escape"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Unsafe"):
                pc._rewrite_style({"sources": {"x": {"url": value}}}, "styles/map.json",
                                  "https://data.example.org/demo/r1/", "collection.json")

    def test_public_processor_description_replaces_local_host_note(self):
        collection = {"providers": [
            {"name": "Original producer", "roles": ["producer"], "description": "Original science."},
            {"name": "nthh", "roles": ["processor", "host"],
             "description": "Local package; not publicly hosted."},
        ]}
        record = {"publication": {"source_coop": {"owner": "nthh", "owner_status": "confirmed",
                                                  "product_id": "demo"}}}
        pc._set_public_host(collection, "demo", record)
        self.assertEqual(collection["providers"][0]["description"], "Original science.")
        self.assertEqual(collection["providers"][1]["description"],
                         "Independent data processing and hosting on Source Cooperative.")
        self.assertEqual(collection["providers"][1]["roles"], ["processor", "host"])
        self.assertEqual(collection["providers"][1]["url"], "https://source.coop/nthh/demo")

    def test_hosting_report_requires_timezone_and_passing_checks(self):
        package = self.make_package()
        self.export(package)
        self.publish()
        path = self.root / "datasets/demo/hosting.json"
        report = json.loads(path.read_text())
        report["checked_at"] = "2026-10-31T12:00:00"
        raw = dump(path, report)
        self.record["publication"]["catalog"]["hosting_report_sha256"] = sha(raw)
        self.write_record()
        with self.assertRaisesRegex(ValueError, "invalid checked_at"):
            pc._generated(self.root, pc.load_config(self.root))
        report["checked_at"] = "2026-10-31T12:00:00Z"
        report["checks"]["cors"] = "failed"
        raw = dump(path, report)
        self.record["publication"]["catalog"]["hosting_report_sha256"] = sha(raw)
        self.write_record()
        with self.assertRaisesRegex(ValueError, "missing/failed"):
            pc._generated(self.root, pc.load_config(self.root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
