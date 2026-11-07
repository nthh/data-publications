"""Small independent source, winner, buffer, and decoded-tile oracle fixtures."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import LineString, MultiLineString
import shapely
from mapbox_vector_tile.Mapbox import vector_tile_pb2 as mvt
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grwl_width_oracle", ROOT / "datasets/grwl-raw/validate_width_overview.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def sample(cell, fid, width, valid, qx, qy, lon, lat):
    return {"cell": cell, "feature_id": fid, "width_m": width, "width_valid": valid,
            "qx": int(qx), "qy": int(qy), "longitude": lon, "latitude": lat}


def write_samples(path, rows):
    pq.write_table(pa.Table.from_pylist(rows, schema=oracle.SAMPLE_SCHEMA), path)


def zigzag(value):
    return (value << 1) ^ (value >> 31)


def encode_point_tile(features, *, wrong_layer=False):
    tile = mvt.tile()
    layer = tile.layers.add()
    layer.name = "wrong" if wrong_layer else "grwl_width_overview"
    layer.version = 2
    layer.extent = 4096
    layer.keys.extend(["width_m", "width_valid"])
    for item in features:
        feature = layer.features.add()
        feature.id = item["feature_id"]
        feature.type = 1
        feature.geometry.extend([9, zigzag(item["x"]), zigzag(item["y"])])
        if item["width_m"] is not None:
            feature.tags.extend([0, len(layer.values)])
            layer.values.add().int_value = item["width_m"]
        feature.tags.extend([1, len(layer.values)])
        layer.values.add().bool_value = item["width_valid"]
    return gzip.compress(tile.SerializeToString(deterministic=True), mtime=0)


def write_archive(path, groups, *, mutate=None):
    with path.open("xb") as stream:
        writer = Writer(stream)
        for tileid in sorted(groups):
            rows = [dict(row) for row in groups[tileid]]
            if mutate is not None:
                rows = mutate(tileid, rows)
            if rows is None:
                continue
            writer.write_tile(tileid, encode_point_tile(rows))
        writer.finalize({"tile_type": TileType.MVT, "tile_compression": Compression.GZIP,
                         "min_lon_e7": -1800000000, "min_lat_e7": -850000000,
                         "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                         "center_zoom": 0, "center_lon_e7": 0, "center_lat_e7": 0},
                        {"name": "width fixture", "vector_layers": [{"id": "grwl_width_overview"}]})


class WidthOverviewOracleTests(unittest.TestCase):
    def test_first_nonempty_part_and_periodic_projection(self):
        geometries = [shapely.from_wkt("MULTILINESTRING (EMPTY, (179.9999 10, 10 20))"),
                      LineString([(-180, 0), (-179.9, 0)])]
        lon, lat = oracle.source_anchors([shapely.to_wkb(g) for g in geometries])
        self.assertEqual(lon.tolist(), [179.9999, -180.0])
        self.assertEqual(lat.tolist(), [10.0, 0.0])
        x, y, error = oracle.project_q(lon, lat)
        self.assertLess(error, 0.3)
        self.assertEqual(int(x[1]), 0)
        xp, _, _ = oracle.project_q(np.array([180.0]), np.array([0.0]))
        self.assertEqual(int(xp[0]), 0)

    def test_full_source_winner_priority_and_tampered_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for fid, lon, width in [(9, -60.0, 1), (8, -60.0, None),
                                    (7, -60.0, 200), (6, -60.0, 200),
                                    (5, 20.0, 1), (4, 20.0, None)]:
                records.append({"feature_id": fid, "width_m": width,
                                "width_valid": width is not None and width > 0 and width != 1,
                                "geometry": shapely.to_wkb(LineString([(lon, 0), (lon + 0.001, 0)]))})
            source = root / "source.parquet"
            pq.write_table(pa.Table.from_pylist(records), source)
            candidates = root / "candidates.parquet"
            count, error = oracle.write_source_candidates(source, candidates, len(records), 0.3)
            self.assertEqual(count, len(records))
            self.assertLess(error, 0.3)
            expected = root / "winners.parquet"
            with duckdb.connect() as db:
                oracle.external_winners(db, candidates, expected)
            rows = pq.read_table(expected).to_pylist()
            self.assertEqual({r["feature_id"] for r in rows}, {6, 4})
            self.assertEqual({r["feature_id"]: r["width_valid"] for r in rows}, {6: True, 4: False})
            good = root / "good.parquet"
            write_samples(good, rows)
            self.assertEqual(oracle.compare_tables(expected, good, "fixture"), 2)
            for name, altered in [("width", [dict(r, width_m=201) if r["feature_id"] == 6 else r for r in rows]),
                                  ("id", [dict(r, feature_id=99) if r["feature_id"] == 6 else r for r in rows]),
                                  ("omission", rows[:1])]:
                with self.subTest(name=name):
                    bad = root / f"bad-{name}.parquet"
                    write_samples(bad, altered)
                    with self.assertRaises(ValueError):
                        oracle.compare_tables(expected, bad, "fixture")

    def test_coarsening_uses_spatial_parent_not_row_major_shift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shift = 28 - 17
            qx = np.array([0, 1 << shift], dtype=np.uint32)
            qy = np.array([1 << shift, 1 << shift], dtype=np.uint32)
            cell = oracle.cells(qx, qy, 7)
            rows = [sample(int(cell[i]), i + 1, 10 + i, True, qx[i], qy[i], -180.0 + i * 0.001, 85.0)
                    for i in range(2)]
            incoming, expected = root / "incoming.parquet", root / "parent.parquet"
            write_samples(incoming, rows)
            with duckdb.connect() as db:
                oracle.external_winners(db, incoming, expected, target_zoom=6)
            result = pq.read_table(expected).to_pylist()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["feature_id"], 2)
            self.assertEqual(result[0]["cell"], int(oracle.cells(qx[1:2], qy[1:2], 6)[0]))

    def test_external_sort_streams_priority_groups_across_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qx = np.array([0, 1 << 11], dtype=np.uint32)
            qy = np.array([1 << 11, 1 << 11], dtype=np.uint32)
            cell = oracle.cells(qx, qy, 7)
            rows = [sample(int(cell[0]), fid, width, width not in (None, 1),
                           qx[0], qy[0], -180.0, 85.0)
                    for fid, width in [(9, 1), (8, None), (7, 20), (6, 20), (5, 10)]]
            rows.extend(sample(int(cell[1]), fid, width, False, qx[1], qy[1], -179.997, 85.0)
                        for fid, width in [(4, 1), (3, None)])
            incoming, expected = root / "incoming.parquet", root / "winner.parquet"
            write_samples(incoming, rows)
            prior_batch = oracle.BATCH
            oracle.BATCH = 2
            try:
                with duckdb.connect() as db:
                    selected = oracle.external_winners(db, incoming, expected)
            finally:
                oracle.BATCH = prior_batch
            self.assertEqual(selected, 2)
            self.assertEqual([row["feature_id"] for row in pq.read_table(expected).to_pylist()], [6, 3])
            self.assertFalse((root / "winner-ordered.parquet").exists())

    def test_buffers_and_every_decoded_tile_detect_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = []
            qx, qy, _ = oracle.project_q(np.array([0.0]), np.array([0.0]))
            for z in range(8):
                path = root / f"z{z}.parquet"
                write_samples(path, [sample(int(oracle.cells(qx, qy, z)[0]), 42, 200, True,
                                            qx[0], qy[0], 0.0, 0.0)])
                files.append(path)
                self.assertEqual(oracle.validate_sample(path, z), 1)
            occurrences = root / "occurrences.parquet"
            oracle.write_occurrences(files, occurrences)
            rows = pq.read_table(occurrences).to_pylist()
            groups = {}
            for row in rows:
                groups.setdefault(row["tileid"], []).append(row)
            # At every z>=1, lon=lat=0 lies exactly on four tile corners.
            self.assertEqual(len(groups), 1 + 7 * 4)
            self.assertEqual(len(groups), len(rows))
            sorted_path = root / "sorted.parquet"
            pq.write_table(pa.Table.from_pylist(sorted(rows, key=lambda r: (r["tileid"], r["feature_id"])),
                                                schema=oracle.OCCURRENCE_SCHEMA), sorted_path)
            criteria = {"overview": {"source_layer": "grwl_width_overview"},
                        "gates": {"maximum_compressed_overview_tile_bytes": 2097152}}
            archive = root / "good.pmtiles"
            write_archive(archive, groups)
            self.assertEqual(oracle.verify_tiles(archive, sorted_path, criteria)["point_occurrences"], len(rows))
            for name, mutation in [
                ("width", lambda tileid, items: [dict(row, width_m=201) for row in items] if tileid == 0 else items),
                ("id", lambda tileid, items: [dict(row, feature_id=43) for row in items] if tileid == 0 else items),
                ("omission", lambda tileid, items: None if tileid == 0 else items),
            ]:
                with self.subTest(name=name):
                    bad = root / f"bad-{name}.pmtiles"
                    write_archive(bad, groups, mutate=mutation)
                    with self.assertRaises(ValueError):
                        oracle.verify_tiles(bad, sorted_path, criteria)

    def test_z0_periodic_seam_has_two_local_placements_of_same_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qx, qy, _ = oracle.project_q(np.array([-180.0]), np.array([0.0]))
            paths = []
            for z in range(8):
                path = root / f"z{z}.parquet"
                write_samples(path, [sample(int(oracle.cells(qx, qy, z)[0]), 123, 80, True,
                                            qx[0], qy[0], -180.0, 0.0)])
                paths.append(path)
            occurrences = root / "occurrences.parquet"
            oracle.write_occurrences(paths, occurrences)
            rows = pq.read_table(occurrences).to_pylist()
            z0 = [row for row in rows if row["tileid"] == zxy_to_tileid(0, 0, 0)]
            self.assertEqual(len(z0), 2)
            self.assertEqual({row["feature_id"] for row in z0}, {123})
            self.assertEqual({row["x"] for row in z0}, {0, 4096})
            self.assertEqual({row["y"] for row in z0}, {2048})

    def test_manifest_scope_requires_exact_frozen_tile_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.parquet"
            source.write_bytes(b"fixture")
            digest = oracle.sha256(source)
            criteria = json.loads(oracle.CRITERIA.read_text())
            manifest = root / "manifest.json"
            for scope, key in (("pilot", "development_tiles"), ("heldout", "heldout_tiles")):
                manifest.write_text(json.dumps({"parquet_sha256": digest, "rows": 17,
                                                "tiles": [{"tile": name} for name in criteria[key]]}))
                self.assertEqual(oracle.scope_for_manifest(source, manifest, criteria)[:2], (scope, 17))
            manifest.write_text(json.dumps({"parquet_sha256": digest, "rows": 17,
                                            "tiles": [{"tile": name} for name in criteria["development_tiles"][:-1]]}))
            with self.assertRaises(ValueError):
                oracle.scope_for_manifest(source, manifest, criteria)

    def test_regional_source_records_must_match_manifest_tile_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.parquet"
            pq.write_table(pa.Table.from_pylist([{"source_tile": "NI15", "feature_id": 1,
                "width_m": 50, "width_valid": True,
                "geometry": shapely.to_wkb(LineString([(0, 0), (0.01, 0)]))}]), source)
            candidates = root / "candidates.parquet"
            self.assertEqual(oracle.write_source_candidates(source, candidates, 1, 0.3, {"NI15"})[0], 1)
            with self.assertRaises(ValueError):
                oracle.write_source_candidates(source, root / "wrong.parquet", 1, 0.3, {"NI16"})

    def test_integrated_small_source_to_every_tile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.parquet"
            pq.write_table(pa.Table.from_pylist([{"feature_id": 55, "width_m": 120,
                "width_valid": True,
                "geometry": shapely.to_wkb(LineString([(0, 0), (0.01, 0)]))}]), source)
            qx, qy, _ = oracle.project_q(np.array([0.0]), np.array([0.0]))
            samples = []
            for zoom in range(8):
                path = root / f"z{zoom}.parquet"
                write_samples(path, [sample(int(oracle.cells(qx, qy, zoom)[0]), 55, 120,
                                            True, qx[0], qy[0], 0.0, 0.0)])
                samples.append(path)
            occurrences = root / "occurrences.parquet"
            oracle.write_occurrences(samples, occurrences)
            groups = {}
            for row in pq.read_table(occurrences).to_pylist():
                groups.setdefault(row["tileid"], []).append(row)
            archive = root / "overview.pmtiles"
            write_archive(archive, groups)
            criteria = {"gates": {"independent_anchor_projection_tolerance_m": 0.3,
                                  "maximum_compressed_overview_tile_bytes": 2097152},
                        "overview": {"source_layer": "grwl_width_overview"}}
            scratch = root / "scratch"
            scratch.mkdir()
            rows, error, expected, tiles = oracle._verify_heavy(
                source, samples, archive, {str(z): 1 for z in range(8)}, 1, criteria, scratch)
            self.assertEqual(rows, 1)
            self.assertLess(error, 0.3)
            self.assertEqual(expected, tiles["point_occurrences"])


if __name__ == "__main__":
    unittest.main()
