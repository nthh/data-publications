#!/usr/bin/env python3
"""Package an immutable local GRIP release with bound verification reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
REQUIRED_REPORTS = (
    "validation.json",
    "stac-validation.json",
    "portolan-validation.json",
    "reproducibility.json",
    "fault-tests.json",
)
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict:
    return {"size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _archive_record(archive: zipfile.ZipFile, name: str) -> dict:
    digest = hashlib.sha256()
    size = 0
    with archive.open(name, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"size_bytes": size, "sha256": digest.hexdigest()}


def safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe archive path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Unsafe archive path: {value!r}")
    return path


def _inside(root: Path, rel: str, *, must_exist: bool = True) -> Path:
    safe = safe_relative(rel)
    path = (root / Path(*safe.parts)).resolve(strict=must_exist)
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes root: {rel}") from exc
    if must_exist and not path.is_file():
        raise ValueError(f"Expected a regular file: {rel}")
    return path


def _json(path: Path, context: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {context} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object: {path}")
    return value


def _canonical_config(record: dict) -> dict:
    source = record.get("source")
    build = record.get("build")
    if not isinstance(source, dict) or not isinstance(build, dict):
        raise ValueError("Canonical dataset record must contain source and build objects")
    if set(source) & set(build):
        raise ValueError("Canonical source/build keys overlap")
    if not isinstance(record.get("id"), str) or not isinstance(record.get("title"), str):
        raise ValueError("Canonical dataset record needs id and title")
    return {"id": record["id"], "title": record["title"], **source, **build}


def _effective_config_sha(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def _check_reports(manifest: dict, manifest_bytes: bytes, reports_dir: Path) -> dict[str, bytes]:
    expected_binding = sha256_bytes(manifest_bytes)
    reports: dict[str, bytes] = {}
    values: dict[str, dict] = {}
    for name in REQUIRED_REPORTS:
        path = reports_dir / name
        if not path.is_file():
            raise ValueError(f"Missing required report: {name}")
        raw = path.read_bytes()
        report = _json(path, "verification report")
        if report.get("release_manifest_sha256") != expected_binding:
            raise ValueError(f"Report {name} is stale or not bound to this release manifest")
        values[name] = report
        reports[name] = raw

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError("Manifest source must be the flattened canonical build configuration")
    source_sha = source.get("source_sha256")
    expected_rows = source.get("expected_rows")
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise ValueError("Manifest source.source_sha256 must be a verified SHA-256")
    if isinstance(expected_rows, bool) or not isinstance(expected_rows, int) or expected_rows <= 0:
        raise ValueError("Manifest source.expected_rows must be a positive verified count")
    validation = values["validation.json"]
    if validation.get("status") != "passed":
        raise ValueError("Conversion validation did not pass")
    if validation.get("source_rows") != source.get("expected_rows"):
        raise ValueError("Validation source_rows differs from manifest source.expected_rows")
    if validation.get("source_sha256") != source.get("source_sha256"):
        raise ValueError("Validation source_sha256 differs from manifest source.source_sha256")
    http = validation.get("http", {})
    if (not isinstance(http, dict) or http.get("status") != "passed"
            or http.get("range_and_cors") is not True
            or isinstance(http.get("duckdb_spatial_subset_rows"), bool)
            or not isinstance(http.get("duckdb_spatial_subset_rows"), int)
            or http.get("duckdb_spatial_subset_rows") < 1
            or http.get("partitions_read") != 7):
        raise ValueError("Loopback HTTP range and spatial subset validation did not pass")
    catalog = validation.get("catalog", {})
    if not isinstance(catalog, dict) or catalog.get("status") != "passed":
        raise ValueError("Catalog validation did not pass")
    pmtiles = validation.get("pmtiles", {})
    if (not isinstance(pmtiles, dict) or pmtiles.get("status") != "passed"
            or pmtiles.get("structure_verified") is not True
            or pmtiles.get("all_tile_ids_and_attributes_checked") is not True):
        raise ValueError("PMTiles validation did not exhaustively pass IDs and attributes")
    sampled = pmtiles.get("geometry_features_checked")
    if isinstance(sampled, bool) or not isinstance(sampled, int) or sampled < 1:
        raise ValueError("PMTiles validation did not check any display geometries")
    max_error = pmtiles.get("maximum_sampled_error_tile_units")
    allowed_error = pmtiles.get("maximum_allowed_error_tile_units")
    if (isinstance(max_error, bool) or not isinstance(max_error, (int, float))
            or isinstance(allowed_error, bool) or not isinstance(allowed_error, (int, float))
            or not math.isfinite(max_error) or not math.isfinite(allowed_error)
            or max_error < 0 or max_error > allowed_error or allowed_error != 4.0):
        raise ValueError("PMTiles geometry sampling did not pass the four tile-unit contract")
    geometry_records = validation.get("exact_geometry_records", validation.get("source_geometry_records"))
    if geometry_records != expected_rows:
        raise ValueError("Exact source geometry records differ from expected_rows")
    geoparquet = validation.get("geoparquet", {})
    if (not isinstance(geoparquet, dict) or geoparquet.get("status") != "passed"
            or geoparquet.get("rows") != expected_rows):
        raise ValueError("GeoParquet validation is missing a passed row-count receipt")
    partitions = geoparquet.get("partitions")
    if isinstance(partitions, bool) or not isinstance(partitions, int) or partitions != 7:
        raise ValueError("GeoParquet validation must report all seven regional partitions")

    stac = values["stac-validation.json"]
    if (stac.get("status") != "passed" or stac.get("validated_documents") != 2
            or stac.get("invalid") != 0 or stac.get("skipped") != 0):
        raise ValueError("STAC validation must pass for exactly two documents with no invalid or skipped documents")

    portolan = values["portolan-validation.json"]
    if portolan.get("status") != "passed" or portolan.get("exit_code") != 0:
        raise ValueError("Portolan validation did not pass")
    raw_portolan = next((portolan[key] for key in ("rawresult", "raw_result", "result") if key in portolan), None)
    if (not isinstance(raw_portolan, dict) or raw_portolan.get("passed") is not True
            or raw_portolan.get("error_count") != 0 or raw_portolan.get("files_checked") != 2):
        raise ValueError("Portolan raw result must certify both documents with no errors")

    assets = manifest.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise ValueError("Manifest assets must be a non-empty object")
    reproduction = values["reproducibility.json"]
    if (reproduction.get("status") != "passed" or reproduction.get("manifest_equal") is not True
            or reproduction.get("conversion_git_commit") != manifest.get("conversion_git_commit")):
        raise ValueError("Reproducibility report is incomplete or refers to a different conversion commit")
    hashes = reproduction.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(assets):
        raise ValueError("Reproducibility hashes must match every manifest asset exactly")
    if reproduction.get("assets_compared") != len(assets):
        raise ValueError("Reproducibility assets_compared differs from manifest assets")
    for rel, item in assets.items():
        safe_relative(rel)
        if not isinstance(item, dict) or hashes.get(rel) != item.get("sha256"):
            raise ValueError(f"Reproducibility hash differs from manifest asset: {rel}")

    faults = values["fault-tests.json"]
    if faults.get("status") != "passed":
        raise ValueError("Fault tests did not pass")
    cases = faults.get("cases")
    if isinstance(cases, list):
        case_rows = cases
    else:
        if isinstance(cases, bool) or not isinstance(cases, int):
            raise ValueError("Fault test cases must report a count or a list")
        case_rows = faults.get("tests", faults.get("results", faults.get("checks")))
        if not isinstance(case_rows, list) or len(case_rows) != cases:
            raise ValueError("Fault test report must include the actual result for every case")
    if len(case_rows) < 4:
        raise ValueError("At least four fault cases are required")
    for i, case in enumerate(case_rows):
        if not isinstance(case, dict) or not (
            case.get("status") == "passed" or case.get("passed") is True or case.get("exit_code") == 0
        ):
            raise ValueError(f"Fault test case {i} did not record an actual passed result")
    return reports


def _manifest_assets(manifest: dict) -> dict[str, dict]:
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise ValueError("Manifest assets must be a non-empty object")
    for rel, record in assets.items():
        safe_relative(rel)
        if not isinstance(record, dict) or isinstance(record.get("size_bytes"), bool) or not isinstance(record.get("size_bytes"), int):
            raise ValueError(f"Asset {rel} has no valid size_bytes")
        if record.get("size_bytes") < 0 or not isinstance(record.get("sha256"), str) or len(record["sha256"]) != 64:
            raise ValueError(f"Asset {rel} has invalid size/hash metadata")
    missing = {"catalog.json", "grip/collection.json", "grip/original-attribute-dictionary.xlsx"} - set(assets)
    if missing:
        raise ValueError(f"Release manifest is missing catalog documents: {sorted(missing)}")
    if not any(name.endswith(".parquet") for name in assets):
        raise ValueError("Release manifest has no analytic GeoParquet asset")
    if not any(name.endswith(".pmtiles") for name in assets):
        raise ValueError("Release manifest has no PMTiles display asset")
    return assets


def _verify_release(release: Path, manifest: dict, manifest_bytes: bytes) -> tuple[dict[str, Path], dict[str, bytes]]:
    assets = _manifest_assets(manifest)
    record_path = release / "dataset.yaml"
    if not record_path.is_file():
        raise ValueError("Release is missing its dataset.yaml snapshot")
    record_bytes = record_path.read_bytes()
    expected_record_sha = manifest.get("dataset_record_sha256_at_build")
    if not isinstance(expected_record_sha, str) or sha256_bytes(record_bytes) != expected_record_sha:
        raise ValueError("Release dataset.yaml snapshot hash differs from manifest")
    try:
        record = yaml.safe_load(record_bytes)
    except yaml.YAMLError as exc:
        raise ValueError(f"Release dataset.yaml is invalid: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError("Release dataset.yaml must contain a mapping")
    canonical_record = (HERE / "dataset.yaml").read_bytes()
    if record_bytes != canonical_record:
        raise ValueError("Release dataset.yaml is not the current canonical snapshot")
    config = _canonical_config(record)
    if manifest.get("effective_config_sha256") != _effective_config_sha(config):
        raise ValueError("Manifest effective_config_sha256 does not match the canonical flattened config")
    if manifest.get("source") != config:
        raise ValueError("Manifest source config differs from canonical source/build configuration")
    if record.get("id") != "grip":
        raise ValueError("Release dataset.yaml is not the GRIP canonical record")

    inputs = manifest.get("build_input_sha256")
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("Manifest build_input_sha256 must be a non-empty object")
    workflow: dict[str, bytes] = {}
    for rel, expected in inputs.items():
        path = _inside(HERE, rel)
        raw = path.read_bytes()
        if not isinstance(expected, str) or sha256_bytes(raw) != expected:
            raise ValueError(f"Current workflow input differs from manifest: {rel}")
        workflow[f"workflow/datasets/grip/{safe_relative(rel).as_posix()}"] = raw

    # The manifest is the sole self-excluded file. The dataset snapshot may also
    # be an asset; its dedicated snapshot hash is checked above as well.
    actual_paths: set[str] = set()
    for path in release.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Release contains a symlink: {path.relative_to(release)}")
        if path.is_file():
            rel = path.relative_to(release).as_posix()
            if rel != "manifest.json":
                actual_paths.add(rel)
    if actual_paths != set(assets):
        missing = sorted(set(assets) - actual_paths)
        extra = sorted(actual_paths - set(assets))
        raise ValueError(f"Release file inventory differs from manifest assets (missing={missing}, extra={extra})")

    payloads: dict[str, Path] = {"manifest.json": release / "manifest.json", "dataset.yaml": record_path}
    for rel, item in assets.items():
        path = _inside(release, rel)
        actual = _file_record(path)
        if actual["size_bytes"] != item["size_bytes"] or actual["sha256"] != item["sha256"]:
            raise ValueError(f"Release asset bytes differ from manifest: {rel}")
        payloads[rel] = path

    for name in ("LICENSE", "NOTICE"):
        path = REPO_ROOT / name
        if not path.is_file():
            raise ValueError(f"Repository is missing required {name}")
        workflow[f"workflow/{name}"] = path.read_bytes()
    workflow["workflow/datasets/grip/dataset.yaml"] = record_bytes
    workflow_readme = (
        "# GRIP4 build workflow snapshot\n\n"
        "The exact build inputs recorded by the release manifest are preserved under `datasets/grip/`, together with the exact canonical `dataset.yaml` snapshot. "
        "The repository-level `LICENSE` and `NOTICE` are included under `workflow/`. These files are a code and provenance snapshot, not a standalone checkout: the bundle contains no `.git` history and no pinned source archive.\n\n"
        f"To reproduce, use a clean Git checkout at conversion commit `{manifest.get('conversion_git_commit')}`, verify each build input against `build_input_sha256` in the release `manifest.json`, "
        "provide the verified GRIP4 source archive and extracted cache described by the dataset workflow, install the locked environment and pinned system tools, then run `uv run --project datasets/grip python datasets/grip/build.py --source-cache <cache> --output <new-release>`. "
        "The exact source bytes are identified by `source.source_sha256`. Choose a new output directory; release directories are immutable.\n"
    ).encode()
    workflow["workflow/README.md"] = workflow_readme
    return payloads, workflow


def _zip_info(name: str) -> zipfile.ZipInfo:
    safe_relative(name)
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def check_archive(path: Path) -> dict:
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive member")
        for name in names:
            safe_relative(name)
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC validation failed")
        if names != sorted(names):
            raise ValueError("Archive members are not path-sorted")
        if any(info.date_time != FIXED_ZIP_TIME or info.compress_type != zipfile.ZIP_STORED for info in infos):
            raise ValueError("Archive timestamp or storage method is not deterministic")
        package_manifest = _json_bytes(archive.read("package-manifest.json"), "package-manifest.json")
        expected: set[str] = {"package-manifest.json"}
        for section in ("release_files", "workflow_files", "reports"):
            items = package_manifest.get(section)
            if not isinstance(items, dict):
                raise ValueError(f"Package manifest missing {section}")
            for name, item in items.items():
                safe_relative(name)
                expected.add(name)
                if not isinstance(item, dict) or "sha256" not in item or "size_bytes" not in item:
                    raise ValueError(f"Malformed package hash record: {name}")
                actual = _archive_record(archive, name)
                if actual["size_bytes"] != item["size_bytes"] or actual["sha256"] != item["sha256"]:
                    raise ValueError(f"Package member hash mismatch: {name}")
        manifest_raw = archive.read("manifest.json")
        if package_manifest.get("release_manifest_sha256") != sha256_bytes(manifest_raw):
            raise ValueError("Package manifest is bound to a different release manifest")
        release_manifest = _json_bytes(manifest_raw, "manifest.json")
        dataset_record = archive.read("dataset.yaml")
        if sha256_bytes(dataset_record) != release_manifest.get("dataset_record_sha256_at_build"):
            raise ValueError("Archived dataset.yaml does not match the build-time snapshot hash")
        embedded_assets = release_manifest.get("assets")
        packaged_release_files = package_manifest.get("release_files", {})
        required_release_files = {"manifest.json", *embedded_assets.keys()}
        if set(packaged_release_files) != required_release_files:
            raise ValueError("Package release file inventory differs from the release manifest")
        for name, expected_asset in embedded_assets.items():
            if packaged_release_files.get(name) != {
                "size_bytes": expected_asset.get("size_bytes"), "sha256": expected_asset.get("sha256")
            }:
                raise ValueError(f"Package manifest asset binding differs from release manifest: {name}")
        snapshot_member = "workflow/datasets/grip/dataset.yaml"
        if (package_manifest.get("workflow_snapshot_sha256") != package_manifest.get("workflow_files", {}).get(snapshot_member, {}).get("sha256")
                or package_manifest.get("workflow_snapshot_sha256") != release_manifest.get("dataset_record_sha256_at_build")):
            raise ValueError("Bundled workflow dataset.yaml differs from the build-time snapshot")
        for name in package_manifest["workflow_files"]:
            if not safe_relative(name).as_posix().startswith("workflow/"):
                raise ValueError(f"Workflow member is outside workflow/: {name}")
        for name in package_manifest["reports"]:
            if not safe_relative(name).as_posix().startswith("reports/"):
                raise ValueError(f"Report member is outside reports/: {name}")
        if set(names) != expected:
            raise ValueError("Archive has missing or unexpected members")
    return {"status": "passed", "members_verified": len(names), "sha256": sha256_file(path)}


def _json_bytes(raw: bytes, context: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {context}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def package(release: Path, reports_dir: Path, output: Path) -> dict:
    release = Path(release).resolve()
    reports_dir = Path(reports_dir).resolve()
    output = Path(output).absolute()
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    if not release.is_dir():
        raise ValueError(f"Release directory does not exist: {release}")
    if output.exists() or receipt_path.exists():
        raise ValueError("Archive or receipt already exists; choose a new output")
    try:
        output.resolve(strict=False).relative_to(release)
    except ValueError:
        pass
    else:
        raise ValueError("Package output must be outside the release directory")

    manifest_path = release / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = _json_bytes(manifest_bytes, "manifest.json")
    report_bytes = _check_reports(manifest, manifest_bytes, reports_dir)
    release_files, workflow_files = _verify_release(release, manifest, manifest_bytes)

    package_manifest = {
        "status": "locally_packaged_not_published",
        "dataset": "grip",
        "release": manifest.get("release"),
        "conversion_git_commit": manifest.get("conversion_git_commit"),
        "release_manifest_sha256": sha256_bytes(manifest_bytes),
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_note": "The selected Zenodo record's structured license field says CC BY 4.0, while its prose and PBL producer page also mention CC0; this package follows the structured CC BY 4.0 field and preserves attribution pending clarification.",
        "workflow_code_license": "Apache-2.0",
        "workflow_snapshot_sha256": manifest["dataset_record_sha256_at_build"],
        "release_files": {
            name: _file_record(path)
            for name, path in release_files.items()
        },
        "workflow_files": {},
        "reports": {},
        "limits": [
            "No GEE comparison or cloud export is part of this package.",
            "No upload, registry submission, or public hosting is performed.",
        ],
    }
    # Workflow payloads are precisely the checked build inputs and repository notices.
    package_manifest["workflow_files"] = {
        name: {"size_bytes": len(data), "sha256": sha256_bytes(data)}
        for name, data in workflow_files.items()
    }
    report_entries = {f"reports/{name}": raw for name, raw in report_bytes.items()}
    package_manifest["reports"] = {
        name: {"size_bytes": len(data), "sha256": sha256_bytes(data)}
        for name, data in report_entries.items()
    }

    entries: dict[str, bytes | Path] = {**release_files, **workflow_files, **report_entries}
    entries["package-manifest.json"] = (json.dumps(package_manifest, indent=2, sort_keys=True) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    archive_temp = None
    receipt_temp = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".grip-package-", suffix=".zip", dir=output.parent, delete=False) as tmp:
            archive_temp = Path(tmp.name)
        with zipfile.ZipFile(archive_temp, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, value in sorted(entries.items()):
                info = _zip_info(name)
                if isinstance(value, Path):
                    with value.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
                else:
                    with archive.open(info, "w", force_zip64=True) as target:
                        target.write(value)
        checked = check_archive(archive_temp)
        receipt = {
            "status": "locally_packaged_not_published",
            "archive": {"path": str(output), "size_bytes": archive_temp.stat().st_size, "sha256": checked["sha256"]},
            "release_manifest_sha256": sha256_bytes(manifest_bytes),
            "package_manifest_sha256": sha256_bytes(entries["package-manifest.json"]),
            "members_verified": checked["members_verified"],
        }
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".grip-package-receipt-", suffix=".json", dir=output.parent, delete=False) as tmp:
            receipt_temp = Path(tmp.name)
            tmp.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        if output.exists() or receipt_path.exists():
            raise ValueError("Archive or receipt appeared while package was being built")
        os.link(archive_temp, output)
        try:
            os.link(receipt_temp, receipt_path)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return receipt
    finally:
        if archive_temp:
            archive_temp.unlink(missing_ok=True)
        if receipt_temp:
            receipt_temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path, help="built immutable release directory")
    parser.add_argument("--reports", type=Path, required=True, help="directory containing five bound verification reports")
    parser.add_argument("--output", type=Path, required=True, help="new ZIP path; existing outputs are never overwritten")
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.release, args.reports, args.output), indent=2))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, yaml.YAMLError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
