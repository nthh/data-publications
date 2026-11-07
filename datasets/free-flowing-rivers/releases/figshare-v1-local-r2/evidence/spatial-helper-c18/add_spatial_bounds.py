#!/usr/bin/env python3
"""Append GeoParquet 1.1 bbox statistics without changing any source fields/WKB."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import resource
import shutil
import sys
from collections import Counter
from itertools import zip_longest
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyproj
import shapely

BBOX_NAMES = ("xmin", "ymin", "xmax", "ymax")
GEOMETRY_TYPES = {0:"Point", 1:"LineString", 2:"LinearRing", 3:"Polygon", 4:"MultiPoint",
                  5:"MultiLineString", 6:"MultiPolygon", 7:"GeometryCollection"}
CHUNK_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_RSS = 1024**3
DEFAULT_START_DISK = 40_000_000_000
DEFAULT_REMAINING_DISK = 10_000_000_000
SENTINEL = object()


class SpatialBoundsError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK_BYTES): h.update(block)
    return h.hexdigest()


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def peak_rss_bytes() -> int:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == "darwin" else raw * 1024)


def _geometry_array(wkb: pa.Array) -> tuple[Any, np.ndarray, np.ndarray, Counter[str]]:
    try:
        geoms = shapely.from_wkb(wkb.to_numpy(zero_copy_only=False), on_invalid="raise")
    except Exception as e:
        raise SpatialBoundsError(f"invalid or unsupported source WKB: {type(e).__name__}: {e}") from e
    dimensions = np.asarray(shapely.get_coordinate_dimension(geoms), dtype=np.int8)
    if np.any(dimensions > 2):
        raise SpatialBoundsError("2D-only bbox helper refuses Z/M WKB geometries")
    bounds = np.asarray(shapely.bounds(geoms), dtype=np.float64)
    valid = (~np.asarray(shapely.is_empty(geoms), dtype=bool)) & np.isfinite(bounds).all(axis=1)
    type_ids = np.asarray(shapely.get_type_id(geoms), dtype=np.int16)
    counts: Counter[str] = Counter()
    for code in type_ids:
        if code >= 0:
            name = GEOMETRY_TYPES.get(int(code))
            if name is None: raise SpatialBoundsError(f"unrecognized WKB geometry type id {int(code)}")
            counts[name] += 1
    # Null and empty/non-finite geometries retain their original bytes/value;
    # their derived bbox children are null.
    valid &= type_ids >= 0
    return geoms, bounds, valid, counts


def bbox_struct(bounds: np.ndarray, valid: np.ndarray) -> pa.StructArray:
    children = [pa.array(bounds[:, i], mask=~valid, type=pa.float64()) for i in range(4)]
    return pa.StructArray.from_arrays(children, names=list(BBOX_NAMES))


def _crs_json(schema: pa.Schema, geometry: str, crs_argument: str | None) -> dict[str, Any] | None:
    raw = (schema.metadata or {}).get(b"geo")
    if raw:
        try:
            geo = json.loads(raw)
            geom = geo["columns"][geometry]
        except Exception as e:
            raise SpatialBoundsError(f"invalid GeoParquet metadata for geometry column {geometry!r}: {e}") from e
        crs_present = "crs" in geom
        old_crs = geom.get("crs")
        if crs_present and old_crs is None and not crs_argument:
            raise SpatialBoundsError("GeoParquet explicitly declares null CRS; provide --crs to identify the source CRS")
        if not crs_present:
            # GeoParquet defines an omitted CRS member as OGC:CRS84.
            old_crs = pyproj.CRS.from_user_input("OGC:CRS84").to_json_dict()
        if crs_argument:
            selected = pyproj.CRS.from_user_input(crs_argument)
            if old_crs is not None:
                try:
                    existing = pyproj.CRS.from_json_dict(old_crs) if isinstance(old_crs, dict) else pyproj.CRS.from_user_input(old_crs)
                    if not existing.equals(selected, ignore_axis_order=True):
                        raise SpatialBoundsError(f"--crs {crs_argument} conflicts with GeoParquet CRS metadata")
                except SpatialBoundsError: raise
                except Exception as e: raise SpatialBoundsError(f"cannot interpret existing GeoParquet CRS: {e}") from e
            old_crs = selected.to_json_dict()
        return old_crs
    if not crs_argument:
        raise SpatialBoundsError("input is not GeoParquet; provide --crs using the source CRS")
    crs = pyproj.CRS.from_user_input(crs_argument)
    return crs.to_json_dict()


def output_schema(input_schema: pa.Schema, geometry: str, bbox_global: list[float] | None,
                  geometry_types: list[str], crs_argument: str | None) -> pa.Schema:
    if geometry not in input_schema.names:
        raise SpatialBoundsError(f"geometry column not found: {geometry}")
    if not pa.types.is_binary(input_schema.field(geometry).type) and not pa.types.is_large_binary(input_schema.field(geometry).type):
        raise SpatialBoundsError("geometry column must contain raw WKB bytes in Arrow binary/large_binary")
    if "bbox" in input_schema.names:
        raise SpatialBoundsError("input already has a bbox field; refusing to overwrite or replace it")
    metadata = dict(input_schema.metadata or {})
    crs = _crs_json(input_schema, geometry, crs_argument)
    try:
        geo = json.loads(metadata[b"geo"]) if b"geo" in metadata else {
            "version": "1.1.0", "primary_column": geometry, "columns": {}
        }
    except Exception as e:
        raise SpatialBoundsError(f"invalid input GeoParquet metadata: {e}") from e
    if geo.get("primary_column", geometry) != geometry:
        raise SpatialBoundsError("input GeoParquet primary geometry differs from --geometry-column")
    geo["version"] = "1.1.0"
    geo["primary_column"] = geometry
    columns = geo.setdefault("columns", {})
    geom_meta = columns.setdefault(geometry, {})
    geom_meta["encoding"] = "WKB"
    geom_meta["geometry_types"] = geometry_types
    geom_meta["crs"] = crs
    if bbox_global is not None: geom_meta["bbox"] = bbox_global
    else: geom_meta.pop("bbox", None)
    geom_meta["covering"] = {"bbox": {name: ["bbox", name] for name in BBOX_NAMES}}
    metadata[b"geo"] = json.dumps(geo, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    bbox_field = pa.field("bbox", pa.struct([pa.field(x, pa.float64(), nullable=True) for x in BBOX_NAMES]), nullable=True)
    return pa.schema(list(input_schema) + [bbox_field], metadata=metadata)


def add_spatial_bounds(input_path: Path, output_path: Path, report_path: Path,
                       geometry: str, crs: str | None = None, batch_rows: int = 1024,
                       max_rss_bytes: int = DEFAULT_MAX_RSS,
                       minimum_remaining_free_bytes: int = DEFAULT_REMAINING_DISK,
                       minimum_start_free_bytes: int = DEFAULT_START_DISK) -> dict[str, Any]:
    input_path, output_path, report_path = input_path.resolve(), output_path.resolve(), report_path.resolve()
    if input_path == output_path or input_path == report_path or output_path == report_path:
        raise SpatialBoundsError("input, output and report paths must be distinct")
    if not input_path.is_file(): raise SpatialBoundsError(f"input Parquet file is missing: {input_path}")
    if output_path.exists(): raise SpatialBoundsError(f"refuse overwrite existing immutable output: {output_path}")
    if report_path.exists(): raise SpatialBoundsError(f"refuse overwrite existing report: {report_path}")
    if batch_rows < 1: raise SpatialBoundsError("batch_rows must be positive")
    if max_rss_bytes <= 0 or minimum_remaining_free_bytes < 0: raise SpatialBoundsError("memory/disk limits must be non-negative")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    in_stat = input_path.stat(); input_hash = sha256(input_path)
    pf = pq.ParquetFile(input_path)
    rows = int(pf.metadata.num_rows)
    if rows <= 0: raise SpatialBoundsError("input Parquet is empty")
    if geometry not in pf.schema_arrow.names: raise SpatialBoundsError(f"geometry column missing: {geometry}")
    estimated = int(in_stat.st_size * 1.2) + rows * 64 + 64 * 1024 * 1024
    free = shutil.disk_usage(output_path.parent).free
    if free < minimum_start_free_bytes:
        raise SpatialBoundsError(f"disk guard: at least {minimum_start_free_bytes} free bytes required before bulk writes; only {free} free")
    if free < estimated + minimum_remaining_free_bytes:
        raise SpatialBoundsError(f"disk guard: need estimated {estimated} output bytes plus {minimum_remaining_free_bytes} remaining; only {free} free")
    stage = output_path.with_name(output_path.name + f".partial-{os.getpid()}")
    if stage.exists(): raise SpatialBoundsError(f"staging path already exists: {stage}")
    stage.parent.mkdir(parents=True, exist_ok=True)
    stage_created = False
    batch_count = 0; input_rows = 0; geom_counts: Counter[str] = Counter()
    global_min = np.array([np.inf, np.inf], dtype=np.float64)
    global_max = np.array([-np.inf, -np.inf], dtype=np.float64)
    try:
        # Pass 1 computes complete metadata, then pass 2 writes each batch once.
        for batch in pf.iter_batches(batch_size=batch_rows, columns=pf.schema_arrow.names):
            _, bounds, valid, types = _geometry_array(batch.column(batch.schema.get_field_index(geometry)))
            geom_counts.update(types)
            if valid.any():
                global_min = np.minimum(global_min, bounds[valid, :2].min(axis=0))
                global_max = np.maximum(global_max, bounds[valid, 2:].max(axis=0))
            input_rows += batch.num_rows; batch_count += 1
            if peak_rss_bytes() > max_rss_bytes:
                raise SpatialBoundsError(f"peak RSS exceeded configured cap {max_rss_bytes} bytes")
        if not batch_count: raise SpatialBoundsError("no source batches were read")

        final_bbox = [float(global_min[0]), float(global_min[1]), float(global_max[0]), float(global_max[1])]
        if not all(math.isfinite(v) for v in final_bbox): raise SpatialBoundsError("no finite non-empty WKB geometry bounds found")
        schema = output_schema(pf.schema_arrow, geometry, final_bbox, sorted(geom_counts), crs)
        writer = pq.ParquetWriter(stage, schema, compression="zstd", compression_level=6,
            use_dictionary=True, write_statistics=True, version="2.6")
        stage_created = True
        try:
            for batch in pf.iter_batches(batch_size=batch_rows, columns=pf.schema_arrow.names):
                _, bounds, valid, _ = _geometry_array(batch.column(batch.schema.get_field_index(geometry)))
                table = pa.Table.from_batches([batch]).append_column("bbox", bbox_struct(bounds, valid))
                writer.write_table(table.replace_schema_metadata(schema.metadata), row_group_size=batch.num_rows)
                if shutil.disk_usage(output_path.parent).free < minimum_remaining_free_bytes:
                    raise SpatialBoundsError("free disk fell below the configured remaining-space floor")
                if peak_rss_bytes() > max_rss_bytes:
                    raise SpatialBoundsError(f"peak RSS exceeded configured cap {max_rss_bytes} bytes")
        finally:
            writer.close()
        validation = validate_pair(input_path, stage, geometry, crs, batch_rows=batch_rows,
                                   expected_bbox=final_bbox, expected_geometry_types=sorted(geom_counts))
        if validation["source_rows"] != rows: raise SpatialBoundsError("independent reread row count differs")
        if peak_rss_bytes() > max_rss_bytes: raise SpatialBoundsError(f"peak RSS exceeded configured cap {max_rss_bytes} bytes during reread")
        if sha256(input_path) != input_hash: raise SpatialBoundsError("input Parquet changed during augmentation")
        output_hash = sha256(stage); output_size = stage.stat().st_size
        os.replace(stage, output_path)
        output_path.chmod(0o444)
        report = {"status": "passed", "input": {"path": str(input_path), "size_bytes": in_stat.st_size, "sha256": input_hash},
            "output": {"path": str(output_path), "size_bytes": output_size, "sha256": output_hash},
            "geometry_column": geometry, "crs_argument": crs,
            "geoparquet_version": "1.1.0", "bbox_column": "bbox",
            "global_bbox": final_bbox, "geometry_types": dict(sorted(geom_counts.items())),
            "source_rows": rows, "source_columns_exactly_compared": pf.schema_arrow.names,
            "source_values_nulls_and_raw_wkb_compared": True, "derived_bbox_values_recomputed_and_compared": True,
            "arrow_batches_written": batch_count, "batch_rows_max": batch_rows,
            "row_groups": pq.ParquetFile(output_path).metadata.num_row_groups,
            "peak_rss_bytes": peak_rss_bytes(), "peak_rss_limit_bytes": max_rss_bytes,
            "estimated_output_bytes": estimated, "minimum_remaining_free_bytes": minimum_remaining_free_bytes,
            "minimum_start_free_bytes": minimum_start_free_bytes,
            "validation": validation, "created": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "limitations": "Spatial bbox is derived from unchanged raw WKB coordinates in the source CRS; no reprojection, repair, sort, or geometry rewrite was performed."}
        json_write(report_path, report); report_path.chmod(0o444)
        return report
    except Exception as e:
        failed_stage = str(stage) if stage.exists() else None
        report = {"status": "failed", "input": {"path": str(input_path), "sha256": input_hash,
                    "size_bytes": in_stat.st_size}, "output_requested": str(output_path),
                  "failed_stage_path": failed_stage, "error_type": type(e).__name__, "error": str(e),
                  "source_mutated": None,
                  "source_mutation_note": "Failure does not by itself establish whether the input changed; compare its recorded SHA-256."}
        if not report_path.exists():
            json_write(report_path, report)
            report_path.chmod(0o444)
        raise


def validate_pair(input_path: Path, output_path: Path, geometry: str, crs: str | None = None,
                  batch_rows: int = 1024, expected_bbox: list[float] | None = None,
                  expected_geometry_types: list[str] | None = None) -> dict[str, Any]:
    """Independent full reread comparison; bounded by `batch_rows`."""
    src, out = pq.ParquetFile(input_path), pq.ParquetFile(output_path)
    src_schema, out_schema = src.schema_arrow, out.schema_arrow
    if out_schema.names != src_schema.names + ["bbox"]:
        raise SpatialBoundsError("output columns differ from input columns plus appended bbox")
    for i, f in enumerate(src_schema):
        if out_schema.field(i) != f:
            raise SpatialBoundsError(f"source field type/nullability/metadata changed: {f.name}")
    if out_schema.field("bbox").type != pa.struct([pa.field(n, pa.float64(), nullable=True) for n in BBOX_NAMES]):
        raise SpatialBoundsError("bbox field has the wrong Arrow struct schema")
    src_meta = dict(src_schema.metadata or {}); out_meta = dict(out_schema.metadata or {})
    for key, value in src_meta.items():
        if key != b"geo" and out_meta.get(key) != value:
            raise SpatialBoundsError(f"non-GeoParquet schema metadata changed: {key!r}")
    if out.metadata.num_rows != src.metadata.num_rows:
        raise SpatialBoundsError(f"row count changed: {src.metadata.num_rows} -> {out.metadata.num_rows}")
    geo = json.loads(out_meta[b"geo"])
    col = geo["columns"][geometry]
    if geo.get("version") != "1.1.0" or col.get("encoding") != "WKB":
        raise SpatialBoundsError("output is not GeoParquet 1.1 WKB")
    if col.get("covering", {}).get("bbox") != {n:["bbox",n] for n in BBOX_NAMES}:
        raise SpatialBoundsError("output GeoParquet bbox covering map is missing or wrong")
    if col.get("bbox") != expected_bbox:
        raise SpatialBoundsError("global GeoParquet bbox metadata differs from WKB bounds")
    if col.get("geometry_types") != expected_geometry_types:
        raise SpatialBoundsError("GeoParquet geometry_types metadata differs from WKB scan")
    expected_crs = _crs_json(src_schema, geometry, crs)
    actual_crs = col.get("crs")
    if actual_crs is None:
        raise SpatialBoundsError("output GeoParquet CRS is explicitly null/unknown")
    try:
        expected_crs_obj = pyproj.CRS.from_json_dict(expected_crs) if isinstance(expected_crs, dict) else pyproj.CRS.from_user_input(expected_crs)
        actual_crs_obj = pyproj.CRS.from_json_dict(actual_crs) if isinstance(actual_crs, dict) else pyproj.CRS.from_user_input(actual_crs)
        if not expected_crs_obj.equals(actual_crs_obj, ignore_axis_order=True):
            raise SpatialBoundsError("output CRS does not semantically match source CRS")
    except SpatialBoundsError:
        raise
    except Exception as e:
        raise SpatialBoundsError(f"cannot compare source/output CRS metadata: {e}") from e
    total=0; type_counts:Counter[str]=Counter(); min_xy=np.array([np.inf,np.inf]);max_xy=np.array([-np.inf,-np.inf])
    src_iter=iter(src.iter_batches(batch_size=batch_rows,columns=src_schema.names))
    out_iter=iter(out.iter_batches(batch_size=batch_rows,columns=out_schema.names))
    a=next(src_iter,None);b=next(out_iter,None);ai=bi=0
    while a is not None and b is not None:
        n=min(a.num_rows-ai,b.num_rows-bi)
        for ix,name in enumerate(src_schema.names):
            left = a.column(ix).slice(ai, n)
            right = b.column(b.schema.get_field_index(name)).slice(bi, n)
            if not left.equals(right):
                raise SpatialBoundsError(f"source field/value/null/raw-WKB mismatch: {name} near row {total+1}")
        wkb = b.column(b.schema.get_field_index(geometry)).slice(bi,n)
        _, bounds, valid, types = _geometry_array(wkb)
        type_counts.update(types)
        if valid.any():
            min_xy=np.minimum(min_xy,bounds[valid,:2].min(axis=0));max_xy=np.maximum(max_xy,bounds[valid,2:].max(axis=0))
        expected_bbox_array=bbox_struct(bounds,valid)
        actual_bbox=b.column(b.schema.get_field_index("bbox")).slice(bi,n)
        if not expected_bbox_array.equals(actual_bbox):
            raise SpatialBoundsError(f"derived per-row bbox mismatch near row {total+1}")
        total+=n;ai+=n;bi+=n
        if ai==a.num_rows:a=next(src_iter,None);ai=0
        if bi==b.num_rows:b=next(out_iter,None);bi=0
    if a is not None or b is not None: raise SpatialBoundsError("input/output streams have different feature multiplicity")
    if total != src.metadata.num_rows: raise SpatialBoundsError("independent comparison row tally differs")
    actual_global=[float(min_xy[0]),float(min_xy[1]),float(max_xy[0]),float(max_xy[1])]
    if actual_global != expected_bbox: raise SpatialBoundsError("reread WKB global bbox differs from expected metadata")
    # Metadata stores the actual type names, while the report captures counts;
    # compare that sorted name set independently here.
    if sorted(type_counts) != expected_geometry_types:
        raise SpatialBoundsError("reread WKB geometry type tally differs from metadata")
    return {"source_rows": total, "source_fields_compared": len(src_schema.names),
            "source_values_nulls_wkb_compared": total * len(src_schema.names),
            "bbox_values_recomputed_and_compared": total * 4,
            "global_bbox": actual_global, "geometry_type_counts": dict(sorted(type_counts.items()))}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--geometry-column", required=True)
    ap.add_argument("--crs", help="Source CRS only when not declared in GeoParquet; coordinates are never transformed")
    ap.add_argument("--batch-rows", type=int, default=1024)
    ap.add_argument("--max-memory-gib", type=float, default=1.0)
    args=ap.parse_args()
    try:
        result=add_spatial_bounds(args.input,args.output,args.report,args.geometry_column,args.crs,args.batch_rows,
            int(args.max_memory_gib*1024**3))
        print(json.dumps(result,indent=2));return 0
    except Exception as e:
        print(f"spatial bounds failed: {type(e).__name__}: {e}",file=sys.stderr);return 1


if __name__=="__main__": raise SystemExit(main())
