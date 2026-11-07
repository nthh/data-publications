import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_prepared.py"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PreparedAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        self.package = self.base / "package"
        self.package.mkdir(parents=True)
        (self.root / "datasets" / "sample").mkdir(parents=True)
        (self.root / "reports").mkdir()
        (self.root / "catalog.publish.yaml").write_text("navigation: {}\npublish: {}\n")
        self.dataset_id = "sample"
        self.release = "r1"

    def tearDown(self):
        self.tmp.cleanup()

    def write_fixture(self, legacy=False, content=b"asset-bytes"):
        (self.package / "data.bin").write_bytes(content)
        if legacy:
            manifest = {
                "dataset": self.dataset_id,
                "release": self.release,
                "assets": {"data.bin": {"size_bytes": len(content), "sha256": sha(content)}},
            }
        else:
            (self.package / "display").mkdir(exist_ok=True)
            display = b"preview"
            (self.package / "display" / "thumb.png").write_bytes(display)
            manifest = {
                "dataset_id": self.dataset_id,
                "release_id": self.release,
                "assets": [{"href": "data.bin", "size_bytes": len(content), "sha256": sha(content)}],
                "display_derivatives": [{"path": "display/thumb.png", "size_bytes": len(display), "sha256": sha(display)}],
            }
        encoded = json.dumps(manifest, sort_keys=True).encode()
        manifest_path = self.root / "datasets" / "sample" / "manifest.json"
        manifest_path.write_bytes(encoded)
        (self.package / "manifest.json").write_bytes(encoded)
        snap = b"snapshot"
        snapshot_path = self.root / "datasets" / "sample" / "snapshot.json"
        snapshot_path.write_bytes(snap)
        record = {
            "id": self.dataset_id,
            "publication": {
                "release": self.release,
                "manifest_path": "datasets/sample/manifest.json",
                "manifest_sha256": sha(encoded),
                "catalog": {"snapshot_path": "datasets/sample/snapshot.json", "snapshot_sha256": sha(snap)},
                "validation": {"stac": "passed", "remote_host": "not_tested"},
                "validation_path": "datasets/sample/validation.json",
                "portolan": {"status": "not_submitted"},
            },
        }
        (self.root / "datasets" / "sample" / "dataset.yaml").write_text(yaml.safe_dump(record))

    def run_audit(self, output):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("audit_prepared", SCRIPT)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.audit_dataset(self.root, "sample", self.package)

    def test_modern_manifest_assets_and_snapshot_pass(self):
        self.write_fixture(legacy=False)
        result = self.run_audit(None)
        self.assertEqual(result["integrity_status"], "passed")
        assets = result["local_integrity"]["declared_assets"]
        self.assertEqual(assets["declared_asset_count"], 2)
        self.assertTrue(all(asset["status"] == "passed" for asset in assets["assets"]))
        self.assertFalse(result["retained_local_gates"]["classification"].startswith("rerun"))

    def test_legacy_manifest_passes(self):
        self.write_fixture(legacy=True)
        result = self.run_audit(None)
        self.assertEqual(result["integrity_status"], "passed")
        self.assertEqual(result["local_integrity"]["declared_assets"]["declared_asset_count"], 1)

    def test_same_length_modified_content_fails_hash(self):
        self.write_fixture(legacy=True, content=b"asset-bytes")
        # Change one byte without changing size after the declared hash was captured.
        (self.package / "data.bin").write_bytes(b"asset-bytez")
        result = self.run_audit(None)
        self.assertEqual(result["integrity_status"], "failed")
        self.assertFalse(result["local_integrity"]["declared_assets"]["assets"][0]["sha256_match"])

    def test_missing_asset_fails(self):
        self.write_fixture(legacy=True)
        (self.package / "data.bin").unlink()
        result = self.run_audit(None)
        self.assertEqual(result["integrity_status"], "failed")
        self.assertIn("missing asset", result["local_integrity"]["declared_assets"]["assets"][0]["error"])

    def test_empty_manifest_and_escaping_assets_fail(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location('audit_prepared', SCRIPT)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(module.AuditError, 'at least one asset'):
            module.asset_declarations({'assets': []})
        with self.assertRaisesRegex(module.AuditError, 'unsafe'):
            module.safe_package_file(self.package, '../outside')

    def test_existing_output_refused_before_input_reads(self):
        output = self.base / "already.json"
        output.write_text("keep me")
        before = output.read_bytes()
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.base / "does-not-exist"), "--package", "sample=/missing", "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("refusing to overwrite", proc.stderr)
        self.assertEqual(output.read_bytes(), before)
        self.assertFalse((self.base / "does-not-exist").exists())


if __name__ == "__main__":
    unittest.main()
