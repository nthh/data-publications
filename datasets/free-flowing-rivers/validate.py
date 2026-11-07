#!/usr/bin/env python3
"""Independently compare every pinned File Geodatabase row with GeoParquet."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
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
ROW_GROUP_ROWS = 4096


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


def _parquet_leaf_arrays(batch: pa.RecordBatch) -> dict[str, pa.Array]:
    leaves: dict[str, pa.Array] = {}

    def add(prefix: str, array: pa.Array, data_type: pa.DataType) -> None:
        if pa.types.is_struct(data_type):
            for index, field in enumerate(data_type):
                add(f"{prefix}.{field.name}", array.field(index), field.type)
        else:
            leaves[prefix] = array

    for field in batch.schema:
        add(field.name, batch.column(field.name), field.type)
    return leaves


def _same_stat(actual: object, expected: object) -> bool:
    if isinstance(actual, float) and isinstance(expected, float):
        if math.isnan(actual) and math.isnan(expected):
            return True
    return actual == expected


def check_row_group_statistics(pf: pq.ParquetFile, expected_group_rows: int = ROW_GROUP_ROWS) -> dict[str, int]:
    """Check footer statistics presence and exact source_row min/max layout.

    Scalar min/max values are checked against each corresponding output batch
    by :func:`check_batch_statistics` during the existing bounded fidelity pass.
    Geometry WKB statistics must exist and have the right null count, but no
    meaningful min/max ordering is assumed for binary geometry bytes.
    """
    need(expected_group_rows > 0, "row-group size contract must be positive")
    metadata = pf.metadata
    total_rows = metadata.num_rows
    expected_groups = (total_rows + expected_group_rows - 1) // expected_group_rows
    need(metadata.num_row_groups == expected_groups,
         f"row-group count {metadata.num_row_groups} differs from expected {expected_groups}")
    total_columns = 0
    for group_no in range(metadata.num_row_groups):
        group = metadata.row_group(group_no)
        first_row = group_no * expected_group_rows + 1
        expected_rows = min(expected_group_rows, total_rows - group_no * expected_group_rows)
        last_row = first_row + expected_rows - 1
        need(group.num_rows == expected_rows,
             f"row-group {group_no} has {group.num_rows} rows; expected {expected_rows}")
        columns = {group.column(i).path_in_schema: group.column(i) for i in range(group.num_columns)}
        need("source_row" in columns, f"row-group {group_no} lacks source_row")
        for path, column in columns.items():
            stats = column.statistics
            need(stats is not None, f"missing statistics for {path} in row-group {group_no}")
            need(stats.null_count is not None, f"missing null_count statistics for {path} in row-group {group_no}")
            if stats.null_count == group.num_rows:
                need(not stats.has_min_max,
                     f"all-null column {path} has min/max statistics in row-group {group_no}")
            if path == "source_row":
                need(stats.has_min_max, f"missing source_row min/max in row-group {group_no}")
                need(stats.min == first_row,
                     f"source_row minimum {stats.min!r} differs from expected {first_row} in row-group {group_no}")
                need(stats.max == last_row,
                     f"source_row maximum {stats.max!r} differs from expected {last_row} in row-group {group_no}")
                need(stats.null_count == 0, f"source_row has nulls in row-group {group_no}")
            total_columns += 1
    return {"row_groups": metadata.num_row_groups, "row_group_rows_max": expected_group_rows,
            "column_chunks_with_statistics": total_columns, "source_row_ranges_checked": metadata.num_row_groups}


def check_batch_statistics(group: pq.RowGroupMetaData, batch: pa.RecordBatch, group_no: int) -> dict[str, int]:
    """Compare each column chunk's stats to values in its bounded row-group batch."""
    need(group.num_rows == batch.num_rows,
         f"row-group {group_no} has {group.num_rows} rows but validation batch has {batch.num_rows}")
    arrays = _parquet_leaf_arrays(batch)
    columns = {group.column(i).path_in_schema: group.column(i) for i in range(group.num_columns)}
    need(set(columns) == set(arrays), f"row-group {group_no} column paths differ from batch fields")
    scalar_bounds_checked = 0
    for path, column in columns.items():
        stats = column.statistics
        need(stats is not None, f"missing statistics for {path} in row-group {group_no}")
        array = arrays[path]
        actual_nulls = array.null_count
        need(stats.null_count == actual_nulls,
             f"null_count for {path} is {stats.null_count!r}; values contain {actual_nulls} nulls in row-group {group_no}")
        if path == GEOMETRY:
            continue
        if actual_nulls == batch.num_rows:
            need(not stats.has_min_max,
                 f"all-null scalar {path} has min/max statistics in row-group {group_no}")
            continue
        try:
            bounds = pc.min_max(array).as_py()
            expected_min, expected_max = bounds["min"], bounds["max"]
        except Exception as exc:
            raise ValueError(f"cannot compute scalar statistics for {path} in row-group {group_no}") from exc
        if (isinstance(expected_min, float) and isinstance(expected_max, float)
                and math.isnan(expected_min) and math.isnan(expected_max)):
            need(not stats.has_min_max,
                 f"all-NaN scalar {path} has min/max statistics in row-group {group_no}")
            continue
        need(stats.has_min_max, f"missing scalar min/max for {path} in row-group {group_no}")
        need(_same_stat(stats.min, expected_min),
             f"minimum statistic for {path} differs from row-group values in group {group_no}")
        need(_same_stat(stats.max, expected_max),
             f"maximum statistic for {path} differs from row-group values in group {group_no}")
        scalar_bounds_checked += 1
    return {"scalar_min_max_columns_checked": scalar_bounds_checked,
            "columns_with_null_count_checked": len(columns)}


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
    row_group_statistics = check_row_group_statistics(pf)
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
    scalar_min_max_checks = null_count_checks = 0
    with pyogrio.open_arrow(source_vfs(source), layer=LAYER, return_fids=True, batch_size=ROW_GROUP_ROWS, use_pyarrow=True) as (meta, reader):
        need(meta["crs"] == "EPSG:4326", "source CRS changed")
        for group_no, (source_batch, output_batch) in enumerate(
            zip(reader, pf.iter_batches(batch_size=ROW_GROUP_ROWS), strict=True)
        ):
            if not verified_schema:
                verify_source_schema(source_batch.schema)
                verified_schema = True
            stat_counts = check_batch_statistics(pf.metadata.row_group(group_no), output_batch, group_no)
            scalar_min_max_checks += stat_counts["scalar_min_max_columns_checked"]
            null_count_checks += stat_counts["columns_with_null_count_checked"]
            compare(source_batch, output_batch, feature_count + 1)
            for name, count in observed_geometry_types(output_batch.column(GEOMETRY).to_pylist()).items():
                geometry_counts[name] = geometry_counts.get(name, 0) + count
            for name, column in zip(source_batch.schema.names, source_batch.columns, strict=True):
                source_null_counts[name] = source_null_counts.get(name, 0) + column.null_count
            feature_count += source_batch.num_rows
    need(feature_count == manifest["records"], "source stream ended before expected records")
    need(verified_schema, "source stream produced no batches")
    need(group_no + 1 == pf.metadata.num_row_groups, "source/output batches did not cover every row group")
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
        "row_group_statistics": {**row_group_statistics, "status": "passed",
                                  "scalar_min_max_values_checked": scalar_min_max_checks,
                                  "null_counts_checked": null_count_checks,
                                  "geometry_min_max_required": False},
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
