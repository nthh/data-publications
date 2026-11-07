from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

import pyarrow as pa
import pyarrow.parquet as pq
import pyproj
import yaml

from package_release import REPO, ReleaseError, build, sha256, verify_package
from serve import Handler, MAX_RANGE_BYTES


def make_fixture(root: Path) -> tuple[Path, Path]:
    bbox_type = pa.struct([("xmin", pa.float64()), ("ymin", pa.float64()),
                           ("xmax", pa.float64()), ("ymax", pa.float64())])
    schema = pa.schema([("id", pa.string()), ("name", pa.string()), ("geometry", pa.binary()), ("bbox", bbox_type)])
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {
        "geometry": {"encoding": "WKB", "geometry_types": ["Point"],
                     "crs": pyproj.CRS.from_epsg(4326).to_json_dict(),
                     "covering": {"bbox": {"xmin": ["bbox", "xmin"], "ymin": ["bbox", "ymin"],
                                  "xmax": ["bbox", "xmax"], "ymax": ["bbox", "ymax"]}}}}}
    schema = schema.with_metadata({b"geo": json.dumps(geo, separators=(",", ":")).encode()})
    points = [(-75.0, 40.0), (-74.0, 41.0), (100.0, -10.0)]
    wkb = [b"\x01\x01\x00\x00\x00" + struct.pack("<dd", x, y) for x, y in points]
    bboxes = [{"xmin": x, "ymin": y, "xmax": x, "ymax": y} for x, y in points]
    table = pa.Table.from_arrays([
        pa.array(["a", "b", "c"]), pa.array(["one", "two", "three"]), pa.array(wkb), pa.array(bboxes, type=bbox_type)
    ], schema=schema)
    data = root / "fixture.parquet"
    pq.write_table(table, data, row_group_size=2)
    record = root / "dataset.yaml"
    record.write_text(yaml.safe_dump({"id": "fixture", "title": "Fixture dataset", "license": "CC-BY-4.0"}, sort_keys=False))
    return data, record


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="folia-release-fixture-")
        self.root = Path(self.tmp.name)
        self.asset, self.record = make_fixture(self.root)
        self.support = self.root / "producer-notes.pdf"
        self.support.write_bytes(b"%PDF-1.4\nfixture producer documentation\n")
        self.asset_id = "fixture-points"
        self.report_paths = [self.root / "source.json", self.root / "rebuild.json"]
        self.refresh_reports()
        self.spec_path = self.root / "spec.json"
        self.write_spec()

    def tearDown(self):
        self.tmp.cleanup()

    def refresh_reports(self, status="passed"):
        entry = {"asset_id": self.asset_id, "sha256": sha256(self.asset), "size_bytes": self.asset.stat().st_size}
        for p in self.report_paths:
            p.write_text(json.dumps({"status": status, "assets": [entry], "evidence": {"fixture": True}}, indent=2) + "\n")

    def write_spec(self, output="package"):
        spec = {"dataset_record_path": self.record.name, "dataset_id": "fixture", "title": "Fixture dataset",
            "release_id": "fixture-r1", "release_version": "1.0.0", "output_dir": output,
            "source_attribution": {"url": "https://producer.example/data", "title": "Fixture source", "attribution": "Source: Fixture"},
            "producers": [{"name": "Fixture Producer", "roles": ["producer", "licensor"], "url": "https://producer.example"}],
            "source_fidelity_report_path": self.report_paths[0].name, "clean_rebuild_report_path": self.report_paths[1].name,
            "assets": [{"asset_id": self.asset_id, "path": self.asset.name, "identifier_column": "id"}],
            "supporting_files": [{"path": self.support.name, "package_path": "source/producer-notes.pdf",
                "title": "Producer technical notes", "media_type": "application/pdf"}],
            "data_license": {"license": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
            "bbox": [-180, -90, 180, 90], "validation_bbox": [-76, 39, -73, 42],
            "created": "2026-10-31T00:00:00Z"}
        self.spec_path.write_text(json.dumps(spec, indent=2) + "\n")

    def test_local_fixture_schema_http_and_remote_subset(self):
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        pinned_path = "scripts/release_tools/add_spatial_bounds.py"
        pinned_bytes = subprocess.check_output(["git", "show", f"{revision}:{pinned_path}"], cwd=REPO)
        spec = json.loads(self.spec_path.read_text())
        spec["workflow_revisions"] = {pinned_path: revision}
        spec["catalog_id"] = "fixture-independent"
        spec["processor"] = {"name": "nthh", "roles": ["host", "processor"], "url": "https://github.com/nthh", "description": "Local package host and converter; no public hosting."}
        self.spec_path.write_text(json.dumps(spec) + "\n")
        try:
            result = build(self.spec_path)
        except ReleaseError:
            p = self.root / "package/evidence"
            for report in sorted(p.glob("*.json")):
                print(f"FIXTURE_REPORT {report.name}: {report.read_text()}")
            raise
        package = self.root / "package"
        self.assertEqual(result["status"], "packaged_locally_not_published")
        self.assertEqual(verify_package(package)["status"], "passed")
        for report in ("stac-node-validation.json", "portolan-validation.json", "local-http-duckdb-validation.json"):
            self.assertEqual(json.loads((package / "evidence" / report).read_text())["status"], "passed")
        subset = json.loads((package / "evidence/local-http-duckdb-validation.json").read_text())["http_and_subset"]["duckdb_subsets"][0]
        self.assertEqual(subset["rows"], 2)
        self.assertGreater(subset["duckdb_http_bytes_served"], 0)
        self.assertTrue((package / "source/producer-notes.pdf").is_file())
        collection = json.loads((package / "collection.json").read_text())
        self.assertIn("support-1", collection["assets"])
        self.assertEqual(collection["providers"][-1], spec["processor"])
        self.assertIn("Local package", collection["providers"][-1]["description"])
        self.assertEqual(json.loads((package / "catalog.json").read_text())["id"], "fixture-independent")
        manifest = json.loads((package / "manifest.json").read_text())
        pinned = manifest["workflow_files"][pinned_path]
        self.assertEqual(pinned["git_revision"], revision)
        self.assertEqual(pinned["sha256"], hashlib.sha256(pinned_bytes).hexdigest())
        self.assertEqual((package / pinned["package_path"]).read_bytes(), pinned_bytes)
        self.assertIn("scripts/release_tools/test_spatial_bounds.py", manifest["workflow_files"])

    def test_explicit_processor_cannot_replace_source_producer(self):
        spec = json.loads(self.spec_path.read_text())
        spec["processor"] = {"name": "nthh", "roles": ["producer", "processor"]}
        self.spec_path.write_text(json.dumps(spec))
        with self.assertRaisesRegex(ReleaseError, "processor must name the converter"):
            build(self.spec_path)
        self.assertFalse((self.root / "package").exists())

    def test_pending_source_report_refuses_before_package_creation(self):
        self.refresh_reports(status="pending")
        with self.assertRaises(ReleaseError):
            build(self.spec_path)
        self.assertFalse((self.root / "package").exists())

    def test_manifest_tampering_and_missing_data_are_detected(self):
        try:
            build(self.spec_path)
        except ReleaseError:
            p = self.root / "package/evidence"
            for report in sorted(p.glob("*.json")):
                print(f"FIXTURE_REPORT {report.name}: {report.read_text()}")
            raise
        package = self.root / "package"
        manifest = package / "manifest.json"
        original = manifest.read_bytes()
        manifest.chmod(0o644)
        manifest.write_bytes(original + b" ")
        self.assertEqual(verify_package(package)["status"], "failed")
        manifest.write_bytes(original)
        readme = package / "README.md"
        readme.chmod(0o644)
        readme.write_bytes(readme.read_bytes() + b"tamper")
        result = verify_package(package)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("bound package file missing/changed: README.md" in x for x in result["failures"]))
        readme.write_bytes(readme.read_bytes()[:-6])
        readme.chmod(0o444)
        asset = package / "assets/fixture-points.parquet"
        asset.parent.chmod(0o755)
        asset.chmod(0o644)
        asset.unlink()
        result = verify_package(package)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("asset missing" in x for x in result["failures"]))
        receipt = package / "package-receipt.json"
        package.chmod(0o755)
        receipt.chmod(0o644)
        receipt.unlink()
        result = verify_package(package)
        self.assertTrue(any("package receipt missing" in x for x in result["failures"]))

    def test_server_rejects_ranges_over_limit(self):
        serve_root = self.root / "range-server"
        serve_root.mkdir()
        large = serve_root / "large.bin"
        with large.open("wb") as f:
            f.truncate(MAX_RANGE_BYTES + 1024)
        server = ThreadingHTTPServer(("127.0.0.1", 0), lambda *args, **kw: Handler(*args, directory=str(serve_root), **kw))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/large.bin"
            req = urllib.request.Request(url, headers={"Range": f"bytes=0-{MAX_RANGE_BYTES}"})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(caught.exception.code, 416)
            self.assertEqual(caught.exception.headers.get("Access-Control-Allow-Origin"), "*")
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
