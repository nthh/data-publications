#!/usr/bin/env python3
"""Validate one uploaded Source Cooperative product using anonymous HTTP.

This validator consumes the exact immutable upload plan and its uploader receipt.
It never authenticates to Source. HTTP range checks sample bytes; the bounded
DuckDB subset may fetch Parquet pages as required by DuckDB's query plan.
Browser rendering remains a separately supplied review attestation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib import error, request, parse

SCRIPT_DIR = Path(__file__).resolve().parent
UPLOAD_PATH = SCRIPT_DIR / "upload.py"
SPEC = importlib.util.spec_from_file_location("source_publish_upload", UPLOAD_PATH)
assert SPEC and SPEC.loader
upload = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = upload
SPEC.loader.exec_module(upload)
BOUND_PATH = SCRIPT_DIR / "bounded_http.py"
BOUND_SPEC = importlib.util.spec_from_file_location("source_publish_bounded_http", BOUND_PATH)
assert BOUND_SPEC and BOUND_SPEC.loader
bounded_http = importlib.util.module_from_spec(BOUND_SPEC)
sys.modules[BOUND_SPEC.name] = bounded_http
BOUND_SPEC.loader.exec_module(bounded_http)
BROWSER_RANGE_PATH = SCRIPT_DIR / "browser_range_evidence.py"
BROWSER_RANGE_SPEC = importlib.util.spec_from_file_location("source_publish_browser_range_evidence", BROWSER_RANGE_PATH)
assert BROWSER_RANGE_SPEC and BROWSER_RANGE_SPEC.loader
browser_range_evidence = importlib.util.module_from_spec(BROWSER_RANGE_SPEC)
sys.modules[BROWSER_RANGE_SPEC.name] = browser_range_evidence
BROWSER_RANGE_SPEC.loader.exec_module(browser_range_evidence)

VIEWER_ORIGIN = "https://browser.portolan-sdi.org"
DATA_ORIGIN = "https://data.source.coop"
OWNER = "nthh"
MAX_METADATA_BYTES = 10 * 1024 * 1024
RANGE_BYTES = 64 * 1024
REQUIRED_CHECKS = ("anonymous_access", "range_requests", "cors", "asset_checksums",
                   "subset_query", "catalog_links", "browser_render")
LARGE_SUFFIXES = (".parquet", ".pmtiles")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HostedValidationError(ValueError):
    """Unsafe or invalid hosted validation input."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostedValidationError(f"cannot read JSON input: {path}") from exc


def _safe_root(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise HostedValidationError(f"{label} must be an absolute directory without symlinks")
    return path.resolve(strict=True)


def _object_url(key: str) -> str:
    # Keys have already passed the upload plan's strict relative-path checks.
    return DATA_ORIGIN + "/" + OWNER + "/" + parse.quote(key, safe="/-._~")


def _url_is_product(url: str, product_id: str) -> bool:
    parsed = parse.urlsplit(url)
    prefix = f"/{OWNER}/{product_id}/"
    return (parsed.scheme == "https" and parsed.netloc == "data.source.coop"
            and parsed.path.startswith(prefix) and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment)


def _request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
             timeout: int = 60, max_body: int = MAX_METADATA_BYTES,
             opener: Any = request.urlopen) -> tuple[int, dict[str, str], bytes, str]:
    req = request.Request(url, headers=headers or {}, method=method)
    try:
        with opener(req, timeout=timeout) as response:
            body = response.read(max_body + 1)
            return response.status, dict(response.headers.items()), body, response.geturl()
    except Exception as exc:
        if isinstance(exc, error.HTTPError):
            body = exc.read(max_body + 1)
            return exc.code, dict(exc.headers.items()), body, exc.geturl()
        raise HostedValidationError(f"request failed for {url}: {type(exc).__name__}") from None


