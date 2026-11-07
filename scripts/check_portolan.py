#!/usr/bin/env python3
"""Run pinned, offline Portolan/STAC checks and write a machine-readable report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PORTOLAN_PROJECT = ROOT / "tools/portolan"
PINS_PATH = PORTOLAN_PROJECT / "pins.json"
OFFLINE_CLI = PORTOLAN_PROJECT / "offline_cli.py"


def read_pins() -> dict:
    return json.loads(PINS_PATH.read_text(encoding="utf-8"))


def version_check(name: str, expected: str) -> dict:
    try:
        observed = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        observed = None
    return {"expected": expected, "observed": observed, "matches": observed == expected}


def reserve_report(path: Path, catalog: Path) -> int:
    path = path.absolute()
    catalog = catalog.resolve(strict=True)
    resolved_path = path.resolve(strict=False)
    if resolved_path == catalog or catalog in resolved_path.parents:
        raise ValueError("Report path must be outside the catalog tree")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Report already exists: {path}")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(path, flags, 0o644)
    return fd


def validator_files(catalog: Path) -> list[Path]:
    if not catalog.is_dir() or catalog.is_symlink():
        raise ValueError(f"Catalog must be an existing regular directory: {catalog}")
    paths = []
    for path in sorted(catalog.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Catalog contains symlink: {path.relative_to(catalog)}")
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("type") in ("Catalog", "Collection", "Feature", "ItemCollection"):
            paths.append(path)
    if not paths:
        raise ValueError("Catalog contains no local STAC Catalog, Collection, Feature, or ItemCollection JSON")
    return paths


def parse_rashid(stdout: str) -> dict | None:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        # Keep support for a tool preamble, but require one complete JSON object.
        start = stdout.find("{")
        if start < 0:
            return None
        try:
            parsed = json.loads(stdout[start:])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def run_offline_cli(tool: str, args: list[str], *, cwd: Path) -> dict:
    command = [sys.executable, str(OFFLINE_CLI), tool, *args]
    try:
        cp = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=120)
        return {"command": command, "exit_code": cp.returncode,
                "stdout": cp.stdout, "stderr": cp.stderr, "launch_error": None}
    except subprocess.TimeoutExpired as exc:
        def decoded(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        return {"command": command, "exit_code": None, "stdout": decoded(exc.stdout),
                "stderr": decoded(exc.stderr), "launch_error": "Validator exceeded 120 seconds"}
    except OSError as exc:
        return {"command": command, "exit_code": None, "stdout": "", "stderr": "",
                "launch_error": f"{type(exc).__name__}: {exc}"}


def run_gate(catalog: Path, report_path: Path, *, local_data: bool = False) -> tuple[dict, int]:
    if catalog.is_symlink():
        raise ValueError("Catalog root must not be a symlink")
    catalog = catalog.resolve(strict=True)
    report_path = report_path.absolute()
    report_fd = reserve_report(report_path, catalog)
    pins = read_pins()
    versions = {tool: version_check(tool, expected) for tool, expected in pins["tools"].items()}
    scope = "local_data" if local_data else "schema_stac_extensions_metadata_only"
    rashid_args = ["check", str(catalog), "--schema", "--no-live", "--json"]
    if local_data:
        rashid_args += ["--data-scope", "local"]
    else:
        rashid_args += ["--no-data"]
    rashid_process = run_offline_cli("rashid", rashid_args, cwd=ROOT)
    rashid_report = parse_rashid(rashid_process["stdout"])
    rashid_pass = bool(rashid_process["exit_code"] == 0 and rashid_report is not None
                       and rashid_report.get("passed") is True
                       and rashid_report.get("error_count") == 0
                       and rashid_report.get("warning_count") == 0
                       and not rashid_process["launch_error"]
                       and versions["rashid"]["matches"])
    try:
        files = validator_files(catalog)
        enumeration_error = None
    except (OSError, ValueError) as exc:
        files = []
        enumeration_error = f"{type(exc).__name__}: {exc}"
    stac_results = []
    for path in files:
        process = run_offline_cli("stac-check", [str(path), "--no-assets-urls"], cwd=ROOT)
        stderr = process.get("stderr", "")
        stdout = process.get("stdout", "")
        if process.get("launch_error") or "OFFLINE GUARD" in stderr or not versions["stac-check"]["matches"]:
            status = "tool_error"
        elif process["exit_code"] == 0:
            status = "passed"
        elif "Traceback (most recent call last)" in stderr or "Traceback (most recent call last)" in stdout:
            status = "tool_error"
        else:
            status = "failed"
        stac_results.append({"path": path.relative_to(catalog).as_posix(), "status": status,
                             "command": process["command"], "exit_code": process["exit_code"],
                             "stdout": stdout, "stderr": stderr, "launch_error": process["launch_error"],
                             "advisory": True})
    versions_match = all(item["matches"] for item in versions.values())
    overall_pass = rashid_pass and versions_match and enumeration_error is None
    advisory_status = ("incomplete" if enumeration_error or any(item["status"] == "tool_error" for item in stac_results)
                       else "findings" if any(item["status"] != "passed" for item in stac_results)
                       else "passed")
    report = {
        "status": "passed" if overall_pass else "failed",
        "toolchain_versions_match": versions_match,
        "schema_version": 1,
        "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "catalog_path": str(catalog),
        "scope": scope,
        "network_access": "prohibited",
        "versions": versions,
        "conformance": {"status": "passed" if rashid_pass else "failed",
                         "tool": "rashid", "expected_scope": {"schema": True, "stac_structure": True,
                         "stac_extensions": True, "data": "local" if local_data else "off", "live": "off"},
                         "command": rashid_process["command"],
                         "exit_code": rashid_process["exit_code"], "launch_error": rashid_process["launch_error"],
                         "report_parse_status": "parsed" if rashid_report is not None else "missing_or_unparseable",
                         "report": rashid_report, "stdout": rashid_process["stdout"],
                         "stderr": rashid_process["stderr"]},
        "stac_check_advisory": {"status": advisory_status,
                                 "tool": "stac-check", "network_access": "prohibited",
                                 "enumeration_error": enumeration_error, "objects_checked": len(stac_results),
                                 "results": stac_results,
                                 "note": "Advisory only; tool failures or crashes do not change the Rashid conformance result."},
    }
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    with os.fdopen(report_fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return report, (0 if overall_pass else 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="local catalog directory")
    parser.add_argument("--report", type=Path, required=True, help="new report path outside the catalog tree")
    parser.add_argument("--local-data", action="store_true", help="check local asset bytes only; never checks remote or live hosts")
    args = parser.parse_args(argv)
    try:
        report, code = run_gate(args.catalog, args.report, local_data=args.local_data)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    conformance = report["conformance"]["status"]
    advisory = report["stac_check_advisory"]["status"]
    print(f"Rashid conformance: {conformance}; stac-check advisory: {advisory} ({report['stac_check_advisory']['objects_checked']} objects). Report: {args.report}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
