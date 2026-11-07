#!/usr/bin/env python3
"""Finalize a provisional PMTiles display package from bound local evidence.

Validation is read-only. The manifest is marked prepared only after all evidence,
report copies, README content, and the complete package inventory are ready.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


REPO = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LAYER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
MAX_ZOOM = 12
MAX_GEOMETRY_METRES = 30.0
MAX_BROWSER_BYTES = 128 * 1024 * 1024
REGIONS = ("global", "north_america", "southwest_europe", "south_america", "asia", "oceania")
ALLOWED_MISSING_CAUSES = {"source_empty", "zero_length", "zero_area", "quantization_collapse"}


class FinalizeError(ValueError):
    """Invalid package or incomplete/mismatched finalization evidence."""


def _json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise FinalizeError(f"{label} is a symlink: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalizeError(f"{label} must be a JSON object: {path}")
    return value


def _safe_rel(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise FinalizeError(f"{label} must be a safe POSIX relative path")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or any(part in ("", ".", "..") for part in value.split("/")):
        raise FinalizeError(f"unsafe {label}: {value}")
    if any(part.startswith(".") for part in posix.parts):
        raise FinalizeError(f"hidden {label} is not allowed: {value}")
    return posix.as_posix()


def _regular_no_symlink(root: Path, rel: str, label: str) -> Path:
    rel = _safe_rel(rel, label)
    current = root
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            raise FinalizeError(f"{label} traverses a symlink: {rel}")
    try:
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise FinalizeError(f"missing {label}: {rel}") from exc
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        raise FinalizeError(f"{label} is not a regular file in its root: {rel}")
    return resolved


def _digest(path: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            hasher.update(block)
    return size, hasher.hexdigest()


def _verify_archive(asset: dict[str, Any], archive_path: Path) -> dict[str, Any]:
    executable = shutil.which("pmtiles")
    if executable is None and Path("/opt/homebrew/bin/pmtiles").is_file():
        executable = "/opt/homebrew/bin/pmtiles"
    if executable is None:
        raise FinalizeError("pmtiles CLI is required to verify each archive before finalization")
    executable_path = Path(executable).resolve(strict=True)
    if not executable_path.is_file():
        raise FinalizeError("pmtiles CLI resolved to a non-file")
    executable_size, executable_hash = _digest(executable_path)
    result = subprocess.run([str(executable_path), "verify", str(archive_path)], capture_output=True,
                            text=True, check=False)
    archive_size, archive_hash = _digest(archive_path)
    evidence = {
        "schema_version": 1,
        "asset_id": asset["id"],
        "command": ["pmtiles", "verify", asset["path"]],
        "binary_label": "pmtiles CLI",
        "executable_size_bytes": executable_size,
        "executable_sha256": executable_hash,
        "exit_code": result.returncode,
        "archive_path": asset["path"],
        "archive_size_bytes": archive_size,
        "archive_sha256": archive_hash,
        "stdout": result.stdout.replace(str(archive_path), asset["path"]).replace(str(executable_path), "pmtiles")[-4000:],
        "stderr": result.stderr.replace(str(archive_path), asset["path"]).replace(str(executable_path), "pmtiles")[-4000:],
    }
    if result.returncode != 0:
        raise FinalizeError(f"pmtiles verify failed for {asset['id']} with exit code {result.returncode}")
    if (archive_size, archive_hash) != (asset.get("size_bytes"), asset.get("sha256")):
        raise FinalizeError(f"archive changed while pmtiles verify ran: {asset['id']}")
    return evidence


def _inventory(package: Path, *, allow_unlisted: set[str] | None = None) -> dict[str, dict[str, Any]]:
    allow_unlisted = allow_unlisted or set()
    result: dict[str, dict[str, Any]] = {}
    for current, dirs, names in os.walk(package, followlinks=False):
        base = Path(current)
        for name in dirs:
            if (base / name).is_symlink():
                raise FinalizeError(f"display package contains a symlink directory: {(base / name).relative_to(package)}")
        for name in names:
            path = base / name
            rel = path.relative_to(package).as_posix()
            _safe_rel(rel, "package path")
            if path.is_symlink() or not path.is_file():
                raise FinalizeError(f"display package contains an unsafe file: {rel}")
            if rel == "manifest.json":
                continue
            size, digest = _digest(path)
            result[rel] = {"size_bytes": size, "sha256": digest}
    return result


def _check_file_declarations(package: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise FinalizeError("provisional manifest files must be a non-empty object")
    declared: dict[str, dict[str, Any]] = {}
    for raw_path, raw_info in files.items():
        rel = _safe_rel(raw_path, "manifest file path")
        if rel == "manifest.json" or not isinstance(raw_info, dict):
            raise FinalizeError(f"invalid manifest file declaration: {rel}")
        size, digest = raw_info.get("size_bytes"), raw_info.get("sha256")
        if type(size) is not int or size < 0 or not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise FinalizeError(f"invalid manifest size/hash declaration: {rel}")
        path = _regular_no_symlink(package, rel, "manifest file")
        actual_size, actual_hash = _digest(path)
        if (actual_size, actual_hash) != (size, digest):
            raise FinalizeError(f"manifest file hash/size mismatch: {rel}")
        declared[rel] = {"size_bytes": size, "sha256": digest}
    actual = _inventory(package)
    if set(actual) != set(declared):
        raise FinalizeError(f"provisional manifest file inventory differs from package: missing={sorted(set(actual)-set(declared))}, stale={sorted(set(declared)-set(actual))}")
    return declared


def _match_build_report(package: Path, asset: dict[str, Any], report: dict[str, Any]) -> None:
    if not isinstance(asset.get("path"), str) or not asset["path"].lower().endswith(".pmtiles"):
        raise FinalizeError(f"display asset does not name a PMTiles archive: {asset.get('id')}")
    _safe_rel(asset.get("path"), "PMTiles asset path")
    source_asset = asset.get("source_asset")
    if not isinstance(source_asset, dict):
        raise FinalizeError(f"display asset source_asset binding is missing: {asset.get('id')}")
    _safe_rel(source_asset.get("path"), "source asset path")
    if (type(asset.get("size_bytes")) is not int or asset["size_bytes"] < 0
            or not isinstance(asset.get("sha256"), str) or not SHA256_RE.fullmatch(asset["sha256"])
            or type(source_asset.get("size_bytes")) is not int or source_asset["size_bytes"] < 0
            or not isinstance(source_asset.get("sha256"), str) or not SHA256_RE.fullmatch(source_asset["sha256"])):
        raise FinalizeError(f"display asset source/archive hash and size bindings are invalid: {asset.get('id')}")
    archive_path = _regular_no_symlink(package, asset["path"], "PMTiles asset")
    if _digest(archive_path) != (asset["size_bytes"], asset["sha256"]):
        raise FinalizeError(f"PMTiles asset size/SHA-256 mismatch: {asset['id']}")
    fields = {
        "layer": asset.get("source_layer"),
        "geometry_type": asset.get("geometry_type"),
        "id_field": asset.get("id_field"),
        "pmtiles_path": asset.get("path"),
        "pmtiles_sha256": asset.get("sha256"),
        "pmtiles_size_bytes": asset.get("size_bytes"),
        "source_sha256": (asset.get("source_asset") or {}).get("sha256"),
        "source_rows": asset.get("source_rows"),
    }
    for key, expected in fields.items():
        if report.get(key) != expected:
            raise FinalizeError(f"build report {key} mismatch for {asset.get('id')}: expected {expected!r}, got {report.get(key)!r}")
    if report.get("source_path") is None:
        raise FinalizeError(f"asset/build report lacks source identity: {asset.get('id')}")
    _safe_rel(report.get("source_path"), "build report source path")
    source_size = report.get("source_size_bytes")
    # The builder report records source path and SHA, while the immutable source size
    # remains in the manifest's source_asset binding.
    if source_size is not None and source_size != source_asset.get("size_bytes"):
        raise FinalizeError(f"build report source size mismatch for {asset.get('id')}")
    report_source = PurePosixPath(str(report["source_path"])).name
    if report_source != PurePosixPath(str(source_asset.get("path", ""))).name:
        raise FinalizeError(f"build report source path mismatch for {asset.get('id')}")
    declared_attrs = asset.get("attribute_fields")
    if not isinstance(declared_attrs, list) or not declared_attrs or any(not isinstance(name, str) for name in declared_attrs):
        raise FinalizeError(f"display asset attribute_fields are invalid: {asset.get('id')}")
    if report.get("attribute_fields") != declared_attrs:
        raise FinalizeError(f"build report attributes mismatch for {asset.get('id')}")
    id_encoding = asset.get("id_encoding")
    if id_encoding not in ("mvt_feature_id", "mvt_feature_id_and_property"):
        raise FinalizeError(f"unsupported display asset id_encoding for {asset.get('id')}: {id_encoding!r}")
    if report.get("id_encoding") != id_encoding:
        raise FinalizeError(f"build report id_encoding mismatch for {asset.get('id')}")
    id_field = asset.get("id_field")
    if not isinstance(id_field, str) or not id_field:
        raise FinalizeError(f"display asset id_field is missing: {asset.get('id')}")
    if (id_encoding == "mvt_feature_id" and id_field in declared_attrs
            or id_encoding == "mvt_feature_id_and_property" and id_field not in declared_attrs):
        raise FinalizeError(f"ID field conflicts with id_encoding for {asset.get('id')}")
    for field in ("min_zoom", "max_zoom"):
        if report.get(field) != asset.get(field):
            raise FinalizeError(f"build report {field} mismatch for {asset.get('id')}")
    if report.get("min_zoom") != 0 or report.get("max_zoom") != MAX_ZOOM:
        raise FinalizeError(f"build report lacks completed z0–z{MAX_ZOOM} archive evidence for {asset.get('id')}")
    if type(report.get("maxzoom_tiles")) is not int or report["maxzoom_tiles"] <= 0:
        raise FinalizeError(f"build report lacks decoded maxzoom tiles for {asset.get('id')}")
    unique = report.get("unique_source_ids")
    decoded = report.get("maxzoom_ids_decoded")
    accounted = report.get("maxzoom_ids_accounted")
    checked = report.get("maxzoom_ids_attribute_checked")
    missing = report.get("maxzoom_missing_id_count")
    if any(type(value) is not int or value < 0 for value in (unique, decoded, accounted, checked, missing)):
        raise FinalizeError(f"build report lacks complete maxzoom ID accounting for {asset.get('id')}")
    if unique != accounted + missing or decoded != accounted or checked != accounted:
        raise FinalizeError(f"build report maxzoom ID accounting is incomplete for {asset.get('id')}")
    if unique != asset.get("source_rows"):
        raise FinalizeError(f"build report source IDs do not account for every source row: {asset.get('id')}")
    counts = report.get("maxzoom_missing_classification_counts")
    if not isinstance(counts, dict) or any(type(value) is not int or value < 0 for value in counts.values()):
        raise FinalizeError(f"build report lacks maxzoom missing-ID classifications for {asset.get('id')}")
    if sum(counts.values()) != missing or set(counts) - ALLOWED_MISSING_CAUSES:
        raise FinalizeError(f"build report has unclassified or unsupported missing IDs for {asset.get('id')}")
    if counts.get("unexpected_loss", 0):
        raise FinalizeError(f"build report has unexplained maxzoom losses for {asset.get('id')}")
    missing_rel = _safe_rel(report.get("maxzoom_missing_ids_path"), "maxzoom missing-ID file")
    missing_path = _regular_no_symlink(package, missing_rel, "maxzoom missing-ID file")
    missing_bytes = missing_path.read_bytes()
    expected_missing_hash = report.get("maxzoom_missing_ids_sha256")
    if not isinstance(expected_missing_hash, str) or not SHA256_RE.fullmatch(expected_missing_hash) or hashlib.sha256(missing_bytes).hexdigest() != expected_missing_hash:
        raise FinalizeError(f"maxzoom missing-ID file hash mismatch for {asset.get('id')}")
    missing_ids = [line.strip() for line in missing_bytes.decode("utf-8").splitlines() if line.strip()]
    try:
        missing_numeric_ids = [int(value) for value in missing_ids]
    except ValueError as exc:
        raise FinalizeError(f"maxzoom missing-ID file contains a non-integer ID for {asset.get('id')}") from exc
    if (len(missing_ids) != missing or len(set(missing_ids)) != missing
            or any(value < 0 or str(value) != text for value, text in zip(missing_numeric_ids, missing_ids))
            or missing_numeric_ids != sorted(missing_numeric_ids)):
        raise FinalizeError(f"maxzoom missing-ID enumeration does not match report for {asset.get('id')}")
    classification_rel = report.get("maxzoom_missing_classification_path")
    if missing:
        classification_rel = _safe_rel(classification_rel, "maxzoom classification file")
        classification_path = _regular_no_symlink(package, classification_rel, "maxzoom classification file")
        classified: dict[str, str] = {}
        for line_number, line in enumerate(classification_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FinalizeError(f"invalid maxzoom classification JSONL at line {line_number}") from exc
            if (not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 0
                    or row.get("cause") not in ALLOWED_MISSING_CAUSES):
                raise FinalizeError(f"invalid maxzoom missing-ID classification at line {line_number}")
            fid = str(row["id"])
            if fid in classified:
                raise FinalizeError(f"duplicate missing-ID classification for {fid}")
            classified[fid] = row["cause"]
        if set(classified) != set(missing_ids):
            raise FinalizeError(f"maxzoom classifications do not enumerate the missing-ID file for {asset.get('id')}")
        observed_counts: dict[str, int] = {}
        for cause in classified.values():
            observed_counts[cause] = observed_counts.get(cause, 0) + 1
        if observed_counts != counts:
            raise FinalizeError(f"maxzoom missing-ID classifications differ from report for {asset.get('id')}")
    bounds = report.get("pmtiles_bounds")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in bounds)
            or bounds[0] > bounds[2] or bounds[1] > bounds[3]):
        raise FinalizeError(f"build report lacks PMTiles structure bounds for {asset.get('id')}")


def _validate_geometry_report(report: dict[str, Any], asset: dict[str, Any], build_report: dict[str, Any]) -> None:
    expected = {
        "asset_id": asset["id"],
        "source_asset_path": asset["source_asset"]["path"],
        "source_size_bytes": asset["source_asset"]["size_bytes"],
        "source_sha256": asset["source_asset"]["sha256"],
        "pmtiles_asset_path": asset["path"],
        "pmtiles_size_bytes": asset["size_bytes"],
        "pmtiles_sha256": asset["sha256"],
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise FinalizeError(f"geometry report {key} mismatch for {asset['id']}")
    if report.get("passed") is not True or report.get("failures") != []:
        raise FinalizeError(f"geometry report did not pass for {asset['id']}")
    tolerance = report.get("tolerance_m")
    if not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance <= 0 or tolerance > MAX_GEOMETRY_METRES:
        raise FinalizeError(f"geometry report tolerance exceeds {MAX_GEOMETRY_METRES:g} m for {asset['id']}")
    sample_rule = report.get("sample_rule")
    required_rule = {"global_ids": 32, "ids_per_region": 8, "max_bbox_tiles": 64,
                     "regional_filter": "source bbox intersects frozen window"}
    if not isinstance(sample_rule, dict) or any(sample_rule.get(k) != v for k, v in required_rule.items()):
        raise FinalizeError(f"geometry report sample rule/limits differ from frozen criteria for {asset['id']}")
    selection = sample_rule.get("selection")
    if (not isinstance(selection, str) or "lowest eligible IDs" not in selection
            or "<=64 bbox tiles cap" not in selection):
        raise FinalizeError(f"geometry report sample selection rule differs from frozen criteria for {asset['id']}")
    groups = report.get("sample_groups")
    if not isinstance(groups, dict) or set(groups) != set(REGIONS):
        raise FinalizeError(f"geometry report lacks required global/regional samples for {asset['id']}")
    for region in REGIONS:
        values = groups[region]
        expected_count = 32 if region == "global" else 8
        if (not isinstance(values, list) or any(type(value) is not int or value < 0 for value in values)
                or len(values) != expected_count or len(set(values)) != expected_count):
            raise FinalizeError(f"geometry report {region} sample count is incomplete for {asset['id']}")
    samples = report.get("samples")
    union_ids = {value for values in groups.values() for value in values}
    if not isinstance(samples, list) or len(samples) != len(union_ids):
        raise FinalizeError(f"geometry report sample details are incomplete for {asset['id']}")
    seen: set[Any] = set()
    distances: list[float] = []
    for sample in samples:
        if (not isinstance(sample, dict) or type(sample.get("id")) is not int
                or sample.get("id") not in union_ids or sample.get("id") in seen):
            raise FinalizeError(f"geometry report has duplicate or unexpected sample IDs for {asset['id']}")
        seen.add(sample["id"])
        if sample.get("failures") != []:
            raise FinalizeError(f"geometry sample has failures for {asset['id']}")
        distance = sample.get("distance_m")
        if not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance < 0 or distance > min(tolerance, MAX_GEOMETRY_METRES):
            raise FinalizeError(f"geometry sample exceeds the declared tolerance for {asset['id']}")
        distances.append(float(distance))
    if seen != union_ids:
        raise FinalizeError(f"geometry report omits sampled IDs for {asset['id']}")
    maximum = report.get("max_distance_m")
    if not isinstance(maximum, (int, float)) or not math.isfinite(maximum) or maximum != max(distances) or maximum > MAX_GEOMETRY_METRES:
        raise FinalizeError(f"geometry report maximum distance is inconsistent for {asset['id']}")
    if report.get("sampled_unique_ids") != len(union_ids) or report.get("source_rows_scanned") != asset.get("source_rows"):
        raise FinalizeError(f"geometry report source sample counts mismatch for {asset['id']}")
    if report.get("id_encoding") != asset.get("id_encoding") or report.get("id_encoding") != build_report.get("id_encoding"):
        raise FinalizeError(f"geometry report ID encoding differs from asset/build report for {asset['id']}")


def _validate_browser_case(case: dict[str, Any], asset: dict[str, Any], browser: dict[str, Any], region: str) -> None:
    if case.get("layer_id") != asset.get("id"):
        raise FinalizeError(f"browser case identity mismatch for {asset.get('id')}/{region}")
    if case.get("format") != "pmtiles" or case.get("status") != "passed" or case.get("region") != region:
        raise FinalizeError(f"browser case did not pass for {asset.get('id')}/{region}")
    if case.get("source_sha256") != asset.get("sha256") or case.get("source_size_bytes") != asset.get("size_bytes"):
        raise FinalizeError(f"browser case is not bound to the PMTiles archive for {asset.get('id')}/{region}")
    viewer = case.get("viewer")
    if not isinstance(viewer, dict) or viewer.get("phase") != "ready" or type(viewer.get("feature_count")) is not int or viewer["feature_count"] <= 0:
        raise FinalizeError(f"browser case has no visible features for {asset.get('id')}/{region}")
    ceiling = browser.get("transfer_ceiling_bytes")
    body_bytes = case.get("response_body_bytes")
    if type(ceiling) is not int or ceiling > MAX_BROWSER_BYTES or type(body_bytes) is not int or body_bytes < 0 or body_bytes > MAX_BROWSER_BYTES:
        raise FinalizeError(f"browser case exceeds {MAX_BROWSER_BYTES} byte transfer ceiling for {asset.get('id')}/{region}")
    requests = case.get("requests")
    if not isinstance(requests, list):
        raise FinalizeError(f"browser case lacks request evidence for {asset.get('id')}/{region}")
    gets = [row for row in requests if isinstance(row, dict) and row.get("method") == "GET"]
    if not gets:
        raise FinalizeError(f"browser case made no ranged data GET for {asset.get('id')}/{region}")
    archive_size = asset["size_bytes"]
    archive_gets = 0
    total_body = 0
    for row in gets:
        range_header = row.get("range")
        content_range = row.get("content_range")
        length = row.get("content_length")
        if (row.get("status") != 206 or not row.get("completed") or row.get("cors") != "*"
                or not isinstance(range_header, str) or not range_header.startswith("bytes=")
                or not isinstance(content_range, str) or type(length) is not int or length < 0):
            raise FinalizeError(f"browser GET is not a completed cross-origin HTTP 206 range for {asset.get('id')}/{region}")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
        requested = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
        if (not match or not requested or int(match.group(1)) != int(requested.group(1))
                or int(match.group(2)) != int(requested.group(2))
                or int(match.group(2)) - int(match.group(1)) + 1 != length):
            raise FinalizeError(f"browser GET range/Content-Range mismatch for {asset.get('id')}/{region}")
        object_size = row.get("object_size_bytes")
        if type(object_size) is not int or int(match.group(3)) != object_size:
            raise FinalizeError(f"browser GET has no bound object size for {asset.get('id')}/{region}")
        if int(match.group(1)) == 0 and int(match.group(2)) == object_size - 1:
            raise FinalizeError(f"browser GET transferred the whole object for {asset.get('id')}/{region}")
        if object_size == archive_size:
            archive_gets += 1
        total_body += length
    if not archive_gets:
        raise FinalizeError(f"browser case did not range-read the bound PMTiles archive for {asset.get('id')}/{region}")
    if total_body != body_bytes:
        raise FinalizeError(f"browser case response-body total does not match GET evidence for {asset.get('id')}/{region}")
    if case.get("page_errors") or case.get("external_requests"):
        raise FinalizeError(f"browser case contains page or external-request errors for {asset.get('id')}/{region}")
    note = case.get("all_attributes_note")
    observed_count = case.get("all_attribute_count")
    expected_count = case.get("expected_source_attribute_count")
    if (not isinstance(note, str) or not note.startswith("All source attributes")
            or type(observed_count) is not int or observed_count <= 0
            or type(expected_count) is not int or expected_count <= 0
            or observed_count != expected_count):
        raise FinalizeError(f"browser case did not complete all-source-attributes lookup for {asset.get('id')}/{region}")
    if case.get("dataset_id") == "lakeatlas" and case.get("layer_switch_lookup_passed") is not True:
        raise FinalizeError(f"browser case did not pass LakeATLAS layer-switch lookup for {asset.get('id')}/{region}")


def _final_readme(manifest: dict[str, Any], report_paths: list[str], report_data: dict[str, dict[str, Any]],
                  build_reports: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# {manifest.get('dataset_id')} display package", "",
        f"Display release: `{manifest.get('display_release')}`; analytical release: `{manifest.get('analytic_release')}`.",
        "Status: prepared local display derivatives. This finalization does not claim new GEE checks, scientific validation, public hosting, or a clean rebuild of the production archive.",
        "",
        f"Attribution: {manifest.get('attribution') or 'See the analytical release metadata.'}",
        f"Analytical release metadata and full data/field-license notices: [release manifest](../../releases/{manifest.get('analytic_release')}/manifest.json).",
        "",
        "The pinned analytical GeoParquet remains authoritative for complete field lookup. PMTiles simplify and quantize geometry for display.",
        "",
        "## Layers", "",
    ]
    for asset in manifest["assets"]:
        lines.append(f"- `{asset['id']}`: [{asset['path']}]({asset['path']}) — {asset['geometry_type']}, source layer `{asset['source_layer']}`, z{asset['min_zoom']}–z{asset['max_zoom']}; source `{asset['source_asset']['path']}` SHA-256 `{asset['source_asset']['sha256']}`.")
        lines.append(f"  - Style: [{asset['style_path']}]({asset['style_path']})")
        report = build_reports[asset["id"]]
        source_rows = report["source_rows"]
        source_ids = report["unique_source_ids"]
        accounted = report["maxzoom_ids_accounted"]
        missing = report["maxzoom_missing_id_count"]
        lines.append(f"  - Source rows: {source_rows}; unique source IDs: {source_ids}; decoded and attribute-checked IDs at maximum zoom: {accounted}.")
        if missing:
            lines.append(f"  - {missing} source IDs are absent at maximum zoom and have the explicit classifications `{report.get('maxzoom_missing_classification_counts', {})}`; this package does not claim those IDs are covered.")
        else:
            lines.append("  - No missing source IDs were reported at maximum zoom.")
    lines.extend(["", "## Finalization evidence", "", "All linked reports are local evidence files included in the complete package inventory."])
    for path in sorted(report_paths):
        lines.append(f"- [{PurePosixPath(path).name}]({path}) (SHA-256 `{report_data[path]['sha256']}`)")
    lines.extend([
        "", "The finalizer reruns `pmtiles verify` and records the executable and archive hashes. Builder reports record maximum-zoom ID/attribute accounting. Explicitly supplied geometry reports establish the sampled, bounded Web Mercator display tolerance only. Browser reports establish the tested global and North America views, nonzero rendering, ranged HTTP 206 reads, and the 128 MiB response-body limit.",
        "",
    ])
    return "\n".join(lines)


def finalize_package(
    package: Path,
    geometry_reports: dict[str, Path],
    browser_report_path: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    input_root = repo_root.expanduser().resolve() if repo_root is not None else Path.cwd().resolve()
    package = package.expanduser()
    package = (package if package.is_absolute() else input_root / package).absolute()
    browser_report_path = browser_report_path.expanduser()
    browser_report_path = browser_report_path if browser_report_path.is_absolute() else input_root / browser_report_path
    geometry_reports = {
        key: path.expanduser() if path.expanduser().is_absolute() else input_root / path.expanduser()
        for key, path in geometry_reports.items()
    }
    if package.is_symlink() or not package.is_dir():
        raise FinalizeError(f"package root is missing or a symlink: {package}")
    manifest_path = package / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise FinalizeError("package requires a regular manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise FinalizeError(f"invalid package manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise FinalizeError("package manifest must be an object")
    if manifest.get("status") == "prepared":
        raise FinalizeError("refusing already prepared display package")
    if manifest.get("status") != "provisional":
        raise FinalizeError(f"package status must be provisional, got {manifest.get('status')!r}")
    dataset_id, release, analytic_release = (manifest.get("dataset_id"), manifest.get("display_release"), manifest.get("analytic_release"))
    if not all(isinstance(value, str) and value for value in (dataset_id, release, analytic_release)):
        raise FinalizeError("manifest dataset_id, display_release, and analytic_release are required")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise FinalizeError("manifest assets must be a non-empty array")
    asset_by_id: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("id"), str) or not asset["id"] or asset["id"] in asset_by_id:
            raise FinalizeError("manifest asset IDs must be unique non-empty strings")
        asset_by_id[asset["id"]] = asset
    if set(geometry_reports) != set(asset_by_id):
        raise FinalizeError(f"geometry reports must cover every asset exactly: expected={sorted(asset_by_id)}, got={sorted(geometry_reports)}")

    declared_files = _check_file_declarations(package, manifest)
    # Build reports are preserved in place by the builder and form the completion
    # record for pmtiles verify, metadata, maxzoom ID decoding, and attributes.
    build_reports: dict[str, dict[str, Any]] = {}
    for asset_id, asset in asset_by_id.items():
        if not LAYER_ID_RE.fullmatch(asset_id):
            raise FinalizeError(f"invalid layer ID: {asset_id}")
        source_layer = asset.get("source_layer")
        build_rel = _safe_rel(f"reports/{source_layer}.build-report.json", "build report path")
        build_path = _regular_no_symlink(package, build_rel, "builder report")
        build_report = _json(build_path, "builder report")
        _match_build_report(package, asset, build_report)
        build_reports[asset_id] = build_report
    for asset_id, report_path in geometry_reports.items():
        if not isinstance(report_path, Path):
            report_path = Path(report_path)
        report = _json(report_path, "geometry report")
        _validate_geometry_report(report, asset_by_id[asset_id], build_reports[asset_id])

    browser = _json(browser_report_path, "browser report")
    if browser.get("schema_version") != 1 or browser.get("status") != "passed":
        raise FinalizeError("browser report is not a completed passing report")
    cases = browser.get("cases")
    if not isinstance(cases, list):
        raise FinalizeError("browser report cases must be an array")
    browser_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise FinalizeError("browser report case must be an object")
        if any(not isinstance(case.get(key), str) for key in ("dataset_id", "layer_id", "region")):
            raise FinalizeError("browser report case identity must use string dataset/layer/region values")
        identity = (case.get("dataset_id"), case.get("layer_id"), case.get("region"))
        if identity in browser_by_identity:
            raise FinalizeError(f"duplicate browser report case: {identity}")
        browser_by_identity[identity] = case
    for asset_id, asset in asset_by_id.items():
        for region in ("global", "north_america"):
            case = browser_by_identity.get((dataset_id, asset_id, region))
            if case is None:
                raise FinalizeError(f"browser report is missing {asset_id}/{region} case")
            _validate_browser_case(case, asset, browser, region)

    verification_evidence = {
        asset_id: _verify_archive(asset, package / asset["path"])
        for asset_id, asset in asset_by_id.items()
    }

    report_sources: dict[str, bytes] = {}
    report_data: dict[str, dict[str, Any]] = {}
    report_paths: list[str] = []
    for asset_id, asset in asset_by_id.items():
        build_rel = f"reports/{asset['source_layer']}.build-report.json"
        report_paths.append(build_rel)
        report_data[build_rel] = declared_files[build_rel]
    for asset_id, report_path in geometry_reports.items():
        target = f"reports/finalization/geometry/{asset_id}.json"
        data = report_path.read_bytes()
        report_sources[target] = data
        size, digest = _digest_bytes(data)
        report_data[target] = {"size_bytes": size, "sha256": digest}
        report_paths.append(target)
    for asset_id, evidence in verification_evidence.items():
        target = f"reports/finalization/pmtiles-verify/{asset_id}.json"
        data = (json.dumps(evidence, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
        report_sources[target] = data
        size, digest = _digest_bytes(data)
        report_data[target] = {"size_bytes": size, "sha256": digest}
        report_paths.append(target)
    browser_target = "reports/finalization/browser-validation.json"
    browser_bytes = browser_report_path.read_bytes()
    report_sources[browser_target] = browser_bytes
    size, digest = _digest_bytes(browser_bytes)
    report_data[browser_target] = {"size_bytes": size, "sha256": digest}
    report_paths.append(browser_target)

    # Treat an existing identical target as a repeat of an interrupted local
    # finalization; differing content is never overwritten silently.
    for target, data in report_sources.items():
        if os.path.lexists(package / target):
            old = _regular_no_symlink(package, target, "existing finalization report")
            if old.read_bytes() != data:
                raise FinalizeError(f"existing finalization report conflicts with current input: {target}")
    old_inventory = _inventory(package)
    expected_existing = set(declared_files) | {target for target in report_sources if target in old_inventory}
    if set(old_inventory) != expected_existing:
        raise FinalizeError("package contains files outside its manifest and finalization report inputs")

    readme_rel = "README.md"
    readme_text = _final_readme(manifest, report_paths, report_data, build_reports)
    readme_data = readme_text.encode("utf-8")
    old_readme = (package / readme_rel).read_bytes() if (package / readme_rel).is_file() else None
    created_targets: list[Path] = []
    readme_changed = False
    try:
        for target, data in report_sources.items():
            path = package / target
            if path.is_file():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, data)
            created_targets.append(path)
        if old_readme != readme_data:
            _atomic_write(package / readme_rel, readme_data)
            readme_changed = True
        final_files = _inventory(package)
        if set(final_files) != set(declared_files) | set(report_sources):
            raise FinalizeError("final package inventory is incomplete after report installation")
        for rel, declaration in declared_files.items():
            if rel != readme_rel and final_files.get(rel) != declaration:
                raise FinalizeError(f"package file changed during finalization: {rel}")
        for asset in assets:
            if final_files.get(asset["path"]) != {"size_bytes": asset["size_bytes"], "sha256": asset["sha256"]}:
                raise FinalizeError(f"PMTiles asset changed during finalization: {asset['id']}")
        finalized = dict(manifest)
        finalized["files"] = final_files
        # This atomic replacement is the only operation that changes status.
        finalized["status"] = "prepared"
        _atomic_write(manifest_path, (json.dumps(finalized, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode())
        return finalized
    except Exception:
        for path in reversed(created_targets):
            path.unlink(missing_ok=True)
        for directory in sorted((path for path in package.rglob("*") if path.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        if readme_changed:
            if old_readme is None:
                (package / readme_rel).unlink(missing_ok=True)
            else:
                _atomic_write(package / readme_rel, old_readme)
        raise


def _digest_bytes(data: bytes) -> tuple[int, str]:
    return len(data), hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _parse_geometry_report(raw: str) -> tuple[str, Path]:
    layer_id, separator, path = raw.partition("=")
    if not separator or not LAYER_ID_RE.fullmatch(layer_id) or not path:
        raise argparse.ArgumentTypeError("--geometry-report must be LAYER_ID=PATH")
    return layer_id, Path(path).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="provisional display package directory")
    parser.add_argument("--geometry-report", action="append", required=True, type=_parse_geometry_report,
                        metavar="LAYER_ID=PATH", help="passing bound geometry report; repeat once per asset")
    parser.add_argument("--browser-report", required=True, type=Path, help="completed browser-validation.json")
    parser.add_argument("--repo-root", type=Path, default=REPO,
                        help="base directory for relative package and evidence paths; no reports are auto-discovered")
    args = parser.parse_args(argv)
    try:
        reports = dict(args.geometry_report)
        if len(reports) != len(args.geometry_report):
            raise FinalizeError("duplicate --geometry-report layer ID")
        manifest = finalize_package(args.package, reports, args.browser_report, args.repo_root)
    except (FinalizeError, OSError) as exc:
        print(f"display finalize: {exc}", file=sys.stderr)
        return 2
    print(f"Prepared {manifest['dataset_id']}/{manifest['display_release']} with {len(manifest['assets'])} layers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