def _range_points(size: int) -> list[tuple[int, int]]:
    if size <= 0:
        raise HostedValidationError("range validation requires a non-empty object")
    width = min(RANGE_BYTES, size)
    starts = (0, max(0, (size - width) // 2), max(0, size - width))
    return list(dict.fromkeys((start, start + width - 1) for start in starts))


def _receipt_records(receipt: Path, plan_sha: str, entries: list[dict[str, Any]],
                     prior_receipts: list[Path] | None = None, *,
                     expected_multipart_parent_summary_sha256: str | None = None,
                     expected_multipart_parent_record_sha256: str | None = None
                     ) -> dict[str, dict[str, Any]]:
    if ((expected_multipart_parent_summary_sha256 is None)
            != (expected_multipart_parent_record_sha256 is None)):
        raise HostedValidationError("multipart parent requires both frozen SHA-256 inputs")
    for digest in (expected_multipart_parent_summary_sha256,
                   expected_multipart_parent_record_sha256):
        if digest is not None and (not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest)):
            raise HostedValidationError("multipart parent SHA-256 input is invalid")
    summary_path = receipt / "summary.json"
    summary = _json(summary_path)
    if (summary.get("schema_version") != 1 or summary.get("plan_sha256") != plan_sha
            or summary.get("mode") != "execute" or summary.get("status") != "complete"
            or summary.get("failed") != 0 or summary.get("completed") != len(entries)
            or summary.get("object_count") != len(entries)):
        raise HostedValidationError("uploader receipt summary is incomplete or bound to another plan")
    resume_mode = summary.get("resume_mode")
    if resume_mode == "existing_multipart":
        if expected_multipart_parent_summary_sha256 is None:
            raise HostedValidationError("multipart parent requires both frozen SHA-256 inputs")
        parent_summary_sha = summary.get("multipart_resume_parent_summary_sha256")
        if (parent_summary_sha != expected_multipart_parent_summary_sha256
                or type(summary.get("resumed_multipart")) is not int or summary["resumed_multipart"] != 1
                or not isinstance(parent_summary_sha, str) or not HEX_SHA256.fullmatch(parent_summary_sha)):
            raise HostedValidationError("multipart resume summary differs from frozen parent binding")
    elif resume_mode is not None or "resumed_multipart" in summary or "multipart_resume_parent_summary_sha256" in summary:
        raise HostedValidationError("uploader receipt has an unsupported multipart resume mode")
    elif expected_multipart_parent_summary_sha256 is not None:
        raise HostedValidationError("multipart parent SHA-256 inputs supplied for a normal receipt")
    records: dict[str, dict[str, Any]] = {}
    for path in sorted((receipt / "objects").glob("*.json")):
        record = _json(path)
        key = record.get("object_key")
        if key in records:
            raise HostedValidationError("duplicate object in uploader receipt")
        records[key] = record
    if set(records) != {entry["object_key"] for entry in entries}:
        raise HostedValidationError("uploader receipt does not cover the selected upload plan")
    prior_receipts = prior_receipts or []
    prior_by_sha = {}
    for prior in prior_receipts:
        summary_file = prior / "summary.json"
        digest = hashlib.sha256(summary_file.read_bytes()).hexdigest()
        if digest in prior_by_sha:
            raise HostedValidationError("duplicate prior receipt")
        old_summary = _json(summary_file)
        if (old_summary.get("schema_version") != 1 or old_summary.get("mode") != "execute"
                or old_summary.get("status") != "failed" or old_summary.get("plan_sha256") != plan_sha
                or old_summary.get("object_count") != len(entries)
                or old_summary.get("include_readme") is not (summary.get("include_readme") is True)
                or type(old_summary.get("failed")) is not int or old_summary["failed"] != 1
                or type(old_summary.get("completed")) is not int
                or not 0 <= old_summary["completed"] < len(entries)):
            raise HostedValidationError("prior receipt summary is not the failed exact-plan attempt")
        prior_by_sha[digest] = prior
    used_prior = set()
    reused = 0
    resumed_multipart = 0
    for index, entry in enumerate(entries):
        record = records[entry["object_key"]]
        if (record.get("schema_version") != 1 or record.get("plan_sha256") != plan_sha
                or record.get("bucket") != OWNER
                or record.get("expected_sha256") != entry["sha256"]
                or record.get("expected_size_bytes") != entry["size_bytes"]
                or record.get("mutable") is not bool(entry.get("mutable"))
                or record.get("remote_sha256") != entry["sha256"]
                or record.get("status") not in {"uploaded_verified", "verified_existing", "verified_prior_attempt"}):
            raise HostedValidationError(f"uploader receipt lacks full remote checksum proof: {entry['object_key']}")
        multipart_parent = record.get("multipart_resume")
        if multipart_parent is not None:
            if resume_mode != "existing_multipart" or not isinstance(multipart_parent, dict):
                raise HostedValidationError("multipart target lacks declared resume mode")
            resumed_multipart += 1
            multipart = record.get("multipart")
            parent_sha = multipart_parent.get("summary_sha256")
            parent_record_sha = multipart_parent.get("record_sha256")
            expected_name = f"{index:04d}-{hashlib.sha256(entry['object_key'].encode()).hexdigest()[:16]}.json"
            if (record.get("status") != "uploaded_verified" or entry.get("mutable")
                    or record.get("remote_sha256_scope") != "current_attempt_full_remote_readback"
                    or type(record.get("bytes_transferred")) is not int
                    or record["bytes_transferred"] != entry["size_bytes"]
                    or not isinstance(multipart, dict) or multipart.get("state") != "completed"
                    or not isinstance(multipart.get("upload_id"), str) or not multipart["upload_id"]
                    or multipart_parent.get("mode") != "existing_multipart"
                    or parent_sha != parent_summary_sha or parent_sha not in prior_by_sha
                    or parent_record_sha != expected_multipart_parent_record_sha256
                    or not isinstance(parent_record_sha, str) or not HEX_SHA256.fullmatch(parent_record_sha)
                    or multipart_parent.get("record_name") != expected_name):
                raise HostedValidationError("multipart target is not bound to a completed exact-plan parent")
            parent_dir = prior_by_sha[parent_sha]
            parent_summary = _json(parent_dir / "summary.json")
            parent_path = parent_dir / "objects" / expected_name
            if (parent_summary.get("completed") != index or parent_path.is_symlink()
                    or not parent_path.is_file()
                    or hashlib.sha256(parent_path.read_bytes()).hexdigest() != parent_record_sha):
                raise HostedValidationError("multipart failed parent record is missing or changed")
            old = _json(parent_path)
            old_multipart = old.get("multipart")
            if (old.get("schema_version") != 1 or old.get("plan_sha256") != plan_sha
                    or old.get("bucket") != OWNER or old.get("object_key") != entry["object_key"]
                    or old.get("expected_size_bytes") != entry["size_bytes"]
                    or old.get("expected_sha256") != entry["sha256"] or old.get("mutable") is not False
                    or old.get("status") != "failed" or not isinstance(old_multipart, dict)
                    or old_multipart.get("state") not in {"open", "abort_failed"}
                    or old_multipart.get("upload_id") != multipart["upload_id"]):
                raise HostedValidationError("multipart failed parent differs from exact resumed target")
            used_prior.add(parent_sha)
        if record["status"] != "verified_prior_attempt":
            continue
        reused += 1
        proof = record.get("prior_proof")
        head = record.get("current_head")
        if (entry.get("mutable") or not isinstance(proof, dict) or not isinstance(head, dict)
                or record.get("remote_sha256_scope") != "prior_attempt_full_remote_readback"
                or type(record.get("bytes_transferred")) is not int or record["bytes_transferred"] != 0
                or proof.get("summary_sha256") not in prior_by_sha
                or (resume_mode == "existing_multipart" and proof.get("summary_sha256") != parent_summary_sha)
                or proof.get("plan_sha256") != plan_sha
                or proof.get("expected_sha256") != entry["sha256"]
                or proof.get("expected_size_bytes") != entry["size_bytes"]
                or proof.get("remote_sha256") != entry["sha256"]
                or proof.get("prior_status") not in {"uploaded_verified", "verified_existing"}
                or head.get("http_status") != 200 or head.get("size_bytes") != entry["size_bytes"]
                or head.get("content_type") != entry["content_type"]):
            raise HostedValidationError(f"prior full-byte proof or current HEAD is invalid: {entry['object_key']}")
        try:
            checked_at = datetime.fromisoformat(head["checked_at"].replace("Z", "+00:00"))
            if checked_at.tzinfo is None or checked_at.utcoffset() is None:
                raise ValueError("missing timezone")
        except (ValueError, AttributeError, KeyError) as exc:
            raise HostedValidationError("prior reuse current HEAD lacks dated observation") from exc
        name = proof.get("record_name")
        expected_name = f"{index:04d}-{hashlib.sha256(entry['object_key'].encode()).hexdigest()[:16]}.json"
        if name != expected_name:
            raise HostedValidationError("prior proof record name is invalid")
        old_path = prior_by_sha[proof["summary_sha256"]] / "objects" / name
        if not old_path.is_file() or hashlib.sha256(old_path.read_bytes()).hexdigest() != proof.get("record_sha256"):
            raise HostedValidationError("prior proof record bytes differ from hash")
        old = _json(old_path)
        if (old.get("schema_version") != 1 or old.get("plan_sha256") != plan_sha
                or old.get("bucket") != OWNER or old.get("object_key") != entry["object_key"]
                or old.get("expected_sha256") != entry["sha256"]
                or old.get("expected_size_bytes") != entry["size_bytes"]
                or old.get("mutable") is not False or old.get("status") != proof["prior_status"]
                or old.get("remote_sha256") != entry["sha256"]
                or (isinstance(old.get("multipart"), dict)
                    and old["multipart"].get("state") in {"open", "abort_failed"})):
            raise HostedValidationError("prior proof record is not an original full-byte exact-plan verification")
        used_prior.add(proof["summary_sha256"])
    if (resume_mode == "existing_multipart" and resumed_multipart != 1
            or resume_mode is None and resumed_multipart != 0):
        raise HostedValidationError("multipart resume target count differs from summary")
    if set(prior_by_sha) != used_prior or ("reused_prior_verified" in summary and summary["reused_prior_verified"] != reused):
        raise HostedValidationError("prior receipt inputs or reused count do not match receipt")
    return records


def _manifest_binding(sources: list[tuple[dict[str, Any], Path]], *, kind: str,
                      root: Path, expected_sha: str, label: str) -> dict[str, Any]:
    matches = [(entry, local) for entry, local in sources
               if entry.get("source", {}).get("kind") == kind
               and entry.get("source", {}).get("path") == "manifest.json"]
    if len(matches) != 1:
        raise HostedValidationError(f"exactly one planned {label} manifest is required")
    entry, local = matches[0]
    if local.parent != root or entry.get("sha256") != expected_sha:
        raise HostedValidationError(f"{label} manifest differs from the canonical pin or plan")
    if entry.get("size_bytes", MAX_METADATA_BYTES + 1) > MAX_METADATA_BYTES:
        raise HostedValidationError(f"{label} manifest exceeds the bounded metadata limit")
    data = local.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != entry["size_bytes"] or digest != entry["sha256"] or digest != expected_sha:
        raise HostedValidationError(f"{label} manifest local bytes do not match plan and canonical pin")
    return {"object_key": entry["object_key"], "sha256": digest, "size_bytes": len(data)}


def _cors_headers(headers: dict[str, str], *, preflight: bool) -> bool:
    normalized = {key.lower(): value.strip() for key, value in headers.items()}
    if normalized.get("access-control-allow-origin") not in {VIEWER_ORIGIN, "*"}:
        return False
    if preflight:
        methods = {x.strip().upper() for x in normalized.get("access-control-allow-methods", "").split(",")}
        allowed = {x.strip().lower() for x in normalized.get("access-control-allow-headers", "").split(",")}
        return ("GET" in methods or "*" in methods) and ("range" in allowed or "*" in allowed)
    exposed = {x.strip().lower() for x in normalized.get("access-control-expose-headers", "").split(",")}
    return "*" in exposed or {"content-range", "content-length", "accept-ranges"}.issubset(exposed)


def _range_check(url: str, local_path: Path, size: int, content_type: str, *, opener: Any) -> dict[str, Any]:
    samples = []
    with local_path.open("rb") as local:
        for start, end in _range_points(size):
            headers = {"Range": f"bytes={start}-{end}", "Origin": VIEWER_ORIGIN,
                       "Accept-Encoding": "identity"}
            status, response_headers, body, final_url = _request(url, headers=headers,
                                                                  max_body=RANGE_BYTES, opener=opener)
            normalized = {k.lower(): v.strip() for k, v in response_headers.items()}
            expected_len = end - start + 1
            actual_type = normalized.get("content-type", "").split(";", 1)[0].strip().lower()
            expected_type = content_type.split(";", 1)[0].strip().lower()
            if (status != 206 or final_url != url
                    or normalized.get("content-range") != f"bytes {start}-{end}/{size}"
                    or normalized.get("content-length") != str(expected_len)
                    or normalized.get("accept-ranges", "").lower() != "bytes"
                    or actual_type != expected_type
                    or len(body) != expected_len):
                raise HostedValidationError(f"invalid ranged GET response: {url} bytes={start}-{end}")
            local.seek(start)
            if body != local.read(expected_len):
                raise HostedValidationError(f"ranged bytes differ from local staged asset: {url}")
            samples.append({"start": start, "end": end, "status": status,
                            "content_range": normalized["content-range"],
                            "content_type": normalized["content-type"],
                            "sha256": hashlib.sha256(body).hexdigest()})
    return {"url": url, "samples": samples}


def _metadata_check(url: str, local_path: Path, max_bytes: int, expected_sha256: str,
                    expected_content_type: str, *, opener: Any) -> dict[str, Any]:
    if max_bytes > MAX_METADATA_BYTES:
        raise HostedValidationError(f"metadata asset exceeds bounded GET limit: {url}")
    status, headers, body, final_url = _request(url, headers={"Origin": VIEWER_ORIGIN}, opener=opener)
    if status != 200 or final_url != url or len(body) != max_bytes:
        raise HostedValidationError(f"metadata GET status/length mismatch: {url}")
    local_data = local_path.read_bytes()
    remote_sha = hashlib.sha256(body).hexdigest()
    local_sha = hashlib.sha256(local_data).hexdigest()
    if (len(local_data) != max_bytes or remote_sha != expected_sha256
            or local_sha != expected_sha256 or remote_sha != local_sha):
        raise HostedValidationError(f"metadata bytes differ from plan/local object: {url}")
    ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "")
    if (not ctype or ctype.split(";", 1)[0].strip().lower()
            != expected_content_type.split(";", 1)[0].strip().lower()):
        raise HostedValidationError(f"metadata Content-Type differs from plan: {url}")
    parsed = None
    ndjson_records = None
    ndjson_record_count = None
    media_type = ctype.split(";", 1)[0].strip().lower()
    if "json" in media_type and media_type != "application/x-ndjson":
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HostedValidationError(f"invalid JSON metadata response: {url}") from exc
    elif media_type == "application/x-ndjson":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HostedValidationError(f"invalid NDJSON metadata response: {url}") from exc
        ndjson_records = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                ndjson_records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise HostedValidationError(
                    f"invalid NDJSON metadata response at line {line_number}: {url}"
                ) from exc
        ndjson_record_count = len(ndjson_records)
    return {"url": url, "status": status, "size_bytes": len(body), "sha256": remote_sha,
            "content_type": ctype,
            "json": parsed, "ndjson_records": ndjson_records,
            "ndjson_record_count": ndjson_record_count}


