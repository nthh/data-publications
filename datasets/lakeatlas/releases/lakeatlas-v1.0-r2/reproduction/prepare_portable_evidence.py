#!/usr/bin/env python3
"""Copy validated LakeATLAS r2 reports with local path prefixes redacted."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


REPORT_NAMES = (
    "source-fidelity.json", "clean-rebuild.json",
    "spatial-order-polygons-primary.json", "spatial-order-pour-points-primary.json",
    "spatial-pruning-polygons-primary.json", "spatial-pruning-pour-points-primary.json",
    "spatial-order-polygons-clean.json", "spatial-order-pour-points-clean.json",
    "spatial-pruning-polygons-clean.json", "spatial-pruning-pour-points-clean.json",
)
PRUNING_TO_SPATIAL = {
    "spatial-pruning-polygons-primary.json": "spatial-order-polygons-primary.json",
    "spatial-pruning-pour-points-primary.json": "spatial-order-pour-points-primary.json",
    "spatial-pruning-polygons-clean.json": "spatial-order-polygons-clean.json",
    "spatial-pruning-pour-points-clean.json": "spatial-order-pour-points-clean.json",
}

def validate_report_bundle(reports: dict[str, dict[str, Any]]) -> None:
    """Require all ten reports to pass and each pruning receipt to bind its asset."""
    if set(reports) != set(REPORT_NAMES):
        raise ValueError("portable evidence input set differs from the ten required LakeATLAS reports")
    for name, report in reports.items():
        if not isinstance(report, dict) or report.get("status") != "passed":
            raise ValueError(f"required report is not passed: {name}")
    for pruning_name, spatial_name in PRUNING_TO_SPATIAL.items():
        pruning = reports[pruning_name]
        output = reports[spatial_name].get("output")
        if not isinstance(output, dict):
            raise ValueError(f"spatial report has no output fingerprint: {spatial_name}")
        spatial_sha, spatial_size = output.get("sha256"), output.get("size_bytes")
        pruning_sha, pruning_size = pruning.get("sha256"), pruning.get("size_bytes")
        if not isinstance(spatial_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", spatial_sha):
            raise ValueError(f"spatial report has an invalid output SHA-256: {spatial_name}")
        if not isinstance(spatial_size, int) or spatial_size <= 0:
            raise ValueError(f"spatial report has an invalid output size: {spatial_name}")
        if pruning_sha != spatial_sha or pruning_size != spatial_size:
            raise ValueError(f"pruning receipt does not bind the completed asset: {pruning_name}")


def redact(value: Any, prefixes: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {str(key): redact(item, prefixes) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, prefixes) for item in value]
    if isinstance(value, str):
        for prefix, token in prefixes.items():
            if value == prefix:
                return token
            if value.startswith(prefix + "/"):
                return token + value[len(prefix) :]
        return value
    return value


def git_value(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=path, text=True).strip()


def rebuild_environment(repo: Path, clean: Path) -> dict[str, Any]:
    clean_commit = git_value(clean, "rev-parse", "HEAD")
    clean_status = git_value(clean, "status", "--porcelain")
    clean_branch = git_value(clean, "branch", "--show-current")
    if clean_commit != "b6579442c8a0ba73e38b444f143bb6194ef056e5" or clean_status or clean_branch:
        raise ValueError("clean rebuild checkout must remain detached, clean, and pinned at b657944")
    lock_files = ("datasets/lakeatlas/uv.lock", "scripts/release_tools/uv.lock")
    lock_hashes = {}
    for relative in lock_files:
        repo_hash = sha256(repo / relative)
        clean_hash = sha256(clean / relative)
        if repo_hash != clean_hash:
            raise ValueError(f"clean checkout lock differs from repository: {relative}")
        lock_hashes[relative] = {"sha256": repo_hash, "repository_clean_checkout_bytes_equal": True}
    versions = {}
    for distribution in ("pyarrow", "numpy", "pyproj", "shapely"):
        versions[distribution] = importlib.metadata.version(distribution)
    return {
        "scope": "spatial_order clean rebuild and evidence-capture environment; raw conversion ran separately at the pinned raw-code revision",
        "clean_checkout": {"commit": clean_commit, "detached": True, "status_porcelain_empty": True},
        "workflow_revisions": {
            "raw_conversion": "691fc304a2df25d04c13652d6429ff0e32993be2",
            "spatial_order": "b6579442c8a0ba73e38b444f143bb6194ef056e5",
            "spatial_pruning_and_fidelity_binding": "7602b5e5252aec2f26167a7f560eaa7dd65a38a0",
            "package_helper": "7cc922857065883d1803a6892a5a160ce5a4f722",
        },
        "runtime": {
            "capture_scope": "runtime observed while preparing portable evidence; not an independent historical-runtime attestation for the raw conversion",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "interpreter_command": "${SHARED_LOCKED_RELEASE_TOOLS_ENV}/bin/python",
            "environment_source": "Shared release-tools virtual environment synchronized from the pinned project with uv sync --locked; the runner used this same environment for the spatial clean writer and completion process.",
            "distributions": versions,
        },
        "locked_environment": {"files": lock_hashes, "repository_and_clean_bytes_identical": True},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--fidelity-root", type=Path, required=True, help="directory created by bind_fidelity.py")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--clean-checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.artifact_root.expanduser().resolve()
    fidelity = args.fidelity_root.expanduser().resolve()
    repo = args.repo_root.expanduser().resolve()
    clean = args.clean_checkout.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    environment = rebuild_environment(repo, clean)
    prefixes = {
        str(fidelity): "${FIDELITY_ROOT}",
        str(artifacts): "${ARTIFACT_ROOT}",
        str(clean): "${CLEAN_CHECKOUT}",
        str(repo): "${REPO_ROOT}",
    }
    primary = artifacts / "releases/lakeatlas-v1.0-r2-spatial-primary-b657944/reports"
    clean_reports = artifacts / "releases/lakeatlas-v1.0-r2-spatial-clean-b657944/reports"
    inputs = [
        (fidelity / "source-fidelity.json", "source-fidelity.json"),
        (fidelity / "clean-rebuild.json", "clean-rebuild.json"),
        (primary / "lakeatlas-polygons-spatial.json", "spatial-order-polygons-primary.json"),
        (primary / "lakeatlas-pour-points-spatial.json", "spatial-order-pour-points-primary.json"),
        (primary / "pruning/lakeatlas-polygons.json", "spatial-pruning-polygons-primary.json"),
        (primary / "pruning/lakeatlas-pour-points.json", "spatial-pruning-pour-points-primary.json"),
        (clean_reports / "lakeatlas-polygons-spatial.json", "spatial-order-polygons-clean.json"),
        (clean_reports / "lakeatlas-pour-points-spatial.json", "spatial-order-pour-points-clean.json"),
        (clean_reports / "pruning/lakeatlas-polygons.json", "spatial-pruning-polygons-clean.json"),
        (clean_reports / "pruning/lakeatlas-pour-points.json", "spatial-pruning-pour-points-clean.json"),
    ]
    loaded: dict[str, dict[str, Any]] = {}
    originals: dict[str, tuple[Path, str]] = {}
    for source, name in inputs:
        if not source.is_file():
            raise FileNotFoundError(f"required passed report is missing: {source.name}")
        original_sha = sha256(source)
        value = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"report is not a JSON object: {source.name}")
        loaded[name] = value
        originals[name] = (source, original_sha)
    validate_report_bundle(loaded)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    environment_bytes = json.dumps(environment, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    portable_environment = redact(environment, prefixes)
    for name in REPORT_NAMES:
        source, original_sha = originals[name]
        value = loaded[name]
        portable = redact(value, prefixes)
        target = output / name
        target.write_text(json.dumps(portable, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        serialized = target.read_text(encoding="utf-8")
        if any(marker in serialized for marker in ("/Users/", "/private/", "/Volumes/")):
            raise ValueError(f"absolute machine path remains in portable report {name}")
        records.append({
            "report": name,
            "original_path_token": next((token + "/" + source.relative_to(Path(prefix)).as_posix()
                                          for prefix, token in prefixes.items()
                                          if source.is_relative_to(Path(prefix))), "${EXTERNAL_REPORT}/" + source.name),
            "original_sha256": original_sha,
            "portable_path": name,
            "portable_sha256": sha256(target),
        })
    environment_path = output / "rebuild-environment.json"
    environment_path.write_text(json.dumps(portable_environment, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    records.append({
        "report": "rebuild-environment.json",
        "original_path_token": "${GENERATED_CONTEXT}/clean-rebuild-environment",
        "original_sha256": hashlib.sha256(environment_bytes).hexdigest(),
        "portable_path": "rebuild-environment.json",
        "portable_sha256": sha256(environment_path),
    })
    provenance = {
        "dataset_id": "lakeatlas",
        "release_id": "lakeatlas-v1.0-r2",
        "path_redaction": "Only local filesystem path prefixes are replaced with portable tokens; report values and validation results are retained.",
        "reports": records,
    }
    (output / "evidence-provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
