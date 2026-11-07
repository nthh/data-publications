#!/usr/bin/env python3
"""Convert the complete HydroLAKES v1 polygon layer to ID-sorted GeoParquet.

The source is read through GDAL/pyogrio as Arrow WKB. Geometry bytes and the
logical Arrow values of every source attribute are carried through unchanged.
An internal per-feature digest travels with the staging rows and is checked
again after DuckDB has sorted the source by Hylak_id. The digest helper is not
included in the published GeoParquet.

This is a local preparation tool. It does not fetch source data or upload the
result. Keep the original ZIP and the explicit staging directory as private,
retained preparation artifacts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import shapely


EXPECTED_COUNT = 1_427_688
EXPECTED_MIN_ID = 1
EXPECTED_MAX_ID = 1_427_688
IDENTITY_COLUMN = "_hydrolakes_source_feature_sha256"
ID_COLUMN = "Hylak_id"
DEFAULT_STAGE_TARGET_BYTES = 1_500_000
MAX_PROJECTED_ROW_GROUP_BYTES = 4 * 1024 * 1024


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _scalar_bytes(value: Any) -> bytes:
    """Encode a decoded Arrow scalar deterministically, retaining nulls/types."""
    if value is None:
        return b"n"
    if isinstance(value, bool):
        return b"b1" if value else b"b0"
    if isinstance(value, int):
        return b"i" + str(value).encode("ascii")
    if isinstance(value, float):
        return b"f" + struct.pack(">d", value)
    if isinstance(value, bytes):
        return b"y" + value
    if isinstance(value, str):
        return b"s" + value.encode("utf-8")
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return b"t" + value.isoformat().encode("ascii")
    if hasattr(value, "as_py"):
        return _scalar_bytes(value.as_py())
    return b"j" + _json_bytes(value)


def feature_digest(schema: pa.Schema, values: list[Any], geometry_index: int) -> bytes:
    """Hash one complete logical feature, including the original WKB bytes."""
    h = hashlib.sha256()
    for field, value in zip(schema, values, strict=True):
        if field.name == IDENTITY_COLUMN:
            raise ValueError(f"source schema reserves internal field {IDENTITY_COLUMN!r}")
        name = field.name.encode("utf-8")
        type_name = str(field.type).encode("ascii")
        payload = _scalar_bytes(value)
        for part in (name, type_name, payload):
            h.update(struct.pack(">Q", len(part)))
            h.update(part)
    geometry = values[geometry_index]
    if geometry is not None:
        # Geometry is also covered by its field above; this explicit marker
        # makes it evident in the digest contract that original WKB is bound.
        h.update(b"original-wkb\0")
        h.update(struct.pack(">Q", len(geometry)))
        h.update(geometry)
    return h.digest()


def resolve_layer(source: Path) -> str:
    """Resolve a ZIP or direct vector path to the single polygon shapefile."""
    source = source.expanduser().resolve()
    if source.is_dir():
        candidates = sorted(source.rglob("*.shp"))
        if len(candidates) != 1:
            raise ValueError(f"expected one shapefile under {source}, found {len(candidates)}")
        return str(candidates[0])
    if source.suffix.lower() != ".zip":
        if not source.is_file():
            raise FileNotFoundError(source)
        return str(source)
    with zipfile.ZipFile(source) as archive:
        candidates = [n for n in archive.namelist() if n.lower().endswith(".shp") and not n.startswith("__MACOSX/")]
    if len(candidates) != 1:
        raise ValueError(f"expected one shapefile in {source.name}, found {len(candidates)}")
    member = candidates[0]
    return f"/vsizip/{source}/{member}"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _geo_metadata(geometry_name: str, crs: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "version": "1.1.0",
        "primary_column": geometry_name,
        "columns": {geometry_name: {"encoding": "WKB"}},
    }
    if crs:
        # GeoParquet 1.1 uses PROJJSON for explicit CRS definitions.
        try:
            from pyproj import CRS

            metadata["columns"][geometry_name]["crs"] = CRS.from_user_input(crs).to_json_dict()
        except (ImportError, ValueError) as exc:
            raise ValueError(
                f"could not encode source CRS {crs!r} as complete GeoParquet PROJJSON"
            ) from exc
    return metadata


def _row_cost(batch: pa.RecordBatch, row: int, geometry_index: int) -> int:
    """Conservative payload estimate for adaptive staged row-group sizing."""
    size = 128
    for index, field in enumerate(batch.schema):
        scalar = batch.column(index)[row].as_py()
        if scalar is None:
            continue
        if index == geometry_index:
            size += len(scalar)
        elif isinstance(scalar, str):
            size += len(scalar.encode("utf-8"))
        elif isinstance(scalar, bytes):
            size += len(scalar)
        else:
            size += min(32, max(1, len(str(scalar))))
    return size


def _write_adaptive(writer: pq.ParquetWriter, table: pa.Table, target_bytes: int, geometry_name: str) -> None:
    if not table.num_rows:
        return
    geometry_index = table.schema.get_field_index(geometry_name)
    batch = table.to_batches(max_chunksize=table.num_rows)[0]
    start = 0
    used = 0
    for row in range(table.num_rows):
        cost = _row_cost(batch, row, geometry_index)
        if row > start and used + cost > target_bytes:
            writer.write_table(table.slice(start, row - start), row_group_size=row - start)
            start = row
            used = 0
        used += cost
    writer.write_table(table.slice(start), row_group_size=table.num_rows - start)


def _field_values(batch: pa.RecordBatch, row: int) -> list[Any]:
    return [batch.column(i)[row].as_py() for i in range(batch.num_columns)]


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def convert(
    source: str | Path,
    output: str | Path,
    staging_dir: str | Path,
    *,
    expected_count: int = EXPECTED_COUNT,
    expected_min_id: int = EXPECTED_MIN_ID,
    expected_max_id: int = EXPECTED_MAX_ID,
    source_url: str | None = None,
    source_sha256: str | None = None,
    batch_size: int = 4096,
    stage_target_bytes: int = DEFAULT_STAGE_TARGET_BYTES,
    output_target_bytes: int = DEFAULT_STAGE_TARGET_BYTES,
    sort_memory_mib: int = 1024,
    sort_threads: int = 2,
) -> dict[str, Any]:
    """Stream, identity-check, sort, and write a complete GeoParquet release."""
    if expected_count < 1 or expected_max_id - expected_min_id + 1 != expected_count:
        raise ValueError("expected ID range must be contiguous and match expected_count")
    if batch_size < 1 or stage_target_bytes < 1 or output_target_bytes < 1:
        raise ValueError("batch_size and row-group target byte sizes must be positive")
    if not isinstance(sort_memory_mib, int) or isinstance(sort_memory_mib, bool) or not 128 <= sort_memory_mib <= 4096:
        raise ValueError("sort_memory_mib must be an integer from 128 through 4096")
    if not isinstance(sort_threads, int) or isinstance(sort_threads, bool) or not 1 <= sort_threads <= 2:
        raise ValueError("sort_threads must be an integer from 1 through 2")

    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    stage_root = Path(staging_dir).expanduser().resolve()
    stage_root.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staged = stage_root / "hydrolakes-unsorted-with-identity.parquet"
    partial_output = output_path.with_name(output_path.name + ".partial")
    if output_path.exists() or partial_output.exists() or staged.exists():
        raise FileExistsError("refusing to overwrite output or retained staging parquet")

    source_layer = resolve_layer(source_path)
    actual_source_sha256 = _hash_file(source_path) if source_path.is_file() else None
    if source_sha256 and actual_source_sha256 and source_sha256.lower() != actual_source_sha256:
        raise ValueError(
            f"official source SHA-256 mismatch: expected {source_sha256.lower()}, got {actual_source_sha256}"
        )
    if source_sha256 and not actual_source_sha256:
        raise ValueError("source_sha256 can only pin a single source file, such as the official ZIP")
    count = 0
    observed_min: int | None = None
    observed_max: int | None = None
    overall_bounds: list[float] | None = None
    identity_checksum = 0
    geometry_name = ""
    id_index = -1
    geometry_index = -1
    source_schema: pa.Schema | None = None
    output_schema: pa.Schema | None = None
    geo_metadata: dict[str, Any] | None = None
    geometry_type_ids: set[int] = set()

    with pyogrio.open_arrow(source_layer, use_pyarrow=True, batch_size=batch_size) as opened:
        source_meta, reader = opened
        geometry_name = source_meta.get("geometry_name") or "wkb_geometry"
        source_schema = reader.schema
        id_index = source_schema.get_field_index(ID_COLUMN)
        geometry_index = source_schema.get_field_index(geometry_name)
        if id_index < 0 or geometry_index < 0:
            raise ValueError(f"source must contain {ID_COLUMN!r} and geometry column {geometry_name!r}")
        if source_schema.field(id_index).type not in (pa.int16(), pa.int32(), pa.int64(), pa.uint16(), pa.uint32(), pa.uint64()):
            raise TypeError(f"{ID_COLUMN} must have an integer Arrow type; got {source_schema.field(id_index).type}")
        if IDENTITY_COLUMN in source_schema.names:
            raise ValueError(f"source contains reserved helper column {IDENTITY_COLUMN!r}")

        geo_metadata = _geo_metadata(geometry_name, source_meta.get("crs"))
        fields = []
        for field in source_schema:
            if field.name == geometry_name:
                fields.append(pa.field(field.name, pa.binary(), nullable=field.nullable))
            else:
                fields.append(field)
        output_schema = pa.schema(fields, metadata={b"geo": _json_bytes(geo_metadata)})
        stage_fields = [
            pa.field(field.name, pa.binary(), nullable=field.nullable)
            if field.name == geometry_name
            else field
            for field in source_schema
        ]
        stage_schema = pa.schema(stage_fields + [pa.field(IDENTITY_COLUMN, pa.binary(32), nullable=False)])

        with pq.ParquetWriter(
            staged,
            stage_schema,
            compression="zstd",
            compression_level=3,
            use_dictionary=True,
            write_statistics=True,
            version="2.6",
        ) as stage_writer:
            for batch in reader:
                ids = batch.column(id_index).to_pylist()
                geometries = batch.column(geometry_index).to_pylist()
                digests: list[bytes] = []
                for row, raw_id in enumerate(ids):
                    if raw_id is None:
                        raise ValueError("source contains a null Hylak_id")
                    lake_id = int(raw_id)
                    count += 1
                    observed_min = lake_id if observed_min is None else min(observed_min, lake_id)
                    observed_max = lake_id if observed_max is None else max(observed_max, lake_id)
                    digest = feature_digest(source_schema, _field_values(batch, row), geometry_index)
                    digests.append(digest)
                    identity_checksum = (identity_checksum + int.from_bytes(digest, "big")) % (1 << 256)
                if geometries:
                    geom_array = shapely.from_wkb(geometries, on_invalid="raise")
                    geometry_type_ids.update(
                        int(value) for value in shapely.get_type_id(geom_array) if int(value) >= 0
                    )
                    bounds = shapely.bounds(geom_array)
                    valid_bounds = bounds[~shapely.is_missing(geom_array)]
                    if len(valid_bounds):
                        batch_bounds = [
                            float(valid_bounds[:, 0].min()),
                            float(valid_bounds[:, 1].min()),
                            float(valid_bounds[:, 2].max()),
                            float(valid_bounds[:, 3].max()),
                        ]
                        if overall_bounds is None:
                            overall_bounds = batch_bounds
                        else:
                            overall_bounds = [
                                min(overall_bounds[0], batch_bounds[0]),
                                min(overall_bounds[1], batch_bounds[1]),
                                max(overall_bounds[2], batch_bounds[2]),
                                max(overall_bounds[3], batch_bounds[3]),
                            ]
                stage_arrays = [
                    batch.column(index).cast(pa.binary()) if field.name == geometry_name else batch.column(index)
                    for index, field in enumerate(source_schema)
                ]
                table = pa.Table.from_arrays(
                    stage_arrays + [pa.array(digests, type=pa.binary(32))], schema=stage_schema
                )
                _write_adaptive(stage_writer, table, stage_target_bytes, geometry_name)

        geometry_type_names = {
            0: "Point",
            1: "LineString",
            2: "LinearRing",
            3: "Polygon",
            4: "MultiPoint",
            5: "MultiLineString",
            6: "MultiPolygon",
            7: "GeometryCollection",
        }
        geo_metadata["columns"][geometry_name]["geometry_types"] = sorted(
            geometry_type_names[type_id] for type_id in geometry_type_ids
        )
        output_schema = pa.schema(fields, metadata={b"geo": _json_bytes(geo_metadata)})

    if source_schema is None or output_schema is None or geo_metadata is None:
        raise RuntimeError("source reader did not initialize")
    if count != expected_count:
        raise ValueError(f"source feature count mismatch: expected {expected_count}, got {count}")
    if observed_min != expected_min_id or observed_max != expected_max_id:
        raise ValueError(
            f"source ID range mismatch: expected {expected_min_id}..{expected_max_id}, "
            f"got {observed_min}..{observed_max}"
        )

    # Sort externally with bounded DuckDB memory and spill only under the
    # explicit private staging directory. Output batches are streamed onward.
    db_file = stage_root / "hydrolakes-sort.duckdb"
    connection = duckdb.connect(str(db_file))
    try:
        connection.execute(f"SET memory_limit='{sort_memory_mib}MiB'")
        connection.execute(f"SET threads={sort_threads}")
        temp_dir = str(stage_root / "duckdb-tmp").replace("'", "''")
        connection.execute(f"SET temp_directory='{temp_dir}'")
        connection.execute(f"SET preserve_insertion_order=false")
        staged_sql_path = str(staged).replace("'", "''")
        relation = f"read_parquet('{staged_sql_path}')"
        columns = ", ".join(_quote_ident(name) for name in source_schema.names + [IDENTITY_COLUMN])
        id_sql = _quote_ident(ID_COLUMN)
        # Consecutive IDs detect both duplicate and missing IDs without a
        # full in-memory set, while ORDER BY is also the final row order.
        dupes, distinct_count = connection.execute(
            f"SELECT count(*) - count(DISTINCT {id_sql}), count(DISTINCT {id_sql}) FROM {relation}"
        ).fetchone()
        if dupes != 0 or distinct_count != expected_count:
            raise ValueError(f"source IDs are not unique: rows={count}, distinct={distinct_count}")

        sql = f"SELECT {columns} FROM {relation} ORDER BY {id_sql}"
        cursor = connection.execute(sql)
        reader = cursor.to_arrow_reader(batch_size=batch_size)
        output_fields = []
        for field in source_schema:
            if field.name == geometry_name:
                output_fields.append(pa.field(field.name, pa.binary(), nullable=field.nullable))
            else:
                output_fields.append(field)
        final_schema = pa.schema(output_fields, metadata={b"geo": _json_bytes(geo_metadata)})
        final_count = 0
        final_min: int | None = None
        final_max: int | None = None
        staged_checksum = 0
        row_group_expected_id = expected_min_id
        with pq.ParquetWriter(
            partial_output,
            final_schema,
            compression="zstd",
            compression_level=3,
            use_dictionary=True,
            write_statistics=True,
            version="2.6",
        ) as writer:
            for batch in reader:
                id_batch = batch.column(batch.schema.get_field_index(ID_COLUMN)).to_pylist()
                digest_batch = batch.column(batch.schema.get_field_index(IDENTITY_COLUMN)).to_pylist()
                for row, (raw_id, expected_digest) in enumerate(zip(id_batch, digest_batch, strict=True)):
                    lake_id = int(raw_id)
                    if lake_id != row_group_expected_id:
                        raise ValueError(
                            f"IDs must be unique and contiguous; expected {row_group_expected_id}, got {lake_id}"
                        )
                    row_group_expected_id += 1
                    # Recompute over precisely the source schema fields. The
                    # private digest column has already been sorted alongside
                    # them by DuckDB.
                    source_values = [
                        batch.column(batch.schema.get_field_index(field.name))[row].as_py()
                        for field in source_schema
                    ]
                    actual_digest = feature_digest(source_schema, source_values, geometry_index)
                    if actual_digest != expected_digest:
                        raise ValueError(f"feature identity changed during conversion for Hylak_id={lake_id}")
                    staged_checksum = (staged_checksum + int.from_bytes(actual_digest, "big")) % (1 << 256)
                    final_count += 1
                    final_min = lake_id if final_min is None else min(final_min, lake_id)
                    final_max = lake_id if final_max is None else max(final_max, lake_id)
                source_columns = [batch.column(batch.schema.get_field_index(name)) for name in source_schema.names]
                output_batch = pa.RecordBatch.from_arrays(source_columns, schema=final_schema)
                table = pa.Table.from_batches([output_batch])
                _write_adaptive(writer, table, output_target_bytes, geometry_name)
        if final_count != expected_count or row_group_expected_id != expected_max_id + 1:
            raise ValueError(f"final row count or ID coverage mismatch: count={final_count}")
        if staged_checksum != identity_checksum:
            raise ValueError("global source/staging identity digest mismatch")

        # Reopen the completed serialized Parquet and compare every decoded
        # feature against its per-ID source digest. This catches any change
        # introduced by the final GeoParquet writer, not just the sorter.
        expected_rows = connection.execute(
            f"SELECT {id_sql}, {_quote_ident(IDENTITY_COLUMN)} FROM {relation} ORDER BY {id_sql}"
        ).to_arrow_reader(batch_size=batch_size)
        final_file = pq.ParquetFile(partial_output)

        def streamed_rows(batches):
            for record_batch in batches:
                id_col = record_batch.schema.get_field_index(ID_COLUMN)
                digest_col = record_batch.schema.get_field_index(IDENTITY_COLUMN)
                for row in range(record_batch.num_rows):
                    yield (
                        int(record_batch.column(id_col)[row].as_py()),
                        record_batch.column(digest_col)[row].as_py(),
                    )

        expected_identity_rows = iter(streamed_rows(expected_rows))
        final_count_verified = 0
        final_checksum = 0
        expected_id = expected_min_id
        serialized_schema = final_file.schema_arrow
        if serialized_schema.names != source_schema.names:
            raise ValueError("serialized output changed the source attribute/geometry column set or order")
        for field in source_schema:
            serialized_field = serialized_schema.field(field.name)
            expected_type = pa.binary() if field.name == geometry_name else field.type
            if serialized_field.type != expected_type:
                raise ValueError(
                    f"serialized schema type changed for {field.name}: "
                    f"expected {expected_type}, got {serialized_field.type}"
                )
        for final_batch in final_file.iter_batches(batch_size=batch_size):
            for row in range(final_batch.num_rows):
                actual_id = int(final_batch.column(final_batch.schema.get_field_index(ID_COLUMN))[row].as_py())
                try:
                    expected_row_id, expected_digest = next(expected_identity_rows)
                except StopIteration as exc:
                    raise ValueError("serialized output has more rows than the staged source") from exc
                if actual_id != expected_row_id or actual_id != expected_id:
                    raise ValueError(
                        f"serialized output ID mismatch: expected {expected_id}, got {actual_id}"
                    )
                source_values = [
                    final_batch.column(final_batch.schema.get_field_index(field.name))[row].as_py()
                    for field in source_schema
                ]
                serialized_digest = feature_digest(source_schema, source_values, geometry_index)
                if serialized_digest != expected_digest:
                    raise ValueError(f"serialized feature identity mismatch for Hylak_id={actual_id}")
                final_checksum = (final_checksum + int.from_bytes(serialized_digest, "big")) % (1 << 256)
                final_count_verified += 1
                expected_id += 1
        try:
            next(expected_identity_rows)
        except StopIteration:
            pass
        else:
            raise ValueError("serialized output has fewer rows than the staged source")
        if final_count_verified != expected_count or expected_id != expected_max_id + 1:
            raise ValueError(f"serialized output count/coverage mismatch: count={final_count_verified}")
        if final_checksum != identity_checksum:
            raise ValueError("global source/serialized-output identity digest mismatch")
    finally:
        connection.close()

    parquet = pq.ParquetFile(partial_output)
    id_idx = source_schema.get_field_index(ID_COLUMN)
    row_groups: list[dict[str, Any]] = []
    previous_max: int | None = None
    for index in range(parquet.metadata.num_row_groups):
        group = parquet.metadata.row_group(index)
        id_stats = group.column(id_idx).statistics
        if id_stats is None or id_stats.min is None or id_stats.max is None:
            raise ValueError(f"row group {index} has no Hylak_id min/max statistics")
        group_min, group_max = int(id_stats.min), int(id_stats.max)
        if previous_max is not None and group_min <= previous_max:
            raise ValueError(f"row-group ID bounds overlap or are unsorted at group {index}")
        previous_max = group_max
        row_groups.append(
            {
                "index": index,
                "first_hylak_id": group_min,
                "last_hylak_id": group_max,
                "rows": group.num_rows,
                "compressed_bytes": sum(group.column(col).total_compressed_size for col in range(group.num_columns)),
                "columns": [
                    {
                        "name": parquet.schema.column(col).name,
                        "file_offset": min(
                            offset
                            for offset in (
                                group.column(col).dictionary_page_offset,
                                group.column(col).data_page_offset,
                            )
                            if offset >= 0
                        ),
                        "dictionary_page_offset": group.column(col).dictionary_page_offset,
                        "data_page_offset": group.column(col).data_page_offset,
                        "compressed_bytes": group.column(col).total_compressed_size,
                    }
                    for col in range(group.num_columns)
                ],
            }
        )
    max_group_bytes = max((rg["compressed_bytes"] for rg in row_groups), default=0)
    if max_group_bytes > MAX_PROJECTED_ROW_GROUP_BYTES:
        raise ValueError(
            f"compressed row group exceeded {MAX_PROJECTED_ROW_GROUP_BYTES} bytes: {max_group_bytes}"
        )

    partial_output.replace(output_path)

    manifest = {
        "format": "GeoParquet",
        "geoparquet_version": "1.1.0",
        "source_dataset": "HydroLAKES v1 polygons",
        "source_layer": "HydroLAKES_polys_v10",
        "source_url": source_url,
        "source_sha256": actual_source_sha256,
        "source_file": str(source_path),
        "source_layer_path": source_layer,
        "source_crs": source_meta.get("crs"),
        "geometry_column": geometry_name,
        "geometry_encoding": "WKB; bytes preserved from GDAL Arrow source",
        "attribute_columns": source_schema.names,
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in source_schema
        ],
        "feature_count": final_count,
        "hylak_id": {"minimum": final_min, "maximum": final_max, "unique": True, "contiguous": True},
        "bbox": overall_bounds,
        "source_final_feature_sha256_sum_mod_2_256": f"{final_checksum:064x}",
        "output_sha256": _hash_file(output_path),
        "output_bytes": output_path.stat().st_size,
        "compression": "ZSTD level 3",
        "sort_order": [ID_COLUMN, "ascending"],
        "row_group_count": len(row_groups),
        "maximum_row_group_compressed_bytes": max_group_bytes,
        "row_groups": row_groups,
        "preparation": {
            "reader": f"pyogrio {pyogrio.__version__} open_arrow(use_pyarrow=True)",
            "arrow": pa.__version__,
            "sorter": duckdb.__version__,
            "duckdb_memory_limit_mib": sort_memory_mib,
            "duckdb_threads": sort_threads,
            "staging_parquet": str(staged),
            "sort_database": str(db_file),
            "staging_retained": True,
            "source_hash_verified_against_manifest": source_sha256 is not None,
        },
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="official HydroLAKES ZIP or extracted shapefile")
    parser.add_argument("--output", required=True, type=Path, help="new output GeoParquet path")
    parser.add_argument("--staging-dir", required=True, type=Path, help="private retained staging directory")
    parser.add_argument("--source-url", help="pinned official source URL for lineage metadata")
    parser.add_argument("--source-sha256", help="expected SHA-256 of the official source ZIP")
    parser.add_argument("--expected-count", type=int, default=EXPECTED_COUNT)
    parser.add_argument("--expected-min-id", type=int, default=EXPECTED_MIN_ID)
    parser.add_argument("--expected-max-id", type=int, default=EXPECTED_MAX_ID)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--output-target-bytes", type=int, default=DEFAULT_STAGE_TARGET_BYTES)
    parser.add_argument("--sort-memory-mib", type=int, default=1024, help="DuckDB sort memory, 128..4096 MiB")
    parser.add_argument("--sort-threads", type=int, default=2, help="DuckDB sort threads, 1..2")
    args = parser.parse_args()
    if args.source_sha256 and len(args.source_sha256) != 64:
        parser.error("--source-sha256 must be 64 hexadecimal characters")
    manifest = convert(
        args.source,
        args.output,
        args.staging_dir,
        expected_count=args.expected_count,
        expected_min_id=args.expected_min_id,
        expected_max_id=args.expected_max_id,
        source_url=args.source_url,
        source_sha256=args.source_sha256,
        batch_size=args.batch_size,
        output_target_bytes=args.output_target_bytes,
        sort_memory_mib=args.sort_memory_mib,
        sort_threads=args.sort_threads,
    )
    print(json.dumps({"output": str(args.output), "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
