#!/usr/bin/env python3
"""Build one bounded global GRWL GeoParquet from the pinned producer ZIP."""
from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack
import hashlib
import importlib.util
import importlib.metadata
import platform
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import time
from typing import Any
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS


RAW_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("grwl_raw_convert", RAW_DIR / "convert.py")
if spec is None or spec.loader is None:
    raise ImportError("Cannot load GRWL raw converter")
convert = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = convert
spec.loader.exec_module(convert)

ROOT = RAW_DIR.parents[1]
DEFAULT_CRITERIA = ROOT / "research/grwl-raw-release-20261102/criteria.json"
DEFAULT_INVENTORY = ROOT / "research/grwl-raw-audit-20261102/vector-inventory-r1.json"
TILE_RE = re.compile(r"^([A-Z]{2}[0-9]{2})\.(shp|shx|dbf|prj)$")
SHAPE_EXTENSIONS = ("shp", "shx", "dbf", "prj")
COPY_CHUNK_BYTES = 1024 * 1024
PARQUET_BATCH_ROWS = 8192
EXPECTED_GLOBAL_ROWS = 64_572_998
MIN_FREE_BYTES = 15 * 1024**3
MAX_TASK_BYTES = 12 * 1024**3


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_digests(path: Path) -> tuple[str, str]:
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(COPY_CHUNK_BYTES), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _existing_disk_path(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists():
        candidate = candidate.parent
    return candidate


def _output_bytes(directory: Path) -> int:
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def _resource_check(archive_size: int, output_dir: Path | None,
                    disk_usage_fn=shutil.disk_usage,
                    min_free_bytes: int = MIN_FREE_BYTES,
                    max_task_bytes: int = MAX_TASK_BYTES) -> dict[str, int]:
    disk = disk_usage_fn(_existing_disk_path(output_dir if output_dir is not None else Path.cwd()))
    free = int(disk.free)
    current_output = _output_bytes(output_dir) if output_dir is not None and output_dir.exists() else 0
    total = archive_size + current_output
    if free < min_free_bytes:
        raise OSError(f"Free disk space {free} is below required floor {min_free_bytes}")
    if total > max_task_bytes:
        raise OSError(f"Archive plus output bytes {total} exceed task ceiling {max_task_bytes}")
    return {"free_bytes": free, "archive_bytes": archive_size,
            "output_bytes": current_output, "archive_plus_output_bytes": total}


def _inventory_tiles(inventory: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, int]]:
    members = inventory.get("members")
    if not isinstance(members, list):
        raise ValueError("Source inventory lacks a members array")
    names: dict[str, dict[str, Any]] = {}
    per_tile: dict[str, dict[str, dict[str, Any]]] = {}
    for item in members:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("Malformed member entry in source inventory")
        name = item["name"]
        if name in names:
            raise ValueError(f"Duplicate inventory member {name}")
        names[name] = item
        match = TILE_RE.fullmatch(Path(name).name)
        if match:
            tile, extension = match.groups()
            fields = per_tile.setdefault(tile, {})
            if extension in fields:
                raise ValueError(f"Multiple {extension} members found for tile {tile}")
            fields[extension] = item
    tiles = sorted(per_tile)
    if not tiles:
        raise ValueError("No GRWL tile members found in inventory")
    rows: dict[str, int] = {}
    for tile in tiles:
        found = per_tile[tile]
        if set(found) != set(SHAPE_EXTENSIONS):
            raise ValueError(f"Incomplete member set for {tile}: {sorted(found)}")
        shx_size = int(found["shx"]["uncompressed_bytes"])
        if shx_size < 100 or (shx_size - 100) % 8:
            raise ValueError(f"Inventory SHX size is not 100-byte header plus 8-byte records: {tile}")
        rows[tile] = (shx_size - 100) // 8
    return tiles, names, rows


