#!/usr/bin/env python3
"""Capture and normalize the public Microsoft Planetary Computer STAC collections inventory.

Offline by default: checks retained inventory.json against the saved redacted pages.
Use --fetch --output-dir NEW_PATH for a new collection-list capture (never assets).
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlunparse

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "retained"
ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1/collections"
MAX_REQUESTS = 120
MAX_BYTES = 30_000_000
UA = "folia-global-candidate-research/1.0 (metadata-only STAC inventory)"


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_url(url: str) -> str:
    """Drop query and fragment from a URL before retaining it; collection pages are public."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))



def redact_url_credentials(value, path=()):
    """Remove signed/token query strings before retaining public provider metadata."""
    redactions = []
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result[key], changes = redact_url_credentials(item, (*path, key))
            redactions.extend(changes)
        return result, redactions
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            clean, changes = redact_url_credentials(item, (*path, index))
            result.append(clean); redactions.extend(changes)
        return result, redactions
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        keys = {key.lower() for key, _ in parse_qsl(parsed.query)}
        if keys & {"sig", "token", "access_token", "api_key", "apikey", "signature", "x-amz-signature"}:
            return safe_url(value), [{"json_path": list(path), "removed_query_parameters": sorted(keys)}]
    return value, redactions


def fetch_pages() -> dict:
    manifest_path = ROOT / "capture-manifest.json"
    existing_pages = list(RAW.glob("page-*.json")) if RAW.exists() else []
    if manifest_path.exists() or existing_pages:
        raise SystemExit(
            "Refusing to overwrite an existing Planetary Computer capture. "
            "Preserve this snapshot and use --output-dir with a new path."
        )
    RAW.mkdir(parents=True, exist_ok=True)
    url = ENDPOINT
    seen: set[str] = set()
    captures = []
    failures = []
    used = 0
    total_bytes = 0
    while url and used < MAX_REQUESTS and total_bytes < MAX_BYTES:
        req_url = url
        if req_url in seen:
            failures.append({"url": safe_url(req_url), "error": "pagination loop"})
            break
        seen.add(req_url)
        used += 1
        req = urllib.request.Request(req_url, headers={"User-Agent": UA, "Accept": "application/json"})
        started = utcnow()
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read(MAX_BYTES - total_bytes + 1)
                if total_bytes + len(body) > MAX_BYTES:
                    failures.append({"url": safe_url(req_url), "error": "30 MB response budget reached; page not retained"})
                    break
                total_bytes += len(body)
                obj, redactions = redact_url_credentials(json.loads(body))
                retained = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
                page_num = len(captures) + 1
                filename = f"page-{page_num:03d}.json"
                (RAW / filename).write_bytes(retained)
                captures.append({
                    "file": f"retained/{filename}", "requested_url": safe_url(req_url),
                    "retrieved_at": started, "http_date": response.headers.get("Date"),
                    "http_last_modified": response.headers.get("Last-Modified"),
                    "status": response.status, "bytes": len(retained), "sha256": sha256(retained),
                    "response_bytes": len(body), "response_sha256": sha256(body), "redactions": redactions,
                    "collection_count": len(obj.get("collections", [])),
                })
                nxt = next((x for x in obj.get("links", []) if x.get("rel") == "next"), None)
                url = nxt.get("href") if nxt else ""
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            failures.append({"url": safe_url(req_url), "error": f"{type(e).__name__}: {e}"})
            break
        time.sleep(0.15)
    if url and used >= MAX_REQUESTS:
        failures.append({"url": safe_url(url), "error": "120 request budget reached before pagination completed"})
    manifest = {
        "provider": "Microsoft Planetary Computer", "endpoint": ENDPOINT,
        "captured_at": utcnow(), "request_count": used, "bytes_total": total_bytes,
        "limits": {"max_requests": MAX_REQUESTS, "max_bytes": MAX_BYTES},
        "captures": captures, "failures": failures,
        "note": "Collection-list metadata only; no item, asset, signing, token, job, upload, or paid requests. Retained bodies remove signed URL query credentials.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _asset_formats(collection: dict) -> list[dict]:
    out = []
    for key, asset in sorted((collection.get("assets") or {}).items()):
        out.append({
            "key": key, "title": asset.get("title"), "type": asset.get("type"),
            "roles": asset.get("roles", []), "href": asset.get("href"),
        })
    return out


def normalize(write: bool = True) -> dict:
    manifest_path = ROOT / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"captures": [], "failures": [], "endpoint": ENDPOINT}
    collections: dict[str, dict] = {}
    source_pages = []
    for capture in manifest.get("captures", []):
        p = ROOT / capture["file"]
        body = p.read_bytes()
        observed_hash = sha256(body)
        if observed_hash != capture["sha256"]:
            raise ValueError(f"hash mismatch for {capture['file']}: manifest {capture['sha256']} actual {observed_hash}")
        obj = json.loads(body)
        source_pages.append({**capture, "hash_verified": True})
        for c in obj.get("collections", []):
            cid = c.get("id")
            if not cid:
                continue
            links = c.get("links", []) or []
            self_link = next((l.get("href") for l in links if l.get("rel") == "self"), None)
            source = self_link or f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{cid}"
            extent = c.get("extent", {})
            spatial = extent.get("spatial", {})
            temporal = extent.get("temporal", {})
            license_value = c.get("license")
            # API responses generally use the STAC collection license string, not a verified rights statement.
            entry = {
                "id": cid, "title": c.get("title"), "description": c.get("description"),
                "keywords": c.get("keywords", []), "providers": c.get("providers", []),
                "license": license_value, "license_metadata_status": "provider metadata declaration; redistribution terms not independently verified",
                "extent": {"spatial_bbox": spatial.get("bbox", []), "temporal_interval": temporal.get("interval", [])},
                "summaries": c.get("summaries", {}), "item_assets": c.get("item_assets", {}),
                "assets": _asset_formats(c), "collection_url": source,
                "landing_links": [{"rel": l.get("rel"), "href": l.get("href"), "type": l.get("type"), "title": l.get("title")} for l in links if l.get("rel") in {"about", "license", "documentation", "cite-as", "describedby", "alternate", "parent", "root"}],
                "stac_version": c.get("stac_version"),
            }
            if cid in collections and collections[cid] != entry:
                raise ValueError(f"duplicate collection id with differing metadata: {cid}")
            collections[cid] = entry
    result = {
        "schema_version": 1, "provider": "Microsoft Planetary Computer",
        "source_endpoint": ENDPOINT, "normalized_at": utcnow(),
        "capture_manifest_sha256": sha256(manifest_path.read_bytes()) if manifest_path.exists() else None,
        "source_pages": source_pages,
        "collection_count": len(collections), "collections": [collections[k] for k in sorted(collections)],
        "failures": manifest.get("failures", []),
        "limitations": ["Current public STAC collection metadata only; no item or asset bytes fetched.", "Extent and license are provider metadata, not validated coverage or redistribution rights.", "Inventory may be incomplete where the bounded capture reports failures or pagination stops."],
    }
    out = ROOT / "inventory.json"
    if write:
        out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return result


def main() -> int:
    global ROOT, RAW
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="Fetch collection metadata into a new output directory")
    mode.add_argument("--check", action="store_true", help="Check retained inventory offline (default)")
    ap.add_argument("--output-dir", type=Path, help="New capture directory for --fetch; existing capture for --check")
    args = ap.parse_args()
    if args.fetch and (args.output_dir is None or args.output_dir.exists()):
        ap.error("--fetch requires a new, nonexistent --output-dir; no requests made")
    if args.output_dir is not None:
        ROOT = args.output_dir.resolve()
        RAW = ROOT / "retained"
    manifest = fetch_pages() if args.fetch else None
    if not args.fetch:
        inventory_path = ROOT / "inventory.json"
        old = json.loads(inventory_path.read_text())
        result = normalize(write=False)
        # Timestamp is intentionally volatile; all structural/source evidence must match.
        old.pop("normalized_at", None); result.pop("normalized_at", None)
        if old != result:
            print("inventory.json differs from deterministic offline normalization", file=sys.stderr)
            return 1
    else:
        result = normalize()
        print(json.dumps({"collection_count": result["collection_count"], "pages": len(result["source_pages"]), "failures": result["failures"], "bytes": (manifest or {}).get("bytes_total")}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
