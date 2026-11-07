#!/usr/bin/env python3
"""Losslessly mirror GRWL PolyLine SHP/DBF tiles into GeoParquet.

DBF numeric values are parsed from their decimal text, and WKB coordinates are
copied from the SHP float64 byte stream. This is a format conversion only; it
does not connect records that happen to share segment identifiers.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS


DBF_FIELDS = (
    "utm_east", "utm_north", "width_m", "nchannels", "segmentID",
    "segmentInd", "lakeFlag", "lon", "lat", "elev_m",
)
INTEGER_FIELDS = {"width_m", "segmentID", "segmentInd", "elev_m"}
DECIMAL_FIELDS = set(DBF_FIELDS) - INTEGER_FIELDS
TILE_RE = re.compile(r"^[A-Z]{2}[0-9]{2}$")
MAX_SAFE_JSON_INTEGER = 2**53
MAX_SOURCE_ROW = 2**32 - 1
WRITE_BATCH_ROWS = 8192


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tile_code(tile: str) -> int:
    if not TILE_RE.fullmatch(tile):
        raise ValueError(f"Invalid GRWL tile code: {tile!r}")
    return ((ord(tile[0]) - 65) * 26 + (ord(tile[1]) - 65)) * 100 + int(tile[2:])


def feature_id(tile: str, source_row: int) -> int:
    if not 1 <= source_row <= MAX_SOURCE_ROW:
        raise ValueError(f"Source row is outside the supported 1-based uint32 range: {source_row}")
    result = (tile_code(tile) << 32) | source_row
    if result >= MAX_SAFE_JSON_INTEGER:
        raise ValueError(f"Feature ID is not exactly representable as a JSON number: {result}")
    return result


def _dbf_layout(path: Path) -> tuple[int, int, int, list[dict[str, Any]]]:
    with path.open("rb") as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise ValueError(f"Truncated DBF header: {path}")
        row_count = struct.unpack_from("<I", header, 4)[0]
        header_len, record_len = struct.unpack_from("<HH", header, 8)
        if header_len < 33 or record_len < 1:
            raise ValueError(f"Invalid DBF header lengths: {path}")
        descriptors = stream.read(header_len - 32)
    if not descriptors or descriptors[-1] != 0x0D:
        raise ValueError(f"DBF field descriptor terminator missing: {path}")
    fields: list[dict[str, Any]] = []
    offset = 1
    for pos in range(0, len(descriptors) - 1, 32):
        desc = descriptors[pos:pos + 32]
        if len(desc) != 32:
            raise ValueError(f"Truncated DBF field descriptor: {path}")
        name = desc[:11].split(b"\0", 1)[0].decode("ascii")
        kind, width, scale = chr(desc[11]), desc[16], desc[17]
        if name not in DBF_FIELDS or kind != "N":
            raise ValueError(f"Unexpected DBF field descriptor {name!r}/{kind!r} in {path.name}")
        fields.append({"name": name, "offset": offset, "width": width, "scale": scale})
        offset += width
    if tuple(field["name"] for field in fields) != DBF_FIELDS:
        raise ValueError(f"Unexpected DBF field order in {path.name}: {[f['name'] for f in fields]}")
    if offset != record_len:
        raise ValueError(f"DBF record length mismatch in {path.name}: {offset} != {record_len}")
    for field in fields:
        if field["scale"] > field["width"]:
            raise ValueError(f"Invalid DBF scale for {field['name']} in {path.name}")
        if field["name"] in INTEGER_FIELDS and field["scale"] != 0:
            raise ValueError(f"Expected integer DBF field {field['name']} in {path.name}")
    return row_count, header_len, record_len, fields


def _parse_numeric(raw: bytes, field: dict[str, Any], tile: str, row: int) -> int | Decimal | None:
    text = raw.strip().decode("ascii")
    if not text or set(text) == {"*"}:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Malformed numeric value in {tile} DBF row {row}, {field['name']}: {text!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Non-finite numeric value in {tile} DBF row {row}, {field['name']}")
    if field["name"] in INTEGER_FIELDS:
        if number != number.to_integral_value():
            raise ValueError(f"Non-integer value in {tile} DBF row {row}, {field['name']}: {text!r}")
        return int(number)
    sign, digits, exponent = number.as_tuple()
    # Extra trailing zeroes in a DBF decimal are exactly representable at a
    # lower Arrow scale. Remove only those zero digits; never round a value.
    if number.is_zero():
        number = Decimal((sign, (0,), 0))
        digits, exponent = number.as_tuple()[1:]
    while len(digits) > 1 and digits[-1] == 0 and -exponent > 18:
        digits = digits[:-1]
        exponent += 1
    if (sign, digits, exponent) != number.as_tuple():
        number = Decimal((sign, digits, exponent))
    scale = max(0, -exponent)
    integer_digits = max(0, len(digits) + exponent)
    if scale > 18 or integer_digits > 20 or integer_digits + scale > 38:
        raise ValueError(f"DBF value cannot fit decimal128(38,18) exactly in {tile} row {row}, {field['name']}: {text!r}")
    # The common schema leaves headroom for wider global DBF fields. PyArrow
    # can scale these values exactly; any value that cannot fit is rejected.
    return number


def _geometry_from_record(content: bytes, tile: str, row: int) -> tuple[bytes, tuple[float, float, float, float], int, int]:
    if len(content) < 44:
        raise ValueError(f"Truncated SHP record in {tile} row {row}")
    shape_type = struct.unpack_from("<i", content, 0)[0]
    if shape_type != 3:
        raise ValueError(f"Expected PolyLine shape type 3 in {tile} row {row}; found {shape_type}")
    part_count, point_count = struct.unpack_from("<ii", content, 36)
    if part_count <= 0 or point_count <= 0:
        raise ValueError(f"Empty PolyLine record in {tile} row {row}")
    part_table_end = 44 + part_count * 4
    coordinate_start = part_table_end
    expected_len = coordinate_start + point_count * 16
    if expected_len != len(content):
        raise ValueError(f"Invalid PolyLine content length in {tile} row {row}")
    starts = struct.unpack_from("<" + "i" * part_count, content, 44)
    if starts[0] != 0 or any(a >= b for a, b in zip(starts, starts[1:])) or starts[-1] >= point_count:
        raise ValueError(f"Invalid part boundaries in {tile} row {row}")
    coords = memoryview(content)[coordinate_start:]
    # MultiLineString WKB, encoded directly from each original finite XY byte slice.
    wkb = bytearray(struct.pack("<BI", 1, 5) + struct.pack("<I", part_count))
    bounds: list[tuple[float, float]] = []
    for part_index, first in enumerate(starts):
        end = starts[part_index + 1] if part_index + 1 < part_count else point_count
        count = end - first
        if count < 2:
            raise ValueError(f"PolyLine part has fewer than two vertices in {tile} row {row}, part {part_index + 1}")
        wkb.extend(struct.pack("<BI", 1, 2))
        wkb.extend(struct.pack("<I", count))
        start_byte, stop_byte = first * 16, end * 16
        part_bytes = coords[start_byte:stop_byte]
        wkb.extend(part_bytes)
        for idx in range(first, end):
            x, y = struct.unpack_from("<dd", coords, idx * 16)
            if not (float("-inf") < x < float("inf") and float("-inf") < y < float("inf")):
                raise ValueError(f"Non-finite XY coordinate in {tile} row {row}")
            bounds.append((x, y))
    xs, ys = zip(*bounds)
    return bytes(wkb), (min(xs), min(ys), max(xs), max(ys)), part_count, point_count


def _tile_rows(tile: str, directory: Path) -> Iterator[tuple[dict[str, Any], bytes, bytes, int, int]]:
    shp_path, shx_path, dbf_path = (directory / f"{tile}.{ext}" for ext in ("shp", "shx", "dbf"))
    prj_path = directory / f"{tile}.prj"
    for path in (shp_path, shx_path, dbf_path, prj_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    try:
        source_crs = CRS.from_wkt(prj_path.read_text())
    except Exception as exc:
        raise ValueError(f"Cannot parse source CRS from {prj_path}") from exc
    if not source_crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
        raise ValueError(f"Expected source CRS EPSG:4326 for {tile}; found {source_crs.to_string()}")
    dbf_count, dbf_header_len, dbf_record_len, fields = _dbf_layout(dbf_path)
    if dbf_count > MAX_SOURCE_ROW:
        raise ValueError(f"{tile} exceeds uint32 source-row capacity")
    with shp_path.open("rb") as shp, shx_path.open("rb") as shx, dbf_path.open("rb") as dbf:
        shp_header, shx_header = shp.read(100), shx.read(100)
        if len(shp_header) != 100 or len(shx_header) != 100:
            raise ValueError(f"Truncated SHP/SHX header for {tile}")
        if struct.unpack_from(">i", shp_header)[0] != 9994 or struct.unpack_from(">i", shx_header)[0] != 9994:
            raise ValueError(f"Invalid SHP/SHX file code for {tile}")
        if struct.unpack_from("<i", shp_header, 28)[0] != 1000 or struct.unpack_from("<i", shx_header, 28)[0] != 1000:
            raise ValueError(f"Unsupported SHP/SHX version for {tile}; expected 1000")
        if struct.unpack_from("<i", shp_header, 32)[0] != 3 or struct.unpack_from("<i", shx_header, 32)[0] != 3:
            raise ValueError(f"Expected PolyLine SHP/SHX for {tile}")
        shp_words = struct.unpack_from(">i", shp_header, 24)[0]
        shx_words = struct.unpack_from(">i", shx_header, 24)[0]
        if shp_path.stat().st_size != shp_words * 2 or shx_path.stat().st_size != shx_words * 2:
            raise ValueError(f"SHP/SHX declared byte length mismatch for {tile}")
        shx_data_bytes = shx_path.stat().st_size - 100
        if shx_data_bytes < 0 or shx_data_bytes % 8 != 0:
            raise ValueError(f"SHX does not contain complete 8-byte index records for {tile}")
        index_count = shx_data_bytes // 8
        if index_count != dbf_count:
            raise ValueError(f"SHP/DBF record count mismatch for {tile}: {index_count} != {dbf_count}")
        dbf.seek(dbf_header_len)
        shp.seek(100)
        for row in range(1, dbf_count + 1):
            idx = shx.read(8)
            if len(idx) != 8:
                raise ValueError(f"Truncated SHX index at {tile} row {row}")
            offset_words, content_words = struct.unpack(">ii", idx)
            shp_offset = offset_words * 2
            if shp.tell() != shp_offset:
                raise ValueError(f"SHP/SHX offset mismatch in {tile} row {row}")
            record_header = shp.read(8)
            if len(record_header) != 8:
                raise ValueError(f"Truncated SHP record header in {tile} row {row}")
            record_number, actual_content_words = struct.unpack(">ii", record_header)
            if record_number != row or actual_content_words != content_words:
                raise ValueError(f"SHP record/index mismatch in {tile} row {row}")
            content = shp.read(content_words * 2)
            if len(content) != content_words * 2:
                raise ValueError(f"Truncated SHP record body in {tile} row {row}")
            dbf_record = dbf.read(dbf_record_len)
            if len(dbf_record) != dbf_record_len:
                raise ValueError(f"Truncated DBF record in {tile} row {row}")
            if dbf_record[0:1] == b"*":
                raise ValueError(f"Deleted DBF record cannot be represented losslessly: {tile} row {row}")
            if dbf_record[0:1] != b" ":
                raise ValueError(f"Unexpected DBF deletion flag in {tile} row {row}")
            attrs = {f["name"]: _parse_numeric(dbf_record[f["offset"]:f["offset"] + f["width"]], f, tile, row)
                     for f in fields}
            geom, bbox, part_count, point_count = _geometry_from_record(content, tile, row)
            attrs.update({"source_tile": tile, "source_row": row, "feature_id": feature_id(tile, row),
                          "geometry": geom, "bbox": {"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3]},
                          "width_valid": attrs["width_m"] is not None and attrs["width_m"] > 0 and attrs["width_m"] != 1})
            yield attrs, content, dbf_record, part_count, point_count
        if shp.tell() != shp_path.stat().st_size:
            raise ValueError(f"Trailing/unindexed bytes in SHP for {tile}")


def raw_schema() -> pa.Schema:
    fields: list[pa.Field] = []
    for name in DBF_FIELDS:
        typ = pa.int64() if name in INTEGER_FIELDS else pa.decimal128(38, 18)
        fields.append(pa.field(name, typ))
    fields.extend([
        pa.field("source_tile", pa.string(), nullable=False),
        pa.field("source_row", pa.uint32(), nullable=False),
        pa.field("feature_id", pa.uint64(), nullable=False),
        pa.field("width_valid", pa.bool_(), nullable=False),
        pa.field("bbox", pa.struct([pa.field(k, pa.float64(), nullable=False) for k in ("xmin", "ymin", "xmax", "ymax")]), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
    ])
    return pa.schema(fields).with_metadata({b"geo": json.dumps(_geo_metadata(), sort_keys=True, separators=(",", ":")).encode(),
                                            b"grwl:source": b"GRWL_vector_V01.01 raw SHP/DBF",
                                            b"grwl:conversion": b"Direct PolyLine-to-MultiLineString WKB; exact source XY bytes"})


def iter_tile_batches(source_dir: Path, tile: str, batch_size: int = WRITE_BATCH_ROWS) -> Iterator[pa.RecordBatch]:
    """Yield bounded Arrow batches for one already-staged SHP/SHX/DBF tile.

    The returned schema is always :func:`raw_schema`, independent of per-tile
    DBF width/scale descriptors, so batches can be appended to one Parquet
    writer across tiles without materializing a complete tile or archive.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    schema = raw_schema()
    rows: list[dict[str, Any]] = []
    for feature, _, _, _, _ in _tile_rows(tile, source_dir):
        rows.append(feature)
        if len(rows) >= batch_size:
            yield pa.Table.from_pylist(rows, schema=schema).to_batches()[0]
            rows.clear()
    if rows:
        yield pa.Table.from_pylist(rows, schema=schema).to_batches()[0]


