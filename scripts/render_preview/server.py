#!/usr/bin/env python3
"""Serve a local, interactive browser view backed by the retained GeoParquet files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import duckdb
from shapely import from_wkb
from shapely.geometry import box, mapping


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = Path.home() / "projects/data-publications/.local"


def asset_specs(data_root: Path) -> dict:
    return {
    "hydrolakes-polygons": {
        "path": data_root / "hydrolakes/releases/v1-local-r3/assets/hydrolakes-polygons.parquet",
        "manifest": data_root / "hydrolakes/releases/v1-local-r3/manifest.json",
        "geometry": "wkb_geometry",
        "id": "Hylak_id",
        "fields": ["Lake_name", "Lake_area", "Country"],
        "kind": "polygon",
        "label": "HydroLAKES polygons",
    },
    "free-flowing-rivers": {
        "path": data_root / "free-flowing-rivers/releases/figshare-v1-local-r2/assets/ffr-reach-network-v1.parquet",
        "manifest": data_root / "free-flowing-rivers/releases/figshare-v1-local-r2/manifest.json",
        "manifest_id": "ffr-reach-network-v1",
        "geometry": "Shape",
        "id": "OBJECTID",
        "fields": ["REACH_ID", "COUNTRY", "CONTINENT", "LENGTH_KM", "CSI_D"],
        "kind": "line",
        "label": "Free-Flowing Rivers reaches",
    },
    "lakeatlas-polygons": {
        "path": data_root / "lakeatlas/releases/lakeatlas-v1.0-r2-prepared/assets/lakeatlas-polygons.parquet",
        "manifest": data_root / "lakeatlas/releases/lakeatlas-v1.0-r2-prepared/manifest.json",
        "geometry": "geometry",
        "id": "OBJECTID",
        "fields": ["Hylak_id", "Lake_name", "Lake_area", "Country", "HYRIV_RCH"],
        "kind": "polygon",
        "label": "LakeATLAS polygons",
    },
    "lakeatlas-pour-points": {
        "path": data_root / "lakeatlas/releases/lakeatlas-v1.0-r2-prepared/assets/lakeatlas-pour-points.parquet",
        "manifest": data_root / "lakeatlas/releases/lakeatlas-v1.0-r2-prepared/manifest.json",
        "geometry": "geometry",
        "id": "OBJECTID",
        "fields": ["Hylak_id", "Lake_name", "Country", "dis_m3_pyr"],
        "kind": "point",
        "label": "LakeATLAS pour points",
    },
    }


ASSETS = asset_specs(DEFAULT_DATA_ROOT)
REGIONS = {
    "north_america": {"label": "North America", "bbox": [-93, 47, -87, 50]},
    "south_america": {"label": "South America", "bbox": [-65, -5, -60, 0]},
    "europe": {"label": "Europe", "bbox": [5, 45, 15, 55]},
    "asia": {"label": "Asia", "bbox": [100, 25, 110, 35]},
    "oceania": {"label": "Oceania", "bbox": [140, -40, 150, -30]},
}
MAX_FEATURES = 1000
QUERY_GATE = threading.BoundedSemaphore(1)


def source_inventory(verify_hashes: bool = True) -> dict:
    result = {}
    for asset_id, spec in ASSETS.items():
        manifest = json.loads(spec["manifest"].read_text())
        manifest_id = spec.get("manifest_id", asset_id)
        entry = next((item for item in manifest["assets"] if item["asset_id"] == manifest_id), None)
        if entry is None:
            raise ValueError(f"{asset_id} missing from immutable release manifest")
        path = spec["path"]
        if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
            raise ValueError(f"{asset_id} file missing or size differs from immutable manifest")
        if verify_hashes:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != entry["sha256"]:
                raise ValueError(f"{asset_id} sha256 differs from immutable release manifest")
        result[asset_id] = {
            "label": spec["label"],
            "kind": spec["kind"],
            "path": str(path),
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
            "rows": entry["row_count"],
            "display_transform": "bbox query; geometry clipped to view; simplified for screen display",
            "max_returned_features": MAX_FEATURES,
        }
    return result


def valid_bbox(raw: str) -> list[float]:
    try:
        values = [float(x.strip()) for x in raw.split(",")]
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox must be four comma-separated numbers") from exc
    if len(values) != 4 or not all(math.isfinite(x) for x in values):
        raise ValueError("bbox must be four finite numbers")
    xmin, ymin, xmax, ymax = values
    if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
        raise ValueError("bbox must be ordered within WGS84 longitude and latitude bounds")
    return values


def json_value(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def query_asset(asset_id: str, bbox_values: list[float], inventory: dict) -> dict:
    spec = ASSETS[asset_id]
    xmin, ymin, xmax, ymax = bbox_values
    with QUERY_GATE:
        con = duckdb.connect(database=":memory:", read_only=False)
        con.execute("SET threads=1")
        parquet = str(spec["path"]).replace("'", "''")
        source = f"read_parquet('{parquet}')"
        where = "bbox.xmax >= ? AND bbox.xmin <= ? AND bbox.ymax >= ? AND bbox.ymin <= ?"
        total = con.execute(f"SELECT count(*) FROM {source} WHERE {where}", [xmin, xmax, ymin, ymax]).fetchone()[0]
        cols = [spec["id"], *spec["fields"], spec["geometry"]]
        select = ", ".join('"' + c.replace('"', '""') + '"' for c in cols)
        # Identifiers are stable in each source. Deterministic ordering makes the capped
        # display subset repeatable and prevents file-order changes from looking scientific.
        rows = con.execute(
            f"SELECT {select} FROM {source} WHERE {where} ORDER BY \"{spec['id']}\" LIMIT {MAX_FEATURES}",
            [xmin, xmax, ymin, ymax],
        ).fetchall()
        con.close()
    clip = box(xmin, ymin, xmax, ymax)
    tolerance = max((xmax - xmin), (ymax - ymin)) / 1200
    features = []
    for row in rows:
        source_id, *tail = row
        wkb = tail[-1]
        attrs = tail[:-1]
        if not wkb:
            continue
        geom = from_wkb(wkb)
        if geom.is_empty:
            continue
        # Clipping and simplification affect only this display response; source WKB is untouched.
        geom = geom.intersection(clip)
        if geom.is_empty:
            continue
        if spec["kind"] != "point":
            geom = geom.simplify(tolerance, preserve_topology=True)
        props = {"source_id": json_value(source_id)}
        props.update({field: json_value(value) for field, value in zip(spec["fields"], attrs)})
        features.append({"type": "Feature", "id": str(json_value(source_id)), "properties": props, "geometry": mapping(geom)})
    return {
        "asset_id": asset_id,
        "label": spec["label"],
        "kind": spec["kind"],
        "bbox": bbox_values,
        "source_sha256": inventory[asset_id]["sha256"],
        "matched_rows": int(total),
        "returned_rows": len(features),
        "capped": total > MAX_FEATURES,
        "max_returned_features": MAX_FEATURES,
        "display_note": "Screen-only geometry clipped to bbox and simplified; deterministic lowest source IDs returned up to cap.",
        "type": "FeatureCollection",
        "features": features,
    }


def make_handler(inventory: dict, log_path: Path | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FoliaLocalRender/1.0"

        def log_message(self, _fmt, *_args):
            return

        def send_json(self, payload, status=200, headers=None):
            body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "null")
            for key, value in (headers or {}).items():
                self.send_header(key, str(value))
            self.end_headers()
            self.wfile.write(body)
            return len(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            started = time.time()
            status, response_bytes, entry = 200, 0, {"path": parsed.path}
            try:
                if parsed.path == "/":
                    body = (HERE / "index.html").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    response_bytes = len(body)
                elif parsed.path == "/api/sources":
                    response_bytes = self.send_json({"assets": inventory, "regions": REGIONS, "max_features_per_asset": MAX_FEATURES})
                elif parsed.path == "/api/features":
                    params = parse_qs(parsed.query, strict_parsing=True)
                    asset_id = params.get("asset", [""])[0]
                    if asset_id not in ASSETS:
                        raise ValueError("unknown asset")
                    if "region" in params:
                        region = params["region"][0]
                        if region not in REGIONS:
                            raise ValueError("unknown geographic control")
                        bbox_values = REGIONS[region]["bbox"]
                        entry["region"] = region
                    elif "bbox" in params:
                        bbox_values = valid_bbox(params["bbox"][0])
                    else:
                        raise ValueError("provide region or bbox")
                    result = query_asset(asset_id, bbox_values, inventory)
                    entry.update({"asset": asset_id, "bbox": bbox_values, "matched_rows": result["matched_rows"], "returned_rows": result["returned_rows"], "capped": result["capped"], "source_sha256": result["source_sha256"]})
                    response_bytes = self.send_json(result, headers={"X-Matched-Rows": result["matched_rows"], "X-Returned-Rows": result["returned_rows"], "X-Source-SHA256": result["source_sha256"]})
                else:
                    status = 404
                    response_bytes = self.send_json({"error": "not found"}, 404)
            except (ValueError, KeyError) as exc:
                status = 400
                entry["error"] = str(exc)
                response_bytes = self.send_json({"error": str(exc)}, 400)
            except Exception as exc:
                status = 500
                entry["error"] = f"{type(exc).__name__}: {exc}"
                response_bytes = self.send_json({"error": entry["error"]}, 500)
            finally:
                entry.update({"status": status, "response_bytes": response_bytes, "elapsed_ms": round((time.time() - started) * 1000, 2)})
                if log_path:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with log_path.open("a") as stream:
                        stream.write(json.dumps(entry, sort_keys=True) + "\n")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Loopback only by default; do not expose this local data server publicly")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT, help="Local data-publications/.local directory containing the retained releases")
    parser.add_argument("--log", type=Path, help="Append query/HTTP evidence as JSONL")
    parser.add_argument("--skip-hash-verification", action="store_true", help="Use only for a disposable development server; render evidence requires verification")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("server may bind only to loopback")
    global ASSETS
    ASSETS = asset_specs(args.data_root.expanduser().resolve())
    inventory = source_inventory(verify_hashes=not args.skip_hash_verification)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(inventory, args.log))
    print(f"Serving render preview at http://{args.host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
