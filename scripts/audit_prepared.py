#!/usr/bin/env python3
"""Read-only integrity audit for manifest-declared prepared release assets.

The audit verifies package manifest bindings, local manifest identity, declared
asset sizes/SHA-256 values, and catalog-input snapshot hashes. It deliberately
does not rerun scientific, release, browser, hosting, or registry checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import yaml

CHUNK_BYTES = 8 * 1024 * 1024


class AuditError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read JSON {path}: {exc}") from exc


def safe_package_file(package: Path, relpath: str) -> Path:
    relative = Path(relpath)
    if relative.is_absolute() or ".." in relative.parts:
        raise AuditError(f"unsafe package asset path: {relpath}")
    candidate = package / relative
    try:
        resolved_package = package.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(str(candidate)) from exc
    if not resolved.is_relative_to(resolved_package):
        raise AuditError(f"asset resolves outside package root: {relpath}")
    if not resolved.is_file():
        raise AuditError(f"asset is not a regular file: {relpath}")
    return resolved


def asset_declarations(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the two manifest forms used by prepared releases.

    Modern shared-package manifests declare analytic assets as a list and
    display derivatives separately. Earlier release manifests declare a path
    to {sha256, size_bytes} map. Other formats fail closed.
    """
    assets = manifest.get("assets")
    result: list[dict[str, Any]] = []
    if isinstance(assets, list):
        for entry in assets:
            if not isinstance(entry, dict):
                raise AuditError("modern manifest assets must be objects")
            result.append({
                "path": entry.get("href"),
                "sha256": entry.get("sha256"),
                "size_bytes": entry.get("size_bytes"),
                "kind": "data_asset",
            })
        derivatives = manifest.get("display_derivatives", [])
        if not isinstance(derivatives, list):
            raise AuditError("display_derivatives must be a list when present")
        for entry in derivatives:
            if not isinstance(entry, dict):
                raise AuditError("display derivative declarations must be objects")
            result.append({
                "path": entry.get("path"),
                "sha256": entry.get("sha256"),
                "size_bytes": entry.get("size_bytes"),
                "kind": "display_derivative",
            })
    elif isinstance(assets, dict):
        for relpath, entry in assets.items():
            if not isinstance(entry, dict):
                raise AuditError("legacy manifest asset entries must be objects")
            result.append({
                "path": relpath,
                "sha256": entry.get("sha256"),
                "size_bytes": entry.get("size_bytes"),
                "kind": "manifest_asset",
            })
    else:
        raise AuditError("unsupported manifest assets format")

    if not result:
        raise AuditError("prepared manifest must declare at least one asset")
    seen: set[str] = set()
    for entry in result:
        relpath = entry.get("path")
        sha = entry.get("sha256")
        size = entry.get("size_bytes")
        if not isinstance(relpath, str) or not relpath:
            raise AuditError("asset declaration is missing a path")
        if relpath in seen:
            raise AuditError(f"duplicate asset declaration: {relpath}")
        seen.add(relpath)
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower()):
            raise AuditError(f"asset has invalid SHA-256 declaration: {relpath}")
        if type(size) is not int or size < 0:
            raise AuditError(f"asset has invalid size_bytes declaration: {relpath}")
    return result