def _active_catalog_roots(sources: list[tuple[dict[str, Any], Path]], *, dataset_id: str,
                          display_publication: dict[str, Any] | None) -> tuple[str, set[str], dict[str, str], bool]:
    """Choose current roots only from exact planned package and manifest paths."""
    by_source = {(entry["source"]["kind"], entry["source"]["path"]): entry for entry, _ in sources}
    if len(by_source) != len(sources):
        raise HostedValidationError("duplicate package source paths in exact upload plan")
    catalog = by_source.get(("package", "catalog.json"))
    collections = [entry for (kind, path), entry in by_source.items()
                   if kind == "package" and (path == "collection.json" or path.endswith("/collection.json"))]
    if catalog is None or not collections:
        raise HostedValidationError("current analytical catalog or collection is absent from exact plan")
    catalog_url = _object_url(catalog["object_key"])
    collection_urls = {_object_url(entry["object_key"]) for entry in collections}
    style_sources: dict[str, str] = {}
    embedded_styles = display_publication is None
    kind = "display_package" if display_publication else "package"
    manifest_entry = by_source.get((kind, "manifest.json"))
    if manifest_entry is None:
        raise HostedValidationError("current style manifest is absent from exact plan")
    manifest_path = next(local for entry, local in sources if entry is manifest_entry)
    manifest = _json(manifest_path)

    def declared(kind: str, path: str, sha: str, size: int) -> str:
        if (not isinstance(path, str) or path.startswith("/") or ".." in path.split("/")
                or not isinstance(sha, str) or not HEX_SHA256.fullmatch(sha)
                or type(size) is not int or size <= 0):
            raise HostedValidationError("current display manifest contains an unsafe asset path or identity")
        entry = by_source.get((kind, path))
        if entry is None or entry["sha256"] != sha or entry["size_bytes"] != size:
            raise HostedValidationError("current display manifest asset differs from exact upload plan")
        return _object_url(entry["object_key"])

    if display_publication:
        assets = manifest.get("assets") if isinstance(manifest, dict) else None
        if not isinstance(assets, list) or not assets:
            raise HostedValidationError("current display manifest lacks style-bearing assets")
        for asset in assets:
            if not isinstance(asset, dict) or not isinstance(asset.get("style_path"), str):
                raise HostedValidationError("current display manifest asset lacks style_path")
            style_path = asset["style_path"]
            if not style_path.startswith("styles/") or not style_path.endswith(".json"):
                raise HostedValidationError("current display style path is not under styles/")
            style_entry = by_source.get(("display_package", style_path))
            if style_entry is None or style_entry["content_type"].split(";")[0] != "application/json":
                raise HostedValidationError("current manifest style is absent from exact planned JSON")
            style_url = _object_url(style_entry["object_key"])
            pmtiles_url = declared("display_package", asset.get("path"), asset.get("sha256"), asset.get("size_bytes"))
            if not pmtiles_url.lower().endswith(".pmtiles") or style_url in style_sources:
                raise HostedValidationError("current display styles or PMTiles are ambiguous")
            style_sources[style_url] = pmtiles_url
    else:
        assets = manifest.get("assets") if isinstance(manifest, dict) else None
        if not isinstance(assets, dict):
            raise HostedValidationError("embedded display package lacks manifest asset inventory")
        style_paths = [path for path in assets if isinstance(path, str)
                       and "/styles/" in f"/{path}" and path.endswith(".json")]
        pmtiles_paths = [path for path in assets if isinstance(path, str) and path.endswith(".pmtiles")]
        if len(style_paths) != 1 or len(pmtiles_paths) != 1:
            raise HostedValidationError("embedded display manifest lacks one current style and PMTiles")
        style_path, pmtiles_path = style_paths[0], pmtiles_paths[0]
        style_meta, pmtiles_meta = assets[style_path], assets[pmtiles_path]
        if not isinstance(style_meta, dict) or not isinstance(pmtiles_meta, dict):
            raise HostedValidationError("embedded style or PMTiles manifest identity is invalid")
        style_url = declared("package", style_path, style_meta.get("sha256"), style_meta.get("size_bytes"))
        pmtiles_url = declared("package", pmtiles_path, pmtiles_meta.get("sha256"), pmtiles_meta.get("size_bytes"))
        style_sources[style_url] = pmtiles_url
    if not style_sources:
        raise HostedValidationError("current display manifest has no active style")
    return catalog_url, collection_urls, style_sources, embedded_styles


