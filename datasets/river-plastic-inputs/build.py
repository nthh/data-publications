#!/usr/bin/env python3
"""Build the pinned river-plastic release locally. No uploads or GEE access."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import zipfile
from decimal import Decimal
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
from dataset_config import load_config, config_sha256
CONFIG = load_config()
CODE_FILES = ["build.py", "catalog.py", "validate.py", "serve.py", "dataset_config.py", "pyproject.toml", "uv.lock", "package.json", "package-lock.json"]


def sha256(path):
    return hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_source(path):
    raw = path.read_bytes()
    if (len(raw), hashlib.md5(raw).hexdigest(), hashlib.sha256(raw).hexdigest()) != (
        CONFIG["source_size"], CONFIG["source_md5"], CONFIG["source_sha256"]
    ):
        raise ValueError("Source size/checksum differs from the pinned release")
    with zipfile.ZipFile(path) as z:
        dbf, shp = z.read("PlasticRiverInputs.dbf"), z.read("PlasticRiverInputs.shp")
        prj = z.read("PlasticRiverInputs.prj").decode()
    if not CRS.from_wkt(prj).equals(CRS.from_epsg(4326), ignore_axis_order=True):
        raise ValueError("Unexpected source CRS")
    rows = struct.unpack_from("<I", dbf, 4)[0]
    header_size, row_size = struct.unpack_from("<HH", dbf, 8)
    fields, offset = [], 1
    for start in range(32, header_size - 1, 32):
        field = dbf[start:start + 32]
        name = field[:11].split(b"\0")[0].decode("ascii")
        kind, width, scale = chr(field[11]), field[16], field[17]
        if kind != "N":
            raise ValueError(f"Unexpected nonnumeric source field: {name}/{kind}")
        fields.append({"name": name, "width": width, "scale": scale, "offset": offset})
        offset += width
    if offset != row_size or rows != CONFIG["expected_rows"]:
        raise ValueError("Unexpected DBF schema/record count")
    values = {f["name"]: [] for f in fields}
    for i in range(rows):
        row = dbf[header_size + i * row_size:header_size + (i + 1) * row_size]
        if len(row) != row_size or row[0:1] != b" ":
            raise ValueError(f"Inactive or incomplete source row {i+1}")
        for field in fields:
            text = row[field["offset"]:field["offset"] + field["width"]].strip().decode("ascii")
            values[field["name"]].append(Decimal(text) if text and set(text) != {"*"} else None)
    if struct.unpack_from(">i", shp, 0)[0] != 9994 or struct.unpack_from("<i", shp, 32)[0] != 1:
        raise ValueError("Expected point shapefile")
    coordinates, cursor = [], 100
    while cursor < len(shp):
        record, words = struct.unpack_from(">ii", shp, cursor)
        kind, x, y = struct.unpack_from("<idd", shp, cursor + 8)
        if record != len(coordinates) + 1 or words != 10 or kind != 1:
            raise ValueError("Unexpected shapefile record layout")
        if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
            raise ValueError("Invalid point coordinate")
        coordinates.append((x, y))
        cursor += 8 + words * 2
    if len(coordinates) != rows or cursor != len(shp):
        raise ValueError("Shape/attribute row count mismatch")
    return fields, values, coordinates


def describe(name):
    if name == "source_row":
        return "One-based original shapefile/DBF row number; stable within the pinned source archive.", None
    if name in ("i_low", "i_mid", "i_high"):
        level = {"i_low": "lower", "i_mid": "midpoint", "i_high": "upper"}[name]
        return f"Annual modeled plastic input, {level} estimate (tonnes/year).", "tonnes/year"
    if name.startswith("i_"):
        _, level, month = name.split("_")
        return f"Modeled plastic input for {month}, {level} estimate (tonnes/month).", "tonnes/month"
    if name.startswith("runoff_"):
        return f"Mean catchment runoff for {name[7:]} (mm/day).", "mm/day"
    if name == "mpw":
        return "Mismanaged plastic waste produced in the catchment (kg/year).", "kg/year"
    if name == "area":
        return "Upstream catchment area (m²).", "m2"
    if name == "geometry":
        return "River input point; WKB Point, WGS84 longitude/latitude (OGC:CRS84).", None
    return "Per-feature xmin, ymin, xmax, ymax covering bounds in longitude/latitude.", None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".local/river-plastic-inputs/PlasticRiverInputs.zip")
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing outputs are never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output directory already exists; choose a new release or reproduction directory")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", str(HERE)], cwd=ROOT, text=True)
    if dirty.strip():
        raise SystemExit("Commit the product build inputs before building a release")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tippecanoe = shutil.which("tippecanoe")
    if not tippecanoe:
        raise SystemExit("tippecanoe is required")
    version = subprocess.run([tippecanoe, "--version"], capture_output=True, text=True, check=True)
    if (version.stdout + version.stderr).strip() != CONFIG["tippecanoe_version"]:
        raise SystemExit("Unexpected tippecanoe version; review and pin before building")
    fields, values, coordinates = read_source(args.source)
    count = len(coordinates)
    x, y = np.array(coordinates).T
    points = gpd.GeoSeries(gpd.points_from_xy(x, y), crs="OGC:CRS84")
    order = np.argsort(points.hilbert_distance(level=16).to_numpy(), kind="stable")
    columns = {"source_row": pa.array(np.arange(1, count+1), type=pa.int32())}
    for field in fields:
        precision = field["width"] - (1 if field["scale"] else 0)
        columns[field["name"]] = pa.array(values[field["name"]], type=pa.decimal128(precision, field["scale"]))
    columns["geometry"] = pa.array([struct.pack("<BIdd", 1, 1, px, py) for px, py in coordinates], type=pa.binary())
    columns["bbox"] = pa.StructArray.from_arrays([pa.array(x), pa.array(y), pa.array(x), pa.array(y)], names=["xmin", "ymin", "xmax", "ymax"])
    bbox = [float(x.min()), float(y.min()), float(x.max()), float(y.max())]
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": ["Point"], "crs": CRS.from_user_input("OGC:CRS84").to_json_dict(),
        "bbox": bbox, "covering": {"bbox": {key: ["bbox", key] for key in ("xmin", "ymin", "xmax", "ymax")}}
    }}}
    table = pa.table(columns).take(pa.array(order)).replace_schema_metadata({
        b"geo": json.dumps(geo, separators=(",", ":")).encode(),
        b"folia:source_doi": CONFIG["source_doi"].encode(),
        b"folia:source_sha256": CONFIG["source_sha256"].encode(),
    })
    args.output.mkdir(parents=True)
    shutil.copyfile(HERE / "dataset.yaml", args.output / "dataset.yaml")
    collection = args.output / CONFIG["id"]
    collection.mkdir()
    parquet = collection / "river-plastic-inputs.parquet"
    pq.write_table(table, parquet, compression="zstd", compression_level=9, row_group_size=CONFIG["row_group_size"], write_statistics=True, version="2.6")
    schema = []
    for field in table.schema:
        description, unit = describe(field.name)
        schema.append({"name": field.name, "type": str(field.type), "description": description, "unit": unit})
    write_json(collection / "schema.json", schema)
    missing_rows = [i+1 for i, value in enumerate(values["i_mid"]) if value is None]
    if missing_rows != CONFIG["expected_missing_estimate_rows"]:
        raise ValueError("Unexpected missing-estimate rows")
    locations = defaultdict(list)
    for ordinal, coordinate in enumerate(coordinates, 1):
        locations[coordinate].append(ordinal)
    coincident = [rows for rows in locations.values() if len(rows) > 1]
    quality = {"distinct_coordinates": len(locations), "coincident_coordinate_groups": len(coincident),
               "coincident_source_rows": coincident,
               "coincident_handling": "Retain all source records and multiplicity. Coincident points are not duplicate records to remove.",
               "missing_estimate_source_rows": missing_rows,
               "null_counts": {name: data.count(None) for name, data in values.items() if any(v is None for v in data)},
               "source_null_encoding": "Numeric DBF fields filled with asterisks are preserved as null, not zero.",
               "independent_check": "GDAL/pyogrio reads the same four rows as null; catchment area, waste production and geometry remain populated.",
               "encoding_reference": "https://github.com/OSGeo/shapelib/blob/master/dbfopen.c"}
    write_json(collection / "quality.json", quality)
    geojson = args.output / "tiles-input.geojsonl"
    with geojson.open("w") as stream:
        for i in order:
            properties = {"source_row": int(i)+1}
            for name in CONFIG["pmtiles_fields"][1:]:
                properties[name] = None if values[name][i] is None else float(values[name][i])
            stream.write(json.dumps({"type": "Feature", "id": int(i)+1, "properties": properties,
                                    "geometry": {"type": "Point", "coordinates": coordinates[i]}}, separators=(",", ":")) + "\n")
    tiles = collection / "river-plastic-inputs.pmtiles"
    command = ["tippecanoe", "--quiet", "--output", str(tiles.relative_to(args.output)), "--layer", "river_inputs", "--name", CONFIG["title"],
               "--description", "2010 modeled annual river plastic input; low zooms thin points. Use GeoParquet for totals.",
               "--attribution", "Lebreton et al. (2017), CC BY 4.0",
               "--maximum-zoom", str(CONFIG["pmtiles_maxzoom"]), "--minimum-zoom", "0", "--drop-densest-as-needed",
               "--extend-zooms-if-still-dropping", "--use-attribute-for-id", "source_row", geojson.name]
    subprocess.run(command, cwd=args.output, env={**os.environ, "TIPPECANOE_MAX_THREADS": "2"}, check=True)
    geojson.unlink()
    from catalog import build_catalog
    build_catalog(args.output, table, schema, bbox, revision)
    assets = {}
    for path in sorted(args.output.rglob("*")):
        if path.is_file():
            assets[path.relative_to(args.output).as_posix()] = {"size_bytes": path.stat().st_size, "sha256": sha256(path)}
    annual = {name: str(sum((v for v in values[name] if v is not None), Decimal(0))) for name in ("i_low", "i_mid", "i_high")}
    manifest = {"status": "local_prepared_not_published", "dataset": CONFIG["id"], "source": CONFIG,
                "release": CONFIG["release"], "conversion_git_commit": revision,
                "dataset_record_sha256_at_build": sha256(HERE / "dataset.yaml"),
                "effective_config_sha256": config_sha256(CONFIG), "build_input_sha256": {name: sha256(HERE/name) for name in CODE_FILES},
                "environment": {"python": platform.python_version(), "packages": {name: importlib.metadata.version(name) for name in
                                ("pyarrow", "geopandas", "shapely", "numpy", "pyproj", "matplotlib", "pmtiles", "mapbox-vector-tile", "rashid")},
                                "tippecanoe_version": CONFIG["tippecanoe_version"], "tippecanoe_sha256": sha256(tippecanoe), "tippecanoe_max_threads": 2},
                "records": count, "source_quality": quality, "original_numeric_fields": len(fields), "bbox": bbox, "annual_input_totals_tonnes": annual,
                "assets": assets, "limitations": ["Local preparation only; no remote publication or registry acceptance.",
                "Decimal values and coordinates are preserved from the source; this does not establish scientific accuracy of the model.",
                "PMTiles quantizes positions, stores display attributes as doubles, and thins lower zooms. Use GeoParquet for analysis."]}
    write_json(args.output / "manifest.json", manifest)
    print(json.dumps({"output": str(args.output), "records": count, "data_bytes": parquet.stat().st_size + tiles.stat().st_size, "git_commit": revision}, indent=2))


if __name__ == "__main__":
    main()