def _validate_inventory_against_zip(archive: zipfile.ZipFile, inventory: dict[str, Any],
                                    inventory_names: dict[str, dict[str, Any]]) -> None:
    infos = archive.infolist()
    zip_names = {info.filename for info in infos}
    if zip_names != set(inventory_names):
        missing = sorted(set(inventory_names) - zip_names)[:5]
        extra = sorted(zip_names - set(inventory_names))[:5]
        raise ValueError(f"ZIP central directory differs from frozen inventory (missing={missing}, extra={extra})")
    for info in infos:
        item = inventory_names[info.filename]
        expected = (int(item["compressed_bytes"]), int(item["uncompressed_bytes"]), str(item["crc32"]).lower())
        actual = (info.compress_size, info.file_size, f"{info.CRC:08x}")
        if actual != expected:
            raise ValueError(f"ZIP central directory metadata differs for {info.filename}")
    if int(inventory.get("archive_size_bytes", -1)) != archive.fp.seek(0, os.SEEK_END):
        raise ValueError("Inventory archive byte size does not match the ZIP")


def _read_member_head(archive: zipfile.ZipFile, name: str, count: int) -> bytes:
    with archive.open(name, "r") as stream:
        data = stream.read(count)
    if len(data) != count:
        raise ValueError(f"Short ZIP member header: {name}")
    return data


def _preflight_dbf(archive: zipfile.ZipFile, name: str, tile: str) -> tuple[int, int, list[dict[str, Any]]]:
    with archive.open(name, "r") as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise ValueError(f"Truncated DBF header: {name}")
        count = struct.unpack_from("<I", header, 4)[0]
        header_len, record_len = struct.unpack_from("<HH", header, 8)
        if header_len < 33 or record_len < 1:
            raise ValueError(f"Invalid DBF header lengths: {name}")
        descriptors = stream.read(header_len - 32)
    if count > convert.MAX_SOURCE_ROW:
        raise ValueError(f"DBF source row count exceeds feature ID capacity in {tile}")
    if len(descriptors) != header_len - 32 or descriptors[-1:] != b"\r" or (len(descriptors) - 1) % 32:
        raise ValueError(f"Invalid DBF descriptor table: {name}")
    offset = 1
    fields = []
    for pos in range(0, len(descriptors) - 1, 32):
        desc = descriptors[pos:pos + 32]
        field_name = desc[:11].split(b"\0", 1)[0].decode("ascii")
        kind, width, scale = chr(desc[11]), desc[16], desc[17]
        if field_name not in convert.DBF_FIELDS or kind != "N":
            raise ValueError(f"Unsupported DBF field {field_name!r}/{kind!r} in {tile}")
        if field_name in convert.INTEGER_FIELDS and scale != 0:
            raise ValueError(f"Unsupported noninteger scale for {field_name} in {tile}: {scale}")
        if scale > width or width < 1 or width > 38 or scale > 18:
            raise ValueError(f"DBF descriptor cannot fit global Arrow schema in {tile} field {field_name}")
        if field_name in convert.INTEGER_FIELDS and width > 19:
            raise ValueError(f"Integer DBF descriptor exceeds supported int64 width in {tile} field {field_name}")
        fields.append({"name": field_name, "type": "N", "width": width, "scale": scale})
        offset += width
    if tuple(f["name"] for f in fields) != convert.DBF_FIELDS or offset != record_len:
        raise ValueError(f"Unsupported DBF field order or record length in {tile}")
    if 32 + (header_len - 32) + count * record_len > archive.getinfo(name).file_size:
        raise ValueError(f"DBF is shorter than its declared records in {tile}")
    return count, record_len, fields


def _preflight_tiles(archive: zipfile.ZipFile, tile_entries: dict[str, dict[str, Any]],
                     inventory_rows: dict[str, int]) -> list[dict[str, Any]]:
    reports = []
    for tile in sorted(tile_entries):
        members = tile_entries[tile]
        dbf_count, _, dbf_fields = _preflight_dbf(archive, members["dbf"]["name"], tile)
        for ext in ("shp", "shx"):
            info = members[ext]
            header = _read_member_head(archive, info["name"], 100)
            if struct.unpack_from(">i", header, 0)[0] != 9994 or struct.unpack_from("<i", header, 28)[0] != 1000:
                raise ValueError(f"Invalid SHP/SHX code or version for {tile}.{ext}")
            if struct.unpack_from("<i", header, 32)[0] != 3:
                raise ValueError(f"Unsupported shape type for {tile}.{ext}")
            if struct.unpack_from(">i", header, 24)[0] * 2 != info["uncompressed_bytes"]:
                raise ValueError(f"Declared file length differs in {tile}.{ext}")
        shx_count = inventory_rows[tile]
        if dbf_count != shx_count:
            raise ValueError(f"DBF/SHX record counts differ for {tile}: {dbf_count} != {shx_count}")
        prj_name = members["prj"]["name"]
        try:
            crs = CRS.from_wkt(archive.read(prj_name).decode("ascii"))
        except Exception as exc:
            raise ValueError(f"Cannot parse PRJ CRS for {tile}") from exc
        if not crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError(f"Unsupported source CRS for {tile}: {crs.to_string()}")
        reports.append({"tile": tile, "records": shx_count, "source_dbf_schema": dbf_fields})
    return reports


