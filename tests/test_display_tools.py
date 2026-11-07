from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "display_tools"))
import build_display as display


def write_fixture(path: Path, ids: tuple[int, ...], areas: tuple[float | None, ...], geometries):
    boxes = []
    for geom in geometries:
        bounds = geom.bounds
        boxes.append({"xmin": bounds[0], "ymin": bounds[1], "xmax": bounds[2], "ymax": bounds[3]})
    table = pa.table({
        "ID": pa.array(ids, type=pa.int64()),
        "Lake_area": pa.array(areas, type=pa.float64()),
        "Lake_name": pa.array([f"lake-{i}" for i in ids]),
        "wkb_geometry": pa.array([shapely.to_wkb(geom) for geom in geometries], type=pa.binary()),
        "bbox": pa.array(boxes, type=pa.struct([
            pa.field("xmin", pa.float64()), pa.field("ymin", pa.float64()),
            pa.field("xmax", pa.float64()), pa.field("ymax", pa.float64()),
        ])),
    })
    pq.write_table(table, path)


class DisplayToolTests(unittest.TestCase):
    def test_piecewise_minzoom_and_unknown_values(self):
        self.assertEqual([display.min_zoom(v) for v in (10000, 1000, 100, 10, 1, 0.1, 0, None, -1)],
                         [0, 2, 4, 6, 8, 10, 12, 12, 12])

    def test_stream_is_deterministic_and_preserves_exact_selected_props(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "fixture.parquet"
            write_fixture(source, (1, 2), (10001.0, None), [shapely.Point(1, 1), shapely.Point(2, 2)])
            first, second = io.BytesIO(), io.BytesIO()
            counts_a = display.stream_features(source, "layer", "ID", ["ID", "Lake_area", "Lake_name"], "Lake_area", first)
            counts_b = display.stream_features(source, "layer", "ID", ["ID", "Lake_area", "Lake_name"], "Lake_area", second)
            self.assertEqual(first.getvalue(), second.getvalue())
            self.assertEqual(counts_a, counts_b)
            self.assertEqual(counts_a["source_rows"], 2)
            self.assertEqual(counts_a["unique_ids"], 2)
            features = [json.loads(line) for line in first.getvalue().splitlines()]
            self.assertEqual(features[0]["id"], features[0]["properties"]["ID"])
            self.assertEqual(features[0]["tippecanoe"]["minzoom"], 0)
            self.assertEqual(features[1]["tippecanoe"]["minzoom"], 12)
            self.assertIsNone(features[1]["properties"]["Lake_area"])
            self.assertEqual(features[0]["properties"]["_src_xmin"], 1.0)

    def test_stream_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "duplicate.parquet"
            write_fixture(source, (7, 7), (2.0, 3.0), [shapely.Point(1, 1), shapely.Point(2, 2)])
            with self.assertRaisesRegex(ValueError, "duplicate source ID 7"):
                display.stream_features(source, "layer", "ID", ["ID", "Lake_area"], "Lake_area", io.BytesIO())

    def test_stream_rejects_missing_required_field(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "missing.parquet"
            pq.write_table(pa.table({"ID": [1], "wkb_geometry": [shapely.to_wkb(shapely.Point(0, 0))], "bbox": [None]}), source)
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                display.stream_features(source, "layer", "ID", ["ID", "Lake_area"], "Lake_area", io.BytesIO())

    def test_mvt_id_decoder_reads_feature_id(self):
        # Minimal protobuf MVT: Tile.layers=[Layer(name="l", features=[Feature(id=42)])].
        feature = b"\x08\x2a"
        layer = b"\x0a\x01l" + b"\x12" + bytes([len(feature)]) + feature
        tile = b"\x1a" + bytes([len(layer)]) + layer
        self.assertEqual(display.mvt_ids(tile), {42})

    def test_package_preflight_refuses_prepared_or_wrong_release_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "new-package"
            destination.mkdir()
            manifest = {"dataset_id": "lakeatlas", "analytic_release": "lakeatlas-v1.0-r2",
                        "display_release": "display-v1", "status": "prepared", "assets": []}
            (destination / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(FileExistsError, "prepared"):
                display.preflight_package(destination, "lakeatlas-pour-points")
            self.assertEqual(sorted(p.name for p in destination.iterdir()), ["manifest.json"])

            manifest["status"] = "provisional"
            for field, wrong in (("dataset_id", "wrong-dataset"),
                                 ("analytic_release", "wrong-release"),
                                 ("display_release", "display-v2")):
                manifest[field] = wrong
                (destination / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, field):
                    display.preflight_package(destination, "lakeatlas-pour-points")
                self.assertEqual(sorted(p.name for p in destination.iterdir()), ["manifest.json"])
                manifest[field] = {"dataset_id": "lakeatlas", "analytic_release": "lakeatlas-v1.0-r2",
                                   "display_release": "display-v1"}[field]

    def test_package_preflight_allows_sibling_asset_but_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "lakeatlas"
            destination.mkdir()
            manifest = {"dataset_id": "lakeatlas", "analytic_release": "lakeatlas-v1.0-r2",
                        "display_release": "display-v1", "status": "provisional",
                        "assets": [{"id": "lakeatlas-1"}]}
            (destination / "manifest.json").write_text(json.dumps(manifest))
            display.preflight_package(destination, "lakeatlas-pour-points")
            with self.assertRaisesRegex(FileExistsError, "already declared"):
                display.preflight_package(destination, "lakeatlas-polygons")

    def test_input_provenance_snapshots_exact_bytes_and_keeps_command_portable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            data_root = Path(td) / "data"
            code = root / "scripts/display_tools/build_display.py"
            lock = root / "datasets/grwl/uv.lock"
            tip_lock = root / "datasets/grwl/tippecanoe.lock.json"
            code.parent.mkdir(parents=True)
            lock.parent.mkdir(parents=True)
            code.write_bytes(b"fixture builder source\n")
            lock.write_bytes(b"fixture lock source\n")
            tip_lock.write_bytes(b"fixture tippecanoe lock\n")
            source = data_root / display.SOURCES["lakeatlas-pour-points"][0]
            source.parent.mkdir(parents=True)
            source.write_bytes(b"fixture source bytes")
            destination = data_root / "lakeatlas/display/display-v1"
            tip_binary, pmtiles_binary = Path(td) / "tippecanoe", Path(td) / "pmtiles"
            tip_binary.write_bytes(b"tippecanoe fixture binary")
            pmtiles_binary.write_bytes(b"pmtiles fixture binary")
            values = dict(key="lakeatlas-pour-points", destination=destination, source=source,
                          data_root=data_root, repository_root=root, tippecanoe_path=tip_binary,
                          pmtiles_path=pmtiles_binary, tippecanoe_version="tippecanoe v2.79.0",
                          pmtiles_version="pmtiles fixture", package_versions={"pyarrow": "23.0.1"},
                          environment_lock=lock, tippecanoe_argv=["tippecanoe", "--output", "<OUTPUT>/test.mbtiles"])
            provenance = display.write_input_provenance(**values)
            code_hash = display.sha256(code)
            code_snapshot = destination / provenance["builder_snapshot"]
            lock_snapshot = destination / provenance["environment_lock_snapshot"]
            recipe_snapshot = destination / provenance["tippecanoe"]["lock_snapshot"]
            self.assertEqual(code_snapshot.read_bytes(), code.read_bytes())
            self.assertEqual(display.sha256(code_snapshot), code_hash)
            self.assertEqual(lock_snapshot.read_bytes(), lock.read_bytes())
            self.assertEqual(recipe_snapshot.read_bytes(), tip_lock.read_bytes())
            self.assertEqual(provenance["source_asset"], display.SOURCES["lakeatlas-pour-points"][0])
            self.assertEqual(provenance["source_sha256"], display.sha256(source))
            self.assertNotIn(str(td), json.dumps(provenance))
            self.assertIn("<DATA_ROOT>", provenance["builder_argv"])
            self.assertEqual(provenance["environment_lock"], "datasets/grwl/uv.lock")
            self.assertEqual(provenance["tippecanoe_argv"], ["tippecanoe", "--output", "<OUTPUT>/test.mbtiles"])
            self.assertEqual(provenance["attribute_fields"][-4:],
                             ["_src_xmin", "_src_ymin", "_src_xmax", "_src_ymax"])
            report_path = destination / "reports/lakeatlas-pour-points.input-provenance.json"
            self.assertEqual(json.loads(report_path.read_text()), provenance)
            self.assertEqual(display.write_input_provenance(**values), provenance)

            external_source = Path(td) / "outside.parquet"
            external_source.write_bytes(b"external fixture source")
            external = dict(values, destination=data_root / "alternate/display-v1", source=external_source)
            external_provenance = display.write_input_provenance(**external)
            self.assertEqual(external_provenance["source_asset"], "<SOURCE_ASSET>")
            self.assertEqual(external_provenance["builder_argv"][-2:], ["--source", "<SOURCE_ASSET>"])
            self.assertNotIn(str(td), json.dumps(external_provenance))

            source.write_bytes(b"different bytes")
            with self.assertRaisesRegex(FileExistsError, "conflicts"):
                display.write_input_provenance(**values)

    def test_real_tippecanoe_pmtiles_roundtrips_point_line_polygon(self):
        tippecanoe = shutil.which("tippecanoe") or ("/opt/homebrew/bin/tippecanoe" if Path("/opt/homebrew/bin/tippecanoe").exists() else None)
        pmtiles = shutil.which("pmtiles") or ("/opt/homebrew/bin/pmtiles" if Path("/opt/homebrew/bin/pmtiles").exists() else None)
        if not tippecanoe or not pmtiles:
            self.skipTest("native Tippecanoe and pmtiles CLIs are not installed")
        from fixture_roundtrip import run_fixture_roundtrip
        report = run_fixture_roundtrip()
        self.assertTrue(report["all_byte_identical"])
        self.assertEqual(set(report["fixtures"]), {"point", "line", "polygon"})
        for result in report["fixtures"].values():
            self.assertEqual(result["maxzoom_ids"][0], result["maxzoom_ids"][1])
            self.assertTrue(result["byte_identical"])


if __name__ == "__main__":
    unittest.main()
