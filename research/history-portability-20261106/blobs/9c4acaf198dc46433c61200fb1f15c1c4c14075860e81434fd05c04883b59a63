#!/usr/bin/env python3
"""Build a bounded deterministic Hilbert-ordered GeoParquet companion."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import gc
import json
import math
import os
import resource
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyproj
import shapely

BBOX_FIELDS = ("xmin", "ymin", "xmax", "ymax")
GEOMETRY_TYPES = {
    0: "Point", 1: "LineString", 2: "LinearRing", 3: "Polygon",
    4: "MultiPoint", 5: "MultiLineString", 6: "MultiPolygon",
    7: "GeometryCollection",
}
KEY_COLUMN = "__folia_hilbert16"
DEFAULT_BATCH_ROWS = 1024
DEFAULT_BUCKETS = 32
DEFAULT_BUFFER_ROWS = 1024
DEFAULT_ROW_GROUP_SIZE = 4096
DEFAULT_MAX_RSS_BYTES = 1_000_000_000
DEFAULT_START_FREE_BYTES = 40_000_000_000
DEFAULT_REMAINING_FREE_BYTES = 10_000_000_000
DEFAULT_TASK_DISK_LIMIT_BYTES = 8_000_000_000
ORDERING_CHUNKS = 10
MAX_OVERLAP_FRACTION = 0.30
MAX_LOCALITY_RATIO = 0.30


class SpatialOrderError(RuntimeError):
    """A spatial transform or its independent validation failed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_inventory(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.is_file():
            files = [path]
        elif path.is_dir():
            records.append({"path": str(path), "kind": "directory"})
            files = sorted(child for child in path.rglob("*") if child.is_file())
        else:
            continue
        for file_path in files:
            records.append({
                "path": str(file_path),
                "size_bytes": file_path.stat().st_size,
                "allocated_bytes": file_path.stat().st_blocks * 512,
                "sha256": sha256(file_path),
            })
    return records


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def source_schema(pf: pq.ParquetFile) -> pa.Schema:
    """Use physical footer metadata, including late GeoParquet metadata."""
    schema = pf.schema_arrow
    metadata = dict(schema.metadata or {})
    physical_geo = (pf.metadata.metadata or {}).get(b"geo")
    if physical_geo is not None:
        if b"geo" in metadata and json.loads(metadata[b"geo"]) != json.loads(physical_geo):
            raise SpatialOrderError("physical GeoParquet metadata conflicts with serialized Arrow schema")
        metadata[b"geo"] = physical_geo
    return schema.with_metadata(metadata)


def _geometry_bounds(wkb: pa.Array) -> tuple[np.ndarray, np.ndarray, Counter[str]]:
    if len(wkb) > 128:
        parts = [_geometry_bounds(wkb.slice(start, 128)) for start in range(0, len(wkb), 128)]
        counts: Counter[str] = Counter()
        for _, _, types in parts:
            counts.update(types)
        return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts]), counts
    try:
        geometries = shapely.from_wkb(wkb.to_numpy(zero_copy_only=False), on_invalid="raise")
    except Exception as error:
        raise SpatialOrderError(f"invalid source WKB: {type(error).__name__}: {error}") from error
    if np.asarray(shapely.has_z(geometries), dtype=bool).any():
        raise SpatialOrderError("3D WKB is unsupported; spatial ordering requires 2D coordinates")
    bounds = np.asarray(shapely.bounds(geometries), dtype=np.float64)
    type_ids = np.asarray(shapely.get_type_id(geometries), dtype=np.int16)
    valid = (type_ids >= 0) & (~np.asarray(shapely.is_empty(geometries), dtype=bool)) & np.isfinite(bounds).all(axis=1)
    counts: Counter[str] = Counter()
    for code in type_ids:
        if code >= 0:
            name = GEOMETRY_TYPES.get(int(code))
            if name is None:
                raise SpatialOrderError(f"unrecognized geometry type id {int(code)}")
            counts[name] += 1
    return bounds, valid, counts


def _bbox_struct(bounds: np.ndarray, valid: np.ndarray) -> pa.StructArray:
    children = [pa.array(bounds[:, i], mask=~valid, type=pa.float64()) for i in range(4)]
    return pa.StructArray.from_arrays(children, names=list(BBOX_FIELDS), mask=pa.array(~valid))


def _bounds_from_bbox(box: pa.StructArray) -> tuple[np.ndarray, np.ndarray]:
    names = box.type.names or []
    if not all(name in names for name in BBOX_FIELDS):
        raise SpatialOrderError("bbox must be a struct with xmin, ymin, xmax, ymax children")
    arrays = []
    valid = box.is_valid().to_numpy(zero_copy_only=False)
    for name in BBOX_FIELDS:
        child = box.field(name)
        if not pa.types.is_floating(child.type):
            raise SpatialOrderError(f"bbox.{name} must be a floating-point child")
        child_valid = child.is_valid().to_numpy(zero_copy_only=False)
        values = child.fill_null(float("nan")).to_numpy(zero_copy_only=False)
        valid &= child_valid & np.isfinite(values)
        arrays.append(values)
    bounds = np.column_stack(arrays).astype(np.float64, copy=False)
    return bounds, valid


def hilbert_xy_to_distance(x: np.ndarray, y: np.ndarray, bits: int = 16) -> np.ndarray:
    """Vectorized integer Hilbert mapping; stable across platforms and runs."""
    if bits < 1 or bits > 16:
        raise ValueError("Hilbert grid resolution must be 1..16 bits per axis")
    x = np.asarray(x, dtype=np.uint32).copy()
    y = np.asarray(y, dtype=np.uint32).copy()
    limit = (1 << bits) - 1
    if np.any(x > limit) or np.any(y > limit):
        raise ValueError("Hilbert coordinates exceed the selected grid")
    distance = np.zeros(len(x), dtype=np.uint64)
    scale = 1 << (bits - 1)
    while scale:
        rx = (x & scale) != 0
        ry = (y & scale) != 0
        distance += np.uint64(scale * scale) * ((rx.astype(np.uint64) * 3) ^ ry.astype(np.uint64))
        rotate = ~ry
        reflect = rotate & rx
        x[reflect] = np.uint32(limit) - x[reflect]
        y[reflect] = np.uint32(limit) - y[reflect]
        swap = rotate
        temp = x[swap].copy()
        x[swap] = y[swap]
        y[swap] = temp
        scale >>= 1
    return distance


def hilbert_keys(bounds: np.ndarray, usable: np.ndarray, bits: int = 16) -> np.ndarray:
    """Key bbox centers in normalized WGS84; null/empty geometry sorts last."""
    keys = np.full(len(bounds), np.iinfo(np.uint64).max, dtype=np.uint64)
    if not usable.any():
        return keys
    centers_x = np.clip((bounds[usable, 0] + bounds[usable, 2]) * 0.5, -180.0, 180.0)
    centers_y = np.clip((bounds[usable, 1] + bounds[usable, 3]) * 0.5, -90.0, 90.0)
    scale = (1 << bits) - 1
    x = np.floor((centers_x + 180.0) / 360.0 * scale).astype(np.uint32)
    y = np.floor((centers_y + 90.0) / 180.0 * scale).astype(np.uint32)
    np.clip(x, 0, scale, out=x)
    np.clip(y, 0, scale, out=y)
    keys[usable] = hilbert_xy_to_distance(x, y, bits)
    return keys


