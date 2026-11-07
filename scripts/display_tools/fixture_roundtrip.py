#!/usr/bin/env python3
"""Rebuild small point, line, and polygon PMTiles fixtures twice and compare bytes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pmtiles import reader as pmtiles_reader

from build_display import decode_features, sha256, stream_features

ROOT = Path(__file__).resolve().parents[2]
TIPPECANOE = shutil.which("tippecanoe") or "/opt/homebrew/bin/tippecanoe"
PMTILES = shutil.which("pmtiles") or "/opt/homebrew/bin/pmtiles"
GEOMETRIES = {
    "point": [shapely.Point(10, 20), shapely.Point(10.2, 20.2)],
    "line": [shapely.LineString([(10, 20), (10.1, 20.1)])],
    "polygon": [shapely.Polygon([(10, 20), (10.1, 20), (10.1, 20.1), (10, 20)])],
}


def write_source(path: Path, geometries: list[Any]) -> tuple[list[int], list[float]]:
    ids = [23 + i for i in range(len(geometries))]
    areas = [123.5 + i for i in range(len(geometries))]
    boxes = [{"xmin": geom.bounds[0], "ymin": geom.bounds[1], "xmax": geom.bounds[2], "ymax": geom.bounds[3]} for geom in geometries]
    table = pa.table({
        "ID": pa.array(ids, type=pa.int64()),
        "Lake_area": pa.array(areas, type=pa.float64()),
        "wkb_geometry": pa.array([shapely.to_wkb(geom) for geom in geometries], type=pa.binary()),
        "bbox": pa.array(boxes, type=pa.struct([
            pa.field("xmin", pa.float64()), pa.field("ymin", pa.float64()),
            pa.field("xmax", pa.float64()), pa.field("ymax", pa.float64()),
        ])),
    })
    pq.write_table(table, path)
    return ids, areas


def run_fixture_roundtrip() -> dict[str, Any]:
    for executable in (TIPPECANOE, PMTILES):
        if not Path(executable).is_file():
            raise FileNotFoundError(f"required native fixture tool not found: {executable}")
    version_result = subprocess.run([TIPPECANOE, "--version"], text=True, capture_output=True, check=True)
    tip_version = (version_result.stdout + version_result.stderr).strip()
    if tip_version != "tippecanoe v2.79.0":
        raise ValueError(f"unexpected Tippecanoe version: {tip_version}")
    tip_sha = sha256(Path(TIPPECANOE))
    pmtiles_sha = sha256(Path(PMTILES))
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="pmtiles-fixture-") as td:
        work = Path(td)
        scratch = work / ".scratch"
        scratch.mkdir()
        for geometry_name, geometries in GEOMETRIES.items():
            source = work / f"{geometry_name}.parquet"
            ids, areas = write_source(source, geometries)
            source_sha = sha256(source)
            stream = io.BytesIO()
            stream_features(source, "fixture", "ID", ["ID", "Lake_area"], "Lake_area", stream)
            input_bytes = stream.getvalue()
            archive_hashes = []
            maxzoom_counts = []
            for _ in range(2):
                for path in (work / "fixture.mbtiles", work / "fixture.pmtiles"):
                    path.unlink(missing_ok=True)
                shutil.rmtree(scratch)
                scratch.mkdir()
                cmd = [TIPPECANOE, "--quiet", "--output", "fixture.mbtiles", "--layer", "fixture",
                       "--name", "display-fixture", "--description", "deterministic test fixture",
                       "--minimum-zoom", "0", "--maximum-zoom", "12", "--base-zoom", "12",
                       "--full-detail", "12", "--low-detail", "12", "--minimum-detail", "12",
                       "--simplification", "1", "--no-feature-limit", "--no-tile-size-limit",
                       "--no-tiny-polygon-reduction", "--no-tiny-polygon-reduction-at-maximum-zoom",
                       "--temporary-directory", ".scratch", "/dev/stdin"]
                subprocess.run(cmd, input=input_bytes, cwd=work,
                               env={**os.environ, "TIPPECANOE_MAX_THREADS": "2"},
                               capture_output=True, check=True)
                subprocess.run([PMTILES, "convert", "fixture.mbtiles", "fixture.pmtiles"], cwd=work,
                               capture_output=True, check=True)
                subprocess.run([PMTILES, "verify", "fixture.pmtiles"], cwd=work,
                               capture_output=True, check=True)
                archive = work / "fixture.pmtiles"
                archive_hashes.append(sha256(archive))
                found: dict[int, dict[str, Any]] = {}
                with archive.open("rb") as archive_file:
                    get_bytes = pmtiles_reader.MmapSource(archive_file)
                    archive_reader = pmtiles_reader.Reader(get_bytes)
                    header = archive_reader.header()
                    metadata = archive_reader.metadata()
                    if header["min_zoom"] != 4 or header["max_zoom"] != 12:
                        raise ValueError(f"unexpected fixture zoom metadata: {header}")
                    if not any(layer.get("id") == "fixture" for layer in metadata.get("vector_layers", [])):
                        raise ValueError("fixture archive missing vector layer")
                    for (z, _, _), tile in pmtiles_reader.all_tiles(get_bytes):
                        if z == 12:
                            for feature in decode_features(tile, "fixture"):
                                found[int(feature["id"])] = feature.get("properties", {})
                if set(found) != set(ids):
                    raise ValueError(f"fixture source IDs do not roundtrip at maxzoom: {sorted(found)}")
                for fid, area in zip(ids, areas):
                    properties = found[fid]
                    if properties.get("ID") != fid or properties.get("Lake_area") != area:
                        raise ValueError(f"fixture selected attributes mismatch for ID {fid}: {properties}")
                maxzoom_counts.append(len(found))
            results[geometry_name] = {
                "source_sha256": source_sha,
                "source_ids": ids,
                "maxzoom_ids": maxzoom_counts,
                "pmtiles_sha256_rebuild_1": archive_hashes[0],
                "pmtiles_sha256_rebuild_2": archive_hashes[1],
                "byte_identical": archive_hashes[0] == archive_hashes[1],
            }
    return {
        "schema_version": 1,
        "fixture_scope": "synthetic point, line, and polygon GeoParquet; Tippecanoe/PMTiles build and validation repeated twice; not a production clean-checkout rebuild",
        "tippecanoe_version": tip_version,
        "tippecanoe_sha256": tip_sha,
        "tippecanoe_max_threads": 2,
        "pmtiles_cli_version": subprocess.run([PMTILES, "version"], text=True, capture_output=True, check=True).stdout.strip(),
        "pmtiles_cli_sha256": pmtiles_sha,
        "python_packages": {name: importlib.metadata.version(name) for name in ("pyarrow", "shapely", "numpy", "pmtiles")},
        "builder_sha256": sha256(ROOT / "scripts/display_tools/build_display.py"),
        "fixtures": results,
        "all_byte_identical": all(item["byte_identical"] for item in results.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional JSON report output path")
    args = parser.parse_args()
    report = run_fixture_roundtrip()
    rendered = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered)
    print(rendered, end="")
    if not report["all_byte_identical"]:
        raise SystemExit("fixture rebuilds produced different PMTiles bytes")


if __name__ == "__main__":
    main()
