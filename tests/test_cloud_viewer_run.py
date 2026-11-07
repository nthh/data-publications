"""Unit tests for package discovery and validation in cloud_viewer.run."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.cloud_viewer.run import RunError, _canonical_plan_products, resolve_display_packages, resolve_packages


PRODUCTS = [
    ("grwl", "summary-v01.02-local-r1"),
    ("river-plastic-inputs", "figshare-v6-r2"),
    ("hydrolakes", "v1-local-r3"),
    ("free-flowing-rivers", "figshare-v1-local-r2"),
    ("lakeatlas", "lakeatlas-v1.0-r2"),
]


def fixture(base: Path):
    root = base / "repo"
    data = base / "packages"
    root.mkdir(parents=True)
    rows = []
    products = []
    files = []
    for dataset_id, release in PRODUCTS:
        (root / "datasets" / dataset_id).mkdir(parents=True)
        record = {
            "id": dataset_id,
            "publication": {
                "release": release,
                "source_coop": {"owner": "nthh", "product_id": dataset_id},
            },
        }
        (root / "datasets" / dataset_id / "dataset.yaml").write_text(yaml.safe_dump(record))
        products.append(
            {
                "dataset_id": dataset_id,
                "release": release,
                "owner": "nthh",
                "bucket": "nthh",
                "product_id": dataset_id,
            }
        )
        files.append(
            {
                "object_key": f"{dataset_id}/releases/{release}/manifest.json",
                "bucket": "nthh",
                "source": {"kind": "package", "dataset_id": dataset_id, "path": "manifest.json"},
            }
        )
    plan = root / "plan.json"
    plan.write_text(json.dumps({"products": products, "files": files}))
    selections = _canonical_plan_products(root, plan)
    return root, data, plan, selections


def write_package(path: Path, dataset_id: str, release: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps({"dataset": dataset_id, "release": release, "assets": {}})
    )


class RunPackageTests(unittest.TestCase):
    def test_discovers_all_three_supported_layouts(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, data, _, products = fixture(Path(temporary))
            for index, (dataset_id, release) in enumerate(PRODUCTS):
                if index % 3 == 0:
                    path = data / dataset_id / release
                elif index % 3 == 1:
                    path = data / dataset_id / "releases" / release
                else:
                    path = data / dataset_id / "releases" / f"{release}-prepared"
                write_package(path, dataset_id, release)
            resolved = resolve_packages(data, products)
            self.assertEqual(len(resolved), 5)
            self.assertTrue(all((path / "manifest.json").is_file() for path in resolved.values()))

    def test_rejects_ambiguous_and_missing_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, data, _, products = fixture(Path(temporary))
            dataset_id, release = PRODUCTS[0]
            write_package(data / dataset_id / release, dataset_id, release)
            write_package(data / dataset_id / "releases" / release, dataset_id, release)
            with self.assertRaisesRegex(RunError, "ambiguous package directories"):
                resolve_packages(data, products)
        with tempfile.TemporaryDirectory() as temporary:
            _, data, _, products = fixture(Path(temporary))
            with self.assertRaisesRegex(RunError, "no package directory found"):
                resolve_packages(data, products)

    def test_manual_override_replaces_discovery_and_validates_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, data, _, products = fixture(base)
            for dataset_id, release in PRODUCTS[1:]:
                write_package(data / dataset_id / "releases" / release, dataset_id, release)
            dataset_id, release = PRODUCTS[0]
            # The override bypasses two ambiguous discovery locations, but not manifest validation.
            write_package(data / dataset_id / release, dataset_id, release)
            write_package(data / dataset_id / "releases" / release, dataset_id, release)
            override = base / "external-package"
            write_package(override, dataset_id, release)
            resolved = resolve_packages(data, products, {dataset_id: override})
            self.assertEqual(resolved[dataset_id], override.resolve())
            (override / "manifest.json").write_text(json.dumps({"dataset": dataset_id, "release": "wrong"}))
            with self.assertRaisesRegex(RunError, "manifest release mismatch"):
                resolve_packages(data, products, {dataset_id: override})

    def test_rejects_plan_canonical_mismatch_and_runs_no_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, data, plan, products = fixture(Path(temporary))
            plan_data = json.loads(plan.read_text())
            plan_data["products"][0]["owner"] = "other-owner"
            plan.write_text(json.dumps(plan_data))
            with self.assertRaisesRegex(RunError, "owner mismatch"):
                _canonical_plan_products(root, plan)
        with tempfile.TemporaryDirectory() as temporary:
            _, data, _, products = fixture(Path(temporary))
            for dataset_id, release in PRODUCTS:
                write_package(data / dataset_id / "releases" / release, dataset_id, release)
            with patch("scripts.cloud_viewer.run.subprocess.run", side_effect=AssertionError("unexpected command")), patch(
                "scripts.cloud_viewer.run.subprocess.Popen", side_effect=AssertionError("unexpected server launch")
            ):
                resolved = resolve_packages(data, products)
            self.assertEqual(len(resolved), 5)

    def test_display_package_discovery_and_canonical_plan_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, data, plan, _ = fixture(Path(temporary))
            dataset_id = "hydrolakes"
            release = "raw-v01.01-display-r1"
            package = data / dataset_id / "display" / release
            package.mkdir(parents=True)
            manifest = json.dumps({"schema_version": 1, "dataset_id": dataset_id,
                                   "display_release": release, "analytic_release": "v1-local-r3",
                                   "status": "prepared", "assets": [], "files": {}}).encode()
            (package / "manifest.json").write_bytes(manifest)
            digest = hashlib.sha256(manifest).hexdigest()
            record_path = root / "datasets" / dataset_id / "dataset.yaml"
            record = yaml.safe_load(record_path.read_text())
            record["publication"]["display"] = {"release": release,
                                                 "manifest_path": f"datasets/{dataset_id}/display/{release}/manifest.json",
                                                 "manifest_sha256": digest}
            record_path.write_text(yaml.safe_dump(record))
            plan_data = json.loads(plan.read_text())
            plan_data["files"].append({"object_key": f"{dataset_id}/display/{release}/manifest.json",
                                        "bucket": "nthh", "sha256": digest, "size_bytes": len(manifest),
                                        "source": {"kind": "display_package", "dataset_id": dataset_id,
                                                   "path": "manifest.json"}})
            plan.write_text(json.dumps(plan_data))
            products = _canonical_plan_products(root, plan)
            resolved = resolve_display_packages(data, products)
            self.assertEqual(resolved[dataset_id], package.resolve())
            (package / "manifest.json").write_bytes(b"altered")
            with self.assertRaisesRegex(RunError, "manifest hash differs"):
                resolve_display_packages(data, products)

    def test_canonical_display_rejects_unsafe_version_slugs(self):
        for release in ("raw..r1", "raw--r1", ".leading", "trailing-", "x" * 41):
            with self.subTest(release=release), tempfile.TemporaryDirectory() as temporary:
                root, _, plan, _ = fixture(Path(temporary))
                record_path = root / "datasets" / "hydrolakes" / "dataset.yaml"
                record = yaml.safe_load(record_path.read_text())
                record["publication"]["display"] = {
                    "release": release,
                    "manifest_path": f"datasets/hydrolakes/display/{release}/manifest.json",
                    "manifest_sha256": "a" * 64,
                }
                record_path.write_text(yaml.safe_dump(record))
                with self.assertRaisesRegex(RunError, "canonical display release/hash is invalid"):
                    _canonical_plan_products(root, plan)

    def test_legacy_plan_without_canonical_display_stays_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, plan, products = fixture(Path(temporary))
            self.assertEqual(len(_canonical_plan_products(root, plan)), 5)
            self.assertEqual(resolve_display_packages(Path(temporary) / "packages", products), {})

    def test_canonical_display_requires_new_plan_unless_explicit_legacy_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, plan, _ = fixture(Path(temporary))
            record_path = root / "datasets" / "hydrolakes" / "dataset.yaml"
            record = yaml.safe_load(record_path.read_text())
            record["publication"]["display"] = {"release": "display-v1", "manifest_path": "datasets/hydrolakes/display/display-v1/manifest.json", "manifest_sha256": "a" * 64}
            record_path.write_text(yaml.safe_dump(record))
            with self.assertRaisesRegex(RunError, "missing the canonical display package"):
                _canonical_plan_products(root, plan)
            products = _canonical_plan_products(root, plan, legacy_plan=True)
            self.assertNotIn("display_release", next(item for item in products if item["dataset_id"] == "hydrolakes"))


if __name__ == "__main__":
    unittest.main()