def verify_assets(package: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    declarations = asset_declarations(manifest)
    results = []
    for declared in declarations:
        item = dict(declared)
        relpath = declared["path"]
        try:
            path = safe_package_file(package, relpath)
            actual_size = path.stat().st_size
            actual_sha = sha256_file(path)
            item.update({
                "observed_size_bytes": actual_size,
                "observed_sha256": actual_sha,
                "size_match": actual_size == declared["size_bytes"],
                "sha256_match": actual_sha == declared["sha256"],
                "status": "passed" if actual_size == declared["size_bytes"] and actual_sha == declared["sha256"] else "failed",
            })
        except FileNotFoundError as exc:
            item.update({"status": "failed", "error": f"missing asset: {exc}"})
        except (OSError, AuditError) as exc:
            item.update({"status": "failed", "error": str(exc)})
        results.append(item)
    return {
        "status": "passed" if all(item["status"] == "passed" for item in results) else "failed",
        "declared_asset_count": len(results),
        "verified_bytes": sum(item.get("observed_size_bytes", 0) for item in results),
        "assets": results,
    }


def expected_record_identity(record: dict[str, Any]) -> tuple[str, str]:
    dataset_id = record.get("id")
    publication = record.get("publication") or {}
    release_id = publication.get("release")
    if not isinstance(dataset_id, str) or not isinstance(release_id, str):
        raise AuditError("canonical record lacks id or publication.release")
    return dataset_id, release_id


def manifest_identity(manifest: dict[str, Any]) -> tuple[str | None, str | None]:
    dataset_id = manifest.get("dataset_id", manifest.get("dataset"))
    release_id = manifest.get("release_id", manifest.get("release"))
    if isinstance(release_id, dict):
        release_id = release_id.get("id") or release_id.get("release_id")
    if not isinstance(dataset_id, str) or not isinstance(release_id, str):
        return None, None
    return dataset_id, release_id


def audit_dataset(root: Path, dataset_id: str, package: Path) -> dict[str, Any]:
    record_path = root / "datasets" / dataset_id / "dataset.yaml"
    try:
        record = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AuditError(f"cannot read canonical record {record_path}: {exc}") from exc
    if not isinstance(record, dict):
        raise AuditError(f"canonical record is not a YAML object: {record_path}")
    canonical_id, selected_release = expected_record_identity(record)
    if canonical_id != dataset_id:
        raise AuditError(f"record id {canonical_id!r} does not match mapping {dataset_id!r}")

    publication = record["publication"]
    manifest_rel = publication.get("manifest_path")
    manifest_sha = publication.get("manifest_sha256")
    if not isinstance(manifest_rel, str) or not isinstance(manifest_sha, str):
        raise AuditError(f"{dataset_id}: canonical record lacks manifest path/hash")
    tracked_manifest_path = safe_package_file(root, manifest_rel)
    tracked_manifest_sha = sha256_file(tracked_manifest_path)
    tracked_manifest = read_json(tracked_manifest_path)
    local_manifest_path = package / "manifest.json"
    local_manifest_sha = sha256_file(local_manifest_path)
    local_manifest = read_json(local_manifest_path)

    observed_identity = manifest_identity(local_manifest)
    identity_match = observed_identity == (dataset_id, selected_release)
    manifest_hash_match = tracked_manifest_sha == manifest_sha and local_manifest_sha == manifest_sha
    if tracked_manifest != local_manifest:
        identity_match = False

    catalog = publication.get("catalog") or {}
    snapshot_rel = catalog.get("snapshot_path")
    snapshot_expected = catalog.get("snapshot_sha256")
    snapshot_result: dict[str, Any] = {"path": snapshot_rel, "expected_sha256": snapshot_expected}
    if isinstance(snapshot_rel, str) and isinstance(snapshot_expected, str):
        snapshot_path = safe_package_file(root, snapshot_rel)
        try:
            actual_snapshot_sha = sha256_file(snapshot_path)
            snapshot_result.update({
                "observed_sha256": actual_snapshot_sha,
                "status": "passed" if actual_snapshot_sha == snapshot_expected else "failed",
            })
        except OSError as exc:
            snapshot_result.update({"status": "failed", "error": str(exc)})
    else:
        snapshot_result.update({"status": "failed", "error": "snapshot path/hash missing"})

    assets = verify_assets(package, local_manifest)
    integrity_status = "passed" if manifest_hash_match and identity_match and snapshot_result["status"] == "passed" and assets["status"] == "passed" else "failed"
    local_gates = {
        "classification": "retained_canonical_record_values_not_rerun",
        "validation_summary": publication.get("validation"),
        "validation_paths": publication.get("validation_evidence", publication.get("validation_evidence_paths", publication.get("validation_path"))),
        "source_fidelity_report": publication.get("source_fidelity_report_path"),
        "release_receipt_path": publication.get("release_receipt_path"),
    }
    missing_host_fields = [name for name in ("package_base_url", "hosting_report_path", "hosting_report_sha256") if not catalog.get(name)]
    return {
        "dataset_id": dataset_id,
        "release": selected_release,
        "integrity_status": integrity_status,
        "local_integrity": {
            "package_path_observed": str(package.resolve()),
            "tracked_manifest_path": manifest_rel,
            "tracked_manifest_expected_sha256": manifest_sha,
            "tracked_manifest_observed_sha256": tracked_manifest_sha,
            "local_manifest_observed_sha256": local_manifest_sha,
            "manifest_hash_match": manifest_hash_match,
            "manifest_identity": {"dataset_id": observed_identity[0], "release": observed_identity[1], "matches_record": identity_match},
            "snapshot": snapshot_result,
            "declared_assets": assets,
        },
        "retained_local_gates": local_gates,
        "public_hosting": {
            "package_base_url": catalog.get("package_base_url"),
            "hosting_report_path": catalog.get("hosting_report_path"),
            "hosting_report_sha256": catalog.get("hosting_report_sha256"),
            "missing_fields": missing_host_fields,
            "registry_status": (publication.get("portolan") or {}).get("status"),
        },
    }


def parse_mapping(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("mapping must be DATASET_ID=/absolute/package/path")
    dataset_id, path = raw.split("=", 1)
    if not dataset_id or not path:
        raise argparse.ArgumentTypeError("mapping must be DATASET_ID=/absolute/package/path")
    return dataset_id, Path(path).expanduser()


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="repository/worktree root with datasets/ and catalog.publish.yaml")
    parser.add_argument("--package", action="append", type=parse_mapping, required=True, metavar="ID=PATH", help="explicit local package path mapping; repeat per dataset")
    parser.add_argument("--output", type=Path, required=True, help="new JSON report path; existing paths are refused")
    args = parser.parse_args(argv)

    out = args.output.expanduser()
    if os.path.lexists(out):
        print(f"refusing to overwrite existing output: {out}", file=sys.stderr)
        return 2
    root = args.root.expanduser().resolve()
    mappings = dict(args.package)
    if len(mappings) != len(args.package):
        print("duplicate --package dataset mapping", file=sys.stderr)
        return 2

    results = []
    for dataset_id, package in args.package:
        try:
            results.append(audit_dataset(root, dataset_id, package.expanduser()))
        except (OSError, AuditError, json.JSONDecodeError) as exc:
            results.append({"dataset_id": dataset_id, "integrity_status": "failed", "error": str(exc)})

    config_path = root / "catalog.publish.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        config = {"read_error": str(exc)}
    report = {
        "schema_version": 1,
        "audit_type": "local_integrity_only",
        "created_by": "scripts/audit_prepared.py",
        "root": str(root),
        "hash_algorithm": "SHA-256",
        "stream_buffer_bytes": CHUNK_BYTES,
        "scope": "Manifest-declared data assets and display derivatives; supporting files are excluded for modern list-format manifests. Legacy map-format assets are verified in full.",
        "scientific_checks_rerun": False,
        "publication_checks_rerun": False,
        "packages": results,
        "catalog_publish_config": {
            "hosting_url": (config.get("navigation") or {}).get("hosting_url"),
            "browser_url_template": (config.get("navigation") or {}).get("browser_url_template"),
            "destination": (config.get("publish") or {}).get("destination"),
            "public_base": (config.get("publish") or {}).get("public_base"),
            "region": (config.get("publish") or {}).get("region"),
            "missing_fields": [name for name, value in {
                "navigation.hosting_url": (config.get("navigation") or {}).get("hosting_url"),
                "navigation.browser_url_template": (config.get("navigation") or {}).get("browser_url_template"),
                "publish.destination": (config.get("publish") or {}).get("destination"),
                "publish.public_base": (config.get("publish") or {}).get("public_base"),
                "publish.region": (config.get("publish") or {}).get("region"),
            }.items() if not value],
        },
        "status": "passed" if len(results) == len(args.package) and all(x.get("integrity_status") == "passed" for x in results) else "failed",
    }
    try:
        out.parent.mkdir(parents=False, exist_ok=True)
        with out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except FileExistsError:
        print(f"refusing to overwrite existing output: {out}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cannot write report {out}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "output": str(out), "packages": len(results)}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(run())
