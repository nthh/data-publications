#!/usr/bin/env python3
"""Check full source parity, GeoParquet/PMTiles bytes, catalog conformance and HTTP reads."""
from __future__ import annotations

import argparse
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
from collections import Counter, defaultdict
import threading
import urllib.request
import zipfile
import yaml

import duckdb
import geopandas as gpd
import mapbox_vector_tile
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely
from pmtiles.reader import Reader, all_tiles
from pmtiles.tile import Compression

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
from dataset_config import load_config, config_sha256
CONFIG = load_config()
PMTILES_MIN_ZOOM = 0  # build.py explicitly passes --minimum-zoom 0.


def require(value, message):
    if not value:
        raise ValueError(message)


def dbf_decimal_type(width, scale):
    """Return the exact Arrow decimal type implied by a DBF Numeric descriptor."""
    if not isinstance(width, int) or not isinstance(scale, int) or width < 1 or scale < 0:
        raise ValueError(f"Invalid DBF Numeric width/scale: {width!r}/{scale!r}")
    precision = width - (1 if scale else 0)  # The DBF width includes the decimal point when scale > 0.
    if precision < 1 or precision > 38 or scale > precision:
        raise ValueError(f"DBF Numeric width/scale cannot fit decimal128: {width}/{scale}")
    return pa.decimal128(precision, scale)


def require_dbf_decimal_type(name, arrow_type, width, scale):
    expected = dbf_decimal_type(width, scale)
    require(arrow_type == expected,
            f"Source decimal type differs for {name}: expected {expected}, found {arrow_type}")


def require_pmtiles_zoom_range(header):
    require(header.get("min_zoom") == PMTILES_MIN_ZOOM,
            f"PMTiles minimum zoom differs: expected {PMTILES_MIN_ZOOM}, found {header.get('min_zoom')}")
    expected_max = CONFIG["pmtiles_maxzoom"]
    require(header.get("max_zoom") == expected_max,
            f"PMTiles maximum zoom differs: expected {expected_max}, found {header.get('max_zoom')}")