def _json_asset_links(results: list[dict[str, Any]], planned_urls: set[str], product_id: str,
                      *, catalog_url: str, collection_urls: set[str],
                      style_sources: dict[str, str], embedded_styles: bool) -> list[dict[str, str]]:
    """Check links reachable from the current catalog and manifest-selected styles."""
    by_url = {result["url"]: result for result in results}
    if len(by_url) != len(results):
        raise HostedValidationError("duplicate metadata response in product inventory")
    roots = {catalog_url, *collection_urls, *style_sources}
    if any(url not in by_url or not isinstance(by_url[url].get("json"), dict) for url in roots):
        raise HostedValidationError("active catalog, collection, or style metadata is missing")

    def traverse(start: list[str]) -> tuple[set[str], list[dict[str, str]]]:
        seen: set[str] = set()
        resolved: list[dict[str, str]] = []
        pending = list(start)
        while pending:
            url = pending.pop()
            if url in seen:
                continue
            seen.add(url)
            result = by_url.get(url)
            if result is None or not isinstance(result.get("json"), dict):
                continue
            value = result["json"]
            candidates: list[tuple[str, str, bool]] = []
            links = value.get("links")
            if isinstance(links, list):
                for index, link in enumerate(links):
                    if isinstance(link, dict) and isinstance(link.get("href"), str):
                        candidates.append((f"link:{link.get('rel') or index}", link["href"], False))
            assets = value.get("assets")
            if isinstance(assets, dict):
                for asset_id, asset in assets.items():
                    if isinstance(asset, dict) and isinstance(asset.get("href"), str):
                        source_reference = asset.get("roles") == ["source"]
                        candidates.append((f"asset:{asset_id}", asset["href"], source_reference))
            sources = value.get("sources")
            if isinstance(sources, dict):
                for source_id, source in sources.items():
                    if not isinstance(source, dict):
                        continue
                    raw_urls = []
                    if isinstance(source.get("url"), str):
                        raw_urls.append(source["url"])
                    if isinstance(source.get("tiles"), list):
                        raw_urls.extend(item for item in source["tiles"] if isinstance(item, str))
                    for raw_url in raw_urls:
                        if raw_url.startswith("pmtiles://"):
                            raw_url = raw_url[len("pmtiles://"):]
                        candidates.append((f"style-source:{source_id}", raw_url, False))
            for label, href, source_reference in candidates:
                parsed_href = parse.urlsplit(href)
                if (parsed_href.scheme in {"http", "https"} and not _url_is_product(href, product_id)
                        and label in {"link:via", "link:license", "link:cite-as",
                                      "link:related", "link:derived_from"}):
                    # External citations, provenance, and license references are not hosted assets.
                    continue
                if (source_reference and parsed_href.scheme == "https" and parsed_href.hostname
                        and not _url_is_product(href, product_id)
                        and not parsed_href.username and not parsed_href.password
                        and not parsed_href.query and not parsed_href.fragment):
                    # A sole source role denotes an external producer reference, not a hosted asset.
                    continue
                target = parse.urljoin(url, href)
                if not _url_is_product(target, product_id) or target not in planned_urls:
                    raise HostedValidationError(f"JSON {label} escapes product or is absent from the exact plan: {href}")
                resolved.append({"source_url": url, "link": label, "url": target})
                if target in by_url and isinstance(by_url[target].get("json"), dict):
                    pending.append(target)
                elif target.lower().endswith(".json") and target not in by_url:
                    raise HostedValidationError(f"active JSON link was not fetched and checksum-checked: {target}")
        return seen, resolved

    catalog_seen, catalog_links = traverse([catalog_url])
    if not collection_urls.issubset(catalog_seen):
        raise HostedValidationError("current analytical collection is not linked from current catalog")
    if embedded_styles and not set(style_sources).issubset(catalog_seen):
        raise HostedValidationError("current embedded style is not linked from current collection")
    style_seen, style_links = traverse(list(style_sources))
    links = catalog_links + [item for item in style_links if item not in catalog_links]
    for style_url, expected_pmtiles in style_sources.items():
        if style_url not in style_seen or not any(item["source_url"] == style_url
                and item["link"].startswith("style-source:") and item["url"] == expected_pmtiles
                for item in links):
            raise HostedValidationError("current style does not refer to its manifest-pinned PMTiles")
    return links


def _load_query_controls(path: Path, dataset_id: str, *, release: str, plan_sha: str,
                        expected_sha256: str, expected_parquet_paths: set[str]) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    controls_sha = hashlib.sha256(raw).hexdigest()
    if not isinstance(expected_sha256, str) or not HEX_SHA256.fullmatch(expected_sha256) or controls_sha != expected_sha256:
        raise HostedValidationError("frozen query controls SHA-256 differs from the approved value")
    try:
        controls = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HostedValidationError("fixed DuckDB query controls are invalid JSON") from exc
    if not isinstance(controls, dict) or controls.get("schema_version") != 1:
        raise HostedValidationError("fixed DuckDB query controls have an unsupported schema")
    if controls.get("plan_sha256") != plan_sha:
        raise HostedValidationError("fixed DuckDB query controls are bound to another upload plan")
    if isinstance(controls.get("datasets"), dict):
        selected = controls["datasets"].get(dataset_id)
    elif controls.get("dataset_id") == dataset_id:
        selected = controls
    else:
        selected = None
    if not isinstance(selected, dict) or not isinstance(selected.get("queries"), list) or not selected["queries"]:
        raise HostedValidationError("fixed DuckDB query controls are missing or mismatched")
    if selected.get("release") != release:
        raise HostedValidationError("fixed DuckDB query controls are bound to another package release")
    seen = set()
    for item in selected["queries"]:
        if not isinstance(item, dict):
            raise HostedValidationError("invalid DuckDB query control")
        name, path_value, column, ids = (item.get(k) for k in ("name", "path", "id_column", "ids"))
        selection = item.get("selection")
        if (not isinstance(name, str) or name in seen or not isinstance(path_value, str)
                or not isinstance(column, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column)
                or not isinstance(ids, list) or not 1 <= len(ids) <= 3
                or any(not isinstance(v, (str, int)) or isinstance(v, bool) for v in ids)
                or not isinstance(selection, dict) or type(selection.get("row_count")) is not int
                or selection["row_count"] < 1):
            raise HostedValidationError("each frozen query must name a Parquet, an ID column, and 1-3 fixed IDs")
        seen.add(name)
    query_paths = [item["path"] for item in selected["queries"]]
    if len(set(query_paths)) != len(query_paths) or set(query_paths) != expected_parquet_paths:
        raise HostedValidationError("frozen query controls do not exactly cover every analytic Parquet asset")
    return selected["queries"], controls_sha


def _load_spatial_hints(path: Path, expected_sha256: str, *, dataset_id: str,
                        controls_sha: str, plan_sha: str, queries: list[dict[str, Any]],
                        parquet_entries: list[tuple[dict[str, Any], Path, str]]) -> tuple[dict[str, dict[str, Any]], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(expected_sha256, str) or not HEX_SHA256.fullmatch(expected_sha256) or digest != expected_sha256:
        raise HostedValidationError("spatial hint SHA-256 differs from approved value")
    hints = _json(path)
    if (hints.get("schema_version") != 1 or hints.get("kind") != "local_spatial_query_supplement"
            or hints.get("original_query_controls_sha256") != controls_sha
            or hints.get("immutable_upload_plan_sha256") != plan_sha):
        raise HostedValidationError("spatial hints are not bound to frozen controls and plan")
    selected = (hints.get("datasets") or {}).get(dataset_id)
    rows = selected.get("queries") if isinstance(selected, dict) else None
    if not isinstance(rows, list) or len(rows) != len(queries):
        raise HostedValidationError("spatial hints do not cover exact frozen queries")
    planned = {entry["source"]["path"]: (entry, local) for entry, local, _ in parquet_entries}
    by_name = {}
    for query, hint in zip(queries, rows):
        if (not isinstance(hint, dict) or any(hint.get(k) != query.get(k) for k in ("name", "path", "id_column", "ids"))
                or hint.get("covering_bbox_status") != "validated"
                or hint.get("covering_bbox_column") != "bbox"
                or hint.get("covering_bbox_fields") != {key: f"bbox.{key}" for key in ("xmin", "ymin", "xmax", "ymax")}
                or hint.get("path") not in planned):
            raise HostedValidationError("spatial hint differs from frozen query or lacks validated bbox")
        entry, local = planned[hint["path"]]
        if (hint.get("parquet_object_sha256") != entry["sha256"]
                or hint.get("parquet_object_size_bytes") != entry["size_bytes"]
                or local.stat().st_size != entry["size_bytes"]):
            raise HostedValidationError("spatial hint Parquet identity differs from exact plan")
        selected_ids = hint.get("selected_ids")
        if (not isinstance(selected_ids, list) or [item.get("id") for item in selected_ids if isinstance(item, dict)] != query["ids"]
                or len(selected_ids) != len(query["ids"])):
            raise HostedValidationError("spatial hint omits or changes a frozen ID")
        for item in selected_ids:
            bbox, center = item.get("covering_bbox"), item.get("center")
            if (not isinstance(bbox, dict) or not isinstance(center, dict)
                    or set(bbox) != {"minx", "miny", "maxx", "maxy"} or set(center) != {"x", "y"}
                    or any(not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value)
                           for value in [*bbox.values(), *center.values()])
                    or bbox["minx"] > bbox["maxx"] or bbox["miny"] > bbox["maxy"]
                    or center["x"] != (bbox["minx"] + bbox["maxx"]) / 2
                    or center["y"] != (bbox["miny"] + bbox["maxy"]) / 2
                    or item.get("local_id_match_count") != 1
                    or item.get("covering_encloses_source_wkb") is not True):
                raise HostedValidationError("spatial hint has invalid covering bbox or center")
        by_name[query["name"]] = hint
    return by_name, digest


