#!/usr/bin/env python3
"""Export reproducible local bbox hints for frozen hosted Parquet ID queries.

Reads only explicitly mapped local package Parquets and their metadata. The
output supplements, but never edits, frozen IDs or upload-plan identities.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import sys
from typing import Any

import duckdb
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("source_publish_upload_for_hints", SCRIPT_DIR / "upload.py")
assert SPEC and SPEC.loader
upload = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = upload
SPEC.loader.exec_module(upload)

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
BBOX_NAMES = ("xmin", "ymin", "xmax", "ymax")
METHOD = ("Frozen IDs and exact planned Parquet SHA remain unchanged. For each selected ID, a covering-bbox center is ANDed with that same ID. Candidate row-group bytes sum all compressed column chunks in groups whose local Parquet statistics cannot rule out the ID and, where present, the spatial predicate. These are column-chunk bounds, not HTTP-transfer guarantees.")


class HintError(ValueError):
    pass


def _read_pinned_json(path: Path, expected_sha: str, label: str) -> dict[str, Any]:
    if not SHA_RE.fullmatch(expected_sha):
        raise HintError(f"{label} requires a lowercase SHA-256 pin")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise HintError(f"{label} bytes differ from expected SHA-256")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise HintError(f"{label} has an unsupported schema")
    return value


def _packages(values: list[str], expected: set[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        dataset, separator, raw = value.partition("=")
        path = Path(raw)
        if (separator != "=" or dataset not in expected or dataset in result
                or not path.is_absolute() or path.is_symlink() or not path.is_dir()):
            raise HintError("each dataset needs one absolute --package DATASET=ROOT mapping")
        result[dataset] = path.resolve(strict=True)
    if set(result) != expected:
        raise HintError("package mappings must exactly cover frozen datasets")
    return result


def _wkb_info(blob: bytes) -> tuple[int, int, dict[str, float]]:
    """Read 2D WKB recursively, including rings and multipart coordinates."""
    if not isinstance(blob, bytes) or not blob:
        raise HintError("selected source WKB is empty or invalid")
    view = memoryview(blob)
    offset = 0
    xs: list[float] = []
    ys: list[float] = []

    def read(fmt: str, order: str) -> tuple[Any, ...]:
        nonlocal offset
        size = struct.calcsize(fmt)
        if offset + size > len(view):
            raise HintError("truncated selected source WKB")
        values = struct.unpack_from(order + fmt, view, offset)
        offset += size
        return values

    def points(count: int, order: str) -> None:
        if count > (len(view) - offset) // 16:
            raise HintError("WKB coordinate count exceeds available bytes")
        for _ in range(count):
            x, y = read("dd", order)
            if not math.isfinite(x) or not math.isfinite(y):
                raise HintError("selected WKB has nonfinite XY coordinates")
            xs.append(x)
            ys.append(y)

    def geometry(depth: int = 0) -> int:
        nonlocal offset
        if depth > 32 or offset >= len(view):
            raise HintError("invalid selected WKB nesting")
        endian = read("B", "<")[0]
        if endian not in (0, 1):
            raise HintError("invalid selected WKB byte order")
        order = "<" if endian == 1 else ">"
        code = read("I", order)[0]
        if code & 0xE0000000 or code >= 1000:
            raise HintError("selected WKB is not plain 2D geometry")
        if code == 1:
            points(1, order)
        elif code == 2:
            points(read("I", order)[0], order)
        elif code == 3:
            for _ in range(read("I", order)[0]):
                points(read("I", order)[0], order)
        elif code in (4, 5, 6, 7):
            child_types = {4: 1, 5: 2, 6: 3}
            for _ in range(read("I", order)[0]):
                child = geometry(depth + 1)
                if code != 7 and child != child_types[code]:
                    raise HintError("multipart WKB child type differs from parent")
        else:
            raise HintError(f"unsupported selected WKB geometry type {code}")
        return code

    geometry_type = geometry()
    if offset != len(view) or not xs:
        raise HintError("selected WKB has trailing bytes or no XY coordinates")
    return geometry_type, len(xs), {"minx": min(xs), "miny": min(ys),
                                    "maxx": max(xs), "maxy": max(ys)}


def _column_stats(group: Any) -> dict[str, tuple[Any, Any]]:
    result = {}
    for index in range(group.num_columns):
        column = group.column(index)
        stats = column.statistics
        if stats is not None and stats.has_min_max:
            result[column.path_in_schema] = (stats.min, stats.max)
    return result


def _group_bound(groups: list[Any], indices: list[int]) -> dict[str, Any]:
    return {"all_column_chunks_compressed_bytes_upper_bound": sum(
                sum(group.column(i).total_compressed_size for i in range(group.num_columns))
                for index, group in enumerate(groups) if index in set(indices)),
            "row_group_count": len(indices), "row_group_indices": indices}


def _candidate_bounds(metadata: Any, id_column: str, selected: list[dict[str, Any]]) -> dict[str, Any]:
    groups = [metadata.row_group(i) for i in range(metadata.num_row_groups)]
    statistics = [_column_stats(group) for group in groups]
    per_id = []
    all_id: set[int] = set()
    all_spatial: set[int] = set()
    for item in selected:
        value = item["id"]
        x, y = item["center"]["x"], item["center"]["y"]
        id_groups = []
        spatial_groups = []
        for index, stats in enumerate(statistics):
            id_stats = stats.get(id_column)
            id_possible = id_stats is None or id_stats[0] <= value <= id_stats[1]
            if not id_possible:
                continue
            id_groups.append(index)
            spatial_possible = True
            for name, test in (("bbox.xmin", lambda pair: pair[0] <= x),
                               ("bbox.xmax", lambda pair: pair[1] >= x),
                               ("bbox.ymin", lambda pair: pair[0] <= y),
                               ("bbox.ymax", lambda pair: pair[1] >= y)):
                pair = stats.get(name)
                if pair is not None and not test(pair):
                    spatial_possible = False
                    break
            if spatial_possible:
                spatial_groups.append(index)
        all_id.update(id_groups)
        all_spatial.update(spatial_groups)
        per_id.append({"id": value, "id_only": _group_bound(groups, id_groups),
                       "id_plus_spatial": _group_bound(groups, spatial_groups)})
    return {"per_id": per_id, "query_union_id_only": _group_bound(groups, sorted(all_id)),
            "query_union_id_plus_spatial": _group_bound(groups, sorted(all_spatial)),
            "whole_file_all_column_chunks": _group_bound(groups, list(range(len(groups))))}


def _query_hint(query: dict[str, Any], entry: dict[str, Any], local: Path) -> dict[str, Any]:
    if (not isinstance(query.get("id_column"), str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", query["id_column"])
            or not isinstance(query.get("ids"), list) or not query["ids"]):
        raise HintError("frozen query has invalid ID column or IDs")
    size, digest = upload.hash_file(local)
    if (size, digest) != (entry["size_bytes"], entry["sha256"]):
        raise HintError(f"local Parquet bytes differ from exact plan: {query['path']}")
    pf = pq.ParquetFile(local)
    try:
        schema = pf.schema_arrow
        geo = json.loads((pf.metadata.metadata or {})[b"geo"])
        geometry_column = geo["primary_column"]
        mapping = geo["columns"][geometry_column]["covering"]["bbox"]
        expected_mapping = {name: ["bbox", name] for name in BBOX_NAMES}
        if mapping != expected_mapping or geometry_column not in schema.names or "bbox" not in schema.names:
            raise HintError("GeoParquet covering bbox mapping differs from required local fields")
        if pf.metadata.num_rows != query["selection"]["row_count"]:
            raise HintError("frozen query row count differs from local footer")
        column = '"' + query["id_column"] + '"'
        placeholders = ",".join("?" for _ in query["ids"])
        sql = (f"SELECT {column}, bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, "
               f'"{geometry_column}" FROM read_parquet(?) WHERE {column} IN ({placeholders})')
        with duckdb.connect(database=":memory:", read_only=False) as con:
            rows = con.execute(sql, [str(local), *query["ids"]]).fetchall()
        by_id: dict[str, list[tuple[Any, ...]]] = {}
        for row in rows:
            by_id.setdefault(str(row[0]), []).append(row)
        selected = []
        match_counts = {}
        for value in query["ids"]:
            matches = by_id.get(str(value), [])
            if len(matches) != 1:
                raise HintError(f"frozen ID has {len(matches)} local rows, expected exactly one")
            _, minx, miny, maxx, maxy, wkb = matches[0]
            bbox = {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy}
            if (any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in bbox.values())
                    or minx > maxx or miny > maxy):
                raise HintError("selected local bbox is invalid")
            center = {"x": (minx + maxx) / 2, "y": (miny + maxy) / 2}
            if not (minx <= center["x"] <= maxx and miny <= center["y"] <= maxy):
                raise HintError("bbox center does not satisfy local spatial predicate")
            geom_type, point_count, envelope = _wkb_info(wkb)
            enclosed = (minx <= envelope["minx"] and miny <= envelope["miny"]
                        and maxx >= envelope["maxx"] and maxy >= envelope["maxy"])
            if not enclosed:
                raise HintError("covering bbox does not enclose selected WKB")
            selected.append({"center": center, "covering_bbox": bbox,
                             "covering_encloses_source_wkb": enclosed, "id": value,
                             "local_id_match_count": 1, "source_wkb_envelope": envelope,
                             "source_wkb_geometry_type": geom_type,
                             "source_wkb_xy_point_count": point_count})
            match_counts[str(value)] = 1
        if len(rows) != len(query["ids"]):
            raise HintError("local frozen-ID subset contains unexpected duplicate rows")
        return {"candidate_row_group_compressed_byte_bounds": _candidate_bounds(pf.metadata, query["id_column"], selected),
                "covering_bbox_column": "bbox", "covering_bbox_fields": {name: f"bbox.{name}" for name in BBOX_NAMES},
                "covering_bbox_status": "validated", "id_column": query["id_column"], "ids": query["ids"],
                "local_spatial_match_counts": match_counts, "name": query["name"],
                "parquet_object_sha256": digest, "parquet_object_size_bytes": size,
                "parquet_row_count": pf.metadata.num_rows, "parquet_row_group_count": pf.metadata.num_row_groups,
                "path": query["path"], "selected_ids": selected,
                "source_geometry_column": geometry_column,
                "spatial_predicate_template": (f'{column} = ? AND bbox.xmin <= ? AND bbox.xmax >= ? '
                                               "AND bbox.ymin <= ? AND bbox.ymax >= ?")}
    finally:
        pf.close()


def export(plan_path: Path, plan_sha: str, controls_path: Path, controls_sha: str,
           package_roots: dict[str, Path]) -> dict[str, Any]:
    plan = _read_pinned_json(plan_path, plan_sha, "upload plan")
    controls = _read_pinned_json(controls_path, controls_sha, "frozen controls")
    if controls.get("plan_sha256") != plan_sha or not isinstance(controls.get("datasets"), dict):
        raise HintError("frozen controls are not bound to the exact plan")
    if set(package_roots) != set(controls["datasets"]):
        raise HintError("package mappings do not cover exactly the frozen datasets")
    products = {item["dataset_id"]: item for item in plan["products"]}
    datasets = {}
    for dataset_id, selected in controls["datasets"].items():
        if dataset_id not in products or selected.get("release") != products[dataset_id]["release"]:
            raise HintError("frozen dataset release differs from exact upload plan")
        _, entries = upload.load_plan(plan_path, dataset_id, include_readme=False)
        assets = {entry["source"]["path"]: entry for entry in entries
                  if entry["source"]["kind"] == "package" and entry["source"]["path"].endswith(".parquet")}
        queries = selected.get("queries")
        if not isinstance(queries, list) or {q.get("path") for q in queries} != set(assets):
            raise HintError("frozen queries do not exactly cover planned analytic Parquets")
        output_queries = []
        for query in queries:
            entry = assets[query["path"]]
            local = upload._safe_file(package_roots[dataset_id], query["path"], "package Parquet")
            output_queries.append(_query_hint(query, entry, local))
        datasets[dataset_id] = {"queries": output_queries, "release": selected["release"]}
    return {"datasets": datasets, "immutable_upload_plan_sha256": plan_sha,
            "kind": "local_spatial_query_supplement", "method": METHOD,
            "original_query_controls_sha256": controls_sha, "schema_version": 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--controls", required=True, type=Path)
    parser.add_argument("--controls-sha256", required=True)
    parser.add_argument("--package", action="append", default=[], metavar="DATASET=ABSOLUTE_ROOT")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("refusing to overwrite an existing hint artifact")
    controls = _read_pinned_json(args.controls, args.controls_sha256, "frozen controls")
    package_roots = _packages(args.package, set(controls.get("datasets") or {}))
    result = export(args.plan, args.plan_sha256, args.controls, args.controls_sha256, package_roots)
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(payload)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                      "datasets": sorted(result["datasets"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
