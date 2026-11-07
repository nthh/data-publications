#!/usr/bin/env python3
"""Finalize a new, checksum-bound local GRWL raw PMTiles package.

The provisional display package and analytical package are read-only inputs.
This tool builds a separate immutable display package and writes ``prepared``
only after source-oracle, browser, PMTiles and complete-inventory checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
CONTROL_POLICY_PATH = ROOT / "research/grwl-raw-release-20261102/global-display-diagnostics-r1/control-policy-r2.json"
EXPECTED_TILES = 829
EXPECTED_ROWS = 64_572_998
EXPECTED_RELEASE = "raw-v01.01-local-r1"
EXPECTED_ARCHIVE_SHA256 = "78072f67991b0cf9eb3373c7a9c314c0da826857c698dd03d20421b2d0d3bbec"
DISPLAY_RELEASE = "raw-v01.01-display-r1"
ASSET_ID = "grwl-raw-display"
SOURCE_ASSET_ID = "grwl-raw-observations"
MAX_GEOMETRY_METRES = 30.0
MAX_CASE_BYTES = 128 * 1024 * 1024
ALLOWED_MISSING_CAUSES = {"source_empty", "zero_length", "zero_area", "quantization_collapse"}
KNOWN_CASE_IDS = {
    "known-summary-11839", "known-summary-13164", "known-summary-15394",
    "known-summary-15397", "known-summary-15450",
}
GLOBAL_CASE_IDS = {
    "global-north_america", "global-south_america", "global-africa",
    "global-europe", "global-asia", "global-oceania",
}
KNOWN_CONTEXTS = {"known-summary-11839": "grwl_11839", "known-summary-13164": "grwl_13164",
                  "known-summary-15394": "grwl_15394", "known-summary-15397": "grwl_15397",
                  "known-summary-15450": "grwl_15450"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RANGE_RE = re.compile(r"^bytes=(\d+)-(\d+)$")
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
TILE_RE = re.compile(r"^[A-Z]{2}[0-9]{2}$")
DISPLAY_RUN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PROVISIONAL_ASSET_REL = "assets/grwl-raw.pmtiles"
ANALYTIC_ASSET_REL = f"assets/{SOURCE_ASSET_ID}.parquet"
VERIFICATION_WORKFLOW_FILES = (
    "datasets/grwl-raw/finalize_display.py",
    "datasets/grwl-raw/validate_display.py",
    "datasets/grwl-raw/native_quantization.py",
    "datasets/grwl-raw/prepare_preview.py",
    "datasets/grwl/validate_display_wrap.py",
    "scripts/cloud_viewer/raw-browser-check.mjs",
    "scripts/cloud_viewer/build.mjs",
    "scripts/cloud_viewer/fetch-assets.mjs",
    "scripts/cloud_viewer/prepare.py",
    "scripts/cloud_viewer/serve.py",
    "scripts/cloud_viewer/run.py",
    "scripts/cloud_viewer/runtime-assets.json",
    "scripts/cloud_viewer/src/app.js",
    "scripts/cloud_viewer/src/core.js",
    "scripts/cloud_viewer/src/parquet.worker.js",
    "scripts/cloud_viewer/src/index.html",
    "scripts/cloud_viewer/src/style.css",
    "scripts/cloud_viewer/src/land-source.json",
    "scripts/cloud_viewer/src/land.geojson",
    "research/grwl-raw-release-20261102/prepare_global_browser_controls.py",
    "research/grwl-raw-release-20261102/criteria.json",
    "research/grwl-raw-release-20261102/display-policy.json",
    "research/grwl-raw-release-20261102/global-criteria.json",
    "research/grwl-raw-release-20261102/global-browser-policy.json",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/control-policy.json",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/control-policy-r2.json",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/source-compactness-r1.json",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/native-quantization-diagnostic.json",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/native-quantization-controls.geojson",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/native-quantization-controls.pmtiles",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/native-threshold-controls.geojson",
    "research/grwl-raw-release-20261102/global-display-diagnostics-r1/native-threshold-controls.pmtiles",
    "research/pmtiles-all-20261102/criteria.json",
    "scripts/display_tools/pyproject.toml",
    "scripts/display_tools/uv.lock",
    "scripts/cloud_viewer/package.json",
    "scripts/cloud_viewer/package-lock.json",
)


class FinalizeError(ValueError):
    """A raw GRWL finalization invariant failed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FinalizeError(f"{label} is missing, not a regular file, or is a symlink: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise FinalizeError(f"Cannot read {label} JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalizeError(f"{label} must be a JSON object")
    return value


def _hash_size(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _tile_code(tile: str) -> int:
    if not TILE_RE.fullmatch(tile):
        raise FinalizeError(f"Invalid source tile code {tile!r}")
    return ((ord(tile[0]) - 65) * 26 + ord(tile[1]) - 65) * 100 + int(tile[2:])


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise FinalizeError(f"{label} must be a safe POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") or part.startswith(".") for part in value.split("/")):
        raise FinalizeError(f"Unsafe {label}: {value!r}")
    return path.as_posix()


def _source_identity(manifest: dict[str, Any], parquet: Path, expected_tiles: int,
                     expected_rows: int) -> tuple[list[dict[str, Any]], str, int]:
    if manifest.get("source_product") != "GRWL_vector_V01.01":
        raise FinalizeError("Analytical manifest source product is not GRWL_vector_V01.01")
    rows, tiles = manifest.get("rows"), manifest.get("tiles")
    if rows != expected_rows or not isinstance(tiles, list) or len(tiles) != expected_tiles:
        raise FinalizeError("Analytical manifest does not meet the required global rows and tile count")
    names = [item.get("tile") if isinstance(item, dict) else None for item in tiles]
    if names != sorted(names) or len(set(names)) != expected_tiles or any(not isinstance(name, str) or not TILE_RE.fullmatch(name) for name in names):
        raise FinalizeError("Analytical manifest tiles must be unique, valid and sorted")
    if sum(item.get("records", -1) for item in tiles) != expected_rows:
        raise FinalizeError("Per-tile source row counts differ from global row count")
    if sum(item.get("parts", -1) for item in tiles) != manifest.get("parts"):
        raise FinalizeError("Per-tile source part counts differ from analytical manifest")
    actual_hash = _sha256(parquet)
    if actual_hash != manifest.get("parquet_sha256"):
        raise FinalizeError("Actual analytical Parquet SHA-256 differs from source manifest")
    try:
        footer_rows = pq.ParquetFile(parquet).metadata.num_rows
    except Exception as exc:
        raise FinalizeError(f"Cannot read analytical Parquet footer: {exc}") from exc
    if footer_rows != expected_rows:
        raise FinalizeError("Analytical Parquet footer row count differs from global source count")
    return tiles, actual_hash, parquet.stat().st_size


def _validate_analytic_package(package: Path, parquet_sha256: str, parquet_size: int,
                               expected_rows: int, fidelity_sha256: str) -> dict[str, Any]:
    manifest_path = package / "manifest.json"
    receipt_path = package / "package-receipt.json"
    binding_path = package / "evidence/package-binding.json"
    verification_path = package / "evidence/final-package-verification.json"
    manifest = _json(manifest_path, "analytic package manifest")
    receipt = _json(receipt_path, "analytic package receipt")
    binding = _json(binding_path, "analytic package binding")
    verification = _json(verification_path, "analytic package final verification")
    manifest_sha = _sha256(manifest_path)
    if (manifest.get("dataset_id") != "grwl-raw" or manifest.get("release_id") != EXPECTED_RELEASE
            or manifest.get("status") != "local-candidate" or manifest.get("publicly_published") is not False):
        raise FinalizeError("Analytic package identity/status is not the expected unpublished local release")
    if (receipt.get("status") != "packaged_locally_not_published" or receipt.get("dataset_id") != "grwl-raw"
            or receipt.get("release_id") != EXPECTED_RELEASE or receipt.get("manifest_sha256") != manifest_sha
            or receipt.get("publicly_published") is not False or receipt.get("registry_submitted") is not False):
        raise FinalizeError("Analytic package receipt is missing, failed, or not bound to this manifest")
    if receipt.get("package_binding_sha256") != _sha256(binding_path):
        raise FinalizeError("Analytic package receipt does not bind package-binding.json")
    if binding.get("manifest_sha256") != manifest_sha:
        raise FinalizeError("Analytic package binding refers to a different manifest")
    if (verification.get("status") != "passed" or receipt.get("final_verification_sha256") != _sha256(verification_path)):
        raise FinalizeError("Analytic package final verification is not passed or not receipt-bound")
    provenance_files = {}
    for key in ("source_attribution", "source_license", "data_license", "source_fidelity_report", "clean_rebuild_report"):
        reference = manifest.get(key)
        if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
            raise FinalizeError(f"Prepared analytic package lacks {key} provenance")
        rel = _safe_relative(reference["path"], f"analytic package {key} path")
        path = package / rel
        if path.is_symlink() or not path.is_file() or _sha256(path) != reference.get("sha256"):
            raise FinalizeError(f"Prepared analytic package {key} report is missing or not manifest-bound")
        if key == "source_fidelity_report" and reference["sha256"] != fidelity_sha256:
            raise FinalizeError("Prepared analytic package source-fidelity report differs from supplied normalized report")
        provenance_files[rel] = {"path": path, "sha256": reference["sha256"], "size_bytes": path.stat().st_size}
    workflow = manifest.get("workflow_files")
    if not isinstance(workflow, dict) or not workflow:
        raise FinalizeError("Prepared analytic package lacks pinned workflow code/lock identities")
    workflow_hashes = {key: value.get("sha256") for key, value in workflow.items() if isinstance(value, dict)}
    if len(workflow_hashes) != len(workflow) or binding.get("workflow_sha256") != workflow_hashes:
        raise FinalizeError("Analytic package binding differs from pinned workflow code/lock identities")
    for rel, info in workflow.items():
        rel = _safe_relative(rel, "analytic workflow path")
        if not isinstance(info, dict) or not isinstance(info.get("package_path"), str):
            raise FinalizeError(f"Malformed analytic workflow pin for {rel}")
        package_rel = _safe_relative(info["package_path"], "packaged analytic workflow path")
        path = package / package_rel
        if (path.is_symlink() or not path.is_file() or _sha256(path) != info.get("sha256")
                or info.get("bytes") != path.stat().st_size):
            raise FinalizeError(f"Packaged analytic workflow bytes differ from manifest pin: {rel}")
        provenance_files[package_rel] = {"path": path, "sha256": info["sha256"],
                                         "size_bytes": path.stat().st_size}
    evidence_root = package / "evidence"
    for current, dirs, names in os.walk(evidence_root, followlinks=False):
        base = Path(current)
        for dirname in dirs:
            if (base / dirname).is_symlink():
                raise FinalizeError("Analytic package evidence contains a symlink directory")
        for name in names:
            path = base / name
            rel = path.relative_to(package).as_posix()
            _safe_relative(rel, "analytic package evidence path")
            if path.is_symlink() or not path.is_file():
                raise FinalizeError(f"Analytic package evidence contains an unsafe file: {rel}")
            provenance_files[rel] = {"path": path, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
    attribution_ref = manifest["source_attribution"]
    source_license_ref = manifest["source_license"]
    data_license_ref = manifest["data_license"]
    attribution = _json(package / attribution_ref["path"], "analytic source attribution")
    source_license = _json(package / source_license_ref["path"], "analytic source license")
    data_license = _json(package / data_license_ref["path"], "analytic data license")
    for report_key, binding_key in (("source_attribution", "source_attribution_sha256"),
                                    ("source_fidelity_report", "source_fidelity_report_sha256"),
                                    ("clean_rebuild_report", "clean_rebuild_report_sha256")):
        if binding.get(binding_key) != manifest[report_key]["sha256"]:
            raise FinalizeError(f"Analytic package binding omits or changes {report_key}")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise FinalizeError("Analytic package manifest has no asset list")
    matches = [item for item in assets if isinstance(item, dict) and item.get("asset_id") == SOURCE_ASSET_ID]
    if len(matches) != 1:
        raise FinalizeError("Analytic package must contain exactly one GRWL raw observations asset")
    asset = matches[0]
    if (asset.get("href") != ANALYTIC_ASSET_REL or asset.get("sha256") != parquet_sha256
            or asset.get("size_bytes") != parquet_size or asset.get("row_count") != expected_rows
            or binding.get("asset_sha256", {}).get(SOURCE_ASSET_ID) != parquet_sha256):
        raise FinalizeError("Analytic package asset does not match the global source Parquet")
    packaged_parquet = package / ANALYTIC_ASSET_REL
    if not packaged_parquet.is_file() or packaged_parquet.is_symlink():
        raise FinalizeError("Prepared analytic package asset file is missing or unsafe")
    if (packaged_parquet.stat().st_size, _sha256(packaged_parquet)) != (parquet_size, parquet_sha256):
        raise FinalizeError("Prepared analytic package Parquet bytes differ from source input")
    return {"manifest_sha256": manifest_sha, "release_id": manifest["release_id"],
            "asset_id": SOURCE_ASSET_ID, "asset_path": ANALYTIC_ASSET_REL,
            "asset_sha256": parquet_sha256, "asset_size_bytes": parquet_size,
            "manifest_path": str(manifest_path.resolve()), "receipt_sha256": _sha256(receipt_path),
            "package_binding_sha256": _sha256(binding_path),
            "final_verification_sha256": _sha256(verification_path),
            "receipt_path": receipt_path, "binding_path": binding_path,
            "verification_path": verification_path,
            "provenance_files": provenance_files, "source_attribution": attribution,
            "source_license": source_license, "data_license": data_license}


def _validate_fidelity(fidelity: dict[str, Any], source_manifest_path: Path,
                       source_manifest: dict[str, Any], source_sha256: str,
                       source_size: int, expected_tiles: int, expected_rows: int) -> dict[str, Any]:
    if fidelity.get("status") != "passed":
        raise FinalizeError("Normalized source-fidelity report is not passed")
    assets = fidelity.get("assets")
    expected_asset = {"asset_id": SOURCE_ASSET_ID, "sha256": source_sha256, "size_bytes": source_size}
    if assets != [expected_asset]:
        raise FinalizeError("Normalized source-fidelity report does not bind exact Parquet bytes")
    evidence = fidelity.get("evidence")
    source_report = evidence.get("source_report") if isinstance(evidence, dict) else None
    if not isinstance(source_report, dict):
        raise FinalizeError("Normalized source-fidelity report lacks the original source validation evidence")
    if (source_report.get("status") != "passed" or source_report.get("error_count") != 0
            or source_report.get("errors") not in ([], None)):
        raise FinalizeError("Original source-validation report did not pass cleanly")
    if source_report.get("manifest_sha256") != _sha256(source_manifest_path):
        raise FinalizeError("Source validation does not bind the exact global source manifest")
    if source_report.get("parquet_sha256") != source_sha256:
        raise FinalizeError("Source validation does not bind the source Parquet")
    progress = source_report.get("progress")
    if (not isinstance(progress, dict) or progress.get("source_rows") != expected_rows
            or progress.get("parquet_rows") != expected_rows
            or progress.get("tiles_completed") != [t["tile"] for t in source_manifest["tiles"]]):
        raise FinalizeError("Source-validation global row/tile coverage differs from manifest")
    if source_report.get("manifest_tile_count") != expected_tiles or source_report.get("source_member_sha256_checked") != expected_tiles * 4:
        raise FinalizeError("Source validation did not cover all tiles and four source members per tile")
    if source_report.get("source_archive_identity_checked") is not True:
        raise FinalizeError("Source validation did not check the complete archive identity")
    archive = source_manifest.get("archive")
    source_archive = source_report.get("source_archive")
    if not isinstance(archive, dict) or not isinstance(source_archive, dict):
        raise FinalizeError("Source archive binding is missing")
    for key in ("filename", "size_bytes", "provider_md5", "sha256"):
        if source_archive.get(key) != archive.get(key):
            raise FinalizeError(f"Source report archive {key} differs from source manifest")
    if (archive.get("filename") != "GRWL_vector_V01.01.zip"
            or archive.get("size_bytes") != 3_104_998_836
            or archive.get("provider_md5") != "40171f15c0fccd470db32446dda0480e"
            or archive.get("sha256") != EXPECTED_ARCHIVE_SHA256):
        raise FinalizeError("Source manifest does not bind the pinned official GRWL raw archive")
    if not isinstance(evidence.get("original_manifest_sha256"), str) or evidence["original_manifest_sha256"] != _sha256(source_manifest_path):
        raise FinalizeError("Normalized source report does not preserve the exact source manifest hash")
    source_validation_sha = evidence.get("source_validation_sha256")
    if not isinstance(source_validation_sha, str) or not SHA256_RE.fullmatch(source_validation_sha):
        raise FinalizeError("Normalized source report lacks the original source-validation file hash")
    if progress.get("parts") != source_manifest.get("parts"):
        raise FinalizeError("Source validation part total differs from source manifest")
    report_tiles = source_report.get("tiles")
    if not isinstance(report_tiles, list) or len(report_tiles) != expected_tiles:
        raise FinalizeError("Source validation has incomplete per-tile evidence")
    if source_report.get("sample_policy") != {"kind": "global_controls", "first_records_per_tile": 8,
                                               "longest_parts_per_tile": 8}:
        raise FinalizeError("Source validator did not use the frozen global source sample policy")
    for expected, checked in zip(source_manifest["tiles"], report_tiles):
        if not isinstance(checked, dict) or checked.get("tile") != expected["tile"]:
            raise FinalizeError("Source validation per-tile order differs from source manifest")
        if (checked.get("source_rows") != expected["records"] or checked.get("matched_rows") != expected["records"]
                or checked.get("parts") != expected.get("parts")
                or checked.get("source_sha256") != expected.get("source_sha256")):
            raise FinalizeError(f"Source fidelity is incomplete or mismatched for tile {expected['tile']}")
        expected_sample_counts = (min(8, expected["records"]), min(8, expected["parts"]))
        first_records, longest_parts = checked.get("first_records"), checked.get("longest_parts")
        if (not isinstance(first_records, list) or not isinstance(longest_parts, list)
                or (len(first_records), len(longest_parts)) != expected_sample_counts):
            raise FinalizeError(f"Source validation omitted frozen raw samples for tile {expected['tile']}")
        for sample in first_records + longest_parts:
            if (not isinstance(sample, dict) or sample.get("source_tile") != expected["tile"]
                    or type(sample.get("source_row")) is not int
                    or not 1 <= sample["source_row"] <= expected["records"]
                    or sample.get("feature_id") != ((_tile_code(expected["tile"]) << 32) | sample["source_row"])):
                raise FinalizeError(f"Source validation sample ID is inconsistent for tile {expected['tile']}")
    return source_report


def _validate_display_manifest(display: dict[str, Any], display_dir: Path,
                               source_sha256: str, source_size: int,
                               source_rows: int, source_tiles: int) -> dict[str, Any]:
    run_id = display.get("display_release")
    if (display.get("schema_version") != 1 or display.get("dataset_id") != "grwl-raw"
            or not isinstance(run_id, str) or not DISPLAY_RUN_RE.fullmatch(run_id)
            or display.get("status") != "provisional"):
        raise FinalizeError("Provisional display manifest identity/status differs from this GRWL release")
    if display.get("source_rows") != source_rows or display.get("source_tiles") != source_tiles:
        raise FinalizeError("Provisional display manifest source totals differ from global source")
    assets = display.get("assets")
    if not isinstance(assets, list) or len(assets) != 1:
        raise FinalizeError("Provisional display package must contain exactly one raw PMTiles asset")
    asset = assets[0]
    if (asset.get("id") != ASSET_ID or asset.get("path") != PROVISIONAL_ASSET_REL
            or asset.get("source_layer") != "grwl_raw" or asset.get("geometry_type") != "line"
            or asset.get("id_field") != "feature_id" or asset.get("id_encoding") != "mvt_feature_id"
            or asset.get("min_zoom") != 8 or asset.get("max_zoom") != 12
            or asset.get("attribute_fields") != ["width_m", "width_valid", "_src_xmin", "_src_ymin", "_src_xmax", "_src_ymax"]):
        raise FinalizeError("Provisional PMTiles asset metadata differs from the frozen raw display contract")
    source_asset = asset.get("source_asset")
    if (not isinstance(source_asset, dict) or source_asset.get("sha256") != source_sha256
            or source_asset.get("size_bytes") != source_size):
        raise FinalizeError("Provisional PMTiles source binding differs from raw analytical Parquet")
    archive = display_dir / PROVISIONAL_ASSET_REL
    if not archive.is_file() or archive.is_symlink():
        raise FinalizeError("Provisional PMTiles asset is missing or unsafe")
    if (asset.get("sha256"), asset.get("size_bytes")) != (_sha256(archive), archive.stat().st_size):
        raise FinalizeError("Provisional PMTiles manifest hash/size differs from actual archive")
    style_rel = _safe_relative(asset.get("style_path"), "display style path")
    style_path = display_dir / style_rel
    style = _json(style_path, "provisional display style")
    sources = style.get("sources")
    vector = sources.get("data") if isinstance(sources, dict) else None
    layers = style.get("layers")
    url = vector.get("url") if isinstance(vector, dict) else None
    if (style.get("version") != 8 or vector is None or vector.get("type") != "vector"
            or not isinstance(url, str) or not url or url.startswith("/") or ":" in url
            or "?" in url or "#" in url):
        raise FinalizeError("Display style does not satisfy the local MapLibre vector-source contract")
    resolved_url = posixpath.normpath(posixpath.join(posixpath.dirname(style_rel), url))
    if resolved_url != asset["path"]:
        raise FinalizeError("Display style source URL does not resolve to the PMTiles asset")
    if (not isinstance(layers, list) or not any(isinstance(layer, dict) and layer.get("source") == "data"
            and layer.get("source-layer") == asset["source_layer"] and layer.get("type") == "line"
            for layer in layers)):
        raise FinalizeError("Display style lacks the expected raw line layer")
    return asset


def _validate_provisional_provenance(display_dir: Path, source_manifest_path: Path,
                                     source_parquet: Path) -> str:
    report_path = display_dir / "reports/input-provenance.json"
    report = _json(report_path, "display build input provenance")
    required_workflow = {
        "build_display.py.txt": ("builder", ROOT / "datasets/grwl-raw/build_display.py"),
        "dateline-helper.py.txt": ("dateline_helper", ROOT / "datasets/grwl/build_display.py"),
        "uv.lock": ("environment_lock", ROOT / "scripts/display_tools/uv.lock"),
        "display-policy.json": ("policy", ROOT / "research/grwl-raw-release-20261102/display-policy.json"),
        "criteria.json": ("criteria", ROOT / "research/grwl-raw-release-20261102/global-criteria.json"),
        "tippecanoe.lock.json": (None, ROOT / "datasets/grwl/tippecanoe.lock.json"),
        "source-manifest.json": ("source_manifest", source_manifest_path),
        "source-fidelity.json": ("source_fidelity", display_dir / "workflow/source-fidelity.json"),
    }
    for filename, (field, current_path) in required_workflow.items():
        copied = display_dir / "workflow" / filename
        descriptor = report.get(field) if field is not None else None
        if field is None:
            descriptor = {"sha256": _sha256(copied), "size_bytes": copied.stat().st_size} if copied.is_file() else None
        if (not isinstance(descriptor, dict) or copied.is_symlink() or not copied.is_file()
                or descriptor.get("sha256") != _sha256(copied)
                or descriptor.get("size_bytes") != copied.stat().st_size):
            raise FinalizeError(f"Display build provenance does not bind workflow input {filename}")
        if not current_path.is_file() or (_sha256(current_path), current_path.stat().st_size) != (
                descriptor["sha256"], descriptor["size_bytes"]):
            raise FinalizeError(f"Display build workflow input differs from current pinned file {field}")
    source_desc = report.get("source")
    if (not isinstance(source_desc, dict) or source_desc.get("sha256") != _sha256(source_parquet)
            or source_desc.get("size_bytes") != source_parquet.stat().st_size):
        raise FinalizeError("Display build provenance does not bind the exact source Parquet")
    fidelity_desc = report["source_fidelity"]
    if fidelity_desc.get("sha256") != _sha256(display_dir / "workflow/source-fidelity.json"):
        raise FinalizeError("Display build provenance source validation differs from copied raw validation")
    tip_lock = _json(display_dir / "workflow/tippecanoe.lock.json", "pinned Tippecanoe contract")
    tip_binary = report.get("tippecanoe")
    if (not isinstance(tip_binary, dict) or tip_binary.get("sha256") != tip_lock.get("binary_sha256")
            or type(tip_binary.get("size_bytes")) is not int or tip_binary["size_bytes"] <= 0
            or report.get("tippecanoe_version") != tip_lock.get("version")):
        raise FinalizeError("Display build Tippecanoe binary/version does not match its pinned contract")
    return _sha256(report_path)


def _validate_native_evidence(policy: dict[str, Any]) -> None:
    contract = policy.get("native_collapse_classifier", {})
    relative = _safe_relative(contract.get("evidence_path"), "native quantization evidence path")
    evidence_path = ROOT / relative
    if relative not in VERIFICATION_WORKFLOW_FILES or _sha256(evidence_path) != contract.get("evidence_sha256"):
        raise FinalizeError("Native quantization evidence does not match the frozen policy checksum")
    evidence = _json(evidence_path, "native quantization evidence")
    lock = _json(ROOT / "datasets/grwl/tippecanoe.lock.json", "pinned native builder")
    native = evidence.get("native_tool", {})
    if native.get("version") != f"tippecanoe v{lock.get('version')}" or native.get("sha256") != lock.get("binary_sha256"):
        raise FinalizeError("Native quantization evidence tool differs from the pinned builder")
    declarations = evidence.get("diagnostic_files")
    required = {"native-quantization-controls.geojson", "native-quantization-controls.pmtiles",
                "native-threshold-controls.geojson", "native-threshold-controls.pmtiles"}
    if not isinstance(declarations, dict) or set(declarations) != required:
        raise FinalizeError("Native quantization evidence has incomplete fixture declarations")
    for name, declaration in declarations.items():
        relative = _safe_relative(declaration.get("path"), "native fixture path")
        path = ROOT / relative
        if (relative not in VERIFICATION_WORKFLOW_FILES or Path(relative).name != name
                or path.is_symlink() or not path.is_file()
                or path.stat().st_size != declaration.get("size_bytes")
                or _sha256(path) != declaration.get("sha256")):
            raise FinalizeError(f"Native quantization fixture checksum/size differs: {name}")


def _validate_oracle(oracle: dict[str, Any], oracle_path: Path, missing_path: Path,
                     manifest_path: Path, source_validation_sha256: str,
                     source_manifest: dict[str, Any], source_sha256: str,
                     pmtiles_sha256: str, expected_tiles: int, expected_rows: int,
                     fidelity: dict[str, Any]) -> dict[str, Any]:
    if (oracle.get("schema_version") != 1 or oracle.get("status") != "passed"
            or oracle.get("errors") != [] or oracle.get("errors_truncated") is not False):
        raise FinalizeError("Independent raw PMTiles oracle is not a clean pass")
    expected_hashes = {
        "source_sha256": source_sha256,
        "source_manifest_sha256": _sha256(manifest_path),
        "source_fidelity_sha256": source_validation_sha256,
        "pmtiles_sha256": pmtiles_sha256,
    }
    for key, expected in expected_hashes.items():
        if oracle.get(key) != expected:
            raise FinalizeError(f"Raw PMTiles oracle {key} is not bound to this release")
    if oracle.get("source_rows") != expected_rows or oracle.get("maxzoom") != 12:
        raise FinalizeError("Raw PMTiles oracle row count or maxzoom differs from global criteria")
    occurrences = oracle.get("maxzoom_feature_occurrences")
    visible = oracle.get("maxzoom_unique_ids")
    missing_count = oracle.get("maxzoom_missing_ids")
    checked = oracle.get("maxzoom_attribute_occurrences_checked")
    if any(type(v) is not int or v < 0 for v in (occurrences, visible, missing_count, checked)):
        raise FinalizeError("Raw PMTiles oracle has invalid z12 accounting totals")
    if visible + missing_count != expected_rows or checked != occurrences or occurrences < visible:
        raise FinalizeError("z12 source ID coverage or attribute occurrence checks are incomplete")
    classes = oracle.get("maxzoom_missing_classification")
    if not isinstance(classes, dict) or any(k not in ALLOWED_MISSING_CAUSES or type(v) is not int or v < 0 for k, v in classes.items()):
        raise FinalizeError("Raw PMTiles oracle has unknown or invalid missing-ID classifications")
    if sum(classes.values()) != missing_count or classes.get("unexpected_loss", 0):
        raise FinalizeError("Raw PMTiles missing-ID classifications do not account for every loss")
    if type(oracle.get("maxzoom_tiles")) is not int or oracle["maxzoom_tiles"] <= 0:
        raise FinalizeError("Raw PMTiles oracle decoded no z12 tiles")
    policy = oracle.get("frozen_sample_policy")
    if policy != {"kind": "global_controls", "first_records_per_tile": 8, "longest_parts_per_tile": 8}:
        raise FinalizeError("Raw PMTiles oracle did not apply the frozen global per-tile sample policy")
    sample_counts = oracle.get("frozen_sample_counts")
    source_tiles = source_manifest.get("tiles", [])
    tile_by_code = {_tile_code(item["tile"]): item for item in source_tiles}
    if not isinstance(sample_counts, list) or len(sample_counts) != expected_tiles:
        raise FinalizeError("Raw PMTiles oracle has incomplete per-tile frozen sample counts")
    sample_ids = set()
    for tile, count in zip(source_tiles, sample_counts):
        if not isinstance(count, dict) or count.get("tile") != tile["tile"]:
            raise FinalizeError("Per-tile frozen sample order differs from source manifest")
        first_expected = min(8, tile["records"])
        longest_expected = min(8, tile["parts"])
        if (count.get("expected_first_records") != first_expected or count.get("validated_first_records") != first_expected
                or count.get("expected_longest_parts") != longest_expected or count.get("validated_longest_parts") != longest_expected):
            raise FinalizeError(f"Frozen global first/longest sample count mismatch for tile {tile['tile']}")
    for tile_evidence in fidelity["evidence"]["source_report"]["tiles"]:
        for item in tile_evidence.get("first_records", []):
            sample_ids.add(item["feature_id"])
        for item in tile_evidence.get("longest_parts", []):
            sample_ids.add(item["feature_id"])
    samples = oracle.get("frozen_geometry_samples")
    if not isinstance(samples, list):
        raise FinalizeError("Raw PMTiles oracle has no geometry sample results")
    observed_ids = []
    for sample in samples:
        if not isinstance(sample, dict) or type(sample.get("id")) is not int:
            raise FinalizeError("Malformed geometry sample result")
        fid = sample["id"]
        if type(sample.get("tiles")) is not int or sample["tiles"] <= 0:
            raise FinalizeError(f"Geometry sample {fid} has no decoded PMTiles geometry")
        observed_ids.append(fid)
        if sample.get("passed") is True:
            distance = sample.get("hausdorff_metres")
            if (sample.get("missing_geometry_exception") is not None or not isinstance(distance, (int, float))
                    or not math.isfinite(distance) or distance < 0 or distance > MAX_GEOMETRY_METRES):
                raise FinalizeError(f"Geometry sample {fid} does not pass the 30 m raw display tolerance")
        else:
            if sample.get("missing_geometry_exception") != "quantization_collapse" or sample.get("hausdorff_metres") is not None:
                raise FinalizeError(f"Geometry sample {fid} is empty/unexplained rather than an enumerated quantization collapse")
    if len(observed_ids) != len(set(observed_ids)) or not sample_ids.issubset(set(observed_ids)):
        raise FinalizeError("Geometry oracle omits frozen source samples or duplicates sample IDs")
    dateline_ids = oracle.get("dateline_bbox_candidate_ids")
    dateline_features = oracle.get("dateline_bbox_candidate_feature_ids")
    if (not isinstance(dateline_features, list) or any(type(fid) is not int for fid in dateline_features)
            or dateline_features != sorted(set(dateline_features)) or dateline_ids != len(dateline_features)):
        raise FinalizeError("Raw display oracle lacks the exact sorted dateline-candidate feature ID inventory")
    control_policy = _json(CONTROL_POLICY_PATH, "frozen display correction/control policy")
    _validate_native_evidence(control_policy)
    if (oracle.get("control_policy_sha256") != _sha256(CONTROL_POLICY_PATH)
            or oracle.get("dateline_control_policy") != control_policy["dateline_supplement"]
            or oracle.get("native_quantizer_sha256") != _sha256(ROOT / "datasets/grwl-raw/native_quantization.py")):
        raise FinalizeError("Raw display oracle does not bind the frozen seam policy and native quantizer")
    crossing_ids = oracle.get("dateline_crossing_feature_ids")
    seam_ids = oracle.get("dateline_seam_feature_ids")
    for values in (crossing_ids, seam_ids):
        if (not isinstance(values, list) or any(type(fid) is not int for fid in values)
                or values != sorted(set(values))):
            raise FinalizeError("Raw display oracle lacks sorted crossing/seam source-ID inventories")
    if set(crossing_ids) & set(seam_ids) or set(dateline_features) != set(crossing_ids) | set(seam_ids):
        raise FinalizeError("Dateline controls differ from the crossing and supplemental seam ID union")
    for fid in dateline_features:
        tile = tile_by_code.get(fid >> 32)
        if tile is None or not 1 <= (fid & 0xFFFFFFFF) <= tile["records"]:
            raise FinalizeError(f"Dateline candidate feature ID {fid} is outside the source inventory")
    if set(observed_ids) != sample_ids | set(dateline_features):
        raise FinalizeError("Geometry oracle samples differ from exact frozen source and dateline candidate ID union")
    if oracle.get("geometry_samples_passed") != sum(s.get("passed") is True for s in samples):
        raise FinalizeError("Raw geometry sample pass count is inconsistent")
    if oracle.get("geometry_samples_missing_exceptions") != sum(s.get("missing_geometry_exception") is not None for s in samples):
        raise FinalizeError("Raw geometry sample exception count is inconsistent")
    sample_results = {s["id"]: s for s in samples}
    wanted_sample_exceptions = {fid for fid, result in sample_results.items() if result.get("passed") is not True}

    if missing_count == 0:
        if wanted_sample_exceptions:
            raise FinalizeError("Oracle marks geometry samples missing without a missing-ID enumeration")
        if oracle.get("maxzoom_missing_path") != missing_path.name:
            raise FinalizeError("Oracle missing-ID path differs from provided file")
        if not missing_path.is_file() or missing_path.is_symlink():
            raise FinalizeError("Raw oracle empty missing-ID evidence file is absent or unsafe")
        if missing_path.stat().st_size:
            raise FinalizeError("Oracle reports zero missing IDs but missing-ID file is nonempty")
        expected_missing_hash = oracle.get("maxzoom_missing_sha256")
        if not isinstance(expected_missing_hash, str) or _sha256(missing_path) != expected_missing_hash:
            raise FinalizeError("Empty missing-ID evidence is not hash-bound")
        return {"visible_ids": visible, "missing_ids": 0, "occurrences": occurrences,
                "attribute_occurrences_checked": checked, "missing_classification": classes,
                "missing_ids_sha256": _sha256(missing_path)}
    if not missing_path.is_file() or missing_path.is_symlink():
        raise FinalizeError("Raw oracle missing-ID evidence file is absent or unsafe")
    if oracle.get("maxzoom_missing_path") != missing_path.name or oracle.get("maxzoom_missing_sha256") != _sha256(missing_path):
        raise FinalizeError("Raw oracle missing-ID path/hash does not match supplied evidence")
    found_sample_exceptions: dict[int, str] = {}
    from collections import Counter
    observed_causes: Counter[str] = Counter()
    previous_id = -1
    counted = 0
    with missing_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FinalizeError(f"Malformed missing-ID JSONL line {line_no}") from exc
            if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= previous_id:
                raise FinalizeError("Missing IDs must be unique and strictly increasing numeric feature IDs")
            fid, cause = row["id"], row.get("cause")
            if cause not in ALLOWED_MISSING_CAUSES:
                raise FinalizeError(f"Unknown missing-ID cause {cause!r}")
            tile_code, source_row = fid >> 32, fid & 0xFFFFFFFF
            tile = tile_by_code.get(tile_code)
            if tile is None or not 1 <= source_row <= tile["records"]:
                raise FinalizeError(f"Missing feature ID {fid} is outside the source inventory")
            if row.get("source_tile") not in (None, tile["tile"]) or row.get("source_row") not in (None, source_row):
                raise FinalizeError(f"Missing feature ID {fid} disagrees with its reported source tile/row")
            if fid in sample_results:
                sample = sample_results[fid]
                if sample.get("passed") is True or cause != "quantization_collapse":
                    raise FinalizeError(f"Geometry sample {fid} is listed missing without its exact collapse exception")
                found_sample_exceptions[fid] = cause
            observed_causes[cause] += 1
            previous_id = fid
            counted += 1
    if counted != missing_count:
        raise FinalizeError("Missing-ID file count differs from oracle summary")
    if any(found_sample_exceptions.get(fid) != "quantization_collapse" for fid in wanted_sample_exceptions):
        raise FinalizeError("Every missing geometry sample must be an enumerated quantization collapse")
    if dict(observed_causes) != {key: value for key, value in classes.items() if value}:
        raise FinalizeError("Per-ID missing causes differ from oracle classification totals")
    return {"visible_ids": visible, "missing_ids": missing_count, "occurrences": occurrences,
            "attribute_occurrences_checked": checked, "missing_classification": classes,
            "missing_ids_sha256": _sha256(missing_path)}


def _attribute_strings(expected: Any) -> dict[str, Any]:
    if not isinstance(expected, dict):
        raise FinalizeError("Browser control expected_analytic_attributes must be an object")
    if len(expected) != 14 or any(not isinstance(k, str) or not isinstance(v, str) for k, v in expected.items()):
        raise FinalizeError("Each browser control must freeze all 14 raw analytical attributes as display strings")
    return expected


def _validate_browser(controls: dict[str, Any], controls_path: Path, report: dict[str, Any],
                      source_sha256: str, source_size: int, source_manifest_sha256: str,
                      source_validation_sha256: str, pmtiles_sha256: str, pmtiles_size: int,
                      policy_sha256: str, expected_rows: int,
                      source_tiles: list[dict[str, Any]]) -> dict[str, Any]:
    if controls.get("status") != "frozen_controls" or controls.get("case_count") != 11 or controls.get("source_rows") != expected_rows:
        raise FinalizeError("Browser controls are not the frozen 11-case global control set")
    cases = controls.get("cases")
    if not isinstance(cases, list) or len(cases) != 11:
        raise FinalizeError("Browser controls must contain exactly 11 cases")
    by_id = {}
    tile_index = {tile["tile"]: tile for tile in source_tiles}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str) or item["case_id"] in by_id:
            raise FinalizeError("Browser controls have malformed or duplicate case IDs")
        by_id[item["case_id"]] = item
        source_tile = tile_index.get(item.get("source_tile"))
        if (type(item.get("source_row")) is not int or type(item.get("feature_id")) is not int
                or source_tile is None or not 1 <= item["source_row"] <= source_tile["records"]
                or item["feature_id"] != ((_tile_code(item.get("source_tile", "")) << 32) | item["source_row"])):
            raise FinalizeError(f"Browser control {item['case_id']} feature ID does not encode source row")
        attributes = _attribute_strings(item.get("expected_analytic_attributes"))
        expected_width = item.get("expected_width")
        if (not isinstance(expected_width, dict) or type(expected_width.get("width_valid")) is not bool
                or not isinstance(expected_width.get("label"), str)):
            raise FinalizeError(f"Browser control {item['case_id']} lacks expected width fields")
        if (attributes.get("source_tile") != item["source_tile"]
                or attributes.get("source_row") != str(item["source_row"])
                or attributes.get("feature_id") != str(item["feature_id"])
                or attributes.get("width_m") != ("null" if expected_width.get("width_m") is None else str(expected_width["width_m"]))
                or attributes.get("width_valid") != ("true" if expected_width["width_valid"] else "false")):
            raise FinalizeError(f"Browser control {item['case_id']} has inconsistent frozen attributes/width")
    if set(by_id) != KNOWN_CASE_IDS | GLOBAL_CASE_IDS:
        raise FinalizeError("Browser controls must contain the five frozen known cases and six continent cases")
    for case_id, context in KNOWN_CONTEXTS.items():
        if by_id[case_id].get("context_region") != context:
            raise FinalizeError(f"Known browser control {case_id} uses the wrong context region")
    for case_id in GLOBAL_CASE_IDS:
        if by_id[case_id].get("context_region") != "grwl_15450":
            raise FinalizeError(f"Global browser control {case_id} must open the global context")
    if controls.get("source_sha256") != source_sha256 or controls.get("source_manifest_sha256") != source_manifest_sha256:
        raise FinalizeError("Frozen browser controls refer to a different analytic source or manifest")
    if controls.get("source_validation_sha256") != source_validation_sha256 or controls.get("browser_policy_sha256") != policy_sha256:
        raise FinalizeError("Frozen browser controls refer to different validation or browser policy evidence")
    if (report.get("schema_version") != 2 or report.get("status") != "passed"
            or report.get("scope") != "Local Chrome source lookup, rendering and bounded HTTP range/CORS checks; no remote publication or GEE claim"):
        raise FinalizeError("Global browser report is not a completed passing v2 report")
    transfer_policy = report.get("transfer_policy")
    if (not isinstance(transfer_policy, dict) or transfer_policy.get("bytes_per_case") != MAX_CASE_BYTES
            or transfer_policy.get("enforced") is not True):
        raise FinalizeError("Browser report did not enforce the frozen 128 MiB per-case transfer limit")
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        raise FinalizeError("Browser report lacks bound input identities")
    expected_inputs = {
        "source_manifest_sha256": source_manifest_sha256,
        "source_validation_sha256": source_validation_sha256,
        "browser_policy_sha256": policy_sha256,
    }
    for key, expected in expected_inputs.items():
        if inputs.get(key) != expected:
            raise FinalizeError(f"Browser report input {key} does not match frozen evidence")
    _check_browser_object(inputs.get("source"), source_sha256, source_size, "source")
    _check_browser_object(inputs.get("pmtiles"), pmtiles_sha256, pmtiles_size, "PMTiles")
    report_cases = report.get("cases")
    if not isinstance(report_cases, list) or len(report_cases) != 11:
        raise FinalizeError("Browser report must contain exactly the 11 frozen control results")
    report_by_id = {}
    for case in report_cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or case["case_id"] in report_by_id:
            raise FinalizeError("Browser report has malformed or duplicate case IDs")
        report_by_id[case["case_id"]] = case
    if set(report_by_id) != set(by_id):
        raise FinalizeError("Browser report case set differs from frozen controls")
    expected_controls_input = inputs.get("controls")
    if (not isinstance(expected_controls_input, dict)
            or expected_controls_input.get("sha256") != _sha256(controls_path)):
        raise FinalizeError("Browser report does not bind the frozen browser controls file")
    if report.get("errors") != []:
        raise FinalizeError("Browser report contains page, external-request, or harness errors")
    for case_id, control in by_id.items():
        case = report_by_id[case_id]
        for key in ("kind", "context_region", "source_tile", "source_row", "feature_id", "detail_bbox"):
            if case.get(key) != control.get(key):
                raise FinalizeError(f"Browser result {case_id} does not match frozen control field {key}")
        for key in ("summary_reference_id", "window_id", "context_bbox"):
            if key in control and case.get(key) != control.get(key):
                raise FinalizeError(f"Browser result {case_id} does not match frozen control field {key}")
        if case.get("status") != "passed":
            raise FinalizeError(f"Browser case {case_id} did not pass full analytic lookup")
        expected_attributes = _attribute_strings(control.get("expected_analytic_attributes"))
        checked_fields = case.get("analytic_attributes_checked")
        if (checked_fields is not True and (type(checked_fields) is not int or checked_fields != len(expected_attributes))):
            raise FinalizeError(f"Browser case {case_id} did not assert every expected analytic attribute")
        if (case.get("analytic_attribute_field_count") != len(expected_attributes)
                or case.get("attribute_mismatches") != []
                or case.get("analytic_attributes") != expected_attributes):
            raise FinalizeError(f"Browser case {case_id} omitted or mismatched analytical attributes")
        expected_width = control.get("expected_width")
        if (not isinstance(expected_width, dict) or type(expected_width.get("width_valid")) is not bool
                or not isinstance(expected_width.get("label"), str)):
            raise FinalizeError(f"Browser control {case_id} has malformed expected width")
        normalized_width = {"width_m": None if expected_width.get("width_m") is None else str(expected_width["width_m"]),
                            "width_valid": expected_width["width_valid"], "label": expected_width["label"]}
        if case.get("width_checked") is not True or case.get("tile_width") != normalized_width:
            raise FinalizeError(f"Browser case {case_id} did not match expected displayed width and label")
        if (case.get("detail_feature_inspected") is not True
                or type(case.get("detail_rendered_features")) is not int or case["detail_rendered_features"] <= 0
                or type(case.get("raw_rendered_features")) is not int or case["raw_rendered_features"] <= 0
                or case["raw_rendered_features"] != case["detail_rendered_features"]):
            raise FinalizeError(f"Browser case {case_id} rendered no features")
        if case.get("error"):
            raise FinalizeError(f"Browser case {case_id} has a recorded page/request error")
        requests = case.get("requests")
        if not isinstance(requests, list) or not requests:
            raise FinalizeError(f"Browser case {case_id} has no HTTP range evidence")
        object_sizes = {
            inputs["source"]["object_path"]: source_size,
            inputs["pmtiles"]["object_path"]: pmtiles_size,
        }
        seen_get_objects = set()
        total_body = 0
        total_requested = 0
        for request in requests:
            method = _validate_range_request(request, case_id)
            if (request["object_path"] not in object_sizes
                    or request["object_size_bytes"] != object_sizes[request["object_path"]]):
                raise FinalizeError(f"Browser case {case_id} range request is not bound to a validated object")
            if method == "GET":
                seen_get_objects.add(request["object_path"])
                total_body += request["body_bytes"]
                total_requested += request["content_length"]
        if seen_get_objects != {inputs["source"]["object_path"], inputs["pmtiles"]["object_path"]}:
            raise FinalizeError(f"Browser case {case_id} did not range-read both bound source and PMTiles")
        requested = total_requested
        if (total_body > MAX_CASE_BYTES or requested > MAX_CASE_BYTES
                or type(case.get("response_body_bytes")) is not int or case["response_body_bytes"] != total_body
                or type(case.get("requested_range_bytes")) is not int or case["requested_range_bytes"] != requested
                or type(case.get("transfer_ceiling_bytes")) is not int or case["transfer_ceiling_bytes"] != MAX_CASE_BYTES):
            raise FinalizeError(f"Browser case {case_id} exceeds or misreports the transfer ceiling")
    if (transfer_policy.get("aggregate_requested_range_bytes") is not True
            or transfer_policy.get("aggregate_response_body_bytes") is not True):
        raise FinalizeError("Browser report did not record its aggregate transfer counters")
    return {"controls_sha256": _sha256(controls_path), "case_count": 11,
            "source_sha256": source_sha256, "pmtiles_sha256": pmtiles_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "source_validation_sha256": source_validation_sha256,
            "browser_policy_sha256": policy_sha256,
            "aggregate_requested_range_bytes": sum(c["requested_range_bytes"] for c in report_cases),
            "aggregate_response_body_bytes": sum(c["response_body_bytes"] for c in report_cases)}


def _check_browser_object(value: Any, digest: str, size: int, label: str) -> None:
    if not isinstance(value, dict) or value.get("sha256") != digest or value.get("size_bytes") != size:
        raise FinalizeError(f"Browser report {label} object is not bound to exact bytes")
    if not isinstance(value.get("object_path"), str) or not value["object_path"]:
        raise FinalizeError(f"Browser report {label} object path is missing")


def _validate_range_request(request: Any, case_id: str) -> str:
    if not isinstance(request, dict):
        raise FinalizeError(f"Malformed HTTP request in browser case {case_id}")
    required = ("object_path", "object_size_bytes", "method", "range", "status", "content_range",
                "content_length", "body_bytes", "cors", "completed")
    if any(key not in request for key in required):
        raise FinalizeError(f"Browser range evidence lacks required fields for {case_id}")
    if request["method"] == "HEAD":
        object_size = request["object_size_bytes"]
        if (type(object_size) is not int or object_size <= 0 or request["completed"] is not True
                or request["cors"] != "*" or request.get("body_error")
                or type(request["content_length"]) is not int or type(request["body_bytes"]) is not int):
            raise FinalizeError(f"Browser HEAD metadata probe is incomplete for {case_id}")
        length = request["content_length"]
        if type(length) is not int or length != object_size or request["body_bytes"] not in (0, object_size):
            raise FinalizeError(f"Browser HEAD metadata size differs for {case_id}")
        if request["range"] is None:
            if request["status"] != 200 or request["content_range"] is not None:
                raise FinalizeError(f"Browser un-ranged HEAD probe is malformed for {case_id}")
        else:
            match_content = CONTENT_RANGE_RE.fullmatch(str(request["content_range"]))
            range_value = str(request["range"])
            valid_full_range = range_value in ("bytes=0-", f"bytes=0-{object_size - 1}")
            if (request["status"] != 206 or not valid_full_range or not match_content
                    or tuple(map(int, match_content.groups())) != (0, object_size - 1, object_size)):
                raise FinalizeError(f"Browser full-object HEAD range metadata is malformed for {case_id}")
        return "HEAD"
    match_range = RANGE_RE.fullmatch(str(request["range"]))
    match_content = CONTENT_RANGE_RE.fullmatch(str(request["content_range"]))
    if (request["method"] != "GET" or request["status"] != 206 or request["cors"] != "*"
            or request["completed"] is not True or request.get("body_error")
            or not match_range or not match_content):
        raise FinalizeError(f"Browser request is not a completed cross-origin partial GET for {case_id}")
    start, end = map(int, match_range.groups())
    cstart, cend, object_size = map(int, match_content.groups())
    length = request["content_length"]
    if (type(request["object_size_bytes"]) is not int or object_size != request["object_size_bytes"]
            or (start, end) != (cstart, cend) or end < start or end >= object_size
            or type(length) is not int or type(request["body_bytes"]) is not int or length != end - start + 1
            or request.get("body_bytes") != length):
        raise FinalizeError(f"Browser request range/Content-Range/size evidence differs for {case_id}")
    if start == 0 and end == object_size - 1:
        raise FinalizeError(f"Browser request transferred the complete object in case {case_id}")
    return "GET"


def _copy_file(source: Path, destination: Path, *, clone: bool = False) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if clone and sys.platform == "darwin":
        proc = subprocess.run(["cp", "-c", str(source), str(destination)], capture_output=True, text=True)
        if proc.returncode == 0:
            if os.path.samefile(source, destination):
                raise FinalizeError("Refusing a hard-linked PMTiles output")
            return "apfs_clone"
        destination.unlink(missing_ok=True)
        free_bytes = shutil.disk_usage(destination.parent).free
        if free_bytes < source.stat().st_size + 15 * 1024**3:
            raise FinalizeError("APFS clone unavailable and insufficient free space remains above the 15 GiB floor")
    shutil.copyfile(source, destination)
    if os.path.samefile(source, destination):
        raise FinalizeError("Refusing a hard-linked output file")
    return "copy"


def _copy_package(provisional: Path, output: Path, pmtiles_rel: str) -> str:
    clone_mode = "copy"
    for current, dirs, files in os.walk(provisional, followlinks=False):
        base = Path(current)
        rel_dir = base.relative_to(provisional)
        dest_dir = output / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        for dirname in dirs:
            child = base / dirname
            if child.is_symlink():
                raise FinalizeError(f"Provisional display contains symlink directory {child}")
        for filename in files:
            source = base / filename
            if source.is_symlink() or not source.is_file():
                raise FinalizeError(f"Provisional display contains unsafe file {source}")
            rel = source.relative_to(provisional).as_posix()
            if rel == "failure.json" or rel == "partial.json":
                raise FinalizeError("Refusing a failed or partial provisional display input")
            mode = _copy_file(source, output / rel, clone=rel == pmtiles_rel)
            if rel == pmtiles_rel:
                clone_mode = mode
    if not (output / "manifest.json").is_file():
        raise FinalizeError("Provisional display manifest was not copied")
    return clone_mode


def _inventory(root: Path) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        base = Path(current)
        for dirname in dirs:
            if (base / dirname).is_symlink():
                raise FinalizeError(f"Output package contains symlink directory {base / dirname}")
        for name in names:
            path = base / name
            rel = path.relative_to(root).as_posix()
            _safe_relative(rel, "output inventory path")
            if path.is_symlink() or not path.is_file():
                raise FinalizeError(f"Output package contains unsafe file {rel}")
            if rel == "manifest.json":
                continue
            files[rel] = {"size_bytes": path.stat().st_size, "sha256": _sha256(path)}
    return dict(sorted(files.items()))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _atomic_json(path: Path, payload: Any) -> None:
    data = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _verify_pmtiles(asset: dict[str, Any], archive_path: Path) -> dict[str, Any]:
    executable = shutil.which("pmtiles")
    if executable is None and Path("/opt/homebrew/bin/pmtiles").is_file():
        executable = "/opt/homebrew/bin/pmtiles"
    if executable is None:
        raise FinalizeError("The pmtiles CLI is required for finalization")
    executable_path = Path(executable).resolve(strict=True)
    binary_size, binary_sha = executable_path.stat().st_size, _sha256(executable_path)
    result = subprocess.run([str(executable_path), "verify", str(archive_path)], capture_output=True, text=True)
    archive_size, archive_sha = archive_path.stat().st_size, _sha256(archive_path)
    if result.returncode != 0:
        raise FinalizeError(f"pmtiles verify failed: {result.stderr[-1000:]}")
    if (archive_size, archive_sha) != (asset["size_bytes"], asset["sha256"]):
        raise FinalizeError("PMTiles archive changed during finalization verification")
    return {"status": "passed", "command": ["pmtiles", "verify", PROVISIONAL_ASSET_REL],
            "binary_size_bytes": binary_size, "binary_sha256": binary_sha,
            "archive_size_bytes": archive_size, "archive_sha256": archive_sha,
            "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}


def _snapshot_verification_workflow(destination: Path, oracle: dict[str, Any]) -> dict[str, Any]:
    raw_validator = ROOT / "datasets/grwl-raw/validate_display.py"
    wrap_validator = ROOT / "datasets/grwl/validate_display_wrap.py"
    environment_lock = ROOT / "scripts/display_tools/uv.lock"
    pins = {
        "validator_sha256": _sha256(raw_validator),
        "wrap_validator_sha256": _sha256(wrap_validator),
        "environment_lock_sha256": _sha256(environment_lock),
        "native_quantizer_sha256": _sha256(ROOT / "datasets/grwl-raw/native_quantization.py"),
        "control_policy_sha256": _sha256(CONTROL_POLICY_PATH),
    }
    for key, digest in pins.items():
        if not SHA256_RE.fullmatch(str(oracle.get(key, ""))) or oracle.get(key) != digest:
            raise FinalizeError(f"Raw display oracle {key} does not match current pinned verifier bytes")
    files = {}
    for relative in VERIFICATION_WORKFLOW_FILES:
        source = ROOT / relative
        if source.is_symlink() or not source.is_file():
            raise FinalizeError(f"Verification workflow input is missing or unsafe: {relative}")
        digest, size = _sha256(source), source.stat().st_size
        target = destination / relative
        _copy_file(source, target)
        if (target.stat().st_size, _sha256(target)) != (size, digest):
            raise FinalizeError(f"Verification workflow snapshot changed during copy: {relative}")
        files[relative] = {"path": target.relative_to(destination.parent.parent.parent).as_posix(),
                           "sha256": digest, "size_bytes": size}
    revision = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True)
    if revision.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}\n?", revision.stdout):
        raise FinalizeError("Cannot record repository commit for the verification workflow snapshot")
    statuses = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *VERIFICATION_WORKFLOW_FILES],
                              capture_output=True, text=True)
    if statuses.returncode != 0:
        raise FinalizeError("Cannot inspect verification workflow working-tree status")
    return {"repository_head": revision.stdout.strip(),
            "working_tree_changes": statuses.stdout.splitlines(),
            "oracle_pins": pins, "files": files}