def _extract_members(archive: zipfile.ZipFile, members: dict[str, dict[str, Any]],
                     scratch: Path, hashes: dict[str, str]) -> dict[str, str]:
    scratch.mkdir(parents=True, exist_ok=False)
    for ext in SHAPE_EXTENSIONS:
        info = members[ext]
        destination = scratch / f"{members['tile']}.{ext}"
        digest = hashlib.sha256()
        written = 0
        with archive.open(info["name"], "r") as source, destination.open("xb") as target:
            for chunk in iter(lambda: source.read(COPY_CHUNK_BYTES), b""):
                target.write(chunk)
                digest.update(chunk)
                written += len(chunk)
        if written != int(info["uncompressed_bytes"]):
            raise ValueError(f"Extracted byte count differs for {info['name']}")
        hashes[ext] = digest.hexdigest()
    return hashes


def _remove_successful_scratch(scratch: Path) -> None:
    for ext in SHAPE_EXTENSIONS:
        path = scratch / f"{scratch.name}.{ext}"
        if path.exists():
            path.unlink()
    scratch.rmdir()


def _source_member_groups(inventory: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, Any]]]:
    tile_codes, inventory_names, rows = _inventory_tiles(inventory)
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for item in inventory["members"]:
        match = TILE_RE.fullmatch(Path(item["name"]).name)
        if match:
            tile, ext = match.groups()
            groups.setdefault(tile, {})[ext] = item
    for tile, group in groups.items():
        if set(group) != set(SHAPE_EXTENSIONS):
            raise ValueError(f"Missing required SHP/SHX/DBF/PRJ inventory member for {tile}")
        group["tile"] = tile
    return tile_codes, groups, inventory_names


