#!/usr/bin/env python3
"""Build local Source Cooperative product drafts and exact upload plans.

This tool is offline and read-only with respect to package data. It never calls
Source Cooperative, creates products, uploads bytes, or changes publication
status. Upload plans contain portable file descriptors and checksums only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
import sys
from typing import Any
from urllib.parse import quote

import yaml

CHUNK_BYTES = 8 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DISPLAY_RELEASE_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
MIME_BY_SUFFIX = {
    ".cpp": "text/plain",
    ".log": "text/plain",
    ".wasm": "application/wasm",
    ".css": "text/css",
    ".csv": "text/csv",
    ".dbf": "application/vnd.shp",
    ".geojson": "application/geo+json",
    ".gpkg": "application/geopackage+sqlite3",
    ".html": "text/html",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".md": "text/markdown",
    ".mjs": "text/javascript",
    ".parquet": "application/vnd.apache.parquet",
    ".pdf": "application/pdf",
    ".pmtiles": "application/vnd.pmtiles",
    ".png": "image/png",
    ".prj": "text/plain",
    ".py": "text/x-python",
    ".shp": "application/vnd.shp",
    ".shx": "application/vnd.shp",
    ".sqlite": "application/vnd.sqlite3",
    ".svg": "image/svg+xml",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".toml": "application/toml",
    ".txt": "text/plain",
    ".webp": "image/webp",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".gz": "application/gzip",
    ".lock": "text/plain",
}
EXTENSIONLESS_TEXT_NAMES = {"LICENSE", "NOTICE"}
FORBIDDEN_NAMES = {
    "credentials", "credential", "secrets", "secret", "token", "tokens",
    "id_rsa", "id_ed25519", "authorized_keys", "known_hosts", "config.json",
    "credentials.json", "service-account.json", "service_account.json",
    "access_key", "access-key", "private_key", "private-key",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}


class ProductError(Exception):
    """Invalid canonical input or unsafe/incomplete upload plan."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark,
                                                     "found an unhashable key", key_node.start_mark) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark,
                                                     f"found duplicate key {key!r}", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_file(path: Path) -> tuple[int, str]:
    before = path.stat()
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    after = path.stat()
    if (size != before.st_size or size != after.st_size or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino or before.st_dev != after.st_dev):
        raise ProductError(f"file changed while hashing: {path.name}")
    return size, digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductError(f"cannot read JSON: {path.name}: {exc}") from exc


def _validate_display_style(style: Any, style_path: str, asset: dict[str, Any], dataset_id: str) -> None:
    if not isinstance(style, dict) or style.get("version") != 8:
        raise ProductError(f"{dataset_id}: display style must be a MapLibre style v8: {style_path}")
    sources = style.get("sources")
    data_source = sources.get("data") if isinstance(sources, dict) else None
    if not isinstance(data_source, dict) or data_source.get("type") != "vector":
        raise ProductError(f"{dataset_id}: display style requires a vector sources.data: {style_path}")
    url = data_source.get("url")
    if not isinstance(url, str) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", url):
        raise ProductError(f"{dataset_id}: display style sources.data.url must be a plain relative path: {style_path}")
    raw_url = url
    if not raw_url or raw_url.startswith("/") or "?" in raw_url or "#" in raw_url:
        raise ProductError(f"{dataset_id}: unsafe PMTiles URL in display style: {url}")
    resolved_url = posixpath.normpath(posixpath.join(posixpath.dirname(style_path), raw_url))
    try:
        resolved_url = safe_relpath(resolved_url, "PMTiles style URL").as_posix()
    except ProductError as exc:
        raise ProductError(f"{dataset_id}: unsafe PMTiles URL in display style: {url}") from exc
    if resolved_url != asset.get("path"):
        raise ProductError(f"{dataset_id}: display style URL does not resolve to asset path: {url}")
    expected_type = {"polygon": "fill", "line": "line", "point": {"circle", "symbol"}}[asset.get("geometry_type")]
    layers = style.get("layers")
    matches = [layer for layer in layers if isinstance(layer, dict)
               and layer.get("source") == "data"
               and layer.get("source-layer") == asset.get("source_layer")
               and layer.get("type") in (expected_type if isinstance(expected_type, set) else {expected_type})] if isinstance(layers, list) else []
    if not matches:
        raise ProductError(f"{dataset_id}: display style has no matching source-layer/type: {style_path}")


def safe_relpath(value: Any, label: str, *, allow_hidden: bool = False) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ProductError(f"{label} must be a non-empty POSIX relative path")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (not posix.parts or posix.is_absolute() or windows.is_absolute() or windows.drive
            or any(part in ("", ".", "..") for part in posix.parts)):
        raise ProductError(f"unsafe {label}: {value}")
    if not allow_hidden and any(part.startswith(".") for part in posix.parts):
        raise ProductError(f"hidden path is not allowed: {value}")
    lower_parts = {part.lower() for part in posix.parts}
    if lower_parts & FORBIDDEN_NAMES or posix.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise ProductError(f"credential path is not allowed: {value}")
    if any("credential" in part.lower() or "secret" in part.lower() for part in posix.parts):
        raise ProductError(f"credential path is not allowed: {value}")
    return posix


