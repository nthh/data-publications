"""Focused standard-library tests for scripts/cloud_viewer/prepare.py."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from scripts.cloud_viewer.prepare import DATASET_IDS, PrepareError, _load_records, _read_parquet, build_config, main


RELEASES = {
    "grwl": "summary-v01.02-local-r1",
    "river-plastic-inputs": "figshare-v6-r2",
    "hydrolakes": "v1-local-r3",
    "free-flowing-rivers": "figshare-v1-local-r2",
    "lakeatlas": "lakeatlas-v1.0-r2",
    "gdw": None,
    "swot_prior_lake_database": None,
}


def _parquet(path: Path, geometry_type: str = "Polygon") -> None:
    table = pa.table(
        {
            "id": pa.array([1], type=pa.int64()),
            "name": ["sample"],
            "bbox": pa.array(
                [{"xmin": 1.0, "ymin": 2.0, "xmax": 3.0, "ymax": 4.0}],
                type=pa.struct(
                    [
                        pa.field("xmin", pa.float64()),
                        pa.field("ymin", pa.float64()),
                        pa.field("xmax", pa.float64()),
                        pa.field("ymax", pa.float64()),
                    ]
                ),
            ),
            "geometry": [b"wkb"],
        }
    )
    metadata = {
        "version": "1.0.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": [geometry_type],
                "bbox": [1, 2, 3, 4],
                "covering": {
                    "bbox": {
                        "xmin": ["bbox", "xmin"],
                        "ymin": ["bbox", "ymin"],
                        "xmax": ["bbox", "xmax"],
                        "ymax": ["bbox", "ymax"],
                    }
                },
            }
        },
    }
    table = table.replace_schema_metadata({b"geo": json.dumps(metadata).encode()})
    pq.write_table(table, path)


def fixture(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    packages = {}
    files = []
    for dataset_id in DATASET_IDS:
        (root / "datasets" / dataset_id).mkdir(parents=True)
        record = {
            "schema_version": 1,
            "id": dataset_id,
            "title": f"Scientific {dataset_id}",
            "publication": {
                "status": "prepared" if RELEASES[dataset_id] else "candidate",
                "release": RELEASES[dataset_id],
                "source_coop": {
                    "owner": "nthh",
                    "product_id": dataset_id,
                    "title": f"{dataset_id} release title",
                    "summary": f"{dataset_id} record summary",
                    "attribution": f"{dataset_id} producer",
                    "limitations": ["Official archive acquisition is blocked by HTTP 403."]
                    if dataset_id == "gdw"
                    else ["Full tile and schema validation remain pending."]
                    if dataset_id == "swot_prior_lake_database"
                    else [],
                },
            },
        }
        (root / "datasets" / dataset_id / "dataset.yaml").write_text(yaml.safe_dump(record))
    for dataset_id in DATASET_IDS[:5]:
        # Package roots are separate from the repository checkout in normal staged runs.
        package = tmp_path / "packages" / dataset_id
        package.mkdir(parents=True)
        packages[dataset_id] = package
        release = RELEASES[dataset_id]
        prefix = f"{dataset_id}/releases/{release}/"
        if dataset_id in ("grwl", "river-plastic-inputs"):
            pmtiles = "data/display.pmtiles"
            style = "styles/display.json"
            (package / pmtiles).parent.mkdir(parents=True, exist_ok=True)
            (package / pmtiles).write_bytes(b"pmtiles fixture")
            (package / style).parent.mkdir(parents=True, exist_ok=True)
            (package / style).write_text(
                json.dumps(
                    {
                        "layers": [
                            {
                                "id": "l",
                                "type": "line" if dataset_id == "grwl" else "circle",
                                "source-layer": "display",
                            }
                        ]
                    }
                )
            )
            files.extend([_plan_entry(prefix, pmtiles, package), _plan_entry(prefix, style, package)])
            parquet = "data/analytics.parquet"
            (package / parquet).parent.mkdir(parents=True, exist_ok=True)
            _parquet(package / parquet, "LineString" if dataset_id == "grwl" else "Point")
            files.append(_plan_entry(prefix, parquet, package))
        else:
            paths = ["assets/data.parquet"] if dataset_id != "lakeatlas" else ["assets/polygons.parquet", "assets/pour_points.parquet"]
            for relative in paths:
                (package / relative).parent.mkdir(parents=True, exist_ok=True)
                _parquet(package / relative, "Point" if "points" in relative else "Polygon")
                files.append(_plan_entry(prefix, relative, package))
    plan = root / "plan.json"
    products = [
        {
            "dataset_id": dataset_id,
            "release": RELEASES[dataset_id],
            "owner": "nthh",
            "bucket": "nthh",
            "product_id": dataset_id,
        }
        for dataset_id in DATASET_IDS[:5]
    ]
    plan.write_text(json.dumps({"files": files, "products": products}))
    return root, plan, packages


def _plan_entry(prefix: str, relative: str, package: Path) -> dict:
    data = (package / relative).read_bytes()
    return {
        "object_key": prefix + relative,
        "bucket": "nthh",
        "content_type": "application/vnd.apache.parquet"
        if relative.endswith("parquet")
        else "application/json"
        if relative.endswith("json")
        else "application/vnd.pmtiles",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source": {"kind": "package", "dataset_id": prefix.split("/")[0], "path": relative},
    }


def add_display_fixture(root: Path, plan: Path, packages: dict[str, Path], *, source_mismatch=False, duplicate=False,
                        asset_changes=None, style_changes=None, display_release="display-v1", dataset_id="hydrolakes"):
    is_grwl = dataset_id == "grwl"
    package = root.parent / "display-packages" / dataset_id
    (package / "tiles").mkdir(parents=True)
    (package / "styles").mkdir()
    (package / "tiles" / "hydrolakes.pmtiles").write_bytes(b"tile bytes")
    style = {"version": 8, "sources": {"data": {"type": "vector", "url": "../tiles/hydrolakes.pmtiles"}},
             "layers": [{"id": "h", "type": "line" if is_grwl else "fill", "source": "data", "source-layer": "lakes"}]}
    if style_changes:
        style.update(style_changes)
    (package / "styles" / "hydrolakes.json").write_text(json.dumps(style))
    analytic_rel = "data/analytics.parquet" if is_grwl else "assets/data.parquet"
    analytic = packages[dataset_id] / analytic_rel
    analytic_hash = hashlib.sha256(analytic.read_bytes()).hexdigest()
    asset = {
        "id": "grwl-display" if is_grwl else "hydrolakes-1", "title": dataset_id, "path": "tiles/hydrolakes.pmtiles",
        "size_bytes": len(b"tile bytes"), "sha256": hashlib.sha256(b"tile bytes").hexdigest(),
        "source_layer": "lakes", "geometry_type": "line" if is_grwl else "polygon", "min_zoom": 0, "max_zoom": 12,
        "id_field": "Hylak_id", "attribute_fields": ["Hylak_id", "_src_xmin", "_src_ymin", "_src_xmax", "_src_ymax"],
        "source_asset": {"path": analytic_rel, "size_bytes": analytic.stat().st_size,
                          "sha256": "0" * 64 if source_mismatch else analytic_hash},
        "style_path": "styles/hydrolakes.json",
    }
    if asset_changes:
        asset.update(asset_changes)
    assets = [asset, dict(asset)] if duplicate else [asset]
    files = {
        "tiles/hydrolakes.pmtiles": {"size_bytes": len(b"tile bytes"), "sha256": hashlib.sha256(b"tile bytes").hexdigest()},
        "styles/hydrolakes.json": {"size_bytes": (package / "styles/hydrolakes.json").stat().st_size,
                                   "sha256": hashlib.sha256((package / "styles/hydrolakes.json").read_bytes()).hexdigest()},
    }
    manifest = {"schema_version": 1, "dataset_id": dataset_id, "display_release": display_release,
                "analytic_release": RELEASES[dataset_id], "status": "prepared", "assets": assets, "files": files}
    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode() + b"\n"
    (package / "manifest.json").write_bytes(manifest_bytes)
    canonical_path = root / "datasets" / dataset_id / "display" / display_release / "manifest.json"
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_bytes(manifest_bytes)
    record_path = root / "datasets" / dataset_id / "dataset.yaml"
    record = yaml.safe_load(record_path.read_text())
    record["publication"]["display"] = {"release": display_release,
                                         "manifest_path": f"datasets/{dataset_id}/display/{display_release}/manifest.json",
                                         "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
    record_path.write_text(yaml.safe_dump(record))
    data = json.loads(plan.read_text())
    for rel in ["manifest.json", *files]:
        source = package / rel
        raw = source.read_bytes()
        data["files"].append({
            "object_key": f"{dataset_id}/display/{display_release}/{rel}", "bucket": "nthh",
            "content_type": "application/json" if rel.endswith("json") else "application/vnd.pmtiles",
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "source": {"kind": "display_package", "dataset_id": dataset_id, "path": rel},
        })
    plan.write_text(json.dumps(data))
    return package


class PrepareTests(unittest.TestCase):
    def test_parquet_decimal_fields_are_detected_without_changing_values_or_precision(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "decimals.parquet"
            bbox_type = pa.struct([
                pa.field("xmin", pa.float64()), pa.field("ymin", pa.float64()),
                pa.field("xmax", pa.float64()), pa.field("ymax", pa.float64()),
            ])
            table = pa.table({
                "id": pa.array([1, 2, 3, 4], type=pa.int64()),
                "width_mean": pa.array([
                    Decimal("97.00000000000"), Decimal("-0.00000000001"),
                    Decimal("0.00000000000"), None,
                ], type=pa.decimal128(30, 11)),
                "precision_value": pa.array([
                    Decimal("12345678901234567890.123456789012345678"),
                    Decimal("-0.000000000000000001"), Decimal("0"), None,
                ], type=pa.decimal128(38, 18)),
                "bbox": pa.array([{"xmin": 1.0, "ymin": 2.0, "xmax": 3.0, "ymax": 4.0}] * 4, type=bbox_type),
                "geometry": pa.array([b"wkb"] * 4, type=pa.binary()),
            })
            metadata = {
                "version": "1.0.0", "primary_column": "geometry",
                "columns": {"geometry": {
                    "encoding": "WKB", "geometry_types": ["LineString"], "bbox": [1, 2, 3, 4],
                    "covering": {"bbox": {axis: ["bbox", axis] for axis in ("xmin", "ymin", "xmax", "ymax")}},
                }},
            }
            pq.write_table(table.replace_schema_metadata({b"geo": json.dumps(metadata).encode()}), path)

            info, schema_names, row_count = _read_parquet(path)
            self.assertEqual(info["decimal_fields"], ["width_mean", "precision_value"])
            self.assertEqual(schema_names, ["id", "width_mean", "precision_value", "bbox", "geometry"])
            self.assertEqual(row_count, 4)
            round_tripped = pq.read_table(path)
            self.assertEqual(round_tripped["width_mean"].to_pylist(), [
                Decimal("97.00000000000"), Decimal("-0.00000000001"), Decimal("0E-11"), None,
            ])
            self.assertEqual(round_tripped["precision_value"].to_pylist(), [
                Decimal("12345678901234567890.123456789012345678"),
                Decimal("-1E-18"), Decimal("0E-18"), None,
            ])

    def test_build_config_maps_exact_files_and_uses_canonical_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            config = build_config(root, plan, packages, gee_evidence_path=None)
            self.assertEqual(len(config["objects"]), 10)
            viewer = config["viewer"]
            self.assertIsNone(viewer["object_origin"])
            self.assertEqual(viewer["max_features"], 1500)
            datasets = {item["id"]: item for item in viewer["datasets"]}
            self.assertEqual(datasets["grwl"]["title"], "grwl release title")
            self.assertEqual(datasets["grwl"]["layers"][0]["source_layer"], "display")
            self.assertEqual(datasets["river-plastic-inputs"]["layers"][0]["geometry_type"], "point")
            self.assertEqual(datasets["hydrolakes"]["layers"][0]["format"], "geoparquet")
            self.assertEqual(datasets["hydrolakes"]["layers"][0]["covering"]["xmin"], "bbox.xmin")
            self.assertEqual(len(datasets["lakeatlas"]["layers"]), 2)
            self.assertTrue(all(item["state"] == "prepared" for item in list(datasets.values())[:5]))
            self.assertEqual(datasets["gdw"]["state"], "unavailable")
            self.assertIn("blocked by HTTP 403", datasets["gdw"]["unavailable_reason"])
            self.assertEqual(datasets["swot_prior_lake_database"]["gee"]["status"], "not_audited")
            self.assertNotIn(str(root), json.dumps(viewer))
            self.assertTrue(all("path" in item for item in config["objects"].values()))

    def test_missing_or_tampered_planned_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            first = json.loads(plan.read_text())["files"][0]
            (packages[first["source"]["dataset_id"]] / first["source"]["path"]).unlink()
            with self.assertRaisesRegex(PrepareError, "missing"):
                build_config(root, plan, packages, gee_evidence_path=None)

    def test_display_pmtiles_keeps_analytic_linkage_and_stable_layer_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            display = add_display_fixture(root, plan, packages)
            config = build_config(root, plan, packages, gee_evidence_path=None, display_packages={"hydrolakes": display})
            layer = next(item for item in config["viewer"]["datasets"] if item["id"] == "hydrolakes")["layers"][0]
            self.assertEqual(layer["id"], "hydrolakes-1")
            self.assertEqual(layer["format"], "pmtiles")
            self.assertEqual(layer["analytic"]["format"], "geoparquet")
            self.assertEqual(layer["analytic"]["object_path"], "/nthh/hydrolakes/releases/v1-local-r3/assets/data.parquet")
            self.assertEqual(layer["attribute_fields"][0], "Hylak_id")

    def test_current_display_supersedes_legacy_embedded_pmtiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            display = add_display_fixture(root, plan, packages, dataset_id="grwl")
            config = build_config(root, plan, packages, gee_evidence_path=None, display_packages={"grwl": display})
            dataset = next(item for item in config["viewer"]["datasets"] if item["id"] == "grwl")
            self.assertEqual(len(dataset["layers"]), 1)
            layer = dataset["layers"][0]
            self.assertEqual(layer["id"], "grwl-display")
            self.assertIn("/grwl/display/display-v1/", layer["object_path"])
            self.assertEqual(layer["analytic"]["object_path"], "/nthh/grwl/releases/summary-v01.02-local-r1/data/analytics.parquet")
            self.assertIn("/nthh/grwl/releases/summary-v01.02-local-r1/data/display.pmtiles", config["objects"])

    def test_display_release_slug_and_style_are_bound_to_the_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            display_release = "raw-v01.01-display-r1"
            display = add_display_fixture(root, plan, packages, display_release=display_release)
            config = build_config(root, plan, packages, gee_evidence_path=None, display_packages={"hydrolakes": display})
            layer = next(item for item in config["viewer"]["datasets"] if item["id"] == "hydrolakes")["layers"][0]
            self.assertIn(f"/display/{display_release}/tiles/hydrolakes.pmtiles", layer["object_path"])

    def test_display_release_rejects_unsafe_version_slugs(self):
        for release in ("raw..r1", "raw--r1", ".leading", "trailing-", "x" * 41):
            with self.subTest(release=release), tempfile.TemporaryDirectory() as temporary:
                root, plan, packages = fixture(Path(temporary))
                display = add_display_fixture(root, plan, packages, display_release=release)
                with self.assertRaisesRegex(PrepareError, "safe version slug"):
                    build_config(root, plan, packages, gee_evidence_path=None, display_packages={"hydrolakes": display})

    def test_display_asset_and_style_metadata_faults_are_rejected(self):
        cases = [
            ({"asset_changes": {"path": None}}, {}, "requires declared path"),
            ({"asset_changes": {"style_path": None}}, {}, "requires declared style_path"),
            ({"asset_changes": {"size_bytes": 9}}, {}, "metadata disagrees"),
            ({"asset_changes": {"max_zoom": -1}}, {}, "zoom range"),
            ({"asset_changes": {"source_layer": ""}}, {}, "source_layer is required"),
            ({"asset_changes": {"geometry_type": "polygonal"}}, {}, "geometry_type"),
            ({"asset_changes": {"id_field": ""}}, {}, "id_field is required"),
            ({}, {"style_changes": {"version": 7}}, "MapLibre style v8"),
            ({}, {"style_changes": {"sources": {"data": {"type": "vector", "url": "wrong.pmtiles"}}}}, "does not resolve"),
            ({}, {"style_changes": {"layers": [{"id": "bad", "type": "line", "source": "data", "source-layer": "lakes"}]}}, "matching source-layer/type"),
        ]
        for index, (asset_kwargs, style_kwargs, expected) in enumerate(cases):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root, plan, packages = fixture(Path(temporary))
                display = add_display_fixture(root, plan, packages, **asset_kwargs, **style_kwargs)
                with self.assertRaisesRegex(PrepareError, expected):
                    build_config(root, plan, packages, gee_evidence_path=None, display_packages={"hydrolakes": display})

    def test_display_binding_mismatch_missing_objects_and_duplicate_ids_fail(self):
        for kwargs, expected in [({"source_mismatch": True}, "source identity mismatches"),
                                 ({"duplicate": True}, "invalid display asset")]:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as temporary:
                root, plan, packages = fixture(Path(temporary))
                display = add_display_fixture(root, plan, packages, **kwargs)
                with self.assertRaisesRegex(PrepareError, expected):
                    build_config(root, plan, packages, gee_evidence_path=None, display_packages={"hydrolakes": display})
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            display = add_display_fixture(root, plan, packages)
            data = json.loads(plan.read_text())
            data["files"] = [item for item in data["files"] if not (item.get("source", {}).get("kind") == "display_package" and item["source"]["path"].endswith("pmtiles"))]
            plan.write_text(json.dumps(data))
            with self.assertRaisesRegex(PrepareError, "do not match display manifest"):
                build_config(root, plan, packages, gee_evidence_path=None, display_packages={"hydrolakes": display})

    def test_historical_plan_needs_explicit_legacy_mode_after_canonical_display_is_added(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            record_path = root / "datasets" / "hydrolakes" / "dataset.yaml"
            record = yaml.safe_load(record_path.read_text())
            record["publication"]["display"] = {"release": "display-v1", "manifest_path": "datasets/hydrolakes/display/display-v1/manifest.json", "manifest_sha256": "a" * 64}
            record_path.write_text(yaml.safe_dump(record))
            with self.assertRaisesRegex(PrepareError, "canonical display packages are missing"):
                build_config(root, plan, packages, gee_evidence_path=None)
            config = build_config(root, plan, packages, gee_evidence_path=None, legacy_plan=True)
            layer = next(item for item in config["viewer"]["datasets"] if item["id"] == "hydrolakes")["layers"][0]
            self.assertEqual(layer["format"], "geoparquet")
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            first = json.loads(plan.read_text())["files"][0]
            target = packages[first["source"]["dataset_id"]] / first["source"]["path"]
            target.write_bytes(b"tampered")
            with self.assertRaisesRegex(PrepareError, "mismatch"):
                build_config(root, plan, packages, gee_evidence_path=None)

    def test_symlink_duplicate_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            first = json.loads(plan.read_text())["files"][0]
            target = packages[first["source"]["dataset_id"]] / first["source"]["path"]
            real = target.with_suffix(".real")
            target.rename(real)
            target.symlink_to(real.name)
            with self.assertRaisesRegex(PrepareError, "symlink"):
                build_config(root, plan, packages, gee_evidence_path=None)
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            data = json.loads(plan.read_text())
            data["files"].append(data["files"][0])
            plan.write_text(json.dumps(data))
            with self.assertRaisesRegex(PrepareError, "duplicate"):
                build_config(root, plan, packages, gee_evidence_path=None)
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            data = json.loads(plan.read_text())
            data["files"][0]["object_key"] = "grwl/releases/../../outside"
            plan.write_text(json.dumps(data))
            with self.assertRaisesRegex(PrepareError, "unsafe object route"):
                build_config(root, plan, packages, gee_evidence_path=None)

    def test_output_refuses_existing_file_and_dangling_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "existing.json"
            output.write_text("keep")
            self.assertEqual(main(["--root", str(root), "--plan", str(root / "absent"), "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "keep")
            link = root / "dangling.json"
            link.symlink_to(root / "no-target")
            self.assertEqual(main(["--root", str(root), "--plan", str(root / "absent"), "--output", str(link)]), 2)

    def test_gee_evidence_requires_release_binding_and_exact_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            (root / "audit.json").write_text("{}")
            report = {
                "datasets": [
                    {
                        "dataset_id": "grwl",
                        "selected_release": "wrong-release",
                        "gee_status": "passed",
                        "gee_summary": "claimed",
                        "evidence": [{"path": "audit.json", "sha256": "bad"}],
                    }
                ]
            }
            gee = root / "gee.json"
            gee.write_text(json.dumps(report))
            with self.assertRaisesRegex(PrepareError, "release mismatch"):
                build_config(root, plan, packages, "gee.json")
            report["datasets"][0]["selected_release"] = RELEASES["grwl"]
            gee.write_text(json.dumps(report))
            with self.assertRaisesRegex(PrepareError, "evidence SHA-256 mismatch"):
                build_config(root, plan, packages, "gee.json")

    def test_legacy_source_cooperative_does_not_satisfy_required_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = fixture(Path(temporary))
            record_path = root / "datasets" / "grwl" / "dataset.yaml"
            record = yaml.safe_load(record_path.read_text())
            record["publication"]["source_cooperative"] = record["publication"].pop("source_coop")
            record_path.write_text(yaml.safe_dump(record))
            with self.assertRaisesRegex(PrepareError, "publication.source_coop"):
                _load_records(root)

    def test_plan_product_release_owner_and_id_are_bound_to_canonical(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            data = json.loads(plan.read_text())
            data["products"][0]["release"] = "stale-release"
            plan.write_text(json.dumps(data))
            with self.assertRaisesRegex(PrepareError, "release mismatch"):
                build_config(root, plan, packages, gee_evidence_path=None)
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            data = json.loads(plan.read_text())
            data["products"][0]["owner"] = "other-account"
            plan.write_text(json.dumps(data))
            with self.assertRaisesRegex(PrepareError, "owner mismatch"):
                build_config(root, plan, packages, gee_evidence_path=None)
        with tempfile.TemporaryDirectory() as temporary:
            root, plan, packages = fixture(Path(temporary))
            data = json.loads(plan.read_text())
            data["products"][0]["product_id"] = "other-product"
            plan.write_text(json.dumps(data))
            with self.assertRaisesRegex(PrepareError, "product_id mismatch"):
                build_config(root, plan, packages, gee_evidence_path=None)


if __name__ == "__main__":
    unittest.main()
