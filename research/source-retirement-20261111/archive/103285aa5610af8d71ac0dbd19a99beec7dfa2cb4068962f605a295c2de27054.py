#!/usr/bin/env python3
"""Independently compare every pinned File Geodatabase row with GeoParquet."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import shapely
from source_schema import verify_source_schema

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "source-inspection.json").read_text())
LAYER = LOCK["layers"][0]["name"]
GEOMETRY = LOCK["layers"][0]["geometry_name"]
GEOMETRY_TYPE_NAMES = {
    0: "Point",
    1: "LineString",
    2: "LinearRing",
    3: "Polygon",
    4: "MultiPoint",
    5: "MultiLineString",
    6: "MultiPolygon",
    7: "GeometryCollection",
}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            sha.update(block)
    return sha.hexdigest()


def source_vfs(path: Path) -> str:
    return f"/vsizip/{path.resolve()}/{LOCK['gdb_path_in_zip']}"


def observed_geometry_types(wkb: list[bytes | None]) -> dict[str, int]:
    geometries = shapely.from_wkb(wkb)
    counts: dict[str, int] = {}
    for type_id in shapely.get_type_id(geometries):
        if type_id >= 0:
            name = GEOMETRY_TYPE_NAMES[int(type_id)]
            counts[name] = counts.get(name, 0) + 1
    return counts


def compare(source_batch: pa.RecordBatch, output_batch: pa.RecordBatch, first_row: int) -> None:
    need(source_batch.num_rows == output_batch.num_rows, f"row count changed at source row {first_row}")
    need(output_batch.schema.names == source_batch.schema.names + ["source_row"], "output source field/geometry schema differs")
    for name, source_column in zip(source_batch.schema.names, source_batch.columns, strict=True):
        actual = output_batch.column(name)
        if name == GEOMETRY:
            # Compare raw WKB byte strings, not topological equality.
            source_values = source_column.to_pylist()
            actual_values = actual.to_pylist()
            need(source_values == actual_values, f"geometry WKB differs at source row {first_row}")
        else:
            need(source_column.equals(actual), f"source field {name} differs at source row {first_row}")
    expected_rows = pa.array(range(first_row, first_row + source_batch.num_rows), type=pa.int64())
    need(output_batch.column("source_row").equals(expected_rows), f"source_row ordinal differs at {first_row}")


def validate(source: Path, release: Path) -> dict[str, object]:
    source = source.resolve()
    release = release.resolve()
    manifest = json.loads((release / "manifest.json").read_text())
    parquet_path = release / "free-flowing-rivers/free-flowing-rivers-figshare-v1.parquet"
    pin = LOCK["archive"]
    need(source.stat().st_size == pin["size_bytes"], "source archive size differs")
    need(digest(source) == pin["sha256"], "source archive SHA-256 differs")
    need(manifest["source"] == LOCK, "manifest source inspection differs")
    need(manifest["source_metadata_sha256"] == digest(HERE / "source-metadata.json"), "source API metadata hash differs")
    need(digest(release / "source-metadata.json") == manifest["source_metadata_sha256"], "release source API metadata differs")
    need(digest(release / "source-inspection.json") == digest(HERE / "source-inspection.json"), "release source inspection differs")
    need(digest(release / "dataset.yaml") == manifest["dataset_record_sha256"], "release dataset record snapshot differs")
    need(manifest["records"] == LOCK["layers"][0]["feature_count"], "manifest record count differs")
    for name, record in manifest["assets"].items():
        asset_path = release / name
        need(asset_path.stat().st_size == record["size_bytes"] and digest(asset_path) == record["sha256"], f"release asset hash differs: {name}")
    asset = manifest["assets"][parquet_path.relative_to(release).as_posix()]
    need(json.loads((release / "free-flowing-rivers/field-dictionary.json").read_text()) == LOCK["field_dictionary"], "release field dictionary differs from producer inspection")
    for name, expected_hash in manifest["build_input_sha256"].items():
        need(digest(HERE / name) == expected_hash, f"build input changed: {name}")
    pf = pq.ParquetFile(parquet_path)
    need(pf.metadata.num_rows == manifest["records"], "Parquet row count differs")
    need(pf.metadata.num_row_groups > 1, "expected multiple bounded row groups")
    geo = json.loads(pf.metadata.metadata[b"geo"])
    need(geo["version"] == "1.1.0", "GeoParquet version differs")
    need(geo["primary_column"] == GEOMETRY, "GeoParquet primary geometry column differs")
    geometry = geo["columns"][GEOMETRY]
    need(geometry["encoding"] == "WKB" and geometry["geometry_types"], "GeoParquet geometry encoding/type differs")
    crs = geometry["crs"]
    need(crs["id"] == {"authority": "EPSG", "code": 4326}, "GeoParquet CRS differs")
    need(geometry["bbox"] == LOCK["layers"][0]["total_bounds"], "GeoParquet bbox differs from source bounds")
    for group_no in range(pf.metadata.num_row_groups):
        group = pf.metadata.row_group(group_no)
        need(group.num_rows <= 4096, f"oversized Parquet row group {group_no}")
        columns = {group.column(i).path_in_schema: group.column(i) for i in range(group.num_columns)}
        ordinal = columns["source_row"].statistics
        need(ordinal is not None and ordinal.has_min_max, f"missing source_row statistics in group {group_no}")
        need(ordinal.min == group_no * 4096 + 1, f"source_row minimum differs in group {group_no}")

    feature_count = 0
    source_null_counts: dict[str, int] = {}
    geometry_counts: dict[str, int] = {}
    verified_schema = False
    with pyogrio.open_arrow(source_vfs(source), layer=LAYER, return_fids=True, batch_size=4096, use_pyarrow=True) as (meta, reader):
        need(meta["crs"] == "EPSG:4326", "source CRS changed")
        for source_batch, output_batch in zip(reader, pf.iter_batches(batch_size=4096), strict=True):
            if not verified_schema:
                verify_source_schema(source_batch.schema)
                verified_schema = True
            compare(source_batch, output_batch, feature_count + 1)
            for name, count in observed_geometry_types(output_batch.column(GEOMETRY).to_pylist()).items():
                geometry_counts[name] = geometry_counts.get(name, 0) + count
            for name, column in zip(source_batch.schema.names, source_batch.columns, strict=True):
                source_null_counts[name] = source_null_counts.get(name, 0) + column.null_count
            feature_count += source_batch.num_rows
    need(feature_count == manifest["records"], "source stream ended before expected records")
    need(source_null_counts == manifest["null_counts"], "source null counts differ from build manifest")
    need(geometry_counts == manifest["geometry_type_counts"], "observed WKB geometry type counts differ from build manifest")
    need(sorted(geometry_counts) == geometry["geometry_types"], "GeoParquet geometry_types differ from observed output WKB")
    return {
        "status": "passed",
        "records": feature_count,
        "source_attribute_fields": len(LOCK["layers"][0]["fields"]),
        "source_attribute_cells_compared": feature_count * len(LOCK["layers"][0]["fields"]),
        "source_fid_records_compared": feature_count,
        "geometry_wkb_records_compared": feature_count,
        "crs": "EPSG:4326",
        "row_groups": pf.metadata.num_row_groups,
        "source_sha256": pin["sha256"],
        "geoparquet_sha256": asset["sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report and args.report.exists():
        raise SystemExit(f"Refusing to overwrite validation report: {args.report}")
    try:
        result = validate(args.source, args.release)
    except Exception as error:
        result = {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "source": str(args.source),
            "release": str(args.release),
        }
        text = json.dumps(result, indent=2) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x") as report:
                report.write(text)
        print(text, end="")
        raise SystemExit(1) from error
    text = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x") as report:
            report.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
