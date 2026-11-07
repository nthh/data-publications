"""Integration tests against the locked Rashid and stac-check console scripts."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/portolan"))
sys.path.insert(0, str(ROOT / "scripts"))
import offline_cli
from check_portolan import run_gate


def multihash(data: bytes) -> str:
    return "1220" + hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def synthetic_parquet(path: Path) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Little-endian WKB for POINT (0 0).
    wkb_point = struct.pack("<BI2d", 1, 1, 0.0, 0.0)
    bbox_type = pa.struct([("xmin", pa.float64()), ("ymin", pa.float64()),
                           ("xmax", pa.float64()), ("ymax", pa.float64())])
    geo = {"version": "1.1.0", "primary_column": "geometry",
           "columns": {"geometry": {"encoding": "WKB", "geometry_types": ["Point"],
                                      "crs": None, "bbox": [0.0, 0.0, 0.0, 0.0],
                                      "covering": {"bbox": {axis: ["bbox", axis] for axis in ("xmin", "ymin", "xmax", "ymax")}}}}}
    schema = pa.schema([("OBJECTID", pa.int64()), ("geometry", pa.binary()), ("bbox", bbox_type)],
                       metadata={b"geo": json.dumps(geo, separators=(",", ":")).encode()})
    table = pa.Table.from_pylist([{"OBJECTID": 1, "geometry": wkb_point,
                                   "bbox": {"xmin": 0.0, "ymin": 0.0, "xmax": 0.0, "ymax": 0.0}}], schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path.read_bytes()


def make_catalog(path: Path, *, with_data: bool = False) -> Path:
    catalog_dir = path / "catalog"
    child_dir = catalog_dir / "fixture"
    child_dir.mkdir(parents=True)
    asset_rel = "assets/ffr-reach-network-v1.parquet"
    data_path = child_dir / asset_rel
    if with_data:
        data = synthetic_parquet(data_path)
        size = len(data)
        checksum = multihash(data)
    else:
        size = 1
        checksum = "1220" + "a" * 64
    thumbnail = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")

    source = json.loads((ROOT / "datasets/free-flowing-rivers/releases/figshare-v1-local-r2/collection.json").read_text())
    collection = copy.deepcopy(source)
    collection["id"] = "fixture"
    collection["title"] = "Synthetic Portolan fixture"
    collection["description"] = "Small synthetic collection for offline validator integration tests."
    collection["assets"] = {"ffr-reach-network-v1": {
        "file:checksum": checksum, "file:size": size, "href": asset_rel,
        "roles": ["data"], "title": "Synthetic point data", "type": "application/vnd.apache.parquet"},
        "thumbnail": {"file:checksum": multihash(thumbnail), "file:size": len(thumbnail),
                       "href": "thumbnail.png", "roles": ["thumbnail"], "title": "Synthetic thumbnail", "type": "image/png"}}
    collection["table:columns"] = [
        {"asset": "ffr-reach-network-v1", "name": "OBJECTID", "type": "int64", "description": "Synthetic row identifier."},
        {"asset": "ffr-reach-network-v1", "name": "geometry", "type": "binary", "description": "WKB point geometry."},
        {"asset": "ffr-reach-network-v1", "name": "bbox", "type": "struct", "description": "Spatial bbox covering."},
    ]
    collection["extent"] = {"spatial": {"bbox": [[0.0, 0.0, 0.0, 0.0]]},
                            "temporal": {"interval": [[None, None]]}}
    collection["links"] = [
        {"rel": "root", "href": "../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        {"rel": "describedby", "href": "./README.md", "type": "text/markdown"},
        {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown"},
        {"rel": "via", "href": "https://example.org/source", "title": "Synthetic source", "type": "text/html"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html"},
    ]
    collection["providers"] = [
        {"name": "Synthetic producer", "roles": ["producer", "licensor"], "url": "https://example.org/"},
        {"name": "Synthetic publisher", "roles": ["host", "processor"], "url": "https://example.org/"},
    ]
    collection["license"] = "CC-BY-4.0"
    collection["portolan:version"] = "0.2.0"
    collection["stac_version"] = "1.1.0"
    collection["version"] = "1.0.0"
    collection["created"] = "2026-10-31T00:00:00Z"
    collection["updated"] = "2026-10-31T00:00:00Z"
    write_json(child_dir / "collection.json", collection)
    (child_dir / "README.md").write_text("# Synthetic collection\n\nLicense: CC-BY-4.0. Source provenance: generated fixture.\n")
    (child_dir / "AGENTS.md").write_text("Synthetic validator fixture; no data conversion is performed.\n")
    (child_dir / "thumbnail.png").write_bytes(thumbnail)
    (catalog_dir / "README.md").write_text("# Synthetic catalog\n\nOffline validator fixture.\n")
    (catalog_dir / "AGENTS.md").write_text("Synthetic catalog fixture.\n")
    root_catalog = {"stac_version": "1.1.0", "type": "Catalog", "id": "synthetic-catalog",
                    "title": "Synthetic test catalog", "description": "Offline conformance test.",
                    "links": [
                        {"rel": "root", "href": "catalog.json", "type": "application/json"},
                        {"rel": "child", "href": "fixture/collection.json", "title": "Synthetic fixture", "type": "application/json"},
                        {"rel": "describedby", "href": "./README.md", "type": "text/markdown"},
                        {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown"},
                    ], "stac_extensions": ["https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"],
                    "portolan:version": "0.2.0", "updated": "2026-10-31T00:00:00Z"}
    write_json(catalog_dir / "catalog.json", root_catalog)
    return catalog_dir


class PortolanGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portolan-gate-")
        self.tmp = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, catalog: Path, report: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "scripts/check_portolan.py"),
                               "--catalog", str(catalog), "--report", str(report), *extra],
                              cwd=ROOT, capture_output=True, text=True, check=False)

    def test_real_rashid_accepts_complete_root_and_collection(self):
        catalog = make_catalog(self.tmp / "positive")
        report_path = self.tmp / "positive-report.json"
        result = self.run_cli(catalog, report_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["conformance"]["status"], "passed")
        self.assertTrue(report["conformance"]["report"]["passed"])
        self.assertEqual(report["conformance"]["report"]["files_checked"], 2)

    def test_removing_collection_license_fails_ptl_lic_001(self):
        catalog = make_catalog(self.tmp / "missing-license")
        collection_path = catalog / "fixture/collection.json"
        collection = json.loads(collection_path.read_text())
        del collection["license"]
        write_json(collection_path, collection)
        report_path = self.tmp / "license-report.json"
        result = self.run_cli(catalog, report_path)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(report_path.read_text())
        findings = report["conformance"]["report"]["findings"]
        self.assertTrue(any(f.get("rule_id") == "PTL-LIC-001" and f.get("severity") == "error" for f in findings), findings)

    def test_data_and_remote_checks_are_off_by_default(self):
        catalog = make_catalog(self.tmp / "default-scope")
        report_path = self.tmp / "scope-report.json"
        result = self.run_cli(catalog, report_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        conformance = json.loads(report_path.read_text())["conformance"]
        args = conformance["command"]
        self.assertIn("--no-data", args)
        self.assertIn("--no-live", args)
        self.assertNotIn("--live", args)
        self.assertNotIn("--data-scope", args)

    def test_local_data_flag_opts_into_local_only_scope(self):
        catalog = make_catalog(self.tmp / "local-data", with_data=True)
        report_path = self.tmp / "local-data-report.json"
        result = self.run_cli(catalog, report_path, "--local-data")
        report = json.loads(report_path.read_text())
        self.assertEqual(report["scope"], "local_data")
        self.assertEqual(report["conformance"]["expected_scope"]["data"], "local")
        self.assertIn("--data-scope", report["conformance"]["command"])
        self.assertIn("local", report["conformance"]["command"])
        self.assertIn("--no-live", report["conformance"]["command"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_offline_guard_blocks_local_socket_connect(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        attempted, restore = offline_cli.install_network_guard()
        try:
            with self.assertRaisesRegex(offline_cli.OfflineNetworkAttempt, "OFFLINE GUARD"):
                client.connect(("127.0.0.1", 9))
            self.assertTrue(attempted["value"])
        finally:
            restore()
            client.close()

    def test_report_overwrite_is_refused(self):
        catalog = make_catalog(self.tmp / "overwrite")
        report_path = self.tmp / "existing-report.json"
        report_path.write_text("keep\n")
        result = self.run_cli(catalog, report_path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Report already exists", result.stderr)
        self.assertEqual(report_path.read_text(), "keep\n")

    def test_stac_advisory_failure_is_separate_and_visible(self):
        catalog = make_catalog(self.tmp / "advisory")
        write_json(catalog / "fixture/broken.json", {"type": "Feature"})
        report_path = self.tmp / "advisory-report.json"
        self.run_cli(catalog, report_path)
        report = json.loads(report_path.read_text())
        advisory = report["stac_check_advisory"]
        self.assertIn(advisory["status"], ("incomplete", "findings"))
        self.assertGreaterEqual(advisory["objects_checked"], 3)
        failed = [item for item in advisory["results"] if item["path"] == "fixture/broken.json"]
        self.assertEqual(len(failed), 1)
        self.assertIn(failed[0]["status"], ("failed", "tool_error"))
        self.assertTrue(failed[0]["advisory"])
        self.assertIn("--no-assets-urls", failed[0]["command"])
        self.assertNotIn("--links", failed[0]["command"])
        self.assertNotIn("--assets", failed[0]["command"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