def _geo_info(schema: pa.Schema, geometry_column: str, crs_arg: str | None,
              geometry_types: list[str], bbox_global: list[float]) -> pa.Schema:
    if geometry_column not in schema.names:
        raise SpatialOrderError(f"geometry column is missing: {geometry_column}")
    geom_field = schema.field(geometry_column)
    if not (pa.types.is_binary(geom_field.type) or pa.types.is_large_binary(geom_field.type)):
        raise SpatialOrderError("geometry column must contain WKB bytes")
    metadata = dict(schema.metadata or {})
    raw_geo = metadata.get(b"geo")
    geo: dict[str, Any]
    if raw_geo is not None:
        try:
            geo = json.loads(raw_geo)
        except Exception as error:
            raise SpatialOrderError(f"invalid GeoParquet metadata: {error}") from error
        if geo.get("primary_column", geometry_column) != geometry_column:
            raise SpatialOrderError("geometry column differs from GeoParquet primary_column")
        old_column = geo.get("columns", {}).get(geometry_column, {})
        old_crs = old_column.get("crs")
        if old_crs is None and "crs" in old_column and not crs_arg:
            raise SpatialOrderError("GeoParquet explicitly declares null CRS; provide --crs")
        if old_crs is None and "crs" not in old_column:
            old_crs = pyproj.CRS.from_user_input("OGC:CRS84").to_json_dict()
        if crs_arg:
            requested = pyproj.CRS.from_user_input(crs_arg)
            if old_crs is not None:
                existing = pyproj.CRS.from_json_dict(old_crs) if isinstance(old_crs, dict) else pyproj.CRS.from_user_input(old_crs)
                if not existing.equals(requested, ignore_axis_order=True):
                    raise SpatialOrderError("--crs conflicts with existing GeoParquet CRS")
            old_crs = requested.to_json_dict()
    else:
        if not crs_arg:
            raise SpatialOrderError("input without GeoParquet CRS metadata requires --crs")
        old_crs = pyproj.CRS.from_user_input(crs_arg).to_json_dict()
        geo = {"version": "1.1.0", "primary_column": geometry_column, "columns": {}}

    declared_crs = pyproj.CRS.from_json_dict(old_crs) if isinstance(old_crs, dict) else pyproj.CRS.from_user_input(old_crs)
    if not declared_crs.equals(pyproj.CRS.from_user_input("OGC:CRS84"), ignore_axis_order=True):
        raise SpatialOrderError("Hilbert quantization requires WGS 84 longitude/latitude coordinates")

    names = schema.names
    if "bbox" in names:
        bbox_type = schema.field("bbox").type
        if not pa.types.is_struct(bbox_type) or not all(name in (bbox_type.names or []) for name in BBOX_FIELDS):
            raise SpatialOrderError("existing bbox field has an unsupported schema")
        output_fields = list(schema)
    else:
        bbox_field = pa.field("bbox", pa.struct([pa.field(n, pa.float64(), nullable=True) for n in BBOX_FIELDS]))
        output_fields = [*schema, bbox_field]

    geo["version"] = "1.1.0"
    geo["primary_column"] = geometry_column
    columns = geo.setdefault("columns", {})
    column = columns.setdefault(geometry_column, {})
    column["encoding"] = "WKB"
    column["geometry_types"] = geometry_types
    column["crs"] = old_crs
    column["bbox"] = bbox_global
    column["covering"] = {"bbox": {name: ["bbox", name] for name in BBOX_FIELDS}}
    metadata[b"geo"] = json.dumps(geo, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return pa.schema(output_fields, metadata=metadata)


def _input_bbox(batch: pa.RecordBatch, geometry_column: str, bbox_exists: bool) -> tuple[pa.StructArray, np.ndarray, np.ndarray, Counter[str]]:
    geometry = batch.column(batch.schema.get_field_index(geometry_column))
    bounds, usable, types = _geometry_bounds(geometry)
    derived = _bbox_struct(bounds, usable)
    if bbox_exists:
        box = batch.column(batch.schema.get_field_index("bbox"))
        if not pa.types.is_struct(box.type):
            raise SpatialOrderError("existing bbox field is not a struct")
        if not _bbox_arrays_equal(box, derived):
            raise SpatialOrderError("existing bbox child values differ from WKB-derived bounds")
        return box, bounds, usable, types
    return derived, bounds, usable, types


def _bbox_arrays_equal(actual: pa.StructArray, expected: pa.StructArray) -> bool:
    if not pa.types.is_struct(actual.type) or not pa.types.is_struct(expected.type):
        return False
    if not all(name in (actual.type.names or []) and name in (expected.type.names or []) for name in BBOX_FIELDS):
        return False
    if not np.array_equal(actual.is_valid().to_numpy(zero_copy_only=False),
                          expected.is_valid().to_numpy(zero_copy_only=False)):
        return False
    for name in BBOX_FIELDS:
        actual_child, expected_child = actual.field(name), expected.field(name)
        if not (pa.types.is_floating(actual_child.type) and pa.types.is_floating(expected_child.type)):
            return False
        actual_valid = actual_child.is_valid().to_numpy(zero_copy_only=False)
        expected_valid = expected_child.is_valid().to_numpy(zero_copy_only=False)
        if not np.array_equal(actual_valid, expected_valid):
            return False
        actual_values = actual_child.to_numpy(zero_copy_only=False)
        expected_values = expected_child.to_numpy(zero_copy_only=False)
        if not np.array_equal(actual_values[actual_valid], expected_values[expected_valid]):
            return False
    return True


def _feature_keys(batch: pa.RecordBatch, geometry_column: str,
                  bbox_exists: bool) -> tuple[np.ndarray, pa.StructArray, Counter[str]]:
    box, bounds, valid, types = _input_bbox(batch, geometry_column, bbox_exists)
    return hilbert_keys(bounds, valid), box, types


def _union(a: tuple[float, float, float, float] | None,
           b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


class ChunkMetrics:
    """Streaming equivalent of Rashid 0.1.8's ten synthetic bbox chunks."""
    def __init__(self, valid_rows: int):
        self.valid_rows = valid_rows
        self.chunk_size = math.ceil(valid_rows / 10) if valid_rows else 0
        self.valid_seen = 0
        self.current: tuple[float, float, float, float] | None = None
        self.boxes: list[tuple[float, float, float, float]] = []

    def add(self, box: pa.StructArray) -> None:
        bounds, valid = _bounds_from_bbox(box)
        indices = np.flatnonzero(valid)
        offset = 0
        while offset < len(indices):
            in_chunk = self.valid_seen % self.chunk_size
            take = min(len(indices) - offset, self.chunk_size - in_chunk)
            rows = bounds[indices[offset:offset + take]]
            part = (float(rows[:, 0].min()), float(rows[:, 1].min()),
                    float(rows[:, 2].max()), float(rows[:, 3].max()))
            self.current = _union(self.current, part)
            self.valid_seen += take
            offset += take
            if self.valid_seen % self.chunk_size == 0 or self.valid_seen == self.valid_rows:
                if self.current is not None:
                    self.boxes.append(self.current)
                self.current = None

    def report(self) -> dict[str, Any]:
        if self.valid_seen != self.valid_rows:
            raise SpatialOrderError(f"bbox metric counted {self.valid_seen} usable rows; expected {self.valid_rows}")
        pairs = max(0, len(self.boxes) - 1)
        overlaps = sum(_overlap(self.boxes[i], self.boxes[i + 1]) for i in range(pairs))
        overlap_fraction = overlaps / pairs if pairs else 0.0
        extent = None
        for box in self.boxes:
            extent = _union(extent, box)
        extent_area = max(0.0, extent[2] - extent[0]) * max(0.0, extent[3] - extent[1]) if extent else 0.0
        mean_chunk_area = (sum(max(0.0, b[2]-b[0]) * max(0.0, b[3]-b[1]) for b in self.boxes) / len(self.boxes)) if self.boxes else 0.0
        area_ratio = mean_chunk_area / extent_area if extent_area else 0.0
        return {
            "validator": "Rashid 0.1.8 PTL-DAT-006 predicate",
            "chunks": len(self.boxes),
            "rows_per_chunk_ceiling": self.chunk_size,
            "adjacent_pairs": pairs,
            "overlapping_pairs": overlaps,
            "overlap_fraction": overlap_fraction,
            "overlap_limit_exclusive": MAX_OVERLAP_FRACTION,
            "mean_chunk_area_over_global_extent_area": area_ratio,
            "area_ratio_limit_exclusive": MAX_LOCALITY_RATIO,
            "passed": overlap_fraction < MAX_OVERLAP_FRACTION or area_ratio < MAX_LOCALITY_RATIO,
        }


def _json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _checkpoint_digest(checkpoint: dict[str, Any]) -> str:
    payload = dict(checkpoint)
    payload.pop("checkpoint_payload_sha256", None)
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    value = dict(checkpoint)
    value["checkpoint_payload_sha256"] = _checkpoint_digest(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_canonical_json_bytes(value))
    path.chmod(0o444)
    return value


def _read_checkpoint(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise SpatialOrderError(f"cannot read stage checkpoint: {type(error).__name__}: {error}") from error
    if not isinstance(value, dict) or value.get("checkpoint_version") != 1:
        raise SpatialOrderError("stage checkpoint has an unsupported format")
    if value.get("status") != "pending_validation":
        raise SpatialOrderError("stage checkpoint is not pending validation")
    if value.get("checkpoint_payload_sha256") != _checkpoint_digest(value):
        raise SpatialOrderError("stage checkpoint checksum mismatch")
    return value


def _schema_b64(schema: pa.Schema) -> str:
    return base64.b64encode(schema.serialize().to_pybytes()).decode("ascii")


def _schema_from_b64(value: str, label: str) -> pa.Schema:
    try:
        return pa.ipc.read_schema(pa.BufferReader(base64.b64decode(value, validate=True)))
    except Exception as error:
        raise SpatialOrderError(f"invalid {label} in stage checkpoint: {type(error).__name__}: {error}") from error


def _helper_sha256() -> str:
    return sha256(Path(__file__).resolve())


def _check_rss(limit: int, phase: str = "unspecified") -> int:
    value = peak_rss_bytes()
    if value >= limit:
        raise SpatialOrderError(f"peak RSS {value} bytes reached configured cap {limit} in phase {phase}")
    return value


class DiskGuard:
    """Check task-owned allocated bytes and free space during each phase."""
    def __init__(self, work_dir: Path, stage_path: Path, output_path: Path,
                 input_size: int, baseline: int, limit: int, free_floor: int,
                 enabled: bool = True):
        self.work_dir = work_dir
        self.stage_path = stage_path
        self.output_path = output_path
        self.input_size = input_size
        self.baseline = baseline
        self.limit = limit
        self.free_floor = free_floor
        self.enabled = enabled

    def check(self) -> None:
        if not self.enabled:
            return
        current = self.baseline + self.input_size
        if self.work_dir.exists():
            current += sum(path.stat().st_blocks * 512 for path in self.work_dir.rglob("*") if path.is_file())
        for path in (self.stage_path, self.output_path):
            if path.exists():
                current += path.stat().st_blocks * 512
        if current > self.limit:
            raise SpatialOrderError(f"task-owned allocated bytes {current} exceed configured limit {self.limit}")
        self.check_free()

    def check_free(self) -> None:
        if not self.enabled:
            return
        free = shutil.disk_usage(self.output_path.parent).free
        if free < self.free_floor:
            raise SpatialOrderError(f"free disk {free} bytes fell below configured floor {self.free_floor}")


def _bucket_writer_schema(schema: pa.Schema) -> pa.Schema:
    if KEY_COLUMN in schema.names:
        raise SpatialOrderError(f"reserved temporary column already exists: {KEY_COLUMN}")
    return pa.schema([*schema, pa.field(KEY_COLUMN, pa.uint64(), nullable=False)], metadata=schema.metadata)


def _flush_bucket(index: int, writers: list[Any], pending: list[list[pa.Table]],
                  pending_rows: list[int], paths: list[Path], schema: pa.Schema) -> None:
    if not pending[index]:
        return
    table = (pa.concat_tables(pending[index]) if len(pending[index]) > 1 else pending[index][0]).combine_chunks()
    writer = writers[index]
    if writer is None:
        sink = pa.OSFile(str(paths[index]), "wb")
        writer = pa.ipc.new_file(sink, schema, options=pa.ipc.IpcWriteOptions(compression="zstd", use_threads=False))
        writers[index] = (writer, sink)
    writer, _sink = writers[index]
    for batch in table.to_batches(max_chunksize=DEFAULT_BUFFER_ROWS):
        writer.write_batch(batch)
    pending[index].clear()
    pending_rows[index] = 0


def _write_spatial_buckets(bucket_dir: Path, source: pq.ParquetFile,
                           input_schema: pa.Schema, output_schema: pa.Schema,
                           identifier_column: str, geometry_column: str, keys: np.ndarray,
                           bucket_for_row: np.ndarray, bucket_count: int, bbox_exists: bool,
                           batch_rows: int, buffer_rows: int, max_rss_bytes: int,
                           disk_guard: DiskGuard) -> tuple[list[Path], list[int]]:
    bucket_dir.mkdir()
    paths = [bucket_dir / f"bucket-{i:03}.arrow" for i in range(bucket_count)]
    temp_schema = _bucket_writer_schema(output_schema)
    writers: list[Any] = [None] * bucket_count
    pending: list[list[pa.Table]] = [[] for _ in range(bucket_count)]
    pending_rows = [0] * bucket_count
    row_counts = [0] * bucket_count
    input_count = 0
    try:
        for batch in source.iter_batches(batch_size=batch_rows, columns=input_schema.names, use_threads=False):
            ids = batch.column(batch.schema.get_field_index(identifier_column)).to_numpy(zero_copy_only=False)
            if len(ids) and (int(ids[0]) != input_count + 1 or np.any(ids != np.arange(input_count + 1, input_count + 1 + len(ids), dtype=ids.dtype))):
                raise SpatialOrderError("identifier ceased to equal the one-based source row ordinal during staging")
            batch_keys, box, _ = _feature_keys(batch, geometry_column, bbox_exists)
            start = input_count
            stop = start + batch.num_rows
            if not np.array_equal(batch_keys, keys[start:stop]):
                raise SpatialOrderError("WKB/bbox changed between spatial-key and staging passes")
            if not bbox_exists:
                table = pa.Table.from_batches([batch]).append_column("bbox", box)
            else:
                table = pa.Table.from_batches([batch])
            table = table.replace_schema_metadata(output_schema.metadata)
            table = table.cast(output_schema)
            key_array = pa.array(batch_keys, type=pa.uint64())
            table = table.append_column(pa.field(KEY_COLUMN, pa.uint64(), nullable=False), key_array)
            bucket_ids = bucket_for_row[start:stop]
            for bucket in np.unique(bucket_ids):
                mask = bucket_ids == bucket
                selection = pa.array(np.flatnonzero(mask), type=pa.int64())
                piece = table.take(selection)
                index = int(bucket)
                pending[index].append(piece)
                piece_rows = piece.num_rows
                pending_rows[index] += piece_rows
                row_counts[index] += piece_rows
                if pending_rows[index] >= buffer_rows:
                    _flush_bucket(index, writers, pending, pending_rows, paths, temp_schema)
            input_count += batch.num_rows
            _check_rss(max_rss_bytes, "bucket_write")
            disk_guard.check_free()
            if input_count % 100_000 < batch.num_rows:
                disk_guard.check()
        if input_count != source.metadata.num_rows:
            raise SpatialOrderError("staging pass row count differs from input footer")
        for i in range(bucket_count):
            _flush_bucket(i, writers, pending, pending_rows, paths, temp_schema)
    finally:
        for entry in writers:
            if entry is not None:
                writer, sink = entry
                writer.close()
                sink.close()
    if sum(row_counts) != source.metadata.num_rows or any(count == 0 for count in row_counts):
        raise SpatialOrderError("spatial bucket multiplicity differs from input row count")
    return paths, row_counts


def _merge_spatial_buckets(bucket_paths: list[Path], bucket_dir: Path, stage_path: Path,
                           output_schema: pa.Schema, identifier_column: str,
                           row_group_size: int, max_rss_bytes: int,
                           disk_guard: DiskGuard) -> int:
    writer = pq.ParquetWriter(stage_path, output_schema, compression="zstd", compression_level=6,
                              use_dictionary=True, write_statistics=True, version="2.6")
    total = 0
    try:
        for path in bucket_paths:
            with pa.memory_map(str(path), "r") as source:
                table = pa.ipc.open_file(source).read_all()
            _check_rss(max_rss_bytes, "bucket_load")
            if KEY_COLUMN not in table.schema.names:
                raise SpatialOrderError(f"temporary bucket lacks {KEY_COLUMN}")
            order = pc.sort_indices(table, sort_keys=[(KEY_COLUMN, "ascending"), (identifier_column, "ascending")])
            sorted_table = table.take(order).drop([KEY_COLUMN])
            del table, order
            gc.collect()
            pa.default_memory_pool().release_unused()
            _check_rss(max_rss_bytes, "bucket_reorder")
            sorted_table = sorted_table.replace_schema_metadata(output_schema.metadata)
            if not sorted_table.schema.equals(output_schema, check_metadata=True):
                raise SpatialOrderError("sorted bucket schema differs from final schema")
            writer.write_table(sorted_table, row_group_size=row_group_size)
            total += sorted_table.num_rows
            path.unlink()
            del sorted_table
            gc.collect()
            pa.default_memory_pool().release_unused()
            _check_rss(max_rss_bytes, "bucket_merge")
            disk_guard.check()
    finally:
        writer.close()
    try:
        bucket_dir.rmdir()
    except OSError:
        pass
    return total


def compare_source_tables(expected: pa.Table, restored: pa.Table, schema: pa.Schema) -> None:
    """Require exact source-order field values, nulls, WKB, and multiplicity."""
    if expected.num_rows != restored.num_rows:
        raise SpatialOrderError("source-order restored table changed feature multiplicity")
    for field in schema:
        if field.name not in restored.schema.names:
            raise SpatialOrderError(f"restored output lost source field {field.name}")
        if restored.schema.field(field.name).type != field.type:
            raise SpatialOrderError(f"restored output changed type for source field {field.name}")
        if not restored.column(field.name).equals(expected.column(field.name)):
            raise SpatialOrderError(f"source value/null/WKB mismatch after restoring identifier order: {field.name}")


def _bbox_metadata(schema: pa.Schema, geometry_column: str) -> dict[str, Any]:
    raw = (schema.metadata or {}).get(b"geo")
    if raw is None:
        raise SpatialOrderError("output is missing GeoParquet metadata")
    try:
        geo = json.loads(raw)
        column = geo["columns"][geometry_column]
    except Exception as error:
        raise SpatialOrderError(f"invalid output geometry metadata: {error}") from error
    if (geo.get("version") != "1.1.0" or geo.get("primary_column") != geometry_column or
            column.get("encoding") != "WKB" or
            column.get("covering", {}).get("bbox") != {n: ["bbox", n] for n in BBOX_FIELDS}):
        raise SpatialOrderError("output GeoParquet 1.1 WKB/bbox covering metadata is invalid")
    crs = column.get("crs")
    if crs is None:
        raise SpatialOrderError("output GeoParquet CRS is absent or explicitly unknown")
    return {"geo": geo, "column": column, "crs": pyproj.CRS.from_json_dict(crs)}


def _wkb_identity(value: pa.Scalar) -> tuple[bool, int, bytes | None]:
    """Hash the Arrow byte view directly without copying a whole WKB batch."""
    if not value.is_valid:
        return True, 0, None
    buffer = value.as_buffer()
    return False, len(buffer), hashlib.sha256(buffer).digest()


def _restore_and_validate(input_path: Path, output_stage: Path, identifier_column: str,
                          geometry_column: str, input_schema: pa.Schema, output_schema: pa.Schema,
                          bbox_was_present: bool, rows: int, valid_bbox_rows: int,
                          expected_global_bbox: list[float] | None, expected_types: Counter[str],
                          bucket_count: int, batch_rows: int, buffer_rows: int,
                          max_rss_bytes: int, work_dir: Path,
                          disk_guard: DiskGuard) -> dict[str, Any]:
    """Compare every source cell using bounded columns and per-feature WKB hashes.

    Wide attributes are restored by ID one column at a time. WKB is never loaded
    as a complete column: every byte is SHA-256 hashed, with byte length and null
    state checked independently for every native ID. This is a full cryptographic
    byte comparison, not an aggregate checksum or a sample.
    """
    source = pq.ParquetFile(input_path)
    output = pq.ParquetFile(output_stage)
    if output.metadata.num_rows != rows or source.metadata.num_rows != rows:
        raise SpatialOrderError("source/output feature multiplicity differs")
    actual_schema = source_schema(output)
    if not actual_schema.equals(output_schema, check_metadata=True):
        raise SpatialOrderError("completed spatial output schema/metadata differs")
    output_info = _bbox_metadata(actual_schema, geometry_column)
    for field in input_schema:
        if not actual_schema.field(field.name).equals(field, check_metadata=True):
            raise SpatialOrderError(f"original field schema/metadata changed: {field.name}")

    id_column = output.read(columns=[identifier_column], use_threads=False).column(0)
    if id_column.null_count:
        raise SpatialOrderError("output native identifier contains nulls")
    ids = id_column.combine_chunks().to_numpy(zero_copy_only=False)
    inverse = np.argsort(ids, kind="stable")
    if not np.array_equal(ids[inverse], np.arange(1, rows + 1, dtype=ids.dtype)):
        raise SpatialOrderError("output identifiers do not preserve the complete unique source ordinal 1..N")
    restore_positions = pa.array(inverse, type=pa.int64())
    attributes_compared = 0
    for field in input_schema:
        if field.name == geometry_column:
            continue
        expected = source.read(columns=[field.name], use_threads=False).column(0)
        spatial = output.read(columns=[field.name], use_threads=False).column(0)
        restored = spatial.take(restore_positions)
        if not expected.equals(restored):
            raise SpatialOrderError(f"source value/null mismatch after restoring identifier order: {field.name}")
        attributes_compared += rows
        del expected, spatial, restored
        gc.collect()
        pa.default_memory_pool().release_unused()
        _check_rss(max_rss_bytes, "attribute_column_comparison:" + field.name)
    output.close()
    source.close()
    del id_column, ids, inverse, restore_positions, output, source
    gc.collect()
    pa.default_memory_pool().release_unused()

    # Release column-reader state before opening a geometry-only stream.
    source = pq.ParquetFile(input_path)
    geometry_hashes = np.zeros((rows, 32), dtype=np.uint8)
    geometry_lengths = np.zeros(rows, dtype=np.uint64)
    geometry_nulls = np.ones(rows, dtype=np.bool_)
    source_count = 0
    for batch in source.iter_batches(batch_size=32, columns=[identifier_column, geometry_column], use_threads=False):
        batch_ids = batch.column(0)
        if batch_ids.null_count or not np.array_equal(batch_ids.to_numpy(zero_copy_only=False),
                np.arange(source_count + 1, source_count + batch.num_rows + 1)):
            raise SpatialOrderError("raw source identifier order changed during validation")
        wkb_array = batch.column(1)
        for offset in range(batch.num_rows):
            index = source_count + offset
            is_null, byte_length, digest = _wkb_identity(wkb_array[offset])
            geometry_nulls[index] = is_null
            geometry_lengths[index] = byte_length
            if digest is not None:
                geometry_hashes[index] = np.frombuffer(digest, dtype=np.uint8)
        source_count += batch.num_rows
        del wkb_array, batch
        _check_rss(max_rss_bytes, "source_wkb_hashing")
    source.close()
    del source, batch_ids
    gc.collect()
    pa.default_memory_pool().release_unused()
    if source_count != rows:
        raise SpatialOrderError("source WKB stream changed feature multiplicity")

    geometry_types: Counter[str] = Counter()
    global_min = np.array([np.inf, np.inf], dtype=np.float64)
    global_max = np.array([-np.inf, -np.inf], dtype=np.float64)
    metric = ChunkMetrics(valid_bbox_rows)
    output_count = 0
    bbox_count = 0
    output = pq.ParquetFile(output_stage)
    for batch in output.iter_batches(batch_size=32, columns=[identifier_column, geometry_column, "bbox"], use_threads=False):
        batch_ids = batch.column(0).to_numpy(zero_copy_only=False)
        wkb_array = batch.column(1)
        for offset, native_id in enumerate(batch_ids):
            index = int(native_id) - 1
            is_null, byte_length, digest = _wkb_identity(wkb_array[offset])
            if is_null != bool(geometry_nulls[index]):
                raise SpatialOrderError(f"WKB null state changed for native ID {int(native_id)}")
            if digest is not None:
                if byte_length != int(geometry_lengths[index]) or not np.array_equal(
                        np.frombuffer(digest, dtype=np.uint8), geometry_hashes[index]):
                    raise SpatialOrderError(f"WKB SHA-256/byte length differs for native ID {int(native_id)}")
        bounds, valid, types = _geometry_bounds(wkb_array)
        geometry_types.update(types)
        bbox_expected = _bbox_struct(bounds, valid)
        bbox_actual = batch.column(2)
        if not _bbox_arrays_equal(bbox_actual, bbox_expected):
            raise SpatialOrderError("derived bbox child differs from independently recomputed WKB bounds")
        bbox_count += int(valid.sum())
        if valid.any():
            global_min = np.minimum(global_min, bounds[valid, :2].min(axis=0))
            global_max = np.maximum(global_max, bounds[valid, 2:].max(axis=0))
        metric.add(bbox_actual)
        output_count += batch.num_rows
        del wkb_array, bbox_actual, bbox_expected, batch
        _check_rss(max_rss_bytes, "final_wkb_and_bbox_comparison")
    output.close()
    if output_count != rows or bbox_count != valid_bbox_rows or geometry_types != expected_types:
        raise SpatialOrderError("output row count, usable bounds or geometry types differ")
    global_bbox = [float(global_min[0]), float(global_min[1]), float(global_max[0]), float(global_max[1])]
    if expected_global_bbox is not None and global_bbox != expected_global_bbox:
        raise SpatialOrderError("independently recomputed global WKB extent differs")
    if output_info["column"].get("bbox") != global_bbox or output_info["column"].get("geometry_types") != sorted(geometry_types):
        raise SpatialOrderError("output extent/geometry-type metadata differs from WKB")
    rashid_metric = metric.report()
    if not rashid_metric["passed"]:
        raise SpatialOrderError("completed spatial ordering fails the Rashid PTL-DAT-006 locality predicate")
    disk_guard.check()
    return {
        "source_rows": output_count,
        "source_fields_compared": len(input_schema.names),
        "source_attribute_values_nulls_compared": attributes_compared,
        "source_values_nulls_and_raw_wkb_compared": True,
        "source_order_reconstructed_and_compared": True,
        "derived_bbox_values_recomputed_and_compared": True,
        "wkb_rows_compared": output_count,
        "wkb_validation_batch_rows": 32,
        "wkb_hash_input": "Arrow scalar byte buffer; no whole-batch Python byte copies",
        "wkb_comparison_method": "Complete per-native-ID SHA-256, byte length and null-state equality; every WKB byte hashed independently in both files",
        "attribute_comparison_method": "Exact Arrow equality for each original column after restoring native identifier order",
        "global_bbox": global_bbox,
        "geometry_types": dict(sorted(geometry_types.items())),
        "rashid_order_metrics": rashid_metric,
    }


def _passed_report(input_path: Path, output_path: Path, output_file_path: Path,
                   input_hash: str, input_size: int,
                   identifier_column: str, geometry_column: str, input_schema: pa.Schema,
                   bbox_exists: bool, rows: int, bucket_count: int,
                   bucket_counts_expected: np.ndarray, row_group_size: int,
                   validation: dict[str, Any], disk: dict[str, Any],
                   sort_peak_rss_bytes: int, validation_peak_rss_bytes: int,
                   max_rss_bytes: int, execution_mode: str,
                   checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the same complete success report for either execution path."""
    output_file = pq.ParquetFile(output_file_path)
    row_groups = output_file.metadata.num_row_groups
    output_file.close()
    output_hash = sha256(output_file_path)
    output_size = output_file_path.stat().st_size
    report = {
        "status": "passed",
        "input": {"path": str(input_path), "sha256": input_hash, "size_bytes": input_size,
                  "allocated_bytes": input_path.stat().st_blocks * 512},
        "output": {"path": str(output_path), "sha256": output_hash, "size_bytes": output_size,
                   "allocated_bytes": output_file_path.stat().st_blocks * 512},
        "identifier_column": identifier_column,
        "geometry_column": geometry_column,
        "transformation": "spatial_order",
        "source_rows": rows,
        "source_columns": input_schema.names,
        "source_order_identity": f"{identifier_column} exactly equals the one-based input row ordinal 1..{rows}",
        "source_order_reconstructed_and_compared": validation["source_order_reconstructed_and_compared"],
        "source_values_nulls_and_raw_wkb_compared": validation["source_values_nulls_and_raw_wkb_compared"],
        "derived_bbox_values_recomputed_and_compared": validation["derived_bbox_values_recomputed_and_compared"],
        "bbox_was_added": not bbox_exists,
        "global_bbox": validation["global_bbox"],
        "geometry_types": validation["geometry_types"],
        "validation": validation,
        "spatial_order": {
            "key": "16-bit Hilbert distance of the WGS84 bbox center",
            "quantization": "x=floor((lon+180)/360*65535), y=floor((lat+90)/180*65535), clamped to [0,65535]",
            "tie_breaker": identifier_column + " ascending",
            "buckets": bucket_count,
            "bucket_rows_min": int(bucket_counts_expected.min()),
            "bucket_rows_max": int(bucket_counts_expected.max()),
            "row_group_size": row_group_size,
            "rashid_order_metrics": validation["rashid_order_metrics"],
        },
        "row_groups": row_groups,
        "geometry_batch_rows_max": 128,
        "arrow_cpu_threads": 2,
        "arrow_io_threads": 2,
        "ipc_threaded_compression": False,
        "peak_rss_bytes": max(sort_peak_rss_bytes, validation_peak_rss_bytes),
        "peak_rss_limit_bytes": max_rss_bytes,
        "phase_peak_rss_bytes": {
            "sort_and_merge": sort_peak_rss_bytes,
            "full_validation": validation_peak_rss_bytes,
        },
        "process_execution": {
            "mode": execution_mode,
            "processes_sequential": execution_mode == "sequential_processes",
        },
        "disk_preflight": disk,
        "created": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if checkpoint is not None:
        report["stage_checkpoint"] = {
            "path": checkpoint["checkpoint_path"],
            "sha256": checkpoint.get("_checkpoint_file_sha256") or sha256(Path(checkpoint["checkpoint_path"])),
            "payload_sha256": checkpoint["checkpoint_payload_sha256"],
            "helper_sha256": checkpoint["helper_sha256"],
        }
    return report


def _promote_stage_and_report(stage_path: Path, output_path: Path, report_path: Path,
                               report: dict[str, Any]) -> None:
    """Promote without replacing either immutable destination."""
    if output_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable output: {output_path}")
    if report_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable report: {report_path}")
    report_temp = report_path.with_name(report_path.name + f".partial-{os.getpid()}")
    if report_temp.exists():
        raise SpatialOrderError(f"refuse existing temporary report path: {report_temp}")
    try:
        _json_write(report_temp, report)
        report_temp.chmod(0o444)
        # Both moves stay on the destination filesystem. The fresh sequential
        # workflow and preflight existence checks make the rename a no-replace
        # promotion for this single-writer tool.
        if output_path.exists() or report_path.exists():
            raise SpatialOrderError("refuse overwrite immutable output or report during promotion")
        os.rename(stage_path, output_path)
        output_path.chmod(0o444)
        os.rename(report_temp, report_path)
        report_path.chmod(0o444)
    except Exception:
        # Keep any output/stage/report bytes for diagnosis; never remove a
        # partially promoted artifact automatically.
        raise


def _preflight(input_path: Path, output_path: Path, input_size: int,
               min_start_free: int, min_remaining_free: int,
               task_baseline: int, task_disk_limit: int) -> dict[str, Any]:
    # Transform and restoration validation each hold at most one temporary copy
    # beside the final output; conservatively reserve two input-sized copies.
    overhead = 128 * 1024 * 1024
    estimated_artifact_peak = input_size * 3 + overhead
    estimated_task_peak = task_baseline + estimated_artifact_peak
    free = shutil.disk_usage(output_path.parent).free
    if free < min_start_free:
        raise SpatialOrderError(f"disk guard requires {min_start_free} free bytes before writing; found {free}")
    if free < estimated_artifact_peak - input_size + min_remaining_free:
        raise SpatialOrderError(f"disk guard needs {estimated_artifact_peak-input_size} staging/output bytes plus {min_remaining_free} free; found {free}")
    if estimated_task_peak > task_disk_limit:
        raise SpatialOrderError(f"task-owned disk estimate {estimated_task_peak} exceeds limit {task_disk_limit}")
    return {
        "free_bytes_before": free,
        "estimated_artifact_peak_bytes": estimated_artifact_peak,
        "task_owned_baseline_bytes": task_baseline,
        "estimated_task_peak_bytes": estimated_task_peak,
        "task_disk_limit_bytes": task_disk_limit,
        "minimum_start_free_bytes": min_start_free,
        "minimum_remaining_free_bytes": min_remaining_free,
        "estimate_note": "Conservatively counts one input plus at most two input-sized temporary/output copies for one asset. Source archive and producer PDFs are excluded from the task-owned baseline.",
    }


def _spatial_order_impl(input_path: Path, output_path: Path, report_path: Path,
                  identifier_column: str, geometry_column: str,
                  crs: str | None = None, bucket_count: int = DEFAULT_BUCKETS,
                  batch_rows: int = DEFAULT_BATCH_ROWS, buffer_rows: int = DEFAULT_BUFFER_ROWS,
                  row_group_size: int = DEFAULT_ROW_GROUP_SIZE,
                  max_rss_bytes: int = DEFAULT_MAX_RSS_BYTES,
                  minimum_start_free_bytes: int = DEFAULT_START_FREE_BYTES,
                  minimum_remaining_free_bytes: int = DEFAULT_REMAINING_FREE_BYTES,
                  task_owned_baseline_bytes: int = 0,
                  task_disk_limit_bytes: int = DEFAULT_TASK_DISK_LIMIT_BYTES,
                  enforce_guards: bool = True, defer_validation: bool = False,
                  checkpoint_path: Path | None = None) -> dict[str, Any]:
    pa.set_cpu_count(2)
    pa.set_io_thread_count(2)
    input_path, output_path, report_path = input_path.resolve(), output_path.resolve(), report_path.resolve()
    if defer_validation and checkpoint_path is None:
        raise SpatialOrderError("--defer-validation requires an explicit checkpoint path")
    if not defer_validation and checkpoint_path is not None:
        raise SpatialOrderError("checkpoint_path is valid only with defer_validation")
    if checkpoint_path is not None:
        checkpoint_path = checkpoint_path.resolve()
    if input_path == output_path or report_path in (input_path, output_path):
        raise SpatialOrderError("input, output, and report paths must be distinct")
    if checkpoint_path is not None and checkpoint_path in (input_path, output_path, report_path):
        raise SpatialOrderError("input, output, report, and checkpoint paths must be distinct")
    if not input_path.is_file():
        raise SpatialOrderError(f"input Parquet is missing: {input_path}")
    if output_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable output: {output_path}")
    if report_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable report: {report_path}")
    if checkpoint_path is not None and checkpoint_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable checkpoint: {checkpoint_path}")
    if bucket_count < 2 or batch_rows < 1 or buffer_rows < 1 or row_group_size < 1:
        raise SpatialOrderError("bucket, batch, buffer, and row-group sizes must be positive")
    if (max_rss_bytes <= 0 or max_rss_bytes > DEFAULT_MAX_RSS_BYTES or
            minimum_start_free_bytes < DEFAULT_START_FREE_BYTES or
            minimum_remaining_free_bytes < DEFAULT_REMAINING_FREE_BYTES or
            task_disk_limit_bytes > DEFAULT_TASK_DISK_LIMIT_BYTES):
        raise SpatialOrderError("resource guards may be made stricter but not relaxed beyond the release limits")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    input_size = input_path.stat().st_size
    disk = _preflight(input_path, output_path, input_size, minimum_start_free_bytes,
                      minimum_remaining_free_bytes, task_owned_baseline_bytes,
                      task_disk_limit_bytes) if enforce_guards else {
        "free_bytes_before": shutil.disk_usage(output_path.parent).free,
        "estimated_artifact_peak_bytes": input_size * 3,
        "task_owned_baseline_bytes": task_owned_baseline_bytes,
        "estimated_task_peak_bytes": task_owned_baseline_bytes + input_size * 3,
        "task_disk_limit_bytes": task_disk_limit_bytes,
        "minimum_start_free_bytes": minimum_start_free_bytes,
        "minimum_remaining_free_bytes": minimum_remaining_free_bytes,
        "estimate_note": "Guards disabled only for bounded unit fixtures.",
    }
    input_hash = sha256(input_path)
    helper_hash = _helper_sha256()
    source = pq.ParquetFile(input_path)
    input_schema = source_schema(source)
    if identifier_column not in input_schema.names:
        raise SpatialOrderError(f"identifier column is missing: {identifier_column}")
    if not pa.types.is_integer(input_schema.field(identifier_column).type):
        raise SpatialOrderError("identifier column must be an integer field")
    if geometry_column not in input_schema.names:
        raise SpatialOrderError(f"geometry column is missing: {geometry_column}")
    geometry_type = input_schema.field(geometry_column).type
    if not (pa.types.is_binary(geometry_type) or pa.types.is_large_binary(geometry_type)):
        raise SpatialOrderError("geometry column must contain WKB binary values")
    bbox_exists = "bbox" in input_schema.names
    if KEY_COLUMN in input_schema.names:
        raise SpatialOrderError(f"input contains reserved temporary field {KEY_COLUMN}")
    rows = int(source.metadata.num_rows)
    if rows <= 0:
        raise SpatialOrderError("input Parquet has no rows")
    if bucket_count > rows:
        raise SpatialOrderError("bucket count cannot exceed the source feature count")

    # Pass 1: verify the reversible identifier, compute one uint64 key per row,
    # and derive the exact output GeoParquet schema/metadata.
    keys = np.empty(rows, dtype=np.uint64)
    ids_seen = 0
    valid_bbox_rows = 0
    global_min = np.array([np.inf, np.inf], dtype=np.float64)
    global_max = np.array([-np.inf, -np.inf], dtype=np.float64)
    geometry_types: Counter[str] = Counter()
    index_columns = [identifier_column, geometry_column, *(["bbox"] if bbox_exists else [])]
    for batch in source.iter_batches(batch_size=min(batch_rows, 128), columns=index_columns, use_threads=False):
        ids = batch.column(batch.schema.get_field_index(identifier_column))
        if ids.null_count:
            raise SpatialOrderError("identifier column contains null values")
        id_values = ids.to_numpy(zero_copy_only=False)
        expected = np.arange(ids_seen + 1, ids_seen + 1 + len(id_values), dtype=id_values.dtype)
        if not np.array_equal(id_values, expected):
            raise SpatialOrderError("identifier must equal the one-based source-order row ordinal 1..N")
        batch_keys, box, types = _feature_keys(batch, geometry_column, bbox_exists)
        geometry_types.update(types)
        bounds, valid = _bounds_from_bbox(box)
        valid_bbox_rows += int(valid.sum())
        if valid.any():
            global_min = np.minimum(global_min, bounds[valid, :2].min(axis=0))
            global_max = np.maximum(global_max, bounds[valid, 2:].max(axis=0))
        keys[ids_seen:ids_seen + len(id_values)] = batch_keys
        ids_seen += len(id_values)
        _check_rss(max_rss_bytes, "key_scan")
    if ids_seen != rows or valid_bbox_rows == 0:
        raise SpatialOrderError("input feature or usable bbox count differs from its Parquet footer")
    global_bbox = [float(global_min[0]), float(global_min[1]), float(global_max[0]), float(global_max[1])]
    output_schema = _geo_info(input_schema, geometry_column, crs, sorted(geometry_types), global_bbox)
    # If bboxes already exist, source cells and metadata stay identical; the
    # source-derived global bounds and types must agree with their declarations.
    if bbox_exists:
        geo = json.loads((input_schema.metadata or {})[b"geo"])
        source_column = geo["columns"][geometry_column]
        if source_column.get("bbox") is not None and not np.allclose(source_column["bbox"], global_bbox, rtol=0, atol=1e-12):
            raise SpatialOrderError("input GeoParquet global bbox differs from the bbox children")
        if source_column.get("geometry_types") and sorted(set(source_column["geometry_types"])) != sorted(geometry_types):
            raise SpatialOrderError("input GeoParquet geometry_types differs from the source WKB tally")

    order = np.lexsort((np.arange(rows, dtype=np.uint64) + 1, keys))
    ranks = np.arange(rows, dtype=np.uint64) * bucket_count // rows
    bucket_for_row = np.empty(rows, dtype=np.uint32)
    bucket_for_row[order] = ranks.astype(np.uint32)
    bucket_counts_expected = np.bincount(bucket_for_row.astype(np.int64), minlength=bucket_count)
    stage_path = output_path.with_name(output_path.name + f".partial-{os.getpid()}")
    work_dir = output_path.with_name(output_path.name + f".work-{os.getpid()}")
    if stage_path.exists() or work_dir.exists() or (checkpoint_path is not None and checkpoint_path in (stage_path, work_dir)):
        raise SpatialOrderError("refuse existing temporary spatial-order path")
    work_dir.mkdir()
    disk_guard = DiskGuard(work_dir, stage_path, output_path, input_size,
                           task_owned_baseline_bytes, task_disk_limit_bytes,
                           minimum_remaining_free_bytes, enabled=enforce_guards)
    try:
        bucket_dir = work_dir / "spatial-buckets"
        bucket_paths, bucket_counts = _write_spatial_buckets(
            bucket_dir, source, input_schema, output_schema,
            identifier_column, geometry_column, keys, bucket_for_row,
            bucket_count, bbox_exists, batch_rows, buffer_rows, max_rss_bytes, disk_guard,
        )
        if not np.array_equal(np.asarray(bucket_counts), bucket_counts_expected):
            raise SpatialOrderError("spatial bucket row counts differ from the deterministic Hilbert rank partition")
        source.close()
        source = None
        del keys, order, ranks, bucket_for_row, batch, ids, id_values
        gc.collect()
        pa.default_memory_pool().release_unused()
        merged_rows = _merge_spatial_buckets(
            bucket_paths, bucket_dir, stage_path, output_schema, identifier_column,
            row_group_size, max_rss_bytes, disk_guard,
        )
        if merged_rows != rows:
            raise SpatialOrderError("spatial output feature count differs from source")
        gc.collect()
        pa.default_memory_pool().release_unused()
        sort_peak_rss_bytes = peak_rss_bytes()
        if defer_validation:
            if sort_peak_rss_bytes >= max_rss_bytes:
                raise SpatialOrderError("spatial-order sort peak RSS reached the memory cap before checkpointing")
            if sha256(input_path) != input_hash:
                raise SpatialOrderError("input Parquet changed during spatial ordering")
            if _helper_sha256() != helper_hash:
                raise SpatialOrderError("spatial_order.py changed during staging")
            disk_guard.check()
            stage_hash = sha256(stage_path)
            stage_size = stage_path.stat().st_size
            stage_path.chmod(0o444)
            checkpoint_value = {
                "checkpoint_version": 1,
                "status": "pending_validation",
                "checkpoint_path": str(checkpoint_path),
                "created": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "stage_process_id": os.getpid(),
                "helper_sha256": helper_hash,
                "input": {"path": str(input_path), "sha256": input_hash, "size_bytes": input_size,
                          "allocated_bytes": input_path.stat().st_blocks * 512},
                "stage": {"path": str(stage_path), "sha256": stage_hash, "size_bytes": stage_size,
                          "allocated_bytes": stage_path.stat().st_blocks * 512},
                "output_path": str(output_path),
                "report_path": str(report_path),
                "identifier_column": identifier_column,
                "geometry_column": geometry_column,
                "crs": crs,
                "rows": rows,
                "valid_bbox_rows": valid_bbox_rows,
                "global_bbox": global_bbox,
                "geometry_types": dict(sorted(geometry_types.items())),
                "bbox_was_present": bbox_exists,
                "input_schema_b64": _schema_b64(input_schema),
                "output_schema_b64": _schema_b64(output_schema),
                "bucket_counts_expected": [int(value) for value in bucket_counts_expected],
                "parameters": {
                    "bucket_count": bucket_count,
                    "batch_rows": batch_rows,
                    "buffer_rows": buffer_rows,
                    "row_group_size": row_group_size,
                    "max_rss_bytes": max_rss_bytes,
                    "minimum_start_free_bytes": minimum_start_free_bytes,
                    "minimum_remaining_free_bytes": minimum_remaining_free_bytes,
                    "task_owned_baseline_bytes": task_owned_baseline_bytes,
                    "task_disk_limit_bytes": task_disk_limit_bytes,
                    "enforce_guards": enforce_guards,
                },
                "sort_peak_rss_bytes": sort_peak_rss_bytes,
                "disk_preflight": disk,
            }
            if work_dir.exists():
                work_dir.rmdir()
            sealed = _write_checkpoint(checkpoint_path, checkpoint_value)
            checkpoint_file_hash = sha256(checkpoint_path)
            return {
                "status": "pending_validation",
                "input": checkpoint_value["input"],
                "stage": checkpoint_value["stage"],
                "checkpoint": {"path": str(checkpoint_path), "sha256": checkpoint_file_hash,
                               "payload_sha256": sealed["checkpoint_payload_sha256"]},
                "output_requested": str(output_path),
                "report_requested": str(report_path),
                "sort_peak_rss_bytes": sort_peak_rss_bytes,
                "disk_preflight": disk,
            }
        validation = _restore_and_validate(
            input_path, stage_path, identifier_column, geometry_column,
            input_schema, output_schema, bbox_exists, rows, valid_bbox_rows,
            global_bbox, geometry_types, bucket_count, batch_rows, buffer_rows,
            max_rss_bytes, work_dir, disk_guard,
        )
        if sha256(input_path) != input_hash:
            raise SpatialOrderError("input Parquet changed during spatial ordering")
        if _helper_sha256() != helper_hash:
            raise SpatialOrderError("spatial_order.py changed during spatial ordering")
        disk_guard.check()
        validation_peak_rss_bytes = peak_rss_bytes()
        report = _passed_report(
            input_path, output_path, stage_path, input_hash, input_size,
            identifier_column, geometry_column, input_schema, bbox_exists, rows,
            bucket_count, bucket_counts_expected, row_group_size, validation, disk,
            sort_peak_rss_bytes, validation_peak_rss_bytes, max_rss_bytes,
            "single_process",
        )
        report_build_peak = peak_rss_bytes()
        validation_peak_rss_bytes = max(validation_peak_rss_bytes, report_build_peak)
        if max(sort_peak_rss_bytes, validation_peak_rss_bytes) >= max_rss_bytes:
            raise SpatialOrderError("spatial-order peak RSS reached the memory cap before promotion")
        report["phase_peak_rss_bytes"]["full_validation"] = validation_peak_rss_bytes
        report["peak_rss_bytes"] = max(sort_peak_rss_bytes, validation_peak_rss_bytes)
        _promote_stage_and_report(stage_path, output_path, report_path, report)
        return report
    except Exception as error:
        source_close = source
        if source_close is not None:
            source_close.close()
        failure = {
            "status": "failed",
            "input": {"path": str(input_path), "sha256": input_hash, "size_bytes": input_size},
            "output_requested": str(output_path),
            "transformation": "spatial_order",
            "error_type": type(error).__name__,
            "error": str(error),
            "source_written_by_transform": False,
            "retained_partial_artifacts": _artifact_inventory(
                [stage_path, work_dir, output_path] +
                ([checkpoint_path] if checkpoint_path is not None else []) +
                ([report_path.with_name(report_path.name + f".partial-{os.getpid()}")] if report_path else [])
            ),
        }
        if not report_path.exists():
            _json_write(report_path, failure)
            report_path.chmod(0o444)
        raise
    finally:
        if stage_path.exists():
            # Failed stage bytes are retained with their immutable report.
            pass
        elif work_dir.exists() and output_path.exists() and report_path.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


def spatial_order(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the transform and retain an immutable failure report for every gate."""
    input_path = Path(args[0] if args else kwargs.get("input_path"))
    output_path = Path(args[1] if len(args) > 1 else kwargs.get("output_path"))
    report_arg = args[2] if len(args) > 2 else kwargs.get("report_path")
    report_path = Path(report_arg).resolve() if report_arg is not None else None
    try:
        return _spatial_order_impl(*args, **kwargs)
    except Exception as error:
        if report_path is not None and not report_path.exists():
            input_record: dict[str, Any] = {"path": str(input_path.resolve())}
            if input_path.is_file():
                input_record.update({"sha256": sha256(input_path), "size_bytes": input_path.stat().st_size})
            failure = {
                "status": "failed",
                "input": input_record,
                "output_requested": str(output_path.resolve()),
                "transformation": "spatial_order",
                "error_type": type(error).__name__,
                "error": str(error),
                "source_written_by_transform": False,
            }
            _json_write(report_path, failure)
            report_path.chmod(0o444)
        raise


def _complete_stage_impl(checkpoint_path: Path) -> dict[str, Any]:
    pa.set_cpu_count(2)
    pa.set_io_thread_count(2)
    checkpoint_path = checkpoint_path.expanduser().resolve()
    if not checkpoint_path.is_file():
        raise SpatialOrderError(f"stage checkpoint is missing: {checkpoint_path}")
    checkpoint = _read_checkpoint(checkpoint_path)
    checkpoint_file_hash = sha256(checkpoint_path)
    if checkpoint.get("checkpoint_path") != str(checkpoint_path):
        raise SpatialOrderError("stage checkpoint path identity differs")
    helper_hash = _helper_sha256()
    if checkpoint.get("helper_sha256") != helper_hash:
        raise SpatialOrderError("spatial_order.py helper checksum differs from the staged code pin")
    if checkpoint.get("stage_process_id") == os.getpid():
        raise SpatialOrderError("stage completion must run in a fresh sequential process")

    try:
        input_record = checkpoint["input"]
        stage_record = checkpoint["stage"]
        input_path = Path(input_record["path"]).resolve()
        stage_path = Path(stage_record["path"]).resolve()
        output_path = Path(checkpoint["output_path"]).resolve()
        report_path = Path(checkpoint["report_path"]).resolve()
        identifier_column = str(checkpoint["identifier_column"])
        geometry_column = str(checkpoint["geometry_column"])
        params = checkpoint["parameters"]
        rows = int(checkpoint["rows"])
        valid_bbox_rows = int(checkpoint["valid_bbox_rows"])
        expected_bbox = [float(value) for value in checkpoint["global_bbox"]]
        expected_types = Counter({str(key): int(value) for key, value in checkpoint["geometry_types"].items()})
        bbox_was_present = bool(checkpoint["bbox_was_present"])
        sort_peak = int(checkpoint["sort_peak_rss_bytes"])
        disk_preflight = checkpoint["disk_preflight"]
        bucket_counts_expected = np.asarray(checkpoint["bucket_counts_expected"], dtype=np.int64)
        input_schema_expected = _schema_from_b64(checkpoint["input_schema_b64"], "input schema")
        output_schema_expected = _schema_from_b64(checkpoint["output_schema_b64"], "output schema")
    except SpatialOrderError:
        raise
    except Exception as error:
        raise SpatialOrderError(f"stage checkpoint is incomplete or invalid: {type(error).__name__}: {error}") from error

    work_dir = output_path.with_name(output_path.name + f".work-{checkpoint['stage_process_id']}")
    paths = [checkpoint_path, input_path, stage_path, output_path, report_path]
    if len(set(paths)) != len(paths):
        raise SpatialOrderError("checkpoint input, stage, output, report, and checkpoint paths must be distinct")
    if output_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable output: {output_path}")
    if report_path.exists():
        raise SpatialOrderError(f"refuse overwrite existing immutable report: {report_path}")
    if work_dir.exists():
        raise SpatialOrderError(f"unexpected retained work directory beside staged output: {work_dir}")
    if not input_path.is_file():
        raise SpatialOrderError(f"staged input is missing: {input_path}")
    if not stage_path.is_file():
        raise SpatialOrderError(f"staged Parquet is missing: {stage_path}")
    if input_path.stat().st_size != int(input_record["size_bytes"]) or sha256(input_path) != input_record["sha256"]:
        raise SpatialOrderError("input identity changed after the spatial-order checkpoint")
    if stage_path.stat().st_size != int(stage_record["size_bytes"]) or sha256(stage_path) != stage_record["sha256"]:
        raise SpatialOrderError("staged Parquet identity changed after the checkpoint")
    if rows <= 0 or valid_bbox_rows < 0 or valid_bbox_rows > rows:
        raise SpatialOrderError("checkpoint feature or bbox counts are invalid")
    max_rss_bytes = int(params["max_rss_bytes"])
    minimum_start_free_bytes = int(params["minimum_start_free_bytes"])
    if max_rss_bytes <= 0 or max_rss_bytes > DEFAULT_MAX_RSS_BYTES:
        raise SpatialOrderError("checkpoint memory limit exceeds the release memory cap")
    if (minimum_start_free_bytes < DEFAULT_START_FREE_BYTES or
            int(params["minimum_remaining_free_bytes"]) < DEFAULT_REMAINING_FREE_BYTES or
            int(params["task_disk_limit_bytes"]) > DEFAULT_TASK_DISK_LIMIT_BYTES):
        raise SpatialOrderError("checkpoint resource guards relax the release disk limits")
    if sort_peak >= max_rss_bytes:
        raise SpatialOrderError("staged sort peak is at or above the recorded memory cap")
    if len(expected_bbox) != 4 or not all(math.isfinite(value) for value in expected_bbox):
        raise SpatialOrderError("checkpoint global bbox is invalid")
    if not expected_types or sum(expected_types.values()) > rows or any(value <= 0 for value in expected_types.values()):
        raise SpatialOrderError("checkpoint geometry type counts are invalid")
    bucket_count = int(params["bucket_count"])
    if (bucket_count < 2 or bucket_count > rows or len(bucket_counts_expected) != bucket_count or
            int(bucket_counts_expected.sum()) != rows or np.any(bucket_counts_expected <= 0)):
        raise SpatialOrderError("checkpoint spatial bucket counts are invalid")
    if not np.array_equal(bucket_counts_expected,
                          np.bincount(np.arange(rows, dtype=np.int64) * bucket_count // rows, minlength=bucket_count)):
        raise SpatialOrderError("checkpoint bucket counts differ from deterministic rank partition")

    if input_schema_expected.names.count(identifier_column) != 1 or input_schema_expected.names.count(geometry_column) != 1:
        raise SpatialOrderError("checkpoint schema omits its identifier or geometry field")
    source = pq.ParquetFile(input_path)
    try:
        if int(source.metadata.num_rows) != rows:
            raise SpatialOrderError("input Parquet row count differs from the checkpoint")
        input_schema = source_schema(source)
        if not input_schema.equals(input_schema_expected, check_metadata=True):
            raise SpatialOrderError("input schema differs from the staged schema identity")
        derived_schema = _geo_info(
            input_schema, geometry_column, checkpoint.get("crs"), sorted(expected_types), expected_bbox,
        )
        if not derived_schema.equals(output_schema_expected, check_metadata=True):
            raise SpatialOrderError("checkpoint output schema differs from source-derived schema")
    finally:
        source.close()
    del source
    gc.collect()
    pa.default_memory_pool().release_unused()

    minimum_remaining_free_bytes = int(params["minimum_remaining_free_bytes"])
    baseline = int(params["task_owned_baseline_bytes"])
    disk_limit = int(params["task_disk_limit_bytes"])
    enforce_guards = bool(params["enforce_guards"])
    if max_rss_bytes <= 0 or disk_limit <= 0 or baseline < 0:
        raise SpatialOrderError("checkpoint memory/disk guard settings are invalid")
    free_before = shutil.disk_usage(output_path.parent).free
    disk_guard = DiskGuard(stage_path.parent / f"{output_path.name}.work-{checkpoint['stage_process_id']}",
                           stage_path, output_path, int(input_record["size_bytes"]),
                           baseline, disk_limit, minimum_remaining_free_bytes, enabled=enforce_guards)
    disk_guard.check()

    # Open no footer readers outside _restore_and_validate: that validator
    # deliberately owns its readers and releases them before its WKB pass.
    validation = _restore_and_validate(
        input_path, stage_path, identifier_column, geometry_column,
        input_schema_expected, output_schema_expected, bbox_was_present,
        rows, valid_bbox_rows, expected_bbox, expected_types,
        bucket_count, int(params["batch_rows"]), int(params["buffer_rows"]),
        max_rss_bytes, work_dir, disk_guard,
    )
    if _helper_sha256() != helper_hash:
        raise SpatialOrderError("spatial_order.py changed during stage validation")
    if sha256(input_path) != input_record["sha256"]:
        raise SpatialOrderError("input Parquet changed during stage validation")
    if sha256(stage_path) != stage_record["sha256"]:
        raise SpatialOrderError("staged Parquet changed during validation")
    if sha256(checkpoint_path) != checkpoint_file_hash:
        raise SpatialOrderError("stage checkpoint changed during validation")
    disk_guard.check()
    validation_peak = peak_rss_bytes()
    disk_preflight = dict(disk_preflight)
    disk_preflight["completion_free_bytes_before"] = free_before
    report_checkpoint = dict(checkpoint)
    report_checkpoint["_checkpoint_file_sha256"] = checkpoint_file_hash
    report = _passed_report(
        input_path, output_path, stage_path, input_record["sha256"], int(input_record["size_bytes"]),
        identifier_column, geometry_column, input_schema_expected, bbox_was_present,
        rows, bucket_count, bucket_counts_expected, int(params["row_group_size"]),
        validation, disk_preflight, sort_peak, validation_peak, max_rss_bytes,
        "sequential_processes", report_checkpoint,
    )
    report_build_peak = peak_rss_bytes()
    validation_peak = max(validation_peak, report_build_peak)
    if max(sort_peak, validation_peak) >= max_rss_bytes:
        raise SpatialOrderError("completion peak RSS reached the recorded memory cap before promotion")
    report["phase_peak_rss_bytes"]["full_validation"] = validation_peak
    report["peak_rss_bytes"] = max(sort_peak, validation_peak)
    if (sha256(input_path) != input_record["sha256"] or
            sha256(stage_path) != stage_record["sha256"] or
            _helper_sha256() != helper_hash or
            sha256(checkpoint_path) != checkpoint_file_hash):
        raise SpatialOrderError("input, staged output, checkpoint, or helper changed before promotion")
    disk_guard.check()
    _promote_stage_and_report(stage_path, output_path, report_path, report)
    return report


def complete_stage(checkpoint_path: Path) -> dict[str, Any]:
    """Validate a deferred stage in a fresh process and promote only on pass."""
    checkpoint_path = Path(checkpoint_path).expanduser().resolve()
    trusted: dict[str, Any] | None = None
    try:
        trusted = _read_checkpoint(checkpoint_path)
        return _complete_stage_impl(checkpoint_path)
    except Exception as error:
        if trusted is not None:
            report_path = Path(str(trusted.get("report_path", ""))).expanduser()
            if report_path.is_absolute() and not report_path.exists():
                artifacts = [checkpoint_path]
                for key in ("input", "stage"):
                    record = trusted.get(key)
                    if isinstance(record, dict) and isinstance(record.get("path"), str):
                        artifacts.append(Path(record["path"]))
                for key in ("output_path", "report_path"):
                    value = trusted.get(key)
                    if isinstance(value, str):
                        artifacts.append(Path(value))
                try:
                    failure = {
                        "status": "failed",
                        "input": trusted.get("input"),
                        "staged_parquet": trusted.get("stage"),
                        "output_requested": trusted.get("output_path"),
                        "checkpoint": {"path": str(checkpoint_path),
                                       "sha256": sha256(checkpoint_path),
                                       "payload_sha256": trusted.get("checkpoint_payload_sha256")},
                        "transformation": "spatial_order_stage_completion",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "source_written_by_transform": False,
                        "retained_partial_artifacts": _artifact_inventory(artifacts),
                    }
                    _json_write(report_path, failure)
                    report_path.chmod(0o444)
                except FileExistsError:
                    pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complete-stage", type=Path,
                        help="validate and promote an immutable deferred checkpoint in this fresh process")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--identifier-column")
    parser.add_argument("--geometry-column")
    parser.add_argument("--defer-validation", action="store_true",
                        help="write a pending immutable checkpoint without final validation or promotion")
    parser.add_argument("--checkpoint", type=Path,
                        help="new checkpoint path; required with --defer-validation")
    parser.add_argument("--crs", help="Identify the source CRS when the GeoParquet metadata does not declare one")
    parser.add_argument("--buckets", type=int, default=DEFAULT_BUCKETS)
    parser.add_argument("--batch-rows", type=int, default=DEFAULT_BATCH_ROWS)
    parser.add_argument("--buffer-rows", type=int, default=DEFAULT_BUFFER_ROWS)
    parser.add_argument("--row-group-size", type=int, default=DEFAULT_ROW_GROUP_SIZE)
    parser.add_argument("--max-memory-gib", type=float, default=DEFAULT_MAX_RSS_BYTES / 1024**3)
    parser.add_argument("--task-owned-baseline-gb", type=float, default=0.0,
                        help="Task-owned bytes already retained, excluding this input and the source archive/docs")
    parser.add_argument("--task-disk-limit-gb", type=float, default=8.0)
    parser.add_argument("--minimum-start-free-gb", type=float, default=40.0)
    parser.add_argument("--minimum-remaining-free-gb", type=float, default=10.0)
    args = parser.parse_args()
    try:
        if args.complete_stage is not None:
            if len(sys.argv) != 3 or sys.argv[1] != "--complete-stage":
                parser.error("--complete-stage cannot be combined with build or defer-validation options")
            report = complete_stage(args.complete_stage)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0
        missing = [name for name, value in (
            ("--input", args.input), ("--output", args.output), ("--report", args.report),
            ("--identifier-column", args.identifier_column), ("--geometry-column", args.geometry_column),
        ) if value is None]
        if missing:
            parser.error("spatial ordering requires " + ", ".join(missing))
        if args.defer_validation and args.checkpoint is None:
            parser.error("--defer-validation requires --checkpoint")
        if not args.defer_validation and args.checkpoint is not None:
            parser.error("--checkpoint is valid only with --defer-validation")
        report = spatial_order(
            args.input, args.output, args.report, args.identifier_column, args.geometry_column,
            crs=args.crs, bucket_count=args.buckets, batch_rows=args.batch_rows,
            buffer_rows=args.buffer_rows, row_group_size=args.row_group_size,
            max_rss_bytes=int(args.max_memory_gib * 1024**3),
            minimum_start_free_bytes=int(args.minimum_start_free_gb * 1_000_000_000),
            minimum_remaining_free_bytes=int(args.minimum_remaining_free_gb * 1_000_000_000),
            task_owned_baseline_bytes=int(args.task_owned_baseline_gb * 1_000_000_000),
            task_disk_limit_bytes=int(args.task_disk_limit_gb * 1_000_000_000),
            defer_validation=args.defer_validation,
            checkpoint_path=args.checkpoint,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"spatial ordering failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
