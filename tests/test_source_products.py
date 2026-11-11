"""Focused safety and determinism tests for local Source Cooperative plans."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import source_products as products


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FlatReadmeTests(unittest.TestCase):
    def test_consumer_links_are_flat_and_include_a_remote_query(self):
        draft = {"title": "Example", "summary": "Example data", "temporal_note": "Version 1", "owner": "nthh", "product_id": "example", "dataset_id": "example", "attribution": "Original producer", "license_note": "CC BY 4.0", "limitations": ["Display tiles are generalized."], "source_links": [], "related_dataset_links": [], "flat_layout": {"files": [{"filename": "example-v1.parquet", "size_bytes": 1000}, {"filename": "example-v1.pmtiles", "size_bytes": 2000}]}}
        result = products.render_consumer_readme(draft)
        self.assertIn("[example-v1.parquet](example-v1.parquet)", result)
        self.assertIn("[example-v1.pmtiles](example-v1.pmtiles)", result)
        self.assertIn("read_parquet('https://data.source.coop/nthh/example/example-v1.parquet')", result)
        self.assertIn("Original producer", result)
        self.assertNotIn("releases/", result)
        self.assertNotIn("display/", result)
        self.assertNotIn("Folia", result)


class SourceProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        self.package = self.base / "package"
        self.root.mkdir()
        self.package.mkdir()
        (self.root / "datasets" / "sample").mkdir(parents=True)
        (self.root / "docs").mkdir()
        self.supplement = b"producer documentation\n"
        (self.root / "docs" / "producer.md").write_bytes(self.supplement)
        self.dataset_id = "sample"
        self.release = "r1"
        self.display_count = 0
        self.config = {
            "owner": "nthh",
            "owner_status": "proposed",
            "product_id": "sample-product",
            "title": "Sample product",
            "summary": "A local draft for testing.",
            "tags": ["hydrology"],
            "license_note": "CC BY 4.0",
            "attribution": "Sample producer",
            "temporal_note": "Static release r1.",
            "limitations": ["No public hosting has been verified."],
            "supplements": [{
                "path": "docs/producer.md",
                "sha256": sha(self.supplement),
                "destination": "metadata/v1/producer.md",
            }],
        }
        self.record = None
        self.write_fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def write_fixture(self, *, publication_status="prepared", manifest_dataset="sample", manifest_release="r1", include_binding=False):
        asset = b"analytic bytes"
        support = b"attribution\n"
        package_readme = b"package README\n"
        (self.package / "assets").mkdir(exist_ok=True)
        (self.package / "support").mkdir(exist_ok=True)
        (self.package / "assets" / "data.parquet").write_bytes(asset)
        (self.package / "support" / "notes.md").write_bytes(support)
        (self.package / "README.md").write_bytes(package_readme)
        (self.package / "LICENSE").write_text("license text\n")
        (self.package / "NOTICE").write_text("notice text\n")
        manifest = {
            "dataset_id": manifest_dataset,
            "release_id": manifest_release,
            "assets": [{
                "href": "assets/data.parquet",
                "sha256": sha(asset),
                "size_bytes": len(asset),
            }],
            "supporting_files": [{
                "path": "support/notes.md",
                "sha256": sha(support),
                "size_bytes": len(support),
            }],
        }
        manifest_data = products.canonical_json(manifest)
        (self.package / "manifest.json").write_bytes(manifest_data)
        tracked_manifest = self.root / "datasets" / "sample" / "manifest.json"
        tracked_manifest.write_bytes(manifest_data)
        collection = {
            "type": "Collection",
            "id": "sample",
            "title": "Sample",
            "description": "A snapshotted collection.",
            "license": "CC-BY-4.0",
            "assets": {"data": {"href": "assets/data.parquet", "title": "Data", "type": "application/vnd.apache.parquet"}},
        }
        collection_data = products.canonical_json(collection)
        (self.package / "collection.json").write_bytes(collection_data)
        repository_collection = self.root / "datasets" / "sample" / "files" / "collection.json"
        repository_collection.parent.mkdir(parents=True, exist_ok=True)
        repository_collection.write_bytes(collection_data)
        snapshot = {
            "schema_version": 1,
            "dataset_id": "sample",
            "release": "r1",
            "package_manifest_sha256": sha(manifest_data),
            "collection_path": "collection.json",
            "files": [
                {"path": "README.md", "sha256": sha(package_readme), "size_bytes": len(package_readme)},
                {"path": "collection.json", "sha256": sha(collection_data), "size_bytes": len(collection_data)},
            ],
        }
        receipt_path = None
        if include_binding:
            bound_files = {}
            for path in sorted(self.package.rglob("*")):
                if path.is_file() and path.name != "manifest.json":
                    rel = path.relative_to(self.package).as_posix()
                    data = path.read_bytes()
                    bound_files[rel] = {"sha256": sha(data), "size_bytes": len(data)}
            package_binding = {"manifest_sha256": sha(manifest_data), "bound_files": bound_files}
            binding_data = products.canonical_json(package_binding)
            binding_path = self.root / "datasets" / "sample" / "proof" / "package-binding.json"
            binding_path.parent.mkdir(parents=True, exist_ok=True)
            binding_path.write_bytes(binding_data)
            (self.package / "evidence").mkdir(exist_ok=True)
            (self.package / "evidence" / "package-binding.json").write_bytes(binding_data)
            final_verification = b"final verification evidence\n"
            (self.package / "evidence" / "final-verification.json").write_bytes(final_verification)
            snapshot["binding_proof"] = {"path": "proof/package-binding.json", "sha256": sha(binding_data)}
            receipt = {"dataset_id": "sample", "release_id": "r1", "manifest_sha256": sha(manifest_data),
                       "package_binding_sha256": sha(binding_data),
                       "final_verification_sha256": sha(final_verification)}
            receipt_data = products.canonical_json(receipt)
            receipt_file = self.root / "datasets" / "sample" / "release-receipt.json"
            receipt_file.write_bytes(receipt_data)
            receipt_path = "datasets/sample/release-receipt.json"
        snapshot_data = products.canonical_json(snapshot)
        snapshot_path = self.root / "datasets" / "sample" / "snapshot.json"
        snapshot_path.write_bytes(snapshot_data)
        record = {
            "id": "sample",
            "title": "Sample dataset",
            "publication": {
                "status": publication_status,
                "release": "r1",
                "manifest_path": "datasets/sample/manifest.json",
                "manifest_sha256": sha(manifest_data),
                "catalog": {"snapshot_path": "datasets/sample/snapshot.json", "snapshot_sha256": sha(snapshot_data)},
                **({"release_receipt_path": receipt_path} if receipt_path else {}),
                "source_coop": self.config,
            },
        }
        (self.root / "datasets" / "sample" / "dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        self.record = record

    def read_record(self):
        return yaml.safe_load((self.root / "datasets" / "sample" / "dataset.yaml").read_text())

    def write_draft(self):
        self.assertEqual(products.generate(self.root, write=True), [])

    def stage(self, *, output_name="stage"):
        output = self.base / output_name
        result = products.stage(self.root, [("sample", self.package)], output)
        return result, output

    def bind_published_hosting(self):
        account = {"owner": "nthh", "status": "confirmed"}
        account_data = products.canonical_json(account)
        (self.root / "account-verification.json").write_bytes(account_data)
        self.config["owner_status"] = "confirmed"
        self.config["account_verification"] = {
            "status": "confirmed", "owner": "nthh", "evidence_path": "account-verification.json",
            "evidence_sha256": sha(account_data)}
        self.write_fixture(publication_status="published")
        record = self.read_record()
        report = {"schema_version": 1, "dataset_id": "sample", "release": "r1",
                  "package_manifest_sha256": record["publication"]["manifest_sha256"],
                  "package_base_url": "https://data.source.coop/nthh/sample-product/releases/r1/",
                  "checked_at": "2026-11-06T12:00:00Z", "status": "passed",
                  "checks": {name: "passed" for name in products.HOSTING_CHECKS}}
        data = products.canonical_json(report)
        report_path = self.root / "datasets/sample/hosting-report.json"
        report_path.write_bytes(data)
        record["publication"]["catalog"].update({
            "package_base_url": report["package_base_url"],
            "hosting_report_path": "datasets/sample/hosting-report.json",
            "hosting_report_sha256": sha(data),
        })
        (self.root / "datasets/sample/dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        return report_path

    def add_display_package(self, *, analytic_release="r1", source_hash=None, duplicate=False,
                            release="display-v1", asset_changes=None, style_changes=None, extra_files=None):
        self.display_count += 1
        display = self.base / f"display-{self.display_count}"
        display.mkdir(exist_ok=True)
        tile = b"pmtiles display"
        style_value = {"version": 8, "sources": {"data": {"type": "vector", "url": "../assets/sample.pmtiles"}},
                       "layers": [{"id": "sample", "type": "fill", "source": "data", "source-layer": "sample"}]}
        if style_changes:
            style_value.update(style_changes)
        style = products.canonical_json(style_value)
        (display / "assets").mkdir(exist_ok=True)
        (display / "styles").mkdir(exist_ok=True)
        (display / "assets" / "sample.pmtiles").write_bytes(tile)
        (display / "styles" / "sample.json").write_bytes(style)
        analytic_bytes = (self.package / "assets" / "data.parquet").read_bytes()
        asset = {
            "id": "sample-1", "title": "Sample", "path": "assets/sample.pmtiles",
            "size_bytes": len(tile), "sha256": sha(tile), "source_layer": "sample",
            "geometry_type": "polygon", "min_zoom": 0, "max_zoom": 12,
            "id_field": "sample_id", "attribute_fields": ["sample_id"],
            "source_asset": {"path": "assets/data.parquet", "size_bytes": len(analytic_bytes),
                             "sha256": source_hash or sha(analytic_bytes)},
            "style_path": "styles/sample.json",
        }
        if asset_changes:
            asset.update(asset_changes)
        assets = [asset, dict(asset)] if duplicate else [asset]
        if duplicate:
            assets[1]["title"] = "Duplicate"
        files = {
            "assets/sample.pmtiles": {"size_bytes": len(tile), "sha256": sha(tile)},
            "styles/sample.json": {"size_bytes": len(style), "sha256": sha(style)},
        }
        for relative, payload in (extra_files or {}).items():
            target = display / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            files[relative] = {"size_bytes": len(payload), "sha256": sha(payload)}
        manifest = {"schema_version": 1, "dataset_id": "sample", "display_release": release,
                    "analytic_release": analytic_release, "status": "prepared", "assets": assets, "files": files}
        data = products.canonical_json(manifest)
        (display / "manifest.json").write_bytes(data)
        canonical = self.root / "datasets" / "sample" / "display" / release / "manifest.json"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_bytes(data)
        record = self.read_record()
        record["publication"]["display"] = {"release": release, "manifest_path": f"datasets/sample/display/{release}/manifest.json",
                                             "manifest_sha256": sha(data)}
        (self.root / "datasets" / "sample" / "dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        return display

    def test_write_and_check_are_deterministic(self):
        self.write_draft()
        paths = products.generated_paths("sample")
        first = [(self.root / path).read_bytes() for path in paths]
        self.assertEqual(products.generate(self.root, write=False), [])
        self.assertEqual(products.generate(self.root, write=True), [])
        self.assertEqual(first, [(self.root / path).read_bytes() for path in paths])

    def test_candidate_draft_has_blocked_state_and_no_assets(self):
        self.write_fixture(publication_status="candidate")
        self.assertEqual(products.generate(self.root, write=True), [])
        draft_path, _, consumer_path = products.generated_paths("sample")
        draft = json.loads((self.root / draft_path).read_text())
        self.assertEqual(draft["local_readiness"], "blocked")
        self.assertEqual(draft["assets"], [])
        self.assertIsNone(draft["snapshot_collection"])
        self.assertFalse(draft["creation_ready"])
        self.assertFalse(draft["hosted"])
        consumer = (self.root / consumer_path).read_text()
        self.assertIn("Planned product", consumer)
        self.assertIn("no converted release", consumer)
        self.assertNotIn("Draft metadata", consumer)
        self.assertNotIn("No product has been created", consumer)
        self.assertNotIn("releases/r1/", consumer)

    def test_display_package_plan_is_separate_and_bound_to_analytic_files(self):
        display = self.add_display_package(release="display-v2")
        self.write_draft()
        output = self.base / "display-stage"
        self.assertEqual(products.stage(self.root, [("sample", self.package)], output, [("sample", display)]), 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        display_files = [item for item in plan["files"] if item["source"]["kind"] == "display_package"]
        self.assertEqual({item["object_key"] for item in display_files}, {
            "sample-product/display/display-v2/manifest.json",
            "sample-product/display/display-v2/assets/sample.pmtiles",
            "sample-product/display/display-v2/styles/sample.json",
        })
        self.assertEqual(plan["products"][0]["release"], "r1")
        self.assertEqual(plan["products"][0]["display_publication"]["release"], "display-v2")

    def test_dotted_display_release_flows_through_draft_and_exact_staging(self):
        release = "raw-v01.01-display-r1"
        display = self.add_display_package(release=release)
        self.write_draft()
        draft, _, _ = products.draft_for(self.root, self.read_record())
        self.assertEqual(draft["display_publication"]["release"], release)
        output = self.base / "dotted-display-stage"
        self.assertEqual(products.stage(self.root, [("sample", self.package)], output, [("sample", display)]), 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        self.assertTrue(any(item["object_key"] == f"sample-product/display/{release}/manifest.json"
                            for item in plan["files"]))
        self.assertEqual(plan["products"][0]["display_publication"]["release"], release)

    def test_display_release_rejects_unsafe_version_slugs(self):
        for release in ("../escape", "a/b", "a\\\\b", "raw..r1", "raw--r1", ".leading", "trailing-", "x" * 41):
            with self.subTest(release=release):
                display = self.add_display_package(release=release)
                with self.assertRaisesRegex(products.ProductError, "publication.display pin is invalid"):
                    products.draft_for(self.root, self.read_record())

    def test_display_verification_sources_and_missing_id_evidence_are_bound(self):
        evidence = {
            "reports/finalization/missing-ids.jsonl": (b'{"id":1,"cause":"quantization_collapse"}\n', "application/x-ndjson"),
            "workflow/viewer/check.mjs": (b'export const checked = true;\n', "text/javascript"),
            "workflow/viewer/app.js": (b'console.log("source snapshot");\n', "text/javascript"),
            "workflow/viewer/style.css": (b'body { margin: 0; }\n', "text/css"),
        }
        display = self.add_display_package(extra_files={path: value[0] for path, value in evidence.items()})
        self.write_draft()
        output = self.base / "verification-source-stage"
        self.assertEqual(products.stage(self.root, [("sample", self.package)], output, [("sample", display)]), 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        staged = {item["path"]: item for item in plan["files"] if item["source"]["kind"] == "display_package"}
        for relative, (payload, mime) in evidence.items():
            self.assertEqual(staged[relative]["content_type"], mime)
            self.assertEqual(staged[relative]["sha256"], sha(payload))
            self.assertEqual(staged[relative]["binding_status"], "bound_by_display_manifest")
        (display / "workflow/viewer/check.mjs").write_bytes(b'altered verification source\n')
        failed = self.base / "verification-source-tampered"
        self.assertEqual(products.stage(self.root, [("sample", self.package)], failed, [("sample", display)]), 1)
        self.assertIn("display file hash/size mismatch", (failed / "failure.json").read_text())

    def test_display_native_and_browser_evidence_content_types_are_bound(self):
        evidence = {
            "reports/replay/build.log": (b"native build passed\n", "text/plain"),
            "workflow/native-oracle/checker.cpp": (b"int main() { return 0; }\n", "text/plain"),
            "workflow/native-oracle/detail-oracle": (b"compiled oracle fixture", "application/octet-stream"),
            "reports/viewer/vendor/engine.wasm": (b"\x00asm\x01\x00\x00\x00", "application/wasm"),
        }
        display = self.add_display_package(extra_files={path: value[0] for path, value in evidence.items()})
        self.write_draft()
        output = self.base / "native-browser-evidence-stage"
        self.assertEqual(products.stage(self.root, [("sample", self.package)], output, [("sample", display)]), 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        staged = {item["path"]: item for item in plan["files"] if item["source"]["kind"] == "display_package"}
        for relative, (payload, mime) in evidence.items():
            self.assertEqual(staged[relative]["content_type"], mime)
            self.assertEqual(staged[relative]["sha256"], sha(payload))
            self.assertEqual(staged[relative]["binding_status"], "bound_by_display_manifest")
        (display / "workflow/native-oracle/detail-oracle").write_bytes(b"changed checker")
        failed = self.base / "native-browser-evidence-tampered"
        self.assertEqual(products.stage(self.root, [("sample", self.package)], failed, [("sample", display)]), 1)
        self.assertIn("display file hash/size mismatch", (failed / "failure.json").read_text())

    def test_native_evidence_mime_does_not_allow_unknown_data_types(self):
        for relative in ("assets/detail-oracle", "workflow/untyped", "workflow/native-oracle/tool.unknown",
                         "reports/native-oracle/detail-oracle", "workflow/native-oracle/nested/tool"):
            with self.subTest(relative=relative), self.assertRaisesRegex(products.ProductError, "unknown asset extension"):
                products.content_type(relative)

    def test_display_draft_uses_pinned_manifest_and_storage_links(self):
        self.add_display_package(release="display-v2")
        draft, _, consumer = products.draft_for(self.root, self.read_record())
        self.assertEqual(draft["display_publication"]["manifest_href"], "display/display-v2/manifest.json")
        self.assertEqual(draft["display_publication"]["assets"][0]["href"], "display/display-v2/assets/sample.pmtiles")
        self.assertIn("application/vnd.pmtiles", consumer)
        self.assertIn("display/display-v2/styles/sample.json", consumer)
        manifest_path = self.root / "datasets" / "sample" / "display" / "display-v2" / "manifest.json"
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
        with self.assertRaisesRegex(products.ProductError, "checksum does not match canonical pin"):
            products.draft_for(self.root, self.read_record())

    def test_selected_canonical_display_cannot_be_omitted_from_staging(self):
        self.add_display_package()
        self.write_draft()
        output = self.base / "omitted-display-stage"
        result = products.stage(self.root, [("sample", self.package)], output)
        self.assertEqual(result, 1)
        self.assertIn("missing required --display-package", (output / "failure.json").read_text())

    def test_display_source_binding_and_files_are_verified(self):
        for kwargs, expected in [({"analytic_release": "other"}, "analytic_release mismatch"),
                                 ({"source_hash": "0" * 64}, "source_asset does not match")]:
            with self.subTest(kwargs=kwargs):
                display = self.add_display_package(**kwargs)
                if kwargs.get("analytic_release") != "other":
                    self.write_draft()
                else:
                    with self.assertRaisesRegex(products.ProductError, "identity/release mismatch"):
                        products.draft_for(self.root, self.read_record())
                    continue
                output = self.base / f"bad-stage-{kwargs.get('analytic_release', kwargs.get('source_hash', 'x'))}"
                result = products.stage(self.root, [("sample", self.package)], output, [("sample", display)])
                self.assertEqual(result, 1)
                self.assertIn(expected, (output / "failure.json").read_text())
        display = self.add_display_package()
        self.write_draft()
        (display / "assets" / "sample.pmtiles").write_bytes(b"altered")
        output = self.base / "altered-stage"
        result = products.stage(self.root, [("sample", self.package)], output, [("sample", display)])
        self.assertEqual(result, 1)
        self.assertIn("hash/size mismatch", (output / "failure.json").read_text())

    def test_display_package_rejects_symlinks_missing_objects_and_duplicate_ids(self):
        display = self.add_display_package()
        (display / "assets" / "sample.pmtiles").unlink()
        (display / "assets" / "sample.pmtiles").symlink_to(self.package / "assets" / "data.parquet")
        self.write_draft()
        output = self.base / "symlink-stage"
        result = products.stage(self.root, [("sample", self.package)], output, [("sample", display)])
        self.assertEqual(result, 1)
        self.assertIn("unsafe file", (output / "failure.json").read_text())
        display = self.add_display_package()
        (display / "assets" / "sample.pmtiles").unlink()
        self.write_draft()
        output = self.base / "missing-stage"
        result = products.stage(self.root, [("sample", self.package)], output, [("sample", display)])
        self.assertEqual(result, 1)
        self.assertIn("files do not match manifest inventory", (output / "failure.json").read_text())
        display = self.add_display_package(duplicate=True)
        with self.assertRaisesRegex(products.ProductError, "asset IDs are invalid or duplicated"):
            products.draft_for(self.root, self.read_record())

    def test_display_asset_metadata_and_style_are_validated(self):
        cases = [
            ({"asset_changes": {"size_bytes": 999}}, {}, "metadata disagrees"),
            ({"asset_changes": {"min_zoom": -1}}, {}, "zoom range"),
            ({"asset_changes": {"source_layer": ""}}, {}, "source_layer is required"),
            ({"asset_changes": {"id_encoding": "guess"}}, {}, "invalid display asset id_encoding"),
            ({"asset_changes": {"attribute_fields": []}}, {}, "ID property is missing"),
            ({"asset_changes": {"attribute_fields": ["sample_id", "sample_id"]}}, {}, "invalid display asset attribute_fields"),
            ({}, {"style_changes": {"sources": {"data": {"type": "vector", "url": "pmtiles://../assets/sample.pmtiles"}}}}, "plain relative path"),
            ({}, {"style_changes": {"version": 7}}, "MapLibre style v8"),
            ({}, {"style_changes": {"sources": {"data": {"type": "vector", "url": "wrong.pmtiles"}}}}, "does not resolve"),
            ({}, {"style_changes": {"layers": [{"id": "bad", "type": "line", "source": "data", "source-layer": "sample"}]}}, "matching source-layer/type"),
        ]
        for index, (asset_kwargs, style_kwargs, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                display = self.add_display_package(**asset_kwargs, **style_kwargs)
                if expected in ("metadata disagrees",):
                    with self.assertRaisesRegex(products.ProductError, expected):
                        products.draft_for(self.root, self.read_record())
                    continue
                self.write_draft()
                output = self.base / f"invalid-display-{index}"
                result = products.stage(self.root, [("sample", self.package)], output, [("sample", display)])
                self.assertEqual(result, 1)
                self.assertIn(expected, (output / "failure.json").read_text())

    def test_consumer_readme_links_release_files_and_versioned_supplements(self):
        self.write_draft()
        draft, _, consumer = products.draft_for(self.root, self.read_record())
        self.assertIn("releases/r1/assets/data.parquet", consumer)
        self.assertIn("releases/r1/support/notes.md", consumer)
        self.assertIn("[producer.md](metadata/v1/producer.md)", consumer)
        result, output = self.stage()
        self.assertEqual(result, 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        supplement = next(item for item in plan["files"] if item.get("kind") == "supplement")
        linked_path = next(line.split("](", 1)[1].split(")", 1)[0]
                           for line in consumer.splitlines() if "producer.md" in line)
        self.assertEqual(linked_path, supplement["object_key"].removeprefix("sample-product/"))
        self.assertNotIn("Draft metadata", consumer)
        self.assertNotIn("No product has been created", consumer)
        self.assertIn("public hosting and validation have not been checked", consumer)
        self.assertEqual(draft["release_files"][0]["path"], "assets/data.parquet")

    def test_consumer_readme_preserves_nested_package_paths(self):
        self.write_draft()
        draft, _, _ = products.draft_for(self.root, self.read_record())
        draft["release_files"] = [{"path": "legacy/collection/data.parquet", "kind": "asset"}]
        consumer = products.render_consumer_readme(draft)
        self.assertIn("releases/r1/legacy/collection/data.parquet", consumer)
        self.assertNotIn("releases/r1/data.parquet", consumer)

    def test_published_product_links_apply_current_maintainer_without_rewriting_snapshot(self):
        collection = {"providers": [
            {"name": "Original authors", "roles": ["producer", "licensor"], "url": "https://example.org/producer"},
            {"name": "Legacy label", "roles": ["processor", "host"], "url": "https://example.org/legacy"},
        ]}
        original = json.dumps(collection, sort_keys=True)
        record = {"id": "sample", "publication": {
            "status": "published", "source_coop": {"owner": "nthh", "owner_status": "confirmed", "product_id": "sample"},
            "catalog": {"processor_correction": {"from": "Legacy label", "to": "nthh"}},
        }}
        links, _ = products.product_links(record, collection)
        by_url = {item["url"]: item["title"] for item in links}
        self.assertEqual(by_url["https://example.org/producer"], "Producer: Original authors")
        self.assertEqual(by_url["https://source.coop/nthh/sample"], "Processor: nthh")
        self.assertNotIn("https://example.org/legacy", by_url)
        self.assertEqual(json.dumps(collection, sort_keys=True), original)
        record["publication"]["catalog"]["processor_correction"]["to"] = "someone-else"
        with self.assertRaisesRegex(products.ProductError, "confirmed maintainer"):
            products.product_links(record, collection)

    def test_host_label_uses_the_actual_provider_name(self):
        links = products.collection_links({"providers": [
            {"name": "nthh", "roles": ["host"], "url": "https://github.com/nthh"},
        ]})
        self.assertEqual(links, [{"title": "Host: nthh", "url": "https://github.com/nthh"}])

    def test_external_links_have_readable_titles_and_dedupe_urls(self):
        source = products.source_field_links({
            "paper_doi": "10.1234/paper",
            "doi": "10.5678/dataset",
            "source_url": "https://example.org/download.zip",
            "technical_documentation": {"url": "https://example.org/docs"},
            "field_catalog": {"url": "https://example.org/catalog"},
            "license_url": "https://example.org/license",
        })
        stac = products.collection_links({
            "links": [
                {"rel": "via", "href": "https://doi.org/10.5678/dataset"},
                {"rel": "license", "href": "https://example.org/license"},
            ],
            "providers": [{"name": "Example publisher", "roles": ["processor", "host"], "url": "https://example.org/publisher"}],
        })
        links = products.dedupe_links(source + stac)
        by_url = {item["url"]: item["title"] for item in links}
        self.assertEqual(by_url["https://doi.org/10.1234/paper"], "Research paper")
        self.assertEqual(by_url["https://doi.org/10.5678/dataset"], "Dataset release")
        self.assertEqual(by_url["https://example.org/download.zip"], "Original download")
        self.assertEqual(by_url["https://example.org/docs"], "Producer technical documentation")
        self.assertEqual(by_url["https://example.org/catalog"], "Producer attribute catalogue")
        self.assertEqual(by_url["https://example.org/license"], "License terms")
        self.assertEqual(by_url["https://example.org/publisher"], "Processor: Example publisher")

    def test_all_versioned_supplements_appear_in_both_readmes(self):
        supplements = []
        for name, payload in (("field-semantics.json", b"{}\n"), ("README.md", b"Semantics guide\n"),
                              ("build_semantics.py", b"# builder\n")):
            path = self.root / "datasets/sample/metadata-enhancements/v1" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            supplements.append({
                "path": f"datasets/sample/metadata-enhancements/v1/{name}",
                "sha256": sha(payload),
                "destination": f"metadata/field-semantics-v1/{name}",
            })
        self.config["supplements"] = supplements
        self.write_fixture()
        self.write_draft()
        _, local_path, consumer_path = products.generated_paths("sample")
        local = (self.root / local_path).read_text()
        consumer = (self.root / consumer_path).read_text()
        for name in ("field-semantics.json", "README.md", "build_semantics.py"):
            self.assertIn(name, local)
            self.assertIn(f"metadata/field-semantics-v1/{name}", consumer)

    def test_owner_proposal_does_not_claim_creation_or_hosting(self):
        self.write_draft()
        draft_path, _, _ = products.generated_paths("sample")
        draft = json.loads((self.root / draft_path).read_text())
        self.assertEqual(draft["proposed_source_proxy"], {"uri": "s3://nthh/sample-product", "status": "proposed"})
        self.assertFalse(draft["creation_ready"])
        self.assertFalse(draft["created"])
        self.assertFalse(draft["hosted"])

    def test_confirmed_owner_and_account_evidence_do_not_promote_candidate(self):
        self.write_fixture(publication_status="candidate")
        evidence = {"owner": "nthh", "status": "confirmed"}
        evidence_data = products.canonical_json(evidence)
        (self.root / "account-verification.json").write_bytes(evidence_data)
        self.config["owner_status"] = "confirmed"
        self.config["account_verification"] = {
            "status": "confirmed", "owner": "nthh", "evidence_path": "account-verification.json",
            "evidence_sha256": sha(evidence_data),
        }
        self.write_fixture(publication_status="candidate")
        self.assertEqual(products.generate(self.root, write=True), [])
        draft_path, _, _ = products.generated_paths("sample")
        draft = json.loads((self.root / draft_path).read_text())
        self.assertEqual(draft["publication_status"], "candidate")
        self.assertFalse(draft["creation_ready"])
        self.assertFalse(draft["created"])

    def test_confirmed_account_evidence_enables_only_creation_readiness(self):
        evidence = {"owner": "nthh", "status": "confirmed"}
        evidence_data = products.canonical_json(evidence)
        (self.root / "account-verification.json").write_bytes(evidence_data)
        self.config["owner_status"] = "confirmed"
        self.config["account_verification"] = {
            "status": "confirmed", "owner": "nthh", "evidence_path": "account-verification.json",
            "evidence_sha256": sha(evidence_data),
        }
        self.write_fixture(publication_status="prepared")
        self.write_draft()
        draft_path, _, _ = products.generated_paths("sample")
        draft = json.loads((self.root / draft_path).read_text())
        self.assertTrue(draft["creation_ready"])
        self.assertEqual(draft["publication_status"], "prepared")
        self.assertFalse(draft["created"])
        self.assertFalse(draft["hosted"])

    def test_pinned_product_creation_receipt_sets_prepared_created_without_hosting(self):
        creation = {"schema_version": 1, "product": {"account_id": "nthh", "product_id": "sample-product",
                    "metadata": {"mirrors": {"aws-opendata-us-west-2": {
                        "is_primary": True, "prefix": "nthh/sample-product/"}}}}}
        creation_bytes = products.canonical_json(creation)
        receipt_path = self.root / "creation.json"
        receipt_path.write_bytes(creation_bytes)
        evidence = {"owner": "nthh", "status": "confirmed", "product_creation_receipts": [
            {"dataset_id": "sample", "path": "creation.json", "sha256": sha(creation_bytes)}]}
        evidence_bytes = products.canonical_json(evidence)
        (self.root / "account-verification.json").write_bytes(evidence_bytes)
        self.config["owner_status"] = "confirmed"
        self.config["account_verification"] = {
            "status": "confirmed", "owner": "nthh", "evidence_path": "account-verification.json",
            "evidence_sha256": sha(evidence_bytes)}
        self.write_fixture(publication_status="prepared")
        draft, review, consumer = products.draft_for(self.root, self.read_record())
        self.assertTrue(draft["created"])
        self.assertFalse(draft["hosted"])
        self.assertIn("separate execution receipts", review)
        self.assertNotIn("No product has been created", review)
        self.assertIn("public hosting and validation have not been checked", consumer)

    def test_published_requires_checksum_bound_matching_hosting_report(self):
        self.bind_published_hosting()
        record = self.read_record()
        record["publication"]["catalog"]["package_base_url"] = "https://data.source.coop/nthh/sample-product/releases/r1/"
        record["publication"]["catalog"].pop("hosting_report_path")
        record["publication"]["catalog"].pop("hosting_report_sha256")
        (self.root / "datasets/sample/dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        with self.assertRaisesRegex(products.ProductError, "checksum-bound hosting report"):
            products.draft_for(self.root, self.read_record())
        report_path = self.bind_published_hosting()
        report_path.write_bytes(report_path.read_bytes().replace(b'"passed"', b'"failed"', 1))
        with self.assertRaisesRegex(products.ProductError, "SHA-256 mismatch"):
            products.draft_for(self.root, self.read_record())
        report = json.loads(report_path.read_text())
        report["release"] = "other-release"
        changed = products.canonical_json(report)
        report_path.write_bytes(changed)
        record = self.read_record()
        record["publication"]["catalog"]["hosting_report_sha256"] = sha(changed)
        (self.root / "datasets/sample/dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        with self.assertRaisesRegex(products.ProductError, "identity or required checks mismatch"):
            products.draft_for(self.root, self.read_record())

    def test_published_consumer_readme_keeps_release_links_and_hosted_scope(self):
        self.bind_published_hosting()
        draft, review, consumer = products.draft_for(self.root, self.read_record())
        self.assertTrue(draft["created"] and draft["hosted"])
        self.assertEqual(draft["snapshot_binding"]["hosted_package_base_url"],
                         "https://data.source.coop/nthh/sample-product/releases/r1/")
        self.assertIn("Validated hosted release", consumer)
        self.assertIn("releases/r1/assets/data.parquet", consumer)
        self.assertIn("[producer.md](metadata/v1/producer.md)", consumer)
        self.assertNotIn("no converted release", consumer)
        self.assertNotIn("No product has been created", review)
        self.assertIn("Hosted product", review)
        self.write_draft()
        result, output = self.stage(output_name="published-stage")
        self.assertEqual(result, 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        self.assertTrue(plan["created"] and plan["hosted"])

    def test_published_display_requires_manifest_bound_hosting_evidence(self):
        report_path = self.bind_published_hosting()
        self.add_display_package()
        record = self.read_record()
        display = record["publication"]["display"]
        base = "https://data.source.coop/nthh/sample-product/display/display-v1/"
        report = json.loads(report_path.read_text())
        report.update({"display_release": display["release"],
                       "display_manifest_sha256": display["manifest_sha256"],
                       "display_package_base_url": base})
        data = products.canonical_json(report)
        report_path.write_bytes(data)
        record["publication"]["catalog"]["hosting_report_sha256"] = sha(data)
        display.update({"package_base_url": base,
                        "hosting_report_path": "datasets/sample/hosting-report.json",
                        "hosting_report_sha256": sha(data)})
        (self.root / "datasets/sample/dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        draft, _, consumer = products.draft_for(self.root, self.read_record())
        self.assertTrue(draft["hosted"])
        self.assertIn("display/display-v1/assets/sample.pmtiles", consumer)
        report["display_manifest_sha256"] = "0" * 64
        wrong = products.canonical_json(report)
        report_path.write_bytes(wrong)
        record["publication"]["catalog"]["hosting_report_sha256"] = sha(wrong)
        display["hosting_report_sha256"] = sha(wrong)
        (self.root / "datasets/sample/dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        with self.assertRaisesRegex(products.ProductError, "display hosting report binding mismatch"):
            products.draft_for(self.root, self.read_record())

    def test_stage_emits_exact_portable_plan_but_not_creation(self):
        self.write_draft()
        result, output = self.stage()
        self.assertEqual(result, 0)
        plan = json.loads((output / "immutable-upload-plan.json").read_text())
        self.assertEqual(plan["file_count"], 8)  # every regular package file plus the supplement
        package_bytes = sum(path.stat().st_size for path in self.package.rglob("*") if path.is_file())
        self.assertEqual(plan["total_bytes"], package_bytes + len(self.supplement))
        self.assertFalse(plan["creation_ready"])
        self.assertFalse(plan["created"])
        self.assertFalse(plan["hosted"])
        self.assertEqual(plan["execution"], "not_started")
        data = next(item for item in plan["files"] if item["path"] == "assets/data.parquet")
        self.assertEqual(data["bucket"], "nthh")
        self.assertEqual(data["endpoint"], "https://data.source.coop")
        self.assertEqual(data["s3_uri_proposed"], "s3://nthh/sample-product/releases/r1/assets/data.parquet")
        self.assertEqual(data["raw_url_proposed"], "https://data.source.coop/nthh/sample-product/releases/r1/assets/data.parquet")
        self.assertEqual(data["binding_status"], "bound_by_canonical_manifest")
        for entry in plan["files"]:
            self.assertNotIn(str(self.base), json.dumps(entry))
            self.assertEqual(entry["source"]["kind"], "package" if entry["source"].get("dataset_id") else "repository")
        product_plan = json.loads((output / "products" / "sample" / "upload-plan.json").read_text())
        self.assertEqual(product_plan["mutable_metadata"][0]["object_key"], "sample-product/README.md")
        self.assertTrue(product_plan["mutable_metadata"][0]["mutable"])
        self.assertFalse(product_plan["mutable_metadata"][0]["upload_allowed"])
        self.assertFalse(product_plan["mutable_metadata"][0]["requires_finalized_publication_copy"])
        self.assertEqual(product_plan["mutable_metadata"][0]["source"]["path"],
                         "datasets/sample/source-coop/product-README.md")
        self.assertFalse(any("finalize publication wording" in item for item in plan["blockers"]))
        for path in output.rglob("*.json"):
            self.assertNotIn(str(self.base).encode(), path.read_bytes())

    def test_package_binding_proof_is_verified_and_extra_files_are_labeled(self):
        self.write_fixture(include_binding=True)
        self.write_draft()
        result, output = self.stage()
        self.assertEqual(result, 0)
        plan = json.loads((output / "products" / "sample" / "upload-plan.json").read_text())
        self.assertEqual(plan["package_binding"]["status"], "verified")
        self.assertGreater(plan["package_binding"]["bound_file_count"], 0)
        files = {item["path"]: item for item in plan["immutable_files"]}
        self.assertEqual(files["evidence/package-binding.json"]["binding_status"],
                         "bound_by_canonical_receipt_digest")
        self.assertEqual(files["evidence/final-verification.json"]["binding_status"],
                         "bound_by_canonical_receipt_digest")
        receipt_digest_paths = {"evidence/package-binding.json", "evidence/final-verification.json"}
        self.assertTrue(all(item["binding_status"] == "bound_by_package_receipt" for item in plan["immutable_files"]
                            if item["source"]["kind"] == "package" and item["path"] not in receipt_digest_paths | {"manifest.json"}))

    def test_extensionless_license_and_notice_are_explicitly_allowed(self):
        self.assertEqual(products.content_type("licenses/software/LICENSE"), "text/plain")
        self.assertEqual(products.content_type("licenses/software/NOTICE"), "text/plain")

    def test_tampered_asset_is_rejected_and_failure_report_is_preserved(self):
        self.write_draft()
        (self.package / "assets" / "data.parquet").write_bytes(b"changed bytes!")
        result, output = self.stage()
        self.assertEqual(result, 1)
        failure = json.loads((output / "failure.json").read_text())
        self.assertIn("changed after manifest verification", failure["error"])

    def test_tampered_supporting_file_is_rejected(self):
        self.write_draft()
        (self.package / "support" / "notes.md").write_bytes(b"attribuXion\n")
        result, output = self.stage()
        self.assertEqual(result, 1)
        self.assertIn("changed after manifest verification", (output / "failure.json").read_text())

    def test_modern_workflow_and_license_manifest_files_are_verified(self):
        manifest = json.loads((self.package / "manifest.json").read_text())
        support = (self.package / "support/notes.md").read_bytes()
        license_bytes = (self.package / "LICENSE").read_bytes()
        manifest["workflow_files"] = {"notes": {
            "package_path": "support/notes.md", "sha256": sha(support), "bytes": len(support),
        }}
        manifest["data_license"] = {
            "path": "LICENSE", "sha256": sha(license_bytes), "bytes": len(license_bytes),
        }
        manifest_data = products.canonical_json(manifest)
        (self.package / "manifest.json").write_bytes(manifest_data)
        record = self.read_record()
        (self.root / record["publication"]["manifest_path"]).write_bytes(manifest_data)
        snapshot_path = self.root / record["publication"]["catalog"]["snapshot_path"]
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["package_manifest_sha256"] = sha(manifest_data)
        snapshot_data = products.canonical_json(snapshot)
        snapshot_path.write_bytes(snapshot_data)
        record["publication"]["manifest_sha256"] = sha(manifest_data)
        record["publication"]["catalog"]["snapshot_sha256"] = sha(snapshot_data)
        (self.root / "datasets/sample/dataset.yaml").write_text(yaml.safe_dump(record, sort_keys=False))

        declarations = products.manifest_declarations(manifest, "sample")
        self.assertEqual(len([item for item in declarations if item["path"] == "support/notes.md"]), 1)
        self.write_draft()
        (self.package / "support/notes.md").write_bytes(b"tampered workflow notes")
        result, output = self.stage(output_name="workflow-failure")
        self.assertEqual(result, 1)
        self.assertIn("support/notes.md", (output / "failure.json").read_text())
        (self.package / "support/notes.md").write_bytes(support)
        (self.package / "LICENSE").write_bytes(b"tampered license")
        result, output = self.stage(output_name="license-failure")
        self.assertEqual(result, 1)
        self.assertIn("LICENSE", (output / "failure.json").read_text())

    def test_tampered_supplement_is_rejected(self):
        self.write_draft()
        (self.root / "docs" / "producer.md").write_bytes(b"changed producer doc")
        result, output = self.stage()
        self.assertEqual(result, 1)
        self.assertIn("supplement SHA-256 mismatch", (output / "failure.json").read_text())

    def test_write_and_check_reject_tampered_supplement(self):
        (self.root / "docs" / "producer.md").write_bytes(b"changed producer doc")
        errors = products.generate(self.root, write=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("supplement SHA-256 mismatch", errors[0])
        self.assertFalse((self.root / products.generated_paths("sample")[0]).exists())

    def test_check_rejects_tampered_consumer_readme(self):
        self.write_draft()
        _, _, consumer_path = products.generated_paths("sample")
        (self.root / consumer_path).write_text("tampered copy\n")
        errors = products.generate(self.root, write=False)
        self.assertEqual(len(errors), 1)
        self.assertIn("product-README.md", errors[0])

    def test_manifest_hash_mismatch_is_rejected(self):
        self.write_draft()
        manifest = json.loads((self.package / "manifest.json").read_text())
        manifest["unbound_metadata_change"] = True
        (self.package / "manifest.json").write_bytes(products.canonical_json(manifest))
        result, output = self.stage()
        self.assertEqual(result, 1)
        self.assertIn("manifest hash differs", (output / "failure.json").read_text())

    def test_tracked_manifest_identity_mismatch_is_rejected(self):
        self.write_fixture(manifest_dataset="other")
        result, output = self.stage()
        self.assertEqual(result, 1)
        self.assertIn("identity does not match", (output / "failure.json").read_text())

    def test_symlink_hidden_credential_and_unknown_extension_are_rejected(self):
        self.write_draft()
        (self.package / ".env").write_text("secret")
        result, output = self.stage(output_name="hidden-stage")
        self.assertEqual(result, 1)
        self.assertIn("hidden path", (output / "failure.json").read_text())
        (self.package / ".env").unlink()
        (self.package / "bad.unknown").write_text("not accepted")
        result, output = self.stage(output_name="extension-stage")
        self.assertEqual(result, 1)
        self.assertIn("unknown asset extension", (output / "failure.json").read_text())
        (self.package / "bad.unknown").unlink()
        try:
            (self.package / "link.md").symlink_to(self.package / "README.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        result, output = self.stage(output_name="symlink-stage")
        self.assertEqual(result, 1)
        self.assertIn("symlink", (output / "failure.json").read_text())

    def test_traversal_and_duplicate_destinations_are_rejected(self):
        with self.assertRaisesRegex(products.ProductError, "unsafe"):
            products.safe_relpath("../outside", "test path")
        self.config["supplements"].append(dict(self.config["supplements"][0]))
        self.write_fixture()
        self.write_draft()
        result, output = self.stage()
        self.assertEqual(result, 1)
        self.assertIn("duplicate object key", (output / "failure.json").read_text())

    def test_empty_assets_bad_owner_ids_and_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaisesRegex(products.ProductError, "assets cannot be empty"):
            products.manifest_declarations({"assets": []}, "sample")
        invalid = self.read_record()
        invalid["publication"]["source_coop"]["owner"] = "nthh--team"
        with self.assertRaisesRegex(products.ProductError, "owner must be null"):
            products.source_config(invalid)
        self.config["owner"] = "nthh"
        (self.root / "datasets" / "sample" / "dataset.yaml").write_text("id: sample\nid: sample\n")
        with self.assertRaisesRegex(products.ProductError, "duplicate key"):
            products.load_records(self.root)

    def test_existing_or_dangling_output_is_refused_without_mutation(self):
        output = self.base / "existing"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep")
        result = products.stage(self.root, [("sample", self.package)], output)
        self.assertEqual(result, 2)
        self.assertEqual(marker.read_text(), "keep")
        dangling = self.base / "dangling"
        try:
            dangling.symlink_to(self.base / "missing")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        result = products.stage(self.root, [("sample", self.package)], dangling)
        self.assertEqual(result, 2)
        self.assertTrue(dangling.is_symlink())


if __name__ == "__main__":
    unittest.main()