def _normalize_row(row: tuple[Any, ...]) -> str:
    def norm(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"bytes_hex": value.hex()}
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, tuple):
            return [norm(x) for x in value]
        if isinstance(value, list):
            return [norm(x) for x in value]
        if isinstance(value, dict):
            return {str(k): norm(v) for k, v in sorted(value.items(), key=lambda pair: str(pair[0]))}
        return value
    return json.dumps([norm(x) for x in row], sort_keys=True, separators=(",", ":"), default=str)


def _browser_record(path: Path, *, dataset_id: str, product: dict[str, Any], plan_sha: str,
                    planned_urls: set[str], controls_path: Path,
                    controls_sha256: str, planned_assets: dict[str, dict[str, Any]],
                    metadata_policy_path: Path | None = None,
                    metadata_policy_sha256: str | None = None) -> dict[str, Any]:
    evidence = _json(path)
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
        raise HostedValidationError("browser evidence has an unsupported schema")
    controls_raw = controls_path.read_bytes()
    actual_controls_sha = hashlib.sha256(controls_raw).hexdigest()
    try:
        controls = json.loads(controls_raw)
    except json.JSONDecodeError as exc:
        raise HostedValidationError("frozen browser controls are invalid JSON") from exc
    if (actual_controls_sha != controls_sha256 or controls.get("schema_version") != 1
            or controls.get("plan_sha256") != plan_sha
            or controls.get("viewer_config_sha256") != evidence.get("viewer_config_sha256")):
        raise HostedValidationError("frozen browser controls are unapproved or bound to another plan")
    control_objects = controls.get("objects")
    expected_product_objects = {url: value for url, value in (control_objects or {}).items()
                                if _url_is_product(url, dataset_id)}
    if expected_product_objects != planned_assets:
        raise HostedValidationError("browser object controls differ from exact plan inventory/checksums")
    if evidence.get("status") not in {"passed", "partial"} or evidence.get("plan_sha256") != plan_sha:
        raise HostedValidationError("aggregate browser evidence is failed or bound to another plan")
    if evidence.get("browser_cases_sha256") != controls_sha256:
        raise HostedValidationError("aggregate browser evidence is bound to another frozen cases file")
    datasets = evidence.get("datasets")
    if not isinstance(datasets, list):
        # Permit a single-dataset record for offline fixtures and older reviews.
        datasets = [evidence]
    matches = [row for row in datasets if isinstance(row, dict) and row.get("dataset_id") == dataset_id]
    if len(matches) != 1:
        raise HostedValidationError("browser evidence must contain exactly one matching dataset")
    row = matches[0]
    display = product.get("display_publication") or {}
    expected_cases = [case["id"] for case in controls.get("cases", [])
                      if isinstance(case, dict) and case.get("dataset_id") == dataset_id]
    expected_prefixes = [f"{dataset_id}/releases/{product['release']}/"]
    if display.get("release"):
        expected_prefixes.append(f"{dataset_id}/display/{display['release']}/")
    display_assets = display.get("assets")
    if isinstance(display_assets, list) and display_assets:
        display_by_layer = {item.get("id"): f"{DATA_ORIGIN}/{OWNER}/{dataset_id}/{item.get('href')}"
                            for item in display_assets if isinstance(item, dict)}
    else:
        # River Plastic's display tile is embedded in its immutable release.
        release_prefix = f"{DATA_ORIGIN}/{OWNER}/{dataset_id}/releases/{product['release']}/"
        embedded = {url for url in planned_urls if url.startswith(release_prefix) and url.lower().endswith(".pmtiles")}
        display_by_layer = {case.get("layer_id"): next(iter(embedded))
                            for case in controls.get("cases", [])
                            if isinstance(case, dict) and case.get("dataset_id") == dataset_id} if len(embedded) == 1 else {}
    if not display_by_layer or any(url not in planned_assets or not url.lower().endswith(".pmtiles")
                                   for url in display_by_layer.values()):
        raise HostedValidationError("frozen display layers do not bind exact planned PMTiles assets")
    case_records = [case for case in evidence.get("cases", [])
                    if isinstance(case, dict) and case.get("dataset_id") == dataset_id]
    if [case.get("id") for case in case_records] != expected_cases:
        raise HostedValidationError("browser case records do not cover frozen product cases")
    frozen_by_id = {case["id"]: case for case in controls["cases"]}
    required_urls: set[str] = set()
    observed_urls: set[str] = set()
    for case in case_records:
        frozen_case = frozen_by_id[case["id"]]
        if (case.get("layer_id") != frozen_case.get("layer_id")
                or case.get("region") != frozen_case.get("region")
                or case.get("view") != frozen_case.get("view")):
            raise HostedValidationError("browser case view differs from frozen controls")
        display_url = display_by_layer.get(case.get("layer_id"))
        if (not display_url or case.get("status") != "passed"
                or case.get("display_object_url") != display_url
                or case.get("display_sha256") != planned_assets[display_url]["sha256"]):
            raise HostedValidationError("browser case does not bind its planned display asset")
        required_urls.add(display_url)
        analytic_url = case.get("analytic_object_url")
        requires_analytic = ((frozen_case.get("region") not in (None, "global") and dataset_id != "river-plastic-inputs")
                             or (dataset_id == "grwl-raw" and (frozen_case.get("view") or {}).get("name") == "mississippi"
                                 and (frozen_case.get("view") or {}).get("zoom") == 7))
        if requires_analytic:
            if (not isinstance(analytic_url, str) or analytic_url not in planned_assets
                    or not analytic_url.lower().endswith(".parquet")
                    or case.get("analytic_sha256") != planned_assets[analytic_url]["sha256"]):
                raise HostedValidationError("browser case lacks its planned analytic lookup")
            required_urls.add(analytic_url)
        requests = case.get("requests")
        if not isinstance(requests, list):
            raise HostedValidationError("browser case lacks object request evidence")
        if any(not isinstance(item, dict) or item.get("status_check") != "passed" for item in requests):
            raise HostedValidationError("browser case includes a failed hosted request")
        case_urls = {item.get("url") for item in requests}
        if display_url not in case_urls or (requires_analytic and analytic_url not in case_urls):
            raise HostedValidationError("browser case did not request its required hosted assets")
        if any(url not in planned_urls for url in case_urls):
            raise HostedValidationError("browser case requested an off-plan object")
        observed_urls.update(case_urls)
    if set(display_by_layer.values()) - required_urls:
        raise HostedValidationError("browser cases omit a planned display layer")
    expected_url_prefixes = [f"{DATA_ORIGIN}/{OWNER}/{prefix}" for prefix in expected_prefixes]
    selected_dataset = evidence.get("selected_dataset_id")
    partial_ok = (evidence.get("status") == "partial" and selected_dataset == dataset_id
                  and isinstance(evidence.get("expected_case_count"), int)
                  and evidence["expected_case_count"] == len(expected_cases))
    full_ok = evidence.get("status") == "passed"
    if (row.get("product_id") != dataset_id or row.get("release") != product.get("release")
            or row.get("display_release") != display.get("release")
            or row.get("status") != "passed" or row.get("plan_sha256") != plan_sha
            or row.get("browser_cases_sha256") != controls_sha256
            or row.get("viewer_config_sha256") != controls.get("viewer_config_sha256")
            or row.get("viewer_build_sha256") != evidence.get("viewer_build_sha256")
            or not isinstance(row.get("checked_at"), str) or not row.get("screenshots")
            or row.get("case_ids") != expected_cases
            or set(row.get("tested_object_urls") or []) != observed_urls
            or not required_urls.issubset(observed_urls)
            or not (partial_ok or full_ok)):
        raise HostedValidationError("browser evidence is incomplete or bound to another hosted plan")
    try:
        checked_at = datetime.fromisoformat(row["checked_at"].replace("Z", "+00:00"))
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise HostedValidationError("browser evidence has invalid checked_at") from exc
    prefix_values = row.get("planned_object_prefixes")
    if not isinstance(prefix_values, list) or sorted(prefix_values) != sorted(expected_prefixes):
        raise HostedValidationError("browser evidence has unsafe planned object prefixes")
    if sorted(row.get("planned_object_url_prefixes") or []) != sorted(expected_url_prefixes):
        raise HostedValidationError("browser evidence has incorrect planned URL prefixes")
    for url in row["tested_object_urls"]:
        if not isinstance(url, str) or not _url_is_product(url, dataset_id) or url not in planned_urls:
            raise HostedValidationError("browser evidence contains a tested URL outside the intended product")
    for screenshot in row["screenshots"]:
        if not isinstance(screenshot, str) or not screenshot:
            raise HostedValidationError("browser screenshot path is missing or unreadable")
        screenshot_path = Path(screenshot)
        if not screenshot_path.is_absolute():
            screenshot_path = path.parent / screenshot_path
        if not screenshot_path.is_file():
            raise HostedValidationError("browser screenshot path is missing or unreadable")
    for key in ("viewer_config_sha256", "viewer_build_sha256"):
        if not isinstance(row.get(key), str) or not HEX_SHA256.fullmatch(row[key]):
            raise HostedValidationError(f"browser evidence lacks valid {key}")
    try:
        transport = browser_range_evidence.validate_transport(
            evidence, case_records, dataset_id=dataset_id, plan_sha=plan_sha,
            controls_sha=controls_sha256, planned_assets=planned_assets,
            evidence_path=path, policy_path=metadata_policy_path,
            policy_sha256=metadata_policy_sha256)
    except browser_range_evidence.BrowserRangeError as exc:
        raise HostedValidationError(str(exc)) from exc
    return {**row, "transport_validation": transport}


