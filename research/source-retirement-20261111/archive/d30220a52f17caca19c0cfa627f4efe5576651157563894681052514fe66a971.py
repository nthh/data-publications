#!/usr/bin/env python3
"""Build a local immutable package for one or more analytic GeoParquet assets.

No upload or registry writes are performed. See README.md for the JSON contract.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import struct
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pyproj
import yaml

from serve import Handler, MAX_RANGE_BYTES

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PORTOLAN = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"
FILE_EXT = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
TABLE_EXT = "https://stac-extensions.github.io/table/v1.2.0/schema.json"
SCIENTIFIC_EXT = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
VERSION_EXT = "https://stac-extensions.github.io/version/v1.2.0/schema.json"
PARQUET_MEDIA = "application/vnd.apache.parquet"
CHUNK = 1024 * 1024
MAX_TEST_RANGE = 8 * 1024 * 1024


class ReleaseError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def resolve_input(value: str | Path, spec_dir: Path) -> Path:
    p = Path(value).expanduser()
    return (p if p.is_absolute() else spec_dir / p).resolve()


def safe_id(value: str, what: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value):
        raise ReleaseError(f"unsafe {what}: {value!r}")
    return value


def copy_portable(src: Path, dest: Path) -> str:
    """Copy without hardlinks; prefer APFS clone on macOS, falling back to copy."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = "copy"
    if sys.platform == "darwin":
        proc = subprocess.run(["cp", "-c", str(src), str(dest)], capture_output=True, text=True)
        if proc.returncode == 0:
            mode = "apfs_clone"
        else:
            if dest.exists():
                dest.unlink()
            free = shutil.disk_usage(dest.parent).free
            required = src.stat().st_size
            if free < required:
                raise ReleaseError(f"APFS clone unavailable and insufficient free space for copy: {required} bytes needed, {free} free")
            shutil.copyfile(src, dest)
    else:
        free = shutil.disk_usage(dest.parent).free
        required = src.stat().st_size
        if free < required:
            raise ReleaseError(f"insufficient free space for portable copy: {required} bytes needed, {free} free")
        shutil.copyfile(src, dest)
    if dest.stat().st_size != src.stat().st_size:
        raise ReleaseError(f"copy size mismatch: {src} -> {dest}")
    if os.path.samefile(src, dest):
        raise ReleaseError("refusing hard-linked package file")
    return mode


