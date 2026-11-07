"""Validate the complete LakeATLAS source-to-GeoParquet conversion."""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import pyproj
import shapely

from build import BATCH_SIZE, GEOMETRY_BATCH_SIZE, REPO, SOURCE_NAME, ROW_GROUP_SIZE, bbox_array, bounds_for, inspect_source, peak_rss_bytes, source_uri
from source import EXPECTED_LAYERS, digest


def reject(reason: str) -> None:
    raise ValueError(reason)


def compare_batches(expected: pa.RecordBatch, actual: pa.RecordBatch, context: str = "batch") -> None:
    if expected.num_rows != actual.num_rows:
        reject(f"{context}: row multiplicity mismatch ({expected.num_rows} != {actual.num_rows})")
    if expected.schema.names != actual.schema.names:
        reject(f"{context}: column names/order mismatch")
    for i, name in enumerate(expected.schema.names):
        left, right = expected.column(i), actual.column(i)
        if left.type != right.type:
            reject(f"{context}: Arrow type mismatch in {name}: {left.type} != {right.type}")
        if not left.equals(right):
            reject(f"{context}: value, null, or geometry mismatch in {name}")


def validate_bbox_array(source_wkb: pa.Array, actual_bbox: pa.StructArray, context: str) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    bounds, usable, type_counts = bounds_for(source_wkb)
    expected_bbox = bbox_array(bounds, usable)
    if not expected_bbox.equals(actual_bbox):
        reject(f"{context}: bbox child value/null mismatch recomputed from WKB")
    return bounds, usable, dict(type_counts)


def close_bbox(left: list[float], right: list[float], context: str) -> None:
    if len(left) != 4 or len(right) != 4 or not np.isfinite(left).all() or not np.isfinite(right).all():
        reject(f"{context}: invalid global bbox")
    if not np.allclose(left, right, rtol=0, atol=1e-12):
        reject(f"{context}: global WKB bbox differs from metadata ({left} != {right})")


def validate_geo_metadata(path: Path, expected_geometry_type: str) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    metadata = parquet.schema_arrow.metadata or {}
    if b"geo" not in metadata:
        reject(f"{path.name}: missing GeoParquet metadata")
    geo = json.loads(metadata[b"geo"])
    if geo.get("version") != "1.1.0" or geo.get("primary_column") != "geometry":
        reject(f"{path.name}: unsupported or incorrect GeoParquet version/primary column")
    column = geo.get("columns", {}).get("geometry", {})
    if column.get("encoding") != "WKB":
        reject(f"{path.name}: geometry encoding is not WKB")
    crs = pyproj.CRS.from_json_dict(column["crs"])
    if not crs.equals(pyproj.CRS.from_epsg(4326), ignore_axis_order=True):
        reject(f"{path.name}: unexpected GeoParquet CRS")
    if column.get("geometry_types") != [expected_geometry_type]:
        reject(f"{path.name}: geometry type metadata mismatch")
    bbox = column.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4 or not np.isfinite(bbox).all():
        reject(f"{path.name}: invalid GeoParquet bbox")
    expected_covering = {name: ["bbox", name] for name in ("xmin", "ymin", "xmax", "ymax")}
    if column.get("covering", {}).get("bbox") != expected_covering:
        reject(f"{path.name}: bbox covering metadata mismatch")
    if "bbox" not in parquet.schema_arrow.names or "geometry" not in parquet.schema_arrow.names:
        reject(f"{path.name}: missing geometry or bbox column")
    return {"bbox": bbox, "crs": "EPSG:4326", "geometry_type": expected_geometry_type,
            "geometry_types": column["geometry_types"]}


def verify_gpd_reader(path: Path, layer_name: str, batch_size: int = BATCH_SIZE) -> dict[str, Any]:
    """Exercise a separate GeoParquet-aware reader on one indexed native-ID subset."""
    import geopandas as gpd

    parquet = pq.ParquetFile(path)
    first = next(parquet.iter_batches(batch_size=1, columns=["OBJECTID", "Hylak_id"]))
    fid = first.column(0)[0].as_py()
    subset = gpd.read_parquet(
        path,
        columns=["OBJECTID", "Hylak_id", "geometry"],
        filters=[("OBJECTID", "=", fid)],
    )
    if subset.empty or "geometry" not in subset or subset.crs is None:
        reject(f"{path.name}: GeoPandas could not read a native-FID subset and CRS")
    if not subset["OBJECTID"].eq(fid).all():
        reject(f"{path.name}: GeoPandas subset returned a wrong native FID")
    expected_type = EXPECTED_LAYERS[layer_name]["geometry"]
    types = set(subset.geometry.geom_type.dropna().unique())
    if types and types != {expected_type}:
        reject(f"{path.name}: GeoPandas subset geometry type mismatch: {types}")
    return {
        "reader": f"geopandas {gpd.__version__}",
        "native_fid": fid,
        "hylak_id": int(subset["Hylak_id"].iloc[0]),
        "rows": len(subset),
        "peak_process_memory_bytes": peak_rss_bytes(),
    }