def _geo_metadata() -> dict[str, Any]:
    return {"version": "1.1.0", "primary_column": "geometry", "columns": {
        "geometry": {"encoding": "WKB", "geometry_types": ["MultiLineString"],
                     "crs": CRS.from_epsg(4326).to_json_dict(), "edges": "planar",
                     "covering": {"bbox": {k: ["bbox", k] for k in ("xmin", "ymin", "xmax", "ymax")}}}}}


def convert(source_dir: Path, tiles: list[str], output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    if not tiles or len(tiles) != len(set(tiles)):
        raise ValueError("Tile list must be nonempty and contain no duplicates")
    for tile in tiles:
        tile_code(tile)
    output_dir.mkdir(parents=True)
    parquet_path = output_dir / "grwl-raw.parquet"
    tile_reports: list[dict[str, Any]] = []
    rows_processed = 0
    rows_written = 0
    current_tile: str | None = None
    completed_tiles: list[str] = []
    writer: pq.ParquetWriter | None = None
    partial_marker = output_dir / "partial.json"
    partial_marker.write_text(json.dumps({"status": "partial", "usable_release": False,
                                         "reason": "Conversion has not completed."}, indent=2) + "\n")
    try:
        schema = raw_schema()
        writer = pq.ParquetWriter(parquet_path, schema, compression="zstd", version="2.6", write_statistics=True)
        for tile in tiles:
            current_tile = tile
            hashes = {ext: sha256_file(source_dir / f"{tile}.{ext}") for ext in ("shp", "shx", "dbf", "prj")}
            record_digest = hashlib.sha256()
            source_digest = hashlib.sha256()
            count = parts_total = points_total = 0
            extent: list[float] | None = None
            batch: list[dict[str, Any]] = []
            for feature, shp_content, dbf_record, part_count, point_count in _tile_rows(tile, source_dir):
                count += 1
                rows_processed += 1
                parts_total += part_count
                points_total += point_count
                bbox = feature["bbox"]
                if extent is None:
                    extent = [bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"]]
                else:
                    extent = [min(extent[0], bbox["xmin"]), min(extent[1], bbox["ymin"]),
                              max(extent[2], bbox["xmax"]), max(extent[3], bbox["ymax"])]
                # Length-prefix records in the digest so boundaries are explicit.
                source_digest.update(struct.pack("<II", len(shp_content), len(dbf_record)))
                source_digest.update(shp_content)
                source_digest.update(dbf_record)
                record_digest.update(struct.pack("<Q", feature["feature_id"]))
                batch.append(feature)
                if len(batch) >= WRITE_BATCH_ROWS:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema), row_group_size=WRITE_BATCH_ROWS)
                    rows_written += len(batch)
                    batch.clear()
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema), row_group_size=WRITE_BATCH_ROWS)
                rows_written += len(batch)
            tile_reports.append({"tile": tile, "records": count, "parts": parts_total, "vertices": points_total,
                                 "extent": extent, "source_sha256": hashes,
                                 "source_dbf_schema": [{"name": f["name"], "type": "N", "width": f["width"], "scale": f["scale"]}
                                                       for f in _dbf_layout(source_dir / f"{tile}.dbf")[3]],
                                 "source_record_digest_sha256": source_digest.hexdigest(),
                                 "feature_id_digest_sha256": record_digest.hexdigest()})
            completed_tiles.append(tile)
        writer.close()
        writer = None
        report = {"schema_version": 1, "source_product": "GRWL_vector_V01.01",
                  "source_directory_member_files": [".shp", ".shx", ".dbf", ".prj"],
                  "geometry": "GeoParquet 1.1 WKB MultiLineString EPSG:4326; source part and vertex order retained",
                  "numeric_schema": {"integer_fields": sorted(INTEGER_FIELDS),
                                     "decimal_fields": {name: {"type": "decimal128", "precision": 38, "scale": 18}
                                                        for name in DBF_FIELDS if name in DECIMAL_FIELDS},
                                     "nulls": "DBF blank and all-asterisk values are Arrow nulls"},
                  "feature_id": "((first_letter*26 + second_letter)*100 + tile_digits) << 32 | source_row; 1-based row",
                  "width_valid": "width_m is nonnull, positive and not the producer sentinel 1",
                  "compression": "ZSTD", "rows": sum(t["records"] for t in tile_reports),
                  "parts": sum(t["parts"] for t in tile_reports), "tiles": tile_reports,
                  "parquet_sha256": sha256_file(parquet_path)}
        (output_dir / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        partial_marker.unlink()
        return report
    except BaseException as exc:
        close_error: str | None = None
        if writer is not None:
            try:
                writer.close()
            except Exception as close_exc:  # retain the original conversion failure
                close_error = f"{type(close_exc).__name__}: {close_exc}"
        failure = {"schema_version": 1, "status": "failed_partial", "usable_release": False,
                   "error_type": type(exc).__name__, "error": str(exc), "current_tile": current_tile,
                   "completed_tiles": completed_tiles, "rows_processed": rows_processed,
                   "rows_written_to_parquet": rows_written, "parquet_finalization_error": close_error,
                   "partial_files": sorted(p.name for p in output_dir.iterdir() if p.is_file() and p.name != "failure.json")}
        try:
            (output_dir / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
            partial_marker.write_text(json.dumps({"status": "partial", "usable_release": False,
                                                  "failure_report": "failure.json"}, indent=2, sort_keys=True) + "\n")
        except Exception:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--tiles-json", required=True, type=Path, help="JSON array of exact two-letter/two-digit tile codes")
    parser.add_argument("--output", required=True, type=Path, help="New output directory (must not exist)")
    args = parser.parse_args()
    tiles = json.loads(args.tiles_json.read_text())
    if not isinstance(tiles, list) or any(not isinstance(tile, str) for tile in tiles):
        raise SystemExit("--tiles-json must contain a JSON array of tile-code strings")
    result = convert(args.source_dir, tiles, args.output)
    print(json.dumps({"rows": result["rows"], "tiles": len(result["tiles"]),
                      "parquet": str(args.output / "grwl-raw.parquet"), "sha256": result["parquet_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
