"""Coordinate sequential LakeATLAS source and independent reader checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("validate_worker.py")
SOURCE_NAME = "LakeATLAS_Data_v10.gdb.zip"
LIMIT_BYTES = 1_000_000_000
LAYERS = ("LakeATLAS_v10_pol", "LakeATLAS_v10_pnt")


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(path: Path, report: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")


def run_worker(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(WORKER), *args], capture_output=True, text=True, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cache", type=Path, default=REPO / ".local/lakeatlas/source")
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    release = args.release.resolve()
    report_path = (args.report or (release / "source-fidelity.json")).resolve()
    source_report_path = report_path.with_name(report_path.stem + "-source-worker.json")
    for path in (report_path, source_report_path):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite prior validation evidence: {path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    source_run = run_worker([
        "--mode", "source", "--source-cache", str(args.source_cache.resolve()),
        "--release", str(release), "--report", str(source_report_path),
    ])
    source_report: dict[str, Any] = {}
    if source_report_path.is_file():
        source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    phase_peaks: dict[str, int] = {}
    if "peak_process_memory_bytes" in source_report:
        phase_peaks["source_fidelity"] = int(source_report["peak_process_memory_bytes"])

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    report: dict[str, Any] = {
        "status": "failed_source_fidelity",
        "source_worker_report": source_report_path.name,
        "source_worker": source_report,
        "independent_readers": {},
        "phase_peak_memory_bytes": phase_peaks,
        "validator": {
            "git_commit": commit,
            "coordinator_sha256": sha256(Path(__file__).resolve()),
            "worker_sha256": sha256(WORKER),
        },
    }
    if source_run.returncode != 0 or source_report.get("status") != "passed_source_only_pending_reader":
        worker_status = source_report.get("status")
        if worker_status in {"failed_memory_limit", "failed_source_fidelity"}:
            report["status"] = worker_status
        report["error"] = source_report.get("error") or source_run.stderr[-4000:] or "Source worker failed without a report"
        report["source_fidelity_checks"] = source_report.get("source_fidelity_checks", "failed")
        report["peak_process_memory_bytes"] = max([peak_rss_bytes(), *phase_peaks.values()])
        write_report(report_path, report)
        print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

    layer_reports = source_report.get("layers", {})
    for layer in LAYERS:
        item = layer_reports.get(layer)
        if not item or not item.get("asset"):
            report["status"] = "failed_independent_reader"
            report["error"] = f"Source worker report missing analytic asset for {layer}"
            break
        reader_run = run_worker([
            "--mode", "reader", "--release", str(release), "--asset", str(release / item["asset"]),
            "--layer", layer,
        ])
        if reader_run.returncode != 0:
            report["status"] = "failed_independent_reader"
            report["error"] = reader_run.stderr[-4000:] or f"GeoPandas reader failed for {layer}"
            break
        try:
            reader_report = json.loads(reader_run.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as error:
            report["status"] = "failed_independent_reader"
            report["error"] = f"Invalid GeoPandas worker output for {layer}: {error}"
            break
        report["independent_readers"][layer] = reader_report
        phase_peaks[f"geopandas_{layer}"] = int(reader_report["peak_process_memory_bytes"])
        layer_reports[layer]["geopandas_subset"] = reader_report
        if reader_report["peak_process_memory_bytes"] >= LIMIT_BYTES:
            report["status"] = "failed_memory_limit"
            report["error"] = f"GeoPandas worker peak memory exceeded 1 GB for {layer}"
            break

    report["source"] = source_report.get("source")
    report["layers"] = layer_reports
    report["source_fidelity_checks"] = "passed"
    report["phase_peak_memory_bytes"] = phase_peaks
    report["peak_process_memory_bytes"] = max([peak_rss_bytes(), *phase_peaks.values()])
    if report["peak_process_memory_bytes"] >= LIMIT_BYTES:
        report["status"] = "failed_memory_limit"
        report["error"] = f"A sequential validation phase exceeded 1 GB: {report['peak_process_memory_bytes']:,} bytes"
    elif report["status"] == "failed_source_fidelity":
        report["status"] = "passed_source_fidelity"
    report["limits"] = source_report.get("limits", []) + [
        "Source fidelity and each independent GeoPandas reader ran sequentially in separate processes; the reported peak is the maximum phase peak, not their sum."
    ]
    write_report(report_path, report)
    if report["status"] != "passed_source_fidelity":
        print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
