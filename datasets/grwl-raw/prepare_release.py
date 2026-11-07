#!/usr/bin/env python3
"""Prepare GRWL raw normalized evidence and a local package specification.

This adapter only prepares inputs for scripts/release_tools/package_release.py.
It does not run the packager, publish, or change canonical metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import yaml
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
GLOBAL_CRITERIA = ROOT / "research/grwl-raw-release-20261102/global-criteria.json"
ORIGINAL_CRITERIA = ROOT / "research/grwl-raw-release-20261102/criteria.json"
DEFAULT_RECORD = ROOT / "datasets/grwl-raw/dataset.yaml"
EXPECTED_ARCHIVE_SHA256 = "78072f67991b0cf9eb3373c7a9c314c0da826857c698dd03d20421b2d0d3bbec"
EXPECTED_ARCHIVE_MD5 = "40171f15c0fccd470db32446dda0480e"
EXPECTED_ARCHIVE_BYTES = 3_104_998_836
EXPECTED_TILES = 829
EXPECTED_ROWS = 64_572_998
ASSET_ID = "grwl-raw-observations"
RELEASE_ID = "raw-v01.01-local-r1"
HEX256 = re.compile(r"^[0-9a-f]{64}$")


class PreparationError(ValueError):
    """Evidence does not satisfy the local preparation contract."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PreparationError(f"Cannot read {label} JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreparationError(f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_record(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PreparationError(f"Cannot read canonical dataset record {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("id") != "grwl-raw":
        raise PreparationError("Canonical record must remain the grwl-raw record")
    return value


def _tile_bounds(manifest: dict[str, Any]) -> list[float]:
    tiles = manifest.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise PreparationError("Global manifest has no per-tile extents")
    extents = []
    for item in tiles:
        if not isinstance(item, dict):
            raise PreparationError("Malformed tile entry in global manifest")
        extent = item.get("extent")
        if extent is None:
            continue
        if not isinstance(extent, list) or len(extent) != 4:
            raise PreparationError(f"Invalid extent in tile {item.get('tile')}")
        try:
            bounds = [float(value) for value in extent]
        except (TypeError, ValueError) as exc:
            raise PreparationError(f"Non-numeric extent in tile {item.get('tile')}") from exc
        if not all(math.isfinite(value) for value in bounds):
            raise PreparationError(f"Non-finite extent in tile {item.get('tile')}")
        extents.append(bounds)
    if not extents:
        raise PreparationError("No nonempty tile extent is available")
    return [min(x[0] for x in extents), min(x[1] for x in extents),
            max(x[2] for x in extents), max(x[3] for x in extents)]


def _validate_manifest(manifest: dict[str, Any], label: str, *, expected_tiles: int,
                       expected_rows: int, archive_sha256: str, archive_md5: str,
                       archive_bytes: int) -> None:
    if manifest.get("status") not in {"provisional", "passed", "complete"}:
        raise PreparationError(f"{label} manifest is failed, partial, or not a completed conversion")
    validation = manifest.get("validation")
    if validation is not None and (not isinstance(validation, dict) or validation.get("status") == "failed"):
        raise PreparationError(f"{label} manifest carries failed validation status")
    archive = manifest.get("archive")
    if not isinstance(archive, dict):
        raise PreparationError(f"{label} manifest lacks archive identity")
    actual = (archive.get("size_bytes"), str(archive.get("provider_md5", "")).lower(),
              str(archive.get("sha256", "")).lower(), archive.get("whole_archive_checksum_verified"))
    expected = (archive_bytes, archive_md5.lower(), archive_sha256.lower(), True)
    if actual != expected:
        raise PreparationError(f"{label} archive identity differs from the official pinned source")
    if manifest.get("rows") != expected_rows:
        raise PreparationError(f"{label} row count is not the required {expected_rows}")
    tiles = manifest.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != expected_tiles:
        raise PreparationError(f"{label} tile count is not the required {expected_tiles}")
    names = [x.get("tile") for x in tiles if isinstance(x, dict)]
    if len(names) != expected_tiles or names != sorted(names) or len(set(names)) != expected_tiles:
        raise PreparationError(f"{label} tile list must be complete, unique, and sorted")
    if sum(int(x.get("records", -1)) for x in tiles) != expected_rows:
        raise PreparationError(f"{label} per-tile record counts differ from global rows")


def _validate_source_report(report: dict[str, Any], original_manifest_path: Path,
                            original_manifest: dict[str, Any], parquet_hash: str,
                            expected_tiles: int, expected_rows: int) -> None:
    if report.get("status") != "passed" or int(report.get("error_count", -1)) != 0:
        raise PreparationError("Original source-fidelity report did not pass cleanly")
    if report.get("errors") not in ([], None):
        raise PreparationError("Original source-fidelity report contains errors")
    if report.get("manifest_sha256") != _sha256(original_manifest_path):
        raise PreparationError("Source-fidelity report does not bind the exact original manifest")
    if report.get("parquet_sha256") != parquet_hash:
        raise PreparationError("Source-fidelity report does not bind the original Parquet bytes")
    progress = report.get("progress")
    if not isinstance(progress, dict) or progress.get("parquet_rows") != expected_rows or progress.get("source_rows") != expected_rows:
        raise PreparationError("Source-fidelity report row counts do not meet the global requirement")
    if progress.get("tiles_completed") != [item["tile"] for item in original_manifest["tiles"]]:
        raise PreparationError("Source-fidelity report tile order differs from original manifest")
    if report.get("manifest_tile_count") != expected_tiles:
        raise PreparationError("Source-fidelity report tile count is incomplete")
    if report.get("source_archive_identity_checked") is not True:
        raise PreparationError("Source validation did not verify the complete source archive identity")
    archive = original_manifest["archive"]
    source_archive = report.get("source_archive")
    if not isinstance(source_archive, dict):
        raise PreparationError("Source validation report lacks verified source archive identity")
    for key in ("filename", "size_bytes", "provider_md5", "sha256"):
        if source_archive.get(key) != archive.get(key):
            raise PreparationError(f"Source validation archive {key} differs from original manifest")
    if report.get("source_member_sha256_checked") != expected_tiles * 4:
        raise PreparationError("Source validation did not hash all four source members for every tile")
    report_tiles = report.get("tiles")
    if not isinstance(report_tiles, list) or len(report_tiles) != expected_tiles:
        raise PreparationError("Source validation per-tile evidence is incomplete")
    if [item.get("tile") if isinstance(item, dict) else None for item in report_tiles] != [
            item["tile"] for item in original_manifest["tiles"]]:
        raise PreparationError("Source validation tile order differs from original manifest")
    manifest_tiles = {entry["tile"]: entry for entry in original_manifest["tiles"]}
    seen = set()
    tile_parts = 0
    for checked in report_tiles:
        if not isinstance(checked, dict):
            raise PreparationError("Malformed per-tile source validation entry")
        tile = checked.get("tile")
        expected = manifest_tiles.get(tile)
        if expected is None or tile in seen:
            raise PreparationError(f"Unexpected or duplicate validated source tile {tile!r}")
        seen.add(tile)
        rows = expected["records"]
        if checked.get("source_rows") != rows or checked.get("matched_rows") != rows:
            raise PreparationError(f"Source rows were not all matched for tile {tile}")
        if checked.get("parts") != expected.get("parts"):
            raise PreparationError(f"Source part count differs from manifest for tile {tile}")
        if checked.get("source_sha256") != expected.get("source_sha256"):
            raise PreparationError(f"Source member hashes differ from manifest for tile {tile}")
        tile_parts += checked["parts"]
    if seen != set(manifest_tiles):
        raise PreparationError("Source validation tile coverage differs from original manifest")
    if progress.get("parts") != tile_parts or tile_parts != original_manifest.get("parts"):
        raise PreparationError("Source validation part totals differ from manifest")


def _validate_receipt(receipt: dict[str, Any], rebuild_manifest: dict[str, Any],
                      rebuild_manifest_sha256: str) -> None:
    if receipt.get("schema_version") != 1 or receipt.get("status") != "passed":
        raise PreparationError("Clean-checkout rebuild receipt is missing or not passed")
    if not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("git_revision", ""))):
        raise PreparationError("Receipt must provide a full 40-character git_revision")
    for key in ("working_tree_before", "working_tree_after"):
        observed = receipt.get(key)
        if not isinstance(observed, dict) or observed.get("status") != "clean":
            raise PreparationError(f"Receipt {key} must explicitly record status clean")
        if observed.get("observed") is not True:
            raise PreparationError(f"Receipt {key} must say cleanliness was observed")
    if receipt.get("exit_status") != 0:
        raise PreparationError("Clean-checkout rebuild exit_status must be zero")
    manifest_inputs = rebuild_manifest.get("build_inputs")
    receipt_inputs = receipt.get("input_hashes")
    if not isinstance(manifest_inputs, dict) or not isinstance(receipt_inputs, dict):
        raise PreparationError("Rebuild manifest and receipt must include build input hashes")
    for key in ("builder_sha256", "converter_sha256", "environment_lock_sha256"):
        digest = manifest_inputs.get(key)
        if not isinstance(digest, str) or not HEX256.fullmatch(digest):
            raise PreparationError(f"Rebuild manifest lacks valid {key}")
        if receipt_inputs.get(key) != digest:
            raise PreparationError(f"Receipt {key} differs from rebuild manifest provenance")
    if receipt.get("parquet_sha256") != rebuild_manifest.get("parquet_sha256"):
        raise PreparationError("Receipt does not bind rebuild Parquet SHA-256")
    if receipt.get("rebuild_manifest_sha256") != rebuild_manifest_sha256:
        raise PreparationError("Receipt does not bind the exact rebuild manifest")


def _workflow_code_pins(manifest: dict[str, Any]) -> dict[str, str]:
    inputs = manifest.get("build_inputs")
    if not isinstance(inputs, dict):
        raise PreparationError("Manifest lacks builder provenance hashes")
    pins = {
        "datasets/grwl-raw/build_global.py": inputs.get("builder_sha256"),
        "datasets/grwl-raw/convert.py": inputs.get("converter_sha256"),
        "scripts/display_tools/uv.lock": inputs.get("environment_lock_sha256"),
    }
    for path, digest in pins.items():
        if not isinstance(digest, str) or not HEX256.fullmatch(digest):
            raise PreparationError(f"Manifest lacks a valid code pin for {path}")
        if _sha256(ROOT / path) != digest:
            raise PreparationError(f"Current workflow bytes no longer match builder provenance: {path}")
    return pins


def _validate_evidence_file_pins(manifest: dict[str, Any]) -> None:
    pins = {
        GLOBAL_CRITERIA.relative_to(ROOT).as_posix(): manifest.get("criteria_sha256"),
        "research/grwl-raw-audit-20261102/vector-inventory-r1.json": manifest.get("source_inventory_sha256"),
    }
    for relative, expected in pins.items():
        path = ROOT / relative
        if not isinstance(expected, str) or not HEX256.fullmatch(expected):
            raise PreparationError(f"Manifest lacks valid identity for {relative}")
        if not path.is_file() or _sha256(path) != expected:
            raise PreparationError(f"Current evidence bytes no longer match manifest: {relative}")


def _validate_optional_validator_pin(report: dict[str, Any]) -> None:
    supplied = report.get("validator_sha256")
    if supplied is None:
        return
    validator_path = ROOT / "datasets/grwl-raw/validate.py"
    if not isinstance(supplied, str) or not HEX256.fullmatch(supplied):
        raise PreparationError("Source report validator_sha256 is malformed")
    if _sha256(validator_path) != supplied:
        raise PreparationError("Current source validator differs from reported validator provenance")


def prepare_release(original_manifest_path: Path, rebuild_manifest_path: Path,
                    original_parquet: Path, rebuild_parquet: Path,
                    source_validation_path: Path, clean_receipt_path: Path,
                    output_dir: Path, *, expected_tiles: int = EXPECTED_TILES,
                    expected_rows: int = EXPECTED_ROWS,
                    archive_sha256: str = EXPECTED_ARCHIVE_SHA256,
                    archive_md5: str = EXPECTED_ARCHIVE_MD5,
                    archive_bytes: int = EXPECTED_ARCHIVE_BYTES) -> dict[str, Any]:
    """Validate bound inputs then create reports and a package spec in a new directory.

    Pin overrides exist for unit fixtures only. The CLI supplies no overrides.
    """
    paths = [original_manifest_path, rebuild_manifest_path, original_parquet,
             rebuild_parquet, source_validation_path, clean_receipt_path]
    paths = [path.expanduser().resolve() for path in paths]
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise PreparationError(f"Refusing to reuse existing output path: {output_dir}")
    if not output_dir.parent.is_dir():
        raise PreparationError(f"Output parent directory must already exist: {output_dir.parent}")
    package_dir = output_dir.parent / f"{output_dir.name}-package"
    if package_dir.exists():
        raise PreparationError(f"Refusing to prepare a spec targeting existing package path: {package_dir}")
    if not all(path.is_file() for path in paths):
        missing = [str(path) for path in paths if not path.is_file()]
        raise PreparationError(f"Missing required evidence/input files: {missing}")
    (original_manifest_path, rebuild_manifest_path, original_parquet,
     rebuild_parquet, source_validation_path, clean_receipt_path) = paths
    original = _read_json(original_manifest_path, "original manifest")
    rebuild = _read_json(rebuild_manifest_path, "rebuild manifest")
    source_report = _read_json(source_validation_path, "source validation report")
    receipt = _read_json(clean_receipt_path, "clean-checkout receipt")
    for manifest, label in ((original, "Original"), (rebuild, "Rebuild")):
        _validate_manifest(manifest, label, expected_tiles=expected_tiles,
                           expected_rows=expected_rows, archive_sha256=archive_sha256,
                           archive_md5=archive_md5, archive_bytes=archive_bytes)
    for key in ("builder_sha256", "converter_sha256", "environment_lock_sha256"):
        if original.get("build_inputs", {}).get(key) != rebuild.get("build_inputs", {}).get(key):
            raise PreparationError(f"Original and rebuild {key} differ")
    original_hash, rebuild_hash = _sha256(original_parquet), _sha256(rebuild_parquet)
    original_size, rebuild_size = original_parquet.stat().st_size, rebuild_parquet.stat().st_size
    for manifest, label, digest, size in ((original, "Original", original_hash, original_size),
                                           (rebuild, "Rebuild", rebuild_hash, rebuild_size)):
        if manifest.get("parquet_sha256") != digest:
            raise PreparationError(f"{label} manifest Parquet SHA-256 differs from actual file")
        expected_size = manifest.get("parquet_size_bytes")
        if expected_size is not None and (not isinstance(expected_size, int) or expected_size != size):
            raise PreparationError(f"{label} manifest Parquet byte size differs from actual file")
        try:
            parquet_rows = pq.ParquetFile(original_parquet if label == "Original" else rebuild_parquet).metadata.num_rows
        except Exception as exc:
            raise PreparationError(f"{label} Parquet footer cannot be read: {exc}") from exc
        if parquet_rows != expected_rows:
            raise PreparationError(f"{label} Parquet footer row count differs from {expected_rows}")
    if original_hash != rebuild_hash or original_size != rebuild_size:
        raise PreparationError("Original and clean rebuild GeoParquet bytes are not identical")
    receipt_size = receipt.get("parquet_size_bytes")
    if receipt_size is not None and receipt_size != rebuild_size:
        raise PreparationError("Receipt Parquet byte size differs from actual rebuild file")
    _validate_source_report(source_report, original_manifest_path, original,
                            original_hash, expected_tiles, expected_rows)
    _validate_receipt(receipt, rebuild, _sha256(rebuild_manifest_path))
    _validate_optional_validator_pin(source_report)
    pins = _workflow_code_pins(rebuild)
    _validate_evidence_file_pins(original)
    _validate_evidence_file_pins(rebuild)
    bounds = _tile_bounds(original)
    record = _load_record(DEFAULT_RECORD)
    source = record["source"]
    license_id = source.get("license")
    license_url = source.get("license_url")
    if not license_id or not license_url or not source.get("citation"):
        raise PreparationError("Canonical source record lacks citation or license")

    assets = [{"asset_id": ASSET_ID, "sha256": original_hash, "size_bytes": original_size}]
    normalized_source = {
        "status": "passed", "assets": assets,
        "evidence": {"kind": "GRWL raw source fidelity", "source_report": source_report,
                     "original_manifest": original, "original_manifest_sha256": _sha256(original_manifest_path),
                     "source_validation_sha256": _sha256(source_validation_path)},
    }
    normalized_rebuild = {
        "status": "passed", "assets": assets,
        "evidence": {"kind": "clean-checkout byte-identical rebuild",
                     "receipt": receipt, "rebuild_manifest": rebuild,
                     "rebuild_manifest_sha256": _sha256(rebuild_manifest_path),
                     "identical_parquet_sha256": original_hash,
                     "identical_parquet_size_bytes": original_size},
    }
    source_report_out = output_dir / "source-fidelity.normalized.json"
    rebuild_report_out = output_dir / "clean-rebuild.normalized.json"
    spec_out = output_dir / "release-spec.json"
    spec = {
        "dataset_record_path": str(DEFAULT_RECORD), "dataset_id": "grwl-raw",
        "title": record["title"], "release_id": RELEASE_ID, "release_version": "1.0.0",
        "output_dir": str(package_dir),
        "catalog_id": "grwl-raw",
        "processor": {"name": "nthh", "roles": ["host", "processor"], "url": "https://github.com/nthh",
                      "description": "Independent format conversion and local package host; not publicly hosted."},
        "source_attribution": {"url": "https://zenodo.org/records/18624542",
            "title": "Global River Width from Landsat raw vector component V01.01",
            "attribution": source["citation"], "version": "V01.01",
            "doi": "https://doi.org/10.5281/zenodo.18624542",
            "license": {"identifier": license_id, "url": license_url}},
        "producers": [{"name": "Allen and Pavelsky / GRWL", "roles": ["producer", "licensor"],
                       "url": "https://zenodo.org/records/18624542"}],
        "source_fidelity_report_path": str(source_report_out),
        "clean_rebuild_report_path": str(rebuild_report_out),
        "assets": [{"asset_id": ASSET_ID, "path": str(original_parquet),
                    "identifier_column": "feature_id", "title": record["title"],
                    "description": "Lossless raw producer PolyLine records with source tile and row identity."}],
        "data_license": {"license": license_id, "url": license_url,
                          "attribution": source["citation"]},
        "source_license": {"identifier": license_id, "url": license_url},
        "stac_license": license_id,
        "citation": source["citation"],
        "description": ("Detailed producer GRWL vector observations with each source record, part and coordinate retained. "
                        "Records are kept separate; segmentID is tile-local. width_m=1 means unknown width, "
                        "and width_valid marks usable measurements. " + source["temporal_scope"]),
        "bbox": bounds, "temporal_interval": [None, None],
        "code_revision": receipt["git_revision"],
        "workflow_paths": ["datasets/grwl-raw/acquire.py", "datasets/grwl-raw/build_global.py",
                           "datasets/grwl-raw/convert.py", "datasets/grwl-raw/validate.py",
                           "datasets/grwl-raw/prepare_release.py", "datasets/grwl-raw/README.md",
                           "research/grwl-raw-release-20261102/run_clean_global.py", "scripts/display_tools/uv.lock",
                           "research/grwl-raw-release-20261102/criteria.json",
                           "research/grwl-raw-release-20261102/global-criteria.json",
                           "research/grwl-raw-audit-20261102/vector-inventory-r1.json"],
        "workflow_revisions": {},
        "preparation_evidence": {"builder_code_sha256": pins,
                                 "environment_lock_sha256": rebuild["build_inputs"]["environment_lock_sha256"],
                                 "criteria_sha256": {"original": _sha256(ORIGINAL_CRITERIA),
                                                     "global": rebuild["criteria_sha256"]},
                                 "original_manifest_sha256": _sha256(original_manifest_path),
                                 "rebuild_manifest_sha256": _sha256(rebuild_manifest_path)},
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        source_report_out.write_text(json.dumps(normalized_source, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rebuild_report_out.write_text(json.dumps(normalized_rebuild, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        spec_out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        (output_dir / "failure.json").write_text(json.dumps({"status": "failed_partial", "error": str(exc)}, indent=2) + "\n")
        raise
    return {"status": "prepared_inputs_only", "output_dir": str(output_dir),
            "source_fidelity_report": str(source_report_out), "clean_rebuild_report": str(rebuild_report_out),
            "release_spec": str(spec_out), "usable_release": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-manifest", type=Path, required=True)
    parser.add_argument("--rebuild-manifest", type=Path, required=True)
    parser.add_argument("--original-parquet", type=Path, required=True)
    parser.add_argument("--rebuild-parquet", type=Path, required=True)
    parser.add_argument("--source-validation", type=Path, required=True)
    parser.add_argument("--clean-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_release(args.original_manifest, args.rebuild_manifest,
                                 args.original_parquet, args.rebuild_parquet,
                                 args.source_validation, args.clean_receipt,
                                 args.output_dir)
    except Exception as exc:
        print(f"prepare_release: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