def read_record(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    except Exception as e:
        raise ReleaseError(f"cannot parse canonical record {path}: {e}") from e
    if not isinstance(value, dict):
        raise ReleaseError("canonical record must be a JSON/YAML object")
    return value


def normalize_report_assets(report: dict[str, Any]) -> dict[str, tuple[str, int]]:
    rows = report.get("assets")
    if not isinstance(rows, list):
        return {}
    result: dict[str, tuple[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("asset_id"), str):
            return {}
        try:
            digest = str(row["sha256"]).lower()
            size = int(row["size_bytes"])
        except (KeyError, TypeError, ValueError):
            return {}
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or size < 0 or row["asset_id"] in result:
            return {}
        result[row["asset_id"]] = (digest, size)
    return result


def load_and_bind_report(value: str | None, label: str, spec_dir: Path,
                         expected_assets: dict[str, tuple[str, int]]) -> tuple[dict[str, Any], bytes]:
    if not value:
        raise ReleaseError(f"{label} report path is required")
    path = resolve_input(value, spec_dir)
    if not path.is_file():
        raise ReleaseError(f"{label} report is missing: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReleaseError(f"{label} report is not valid JSON: {path}: {e}") from e
    if not isinstance(report, dict):
        raise ReleaseError(f"{label} report must be a JSON object")
    if report.get("status") != "passed":
        raise ReleaseError(f"{label} report status must be 'passed'; got {report.get('status')!r}")
    if normalize_report_assets(report) != expected_assets:
        raise ReleaseError(f"{label} report does not bind every exact asset_id/SHA-256/size_bytes")
    return {"path": str(path), "sha256": sha256(path), "report": report}, path.read_bytes()


def geo_metadata(pf: pq.ParquetFile, asset_id: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    raw = pf.metadata.metadata or {}
    try:
        geo = json.loads(raw[b"geo"])
    except Exception as e:
        raise ReleaseError(f"{asset_id}: missing or invalid GeoParquet 'geo' metadata") from e
    primary = geo.get("primary_column")
    columns = geo.get("columns", {})
    if not isinstance(primary, str) or primary not in columns:
        raise ReleaseError(f"{asset_id}: GeoParquet primary_column is absent from columns metadata")
    geom = columns[primary]
    if geom.get("encoding") != "WKB":
        raise ReleaseError(f"{asset_id}: geometry encoding must be WKB")
    if "crs" not in geom:
        raise ReleaseError(f"{asset_id}: GeoParquet geometry CRS is not explicitly recorded")
    if geom.get("crs") is None:
        supported = geom.get("supportedCRS", geo.get("supportedCRS"))
        if not supported:
            raise ReleaseError(f"{asset_id}: null GeoParquet CRS requires explicit supportedCRS metadata")
        values = supported if isinstance(supported, list) else [supported]
        try:
            if not values: raise ValueError("empty supportedCRS")
            for value in values: pyproj.CRS.from_user_input(value)
        except Exception as e:
            raise ReleaseError(f"{asset_id}: supportedCRS metadata is not valid CRS information: {e}") from e
    if primary not in pf.schema_arrow.names:
        raise ReleaseError(f"{asset_id}: geometry column is missing from Parquet schema")
    return primary, geo, geom


def parquet_metadata(asset: dict[str, Any], src: Path) -> dict[str, Any]:
    try:
        pf = pq.ParquetFile(src)
    except Exception as e:
        raise ReleaseError(f"{asset['asset_id']}: cannot open Parquet file: {e}") from e
    if pf.metadata.num_rows <= 0:
        raise ReleaseError(f"{asset['asset_id']}: empty Parquet files are not packageable")
    ident = asset["identifier_column"]
    if ident not in pf.schema_arrow.names:
        raise ReleaseError(f"{asset['asset_id']}: identifier column {ident!r} is absent")
    primary, geo, geom = geo_metadata(pf, asset["asset_id"])
    names = set(pf.schema_arrow.names)
    bbox_fields = None
    if "bbox" in names and pa.types.is_struct(pf.schema_arrow.field("bbox").type):
        b = set(pf.schema_arrow.field("bbox").type.names)
        if {"xmin", "ymin", "xmax", "ymax"} <= b:
            bbox_fields = {k: f"bbox.{k}" for k in ("xmin", "ymin", "xmax", "ymax")}
    field_dictionary = None
    dictionary_path = asset.get("field_dictionary_path")
    if dictionary_path:
        dp = resolve_input(dictionary_path, asset["_spec_dir"])
        if not dp.is_file():
            raise ReleaseError(f"{asset['asset_id']}: field dictionary is missing: {dp}")
        field_dictionary = {"path": dp, "sha256": sha256(dp), "bytes": dp.read_bytes()}
    descriptions: dict[str, dict[str, Any]] = {}
    if field_dictionary:
        try:
            user_dict = json.loads(field_dictionary["bytes"])
            raw_fields = user_dict.get("fields", user_dict) if isinstance(user_dict, dict) else user_dict
            if isinstance(raw_fields, dict):
                descriptions = {str(k): v for k, v in raw_fields.items() if isinstance(v, dict)}
            elif isinstance(raw_fields, list):
                descriptions = {str(x["name"]): x for x in raw_fields if isinstance(x, dict) and "name" in x}
        except Exception:
            # Preserve non-JSON field dictionaries as source documentation; the
            # generated table extension still contains names/types/identifier.
            descriptions = {}
    cols = []
    for field in pf.schema_arrow:
        info = descriptions.get(field.name, {})
        col = {"name": field.name, "type": str(field.type)}
        description = info.get("description")
        if isinstance(description, str) and description.strip():
            col["description"] = description.strip()
        if isinstance(info.get("unit"), str) and info["unit"].strip():
            col["unit"] = info["unit"].strip()
        cols.append(col)
    return {"rows": pf.metadata.num_rows, "schema": pf.schema_arrow, "schema_names": names,
            "primary_geometry": primary, "geo_metadata": geo, "geometry_metadata": geom,
            "bbox_fields": bbox_fields, "table_columns": cols, "field_dictionary": field_dictionary,
            "dictionary_descriptions": descriptions}


def get_bbox(asset_info: list[dict[str, Any]], asset_rows: list[dict[str, Any]], spec: dict[str, Any]) -> list[float]:
    explicit = spec.get("bbox")
    if explicit is not None:
        bbox = [float(x) for x in explicit]
    else:
        bboxes = []
        conn = duckdb.connect()
        try:
            for asset, info in zip(asset_rows, asset_info):
                fields = info["bbox_fields"]
                if not fields:
                    raise ReleaseError(f"{asset['asset_id']}: provide spec.bbox or a bbox struct with xmin/ymin/xmax/ymax")
                src = str(asset["_source"])
                row = conn.execute(
                    "SELECT min(bbox.xmin), min(bbox.ymin), max(bbox.xmax), max(bbox.ymax) FROM read_parquet(?)", [src]
                ).fetchone()
                if row is None or any(v is None for v in row):
                    raise ReleaseError(f"{asset['asset_id']}: cannot derive a non-null bbox")
                bboxes.append([float(x) for x in row])
        finally:
            conn.close()
        bbox = [min(x[0] for x in bboxes), min(x[1] for x in bboxes),
                max(x[2] for x in bboxes), max(x[3] for x in bboxes)]
    if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox):
        raise ReleaseError("bbox must contain four finite numbers [west,south,east,north]")
    if not (-180 <= bbox[0] <= bbox[2] <= 180 and -90 <= bbox[1] <= bbox[3] <= 90):
        raise ReleaseError(f"bbox is outside valid EPSG:4326 limits: {bbox}")
    return bbox


def source_report_assets(asset_descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"asset_id": x["asset_id"], "sha256": x["sha256"], "size_bytes": x["size_bytes"]}
            for x in asset_descriptors]


def stac_asset(href: str, media: str, roles: list[str], title: str,
               size: int, digest: str) -> dict[str, Any]:
    return {"href": href, "type": media, "roles": roles, "title": title,
            "file:size": size, "file:checksum": "1220" + digest}


def wkb_segments(raw: bytes) -> list[list[tuple[float, float]]]:
    """Decode standard WKB linework with bounded dimensional-coordinate skips."""
    segments: list[list[tuple[float, float]]] = []
    def parse(pos: int) -> int:
        if pos + 5 > len(raw): raise ReleaseError("truncated WKB geometry")
        endian = "<" if raw[pos] == 1 else ">" if raw[pos] == 0 else None
        if endian is None: raise ReleaseError("invalid WKB byte-order marker")
        code = struct.unpack_from(endian + "I", raw, pos + 1)[0]
        pos += 5
        ewkb_z, ewkb_m, ewkb_srid = bool(code & 0x80000000), bool(code & 0x40000000), bool(code & 0x20000000)
        base = code & 0x1FFFFFFF
        if base >= 1000:
            dim, base = base // 1000, base % 1000
            has_z, has_m = dim in (1,3), dim in (2,3)
        else:
            has_z, has_m = ewkb_z, ewkb_m
        if ewkb_srid:
            if pos + 4 > len(raw): raise ReleaseError("truncated WKB SRID")
            pos += 4
        stride = (2 + int(has_z) + int(has_m)) * 8
        def point_seq(p: int) -> tuple[list[tuple[float,float]], int]:
            if p + 4 > len(raw): raise ReleaseError("truncated WKB point count")
            n = struct.unpack_from(endian + "I", raw, p)[0]; p += 4
            if p + n*stride > len(raw): raise ReleaseError("truncated WKB coordinate sequence")
            pts=[]
            for _ in range(n):
                pts.append(struct.unpack_from(endian + "dd", raw, p)); p += stride
            return pts,p
        if base == 1:
            if pos + stride > len(raw): raise ReleaseError("truncated WKB point")
            segments.append([struct.unpack_from(endian + "dd", raw, pos)])
            return pos + stride
        if base == 2:
            pts,pos=point_seq(pos); segments.append(pts); return pos
        if base == 3:
            if pos+4>len(raw): raise ReleaseError("truncated WKB ring count")
            n=struct.unpack_from(endian+"I",raw,pos)[0];pos+=4
            for _ in range(n):
                pts,pos=point_seq(pos);segments.append(pts)
            return pos
        if base in (4,5,6,7):
            if pos+4>len(raw): raise ReleaseError("truncated WKB member count")
            n=struct.unpack_from(endian+"I",raw,pos)[0];pos+=4
            for _ in range(n): pos=parse(pos)
            return pos
        raise ReleaseError(f"unsupported WKB geometry type {base}")
    end = parse(0)
    if end != len(raw): raise ReleaseError("unparsed trailing bytes in WKB geometry")
    return segments


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def make_thumbnail(asset_rows: list[dict[str, Any]], infos: list[dict[str, Any]], out: Path, bbox: list[float]) -> dict[str, Any]:
    """Generate a modest, explicitly sampled PNG preview without changing analytics."""
    width, height = 1000, 500
    bg, ink = (247, 249, 250), (29, 116, 139)
    pixels = bytearray(bg * (width * height))
    def xy(x: float, y: float) -> tuple[int,int]:
        fx = (x - bbox[0]) / max(1e-12, bbox[2] - bbox[0])
        fy = (bbox[3] - y) / max(1e-12, bbox[3] - bbox[1])
        return max(0,min(width-1,round(fx*(width-1)))), max(0,min(height-1,round(fy*(height-1))))
    def dot(x: int, y: int) -> None:
        if 0 <= x < width and 0 <= y < height:
            off=(y*width+x)*3;pixels[off:off+3]=bytes(ink)
    def line(a: tuple[int,int], b: tuple[int,int]) -> None:
        x0,y0=a;x1,y1=b;dx=abs(x1-x0);sx=1 if x0<x1 else -1;dy=-abs(y1-y0);sy=1 if y0<y1 else -1;err=dx+dy
        while True:
            dot(x0,y0)
            if x0==x1 and y0==y1: break
            e2=2*err
            if e2>=dy: err+=dy;x0+=sx
            if e2<=dx: err+=dx;y0+=sy
    total_features=total_vertices=0;max_features=50000;max_vertices=500000
    for asset,info in zip(asset_rows,infos):
        pf=pq.ParquetFile(asset["_source"])
        for batch in pf.iter_batches(batch_size=512,columns=[info["primary_geometry"]]):
            for cell in batch.column(0):
                raw=cell.as_py()
                if raw is None: continue
                segs=wkb_segments(raw);total_features+=1
                for seg in segs:
                    total_vertices+=len(seg)
                    if not seg: continue
                    pts=[xy(float(x),float(y)) for x,y in seg if math.isfinite(float(x)) and math.isfinite(float(y))]
                    if len(pts)==1: dot(*pts[0])
                    else:
                        for a,b in zip(pts,pts[1:]): line(a,b)
                    if total_vertices>=max_vertices: break
                if total_features>=max_features or total_vertices>=max_vertices: break
            if total_features>=max_features or total_vertices>=max_vertices: break
    raw=b"".join(b"\0"+bytes(pixels[y*width*3:(y+1)*width*3]) for y in range(height))
    png=b"\x89PNG\r\n\x1a\n"+png_chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+png_chunk(b"IDAT",zlib.compress(raw,6))+png_chunk(b"IEND",b"")
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(png)
    return {"path": "display/thumbnail.png", "sha256": hashlib.sha256(png).hexdigest(), "size_bytes": len(png),
            "format": "PNG", "role": "thumbnail", "sampled_features": total_features,
            "sampled_vertices": total_vertices, "display_only": True,
            "sampling_limit": {"max_features": max_features, "max_vertices": max_vertices}}


def run_schema_gates(root: Path, manifest_sha: str) -> tuple[dict[str, Any], dict[str, Any]]:
    node = HERE / "node_modules/.bin/stac-node-validator"
    if not node.exists():
        node_report = {"status": "failed", "validator": "stac-node-validator 2.0.0",
                       "error": f"validator executable not found: {node}"}
    else:
        cp = subprocess.run([str(node), str(root / "catalog.json"), str(root / "collection.json")],
                            cwd=HERE, capture_output=True, text=True)
        output = cp.stdout + cp.stderr
        output = output.replace(str(root), "<package>")
        output = re.sub(r"/(?:Users|private|tmp)/[^\s,:\"']+", "<local-path>", output)
        found = {k: re.search(rf"{k}:\s*(\d+)\b", output, re.I) for k in ("Passed", "Invalid", "Skipped")}
        counts = {k: int(v.group(1)) if v else None for k, v in found.items()}
        passed = cp.returncode == 0 and counts == {"Passed": 2, "Invalid": 0, "Skipped": 0}
        node_report = {"status": "passed" if passed else "failed", "validator": "stac-node-validator 2.0.0",
                       "exit_code": cp.returncode, "release_manifest_sha256": manifest_sha,
                       "validated_documents": ["catalog.json", "collection.json"],
                       "counts": counts, "output": output}
    rashid = HERE / ".venv/bin/rashid"
    if not rashid.exists():
        port_report = {"status": "failed", "validator": "rashid 0.1.8",
                       "error": f"validator executable not found: {rashid}"}
    else:
        cp = subprocess.run([str(rashid), "check", str(root), "--schema", "--data-scope", "local", "--json"],
                            cwd=HERE, capture_output=True, text=True)
        output = cp.stdout + cp.stderr
        output = output.replace(str(root), "<package>")
        output = re.sub(r"/(?:Users|private|tmp)/[^\s,:\"']+", "<local-path>", output)
        try:
            result = json.loads(cp.stdout.replace(str(root), "<package>"))
        except json.JSONDecodeError:
            result = {"raw_output": output}
        passed = cp.returncode == 0 and isinstance(result, dict) and result.get("passed") is True and result.get("error_count") == 0
        port_report = {"status": "passed" if passed else "failed", "validator": "rashid 0.1.8",
                       "exit_code": cp.returncode, "release_manifest_sha256": manifest_sha,
                       "checks": ["Portolan v0.2.0 bundled schema", "STAC 1.1 structural schema", "local asset bytes"],
                       "result": result, "output": output if not passed else None}
    return node_report, port_report


def subset_fingerprint(conn: Any, source: str, id_col: str, geometry_col: str, subset: str) -> dict[str, Any]:
    """Order-independent SHA-256 multiset binding of identifiers to raw WKB."""
    ident = '"' + id_col.replace('"', '""') + '"'
    geom = '"' + geometry_col.replace('"', '""') + '"'
    query = f"SELECT {ident}, {geom} FROM read_parquet(?) WHERE {subset}"
    cursor = conn.execute(query, [source])
    count = 0
    nonempty = 0
    accumulator = 0
    modulus = 1 << 256
    while rows := cursor.fetchmany(2048):
        for identifier, wkb in rows:
            count += 1
            id_bytes = json.dumps(identifier, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
            geom_bytes = bytes(wkb) if wkb is not None else b""
            if wkb is not None:
                nonempty += 1
            framed = len(id_bytes).to_bytes(8, "big") + id_bytes + len(geom_bytes).to_bytes(8, "big") + geom_bytes
            accumulator = (accumulator + int.from_bytes(hashlib.sha256(framed).digest(), "big")) % modulus
    return {"rows": count, "nonempty_geometry_rows": nonempty,
            "identifier_wkb_sha256_multiset_sum": f"{accumulator:064x}"}


def http_and_subset_checks(root: Path, asset_rows: list[dict[str, Any]], asset_infos: list[dict[str, Any]],
                           bbox: list[float], spec: dict[str, Any]) -> dict[str, Any]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), lambda *args, **kw: Handler(*args, directory=str(root), **kw))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    result: dict[str, Any] = {"status": "running", "base_url": base,
                              "max_probe_response_bytes": MAX_TEST_RANGE, "ranges": []}
    try:
        Handler.reset_bytes_served()
        conn = duckdb.connect(config={"threads": 2, "memory_limit": "512MB"})
        try:
            for asset in asset_rows:
                rel = f"assets/{asset['asset_id']}.parquet"
                url = base + "/" + rel
                local_path = root / rel
                expected_len = local_path.stat().st_size
                options = urllib.request.Request(url, method="OPTIONS", headers={
                    "Origin": "https://localhost.invalid", "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Range"})
                with urllib.request.urlopen(options, timeout=10) as preflight:
                    if (preflight.status != 204 or preflight.headers.get("Access-Control-Allow-Origin") != "*" or
                        "GET" not in preflight.headers.get("Access-Control-Allow-Methods", "") or
                        "Range" not in preflight.headers.get("Access-Control-Allow-Headers", "")):
                        raise ReleaseError(f"CORS preflight failed for {asset['asset_id']}")
                max_probe_end = min(MAX_TEST_RANGE - 1, expected_len - 1)
                cases = [("bytes=0-31", 206, min(32, expected_len)), ("bytes=-16", 206, min(16, expected_len)),
                         (f"bytes={expected_len + 1}-{expected_len + 64}", 416, None),
                         (f"bytes=0-{max_probe_end}", 206, max_probe_end + 1)]
                if expected_len > MAX_RANGE_BYTES:
                    cases.append((f"bytes=0-{MAX_RANGE_BYTES}", 416, None))
                for header, expected_status, expected_bytes in cases:
                    req = urllib.request.Request(url, headers={"Range": header, "Origin": "https://localhost.invalid"})
                    try:
                        response = urllib.request.urlopen(req, timeout=10)
                        with response:
                            body = response.read(MAX_TEST_RANGE + 1)
                            status, headers = response.status, response.headers
                    except urllib.error.HTTPError as e:
                        with e:
                            body = e.read(MAX_TEST_RANGE + 1)
                            status, headers = e.code, e.headers
                    if len(body) > MAX_TEST_RANGE:
                        raise ReleaseError(f"HTTP probe exceeded response cap for {asset['asset_id']} {header}")
                    if status != expected_status or headers.get("Access-Control-Allow-Origin") != "*":
                        raise ReleaseError(f"HTTP range/CORS check failed: {asset['asset_id']} {header} status={status}")
                    if expected_bytes is not None and len(body) != expected_bytes:
                        raise ReleaseError(f"HTTP range length mismatch: {asset['asset_id']} {header}")
                    result["ranges"].append({"asset_id": asset["asset_id"], "range": header,
                                             "status": status, "response_bytes": len(body),
                                             "cors": headers.get("Access-Control-Allow-Origin")})
                probe_bytes = Handler.get_bytes_served()
                Handler.reset_bytes_served()
                requested_subset = spec.get("validation_bbox")
                if requested_subset is not None:
                    sb = [float(x) for x in requested_subset]
                    if len(sb) != 4 or not all(math.isfinite(x) for x in sb):
                        raise ReleaseError("validation_bbox must contain four finite values")
                else:
                    row_bbox = conn.execute("SELECT bbox.xmin,bbox.ymin,bbox.xmax,bbox.ymax FROM read_parquet(?) LIMIT 1", [str(local_path)]).fetchone()
                    if not row_bbox or any(v is None for v in row_bbox):
                        raise ReleaseError(f"cannot derive a non-empty validation subset for {asset['asset_id']}")
                    cx, cy = (float(row_bbox[0]) + float(row_bbox[2])) / 2, (float(row_bbox[1]) + float(row_bbox[3])) / 2
                    pad_x = max(0.001, min(1.0, (bbox[2] - bbox[0]) / 1000))
                    pad_y = max(0.001, min(1.0, (bbox[3] - bbox[1]) / 1000))
                    sb = [max(-180.0, cx-pad_x), max(-90.0, cy-pad_y), min(180.0, cx+pad_x), min(90.0, cy+pad_y)]
                subset = (f"bbox.xmax >= {sb[0]} AND bbox.xmin <= {sb[2]} AND "
                          f"bbox.ymax >= {sb[1]} AND bbox.ymin <= {sb[3]}")
                geometry_col = asset_infos[asset_rows.index(asset)]["primary_geometry"]
                local = subset_fingerprint(conn, str(local_path), asset["identifier_column"], geometry_col, subset)
                remote = subset_fingerprint(conn, url, asset["identifier_column"], geometry_col, subset)
                duckdb_bytes = Handler.get_bytes_served()
                Handler.reset_bytes_served()
                if local["rows"] == 0 or local["nonempty_geometry_rows"] == 0:
                    raise ReleaseError(f"empty validation subset for {asset['asset_id']}")
                if local != remote:
                    raise ReleaseError(f"DuckDB remote subset identifier/WKB fingerprint differs from local for {asset['asset_id']}: {remote} vs {local}")
                result.setdefault("duckdb_subsets", []).append({"asset_id": asset["asset_id"],
                    "bbox": sb, **remote, "local_remote_equal": True,
                    "http_probe_bytes": probe_bytes,
                    "duckdb_http_bytes_served": duckdb_bytes,
                    "query_engine": f"DuckDB {duckdb.__version__}"})
        finally:
            conn.close()
        result["status"] = "passed"
        result["cors_preflight"] = "OPTIONS 204; wildcard origin; GET/HEAD/OPTIONS and Range permitted"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    return result


def chmod_readonly(root: Path) -> None:
    for p in sorted(root.rglob("*"), reverse=True):
        if p.is_file(): p.chmod(0o444)
        elif p.is_dir(): p.chmod(0o555)
    root.chmod(0o555)


def verify_package(root: Path) -> dict[str, Any]:
    """Verify immutable package bindings, file presence and all recorded hashes."""
    root = root.resolve()
    failures: list[str] = []
    try:
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_digest = sha256(manifest_path)
        check = manifest.get("dataset_record", {})
        if not (root / check.get("path", "dataset.yaml")).is_file() or sha256(root / check.get("path", "dataset.yaml")) != check.get("sha256"):
            failures.append("canonical dataset record snapshot missing or changed")
        for item in manifest.get("assets", []):
            p = root / item.get("href", "")
            if not p.is_file():
                failures.append(f"asset missing: {item.get('asset_id')}")
            elif p.stat().st_size != item.get("size_bytes") or sha256(p) != item.get("sha256"):
                failures.append(f"asset size/hash changed: {item.get('asset_id')}")
            fd = root / item.get("field_dictionary", "")
            if not fd.is_file() or sha256(fd) != item.get("field_dictionary_sha256"):
                failures.append(f"field dictionary missing/changed: {item.get('asset_id')}")
        for item in manifest.get("supporting_files", []):
            p = root / item.get("path", "")
            if not p.is_file() or p.stat().st_size != item.get("size_bytes") or sha256(p) != item.get("sha256"):
                failures.append(f"supporting file missing/changed: {item.get('path')}")
        for item in manifest.get("display_derivatives", []):
            p = root / item.get("path", "")
            if not p.is_file() or p.stat().st_size != item.get("size_bytes") or sha256(p) != item.get("sha256"):
                failures.append(f"display derivative missing/changed: {item.get('path')}")
        for key in ("source_attribution", "source_license", "data_license", "source_fidelity_report", "clean_rebuild_report"):
            info = manifest.get(key, {})
            p = root / info.get("path", "")
            if not p.is_file() or sha256(p) != info.get("sha256"):
                failures.append(f"bound {key} file missing or changed")
        for rel, info in manifest.get("workflow_files", {}).items():
            p = root / info.get("package_path", "")
            if not p.is_file() or sha256(p) != info.get("sha256"):
                failures.append(f"workflow file missing/changed: {rel}")
        binding_path = root / "evidence/package-binding.json"
        binding = json.loads(binding_path.read_text(encoding="utf-8")) if binding_path.exists() else {}
        if binding.get("manifest_sha256") != manifest_digest:
            failures.append("package binding manifest SHA-256 mismatch")
        required_bound_files = {"catalog.json", "collection.json", "README.md", "AGENTS.md",
            "licenses/software/LICENSE", "licenses/software/NOTICE"}
        if not required_bound_files.issubset(set(binding.get("bound_files", {}))):
            failures.append("package binding omits required catalog, guidance, or software-license files")
        for rel, info in binding.get("bound_files", {}).items():
            p = root / rel
            if not p.is_file() or p.stat().st_size != info.get("size_bytes") or sha256(p) != info.get("sha256"):
                failures.append(f"bound package file missing/changed: {rel}")
        required_reports = ("stac-node-validation.json", "portolan-validation.json",
                            "local-http-duckdb-validation.json", "package-integrity-validation.json")
        for rel in required_reports:
            p = root / "evidence" / rel
            if not p.is_file(): failures.append(f"required validation report missing: {rel}")
        for rel, expected in binding.get("verification_sha256", {}).items():
            p = root / "evidence" / rel
            if not p.is_file() or sha256(p) != expected:
                failures.append(f"verification report missing/changed: {rel}")
        receipt_path = root / "package-receipt.json"
        if not receipt_path.is_file():
            failures.append("package receipt missing")
        else:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("manifest_sha256") != manifest_digest:
                failures.append("package receipt manifest SHA-256 mismatch")
            if receipt.get("package_binding_sha256") != sha256(binding_path):
                failures.append("package receipt binding SHA-256 mismatch")
            final_report = root / "evidence/final-package-verification.json"
            if receipt.get("final_verification_sha256") and (not final_report.is_file() or sha256(final_report) != receipt["final_verification_sha256"]):
                failures.append("final package verification report missing or changed")
    except Exception as e:
        failures.append(f"package verification error: {type(e).__name__}: {e}")
        manifest_digest = None
    return {"status": "passed" if not failures else "failed", "manifest_sha256": manifest_digest,
            "failures": failures}


def build(spec_path: Path) -> dict[str, Any]:
    spec_path = spec_path.resolve()
    spec_dir = spec_path.parent
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReleaseError(f"cannot read JSON spec {spec_path}: {e}") from e
    if not isinstance(spec, dict):
        raise ReleaseError("release specification must be a JSON object")
    for key in ("dataset_record_path", "release_id", "release_version", "output_dir", "assets",
                "source_fidelity_report_path", "clean_rebuild_report_path", "producers", "source_attribution"):
        if key not in spec: raise ReleaseError(f"missing required spec field: {key}")
    release_id = safe_id(str(spec["release_id"]), "release_id")
    ds_record_path = resolve_input(spec["dataset_record_path"], spec_dir)
    if not ds_record_path.is_file(): raise ReleaseError(f"canonical dataset record missing: {ds_record_path}")
    record = read_record(ds_record_path)
    dataset_id = safe_id(str(record.get("id", spec.get("dataset_id", ""))), "dataset id")
    title = str(spec.get("title") or record.get("title") or "").strip()
    if not title: raise ReleaseError("title must be supplied by the spec or canonical record")
    if spec.get("dataset_id") and spec["dataset_id"] != dataset_id:
        raise ReleaseError("spec.dataset_id differs from canonical record id")
    if spec.get("title") and record.get("title") and spec["title"] != record["title"]:
        raise ReleaseError("spec.title differs from canonical record title")
    if not isinstance(spec["assets"], list) or not spec["assets"]:
        raise ReleaseError("assets must be a non-empty array")
    if not isinstance(spec["producers"], list) or not spec["producers"]:
        raise ReleaseError("producers must be a non-empty array")
    if not isinstance(spec["source_attribution"], dict):
        raise ReleaseError("source_attribution must be an object")
    catalog_id = safe_id(str(spec.get("catalog_id", "folia-" + dataset_id)), "catalog_id")
    processor = spec.get("processor", {"name": "Folia", "roles": ["host", "processor"],
        "url": "https://folia.sh", "description": "Local candidate package only; public hosting has not occurred."})
    if (not isinstance(processor, dict) or not isinstance(processor.get("name"), str)
            or not processor["name"].strip() or processor.get("roles") not in (["processor"], ["host", "processor"])):
        raise ReleaseError("processor must name the converter and use processor roles")
    source_href = spec["source_attribution"].get("url")
    source_title = spec["source_attribution"].get("title")
    if not isinstance(source_href, str) or not source_href.startswith("https://") or not source_title:
        raise ReleaseError("source_attribution requires HTTPS url and title")
    out = resolve_input(spec["output_dir"], spec_dir)
    if out.exists(): raise ReleaseError(f"refuse overwrite existing immutable release path: {out}")
    if not out.parent.is_dir(): raise ReleaseError(f"output parent must already exist: {out.parent}")

    assets: list[dict[str, Any]] = []
    ids = set()
    for raw in spec["assets"]:
        if not isinstance(raw, dict): raise ReleaseError("each asset must be an object")
        for k in ("asset_id", "path", "identifier_column"):
            if k not in raw: raise ReleaseError(f"asset is missing {k}")
        asset_id = safe_id(str(raw["asset_id"]), "asset_id")
        if asset_id in ids: raise ReleaseError(f"duplicate asset_id: {asset_id}")
        ids.add(asset_id)
        src = resolve_input(raw["path"], spec_dir)
        if not src.is_file(): raise ReleaseError(f"asset is missing: {src}")
        if src.suffix.lower() != ".parquet": raise ReleaseError(f"asset must be a .parquet file: {src}")
        assets.append({**raw, "asset_id": asset_id, "path": str(src), "_source": str(src), "_spec_dir": spec_dir})

    infos = [parquet_metadata(a, Path(a["_source"])) for a in assets]
    descriptors = []
    for a in assets:
        path = Path(a["_source"])
        descriptors.append({"asset_id": a["asset_id"], "sha256": sha256(path), "size_bytes": path.stat().st_size})
    expected_report_assets = {x["asset_id"]: (x["sha256"], x["size_bytes"]) for x in descriptors}
    source_report, source_report_bytes = load_and_bind_report(spec["source_fidelity_report_path"], "source_fidelity", spec_dir, expected_report_assets)
    rebuild_report, rebuild_report_bytes = load_and_bind_report(spec["clean_rebuild_report_path"], "clean_rebuild", spec_dir, expected_report_assets)
    bbox = get_bbox(infos, assets, spec)

    # From here the output is an immutable, uniquely named staging directory.
    out.mkdir(parents=False)
    package_assets = []
    clone_modes: dict[str, str] = {}
    try:
        (out / "assets").mkdir()
        for a, info, d in zip(assets, infos, descriptors):
            dest_rel = f"assets/{a['asset_id']}.parquet"
            mode = copy_portable(Path(a["_source"]), out / dest_rel)
            clone_modes[a["asset_id"]] = mode
            if sha256(out / dest_rel) != d["sha256"]:
                raise ReleaseError(f"copied package asset hash differs: {a['asset_id']}")
            fd_rel = None
            fd = info["field_dictionary"]
            if fd:
                ext = Path(fd["path"]).suffix or ".txt"
                fd_rel = f"metadata/{a['asset_id']}-field-dictionary{ext}"
                copy_portable(fd["path"], out / fd_rel)
            else:
                fd_rel = f"metadata/{a['asset_id']}-field-dictionary.json"
                write_json(out / fd_rel, {"asset_id": a["asset_id"], "identifier_column": a["identifier_column"],
                    "fields": [{**c, **({"identifier": True} if c["name"] == a["identifier_column"] else {})}
                               for c in info["table_columns"]]})
            package_assets.append({**d, "href": dest_rel, "media_type": a.get("media_type", PARQUET_MEDIA),
                                   "title": a.get("title", a["asset_id"]), "description": a.get("description", "Analytic GeoParquet asset"),
                                   "identifier_column": a["identifier_column"], "row_count": info["rows"],
                                   "field_dictionary": fd_rel, "field_dictionary_sha256": sha256(out / fd_rel),
                                   "geometry_column": info["primary_geometry"],
                                   "geometry_types": info["geometry_metadata"].get("geometry_types", []),
                                   "geo_metadata_version": info["geo_metadata"].get("version"),
                                   "source_path": Path(a["_source"]).name})
        thumbnail = make_thumbnail(assets, infos, out / "display/thumbnail.png", bbox)
        copy_portable(ds_record_path, out / "dataset.yaml")
        write_json(out / "source/attribution.json", spec["source_attribution"])
        supporting_files = []
        support_specs = spec.get("supporting_files", [])
        if not isinstance(support_specs, list): raise ReleaseError("supporting_files must be an array")
        for item in support_specs:
            if not isinstance(item, dict) or not all(k in item for k in ("path", "package_path", "title")):
                raise ReleaseError("each supporting_files entry needs path, package_path, and title")
            src = resolve_input(item["path"], spec_dir)
            if not src.is_file(): raise ReleaseError(f"supporting file is missing: {src}")
            rel = Path(str(item["package_path"]))
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise ReleaseError(f"unsafe supporting package_path: {rel}")
            if (out / rel).exists(): raise ReleaseError(f"supporting package_path already exists: {rel}")
            mode = copy_portable(src, out / rel)
            media = item.get("media_type") or mimetypes.guess_type(src.name)[0] or "application/octet-stream"
            supporting_files.append({"path": rel.as_posix(), "title": str(item["title"]),
                "media_type": str(media), "sha256": sha256(out / rel), "size_bytes": (out / rel).stat().st_size,
                "source_basename": src.name, "copy_mode": mode, "description": item.get("description")})
        source_license = spec.get("source_license") or spec["source_attribution"].get("license") or {
            "note": "See producer/source attribution and canonical dataset record for upstream license terms."}
        write_json(out / "licenses/source-license.json", source_license)
        write_json(out / "licenses/data-license.json", spec.get("data_license", {
            "license": record.get("license", "see canonical dataset record"),
            "source_url": source_href,
            "note": "Dataset-specific license and attribution are retained from the canonical record and producer source."}))
        code_license = REPO / "LICENSE"
        notice = REPO / "NOTICE"
        if not code_license.is_file() or not notice.is_file():
            raise ReleaseError("repository software LICENSE and NOTICE are required package materials")
        copy_portable(code_license, out / "licenses/software/LICENSE")
        copy_portable(notice, out / "licenses/software/NOTICE")
        (out / "README.md").write_text(make_readme(spec, dataset_id, title, release_id, release_version=str(spec["release_version"]),
            assets=package_assets, bbox=bbox, reports={"source_fidelity": source_report["report"], "clean_rebuild": rebuild_report["report"]}))
        (out / "AGENTS.md").write_text(make_agents(dataset_id, release_id, package_assets))

        code_revision = spec.get("code_revision")
        if not code_revision:
            try: code_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
            except Exception: code_revision = "unknown"
        workflow = {}
        workflow_paths = spec.get("workflow_paths", [])
        if not isinstance(workflow_paths, list): raise ReleaseError("workflow_paths must be an array of repository-relative paths")
        # The generic helper and its locked runtime are always included.
        defaults = ["scripts/release_tools/package_release.py", "scripts/release_tools/serve.py",
                    "scripts/release_tools/add_spatial_bounds.py", "scripts/release_tools/test_spatial_bounds.py",
                    "scripts/release_tools/pyproject.toml", "scripts/release_tools/uv.lock",
                    "scripts/release_tools/package.json", "scripts/release_tools/package-lock.json",
                    "scripts/release_tools/README.md", "scripts/release_tools/AGENTS.md",
                    "scripts/release_tools/test_package_release.py",
                    "scripts/release_tools/add_spatial_bounds.py", "scripts/release_tools/test_spatial_bounds.py"]
        revisions = spec.get("workflow_revisions", {})
        if not isinstance(revisions, dict):
            raise ReleaseError("workflow_revisions must map repository-relative files to full Git commit IDs")
        allowed_workflow = set(defaults + [str(x) for x in workflow_paths])
        if set(revisions) - allowed_workflow:
            raise ReleaseError("workflow_revisions keys must be included in workflow_paths or helper defaults")
        for revision in revisions.values():
            if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise ReleaseError("workflow revision must be a full lowercase 40-character Git commit ID")
        seen_workflow = set()
        for rel in defaults + [str(x) for x in workflow_paths]:
            relpath = Path(rel)
            if relpath.is_absolute() or ".." in relpath.parts:
                raise ReleaseError(f"workflow path must be repository-relative and safe: {rel}")
            src = (REPO / relpath).resolve()
            if not src.is_file(): raise ReleaseError(f"workflow file does not exist: {rel}")
            key = relpath.as_posix()
            if key in seen_workflow: continue
            seen_workflow.add(key)
            dest_rel = "verification/workflow/" + key
            revision = revisions.get(key)
            if revision:
                selected = subprocess.run(["git", "show", f"{revision}:{key}"], cwd=REPO, capture_output=True)
                if selected.returncode:
                    raise ReleaseError(f"cannot read pinned workflow {key} at {revision}")
                body = selected.stdout
                if len(body) > 8 * 1024 * 1024:
                    raise ReleaseError(f"workflow snapshot exceeds 8 MiB: {key}")
                destination = out / dest_rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(body)
                workflow[key] = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                                 "package_path": dest_rel, "git_revision": revision}
            else:
                copy_portable(src, out / dest_rel)
                workflow[key] = {"sha256": sha256(src), "bytes": src.stat().st_size, "package_path": dest_rel}

        (out / "evidence").mkdir()
        (out / "evidence/source-fidelity.json").write_bytes(source_report_bytes)
        (out / "evidence/clean-rebuild.json").write_bytes(rebuild_report_bytes)
        manifest = {"manifest_version": "1.0", "dataset_id": dataset_id, "title": title,
                    "release_id": release_id, "release_version": str(spec["release_version"]),
                    "status": "local-candidate", "publicly_published": False,
                    "dataset_record": {"path": "dataset.yaml", "sha256": sha256(out / "dataset.yaml")},
                    "source_attribution": {"path": "source/attribution.json", "sha256": sha256(out / "source/attribution.json")},
                    "source_license": {"path": "licenses/source-license.json", "sha256": sha256(out / "licenses/source-license.json")},
                    "data_license": {"path": "licenses/data-license.json", "sha256": sha256(out / "licenses/data-license.json")},
                    "assets": package_assets, "supporting_files": supporting_files,
                    "display_derivatives": [thumbnail],
                    "source_fidelity_report": {"path": "evidence/source-fidelity.json", "sha256": sha256(out / "evidence/source-fidelity.json")},
                    "clean_rebuild_report": {"path": "evidence/clean-rebuild.json", "sha256": sha256(out / "evidence/clean-rebuild.json")},
                    "code_revision": code_revision, "workflow_files": workflow,
                    "copied_data_modes": clone_modes, "created": spec.get("created") or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "spatial_bbox": bbox, "temporal_interval": spec.get("temporal_interval", [None, None]),
                    "scope_note": "Local package only; not uploaded, publicly hosted, or submitted to a registry."}
        write_json(out / "manifest.json", manifest)
        manifest_digest = sha256(out / "manifest.json")

        stac_created = manifest["created"]
        canonical_license = record.get("license")
        if isinstance(canonical_license, dict):
            canonical_license = canonical_license.get("spdx") or canonical_license.get("id") or canonical_license.get("identifier") or "other"
        portolan_license = str(spec.get("stac_license") or
            (spec.get("data_license", {}).get("stac_license") if isinstance(spec.get("data_license"), dict) else None) or
            (canonical_license if isinstance(canonical_license, str) else "other"))
        source_links = [{"rel": "via", "href": source_href, "type": "text/html", "title": source_title}]
        license_info = spec.get("data_license", {})
        lic_url = license_info.get("url") if isinstance(license_info, dict) else None
        if not lic_url and isinstance(record.get("license"), dict): lic_url = record["license"].get("url")
        if not lic_url and isinstance(record.get("license"), str) and record["license"].startswith("https://"): lic_url = record["license"]
        if lic_url: source_links.append({"rel": "license", "href": lic_url, "type": "text/html"})
        providers = []
        for provider in spec["producers"]:
            if not isinstance(provider, dict) or not provider.get("name"):
                raise ReleaseError("each producer must include a name")
            prov = {**provider}
            roles = prov.get("roles", ["producer"])
            if "producer" not in roles: roles = list(roles) + ["producer"]
            prov["roles"] = roles
            providers.append(prov)
        providers.append(processor)
        data_assets = {}
        table_columns = []
        for asset, info, entry in zip(assets, infos, package_assets):
            data_assets[asset["asset_id"]] = stac_asset(entry["href"], entry["media_type"], ["data"], entry["title"], entry["size_bytes"], entry["sha256"])
            # One field dictionary link per analytic asset.
            table_columns.extend({**c, "asset": asset["asset_id"]} for c in info["table_columns"])
            fd = entry["field_dictionary"]
            field_media = "application/json" if Path(fd).suffix.lower() == ".json" else (mimetypes.guess_type(fd)[0] or "text/plain")
            data_assets[asset["asset_id"] + "_fields"] = stac_asset(fd, field_media, ["metadata"],
                f"{asset['asset_id']} field dictionary", (out / fd).stat().st_size, sha256(out / fd))
        data_assets["thumbnail"] = stac_asset(thumbnail["path"], "image/png", ["thumbnail"],
            "Sampled display-only overview; not an analytic asset", thumbnail["size_bytes"], thumbnail["sha256"])
        for index, item in enumerate(supporting_files):
            data_assets[f"support-{index+1}"] = stac_asset(item["path"], item["media_type"], ["metadata"],
                item["title"], item["size_bytes"], item["sha256"])
        collection_id = dataset_id
        description = str(spec.get("description") or record.get("description") or title)
        collection = {"type": "Collection", "stac_version": "1.1.0",
            "stac_extensions": [PORTOLAN, FILE_EXT, TABLE_EXT, SCIENTIFIC_EXT, VERSION_EXT],
            "id": collection_id, "title": title, "description": description,
            "created": stac_created, "updated": stac_created, "license": portolan_license,
            "version": str(spec["release_version"]),
            "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [spec.get("temporal_interval", [None, None])]}},
            "providers": providers, "links": [{"rel": "root", "href": "catalog.json", "type": "application/json"},
                {"rel": "parent", "href": "catalog.json", "type": "application/json"},
                {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
                {"rel": "agents", "href": "AGENTS.md", "type": "text/markdown"},
                {"rel": "thumbnail", "href": "display/thumbnail.png", "type": "image/png"},
                *source_links],
            "assets": data_assets, "table:columns": table_columns,
            "sci:citation": spec.get("citation", source_title),
            "portolan:version": "0.2.0"}
        if spec.get("doi"): collection["sci:doi"] = str(spec["doi"])
        write_json(out / "collection.json", collection)
        catalog = {"type": "Catalog", "stac_version": "1.1.0", "stac_extensions": [PORTOLAN],
            "id": catalog_id, "title": title, "description": description,
            "created": stac_created, "updated": stac_created,
            "links": [{"rel": "root", "href": "catalog.json", "type": "application/json"},
                {"rel": "child", "href": "collection.json", "type": "application/json", "title": title},
                {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
                {"rel": "agents", "href": "AGENTS.md", "type": "text/markdown"},
                {"rel": "thumbnail", "href": "display/thumbnail.png", "type": "image/png"}, *source_links],
            "portolan:version": "0.2.0"}
        write_json(out / "catalog.json", catalog)

        # Bounded local verification; retain each stage report even on failure.
        node_report, port_report = run_schema_gates(out, manifest_digest)
        write_json(out / "evidence/stac-node-validation.json", node_report)
        write_json(out / "evidence/portolan-validation.json", port_report)
        local_report: dict[str, Any] = {"status": "pending", "release_manifest_sha256": manifest_digest,
            "checks": ["GeoParquet metadata", "asset checksums", "HTTP 206/CORS and range cap", "DuckDB local/HTTP subset match"]}
        try:
            # Confirm copies, metadata and manifest binding before serving them.
            for item in package_assets:
                path = out / item["href"]
                if not path.is_file() or path.stat().st_size != item["size_bytes"] or sha256(path) != item["sha256"]:
                    raise ReleaseError(f"manifest asset check failed: {item['asset_id']}")
            network = http_and_subset_checks(out, assets, infos, bbox, spec)
            local_report.update(status=network.get("status"), release_manifest_sha256=manifest_digest, http_and_subset=network,
                                validated_asset_ids=[x["asset_id"] for x in package_assets])
        except Exception as e:
            local_report.update(status="failed", error=f"{type(e).__name__}: {e}")
        write_json(out / "evidence/local-http-duckdb-validation.json", local_report)
        validations_passed = node_report.get("status") == "passed" and port_report.get("status") == "passed" and local_report.get("status") == "passed"
        state = "prepared-local" if validations_passed else "failed-local-validation"
        integrity = {"status": "passed", "release_manifest_sha256": manifest_digest,
                     "asset_ids": [x["asset_id"] for x in package_assets],
                     "asset_sha256": {x["asset_id"]: x["sha256"] for x in package_assets},
                     "detail": "Manifest, dataset record, attribution, license, field dictionaries, assets, reports, and workflow snapshots checked before binding."}
        write_json(out / "evidence/package-integrity-validation.json", integrity)
        verification = {name: sha256(out / f"evidence/{name}") for name in (
            "source-fidelity.json", "clean-rebuild.json", "stac-node-validation.json", "portolan-validation.json", "local-http-duckdb-validation.json", "package-integrity-validation.json")}
        bound_paths = ["catalog.json", "collection.json", "README.md", "AGENTS.md",
            "licenses/software/LICENSE", "licenses/software/NOTICE"]
        bound_paths.extend(x["path"] for x in supporting_files)
        bound_files = {}
        for rel in bound_paths:
            path = out / rel
            if path.is_file(): bound_files[rel] = {"sha256": sha256(path), "size_bytes": path.stat().st_size}
        binding = {"manifest_sha256": manifest_digest, "bound_files": bound_files,
            "dataset_record_sha256": manifest["dataset_record"]["sha256"],
            "source_attribution_sha256": manifest["source_attribution"]["sha256"],
            "source_fidelity_report_sha256": manifest["source_fidelity_report"]["sha256"],
            "clean_rebuild_report_sha256": manifest["clean_rebuild_report"]["sha256"],
            "asset_sha256": {x["asset_id"]: x["sha256"] for x in package_assets},
            "workflow_sha256": {k: v["sha256"] for k,v in workflow.items()},
            "verification_sha256": verification}
        write_json(out / "evidence/package-binding.json", binding)
        receipt = {"status": "packaged_locally_not_published" if state == "prepared-local" else state,
                   "dataset_id": dataset_id, "release_id": release_id, "release_version": str(spec["release_version"]),
                   "package_dir": out.name, "manifest_sha256": manifest_digest,
                   "package_binding_sha256": sha256(out / "evidence/package-binding.json"),
                   "asset_count": len(package_assets), "assets": descriptors,
                   "publicly_published": False, "registry_submitted": False}
        write_json(out / "package-receipt.json", receipt)
        final_integrity = verify_package(out)
        write_json(out / "evidence/final-package-verification.json", final_integrity)
        if final_integrity["status"] != "passed":
            receipt["status"] = "failed-package-integrity"
            receipt["integrity_failures"] = final_integrity["failures"]
            write_json(out / "package-receipt.json", receipt)
            state = "failed-package-integrity"
        else:
            receipt["final_verification_sha256"] = sha256(out / "evidence/final-package-verification.json")
            write_json(out / "package-receipt.json", receipt)
            post_receipt = verify_package(out)
            if post_receipt["status"] != "passed":
                post_receipt_path = out / "evidence/final-package-verification.json"
                write_json(post_receipt_path, post_receipt)
                receipt["status"] = "failed-package-integrity"
                receipt["final_verification_sha256"] = sha256(post_receipt_path)
                receipt["integrity_failures"] = post_receipt["failures"]
                write_json(out / "package-receipt.json", receipt)
                state = "failed-package-integrity"
        # A failure remains readable and explicitly failed; a passing package is made read-only.
        if state == "prepared-local": chmod_readonly(out)
        if state != "prepared-local":
            raise ReleaseError(f"package retained with status {state}; see {out / 'evidence'}")
        return receipt
    except Exception as error:
        # Preserve the partial directory and any failed reports for inspection.
        if out.exists() and not (out / "package-receipt.json").exists():
            try:
                write_json(out / "evidence/package-staging-failure.json", {
                    "status": "failed", "stage": "package_staging", "error": f"{type(error).__name__}: {error}"})
            except Exception:
                pass
        raise


def make_readme(spec: dict[str, Any], dataset_id: str, title: str, release_id: str,
                release_version: str, assets: list[dict[str, Any]], bbox: list[float], reports: dict[str, Any]) -> str:
    lines = [f"# {title}", "", "Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.", "",
        f"Dataset ID: `{dataset_id}`  ", f"Release: `{release_id}` (`{release_version}`)  ",
        f"Spatial extent: `{bbox}`  ", f"Source: [{spec['source_attribution']['title']}]({spec['source_attribution']['url']})", "",
        "## Analytic assets", "", "| Asset | Path | Rows | Identifier column | SHA-256 |", "|---|---|---:|---|---|"]
    for a in assets:
        lines.append(f"| `{a['asset_id']}` | `{a['href']}` | {a['row_count']} | `{a['identifier_column']}` | `{a['sha256']}` |")
    lines.extend(["", "## Evidence", "", "The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.", "",
        "## Licenses and attribution", "", f"Source attribution: {spec['source_attribution'].get('attribution', spec['source_attribution']['title'])}.", "",
        "Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.", "",
        "## Reproduction", "", "The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.", ""])
    return "\n".join(lines)


def make_agents(dataset_id: str, release_id: str, assets: list[dict[str, Any]]) -> str:
    asset_names = ", ".join(f"`{x['href']}`" for x in assets)
    return (f"# Package instructions\n\nDataset `{dataset_id}`, release `{release_id}`. Use only the analytic GeoParquet assets {asset_names} for analysis. "
            "Preserve source identifiers, values, nulls, geometry, CRS, and feature multiplicity. Field dictionaries are in `metadata/`. "
            "This is a local package, not evidence of public hosting or registry acceptance. Keep `manifest.json`, `dataset.yaml`, source attribution, licenses, workflow hashes, and validation reports together.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", nargs="?", type=Path, help="JSON package specification; relative paths resolve from the spec file")
    ap.add_argument("--verify", type=Path, help="verify an existing immutable package directory")
    args = ap.parse_args()
    try:
        if args.verify:
            report = verify_package(args.verify)
            print(json.dumps(report, indent=2))
            return 0 if report["status"] == "passed" else 1
        if args.spec is None:
            ap.error("provide a release specification or --verify package_dir")
        result = build(args.spec)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(f"release package failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