def validate(root, source, http=False):
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    require(manifest["source"] == CONFIG and manifest["effective_config_sha256"] == config_sha256(CONFIG),
            "Effective source/build settings changed")
    record_bytes = (root / "dataset.yaml").read_bytes()
    require(hashlib.sha256(record_bytes).hexdigest() == manifest["dataset_record_sha256_at_build"],
            "Canonical record snapshot changed")
    record = yaml.safe_load(record_bytes)
    recorded_config = {"id": record["id"], "title": record["title"], **record["source"], **record["build"]}
    require(recorded_config == manifest["source"], "Canonical record snapshot and build settings differ")
    raw = source.read_bytes()
    require(len(raw) == CONFIG["source_size"], "Source size mismatch")
    require(hashlib.sha256(raw).hexdigest() == CONFIG["source_sha256"], "Source SHA-256 mismatch")
    require(hashlib.md5(raw).hexdigest() == CONFIG["source_md5"], "Source provider checksum mismatch")
    for name, expected in manifest["assets"].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "Manifest path escapes the release")
        require(path.stat().st_size == expected["size_bytes"], f"Asset size mismatch: {name}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"], f"Asset hash mismatch: {name}")
    for name, expected in manifest["build_input_sha256"].items():
        require(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, f"Build input changed: {name}")
    folder = root / CONFIG["id"]
    parquet = folder / "river-plastic-inputs.parquet"
    table = pq.read_table(parquet).sort_by("source_row")
    require(table.num_rows == CONFIG["expected_rows"], "Analytic row count mismatch")
    require(table["source_row"].to_pylist() == list(range(1, CONFIG["expected_rows"] + 1)), "Missing or duplicated identifiers")
    with zipfile.ZipFile(source) as archive:
        dbf, shp = archive.read("PlasticRiverInputs.dbf"), archive.read("PlasticRiverInputs.shp")
    source_rows = struct.unpack_from("<I", dbf, 4)[0]
    header_size, record_size = struct.unpack_from("<HH", dbf, 8)
    names, field_offset, value_checks, nulls = [], 1, 0, {}
    for position in range(32, header_size - 1, 32):
        descriptor = dbf[position:position+32]
        name = descriptor[:11].split(b"\0")[0].decode()
        names.append(name)
        width, scale = descriptor[16], descriptor[17]
        expected = []
        for i in range(source_rows):
            row_start = header_size + i*record_size
            require(dbf[row_start:row_start+1] == b" ", "Deleted source row")
            text = dbf[row_start+field_offset:row_start+field_offset+width].strip().decode()
            expected.append(Decimal(text) if text and set(text) != {"*"} else None)
        require(table[name].to_pylist() == expected, f"Source numeric values changed: {name}")
        require_dbf_decimal_type(name, table.schema.field(name).type, width, scale)
        nulls[name] = expected.count(None)
        value_checks += source_rows
        field_offset += width
    require(table.column_names == ["source_row", *names, "geometry", "bbox"], "Missing, renamed, or unexpected analytic columns")
    require([i+1 for i, value in enumerate(table["i_mid"].to_pylist()) if value is None] == CONFIG["expected_missing_estimate_rows"], "Missing estimates changed")
    source_coordinates = []
    cursor = 100
    while cursor < len(shp):
        number, words = struct.unpack_from(">ii", shp, cursor)
        require(number == len(source_coordinates)+1 and words == 10, "Unexpected source shape layout")
        kind, x, y = struct.unpack_from("<idd", shp, cursor+8)
        require(kind == 1, "Unexpected source geometry")
        source_coordinates.append((x, y))
        cursor += 8 + words*2
    geom = shapely.from_wkb(table["geometry"].to_pylist())
    xy = shapely.get_coordinates(geom)
    require(np.array_equal(xy, np.array(source_coordinates)), "Geometry changed during conversion")
    require(bool(shapely.is_valid(geom).all()) and bool((shapely.get_type_id(geom) == 0).all()), "Invalid/nonpoint geometry")
    for name, expected in (("xmin", xy[:, 0]), ("xmax", xy[:, 0]), ("ymin", xy[:, 1]), ("ymax", xy[:, 1])):
        require(np.array_equal(pc.struct_field(table["bbox"], name).to_numpy(), expected), f"Incorrect covering bounds: {name}")
    frame = gpd.read_parquet(parquet)
    distances = frame.geometry.hilbert_distance(level=16).to_numpy()
    require(bool(np.all(distances[:-1] <= distances[1:])), "Rows are not Hilbert ordered")
    metadata = pq.ParquetFile(parquet).metadata
    geo = json.loads(metadata.metadata[b"geo"])
    require(geo["version"] == "1.1.0" and geo["columns"]["geometry"]["encoding"] == "WKB", "Wrong GeoParquet version/encoding")
    for i in range(metadata.num_row_groups):
        group = metadata.row_group(i)
        require(group.num_rows <= 150000, "Oversized row group")
        stats = {group.column(j).path_in_schema: group.column(j).statistics for j in range(group.num_columns)}
        for name in ("xmin", "ymin", "xmax", "ymax"):
            require(stats["bbox." + name] is not None and stats["bbox." + name].has_min_max, "Missing spatial statistics")
    tile_path = folder / "river-plastic-inputs.pmtiles"
    payload = tile_path.read_bytes()
    require(payload[:8] == b"PMTiles\x03", "Expected PMTiles v3")
    get_bytes = lambda offset, length: payload[offset:offset+length]
    reader = Reader(get_bytes)
    header, tile_metadata = reader.header(), reader.metadata()
    require_pmtiles_zoom_range(header)
    require(any(layer["id"] == "river_inputs" for layer in tile_metadata["vector_layers"]), "Missing PMTiles layer")
    seen, tiles_checked, tile_features, max_error = set(), 0, 0, 0.0
    expected_columns = {name: table[name].to_pylist() for name in CONFIG["pmtiles_fields"]}
    for (z, tx, ty), tile in all_tiles(get_bytes):
        if z != header["max_zoom"]:
            continue
        if header["tile_compression"] == Compression.GZIP:
            tile = gzip.decompress(tile)
        elif header["tile_compression"] != Compression.NONE:
            raise ValueError("Unsupported tile compression")
        layers = mapbox_vector_tile.decode(tile, default_options={"y_coord_down": True})
        require(set(layers) == {"river_inputs"}, "Unexpected tile layer")
        layer = layers["river_inputs"]
        extent = layer["extent"]
        for feature in layer["features"]:
            identity = feature["id"]
            require(1 <= identity <= source_rows, "Invalid tile identifier")
            seen.add(identity); tile_features += 1
            for name in CONFIG["pmtiles_fields"][1:]:
                original, observed = expected_columns[name][identity-1], feature["properties"].get(name)
                require((original is None and observed is None) or
                        (original is not None and observed is not None and math.isclose(float(original), observed, rel_tol=1e-12, abs_tol=1e-9)),
                        f"Tile attribute differs from source: {identity}/{name}")
            require(feature["geometry"]["type"] == "Point", "Unexpected tile geometry")
            lon, lat = source_coordinates[identity-1]
            expected_x = ((lon+180)/360 * 2**z - tx) * extent
            expected_y = ((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2 * 2**z - ty) * extent
            observed_x, observed_y = feature["geometry"]["coordinates"]
            error = max(abs(expected_x-observed_x), abs(expected_y-observed_y))
            max_error = max(max_error, error)
            require(error <= 1.01, f"Excess tile quantization error: {identity}/{error}")
        tiles_checked += 1
    require(seen == set(range(1, source_rows+1)), f"Maximum zoom lost {source_rows-len(seen)} source identifiers")
    subprocess.run(["pmtiles", "verify", str(tile_path)], check=True, capture_output=True, text=True)
    result = subprocess.run([str(Path(sys.executable).parent / "rashid"), "check", str(root), "--schema", "--data-scope", "local", "--json"],
                            capture_output=True, text=True)
    try:
        rashid = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ValueError("Portolan validator did not return a JSON report: " + result.stderr[:500])
    if result.returncode:
        print(json.dumps(rashid, indent=2))
        raise ValueError("Portolan/STAC validation failed")
    coordinate_counts = Counter(source_coordinates)
    quality = json.loads((folder / "quality.json").read_text())
    require(quality["distinct_coordinates"] == len(coordinate_counts), "Distinct coordinate count differs")
    require(quality["coincident_coordinate_groups"] == sum(n > 1 for n in coordinate_counts.values()), "Coincident group count differs")
    groups = defaultdict(list)
    for ordinal, coordinate in enumerate(source_coordinates, 1):
        groups[coordinate].append(ordinal)
    require(quality["coincident_source_rows"] == [rows for rows in groups.values() if len(rows) > 1],
            "Coincident group membership differs from source")
    require(quality == manifest["source_quality"], "Source quality differs from manifest")
    report = {"status": "passed", "release_manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
              "source_quality": quality, "publication_status": "local_only", "source_rows": source_rows,
              "numeric_fields": len(names), "exact_numeric_value_comparisons": value_checks,
              "exact_geometry_comparisons": len(source_coordinates), "null_counts": nulls,
              "geoparquet": {"version": "1.1.0", "row_groups": metadata.num_row_groups, "rows": table.num_rows, "hilbert_ordered": True},
              "pmtiles": {"max_zoom": header["max_zoom"], "tiles_checked_at_max_zoom": tiles_checked,
                          "features_including_tile_buffer_duplicates": tile_features, "unique_source_identifiers": len(seen),
                          "maximum_quantization_error_tile_units": max_error, "structure_verified": True},
              "rashid": rashid,
              "http": {"status": "not_run", "scope": "Local server only; no remote host is certified."}}
    if http:
        from serve import server
        with server(root) as httpd:
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{httpd.server_port}/"
            url = base + CONFIG["id"] + "/river-plastic-inputs.parquet"
            try:
                request = urllib.request.Request(url, headers={"Range": "bytes=0-3", "Origin": "https://example.org"})
                with urllib.request.urlopen(request) as response:
                    require(response.status == 206 and response.read() == b"PAR1", "Range request failed")
                    require(response.headers.get("Access-Control-Allow-Origin") == "*", "CORS header missing")
                tile_request = urllib.request.Request(base + CONFIG["id"] + "/river-plastic-inputs.pmtiles", headers={"Range": "bytes=0-126"})
                with urllib.request.urlopen(tile_request) as response:
                    require(response.status == 206 and response.read() == payload[:127], "PMTiles range request failed")
                with duckdb.connect() as con:
                    con.execute("LOAD httpfs")
                    remote = con.execute("SELECT source_row, i_mid FROM read_parquet(?) WHERE bbox.xmin BETWEEN 100 AND 110 AND bbox.ymin BETWEEN 0 AND 20 ORDER BY source_row", [url]).fetchall()
                expected = [(i+1, expected_columns["i_mid"][i]) for i, (lon, lat) in enumerate(source_coordinates) if 100 <= lon <= 110 and 0 <= lat <= 20]
                require(remote == expected and len(remote) > 0, "HTTP subset query differs from original data")
                report["http"] = {"status": "passed", "parquet_range": "206 + PAR1", "pmtiles_range": "206 + exact header",
                                  "cors": "*", "duckdb_subset_rows": len(remote), "scope": "Loopback server only; future remote hosting remains untested."}
            finally:
                httpd.shutdown(); worker.join()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source", type=Path, default=ROOT / ".local/river-plastic-inputs/PlasticRiverInputs.zip")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.directory, args.source, args.http)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "source_rows", "exact_numeric_value_comparisons", "geoparquet", "pmtiles", "http")}, indent=2))


if __name__ == "__main__":
    main()