def validate_full(source_cache: Path, release: Path) -> dict[str, Any]:
    source = source_cache / SOURCE_NAME
    source_report = inspect_source(source, verify_crc=True)
    print(f"source verified; peak RSS={peak_rss_bytes():,} bytes", file=sys.stderr, flush=True)
    build_path = release / "build-manifest.json"
    if not build_path.exists():
        reject("Missing build-manifest.json")
    build_report = json.loads(build_path.read_text(encoding="utf-8"))
    if build_report.get("source_sha256") != source_report["source_file"]["sha256"]:
        reject("Build manifest source hash differs from acquired source")
    results = {}
    uri = source_uri(source)
    for layer, expected in EXPECTED_LAYERS.items():
        item = build_report.get("layers", {}).get(layer)
        if item is None:
            reject(f"Build manifest missing layer {layer}")
        path = release / item["path"]
        if not path.is_file():
            reject(f"Missing analytic asset: {path}")
        if path.stat().st_size != item["size_bytes"] or digest(path, "sha256") != item["sha256"]:
            reject(f"Asset size or SHA-256 mismatch: {path.name}")
        if item["feature_count"] != expected["rows"]:
            reject(f"Manifest source row count mismatch for {layer}")
    for layer, expected in EXPECTED_LAYERS.items():
        item = build_report["layers"][layer]
        path = release / item["path"]
        if item["feature_count"] != expected["rows"]:
            reject(f"Manifest source row count mismatch for {layer}")
        meta_report = validate_geo_metadata(path, expected["geometry"])
        geometry_tally_manifest = item.get("geometry_types", {})
        if set(geometry_tally_manifest) != set(meta_report["geometry_types"]) or sum(geometry_tally_manifest.values()) != expected["rows"]:
            reject(f"{layer}: geometry-type tally does not match GeoParquet metadata or row count")
        parquet = pq.ParquetFile(path)
        print(f"opened Parquet metadata for {layer}; row_groups={parquet.metadata.num_row_groups}, peak RSS={peak_rss_bytes():,} bytes", file=sys.stderr, flush=True)
        if item.get("row_group_size") != ROW_GROUP_SIZE or any(
            parquet.metadata.row_group(i).num_rows > ROW_GROUP_SIZE
            for i in range(parquet.metadata.num_row_groups)
        ):
            reject(f"{layer}: row group sizes exceed the pinned maximum")
        source_count = 0
        source_geometry_tally: dict[str, int] = {}
        source_extent_min = np.array([np.inf, np.inf])
        source_extent_max = np.array([-np.inf, -np.inf])
        with pyogrio.open_arrow(uri, layer=layer, use_pyarrow=True, return_fids=True, batch_size=BATCH_SIZE) as (meta, reader):
            geometry_name = meta["geometry_name"]
            source_names = ["geometry" if name == geometry_name else name for name in reader.schema.names]
            if source_names != [n for n in parquet.schema_arrow.names if n not in ("bbox",)]:
                reject(f"{layer}: output schema names/order differ from source")
            parquet_batches = parquet.iter_batches(batch_size=BATCH_SIZE, columns=[*source_names, "bbox"])
            for source_batch in reader:
                try:
                    output_batch = next(parquet_batches)
                except StopIteration:
                    reject(f"{layer}: output ended before source")
                source_batch = source_batch.rename_columns(source_names)
                context = f"{layer} batch {source_count // BATCH_SIZE}"
                compare_batches(source_batch, output_batch.select(source_names), context)
                wkb = source_batch.column(source_names.index("geometry"))
                bbox_column = output_batch.column(output_batch.schema.get_field_index("bbox"))
                for offset in range(0, source_batch.num_rows, GEOMETRY_BATCH_SIZE):
                    size = min(GEOMETRY_BATCH_SIZE, source_batch.num_rows - offset)
                    bounds, usable, geometry_tally = validate_bbox_array(
                        wkb.slice(offset, size), bbox_column.slice(offset, size), context
                    )
                    for name, count in geometry_tally.items():
                        source_geometry_tally[name] = source_geometry_tally.get(name, 0) + count
                    if usable.any():
                        source_extent_min = np.minimum(source_extent_min, bounds[usable, :2].min(axis=0))
                        source_extent_max = np.maximum(source_extent_max, bounds[usable, 2:].max(axis=0))
                source_count += source_batch.num_rows
                if source_count % 100_000 < source_batch.num_rows:
                    print(f"{layer}: validated {source_count:,} source rows; peak RSS={peak_rss_bytes():,} bytes", file=sys.stderr, flush=True)
            try:
                next(parquet_batches)
            except StopIteration:
                pass
            else:
                reject(f"{layer}: output has extra rows")
        if source_count != expected["rows"] or source_count != parquet.metadata.num_rows:
            reject(f"{layer}: full source/output row count mismatch")
        observed_types = dict(sorted(source_geometry_tally.items()))
        if observed_types != dict(sorted(geometry_tally_manifest.items())):
            reject(f"{layer}: independently counted source geometry tally differs from the build manifest")
        source_extent = [float(source_extent_min[0]), float(source_extent_min[1]),
                         float(source_extent_max[0]), float(source_extent_max[1])]
        close_bbox(source_extent, meta_report["bbox"], f"{layer} GeoParquet metadata")
        close_bbox(source_extent, item["extent"], f"{layer} build manifest")
        print(f"validated {layer}; peak RSS={peak_rss_bytes():,} bytes", file=sys.stderr, flush=True)
        results[layer] = {
            "asset": item["path"],
            "source_rows": source_count,
            "source_equal_rows": source_count,
            "source_equal_native_fields": len(source_report["layers"][layer]["fields"]),
            "source_equal_wkb_rows": source_count,
            "source_reread": "passed_exact_column_arrays_in_source_order",
            "source_geometry_type_tally": observed_types,
            "source_wkb_global_bbox": source_extent,
            "geo_metadata": meta_report,
            "asset_sha256": item["sha256"],
            "asset_bytes": item["size_bytes"],
        }
        del parquet, parquet_batches, reader, meta, source_batch, output_batch, wkb, bbox_column
        pa.default_memory_pool().release_unused()
    return {
        "status": "passed_source_only_pending_reader",
        "source": {"name": SOURCE_NAME, "sha256": source_report["source_file"]["sha256"],
                   "size_bytes": source_report["source_file"]["size_bytes"]},
        "validator": {
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "sha256": digest(Path(__file__).resolve(), "sha256"),
        },
        "layers": results,
        "limits": [
            "The source reread uses the same GDAL OpenFileGDB decoder, but compares every source-order Arrow cell and WKB byte against independently reread Parquet batches.",
            "Source fidelity does not validate upstream scientific accuracy.",
            "GeoPandas subset checks run in separate sequential worker processes and are combined by validate.py.",
        ],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("source", "reader"), required=True)
    parser.add_argument("--source-cache", type=Path, default=REPO / ".local/lakeatlas/source")
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--asset", type=Path)
    parser.add_argument("--layer")
    args = parser.parse_args()
    if args.mode == "reader":
        if args.asset is None or args.layer not in EXPECTED_LAYERS:
            parser.error("reader mode requires --asset and a recognized --layer")
        print(json.dumps(verify_gpd_reader(args.asset, args.layer), sort_keys=True))
        return
    report_path = args.report or (args.release / "source-fidelity.json")
    if report_path.exists():
        raise SystemExit(f"Refusing to overwrite prior validation evidence: {report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = validate_full(args.source_cache, args.release)
    except Exception as error:
        report = {
            "status": "failed_source_fidelity",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        write_report(report_path, report)
        print(rendered, file=sys.stderr)
        raise SystemExit(1) from error
    peak_bytes = peak_rss_bytes()
    report["peak_process_memory_bytes"] = peak_bytes
    if peak_bytes >= 1_000_000_000:
        report["status"] = "failed_memory_limit"
        report["source_fidelity_checks"] = "passed"
        report["error"] = f"Source-fidelity worker peak memory exceeded the 1 GB limit: {peak_bytes:,} bytes"
        write_report(report_path, report)
        print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    write_report(report_path, report)
    print(rendered)


if __name__ == "__main__":
    main()