def safe_repo_file(root: Path, relative: str, label: str) -> Path:
    rel = safe_relpath(relative, label)
    candidate = root.joinpath(*rel.parts)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ProductError(f"{label} traverses a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        repo = root.resolve(strict=True)
    except OSError as exc:
        raise ProductError(f"missing {label}: {relative}") from exc
    if not resolved.is_relative_to(repo) or not resolved.is_file():
        raise ProductError(f"{label} is not a regular in-repository file: {relative}")
    return resolved


def verify_supplements(root: Path, config: dict[str, Any], dataset_id: str) -> None:
    """Check canonical supplement pins while generating as well as staging drafts."""
    for supplement in config["supplements"]:
        source_path = safe_repo_file(root, supplement["path"], "supplement")
        _, actual_hash = inspect_file(source_path)
        if actual_hash != supplement["sha256"]:
            raise ProductError(f"{dataset_id}: supplement SHA-256 mismatch: {supplement['path']}")


def load_records(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for record_path in sorted((root / "datasets").glob("*/dataset.yaml")):
        try:
            record = yaml.load(record_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except (OSError, yaml.YAMLError) as exc:
            raise ProductError(f"cannot read canonical record {record_path.parent.name}: {exc}") from exc
        if not isinstance(record, dict):
            raise ProductError(f"canonical record must be a YAML object: {record_path.parent.name}")
        dataset_id = record.get("id")
        if not isinstance(dataset_id, str) or dataset_id != record_path.parent.name:
            raise ProductError(f"canonical id does not match datasets directory: {record_path.parent.name}")
        if record.get("publication", {}).get("source_coop") is not None:
            records[dataset_id] = record
    return records


def source_config(record: dict[str, Any]) -> dict[str, Any]:
    config = (record.get("publication") or {}).get("source_coop")
    if not isinstance(config, dict):
        raise ProductError(f"{record.get('id')}: publication.source_coop must be an object")
    product_id = config.get("product_id")
    if (not isinstance(product_id, str) or not 3 <= len(product_id) <= 40
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", product_id)
            or "--" in product_id):
        raise ProductError("product_id must be a 3–40 character lowercase Source-style slug without consecutive hyphens")
    if config.get("owner_status") not in ("proposed", "confirmed"):
        raise ProductError(f"{record.get('id')}: owner_status must be proposed or confirmed")
    owner = config.get("owner")
    if owner is not None and (not isinstance(owner, str) or not 3 <= len(owner) <= 40
                              or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", owner)
                              or "--" in owner):
        raise ProductError(f"{record.get('id')}: owner must be null or a 3–40 character lowercase account slug")
    for key in ("title", "summary", "license_note", "attribution", "temporal_note"):
        if not isinstance(config.get(key), str):
            raise ProductError(f"{record.get('id')}: source_coop.{key} must be a string")
    for key in ("tags", "limitations", "supplements"):
        if not isinstance(config.get(key), list):
            raise ProductError(f"{record.get('id')}: source_coop.{key} must be a list")
    for item in config["tags"] + config["limitations"]:
        if not isinstance(item, str):
            raise ProductError(f"{record.get('id')}: tags and limitations must contain strings")
    for supplement in config["supplements"]:
        if not isinstance(supplement, dict):
            raise ProductError(f"{record.get('id')}: supplement must be an object")
        safe_relpath(supplement.get("path"), "supplement path")
        safe_relpath(supplement.get("destination"), "supplement destination")
        if not supplement["destination"].startswith("metadata/"):
            raise ProductError(f"{record.get('id')}: supplement destination must start metadata/<version>/")
        if len(PurePosixPath(supplement["destination"]).parts) < 3:
            raise ProductError(f"{record.get('id')}: supplement destination must include a file below metadata/<version>/")
        if not isinstance(supplement.get("sha256"), str) or not SHA256_RE.fullmatch(supplement["sha256"]):
            raise ProductError(f"{record.get('id')}: supplement SHA-256 is invalid")
    return config


def verified_account(root: Path, config: dict[str, Any]) -> tuple[bool, str | None]:
    owner = config.get("owner")
    verification = config.get("account_verification")
    if not isinstance(verification, dict):
        return False, "Source Cooperative account verification is not recorded"
    if verification.get("status") != "confirmed" or verification.get("owner") != owner or not owner:
        return False, "account_verification must confirm the exact proposed owner"
    evidence_path = verification.get("evidence_path")
    evidence_hash = verification.get("evidence_sha256")
    if not isinstance(evidence_path, str) or not isinstance(evidence_hash, str) or not SHA256_RE.fullmatch(evidence_hash):
        return False, "account_verification evidence path/hash is missing or invalid"
    try:
        path = safe_repo_file(root, evidence_path, "account verification evidence")
        actual_hash = sha256_file(path)
        if actual_hash != evidence_hash:
            return False, "account verification evidence checksum does not match"
        evidence = read_json(path)
    except ProductError:
        return False, "account verification evidence is missing or unsafe"
    if not isinstance(evidence, dict) or evidence.get("owner") != owner or evidence.get("status") != "confirmed":
        return False, "account verification evidence does not confirm the owner"
    return True, None


def _snapshot_status(root: Path, record: dict[str, Any]) -> tuple[bool, dict[str, Any], dict[str, Any] | None, str | None]:
    publication = record.get("publication") or {}
    dataset_id = record["id"]
    release = publication.get("release")
    manifest_path = publication.get("manifest_path")
    manifest_sha = publication.get("manifest_sha256")
    catalog = publication.get("catalog") or {}
    snapshot_path = catalog.get("snapshot_path")
    snapshot_sha = catalog.get("snapshot_sha256")
    summary = {"release": release, "manifest_path": manifest_path, "manifest_sha256": manifest_sha,
               "snapshot_path": snapshot_path, "snapshot_sha256": snapshot_sha}
    if publication.get("status") != "prepared":
        return False, summary, None, f"canonical publication status is {publication.get('status', 'unset')}, not prepared"
    try:
        if not isinstance(release, str):
            raise ProductError("canonical publication.release is missing")
        release_path = safe_relpath(release, "release id")
        if len(release_path.parts) != 1:
            raise ProductError("canonical publication.release must be one path segment")
        if not isinstance(manifest_path, str) or not isinstance(manifest_sha, str) or not SHA256_RE.fullmatch(manifest_sha):
            raise ProductError("canonical manifest path/hash is missing or invalid")
        if not isinstance(snapshot_path, str) or not isinstance(snapshot_sha, str) or not SHA256_RE.fullmatch(snapshot_sha):
            raise ProductError("canonical catalog snapshot path/hash is missing or invalid")
        tracked_manifest_path = safe_repo_file(root, manifest_path, "tracked release manifest")
        if sha256_file(tracked_manifest_path) != manifest_sha:
            raise ProductError("tracked release manifest checksum does not match canonical record")
        manifest = read_json(tracked_manifest_path)
        if manifest_identity(manifest) != (dataset_id, release):
            raise ProductError("tracked release manifest identity does not match canonical record")
        snapshot_file = safe_repo_file(root, snapshot_path, "catalog snapshot")
        if sha256_file(snapshot_file) != snapshot_sha:
            raise ProductError("catalog snapshot checksum does not match canonical record")
        snapshot = read_json(snapshot_file)
        if not isinstance(snapshot, dict) or snapshot.get("dataset_id") != dataset_id or snapshot.get("release") != release:
            raise ProductError("catalog snapshot identity does not match canonical record")
        if snapshot.get("package_manifest_sha256") != manifest_sha:
            raise ProductError("catalog snapshot does not bind canonical manifest")
        receipt_path = publication.get("release_receipt_path")
        local_binding: dict[str, Any] = {"status": "inventory_only_unbound", "sha256": None, "bound_files": {}}
        if receipt_path:
            receipt_file = safe_repo_file(root, receipt_path, "release receipt")
            receipt = read_json(receipt_file)
            if not isinstance(receipt, dict) or receipt.get("manifest_sha256") != manifest_sha:
                raise ProductError("release receipt does not bind canonical manifest")
            if receipt.get("dataset_id", dataset_id) != dataset_id or receipt.get("release_id", release) != release:
                raise ProductError("release receipt identity does not match canonical record")
            binding_sha = receipt.get("package_binding_sha256")
            if binding_sha is not None:
                if not isinstance(binding_sha, str) or not SHA256_RE.fullmatch(binding_sha):
                    raise ProductError("release receipt package binding SHA-256 is invalid")
                proof = snapshot.get("binding_proof")
                if not isinstance(proof, dict) or proof.get("path") != "proof/package-binding.json" or proof.get("sha256") != binding_sha:
                    raise ProductError("catalog snapshot package binding proof does not match release receipt")
                proof_rel = PurePosixPath(snapshot_path).parent / safe_relpath(proof["path"], "package binding proof path")
                proof_file = safe_repo_file(root, proof_rel.as_posix(), "package binding proof")
                if sha256_file(proof_file) != binding_sha:
                    raise ProductError("package binding proof checksum does not match release receipt")
                package_binding = read_json(proof_file)
                if not isinstance(package_binding, dict) or package_binding.get("manifest_sha256") != manifest_sha:
                    raise ProductError("package binding proof does not bind canonical manifest")
                bound_files = package_binding.get("bound_files")
                if not isinstance(bound_files, dict):
                    raise ProductError("package binding proof lacks bound_files inventory")
                normalized_bound = {}
                for path, item in bound_files.items():
                    rel = safe_relpath(path, "bound package path").as_posix()
                    if (not isinstance(item, dict) or not isinstance(item.get("sha256"), str)
                            or not SHA256_RE.fullmatch(item["sha256"]) or type(item.get("size_bytes")) is not int
                            or item["size_bytes"] < 0):
                        raise ProductError(f"package binding has invalid file declaration: {rel}")
                    normalized_bound[rel] = {"sha256": item["sha256"], "size_bytes": item["size_bytes"]}
                local_binding = {"status": "verified", "sha256": binding_sha, "bound_files": normalized_bound}
            elif snapshot.get("binding_proof"):
                raise ProductError("catalog snapshot has an unbound package binding proof")
        elif snapshot.get("binding_proof"):
            raise ProductError("catalog snapshot package binding proof has no canonical release receipt")
        snapshot["_source_products_package_binding"] = local_binding
        summary["local_metadata_integrity"] = "passed"
        summary["package_binding_status"] = local_binding["status"]
        summary["package_binding_sha256"] = local_binding["sha256"]
        summary["bound_file_count"] = len(local_binding["bound_files"])
        summary["snapshot_file_count"] = len(snapshot.get("files", []))
        return True, summary, snapshot, None
    except (OSError, ProductError, json.JSONDecodeError) as exc:
        summary["local_metadata_integrity"] = "failed"
        return False, summary, None, str(exc)


def manifest_identity(manifest: dict[str, Any]) -> tuple[str | None, str | None]:
    if not isinstance(manifest, dict):
        return None, None
    dataset = manifest.get("dataset_id", manifest.get("dataset"))
    release = manifest.get("release_id", manifest.get("release"))
    if isinstance(release, dict):
        release = release.get("id") or release.get("release_id")
    return (dataset if isinstance(dataset, str) else None,
            release if isinstance(release, str) else None)


def snapshot_collection(root: Path, snapshot_path: str | None, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    rel = snapshot.get("collection_path")
    if not isinstance(snapshot_path, str) or not isinstance(rel, str):
        return None
    safe_collection = safe_relpath(rel, "snapshot collection path")
    base = PurePosixPath(snapshot_path).parent / "files" / safe_collection
    path = safe_repo_file(root, base.as_posix(), "snapshot collection")
    entries = snapshot.get("files")
    expected = next((item for item in entries if isinstance(item, dict) and item.get("path") == rel), None) if isinstance(entries, list) else None
    if not isinstance(expected, dict):
        raise ProductError("catalog snapshot does not include its collection file")
    if (type(expected.get("size_bytes")) is not int or path.stat().st_size != expected["size_bytes"]
            or not isinstance(expected.get("sha256"), str) or sha256_file(path) != expected["sha256"]):
        raise ProductError("snapshot collection file does not match its recorded size/SHA-256")
    collection = read_json(path)
    if not isinstance(collection, dict):
        raise ProductError("snapshot collection must be a JSON object")
    if collection.get("type") != "Collection" or collection.get("id") != snapshot.get("dataset_id"):
        raise ProductError("snapshot collection is not a STAC Collection")
    return collection


def external_links(value: Any, prefix: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                label = f"{path}.{key}" if path else str(key)
                normalized = str(key).lower().replace(":", "_")
                if isinstance(child, str) and (normalized in ("url", "href") or normalized.endswith("_url")):
                    if child.startswith(("https://", "http://")):
                        found.append({"title": "Producer source", "url": child})
                else:
                    visit(child, label)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")

    visit(value, prefix)
    return dedupe_links(found)


def normalize_external_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value.startswith(("https://", "http://")):
        return value
    if re.fullmatch(r"10\.\d{4,9}/\S+", value):
        return f"https://doi.org/{value}"
    return None


def source_field_links(source: Any) -> list[dict[str, str]]:
    if not isinstance(source, dict):
        return []
    links: list[dict[str, str]] = []

    def add(value: Any, title: str) -> None:
        url = normalize_external_url(value)
        if url:
            links.append({"title": title, "url": url})

    add(source.get("paper_doi"), "Research paper")
    add(source.get("source_doi"), "Dataset release")
    add(source.get("doi"), "Dataset release")
    add(source.get("url"), "Original download")
    add(source.get("source_url"), "Original download")
    technical = source.get("technical_documentation")
    if isinstance(technical, dict):
        add(technical.get("url"), "Producer technical documentation")
    field_catalog = source.get("field_catalog")
    if isinstance(field_catalog, dict):
        add(field_catalog.get("url"), "Producer attribute catalogue")
    license_info = source.get("license")
    if isinstance(license_info, dict):
        add(license_info.get("url"), "License terms")
    add(source.get("license_url"), "License terms")
    return links


def collection_links(collection: dict[str, Any] | None) -> list[dict[str, str]]:
    if not collection:
        return []
    links: list[dict[str, str]] = []
    rel_titles = {
        "via": "Dataset release",
        "license": "License terms",
        "canonical": "Canonical dataset record",
        "cite-as": "Research paper",
    }
    for item in collection.get("links", []):
        if not isinstance(item, dict):
            continue
        title = rel_titles.get(item.get("rel"))
        url = normalize_external_url(item.get("href"))
        if title and url:
            links.append({"title": title, "url": url})
    role_titles = {
        "producer": "Producer",
        "processor": "Folia converter",
        "host": "Folia host",
        "licensor": "Licensor",
    }
    for provider in collection.get("providers", []):
        if not isinstance(provider, dict):
            continue
        name = provider.get("name")
        url = normalize_external_url(provider.get("url"))
        roles = provider.get("roles", [])
        if (not url or not isinstance(name, str) or not isinstance(roles, list)
                or any(not isinstance(role, str) for role in roles)):
            continue
        normalized_roles = set(roles)
        if name.lower() == "folia" and {"processor", "host"}.issubset(normalized_roles):
            links.append({"title": "Folia converter/host", "url": url})
            continue
        for role in roles:
            title_prefix = role_titles.get(role)
            if title_prefix:
                title = f"{title_prefix}: {name}" if role in ("producer", "licensor") else title_prefix
                links.append({"title": title, "url": url})
    return links


def dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for item in links:
        current = unique.get(item["url"])
        if current is None or (current["title"] == "Producer source" and item["title"] != "Producer source"):
            unique[item["url"]] = item
    return [unique[url] for url in sorted(unique)]


def product_links(record: dict[str, Any], collection: dict[str, Any] | None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    review = record.get("review") or {}
    sources: list[dict[str, str]] = source_field_links(record.get("source"))
    sources.extend(collection_links(collection))
    for label, value in (
        ("publication_assessment", review.get("publication_assessment")),
        ("availability", review.get("availability")),
        ("discovery", record.get("discovery")),
        ("community", {"url": record.get("community_url")}),
    ):
        sources.extend(external_links(value, label))
    related: list[dict[str, str]] = []
    for item in record.get("related_datasets") or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("id") or "Related dataset"
        url = item.get("url")
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            related.append({"title": str(title), "url": url})
        related.extend(external_links(item.get("evidence", []), str(title)))
    source_unique = {(item["title"], item["url"]): item for item in sources}
    related_unique = {(item["title"], item["url"]): item for item in related}
    return (dedupe_links(list(source_unique.values())),
            dedupe_links(list(related_unique.values())))


def draft_for(root: Path, record: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    config = source_config(record)
    dataset_id = record["id"]
    verify_supplements(root, config, dataset_id)
    publication = record.get("publication") or {}
    review = record.get("review") or {}
    readiness = review.get("publication_readiness") or {}
    assessment = review.get("publication_assessment") or {}
    review_stage = readiness.get("stage") or assessment.get("stage")
    local_followup = readiness.get("local_followup") or []
    blockers: list[str] = []
    ready, binding, snapshot, error = _snapshot_status(root, record)
    if not ready:
        blockers.append(error or "local release is not prepared")
    account_ok, account_error = verified_account(root, config)
    if config.get("owner_status") != "confirmed":
        blockers.append("Source Cooperative owner is proposed, not confirmed")
    if not account_ok:
        blockers.append(account_error or "Source Cooperative account verification is incomplete")
    if not config.get("owner"):
        blockers.append("Source Cooperative owner is not set")
    if not config["product_id"]:
        blockers.append("Source Cooperative product_id is not set")
    if review_stage and (not ready or local_followup):
        blockers.append(f"Canonical publication review stage: {review_stage}")
    if isinstance(local_followup, list):
        blockers.extend(f"Canonical local follow-up: {item}" for item in local_followup if isinstance(item, str))
    collection = None
    if ready and snapshot is not None:
        try:
            collection = snapshot_collection(root, binding["snapshot_path"], snapshot)
        except (OSError, ProductError, json.JSONDecodeError) as exc:
            ready = False
            blockers.append(f"catalog snapshot collection is unavailable: {exc}")
    assets = []
    release_files = []
    if ready and isinstance(collection, dict):
        raw_assets = collection.get("assets") or {}
        if isinstance(raw_assets, dict):
            for asset_id, asset in sorted(raw_assets.items()):
                if isinstance(asset, dict):
                    assets.append({
                        "asset_id": asset_id,
                        "title": asset.get("title"),
                        "href": asset.get("href"),
                        "media_type": asset.get("type"),
                        "roles": asset.get("roles", []),
                        "checksum": asset.get("file:checksum"),
                        "size_bytes": asset.get("file:size"),
                    })
        manifest = read_json(safe_repo_file(root, binding["manifest_path"], "tracked release manifest"))
        release_files = [
            {"path": item["path"], "kind": item["kind"], "size_bytes": item["size_bytes"]}
            for item in manifest_declarations(manifest, dataset_id)
            if set(item["kind"].split(", ")) & {
                "asset", "field_dictionary", "supporting_files", "display_derivatives",
                "data_license", "source_license", "source_attribution",
            }
        ]
    if ready and binding.get("release"):
        release_files.extend({"path": item["destination"], "kind": "supplement"} for item in config["supplements"])
    display_ref = _display_draft_reference(record)
    display_publication = (_load_display_draft(root, record, binding.get("release")) if display_ref else None)
    source_proxy = f"s3://{config['owner']}/{config['product_id']}" if config.get("owner") else None
    creation_ready = bool(ready and config.get("owner_status") == "confirmed" and account_ok and not local_followup)
    source_links, related_links = product_links(record, collection)
    draft = {
        "schema_version": 1,
        "draft_type": "source_coop_product_draft",
        "dataset_id": dataset_id,
        "dataset_title": record.get("title"),
        "publication_status": publication.get("status", "candidate"),
        "release": binding.get("release"),
        "display_publication": display_publication,
        "local_readiness": (review_stage or "prepared") if ready else "blocked",
        "owner": config.get("owner"),
        "owner_status": config["owner_status"],
        "independent_maintainer_proposal": {
            "owner": config.get("owner"),
            "status": config["owner_status"],
            "relationship": "new Source Cooperative product proposal; immutable package metadata is unchanged",
        },
        "product_id": config["product_id"],
        "title": config["title"],
        "summary": config["summary"],
        "tags": config["tags"],
        "license_note": config["license_note"],
        "attribution": config["attribution"],
        "temporal_note": config["temporal_note"],
        "limitations": config["limitations"],
        "supplements": config["supplements"],
        "proposed_source_proxy": {"uri": source_proxy, "status": "proposed"} if source_proxy else None,
        "snapshot_binding": binding,
        "review_context": {
            "stage": review_stage,
            "local_followup": local_followup,
            "asset_integrity": readiness.get("asset_integrity"),
            "public_followup": readiness.get("public_followup", []),
            "status_basis": "canonical publication status plus local manifest/snapshot hashes; this tool does not rerun scientific or public-host validation",
        },
        "snapshot_collection": ({
            "id": collection.get("id"),
            "title": collection.get("title"),
            "description": collection.get("description"),
            "license": collection.get("license"),
            "extent": collection.get("extent"),
            "providers": collection.get("providers"),
            "assets": assets,
        } if collection else None),
        "assets": assets if ready else [],
        "release_files": release_files,
        "source_links": source_links,
        "related_dataset_links": related_links,
        "creation_ready": creation_ready,
        "ready_for_review": True,
        "ready_for_creation": creation_ready,
        "created": False,
        "hosted": False,
        "blockers": sorted(set(blockers)),
    }
    readme = render_readme(draft)
    consumer_readme = render_consumer_readme(draft)
    return draft, readme, consumer_readme


def _display_draft_reference(record: dict[str, Any]) -> dict[str, Any] | None:
    display = (record.get("publication") or {}).get("display")
    if display is None:
        return None
    if not isinstance(display, dict):
        raise ProductError(f"{record.get('id')}: publication.display must be an object")
    release = display.get("release")
    manifest_path = display.get("manifest_path")
    manifest_sha = display.get("manifest_sha256")
    if (not isinstance(release, str) or len(release) > 40 or not DISPLAY_RELEASE_RE.fullmatch(release) or not isinstance(manifest_path, str)
            or not isinstance(manifest_sha, str) or not SHA256_RE.fullmatch(manifest_sha)):
        raise ProductError(f"{record.get('id')}: publication.display pin is invalid")
    safe_relpath(manifest_path, "display manifest path")
    expected_path = f"datasets/{record.get('id')}/display/{release}/manifest.json"
    if manifest_path != expected_path:
        raise ProductError(f"{record.get('id')}: display manifest path must be {expected_path}")
    return {"release": release, "manifest_path": manifest_path, "manifest_sha256": manifest_sha}


def _load_display_draft(root: Path, record: dict[str, Any], analytic_release: str | None) -> dict[str, Any]:
    reference = _display_draft_reference(record)
    if reference is None:
        raise ProductError(f"{record.get('id')}: no canonical display pin")
    path = safe_repo_file(root, reference["manifest_path"], "tracked display manifest")
    if sha256_file(path) != reference["manifest_sha256"]:
        raise ProductError(f"{record.get('id')}: tracked display manifest checksum does not match canonical pin")
    manifest = read_json(path)
    expected = {"schema_version": 1, "dataset_id": record.get("id"),
                "display_release": reference["release"], "analytic_release": analytic_release,
                "status": "prepared"}
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in expected.items()):
        raise ProductError(f"{record.get('id')}: tracked display manifest identity/release mismatch")
    files = manifest.get("files")
    assets = manifest.get("assets")
    if not isinstance(files, dict) or not isinstance(assets, list) or not assets:
        raise ProductError(f"{record.get('id')}: tracked display manifest has no valid file/asset inventory")
    displayed_assets = []
    seen_ids = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ProductError(f"{record.get('id')}: tracked display manifest asset is invalid")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id or asset_id in seen_ids:
            raise ProductError(f"{record.get('id')}: tracked display manifest asset IDs are invalid or duplicated")
        seen_ids.add(asset_id)
        path_rel = safe_relpath(asset.get("path"), "display asset path").as_posix()
        style_rel = safe_relpath(asset.get("style_path"), "display style path").as_posix()
        if path_rel not in files or style_rel not in files:
            raise ProductError(f"{record.get('id')}: display asset/style is absent from manifest file inventory")
        declaration = files[path_rel]
        if (not isinstance(declaration, dict) or declaration.get("sha256") != asset.get("sha256")
                or declaration.get("size_bytes") != asset.get("size_bytes")):
            raise ProductError(f"{record.get('id')}: display asset metadata disagrees with manifest file inventory: {path_rel}")
        href_prefix = f"display/{reference['release']}"
        displayed_assets.append({
            "id": asset_id,
            "title": asset.get("title") or asset_id,
            "path": path_rel,
            "href": f"{href_prefix}/{path_rel}",
            "style_path": style_rel,
            "style_href": f"{href_prefix}/{style_rel}",
            "size_bytes": asset["size_bytes"],
            "sha256": asset["sha256"],
        })
    href = f"display/{reference['release']}/manifest.json"
    return {**reference, "manifest_href": href, "assets": displayed_assets}


def render_readme(draft: dict[str, Any]) -> str:
    lines = [
        f"# {draft['title']}", "",
        "**Draft metadata:** finalize the publication wording and re-check this file before any upload. No product has been created and no files have been uploaded.", "",
        f"- Dataset: `{draft['dataset_id']}` ({draft.get('dataset_title') or 'title not set'})",
        f"- Product ID: `{draft['product_id']}`",
        f"- Local publication status: `{draft['publication_status']}`",
        f"- Local readiness: `{draft['local_readiness']}`",
        f"- Owner: `{draft.get('owner') or 'unset'}` ({draft['owner_status']})",
        f"- Canonical publication review stage: `{draft.get('review_context', {}).get('stage') or 'not recorded'}`",
        f"- Creation readiness: `{str(draft['creation_ready']).lower()}`",
        f"- Hosted: `{str(draft['hosted']).lower()}`",
        "",
        "## Summary", "", draft["summary"], "",
        "The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.", "",
        "## Credits and license", "",
        f"- Producer attribution: {draft['attribution']}",
        f"- License note: {draft['license_note']}",
        f"- Temporal scope: {draft['temporal_note']}", "",
    ]
    lines.extend(["## Sources and DOI references", ""])
    for link in draft.get("source_links", []):
        lines.append(f"- [{link['title']}]({link['url']})")
    if not draft.get("source_links"):
        lines.append("No source or DOI links are recorded.")
    lines.extend(["", "## Related datasets", ""])
    for link in draft.get("related_dataset_links", []):
        lines.append(f"- [{link['title']}]({link['url']})")
    if not draft.get("related_dataset_links"):
        lines.append("No related dataset links are recorded.")
    lines.extend(["", "## Versioned metadata supplements", ""])
    supplements = draft.get("supplements") or []
    if supplements:
        for item in supplements:
            relative = posixpath.relpath(item["path"], f"datasets/{draft['dataset_id']}/source-coop")
            lines.append(f"- [{PurePosixPath(item['path']).name}]({relative}) → `{item['destination']}`")
    else:
        lines.append("No separate metadata supplements are recorded.")
    lines.extend(["", "## Snapshot assets", ""])
    assets = draft.get("assets") or []
    if assets:
        for asset in assets:
            lines.append(f"- `{asset['asset_id']}`: {asset.get('title') or asset.get('href') or 'untitled'} ({asset.get('media_type') or 'media type unspecified'})")
    else:
        lines.append("No release assets are included in this draft.")
    display = draft.get("display_publication")
    lines.extend(["", "## Versioned display package", ""])
    if display:
        lines.append(f"- [Display manifest]({display['manifest_href']}) (SHA-256 `{display['manifest_sha256']}`)")
        for asset in display.get("assets", []):
            lines.append(f"- [{asset['title']} PMTiles]({asset['href']}) ({asset['size_bytes']} bytes; SHA-256 `{asset['sha256']}`)")
            lines.append(f"  - [Map style]({asset['style_href']})")
    else:
        lines.append("No versioned display package is recorded.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in draft.get("limitations", []))
    if not draft.get("limitations"):
        lines.append("- None recorded.")
    lines.extend(["", "## Proposed route", ""])
    proxy = draft.get("proposed_source_proxy")
    if proxy:
        lines.append(f"Proposed source proxy: `{proxy['uri']}`. This is a proposal, not a hosted location.")
    else:
        lines.append("No owner is confirmed; no source proxy is proposed.")
    if draft.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in draft["blockers"])
    local_followup = draft.get("review_context", {}).get("local_followup") or []
    if local_followup:
        lines.extend(["", "## Canonical local follow-up", ""])
        lines.extend(f"- {item}" for item in local_followup)
    lines.append("")
    return "\n".join(lines)


def render_consumer_readme(draft: dict[str, Any]) -> str:
    lines = [f"# {draft['title']}", "", draft["summary"], ""]
    if draft.get("publication_status") != "prepared" or not draft.get("release"):
        lines.extend([
            "**Planned product:** no converted release is currently available.", "",
            "This page describes the intended dataset and its planned metadata. No release files are linked yet.", "",
        ])
    else:
        lines.extend([
            f"**Selected release:** `{draft['release']}`. This link structure describes the prepared package; public hosting and validation have not been checked by this generator.", "",
        ])
    lines.extend(["## Scope and formats", ""])
    collection = draft.get("snapshot_collection") or {}
    description = collection.get("description")
    if description:
        lines.extend([str(description), ""])
    assets = draft.get("assets") or []
    formats = sorted({asset["media_type"] for asset in assets if asset.get("media_type")})
    if draft.get("display_publication"):
        formats = sorted(set(formats) | {"application/vnd.pmtiles"})
    if formats:
        lines.append("Formats: " + ", ".join(f"`{value}`" for value in formats) + ".")
    elif draft.get("publication_status") != "prepared":
        lines.append("Formats will be listed when a converted release is prepared.")
    else:
        lines.append("The prepared package has no declared media types in its collection assets.")
    lines.extend(["", "## Producer, source, and license", "",
                  f"- Producer attribution: {draft['attribution']}",
                  f"- License: {draft['license_note']}",
                  f"- Temporal scope: {draft['temporal_note']}", ""])
    if draft.get("source_links"):
        for link in draft["source_links"]:
            lines.append(f"- [{link['title']}]({link['url']})")
        lines.append("")
    lines.extend(["## Release files", ""])
    release_files = draft.get("release_files") or []
    if release_files and draft.get("release"):
        for item in release_files:
            kind = item.get("kind", "file")
            label = PurePosixPath(item["path"]).name
            href = (item["path"] if kind == "supplement"
                    else f"releases/{draft['release']}/{item['path']}")
            lines.append(f"- [{label}]({href}) ({kind})")
    else:
        lines.append("No release files are available.")
    display = draft.get("display_publication")
    lines.extend(["", "## Display package", ""])
    if display:
        lines.extend([
            f"Display release: `{display['release']}`. The manifest is pinned at SHA-256 `{display['manifest_sha256']}`.",
            "Display assets are separate immutable derivatives bound to this analytical release.",
            f"- [Display manifest](display/{display['release']}/manifest.json)",
        ])
        for asset in display.get("assets", []):
            lines.append(f"- [{asset['title']} PMTiles]({asset['href']}) ({asset['size_bytes']} bytes; SHA-256 `{asset['sha256']}`)")
            lines.append(f"  - [Map style]({asset['style_href']})")
    else:
        lines.append("No versioned display package is recorded.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in draft.get("limitations", []))
    if not draft.get("limitations"):
        lines.append("- None recorded.")
    related = draft.get("related_dataset_links") or []
    if related:
        lines.extend(["", "## Related datasets", ""])
        lines.extend(f"- [{item['title']}]({item['url']})" for item in related)
    lines.extend(["", "Public hosting and scientific validation status must be checked independently.", ""])
    return "\n".join(lines)


def generated_paths(dataset_id: str) -> tuple[Path, Path, Path]:
    base = Path("datasets") / dataset_id / "source-coop"
    return base / "product-draft.json", base / "README.md", base / "product-README.md"


def generate(root: Path, *, write: bool) -> list[str]:
    errors = []
    for dataset_id, record in load_records(root).items():
        try:
            draft, readme, consumer_readme = draft_for(root, record)
            json_rel, readme_rel, consumer_rel = generated_paths(dataset_id)
            outputs = {json_rel: canonical_json(draft), readme_rel: readme.encode("utf-8"),
                       consumer_rel: consumer_readme.encode("utf-8")}
            for relative, expected in outputs.items():
                path = root / relative
                if write:
                    check = root
                    for part in relative.parts[:-1]:
                        check = check / part
                        if check.is_symlink():
                            raise ProductError(f"generated output path traverses a symlink: {relative.as_posix()}")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.is_symlink():
                        raise ProductError(f"generated output is a symlink: {relative.as_posix()}")
                    path.write_bytes(expected)
                elif not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
                    errors.append(f"stale or missing generated view: {relative.as_posix()}")
        except (OSError, ProductError, json.JSONDecodeError) as exc:
            errors.append(f"{dataset_id}: {exc}")
    return errors


def content_type(relpath: str) -> str:
    if not isinstance(relpath, str) or "\\" in relpath:
        raise ProductError(f"unknown asset extension: {relpath}")
    path = PurePosixPath(relpath)
    parts = path.parts
    if (path.is_absolute() or any(part in (".", "..") for part in parts)
            or re.match(r"^[A-Za-z]:", relpath) or str(path) != relpath
            or any(part.startswith(".") for part in parts)):
        raise ProductError(f"unsafe asset path: {relpath}")
    # Pinned native validation executables are provenance, not analytic assets.
    # Keep extensionless binary support limited to these exact provenance roles.
    direct_native = (len(parts) == 3 and parts[:2] == ("workflow", "native-oracle"))
    historical_native = (
        len(parts) == 5
        and parts[0] == "reports"
        and re.fullmatch(r"baseline-r[1-9][0-9]*", parts[1]) is not None
        and parts[2:4] == ("workflow", "native-oracle")
    )
    if (direct_native or historical_native) and path.name and not path.suffix:
        return "application/octet-stream"
    if path.name in EXTENSIONLESS_TEXT_NAMES:
        return "text/plain"
    suffix = PurePosixPath(relpath).suffix.lower()
    if suffix not in MIME_BY_SUFFIX:
        raise ProductError(f"unknown asset extension: {relpath}")
    return MIME_BY_SUFFIX[suffix]


def route_details(owner: str, object_key: str) -> dict[str, str]:
    encoded = "/".join(quote(part, safe="-._~") for part in object_key.split("/"))
    return {
        "bucket": owner,
        "endpoint": "https://data.source.coop",
        "s3_uri_proposed": f"s3://{owner}/{encoded}",
        "raw_url_proposed": f"https://data.source.coop/{quote(owner, safe='-._~')}/{encoded}",
    }


def package_inventory(package: Path, dataset_id: str, owner: str, product_id: str, release: str) -> list[dict[str, Any]]:
    if package.is_symlink():
        raise ProductError(f"{dataset_id}: package root is a symlink")
    try:
        package = package.resolve(strict=True)
    except OSError as exc:
        raise ProductError(f"{dataset_id}: package path does not exist") from exc
    if not package.is_dir():
        raise ProductError(f"{dataset_id}: package path is not a directory")
    files: list[Path] = []
    def walk_error(error: OSError) -> None:
        raise ProductError(f"{dataset_id}: cannot enumerate package files ({type(error).__name__})")

    for current, dirs, names in os.walk(package, topdown=True, onerror=walk_error, followlinks=False):
        base = Path(current)
        for name in list(dirs):
            path = base / name
            if path.is_symlink():
                raise ProductError(f"{dataset_id}: symlink is not allowed: {path.relative_to(package).as_posix()}")
            safe_relpath(path.relative_to(package).as_posix(), "package path")
        for name in names:
            path = base / name
            rel = path.relative_to(package).as_posix()
            safe_relpath(rel, "package path")
            if path.is_symlink():
                raise ProductError(f"{dataset_id}: symlink is not allowed: {rel}")
            if not path.is_file():
                raise ProductError(f"{dataset_id}: non-regular file is not allowed: {rel}")
            content_type(rel)
            files.append(path)
    files.sort(key=lambda path: path.relative_to(package).as_posix())
    result = []
    for path in files:
        rel = path.relative_to(package).as_posix()
        key = f"{product_id}/releases/{release}/{rel}"
        size, digest = inspect_file(path)
        result.append({
            "object_key": key,
            "path": rel,
            "size_bytes": size,
            "sha256": digest,
            "content_type": content_type(rel),
            **route_details(owner, key),
            "source": {"kind": "package", "dataset_id": dataset_id, "path": rel},
        })
    return result


def manifest_declarations(manifest: dict[str, Any], dataset_id: str) -> list[dict[str, Any]]:
    declarations_by_path: dict[str, dict[str, Any]] = {}

    def add(path: Any, digest: Any, size: Any, label: str, *, require_size: bool = True) -> None:
        rel = safe_relpath(path, f"{label} path").as_posix()
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ProductError(f"{dataset_id}: {label} has invalid SHA-256: {rel}")
        if require_size and (type(size) is not int or size < 0):
            raise ProductError(f"{dataset_id}: {label} has invalid size_bytes: {rel}")
        if size is not None and (type(size) is not int or size < 0):
            raise ProductError(f"{dataset_id}: {label} has invalid size_bytes: {rel}")
        declaration = {"path": rel, "sha256": digest, "size_bytes": size, "kind": label}
        previous = declarations_by_path.get(rel)
        if previous is not None:
            if previous["sha256"] != digest or (previous["size_bytes"] is not None and size is not None
                                                  and previous["size_bytes"] != size):
                raise ProductError(f"{dataset_id}: conflicting manifest declarations for {rel}")
            if previous["size_bytes"] is None:
                previous["size_bytes"] = size
            previous["kind"] = ", ".join(sorted(set(previous["kind"].split(", ")) | {label}))
        else:
            declarations_by_path[rel] = declaration

    raw_assets = manifest.get("assets")
    if isinstance(raw_assets, list):
        if not raw_assets:
            raise ProductError(f"{dataset_id}: prepared manifest assets cannot be empty")
        for item in raw_assets:
            if not isinstance(item, dict):
                raise ProductError(f"{dataset_id}: manifest assets must contain objects")
            add(item.get("href"), item.get("sha256"), item.get("size_bytes"), "asset")
            if item.get("field_dictionary"):
                add(item["field_dictionary"], item.get("field_dictionary_sha256"), None,
                    "field_dictionary", require_size=False)
    elif isinstance(raw_assets, dict):
        if not raw_assets:
            raise ProductError(f"{dataset_id}: prepared manifest assets cannot be empty")
        for path, item in sorted(raw_assets.items()):
            if not isinstance(item, dict):
                raise ProductError(f"{dataset_id}: legacy manifest asset must be an object")
            add(path, item.get("sha256"), item.get("size_bytes"), "asset")
    else:
        raise ProductError(f"{dataset_id}: manifest assets have unsupported form")

    for key in ("supporting_files", "display_derivatives"):
        values = manifest.get(key, [])
        if not isinstance(values, list):
            raise ProductError(f"{dataset_id}: manifest {key} must be a list")
        for item in values:
            if not isinstance(item, dict):
                raise ProductError(f"{dataset_id}: manifest {key} entry must be an object")
            add(item.get("path"), item.get("sha256"), item.get("size_bytes"), key)

    for key in ("dataset_record", "data_license", "source_license", "source_attribution",
                "source_fidelity_report", "clean_rebuild_report"):
        item = manifest.get(key)
        if isinstance(item, dict):
            add(item.get("path"), item.get("sha256"), item.get("bytes", item.get("size_bytes")), key,
                require_size=False)
    workflow_files = manifest.get("workflow_files", {})
    if "workflow_files" in manifest and not isinstance(workflow_files, dict):
        raise ProductError(f"{dataset_id}: manifest workflow_files must be an object")
    if workflow_files:
        for item in workflow_files.values():
            if not isinstance(item, dict):
                raise ProductError(f"{dataset_id}: manifest workflow_files entries must be objects")
            add(item.get("package_path"), item.get("sha256"), item.get("bytes", item.get("size_bytes")),
                "workflow_file", require_size=False)
    return [declarations_by_path[path] for path in sorted(declarations_by_path)]


def stage_product(root: Path, dataset_id: str, package_arg: Path) -> dict[str, Any]:
    record = load_records(root).get(dataset_id)
    if record is None:
        raise ProductError(f"{dataset_id}: no canonical publication.source_coop object")
    config = source_config(record)
    if not config.get("owner"):
        raise ProductError(f"{dataset_id}: staging requires a proposed Source Cooperative bucket owner")
    ready, binding, snapshot, error = _snapshot_status(root, record)
    if not ready or snapshot is None:
        raise ProductError(f"{dataset_id}: product is blocked/not prepared: {error or 'canonical binding failed'}")
    package = package_arg.expanduser()
    if package.is_symlink():
        raise ProductError(f"{dataset_id}: package root is a symlink")
    try:
        package = package.resolve(strict=True)
    except OSError as exc:
        raise ProductError(f"{dataset_id}: package path does not exist") from exc
    manifest_file = package / "manifest.json"
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ProductError(f"{dataset_id}: package root must contain a regular manifest.json")
    manifest = read_json(manifest_file)
    if not isinstance(manifest, dict) or manifest_identity(manifest) != (dataset_id, binding["release"]):
        raise ProductError(f"{dataset_id}: package manifest identity/release mismatch")
    inventory = package_inventory(package, dataset_id, config["owner"], config["product_id"], binding["release"])
    inventory_by_path = {item["path"]: item for item in inventory}
    manifest_sha = inventory_by_path.get("manifest.json", {}).get("sha256")
    if manifest_sha != binding["manifest_sha256"]:
        raise ProductError(f"{dataset_id}: package manifest hash differs from canonical manifest")
    declarations = manifest_declarations(manifest, dataset_id)
    for declaration in declarations:
        item = inventory_by_path.get(declaration["path"])
        if item is None:
            raise ProductError(f"{dataset_id}: declared manifest file absent from package inventory: {declaration['path']}")
        if (item["sha256"] != declaration["sha256"]
                or (declaration["size_bytes"] is not None and item["size_bytes"] != declaration["size_bytes"])):
            raise ProductError(f"{dataset_id}: package file changed after manifest verification: {declaration['path']}")
    for item in snapshot.get("files", []):
        if not isinstance(item, dict) or item.get("path") not in inventory_by_path:
            raise ProductError(f"{dataset_id}: catalog snapshot file absent from package inventory")
        actual = inventory_by_path[item["path"]]
        if actual["sha256"] != item.get("sha256") or actual["size_bytes"] != item.get("size_bytes"):
            raise ProductError(f"{dataset_id}: catalog snapshot file changed during staging: {item.get('path')}")

    package_binding = snapshot.get("_source_products_package_binding") or {"status": "inventory_only_unbound", "bound_files": {}}
    bound_files = package_binding.get("bound_files", {})
    for path, expected in bound_files.items():
        actual = inventory_by_path.get(path)
        if actual is None:
            raise ProductError(f"{dataset_id}: package binding references missing package file: {path}")
        if actual["sha256"] != expected["sha256"] or actual["size_bytes"] != expected["size_bytes"]:
            raise ProductError(f"{dataset_id}: package binding mismatch: {path}")
    receipt_pinned_paths: set[str] = set()
    receipt_path = (record.get("publication") or {}).get("release_receipt_path")
    if receipt_path:
        receipt = read_json(safe_repo_file(root, receipt_path, "release receipt"))
        for field in ("package_binding_sha256", "final_verification_sha256"):
            digest = receipt.get(field) if isinstance(receipt, dict) else None
            if isinstance(digest, str) and SHA256_RE.fullmatch(digest):
                matches = [item["path"] for item in inventory if item["sha256"] == digest]
                if len(matches) == 1:
                    receipt_pinned_paths.add(matches[0])
    manifest_paths = {item["path"] for item in declarations}
    snapshot_paths = {item["path"] for item in snapshot.get("files", []) if isinstance(item, dict)}
    for item in inventory:
        if item["path"] in bound_files:
            item["binding_status"] = "bound_by_package_receipt"
        elif item["path"] in receipt_pinned_paths:
            item["binding_status"] = "bound_by_canonical_receipt_digest"
        elif item["path"] in manifest_paths:
            item["binding_status"] = "bound_by_canonical_manifest"
        elif item["path"] in snapshot_paths:
            item["binding_status"] = "bound_by_catalog_snapshot"
        elif item["path"] == "manifest.json":
            item["binding_status"] = "bound_by_canonical_manifest_hash"
        else:
            item["binding_status"] = "inventory_only_unbound"

    keys = {item["object_key"] for item in inventory}
    supplements = []
    for supplement in config["supplements"]:
        source_path = safe_repo_file(root, supplement["path"], "supplement")
        size, actual_hash = inspect_file(source_path)
        if actual_hash != supplement["sha256"]:
            raise ProductError(f"{dataset_id}: supplement SHA-256 mismatch: {supplement['path']}")
        destination = safe_relpath(supplement["destination"], "supplement destination").as_posix()
        if not destination.startswith("metadata/"):
            raise ProductError(f"{dataset_id}: supplement destination must be under metadata/<version>/")
        key = f"{config['product_id']}/{destination}"
        if key in keys:
            raise ProductError(f"{dataset_id}: duplicate object key: {key}")
        keys.add(key)
        supplements.append({
            "object_key": key,
            "path": destination,
            "size_bytes": size,
            "sha256": actual_hash,
            "content_type": content_type(destination),
            "kind": "supplement",
            "binding_status": "bound_by_canonical_supplement_pin",
            **route_details(config["owner"], key),
            "source": {"kind": "repository", "path": supplement["path"]},
        })

    draft_path, readme_path, consumer_readme_path = generated_paths(dataset_id)
    draft, readme, consumer_readme = draft_for(root, record)
    if not (root / draft_path).is_file() or (root / draft_path).read_bytes() != canonical_json(draft):
        raise ProductError(f"{dataset_id}: generated product draft is missing/stale; run source_products.py write")
    if not (root / readme_path).is_file() or (root / readme_path).read_text(encoding="utf-8") != readme:
        raise ProductError(f"{dataset_id}: generated local review README is missing/stale; run source_products.py write")
    if not (root / consumer_readme_path).is_file() or (root / consumer_readme_path).read_text(encoding="utf-8") != consumer_readme:
        raise ProductError(f"{dataset_id}: generated consumer product README is missing/stale; run source_products.py write")

    readme_data = consumer_readme.encode("utf-8")
    metadata_key = f"{config['product_id']}/README.md"
    if metadata_key in keys:
        raise ProductError(f"{dataset_id}: duplicate object key: {metadata_key}")
    creation_ready = bool(draft["creation_ready"])
    blockers = list(draft["blockers"])
    immutable = inventory + supplements
    display_ref = draft.get("display_publication")
    return {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "release": binding["release"],
        "product_id": config["product_id"],
        "title": config["title"],
        "product_metadata": {
            "summary": config["summary"],
            "tags": config["tags"],
            "license_note": config["license_note"],
            "attribution": config["attribution"],
            "temporal_note": config["temporal_note"],
            "limitations": config["limitations"],
            "source_links": draft["source_links"],
            "related_dataset_links": draft["related_dataset_links"],
        },
        "owner": config.get("owner"),
        "owner_status": config.get("owner_status"),
        "publication_status": (record.get("publication") or {}).get("status"),
        "review_context": draft["review_context"],
        "manifest_sha256": manifest_sha,
        "display_publication": display_ref,
        "snapshot_sha256": binding["snapshot_sha256"],
        "source_proxy": {"uri": f"s3://{config['owner']}/{config['product_id']}", "status": "proposed"} if config.get("owner") else None,
        "bucket": config["owner"],
        "endpoint": "https://data.source.coop",
        "independent_maintainer_proposal": {
            "owner": config.get("owner"),
            "status": config.get("owner_status"),
            "relationship": "new Source Cooperative product proposal; immutable package metadata is unchanged",
        },
        "package_binding": {
            "status": package_binding.get("status"),
            "sha256": package_binding.get("sha256"),
            "bound_file_count": len(bound_files),
            "receipt_digest_bound_file_count": len(receipt_pinned_paths),
            "unbound_inventory_file_count": sum(item["binding_status"] == "inventory_only_unbound" for item in inventory),
        },
        "integrity_status": "local_package_metadata_verified",
        "public_validation_status": "not_checked_by_this_tool",
        "plan_status": "locally_hashed_exact_file_inventory",
        "creation_ready": creation_ready,
        "ready_for_review": True,
        "ready_for_creation": creation_ready,
        "ready_for_upload": False,
        "created": False,
        "hosted": False,
        "blockers": blockers,
        "immutable_file_count": len(immutable),
        "immutable_total_bytes": sum(item["size_bytes"] for item in immutable),
        "immutable_files": immutable,
        "mutable_metadata": [{
            "object_key": metadata_key,
            "size_bytes": len(readme_data),
            "sha256": sha256_bytes(readme_data),
            "content_type": "text/markdown",
            **route_details(config["owner"], metadata_key),
            "source": {"kind": "repository", "path": consumer_readme_path.as_posix()},
            "mutable": True,
            "binding_status": "canonical_generated_consumer_copy",
            "upload_allowed": False,
            "requires_finalized_publication_copy": False,
        }],
    }


def stage_display_package(
    root: Path, dataset_id: str, package_arg: Path, analytic_product: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate and inventory a versioned display package bound to its analytic release."""
    record = load_records(root).get(dataset_id)
    if record is None:
        raise ProductError(f"{dataset_id}: no canonical publication.source_coop object")
    publication = record.get("publication") or {}
    reference = _display_draft_reference(record)
    if reference is None:
        raise ProductError(f"{dataset_id}: no canonical publication.display binding")
    package = package_arg.expanduser()
    if package.is_symlink():
        raise ProductError(f"{dataset_id}: display package root is a symlink")
    try:
        package = package.resolve(strict=True)
    except OSError as exc:
        raise ProductError(f"{dataset_id}: display package path does not exist") from exc
    if not package.is_dir():
        raise ProductError(f"{dataset_id}: display package path is not a directory")
    manifest_path = package / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ProductError(f"{dataset_id}: display package requires a regular manifest.json")
    size, digest = inspect_file(manifest_path)
    if digest != reference["manifest_sha256"]:
        raise ProductError(f"{dataset_id}: display manifest SHA-256 differs from canonical pin")
    canonical_path = safe_repo_file(root, reference["manifest_path"], "canonical display manifest")
    if sha256_file(canonical_path) != digest:
        raise ProductError(f"{dataset_id}: tracked display manifest checksum differs from canonical pin")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ProductError(f"{dataset_id}: display manifest must be an object")
    expected_identity = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "display_release": reference["release"],
        "analytic_release": analytic_product["release"],
        "status": "prepared",
    }
    for field, expected in expected_identity.items():
        if manifest.get(field) != expected:
            raise ProductError(f"{dataset_id}: display manifest {field} mismatch: expected {expected!r}")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise ProductError(f"{dataset_id}: display manifest files must be a non-empty object")
    declarations: dict[str, tuple[int, str]] = {}
    for raw_path, declaration in raw_files.items():
        rel = safe_relpath(raw_path, "display file path").as_posix()
        if rel == "manifest.json" or rel in declarations:
            raise ProductError(f"{dataset_id}: invalid/duplicate display file declaration: {rel}")
        if not isinstance(declaration, dict):
            raise ProductError(f"{dataset_id}: display file declaration must be an object: {rel}")
        declared_size, declared_hash = declaration.get("size_bytes"), declaration.get("sha256")
        if (not isinstance(declared_size, int) or isinstance(declared_size, bool) or declared_size < 0
                or not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash)):
            raise ProductError(f"{dataset_id}: invalid display file hash/size: {rel}")
        declarations[rel] = (declared_size, declared_hash)

    actual_files: dict[str, tuple[int, str]] = {}
    def walk_error(error: OSError) -> None:
        raise ProductError(f"{dataset_id}: cannot enumerate display files ({type(error).__name__})")
    for current, dirs, names in os.walk(package, topdown=True, onerror=walk_error, followlinks=False):
        base = Path(current)
        for name in list(dirs):
            path = base / name
            rel = path.relative_to(package).as_posix()
            safe_relpath(rel, "display directory")
            if path.is_symlink():
                raise ProductError(f"{dataset_id}: display package symlink is not allowed: {rel}")
        for name in names:
            path = base / name
            rel = path.relative_to(package).as_posix()
            safe_relpath(rel, "display package path")
            if path.is_symlink() or not path.is_file():
                raise ProductError(f"{dataset_id}: display package contains unsafe file: {rel}")
            actual_files[rel] = inspect_file(path)
    if set(actual_files) != set(declarations) | {"manifest.json"}:
        raise ProductError(f"{dataset_id}: display package files do not match manifest inventory")
    for rel, (expected_size, expected_hash) in declarations.items():
        if actual_files[rel] != (expected_size, expected_hash):
            raise ProductError(f"{dataset_id}: display file hash/size mismatch: {rel}")

    analytic_files = {item["path"]: item for item in analytic_product["immutable_files"] if item.get("source", {}).get("kind") == "package"}
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ProductError(f"{dataset_id}: display manifest assets must be a non-empty array")
    seen_asset_ids: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ProductError(f"{dataset_id}: display asset must be an object")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id or asset_id in seen_asset_ids:
            raise ProductError(f"{dataset_id}: display asset IDs must be unique non-empty strings")
        seen_asset_ids.add(asset_id)
        for label in ("path", "style_path"):
            path = safe_relpath(asset.get(label), f"display asset {label}").as_posix()
            if path not in declarations:
                raise ProductError(f"{dataset_id}: display asset references undeclared file: {path}")
        asset_path = asset["path"]
        if not asset_path.lower().endswith(".pmtiles"):
            raise ProductError(f"{dataset_id}: display asset path must name a PMTiles file: {asset_path}")
        asset_size, asset_hash = asset.get("size_bytes"), asset.get("sha256")
        if (not isinstance(asset_size, int) or isinstance(asset_size, bool) or asset_size < 0
                or not isinstance(asset_hash, str) or not SHA256_RE.fullmatch(asset_hash)
                or declarations[asset_path] != (asset_size, asset_hash)):
            raise ProductError(f"{dataset_id}: display asset metadata disagrees with its file declaration: {asset_path}")
        source_layer = asset.get("source_layer")
        geometry_type = asset.get("geometry_type")
        id_field = asset.get("id_field")
        min_zoom, max_zoom = asset.get("min_zoom"), asset.get("max_zoom")
        if not isinstance(source_layer, str) or not source_layer:
            raise ProductError(f"{dataset_id}: display asset source_layer is required: {asset_id}")
        if geometry_type not in ("polygon", "line", "point"):
            raise ProductError(f"{dataset_id}: invalid display asset geometry_type: {asset_id}")
        if not isinstance(id_field, str) or not id_field:
            raise ProductError(f"{dataset_id}: display asset id_field is required: {asset_id}")
        id_encoding = asset.get("id_encoding", "mvt_feature_id_and_property")
        if id_encoding not in ("mvt_feature_id", "mvt_feature_id_and_property"):
            raise ProductError(f"{dataset_id}: invalid display asset id_encoding: {asset_id}")
        fields = asset.get("attribute_fields")
        if (not isinstance(fields, list) or any(not isinstance(field, str) or not field for field in fields)
                or len(fields) != len(set(fields))):
            raise ProductError(f"{dataset_id}: invalid display asset attribute_fields: {asset_id}")
        if id_encoding == "mvt_feature_id_and_property" and id_field not in fields:
            raise ProductError(f"{dataset_id}: display ID property is missing from attribute_fields: {asset_id}")
        if (not isinstance(min_zoom, int) or isinstance(min_zoom, bool) or not 0 <= min_zoom <= 30
                or not isinstance(max_zoom, int) or isinstance(max_zoom, bool) or not min_zoom <= max_zoom <= 30):
            raise ProductError(f"{dataset_id}: invalid display asset zoom range: {asset_id}")
        _validate_display_style(read_json(package / asset["style_path"]), asset["style_path"], asset, dataset_id)
        source_asset = asset.get("source_asset")
        if not isinstance(source_asset, dict):
            raise ProductError(f"{dataset_id}: display asset lacks source_asset binding: {asset_id}")
        source_path = safe_relpath(source_asset.get("path"), "display source asset path").as_posix()
        analytic = analytic_files.get(source_path)
        if (analytic is None or source_asset.get("sha256") != analytic["sha256"]
                or source_asset.get("size_bytes") != analytic["size_bytes"]):
            raise ProductError(f"{dataset_id}: display asset source_asset does not match analytical release: {source_path}")

    config = source_config(record)
    prefix = f"{config['product_id']}/display/{reference['release']}"
    results = []
    for rel in sorted(actual_files):
        file_size, file_hash = actual_files[rel]
        key = f"{prefix}/{rel}"
        results.append({
            "object_key": key, "path": rel, "size_bytes": file_size, "sha256": file_hash,
            "content_type": content_type(rel), "kind": "display_asset",
            "binding_status": "bound_by_canonical_display_manifest" if rel == "manifest.json" else "bound_by_display_manifest",
            **route_details(config["owner"], key),
            "source": {"kind": "display_package", "dataset_id": dataset_id, "path": rel},
        })
    return results


def parse_package(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("--package must be DATASET_ID=PATH")
    dataset_id, path = raw.split("=", 1)
    if not dataset_id or not path:
        raise argparse.ArgumentTypeError("--package must be DATASET_ID=PATH")
    return dataset_id, Path(path).expanduser()


def stage(root: Path, packages: list[tuple[str, Path]], output: Path,
          display_packages: list[tuple[str, Path]] | None = None) -> int:
    if os.path.lexists(output):
        print("refusing existing or dangling output path", file=sys.stderr)
        return 2
    try:
        output.mkdir(parents=True)
    except OSError as exc:
        print(f"cannot create new output directory: {type(exc).__name__}", file=sys.stderr)
        return 2
    try:
        if len({dataset_id for dataset_id, _ in packages}) != len(packages):
            raise ProductError("duplicate --package dataset mapping")
        if not packages:
            raise ProductError("stage requires at least one --package mapping")
        staged = []
        for dataset_id, package in packages:
            staged.append(stage_product(root, dataset_id, package))
        display_packages = display_packages or []
        if len({dataset_id for dataset_id, _ in display_packages}) != len(display_packages):
            raise ProductError("duplicate --display-package dataset mapping")
        staged_by_id = {product["dataset_id"]: product for product in staged}
        selected_display_ids = {dataset_id for dataset_id, _ in packages
                                if _display_draft_reference(load_records(root).get(dataset_id, {})) is not None}
        provided_display_ids = {dataset_id for dataset_id, _ in display_packages}
        missing_display_ids = selected_display_ids - provided_display_ids
        if missing_display_ids:
            raise ProductError(f"missing required --display-package for canonical display bindings: {sorted(missing_display_ids)}")
        unexpected_display_ids = provided_display_ids - selected_display_ids
        if unexpected_display_ids:
            raise ProductError(f"--display-package has no canonical display binding: {sorted(unexpected_display_ids)}")
        for dataset_id, display_package in display_packages:
            if dataset_id not in staged_by_id:
                raise ProductError(f"{dataset_id}: --display-package requires a matching --package")
            product = staged_by_id[dataset_id]
            product["immutable_files"].extend(stage_display_package(root, dataset_id, display_package, product))
            product["immutable_file_count"] = len(product["immutable_files"])
            product["immutable_total_bytes"] = sum(item["size_bytes"] for item in product["immutable_files"])
        seen: set[tuple[str, str]] = set()
        all_immutable = []
        for product in staged:
            for item in product["immutable_files"] + product["mutable_metadata"]:
                identity = (item["bucket"], item["object_key"])
                if identity in seen:
                    raise ProductError(f"duplicate object key across products: {identity[0]}/{identity[1]}")
                seen.add(identity)
            all_immutable.extend(product["immutable_files"])
        for product in staged:
            product_dir = output / "products" / product["dataset_id"]
            product_dir.mkdir(parents=True, exist_ok=True)
            (product_dir / "upload-plan.json").write_bytes(canonical_json(product))
        aggregate = {
            "schema_version": 1,
            "plan_type": "source_coop_immutable_exact_file_plan",
            "execution": "not_started",
            "products": [{
                "dataset_id": p["dataset_id"],
                "owner": p["owner"],
                "bucket": p["bucket"],
                "endpoint": p["endpoint"],
                "product_id": p["product_id"],
                "release": p["release"],
                **({"display_publication": p["display_publication"]} if p.get("display_publication") else {}),
                "source_proxy": p["source_proxy"],
            } for p in staged],
            "file_count": len(all_immutable),
            "total_bytes": sum(item["size_bytes"] for item in all_immutable),
            "files": sorted(all_immutable, key=lambda item: (item["bucket"], item["object_key"])),
            "creation_ready": all(p["creation_ready"] for p in staged),
            "ready_for_creation": all(p["ready_for_creation"] for p in staged),
            "ready_for_upload": False,
            "ready_for_review": True,
            "hosted": False,
            "created": False,
            "blockers": sorted({blocker for product in staged for blocker in product["blockers"]}),
            "mutable_metadata_count": sum(len(p["mutable_metadata"]) for p in staged),
            "mutable_metadata": [item for p in staged for item in p["mutable_metadata"]],
            "mutable_metadata_upload_allowed": False,
            "upload_blockers": sorted({blocker for product in staged for blocker in product["blockers"]}),
        }
        (output / "immutable-upload-plan.json").write_bytes(canonical_json(aggregate))
        (output / "stage-summary.json").write_bytes(canonical_json({
            "schema_version": 1,
            "status": "verified_exact_file_plan",
            "created": False,
            "hosted": False,
            "product_count": len(staged),
            "immutable_file_count": aggregate["file_count"],
            "immutable_total_bytes": aggregate["total_bytes"],
            "creation_ready": aggregate["creation_ready"],
            "ready_for_review": aggregate["ready_for_review"],
            "ready_for_creation": aggregate["ready_for_creation"],
            "ready_for_upload": aggregate["ready_for_upload"],
            "blockers": aggregate["blockers"],
        }))
        return 0
    except (OSError, ProductError, json.JSONDecodeError) as exc:
        failure = {"schema_version": 1, "status": "failed", "error_type": type(exc).__name__, "error": str(exc), "created": False, "hosted": False}
        (output / "failure.json").write_bytes(canonical_json(failure))
        print(f"staging failed; failure report written to new output directory ({type(exc).__name__})", file=sys.stderr)
        return 1


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="repository/worktree root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("write", help="write deterministic local product drafts")
    sub.add_parser("check", help="check local product drafts without writing")
    stage_parser = sub.add_parser("stage", help="verify packages and write an exact local upload plan")
    stage_parser.add_argument("--package", action="append", type=parse_package, required=True, metavar="ID=PATH")
    stage_parser.add_argument("--display-package", action="append", type=parse_package, default=[], metavar="ID=PATH",
                              help="stage a pinned display package alongside its analytical --package")
    stage_parser.add_argument("--output", type=Path, required=True, help="new output directory; existing paths are refused")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.command in ("write", "check"):
        errors = generate(root, write=args.command == "write")
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        return 0
    return stage(root, args.package, args.output.expanduser(), args.display_package)


if __name__ == "__main__":
    raise SystemExit(run())