def _readme(manifest: dict[str, Any], finalization: dict[str, Any]) -> str:
    asset = manifest["assets"][0]
    attribution = finalization["source_attribution"]
    source_license = finalization["source_license"]
    citation = attribution.get("attribution") or attribution.get("title") or "GRWL vector V01.01"
    citation_url = attribution.get("url") or "https://zenodo.org/records/18624542"
    license_name = source_license.get("identifier") or source_license.get("license") or "Source license"
    license_url = source_license.get("url") or "https://creativecommons.org/licenses/by/4.0/"
    lines = [
        "# GRWL raw vectors V01.01 display package", "",
        f"Display release `{manifest['display_release']}` is bound to analytical release `{manifest['analytic_release']}`.",
        "Status: prepared local display derivative. This is not a public hosting, Source Cooperative publication, GEE parity, or scientific-accuracy claim.", "",
        "The GeoParquet remains the analytical source of record. This detail-only PMTiles layer shows separate producer observations at zooms 8–12. Source records are never joined by segment identifiers or proximity. `width_m=1` is the producer unknown-width sentinel; displayed strokes are not bank outlines.", "",
        f"- PMTiles: `{asset['path']}` ({asset['size_bytes']} bytes, SHA-256 `{asset['sha256']}`)",
        f"- Analytical asset: `{asset['source_asset']['path']}` ({asset['source_asset']['size_bytes']} bytes, SHA-256 `{asset['source_asset']['sha256']}`)",
        f"- Source rows: {manifest['source_rows']:,}; source tiles: {manifest['source_tiles']}",
        f"- z12 missing IDs: {finalization['oracle']['missing_ids']:,}, all explicitly classified as {finalization['oracle']['missing_classification']}",
        f"- Producer citation: {citation} Source record: {citation_url}",
        f"- Producer license: {license_name} ({license_url}). Preserve attribution and cite the source release.", "",
        "## Finalization evidence", "",
        "The package inventory binds the source-fidelity evidence, full raw display oracle and missing-ID enumeration, frozen browser controls and report, PMTiles verification, builder provenance, verifier/browser code, dependency locks, and all package assets. The finalization report records the repository commit and per-file SHA-256 values for repeatable inspection. The raw oracle checks z12 ID and attribute accounting and the frozen per-tile geometry samples. Browser evidence checks the exact frozen source attributes and width presentation over local ranged requests.", "",
        "No masks, optional tile index, RSSA supplement, SummaryStats aggregates, current-condition claim, GEE parity, or global scientific-accuracy assessment are included.", "",
    ]
    return "\n".join(lines)


