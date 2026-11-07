#!/usr/bin/env python3
"""Check bbox row-group pruning for fixed, predeclared geographic windows.

This measures footer-based pruning eligibility, not engine-internal I/O. Actual
loopback HTTP byte counts and ID/WKB equality are checked separately by packaging.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import duckdb
import pyarrow.parquet as pq

WINDOWS = {
    "Europe": [5, 45, 15, 55],
    "North America": [-100, 40, -90, 50],
    "East Africa": [20, -5, 35, 5],
    "Australia": [135, -35, 150, -20],
}
MINIMUM_PRUNABLE_FRACTION = 0.5


def check(path: Path, windows: dict[str, list[float]] | None = None) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    result = {"asset": path.name, "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size,
              "status": "running", "minimum_prunable_fraction": MINIMUM_PRUNABLE_FRACTION,
              "measurement": "row groups ruled out by bbox min/max; engine I/O checked separately", "queries": []}
    pf = pq.ParquetFile(path)
    groups = pf.metadata.num_row_groups
    if not groups:
        raise ValueError("empty Parquet row groups")
    stats = []
    for group_index in range(groups):
        group = pf.metadata.row_group(group_index)
        values = {}
        for i in range(group.num_columns):
            col = group.column(i)
            if col.path_in_schema in {"bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax"}:
                stat = col.statistics
                if stat is None or not stat.has_min_max:
                    raise ValueError(f"missing bbox min/max in row group {group_index}")
                values[col.path_in_schema] = (stat.min, stat.max)
        if len(values) != 4:
            raise ValueError(f"missing bbox statistics columns in row group {group_index}")
        stats.append(values)
    result["row_groups"] = groups
    pf.close()
    with duckdb.connect(config={"threads": 2, "memory_limit": "256MB"}) as conn:
        for name, bbox in (WINDOWS if windows is None else windows).items():
            west, south, east, north = bbox
            skipped = sum(s["bbox.xmax"][1] < west or s["bbox.xmin"][0] > east or
                          s["bbox.ymax"][1] < south or s["bbox.ymin"][0] > north for s in stats)
            count = conn.execute("SELECT count(*) FROM read_parquet(?) WHERE "
                                 "bbox.xmax >= ? AND bbox.xmin <= ? AND bbox.ymax >= ? AND bbox.ymin <= ?",
                                 [str(path), west, east, south, north]).fetchone()[0]
            fraction = skipped / groups
            status = "empty_reported" if count == 0 else "passed" if fraction >= MINIMUM_PRUNABLE_FRACTION else "failed"
            result["queries"].append({"name": name, "bbox": bbox, "matching_rows": count,
                                      "row_groups_prunable": skipped, "prunable_fraction": fraction, "status": status})
    nonempty = [q for q in result["queries"] if q["matching_rows"] > 0]
    result["status"] = "passed" if nonempty and all(q["status"] == "passed" for q in nonempty) else "failed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("refusing to overwrite an existing report")
    try:
        result = check(args.input)
    except Exception as error:
        result = {"status": "failed", "error": f"{type(error).__name__}: {error}", "asset": args.input.name}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