def _duckdb_compare(queries: list[dict[str, Any]], local_files: dict[str, Path],
                    remote_urls: dict[str, str], *, connect: Callable[..., Any] | None = None,
                    spatial_hints: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if connect is None:
        try:
            import duckdb
        except ImportError as exc:
            raise HostedValidationError("DuckDB Python package is required for subset validation") from exc
        connect = duckdb.connect
    con = connect(database=":memory:", read_only=False)
    try:
        try:
            con.execute("LOAD httpfs")
        except Exception as exc:
            raise HostedValidationError("DuckDB httpfs extension is unavailable; install it before validation") from exc
        results = []
        for query in queries:
            path = query["path"]
            local = local_files.get(path)
            remote = remote_urls.get(path)
            if local is None or remote is None:
                raise HostedValidationError(f"fixed query path is not a staged Parquet asset: {path}")
            column = '"' + query["id_column"].replace('"', '""') + '"'
            ids = query["ids"]
            if not ids or len({str(value) for value in ids}) != len(ids):
                raise HostedValidationError(f"fixed DuckDB IDs must be distinct: {query['name']}")
            local_count = con.execute("SELECT num_rows FROM parquet_file_metadata(?)",
                                      [str(local)]).fetchone()[0]
            remote_count = con.execute("SELECT num_rows FROM parquet_file_metadata(?)",
                                       [remote]).fetchone()[0]
            expected_count = (query.get("selection") or {}).get("row_count")
            if ((expected_count is not None and local_count != expected_count)
                    or local_count != remote_count):
                raise HostedValidationError(f"Parquet footer row count differs for query {query['name']}")
            # Each equality predicate can prune to its own row group. A combined IN
            # predicate on discontiguous IDs can request thousands of remote chunks.
            id_sql = (f"SELECT CAST({column} AS VARCHAR), count(*) FROM read_parquet(?) "
                      f"WHERE {column} = ? GROUP BY {column}")
            local_id_counts: dict[str, int] = {}
            remote_id_counts: dict[str, int] = {}
            for value in ids:
                for source, counts in ((str(local), local_id_counts), (remote, remote_id_counts)):
                    # DuckDB binds Python integers as HUGEINT; GRWL's uint64 ID
                    # column would be cast, preventing row-group min/max pruning.
                    rows = con.execute(id_sql, [source, str(value)]).fetchall()
                    for key, count in rows:
                        key = str(key)
                        if key in counts or key != str(value):
                            raise HostedValidationError(f"fixed DuckDB ID result differs: {query['name']}")
                        counts[key] = count
            required_ids = {str(value) for value in ids}
            if (local_id_counts != remote_id_counts or not required_ids.issubset(local_id_counts)):
                raise HostedValidationError(f"fixed DuckDB IDs are missing or multiplicities differ: {query['name']}")
            hint = spatial_hints.get(query["name"]) if spatial_hints is not None else None
            hints_by_id = {}
            if hint is not None:
                bbox_sql = (f"SELECT CAST({column} AS VARCHAR), bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax "
                            f"FROM read_parquet(?) WHERE {column} = ?")
                actual = []
                for value in ids:
                    actual.extend(con.execute(bbox_sql, [str(local), str(value)]).fetchall())
                actual_by_id = {str(row[0]): row[1:] for row in actual}
                if len(actual) != len(ids) or len(actual_by_id) != len(actual):
                    raise HostedValidationError(f"local spatial hint ID multiplicity differs: {query['name']}")
                for item in hint["selected_ids"]:
                    if str(item["id"]) in hints_by_id:
                        raise HostedValidationError(f"local spatial hint ID multiplicity differs: {query['name']}")
                    hints_by_id[str(item["id"])] = item
                    bbox = item["covering_bbox"]
                    expected = (bbox["minx"], bbox["miny"], bbox["maxx"], bbox["maxy"])
                    if actual_by_id.get(str(item["id"])) != expected:
                        raise HostedValidationError(f"local spatial hint bbox changed: {query['name']}: {item['id']}")
                if set(hints_by_id) != required_ids:
                    raise HostedValidationError(f"local spatial hint IDs differ: {query['name']}")
            local_rows = []
            remote_rows = []
            for value in ids:
                sql = f"SELECT * FROM read_parquet(?) WHERE {column} = ?"
                parameters: list[Any] = [str(value)]
                if hint is not None:
                    center = hints_by_id[str(value)]["center"]
                    sql += " AND bbox.xmin <= ? AND bbox.xmax >= ? AND bbox.ymin <= ? AND bbox.ymax >= ?"
                    parameters.extend((center["x"], center["x"], center["y"], center["y"]))
                sql += " LIMIT 1001"
                local_rows.extend(con.execute(sql, [str(local), *parameters]).fetchall())
                remote_rows.extend(con.execute(sql, [remote, *parameters]).fetchall())
                if len(local_rows) > 1000 or len(remote_rows) > 1000:
                    raise HostedValidationError(f"fixed DuckDB subset exceeds the 1000-row comparison cap: {query['name']}")
            if hint is not None and (len(local_rows) != sum(local_id_counts.values())
                                      or len(remote_rows) != sum(remote_id_counts.values())):
                raise HostedValidationError(f"spatial predicate omitted a frozen-ID row: {query['name']}")
            if len(local_rows) > 1000 or len(remote_rows) > 1000:
                raise HostedValidationError(f"fixed DuckDB subset exceeds the 1000-row comparison cap: {query['name']}")
            local_multiset = Counter(_normalize_row(row) for row in local_rows)
            remote_multiset = Counter(_normalize_row(row) for row in remote_rows)
            if local_multiset != remote_multiset:
                raise HostedValidationError(f"fixed DuckDB subset differs for query {query['name']}")
            result = {"name": query["name"], "path": path, "ids": query["ids"],
                            "footer_rows": local_count,
                            "id_multiplicity": local_id_counts,
                            "rows": len(local_rows), "result_sha256": hashlib.sha256(
                                "\n".join(sorted(local_multiset.elements())).encode()).hexdigest()}
            if hint is not None:
                bounds = hint.get("candidate_row_group_compressed_byte_bounds") or {}
                result["spatial_hint"] = {"predicate": "frozen ID AND center within unchanged local bbox",
                    "local_bbox_verified": True,
                    "id_only_candidate_compressed_bytes": (bounds.get("query_union_id_only") or {}).get("all_column_chunks_compressed_bytes_upper_bound"),
                    "id_spatial_candidate_compressed_bytes": (bounds.get("query_union_id_plus_spatial") or {}).get("all_column_chunks_compressed_bytes_upper_bound"),
                    "estimate_scope": "local row-group column-chunk estimate, not remote HTTP byte guarantee"}
            results.append(result)
        return results
    finally:
        con.close()


def validate(*, plan_path: Path, dataset_id: str, receipt_path: Path, package_root: Path,
             display_root: Path | None, controls_path: Path, output_path: Path,
             package_manifest_sha256: str, controls_sha256: str,
             browser_evidence_path: Path | None = None, browser_controls_path: Path | None = None,
             browser_controls_sha256: str | None = None,
             browser_metadata_policy_path: Path | None = None,
             browser_metadata_policy_sha256: str | None = None,
             query_spatial_hints_path: Path | None = None, query_spatial_hints_sha256: str | None = None,
             prior_receipt_paths: list[Path] | None = None,
             expected_multipart_parent_summary_sha256: str | None = None,
             expected_multipart_parent_record_sha256: str | None = None,
             opener: Any = request.urlopen, duckdb_connect: Callable[..., Any] | None = None) -> dict[str, Any]:
    if (query_spatial_hints_path is None) != (query_spatial_hints_sha256 is None):
        raise HostedValidationError("spatial hints require both path and approved SHA-256")
    if (browser_metadata_policy_path is None) != (browser_metadata_policy_sha256 is None):
        raise HostedValidationError("browser metadata policy requires both path and approved SHA-256")
    if browser_metadata_policy_path is not None and browser_evidence_path is None:
        raise HostedValidationError("browser metadata policy requires browser evidence")
    receipt_summary = _json(receipt_path / "summary.json")
    plan_sha, entries = upload.load_plan(plan_path, dataset_id,
                                         include_readme=receipt_summary.get("include_readme") is True)
    plan = _json(plan_path)
    product = next(row for row in plan["products"] if row["dataset_id"] == dataset_id)
    if not isinstance(package_manifest_sha256, str) or not HEX_SHA256.fullmatch(package_manifest_sha256):
        raise HostedValidationError("canonical package manifest SHA-256 is required")
    receipt = _receipt_records(
        receipt_path, plan_sha, entries, prior_receipt_paths,
        expected_multipart_parent_summary_sha256=expected_multipart_parent_summary_sha256,
        expected_multipart_parent_record_sha256=expected_multipart_parent_record_sha256)
    package_root = _safe_root(package_root, "package root")
    if display_root is not None:
        display_root = _safe_root(display_root, "display root")
    product_prefix = f"{OWNER}/{dataset_id}/"
    package_base = f"{DATA_ORIGIN}/{product_prefix}releases/{product['release']}/"
    display_pub = product.get("display_publication")
    display_base = (f"{DATA_ORIGIN}/{product_prefix}display/{display_pub['release']}/"
                    if isinstance(display_pub, dict) else None)
    sources = upload.resolve_sources(entries, {dataset_id: package_root},
                                     {dataset_id: display_root} if display_root else {},
                                     Path(__file__).resolve().parents[2])
    package_manifest = _manifest_binding(sources, kind="package", root=package_root,
                                         expected_sha=package_manifest_sha256,
                                         label="analytic package")
    display_manifest = None
    if isinstance(display_pub, dict):
        if display_root is None:
            raise HostedValidationError("display package root is required by the exact upload plan")
        display_manifest = _manifest_binding(sources, kind="display_package", root=display_root,
                                             expected_sha=display_pub.get("manifest_sha256"),
                                             label="display package")
    elif display_root is not None:
        raise HostedValidationError("unexpected display package root for a product without display assets")
    checks: dict[str, str] = {name: "failed" for name in REQUIRED_CHECKS}
    checks["browser_render"] = "not_run"
    evidence: dict[str, Any] = {"plan_sha256": plan_sha, "receipt_object_count": len(receipt)}
    evidence["package_manifest"] = package_manifest
    if display_manifest:
        evidence["display_manifest"] = display_manifest
    evidence["asset_checksum_scope"] = (
        "Full remote bytes were SHA-256 verified in original upload attempt receipts. "
        "For reused objects, this run binds their original byte proofs and separately checks current HEAD "
        "and anonymous range samples; current HEAD is not a fresh full-byte hash."
    )
    evidence["prior_full_byte_proofs"] = [{"object_key": key,
        "prior_status": row["prior_proof"]["prior_status"],
        "prior_summary_sha256": row["prior_proof"]["summary_sha256"],
        "prior_record_sha256": row["prior_proof"]["record_sha256"],
        "current_head": row["current_head"]} for key, row in receipt.items()
        if row["status"] == "verified_prior_attempt"]
    for key, row in receipt.items():
        parent = row.get("multipart_resume")
        if parent is not None:
            evidence["multipart_resume_parent"] = {
                "object_key": key, "summary_sha256": parent["summary_sha256"],
                "record_name": parent["record_name"],
                "record_sha256": parent["record_sha256"],
                "remote_sha256_scope": row["remote_sha256_scope"]}
    evidence["catalog_link_scope"] = (
        "Immutable product package catalog/collection/styles/docs only; the aggregate Portolan catalog is "
        "not deployed or checked by this per-product run. External assets with sole role 'source' "
        "are provenance references; their bytes and transport are not checked."
    )
    failures: list[str] = []

    try:
        asset_urls: dict[str, str] = {}
        large_files = []
        metadata_files = []
        for entry, local in sources:
            key = entry["object_key"]
            url = _object_url(key)
            if not _url_is_product(url, dataset_id):
                raise HostedValidationError(f"object URL escaped intended product: {key}")
            asset_urls[key] = url
            suffix = Path(key).suffix.lower()
            if suffix in LARGE_SUFFIXES:
                large_files.append((entry, local, url))
            elif entry["size_bytes"] <= MAX_METADATA_BYTES:
                metadata_files.append((entry, local, url))
        package_paths = {entry["source"]["path"] for entry, _ in sources
                         if entry["source"]["kind"] == "package"}
        display_paths = {entry["source"]["path"] for entry, _ in sources
                         if entry["source"]["kind"] == "display_package"}
        catalog_url, collection_urls, style_sources, embedded_styles = _active_catalog_roots(
            sources, dataset_id=dataset_id, display_publication=display_pub)
        catalog_inventory = {
            "catalog": ["catalog.json"],
            "collections": sorted(entry["source"]["path"] for entry, _ in sources
                                  if _object_url(entry["object_key"]) in collection_urls),
            "styles": sorted(entry["source"]["path"] for entry, _ in sources
                             if _object_url(entry["object_key"]) in style_sources),
            "documentation": sorted(path for path in package_paths | display_paths
                                    if Path(path).name.lower() in {"readme.md", "agents.md"}),
        }
        if not all(catalog_inventory[key] for key in catalog_inventory):
            raise HostedValidationError("planned product package lacks required catalog, collection, style, or documentation metadata")
        evidence["catalog_inventory"] = catalog_inventory
        # Receipt fields are full-object remote hashes from the uploader's ranged
        # checksum verification; remote metadata is never used as checksum proof.
        checks["asset_checksums"] = "passed"
        evidence["receipt_checksums"] = [{"object_key": entry["object_key"],
                                           "sha256": receipt[entry["object_key"]]["remote_sha256"],
                                           "size_bytes": entry["size_bytes"]}
                                          for entry, _ in sources]

        range_results = []
        cors_results = []
        for entry, local, url in large_files:
            range_results.append(_range_check(url, local, entry["size_bytes"], entry["content_type"], opener=opener))
            evidence["range_samples"] = range_results
        checks["range_requests"] = "passed"
        for entry, local, url in large_files:
            # Preflight is issued for each hosted large asset; GET range responses
            # above must also expose range metadata to the actual viewer origin.
            status, headers, _, final_url = _request(
                url, method="OPTIONS", headers={"Origin": VIEWER_ORIGIN,
                "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "range"},
                max_body=1024, opener=opener)
            preflight_passed = status in {200, 204} and final_url == url and _cors_headers(headers, preflight=True)
            cors_results.append({"url": url, "preflight_status": status,
                                 "preflight_passed": preflight_passed,
                                 "preflight_headers": headers,
                                 "preflight_note": "credentialless request; Fetch wildcard CORS fields apply"})
            evidence["cors"] = cors_results
            if not preflight_passed:
                raise HostedValidationError(f"CORS preflight failed: {url}")
            # Check actual GET CORS exposure using a first-byte request.
            get_status, get_headers, _, get_final_url = _request(
                url, headers={"Range": "bytes=0-0", "Origin": VIEWER_ORIGIN},
                max_body=1, opener=opener)
            cors_results[-1]["get_status"] = get_status
            cors_results[-1]["get_headers"] = get_headers
            evidence["cors"] = cors_results
            if (get_status != 206 or get_final_url != url or not _cors_headers(get_headers, preflight=False)):
                raise HostedValidationError(f"CORS ranged GET headers are not accessible: {url}")
            cors_results[-1]["get_passed"] = True
        checks["cors"] = "passed"
        evidence["range_samples"] = range_results
        evidence["cors"] = cors_results

        metadata_results = []
        for entry, local, url in metadata_files:
            if not _url_is_product(url, dataset_id):
                raise HostedValidationError(f"metadata URL escaped intended product: {url}")
            metadata_results.append(_metadata_check(url, local, entry["size_bytes"],
                                                   entry["sha256"], entry["content_type"], opener=opener))
        linked_assets = _json_asset_links(metadata_results, set(asset_urls.values()), dataset_id,
                                         catalog_url=catalog_url, collection_urls=collection_urls,
                                         style_sources=style_sources, embedded_styles=embedded_styles)
        checks["anonymous_access"] = "passed" if metadata_results and range_results else "failed"
        checks["catalog_links"] = "passed" if metadata_results and range_results and linked_assets else "failed"
        evidence["metadata_gets"] = metadata_results
        evidence["json_asset_links"] = linked_assets
        for item in metadata_results:
            item.pop("json", None)
            item.pop("ndjson_records", None)

        parquet_entries = [(entry, local, url) for entry, local, url in large_files
                           if Path(entry["object_key"]).suffix.lower() == ".parquet"]
        parquet_paths = {entry["source"]["path"] for entry, _, _ in parquet_entries}
        controls, controls_digest = _load_query_controls(
            controls_path, dataset_id, release=product["release"], plan_sha=plan_sha,
            expected_sha256=controls_sha256, expected_parquet_paths=parquet_paths)
        evidence["query_controls_sha256"] = controls_digest
        evidence["query_controls"] = controls
        query_local = {entry["source"]["path"]: local for entry, local, _ in parquet_entries}
        query_remote = {entry["source"]["path"]: url for entry, _, url in parquet_entries}
        if query_spatial_hints_path is not None:
            hints, hints_digest = _load_spatial_hints(
                query_spatial_hints_path, query_spatial_hints_sha256,
                dataset_id=dataset_id, controls_sha=controls_digest, plan_sha=plan_sha,
                queries=controls, parquet_entries=parquet_entries)
            evidence["query_spatial_hints_sha256"] = hints_digest
            proxy_assets = {entry["source"]["path"]: {"url": url, "size_bytes": entry["size_bytes"],
                            "content_type": entry["content_type"]} for entry, _, url in parquet_entries}
            proxy = bounded_http.BoundedSourceProxy(proxy_assets, product_id=dataset_id)
            try:
                with proxy:
                    query_proxy = {path: proxy.url_for(path) for path in query_remote}
                    evidence["subset_queries"] = _duckdb_compare(controls, query_local, query_proxy,
                        connect=duckdb_connect, spatial_hints=hints)
            finally:
                evidence["duckdb_bounded_http"] = proxy.snapshot()
                evidence["duckdb_remote_transfer_bytes_instrumented"] = True
            if evidence["duckdb_bounded_http"]["errors"]:
                raise HostedValidationError("bounded DuckDB transport rejected requests: " +
                                            "; ".join(evidence["duckdb_bounded_http"]["errors"][:4]))
        else:
            evidence["subset_queries"] = _duckdb_compare(controls, query_local, query_remote,
                                                           connect=duckdb_connect)
            evidence["duckdb_remote_transfer_bytes_instrumented"] = False
        checks["subset_query"] = "passed"
        if browser_evidence_path:
            if browser_controls_path is None or browser_controls_sha256 is None:
                raise HostedValidationError("browser evidence requires independently frozen browser controls")
            browser = _browser_record(browser_evidence_path, dataset_id=dataset_id,
                                      product=product, plan_sha=plan_sha,
                                      planned_urls=set(asset_urls.values()),
                                      controls_path=browser_controls_path,
                                      controls_sha256=browser_controls_sha256,
                                      metadata_policy_path=browser_metadata_policy_path,
                                      metadata_policy_sha256=browser_metadata_policy_sha256,
                                      planned_assets={asset_urls[entry["object_key"]]: {
                                          "sha256": entry["sha256"], "size_bytes": entry["size_bytes"],
                                          "content_type": entry["content_type"]}
                                          for entry, _ in sources if not entry.get("mutable")})
            evidence["browser_evidence"] = browser
            checks["browser_render"] = "passed"
        else:
            checks["browser_render"] = "not_run"
    except Exception as exc:
        failures.append(str(exc)[:1500] if isinstance(exc, HostedValidationError)
                        else f"{type(exc).__name__}: {str(exc)[:1400]}")

    if failures:
        # Checks are reported only as passed once the full applicable phase ended.
        for name in REQUIRED_CHECKS:
            if checks[name] == "failed":
                checks[name] = "failed"
    passed = not failures and all(checks[name] == "passed" for name in REQUIRED_CHECKS)
    display_manifest_sha = display_pub.get("manifest_sha256") if isinstance(display_pub, dict) else None
    report = {"schema_version": 1, "dataset_id": dataset_id, "release": product["release"],
              "package_manifest_sha256": package_manifest_sha256, "package_base_url": package_base,
              "display_release": display_pub.get("release") if isinstance(display_pub, dict) else None,
              "display_manifest_sha256": display_manifest_sha, "display_package_base_url": display_base,
              "status": "passed" if passed else "failed",
              "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "checks": checks, "evidence": evidence, "failures": failures}
    if output_path.exists():
        raise HostedValidationError("report output already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--dataset", required=True, choices=sorted(upload.ALLOWED_PRODUCTS))
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--package-manifest-sha256", required=True)
    parser.add_argument("--display-package", type=Path)
    parser.add_argument("--query-controls", required=True, type=Path)
    parser.add_argument("--controls-sha256", required=True)
    parser.add_argument("--query-spatial-hints", type=Path)
    parser.add_argument("--query-spatial-hints-sha256")
    parser.add_argument("--prior-receipt", action="append", type=Path, default=[])
    parser.add_argument("--expected-multipart-parent-summary-sha256")
    parser.add_argument("--expected-multipart-parent-record-sha256")
    parser.add_argument("--browser-evidence", type=Path)
    parser.add_argument("--browser-controls", type=Path)
    parser.add_argument("--browser-controls-sha256")
    parser.add_argument("--browser-metadata-policy", type=Path)
    parser.add_argument("--browser-metadata-policy-sha256")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate(plan_path=args.plan, dataset_id=args.dataset, receipt_path=args.receipt,
                          package_root=args.package, display_root=args.display_package,
                          controls_path=args.query_controls, output_path=args.output,
                          package_manifest_sha256=args.package_manifest_sha256,
                          controls_sha256=args.controls_sha256,
                          query_spatial_hints_path=args.query_spatial_hints,
                          query_spatial_hints_sha256=args.query_spatial_hints_sha256,
                          prior_receipt_paths=args.prior_receipt,
                          expected_multipart_parent_summary_sha256=args.expected_multipart_parent_summary_sha256,
                          expected_multipart_parent_record_sha256=args.expected_multipart_parent_record_sha256,
                          browser_evidence_path=args.browser_evidence,
                          browser_controls_path=args.browser_controls,
                          browser_controls_sha256=args.browser_controls_sha256,
                          browser_metadata_policy_path=args.browser_metadata_policy,
                          browser_metadata_policy_sha256=args.browser_metadata_policy_sha256)
        print(json.dumps({"dataset_id": report["dataset_id"], "status": report["status"],
                          "checks": report["checks"], "failures": report["failures"]}, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    except Exception as exc:
        print(f"hosted validation could not start: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