def _validate_inputs(source_manifest_path: Path, fidelity_path: Path, source_parquet: Path,
                     provisional_dir: Path, oracle_path: Path, missing_path: Path,
                     controls_path: Path, browser_report_path: Path, analytic_package: Path,
                     *, expected_tiles: int, expected_rows: int,
                     pmtiles_verifier: Callable[[dict[str, Any], Path], dict[str, Any]] | None,
                     controls_pin_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if provisional_dir.is_symlink() or analytic_package.is_symlink():
        raise FinalizeError("Display and analytic package roots must not be symlinks")
    for path, label in ((source_manifest_path, "source manifest"), (fidelity_path, "fidelity report"),
                        (source_parquet, "source Parquet"), (oracle_path, "display oracle"),
                        (missing_path, "missing-ID evidence"), (controls_path, "browser controls"),
                        (browser_report_path, "browser report")):
        if path.is_symlink():
            raise FinalizeError(f"Refusing symlink input for {label}: {path}")
    manifest = _json(source_manifest_path, "analytical source manifest")
    fidelity = _json(fidelity_path, "normalized source-fidelity report")
    provisional = _json(provisional_dir / "manifest.json", "provisional display manifest")
    oracle = _json(oracle_path, "raw display oracle")
    controls = _json(controls_path, "frozen browser controls")
    frozen_controls = _json(controls_pin_path, "canonical frozen global browser controls")
    for key in ("schema_version", "status", "source_rows", "case_count", "source_sha256",
                "browser_policy_sha256", "browser_limits", "cases"):
        if controls.get(key) != frozen_controls.get(key):
            raise FinalizeError(f"Browser controls differ from canonical frozen global controls field {key}")
    browser = _json(browser_report_path, "global browser report")
    tiles, source_sha, source_size = _source_identity(manifest, source_parquet, expected_tiles, expected_rows)
    _validate_fidelity(fidelity, source_manifest_path, manifest, source_sha, source_size, expected_tiles, expected_rows)
    source_evidence = fidelity["evidence"]
    source_validation_sha = source_evidence["source_validation_sha256"]
    copied_source_validation = provisional_dir / "workflow/source-fidelity.json"
    if not copied_source_validation.is_file() or _sha256(copied_source_validation) != source_validation_sha:
        raise FinalizeError("Provisional display workflow does not preserve the bound raw source-validation report")
    copied_source_validation_report = _json(copied_source_validation, "copied raw source-validation report")
    if copied_source_validation_report != source_evidence["source_report"]:
        raise FinalizeError("Copied raw source-validation report differs from normalized fidelity evidence")
    display_provenance_sha = _validate_provisional_provenance(provisional_dir, source_manifest_path,
                                                               source_parquet)
    analytic = _validate_analytic_package(analytic_package, source_sha, source_size, expected_rows,
                                          _sha256(fidelity_path))
    asset = _validate_display_manifest(provisional, provisional_dir, source_sha, source_size, expected_rows, expected_tiles)
    pmtiles_path = provisional_dir / asset["path"]
    pmtiles_sha, pmtiles_size = _sha256(pmtiles_path), pmtiles_path.stat().st_size
    oracle_summary = _validate_oracle(oracle, oracle_path, missing_path, source_manifest_path, source_validation_sha,
                                      manifest, source_sha, pmtiles_sha, expected_tiles, expected_rows, fidelity)
    policy_path = ROOT / "research/grwl-raw-release-20261102/global-browser-policy.json"
    policy_sha = _sha256(policy_path)
    browser_summary = _validate_browser(controls, controls_path, browser, source_sha, source_size,
                                        _sha256(source_manifest_path), source_validation_sha,
                                        pmtiles_sha, pmtiles_size, policy_sha, expected_rows, tiles)
    verifier = pmtiles_verifier or _verify_pmtiles
    verification = verifier(asset, pmtiles_path)
    if not isinstance(verification, dict) or verification.get("status") != "passed":
        raise FinalizeError("PMTiles verification did not pass")
    if (verification.get("archive_sha256") != pmtiles_sha
            or verification.get("archive_size_bytes") != pmtiles_size):
        raise FinalizeError("PMTiles verification report does not bind current archive bytes")
    return {
        "manifest": manifest, "fidelity": fidelity, "source_sha256": source_sha,
        "source_size_bytes": source_size, "source_tiles": tiles, "source_rows": expected_rows,
        "analytic": analytic, "provisional_manifest": provisional, "display_asset": asset,
        "provisional_run_id": provisional["display_release"], "raw_oracle_report": oracle,
        "pmtiles_path": pmtiles_path, "pmtiles_sha256": pmtiles_sha,
        "pmtiles_size_bytes": pmtiles_size, "oracle": oracle_summary,
        "display_provenance_sha256": display_provenance_sha,
        "oracle_report_sha256": _sha256(oracle_path), "missing_path": missing_path,
        "missing_sha256": _sha256(missing_path) if missing_path.exists() else None,
        "browser": browser_summary, "browser_report_sha256": _sha256(browser_report_path),
        "controls_sha256": _sha256(controls_path), "verification": verification,
        "provisional_manifest_sha256": _sha256(provisional_dir / "manifest.json"),
        "verification_binary_sha256": verification.get("binary_sha256"),
    }, {"oracle_path": oracle_path, "missing_path": missing_path, "controls_path": controls_path,
        "browser_report_path": browser_report_path, "fidelity_path": fidelity_path,
        "manifest_path": source_manifest_path, "raw_validation_path": provisional_dir / "workflow/source-fidelity.json",
        "provisional_manifest_path": provisional_dir / "manifest.json", "analytic_package": analytic_package}


def finalize_display(source_manifest_path: Path, fidelity_path: Path, source_parquet: Path,
                     provisional_dir: Path, oracle_path: Path, missing_path: Path,
                     controls_path: Path, browser_report_path: Path, analytic_package: Path,
                     output_dir: Path, *, expected_tiles: int = EXPECTED_TILES,
                     expected_rows: int = EXPECTED_ROWS,
                     controls_pin_path: Path | None = None,
                     pmtiles_verifier: Callable[[dict[str, Any], Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Prepare a distinct display package; injected verifier is intended for unit fixtures."""
    source_manifest_path, fidelity_path, source_parquet = map(Path, (source_manifest_path, fidelity_path, source_parquet))
    provisional_dir, oracle_path, missing_path = map(Path, (provisional_dir, oracle_path, missing_path))
    controls_path, browser_report_path, analytic_package = map(Path, (controls_path, browser_report_path, analytic_package))
    controls_pin_path = Path(controls_pin_path) if controls_pin_path is not None else ROOT / "research/grwl-raw-release-20261102/global-browser-controls-r2.json"
    output_dir = Path(output_dir).expanduser()
    if os.path.lexists(output_dir):
        raise FileExistsError(f"Refusing to reuse existing final display output: {output_dir}")
    output_dir = output_dir.resolve(strict=False)
    for protected in (provisional_dir, analytic_package):
        protected = Path(protected).expanduser().resolve(strict=True)
        if output_dir == protected or output_dir.is_relative_to(protected) or protected.is_relative_to(output_dir):
            raise FinalizeError("Final display output must not overlap a read-only input package")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=False, exist_ok=False)
    _write_json(output_dir / "partial.json", {"status": "partial", "usable_release": False})
    try:
        checked, input_paths = _validate_inputs(source_manifest_path, fidelity_path, source_parquet,
            provisional_dir, oracle_path, missing_path, controls_path, browser_report_path,
            analytic_package, expected_tiles=expected_tiles, expected_rows=expected_rows,
            pmtiles_verifier=pmtiles_verifier, controls_pin_path=controls_pin_path)
        asset = checked["display_asset"]
        clone_mode = _copy_package(provisional_dir, output_dir, asset["path"])
        output_archive = output_dir / asset["path"]
        if (output_archive.stat().st_size, _sha256(output_archive)) != (checked["pmtiles_size_bytes"], checked["pmtiles_sha256"]):
            raise FinalizeError("Cloned/copied PMTiles bytes differ from provisional archive")
        asset["source_asset"]["path"] = ANALYTIC_ASSET_REL
        finalization_dir = output_dir / "reports/finalization"
        finalization_dir.mkdir(parents=True, exist_ok=True)
        evidence_files = {
            "source-manifest.json": input_paths["manifest_path"],
            "raw-source-validation.json": input_paths["raw_validation_path"],
            "source-fidelity.normalized.json": input_paths["fidelity_path"],
            "provisional-display-manifest.json": input_paths["provisional_manifest_path"],
            "raw-display-oracle.json": input_paths["oracle_path"],
            "raw-display-missing-ids.jsonl": input_paths["missing_path"],
            "global-browser-controls.json": input_paths["controls_path"],
            "global-browser-report.json": input_paths["browser_report_path"],
            "global-browser-policy.json": ROOT / "research/grwl-raw-release-20261102/global-browser-policy.json",
        }
        for name, source_path in evidence_files.items():
            if source_path.is_file():
                _copy_file(source_path, finalization_dir / name)
        for relative, item in checked["analytic"]["provenance_files"].items():
            _copy_file(item["path"], finalization_dir / "analytic-package" / relative)
        for name, source_path in (("manifest.json", input_paths["analytic_package"] / "manifest.json"),
                                  ("package-receipt.json", checked["analytic"]["receipt_path"])):
            _copy_file(source_path, finalization_dir / "analytic-package" / name)
        _write_json(finalization_dir / "pmtiles-verify.json", checked["verification"])
        verification_workflow = _snapshot_verification_workflow(
            finalization_dir / "verification-workflow", checked["raw_oracle_report"])
        finalization_report = {
            "schema_version": 1, "status": "passed", "dataset_id": "grwl-raw",
            "analytic_release": checked["analytic"]["release_id"], "display_release": DISPLAY_RELEASE,
            "provisional_display_run_id": checked["provisional_run_id"],
            "source_rows": checked["source_rows"], "source_tiles": len(checked["source_tiles"]),
            "source_attribution": checked["analytic"]["source_attribution"],
            "source_license": checked["analytic"]["source_license"],
            "data_license": checked["analytic"]["data_license"],
            "source_parquet": {"sha256": checked["source_sha256"], "size_bytes": checked["source_size_bytes"]},
            "pmtiles": {"sha256": checked["pmtiles_sha256"], "size_bytes": checked["pmtiles_size_bytes"]},
            "source_manifest_sha256": _sha256(source_manifest_path),
            "provisional_display_manifest_sha256": checked["provisional_manifest_sha256"],
            "display_input_provenance_sha256": checked["display_provenance_sha256"],
            "verification_workflow": verification_workflow,
            "source_fidelity_sha256": _sha256(fidelity_path),
            "raw_display_oracle_sha256": checked["oracle_report_sha256"],
            "missing_ids_sha256": checked["missing_sha256"],
            "browser_controls_sha256": checked["controls_sha256"],
            "browser_report_sha256": checked["browser_report_sha256"],
            "oracle": checked["oracle"], "browser": checked["browser"],
            "pmtiles_verification_sha256": _sha256(finalization_dir / "pmtiles-verify.json"),
            "pmtiles_verification_binary_sha256": checked["verification_binary_sha256"],
            "pmtiles_copy_mode": clone_mode, "publicly_published": False, "hosted": False,
        }
        _write_json(finalization_dir / "report.json", finalization_report)
        display_manifest = checked["provisional_manifest"]
        display_manifest.update({
            "display_release": DISPLAY_RELEASE,
            "analytic_release": checked["analytic"]["release_id"],
            "source_rows": checked["source_rows"], "source_tiles": len(checked["source_tiles"]),
            "attribution": checked["analytic"]["source_attribution"].get("attribution")
                or checked["analytic"]["source_attribution"].get("title"),
            "source_license": checked["analytic"]["source_license"],
            "assets": [asset],
        })
        readme = _readme(display_manifest, finalization_report)
        (output_dir / "README.md").write_text(readme, encoding="utf-8")
        (output_dir / "partial.json").unlink()
        display_manifest["status"] = "prepared"
        display_manifest["files"] = _inventory(output_dir)
        _atomic_json(output_dir / "manifest.json", display_manifest)
        return {"status": "prepared", "dataset_id": "grwl-raw", "analytic_release": checked["analytic"]["release_id"],
                "display_release": DISPLAY_RELEASE, "output_dir": str(output_dir),
                "manifest_sha256": _sha256(output_dir / "manifest.json"), "asset_sha256": checked["pmtiles_sha256"]}
    except BaseException as exc:
        _write_json(output_dir / "failure.json", {"schema_version": 1, "status": "failed_partial",
                                                   "usable_release": False, "error_type": type(exc).__name__,
                                                   "error": str(exc)})
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-manifest", "fidelity", "source-parquet", "provisional-display",
                 "oracle", "missing-ids", "browser-controls", "browser-report", "analytic-package", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = finalize_display(args.source_manifest, args.fidelity, args.source_parquet,
            args.provisional_display, args.oracle, args.missing_ids, args.browser_controls,
            args.browser_report, args.analytic_package, args.output_dir)
    except Exception as exc:
        print(f"GRWL raw display finalization: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