def _write_failure(output_dir: Path, error: BaseException, current_tile: str | None,
                   completed_tiles: list[str], rows_processed: int, rows_written: int,
                   writer_error: str | None, archive_identity: dict[str, Any],
                   current_member_hashes: dict[str, str] | None,
                   tile_reports: list[dict[str, Any]]) -> None:
    failure = {"schema_version": 1, "status": "failed_partial", "usable_release": False,
               "error_type": type(error).__name__, "error": str(error), "current_tile": current_tile,
               "completed_tiles": completed_tiles, "rows_processed": rows_processed,
               "rows_written_to_parquet": rows_written, "parquet_finalization_error": writer_error,
               "archive": archive_identity, "completed_tile_sources": tile_reports,
               "current_tile_member_sha256": current_member_hashes,
               "retained_files": sorted(str(p.relative_to(output_dir)) for p in output_dir.rglob("*") if p.is_file())}
    (output_dir / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
    (output_dir / "partial.json").write_text(json.dumps({"status": "partial", "usable_release": False,
                                                          "failure_report": "failure.json"}, indent=2, sort_keys=True) + "\n")


def build_global(archive_path: Path, output_dir: Path, criteria: dict[str, Any],
                 inventory: dict[str, Any], source_pin: dict[str, Any], *,
                 criteria_sha256: str | None = None, inventory_sha256: str | None = None,
                 disk_usage_fn=shutil.disk_usage,
                 min_free_bytes: int = MIN_FREE_BYTES,
                 max_task_bytes: int = MAX_TASK_BYTES) -> dict[str, Any]:
    """Preflight pinned ZIP, then stream sorted tiles into one Parquet file.

    `source_pin` is explicit so tiny synthetic archives can exercise this same
    implementation without weakening the official CLI's frozen pins.
    """
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    raw_criteria = criteria.get("raw_component", {})
    if int(source_pin.get("archive_size_bytes", -1)) != int(raw_criteria.get("archive_size_bytes", -2)):
        raise ValueError("Source pin archive size does not match criteria")
    if str(source_pin.get("provider_md5", "")).lower() != str(raw_criteria.get("provider_md5", "")).lower():
        raise ValueError("Source pin MD5 does not match criteria")
    if raw_criteria.get("filename") and archive_path.name != raw_criteria["filename"]:
        raise ValueError(f"Archive filename differs from criteria: {archive_path.name}")
    expected_tile_count = int(source_pin.get("expected_tiles", -1))
    expected_rows = int(source_pin.get("expected_rows", -1))
    if expected_tile_count != int(raw_criteria.get("expected_tiles", -2)):
        raise ValueError("Source pin tile count does not match criteria")
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    actual_size = archive_path.stat().st_size
    if actual_size != int(source_pin["archive_size_bytes"]):
        raise ValueError(f"Archive size pin mismatch: {actual_size} != {source_pin['archive_size_bytes']}")
    md5, archive_sha256 = _archive_digests(archive_path)
    if md5.lower() != str(source_pin["provider_md5"]).lower():
        raise ValueError(f"Archive provider MD5 mismatch: {md5}")
    _resource_check(actual_size, output_dir, disk_usage_fn, min_free_bytes, max_task_bytes)
    tile_codes, tile_members, inventory_names = _source_member_groups(inventory)
    if len(tile_codes) != expected_tile_count:
        raise ValueError(f"Inventory tile count {len(tile_codes)} != pinned {expected_tile_count}")
    inventory_row_total = sum((int(item["uncompressed_bytes"]) - 100) // 8
                              for item in inventory["members"]
                              if TILE_RE.fullmatch(Path(item["name"]).name)
                              and Path(item["name"]).suffix.lower() == ".shx")
    if inventory_row_total != expected_rows:
        raise ValueError(f"Inventory SHX row total {inventory_row_total} != pinned {expected_rows}")
    if expected_rows == EXPECTED_GLOBAL_ROWS and expected_tile_count != 829:
        raise ValueError("The official global source row total requires all 829 tiles")
    if int(inventory.get("archive_size_bytes", -1)) != actual_size:
        raise ValueError("Inventory archive size differs from pinned archive")

    with zipfile.ZipFile(archive_path, "r") as archive:
        _validate_inventory_against_zip(archive, inventory, inventory_names)
        preflight_reports = _preflight_tiles(archive, tile_members, {
            tile: (int(tile_members[tile]["shx"]["uncompressed_bytes"]) - 100) // 8 for tile in tile_codes})
    if len(preflight_reports) != expected_tile_count or sum(t["records"] for t in preflight_reports) != expected_rows:
        raise ValueError("Preflight tile and record totals differ from source pins")

    environment_lock = Path(sys.prefix).resolve().parent / "uv.lock"
    if not environment_lock.is_file():
        raise ValueError("Use a locked repository Python environment with uv.lock next to .venv")
    provenance = {"builder_sha256": _sha256_file(Path(__file__)),
                  "converter_sha256": _sha256_file(RAW_DIR / "convert.py"),
                  "environment_lock_sha256": _sha256_file(environment_lock),
                  "python_version": platform.python_version(),
                  "packages": {name: importlib.metadata.version(name) for name in ("pyarrow", "pyproj")}}

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    _resource_check(actual_size, output_dir, disk_usage_fn, min_free_bytes, max_task_bytes)
    output_dir.mkdir()
    partial_marker = output_dir / "partial.json"
    partial_marker.write_text(json.dumps({"status": "partial", "usable_release": False,
                                         "reason": "Global conversion has not completed."}, indent=2) + "\n")
    workflow = output_dir / "workflow"
    parquet_path = output_dir / "grwl-raw.parquet"
    scratch_root = output_dir / ".scratch"
    writer = None
    current_tile = None
    current_member_hashes: dict[str, str] | None = None
    rows_processed = rows_written = parts_total = 0
    completed_tiles: list[str] = []
    tile_reports: list[dict[str, Any]] = []
    last_resource = {}
    started = time.monotonic()
    try:
        workflow.mkdir()
        for original, name in [(Path(__file__), "build_global.py.txt"), (RAW_DIR / "convert.py", "convert.py.txt"), (environment_lock, "uv.lock")]:
            shutil.copyfile(original, workflow / name)
        (workflow / "criteria.json").write_text(json.dumps(criteria, indent=2)+"\n")
        (workflow / "inventory.json").write_text(json.dumps(inventory, indent=2)+"\n")
        schema = convert.raw_schema()
        writer = pq.ParquetWriter(parquet_path, schema, compression="zstd", version="2.6", write_statistics=True)
        scratch_root.mkdir()
        with zipfile.ZipFile(archive_path, "r") as archive:
            for index, preflight in enumerate(preflight_reports, start=1):
                tile = preflight["tile"]
                current_tile = tile
                scratch = scratch_root / tile
                current_member_hashes = {}
                member_hashes = _extract_members(archive, tile_members[tile], scratch, current_member_hashes)
                last_resource = _resource_check(actual_size, output_dir, disk_usage_fn, min_free_bytes, max_task_bytes)
                source_digest, feature_digest = hashlib.sha256(), hashlib.sha256()
                count = tile_parts = vertices = 0
                extent = None
                batch = []
                for feature, shp_content, dbf_record, part_count, point_count in convert._tile_rows(tile, scratch):
                    count += 1
                    rows_processed += 1
                    tile_parts += part_count
                    vertices += point_count
                    parts_total += part_count
                    bbox = feature["bbox"]
                    if extent is None:
                        extent = [bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"]]
                    else:
                        extent = [min(extent[0], bbox["xmin"]), min(extent[1], bbox["ymin"]),
                                  max(extent[2], bbox["xmax"]), max(extent[3], bbox["ymax"])]
                    source_digest.update(struct.pack("<II", len(shp_content), len(dbf_record)))
                    source_digest.update(shp_content)
                    source_digest.update(dbf_record)
                    feature_digest.update(struct.pack("<Q", feature["feature_id"]))
                    batch.append(feature)
                    if len(batch) >= PARQUET_BATCH_ROWS:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema), row_group_size=PARQUET_BATCH_ROWS)
                        rows_written += len(batch)
                        batch.clear()
                if batch:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema), row_group_size=PARQUET_BATCH_ROWS)
                    rows_written += len(batch)
                if count != preflight["records"]:
                    raise ValueError(f"Processed row count for {tile} differs from preflight: {count} != {preflight['records']}")
                last_resource = _resource_check(actual_size, output_dir, disk_usage_fn, min_free_bytes, max_task_bytes)
                tile_reports.append({"tile": tile, "records": count, "parts": tile_parts, "vertices": vertices,
                                     "extent": extent, "source_sha256": {ext: member_hashes[ext] for ext in SHAPE_EXTENSIONS},
                                     "source_dbf_schema": preflight["source_dbf_schema"],
                                     "source_record_digest_sha256": source_digest.hexdigest(),
                                     "feature_id_digest_sha256": feature_digest.hexdigest(),
                                     "source_member_crc32": {ext: f"{int(tile_members[tile][ext]['crc32'], 16):08x}"
                                                              for ext in SHAPE_EXTENSIONS}})
                completed_tiles.append(tile)
                _remove_successful_scratch(scratch)
                last_resource = _resource_check(actual_size, output_dir, disk_usage_fn, min_free_bytes, max_task_bytes)
                if index % 10 == 0 or index == len(preflight_reports):
                    print(json.dumps({"tiles_completed": index, "tiles_total": len(preflight_reports),
                                      "rows_written": rows_written, "output_bytes": last_resource["output_bytes"],
                                      "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
        geo = convert._geo_metadata()
        extents = [t["extent"] for t in tile_reports if t["extent"] is not None]
        geo["columns"]["geometry"]["bbox"] = [min(b[0] for b in extents), min(b[1] for b in extents),
                                                  max(b[2] for b in extents), max(b[3] for b in extents)]
        geo_bytes = json.dumps(geo, sort_keys=True, separators=(",", ":")).encode()
        final_schema = schema.with_metadata({**schema.metadata, b"geo": geo_bytes})
        # Arrow readers prefer the embedded Arrow schema. Update it together
        # with GeoParquet metadata so both views expose the same global bbox.
        writer.add_key_value_metadata({"geo": geo_bytes,
            "ARROW:schema": base64.b64encode(final_schema.serialize().to_pybytes())})
        writer.close()
        writer = None
        last_resource = _resource_check(actual_size, output_dir, disk_usage_fn, min_free_bytes, max_task_bytes)
        if rows_written != expected_rows or parts_total <= 0:
            raise ValueError(f"Completed output totals differ from pins: rows={rows_written}, parts={parts_total}")
        report = {"schema_version": 1, "status": "provisional", "usable_release": False,
                  "validation": {"status": "pending", "required": "independent source-to-GeoParquet validation"},
                  "build_inputs": provenance, "source_product": "GRWL_vector_V01.01", "archive": {"filename": raw_criteria.get("filename"),
                      "size_bytes": actual_size, "provider_md5": md5, "sha256": archive_sha256,
                      "whole_archive_checksum_verified": True},
                  "criteria_sha256": criteria_sha256 or hashlib.sha256(json.dumps(criteria, sort_keys=True).encode()).hexdigest(),
                  "source_inventory_sha256": inventory_sha256 or hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
                  "source_inventory_member_count": len(inventory_names),
                  "geometry": "GeoParquet 1.1 WKB MultiLineString EPSG:4326; source part and vertex order retained",
                  "numeric_schema": {"integer_fields": sorted(convert.INTEGER_FIELDS),
                                     "decimal_fields": {name: {"type": "decimal128", "precision": 38, "scale": 18}
                                                        for name in convert.DBF_FIELDS if name in convert.DECIMAL_FIELDS},
                                     "nulls": "DBF blank and all-asterisk values are Arrow nulls"},
                  "feature_id": "((first_letter*26 + second_letter)*100 + tile_digits) << 32 | source_row; 1-based row",
                  "width_valid": "width_m is nonnull, positive and not the producer sentinel 1",
                  "compression": "ZSTD", "rows": rows_written, "parts": parts_total,
                  "tiles": tile_reports, "resource_check": last_resource,
                  "parquet_sha256": _sha256_file(parquet_path)}
        (output_dir / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        partial_marker.unlink()
        scratch_root.rmdir()
        return report
    except BaseException as exc:
        writer_error = None
        if writer is not None:
            try:
                writer.close()
            except Exception as close_exc:
                writer_error = f"{type(close_exc).__name__}: {close_exc}"
        _write_failure(output_dir, exc, current_tile, completed_tiles, rows_processed, rows_written,
                       writer_error, {"size_bytes": actual_size, "provider_md5": md5, "sha256": archive_sha256},
                       current_member_hashes, tile_reports)
        raise


def _load_cli_inputs(criteria_path: Path, inventory_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    criteria_bytes = criteria_path.read_bytes()
    inventory_bytes = inventory_path.read_bytes()
    criteria = json.loads(criteria_bytes)
    inventory = json.loads(inventory_bytes)
    raw = criteria["raw_component"]
    if (raw.get("filename") != "GRWL_vector_V01.01.zip"
            or raw.get("archive_size_bytes") != 3104998836
            or raw.get("provider_md5") != "40171f15c0fccd470db32446dda0480e"):
        raise ValueError("Production source pins differ from the selected official GRWL archive")
    tile_codes, _, rows = _inventory_tiles(inventory)
    expected_rows = sum(rows.values())
    pin = {"archive_size_bytes": int(raw["archive_size_bytes"]), "provider_md5": raw["provider_md5"],
           "expected_tiles": int(raw["expected_tiles"]), "expected_rows": expected_rows}
    if pin["expected_tiles"] != 829 or expected_rows != EXPECTED_GLOBAL_ROWS or len(tile_codes) != 829:
        raise ValueError("Frozen global criteria/inventory differ from 829 tiles and 64,572,998 SHX rows")
    if tile_codes != sorted(tile_codes):
        raise ValueError("Global inventory tile list is not sorted")
    return criteria, inventory, pin, hashlib.sha256(criteria_bytes).hexdigest(), hashlib.sha256(inventory_bytes).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()
    criteria, inventory, pin, criteria_hash, inventory_hash = _load_cli_inputs(args.criteria, args.inventory)
    resources = criteria["resources"]
    free = shutil.disk_usage(_existing_disk_path(args.output)).free
    if free < resources["native_start_free_bytes"]:
        raise OSError("Global conversion is below the recorded starting disk floor")
    result = build_global(args.archive, args.output, criteria, inventory, pin,
                          criteria_sha256=criteria_hash, inventory_sha256=inventory_hash,
                          min_free_bytes=resources["native_stop_free_bytes"],
                          max_task_bytes=resources["task_storage_ceiling_bytes"])
    print(json.dumps({"status": result["status"], "rows": result["rows"], "tiles": len(result["tiles"]),
                      "parquet_sha256": result["parquet_sha256"], "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
