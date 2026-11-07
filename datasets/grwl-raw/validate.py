#!/usr/bin/env python3
"""Independently compare raw GRWL SHP/DBF records with a GeoParquet mirror."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from decimal import Decimal, InvalidOperation
import hashlib
import heapq
import json
import math
from pathlib import Path
import re
import struct
import sys
from typing import Any, BinaryIO, Iterator
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS, Geod


DBF_FIELDS = ("utm_east", "utm_north", "width_m", "nchannels", "segmentID",
              "segmentInd", "lakeFlag", "lon", "lat", "elev_m")
INTEGER_FIELDS = {"width_m", "segmentID", "segmentInd", "elev_m"}
DECIMAL_FIELDS = set(DBF_FIELDS) - INTEGER_FIELDS
SOURCE_EXTENSIONS = ("shp", "shx", "dbf", "prj")
TILE_MEMBER_RE = re.compile(r"^([A-Z]{2}[0-9]{2})\.(shp|shx|dbf|prj)$")
PILOT_TILES = ["NI15", "NI16", "NJ12", "NK12", "NL10", "NL11", "NL12", "NL13", "NM11"]
PILOT_FIRST_COUNT, PILOT_LONGEST_COUNT = 32, 32
GLOBAL_FIRST_COUNT, GLOBAL_LONGEST_COUNT = 8, 8
ERROR_LIMIT = 100
BATCH_ROWS = 8192
GEOD = Geod(ellps="WGS84")


class ValidationError(ValueError):
    """A source/Parquet invariant could not be checked or did not match."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_digests(path: Path) -> tuple[str, str]:
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _hash_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _expected_schema() -> pa.Schema:
    """The analytical contract is defined independently of the converter."""
    fields = [pa.field(name, pa.int64() if name in INTEGER_FIELDS else pa.decimal128(38, 18))
              for name in DBF_FIELDS]
    fields.extend((
        pa.field("source_tile", pa.string(), nullable=False),
        pa.field("source_row", pa.uint32(), nullable=False),
        pa.field("feature_id", pa.uint64(), nullable=False),
        pa.field("width_valid", pa.bool_(), nullable=False),
        pa.field("bbox", pa.struct([pa.field(key, pa.float64(), nullable=False)
                                    for key in ("xmin", "ymin", "xmax", "ymax")]), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
    ))
    return pa.schema(fields)


def _member_name(archive_names: dict[str, list[str]], tile: str, ext: str) -> str:
    matches = archive_names.get(f"{tile}.{ext}", [])
    if len(matches) != 1:
        raise ValidationError(f"Expected exactly one {tile}.{ext} archive member; found {len(matches)}")
    return matches[0]


def _verify_source_members(source_dir: Path | None, archive: zipfile.ZipFile | None,
                           archive_names: dict[str, list[str]], tile_item: dict[str, Any]) -> dict[str, str]:
    tile = tile_item["tile"]
    expected = tile_item.get("source_sha256")
    if not isinstance(expected, dict) or set(expected) != set(SOURCE_EXTENSIONS):
        raise ValidationError(f"Manifest lacks four source member SHA-256 pins for {tile}")
    actual = {}
    for ext in SOURCE_EXTENSIONS:
        if source_dir is not None:
            path = source_dir / f"{tile}.{ext}"
            if not path.is_file():
                raise ValidationError(f"Missing source member {path}")
            actual[ext] = _sha256(path)
        else:
            if archive is None:
                raise ValidationError("Exactly one source input is required")
            name = _member_name(archive_names, tile, ext)
            with archive.open(name, "r") as stream:
                actual[ext] = _hash_stream(stream)
        if actual[ext] != expected[ext]:
            raise ValidationError(f"{tile}.{ext} SHA-256 differs from conversion manifest")
    if source_dir is not None:
        wkt = (source_dir / f"{tile}.prj").read_text(encoding="utf-8")
    else:
        wkt = archive.read(_member_name(archive_names, tile, "prj")).decode("utf-8")
    try:
        source_crs = CRS.from_wkt(wkt)
    except Exception as exc:
        raise ValidationError(f"Cannot parse source PRJ CRS for {tile}") from exc
    if not source_crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
        raise ValidationError(f"Source PRJ CRS is not EPSG:4326 for {tile}")
    return actual


def _feature_id(tile: str, row: int) -> int:
    if len(tile) != 4 or not tile[:2].isalpha() or not tile[:2].isupper() or not tile[2:].isdigit():
        raise ValidationError(f"Invalid tile identifier {tile!r}")
    code = ((ord(tile[0]) - 65) * 26 + (ord(tile[1]) - 65)) * 100 + int(tile[2:])
    value = (code << 32) | row
    if row < 1 or row >= 2**32 or value >= 2**53:
        raise ValidationError(f"Feature ID cannot be represented exactly for {tile} source row {row}")
    return value


def _read_exact(stream: BinaryIO, count: int, label: str) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise ValidationError(f"Truncated {label}: expected {count} bytes, found {len(data)}")
    return data


def _dbf_header(stream: BinaryIO, tile: str) -> tuple[int, int, list[dict[str, Any]]]:
    header = _read_exact(stream, 32, f"{tile} DBF header")
    count = struct.unpack_from("<I", header, 4)[0]
    header_len, record_len = struct.unpack_from("<HH", header, 8)
    if header_len < 33 or record_len < 1:
        raise ValidationError(f"Invalid DBF header lengths in {tile}")
    descs = _read_exact(stream, header_len - 32, f"{tile} DBF descriptors")
    if not descs or descs[-1] != 0x0D or (len(descs) - 1) % 32:
        raise ValidationError(f"Invalid DBF descriptor table in {tile}")
    fields = []
    offset = 1
    for pos in range(0, len(descs) - 1, 32):
        descriptor = descs[pos:pos + 32]
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        kind, width, scale = chr(descriptor[11]), descriptor[16], descriptor[17]
        if kind != "N" or name not in DBF_FIELDS:
            raise ValidationError(f"Unexpected DBF field {name!r}/{kind!r} in {tile}")
        fields.append({"name": name, "offset": offset, "width": width, "scale": scale})
        offset += width
    if tuple(field["name"] for field in fields) != DBF_FIELDS or offset != record_len:
        raise ValidationError(f"DBF field order or record length differs in {tile}")
    return count, record_len, fields


def _dbf_values(record: bytes, fields: list[dict[str, Any]], tile: str, row: int) -> dict[str, Any]:
    if record[:1] != b" ":
        raise ValidationError(f"Deleted or invalid DBF record flag in {tile} source row {row}")
    values = {}
    for field in fields:
        text = record[field["offset"]:field["offset"] + field["width"]].strip().decode("ascii")
        if not text or set(text) == {"*"}:
            values[field["name"]] = None
            continue
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError(f"Invalid DBF decimal {text!r} in {tile} row {row} field {field['name']}") from exc
        if not number.is_finite():
            raise ValidationError(f"Non-finite DBF decimal in {tile} row {row} field {field['name']}")
        if field["name"] in INTEGER_FIELDS:
            if number != number.to_integral_value():
                raise ValidationError(f"Noninteger value in DBF integer field {field['name']} at {tile} row {row}")
            values[field["name"]] = int(number)
        else:
            values[field["name"]] = number
    return values


def _shape_record(content: bytes, tile: str, row: int) -> tuple[list[bytes], list[list[tuple[float, float]]], tuple[float, float, float, float]]:
    if len(content) < 44 or struct.unpack_from("<i", content)[0] != 3:
        raise ValidationError(f"Invalid or non-PolyLine SHP record in {tile} row {row}")
    part_count, point_count = struct.unpack_from("<ii", content, 36)
    if part_count < 1 or point_count < 1:
        raise ValidationError(f"Empty SHP PolyLine in {tile} row {row}")
    coord_offset = 44 + part_count * 4
    if coord_offset + point_count * 16 != len(content):
        raise ValidationError(f"Invalid SHP PolyLine content size in {tile} row {row}")
    starts = struct.unpack_from("<" + "i" * part_count, content, 44)
    if starts[0] != 0 or starts[-1] >= point_count or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValidationError(f"Invalid SHP part starts in {tile} row {row}")
    coord_bytes = memoryview(content)[coord_offset:]
    raw_parts, coordinate_parts, xs, ys = [], [], [], []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else point_count
        if end - start < 2:
            raise ValidationError(f"SHP part has fewer than two vertices in {tile} row {row}, part {i + 1}")
        raw = bytes(coord_bytes[start * 16:end * 16])
        raw_parts.append(raw)
        coords = list(struct.iter_unpack("<dd", raw))
        if any(not math.isfinite(x) or not math.isfinite(y) for x, y in coords):
            raise ValidationError(f"Non-finite SHP coordinate in {tile} row {row}")
        coordinate_parts.append(coords)
        xs.extend(x for x, _ in coords)
        ys.extend(y for _, y in coords)
    return raw_parts, coordinate_parts, (min(xs), min(ys), max(xs), max(ys))


def _wkb_parts(value: Any, tile: str, row: int) -> list[bytes]:
    if value is None:
        raise ValidationError(f"Null GeoParquet geometry for {tile} row {row}")
    data = memoryview(value)
    offset = 0

    def uint32(order: str) -> int:
        nonlocal offset
        if offset + 4 > len(data):
            raise ValidationError(f"Truncated WKB in {tile} row {row}")
        result = struct.unpack_from(order + "I", data, offset)[0]
        offset += 4
        return result

    if len(data) < 9:
        raise ValidationError(f"Short WKB geometry in {tile} row {row}")
    byte_order = data[offset]
    offset += 1
    if byte_order not in (0, 1):
        raise ValidationError(f"Invalid WKB byte order in {tile} row {row}")
    root_order = "<" if byte_order == 1 else ">"
    if uint32(root_order) != 5:
        raise ValidationError(f"Expected WKB MultiLineString in {tile} row {row}")
    part_count = uint32(root_order)
    parts = []
    for part_index in range(part_count):
        if offset >= len(data):
            raise ValidationError(f"Truncated WKB part in {tile} row {row}")
        order_byte = data[offset]
        offset += 1
        if order_byte not in (0, 1):
            raise ValidationError(f"Invalid WKB part byte order in {tile} row {row}")
        order = "<" if order_byte == 1 else ">"
        if uint32(order) != 2:
            raise ValidationError(f"Expected WKB LineString child in {tile} row {row}, part {part_index + 1}")
        point_count = uint32(order)
        byte_count = point_count * 16
        if offset + byte_count > len(data):
            raise ValidationError(f"Truncated WKB coordinates in {tile} row {row}")
        source_bytes = data[offset:offset + byte_count]
        if order == "<":
            parts.append(bytes(source_bytes))
        else:
            canonical = bytearray()
            for i in range(point_count):
                x, y = struct.unpack_from(">dd", source_bytes, i * 16)
                canonical.extend(struct.pack("<dd", x, y))
            parts.append(bytes(canonical))
        offset += byte_count
    if offset != len(data):
        raise ValidationError(f"Trailing data after WKB geometry in {tile} row {row}")
    return parts


@contextmanager
def _source_tile(source_dir: Path | None, archive: zipfile.ZipFile | None,
                 archive_names: dict[str, list[str]], tile: str) -> Iterator[tuple[BinaryIO, BinaryIO, BinaryIO, dict[str, int]]]:
    extensions = ("shp", "shx", "dbf")
    if source_dir is not None:
        paths = {ext: source_dir / f"{tile}.{ext}" for ext in extensions}
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        sizes = {ext: path.stat().st_size for ext, path in paths.items()}
        with ExitStack() as stack:
            streams = [stack.enter_context(paths[ext].open("rb")) for ext in extensions]
            yield streams[0], streams[1], streams[2], sizes
        return
    if archive is None:
        raise ValidationError("Exactly one source input is required")
    members = {}
    for ext in extensions:
        matches = archive_names.get(f"{tile}.{ext}", [])
        if len(matches) != 1:
            raise ValidationError(f"Expected exactly one {tile}.{ext} archive member; found {len(matches)}")
        members[ext] = matches[0]
    sizes = {ext: archive.getinfo(name).file_size for ext, name in members.items()}
    with ExitStack() as stack:
        streams = [stack.enter_context(archive.open(members[ext], "r")) for ext in extensions]
        yield streams[0], streams[1], streams[2], sizes


def _source_records(shp: BinaryIO, shx: BinaryIO, dbf: BinaryIO,
                    sizes: dict[str, int], tile: str) -> Iterator[tuple[int, dict[str, Any], list[bytes], list[list[tuple[float, float]]], tuple[float, float, float, float]]]:
    shp_header = _read_exact(shp, 100, f"{tile} SHP header")
    shx_header = _read_exact(shx, 100, f"{tile} SHX header")
    if struct.unpack_from(">i", shp_header)[0] != 9994 or struct.unpack_from(">i", shx_header)[0] != 9994:
        raise ValidationError(f"Invalid SHP/SHX file code in {tile}")
    if struct.unpack_from("<i", shp_header, 28)[0] != 1000 or struct.unpack_from("<i", shx_header, 28)[0] != 1000:
        raise ValidationError(f"Unsupported SHP/SHX version in {tile}")
    if struct.unpack_from("<i", shp_header, 32)[0] != 3 or struct.unpack_from("<i", shx_header, 32)[0] != 3:
        raise ValidationError(f"Expected PolyLine SHP/SHX in {tile}")
    if struct.unpack_from(">i", shp_header, 24)[0] * 2 != sizes["shp"]:
        raise ValidationError(f"SHP declared length mismatch in {tile}")
    if struct.unpack_from(">i", shx_header, 24)[0] * 2 != sizes["shx"]:
        raise ValidationError(f"SHX declared length mismatch in {tile}")
    if (sizes["shx"] - 100) < 0 or (sizes["shx"] - 100) % 8:
        raise ValidationError(f"SHX has incomplete 8-byte index records in {tile}")
    dbf_count, dbf_record_len, dbf_fields = _dbf_header(dbf, tile)
    shx_count = (sizes["shx"] - 100) // 8
    if dbf_count != shx_count:
        raise ValidationError(f"SHP/DBF row count differs in {tile}: {shx_count} vs {dbf_count}")
    shp_offset = 100
    for row in range(1, dbf_count + 1):
        offset_words, content_words = struct.unpack(">ii", _read_exact(shx, 8, f"{tile} SHX index row {row}"))
        if offset_words * 2 != shp_offset:
            raise ValidationError(f"SHP/SHX offsets differ at {tile} row {row}")
        record_no, actual_words = struct.unpack(">ii", _read_exact(shp, 8, f"{tile} SHP record header row {row}"))
        if record_no != row or actual_words != content_words or content_words < 0:
            raise ValidationError(f"SHP/SHX record header differs at {tile} row {row}")
        content = _read_exact(shp, content_words * 2, f"{tile} SHP record row {row}")
        record = _read_exact(dbf, dbf_record_len, f"{tile} DBF record row {row}")
        values = _dbf_values(record, dbf_fields, tile, row)
        raw_parts, coords, bounds = _shape_record(content, tile, row)
        yield row, values, raw_parts, coords, bounds
        shp_offset += 8 + content_words * 2
    if shp_offset != sizes["shp"]:
        raise ValidationError(f"SHP contains trailing/unindexed records in {tile}")


def _part_length(coords: list[tuple[float, float]]) -> float:
    return float(GEOD.line_length([p[0] for p in coords], [p[1] for p in coords]))


def _add_error(errors: list[dict[str, Any]], total: list[int], message: str,
               tile: str | None = None, row: int | None = None, field: str | None = None) -> None:
    total[0] += 1
    if len(errors) < ERROR_LIMIT:
        item: dict[str, Any] = {"message": message}
        if tile is not None:
            item["source_tile"] = tile
        if row is not None:
            item["source_row"] = row
        if field is not None:
            item["field"] = field
        errors.append(item)


def _manifest_tiles(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    tiles = manifest.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise ValidationError("Manifest must contain a nonempty tiles array")
    codes = [item.get("tile") for item in tiles if isinstance(item, dict)]
    if len(codes) != len(tiles) or any(not isinstance(code, str) for code in codes):
        raise ValidationError("Every manifest tile entry must have a string tile code")
    if codes != sorted(codes) or len(set(codes)) != len(codes):
        raise ValidationError("Manifest tile list must be unique and sorted lexicographically")
    return tiles


def validate(source_dir: Path | None, archive_path: Path | None, parquet_path: Path,
             manifest_path: Path, report_path: Path, *, progress_output: bool = False) -> dict[str, Any]:
    """Write a new bounded audit report and return its contents.

    Validation mismatches and parser failures are recorded in the report; the
    CLI exits nonzero when its status is failed. Inputs are only opened read-only.
    """
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite validation report: {report_path}")
    result: dict[str, Any] = {"schema_version": 1, "status": "running", "usable_release": False,
                              "tiles": [], "errors": [], "error_count": 0}
    errors: list[dict[str, Any]] = result["errors"]
    error_total = [0]
    progress = {"tiles_completed": [], "source_rows": 0, "parquet_rows": 0, "parts": 0,
                "width_missing": 0, "width_sentinel_1": 0}
    try:
        if (source_dir is None) == (archive_path is None):
            raise ValidationError("Specify exactly one of source_dir or archive")
        manifest = json.loads(manifest_path.read_text())
        tile_entries = _manifest_tiles(manifest)
        tile_codes = [item["tile"] for item in tile_entries]
        sample_policy = ({"kind": "frozen_pilot", "first_records_per_tile": PILOT_FIRST_COUNT,
                         "longest_parts_per_tile": PILOT_LONGEST_COUNT} if tile_codes == PILOT_TILES else
                        {"kind": "global_controls", "first_records_per_tile": GLOBAL_FIRST_COUNT,
                         "longest_parts_per_tile": GLOBAL_LONGEST_COUNT})
        result.update({"manifest_sha256": _sha256(manifest_path), "parquet_filename": parquet_path.name,
                       "parquet_sha256": _sha256(parquet_path),
                       "manifest_tile_count": len(tile_codes), "sample_policy": sample_policy,
                       "sample_selection": "selected from raw source records before display processing",
                       "source_archive_identity_checked": archive_path is not None})
        if result["parquet_sha256"] != manifest.get("parquet_sha256"):
            _add_error(errors, error_total, "Parquet bytes differ from the conversion manifest SHA-256")
        result["validation_scope"] = "All supplied source records; a pilot is not a global release or scientific/GEE validation"
        parquet = pq.ParquetFile(parquet_path)
        result["parquet_metadata"] = {"rows": parquet.metadata.num_rows,
                                      "row_groups": parquet.metadata.num_row_groups,
                                      "schema": str(parquet.schema_arrow)}
        schema = parquet.schema_arrow
        if not schema.equals(_expected_schema(), check_metadata=False):
            _add_error(errors, error_total, "Analytical Arrow field types, order, or nullability differ from the frozen GRWL raw schema", field="schema")
            raise ValidationError("Analytical GeoParquet schema differs from the frozen contract")
        metadata = schema.metadata or {}
        geo = json.loads(metadata[b"geo"]) if b"geo" in metadata else None
        if not geo or geo.get("version") != "1.1.0" or geo.get("primary_column") != "geometry":
            _add_error(errors, error_total, "Parquet is missing valid GeoParquet 1.1 metadata")
        else:
            geometry_meta = geo.get("columns", {}).get("geometry", {})
            if geometry_meta.get("encoding") != "WKB" or geometry_meta.get("geometry_types") != ["MultiLineString"]:
                _add_error(errors, error_total, "GeoParquet geometry metadata must declare WKB MultiLineString")
            if geometry_meta.get("edges") != "planar":
                _add_error(errors, error_total, "GeoParquet geometry edges must be planar")
            covering = geometry_meta.get("covering", {}).get("bbox")
            expected_covering = {key: ["bbox", key] for key in ("xmin", "ymin", "xmax", "ymax")}
            if covering != expected_covering:
                _add_error(errors, error_total, "GeoParquet covering bbox paths differ from analytical bbox columns")
            try:
                declared_crs = CRS.from_json_dict(geometry_meta["crs"])
                if not declared_crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
                    _add_error(errors, error_total, "GeoParquet geometry CRS is not EPSG:4326")
            except Exception:
                _add_error(errors, error_total, "GeoParquet metadata lacks valid EPSG:4326 PROJJSON")

        if archive_path is not None:
            archive_meta = manifest.get("archive")
            if not isinstance(archive_meta, dict):
                raise ValidationError("ZIP source validation requires archive identity pins in the manifest")
            size = archive_path.stat().st_size
            md5, archive_sha256 = _archive_digests(archive_path)
            if (archive_meta.get("filename") != archive_path.name
                    or archive_meta.get("size_bytes") != size
                    or str(archive_meta.get("provider_md5", "")).lower() != md5
                    or archive_meta.get("sha256") != archive_sha256):
                raise ValidationError("Source ZIP filename, size, MD5, or SHA-256 differs from conversion manifest")
            result["source_archive"] = {"filename": archive_path.name, "size_bytes": size,
                                         "provider_md5": md5, "sha256": archive_sha256}

        archive = zipfile.ZipFile(archive_path) if archive_path is not None else None
        try:
            archive_names: dict[str, list[str]] = {}
            if archive is not None:
                for name in archive.namelist():
                    archive_names.setdefault(Path(name).name, []).append(name)
                source_tiles = {match.group(1) for name in archive.namelist()
                                if (match := TILE_MEMBER_RE.fullmatch(Path(name).name))}
                if source_tiles != set(tile_codes):
                    raise ValidationError("Source ZIP tile inventory differs from conversion manifest")
            columns = list(DBF_FIELDS) + ["source_tile", "source_row", "feature_id", "width_valid", "bbox", "geometry"]
            row_iterator = (row for batch in parquet.iter_batches(batch_size=BATCH_ROWS, columns=columns)
                            for row in batch.to_pylist())
            for tile_item in tile_entries:
                tile = tile_item["tile"]
                source_hashes = _verify_source_members(source_dir, archive, archive_names, tile_item)
                tile_report: dict[str, Any] = {"tile": tile, "source_rows": 0, "matched_rows": 0,
                                               "parts": 0, "vertices": 0, "extent": None,
                                               "width_missing": 0, "width_sentinel_1": 0,
                                               "first_records": [], "longest_parts": [],
                                               "source_sha256": source_hashes}
                first_limit = sample_policy["first_records_per_tile"]
                longest_limit = sample_policy["longest_parts_per_tile"]
                longest_heap: list[tuple[float, int, int, dict[str, Any]]] = []
                extent = None
                with _source_tile(source_dir, archive, archive_names, tile) as (shp, shx, dbf, sizes):
                    for source_row, attrs, source_parts, coordinate_parts, bounds in _source_records(shp, shx, dbf, sizes, tile):
                        tile_report["source_rows"] += 1
                        progress["source_rows"] += 1
                        parts_count = len(source_parts)
                        vertices = sum(len(p) // 16 for p in source_parts)
                        tile_report["parts"] += parts_count
                        tile_report["vertices"] += vertices
                        progress["parts"] += parts_count
                        extent = bounds if extent is None else (min(extent[0], bounds[0]), min(extent[1], bounds[1]),
                                                               max(extent[2], bounds[2]), max(extent[3], bounds[3]))
                        if attrs["width_m"] is None:
                            progress["width_missing"] += 1
                            tile_report["width_missing"] += 1
                        if attrs["width_m"] == 1:
                            progress["width_sentinel_1"] += 1
                            tile_report["width_sentinel_1"] += 1
                        feature_len = 0.0
                        for part_index, coords in enumerate(coordinate_parts, start=1):
                            length = _part_length(coords)
                            feature_len += length
                            part_bbox = (min(x for x, _ in coords), min(y for _, y in coords),
                                         max(x for x, _ in coords), max(y for _, y in coords))
                            sample = {"source_tile": tile, "source_row": source_row,
                                      "feature_id": _feature_id(tile, source_row), "part": part_index,
                                      "bbox": list(part_bbox), "length_m": length, "vertices": len(coords)}
                            key = (length, -source_row, -part_index, sample)
                            if len(longest_heap) < longest_limit:
                                heapq.heappush(longest_heap, key)
                            elif key[:3] > longest_heap[0][:3]:
                                heapq.heapreplace(longest_heap, key)
                        if source_row <= first_limit:
                            tile_report["first_records"].append({"source_tile": tile, "source_row": source_row,
                                "feature_id": _feature_id(tile, source_row), "bbox": list(bounds),
                                "length_m": feature_len, "parts": parts_count, "vertices": vertices})

                        try:
                            parquet_row = next(row_iterator)
                            progress["parquet_rows"] += 1
                        except StopIteration:
                            parquet_row = None
                        if parquet_row is None:
                            _add_error(errors, error_total, "Parquet ended before source rows", tile, source_row)
                            continue
                        mismatch = False
                        if parquet_row.get("source_tile") != tile:
                            _add_error(errors, error_total, f"source_tile mismatch: {parquet_row.get('source_tile')!r}", tile, source_row, "source_tile")
                            mismatch = True
                        if parquet_row.get("source_row") != source_row:
                            _add_error(errors, error_total, f"source_row mismatch: {parquet_row.get('source_row')!r}", tile, source_row, "source_row")
                            mismatch = True
                        expected_id = _feature_id(tile, source_row)
                        if parquet_row.get("feature_id") != expected_id:
                            _add_error(errors, error_total, f"feature_id mismatch: {parquet_row.get('feature_id')!r} != {expected_id}", tile, source_row, "feature_id")
                            mismatch = True
                        for field in DBF_FIELDS:
                            actual = parquet_row.get(field)
                            expected = attrs[field]
                            if actual != expected:
                                _add_error(errors, error_total, f"DBF mismatch: parquet={actual!r}, source={expected!r}", tile, source_row, field)
                                mismatch = True
                        expected_width_valid = attrs["width_m"] is not None and attrs["width_m"] > 0 and attrs["width_m"] != 1
                        if parquet_row.get("width_valid") is not expected_width_valid:
                            _add_error(errors, error_total, f"width_valid mismatch: {parquet_row.get('width_valid')!r} != {expected_width_valid!r}", tile, source_row, "width_valid")
                            mismatch = True
                        actual_bbox = parquet_row.get("bbox")
                        expected_bbox = {"xmin": bounds[0], "ymin": bounds[1], "xmax": bounds[2], "ymax": bounds[3]}
                        if actual_bbox != expected_bbox:
                            _add_error(errors, error_total, f"bbox mismatch: {actual_bbox!r} != {expected_bbox!r}", tile, source_row, "bbox")
                            mismatch = True
                        try:
                            parquet_parts = _wkb_parts(parquet_row.get("geometry"), tile, source_row)
                            if len(parquet_parts) != len(source_parts):
                                _add_error(errors, error_total, f"part count mismatch: {len(parquet_parts)} != {len(source_parts)}", tile, source_row, "geometry")
                                mismatch = True
                            elif any(actual_part != source_part for actual_part, source_part in zip(parquet_parts, source_parts)):
                                _add_error(errors, error_total, "XY float64 bits or part boundaries differ from SHP", tile, source_row, "geometry")
                                mismatch = True
                        except ValidationError as exc:
                            _add_error(errors, error_total, str(exc), tile, source_row, "geometry")
                            mismatch = True
                        if not mismatch:
                            tile_report["matched_rows"] += 1

                tile_report["extent"] = list(extent) if extent is not None else None
                if tile_item.get("extent") != tile_report["extent"]:
                    _add_error(errors, error_total, "Manifest tile extent differs from source coordinates", tile, field="extent")
                tile_report["longest_parts"] = [item[3] for item in sorted(longest_heap, key=lambda x: (-x[0], -x[1], -x[2]))]
                expected_count = tile_item.get("records")
                if expected_count is not None and expected_count != tile_report["source_rows"]:
                    _add_error(errors, error_total, f"Manifest row count {expected_count} differs from source {tile_report['source_rows']}", tile)
                result["tiles"].append(tile_report)
                progress["tiles_completed"].append(tile)
                if progress_output and (len(progress["tiles_completed"]) % 10 == 0 or len(progress["tiles_completed"]) == len(tile_entries)):
                    print(json.dumps({"tiles_checked": len(progress["tiles_completed"]),
                                      "tiles_total": len(tile_entries), "source_rows_checked": progress["source_rows"],
                                      "errors_so_far": error_total[0]}), file=sys.stderr, flush=True)
            extras = 0
            for _ in row_iterator:
                extras += 1
                progress["parquet_rows"] += 1
            if extras:
                _add_error(errors, error_total, f"Parquet has {extras} extra rows after source tiles")
        finally:
            if archive is not None:
                archive.close()
        if parquet.metadata.num_rows != progress["source_rows"]:
            _add_error(errors, error_total, f"Parquet footer row count {parquet.metadata.num_rows} differs from source {progress['source_rows']}")
        result["source_member_sha256_checked"] = len(result["tiles"]) * len(SOURCE_EXTENSIONS)
        extents = [tile["extent"] for tile in result["tiles"] if tile["extent"] is not None]
        expected_bbox = ([min(box[0] for box in extents), min(box[1] for box in extents),
                          max(box[2] for box in extents), max(box[3] for box in extents)] if extents else None)
        geometry_bbox = geo.get("columns", {}).get("geometry", {}).get("bbox") if geo else None
        if geometry_bbox is not None or len(tile_codes) == 829:
            if geometry_bbox != expected_bbox:
                _add_error(errors, error_total, f"GeoParquet global bbox {geometry_bbox!r} differs from source {expected_bbox!r}", field="geo.bbox")
        result["status"] = "passed" if error_total[0] == 0 else "failed"
        result["usable_release"] = error_total[0] == 0
    except Exception as exc:
        result["status"] = "failed"
        result["usable_release"] = False
        result["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)}
    result["progress"] = progress
    result["error_count"] = error_total[0]
    result["errors"] = errors
    result["errors_truncated"] = error_total[0] > len(errors)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-dir", type=Path)
    source.add_argument("--archive", type=Path)
    parser.add_argument("--parquet", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path, help="New JSON report path; existing files are never overwritten")
    parser.add_argument("--progress", action="store_true", help="Print bounded tile progress to stderr")
    args = parser.parse_args()
    report = validate(args.source_dir, args.archive, args.parquet, args.manifest, args.report, progress_output=args.progress)
    print(json.dumps({"status": report["status"], "error_count": report["error_count"], "report": str(args.report)}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
