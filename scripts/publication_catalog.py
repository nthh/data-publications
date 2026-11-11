#!/usr/bin/env python3
"""Build and locally stage a deterministic, metadata-only publication catalog.

This tool does not upload files or perform hosting checks. A published record must
be accompanied by a checksum-bound snapshot and a prior hosting evidence report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from datetime import datetime
import posixpath
from urllib.parse import quote, urljoin, urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker

try:
    from catalog import load_records, record_paths
except ImportError:  # package-style import in tests
    from scripts.catalog import load_records, record_paths


MAX_METADATA_BYTES = 10 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
METADATA_SUFFIXES = {".json", ".md", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".css"}
PORTOLAN_SCHEMA = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"
WEB_MAP_LINKS_SCHEMA = "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"
PAGES_DESTINATION = "github-pages://nthh/data-publications/"
PAGES_PUBLIC_BASE = "https://nthh.github.io/data-publications/"
PASSING_CHECKS = ("anonymous_access", "range_requests", "cors", "asset_checksums",
                  "subset_query", "catalog_links", "browser_render")
ROOT_AGENTS = ("# Catalog guidance\n\nRead each collection README, license and source provenance before use. "
               "Use assets with the data role for analysis; visual derivatives serve display. "
               "Source fidelity, hosting checks and scientific validation have separate scopes.\n\n"
               "This metadata tree is generated from canonical dataset records and pinned release inputs. "
               "Contributors regenerate it with scripts/publication_catalog.py rather than editing it by hand.\n")


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: str, *, label: str = "path") -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Invalid {label}: {value!r}")
    if value.startswith("/") or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"Unsafe {label}: {value}")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise ValueError(f"Unsafe {label}: {value}")
    return p


def inside(root: Path, relative: str | PurePosixPath, *, must_exist: bool = True) -> Path:
    if root.is_symlink():
        raise ValueError(f"Symlink root is not allowed: {root}")
    rel = safe_relative(str(relative))
    target = root.joinpath(*rel.parts)
    # Reject symlinks anywhere, including links that resolve back inside.
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"Symlink is not allowed: {cursor}")
    resolved_root = root.resolve()
    resolved = target.resolve(strict=must_exist)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"Path escapes root: {relative}")
    return target


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError(f"Missing, unsafe or oversized JSON metadata: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def unique_yaml(path: Path) -> dict:
    """Reject duplicate keys instead of silently selecting the final value."""
    class UniqueLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise ValueError(f"Duplicate YAML key {key!r}: {path}")
                seen.add(key)
            return super().construct_mapping(node, deep=deep)
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML metadata: {path}: {exc}") from exc


def browser_template_placeholder(template: str) -> str:
    """Return the one supported browser template placeholder."""
    match = re.fullmatch(r"[^{}]*\{(catalog_url|catalog_host_path)\}[^{}]*", template)
    if not match or not template.startswith("https://") or any(c.isspace() for c in template):
        raise ValueError(
            "navigation.browser_url_template must be an HTTPS URL with exactly one "
            "{catalog_url} or {catalog_host_path} placeholder"
        )
    return match.group(1)


def portolan_browser_host_path(catalog_url: str) -> str:
    """Return the safe host/path form used by Portolan Browser's /external/ route."""
    parsed = urlsplit(catalog_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(c.isspace() for c in catalog_url)):
        raise ValueError("Portolan Browser catalog URL must be a clean absolute HTTPS URL")
    if re.search(r"%(?![0-9A-Fa-f]{2})", parsed.path):
        raise ValueError("Portolan Browser catalog URL has an invalid percent escape in its path")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Portolan Browser catalog URL has an invalid port") from exc
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None:
        host += f":{port}"
    # Keep path separators and already-valid escapes. Encode raw path characters so
    # '?', '#', and other route syntax cannot escape the path in the browser URL.
    return host + quote(parsed.path, safe="/-._~%")


def load_config(root: Path) -> dict:
    path = root / "catalog.publish.yaml"
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing or unsafe catalog.publish.yaml")
    config = unique_yaml(path)
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("catalog.publish.yaml must have schema_version: 1")
    for section in ("catalog", "navigation", "publish"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"catalog.publish.yaml requires {section} object")
    for field in ("id", "title", "description"):
        if not isinstance(config["catalog"].get(field), str) or not config["catalog"][field].strip():
            raise ValueError(f"catalog.{field} requires nonempty text")
    for field in ("repository_url", "issues_url", "hosting_url", "browser_url_template"):
        value = config["navigation"].get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"navigation.{field} must be text or null")
    for field in ("destination", "public_base", "region"):
        value = config["publish"].get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"publish.{field} must be nonempty text or null")
    for field in ("repository_url", "issues_url", "hosting_url"):
        if config["navigation"].get(field):
            https_url(config["navigation"][field], f"navigation.{field}")
    template = config["navigation"].get("browser_url_template")
    if template:
        browser_template_placeholder(template)
    if config["publish"].get("public_base"):
        base = https_url(config["publish"]["public_base"], "publish.public_base")
        if not base.endswith("/"):
            raise ValueError("publish.public_base must end with /")
    destination = config["publish"].get("destination")
    if destination == PAGES_DESTINATION:
        if config["publish"].get("public_base") != PAGES_PUBLIC_BASE:
            raise ValueError(f"publish.public_base must be {PAGES_PUBLIC_BASE} for GitHub Pages")
        if config["publish"].get("region") is not None:
            raise ValueError("publish.region must be null for GitHub Pages")
    elif destination and not re.fullmatch(r"s3://[A-Za-z0-9._-]+(?:/[A-Za-z0-9._/-]*)?/", destination):
        raise ValueError("publish.destination must be an s3://bucket/prefix/ URI or the exact GitHub Pages destination")
    return config


def validated_records(root: Path) -> dict:
    for path in record_paths(root):
        unique_yaml(inside(root, path.relative_to(root).as_posix()))
    records = load_records(root)
    schema = read_json(inside(root, "schemas/dataset.schema.json"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for dataset_id, record in records.items():
        try:
            validator.validate(record)
        except Exception as exc:
            detail = getattr(exc, "message", str(exc))
            raise ValueError(f"Invalid canonical dataset record {dataset_id}: {detail}") from exc
    return records


def https_url(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an HTTPS URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(c.isspace() for c in value)):
        raise ValueError(f"{label} must be an absolute HTTPS URL: {value!r}")
    return value


def https_reference(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an HTTPS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
        raise ValueError(f"{label} must be an HTTPS URL: {value!r}")
    return value


def local_url(value: str) -> bool:
    p = urlsplit(value)
    return not p.scheme and not p.netloc and not value.startswith("#")


def path_from_href(href: str, *, label: str = "href") -> str:
    if not isinstance(href, str) or not href or "\\" in href:
        raise ValueError(f"Invalid {label}: {href!r}")
    p = urlsplit(href)
    if p.scheme or p.netloc or p.query or p.fragment or p.path.startswith("/"):
        raise ValueError(f"Expected local relative {label}: {href}")
    path = p.path.removeprefix("./")
    return str(safe_relative(path, label=label))


def package_path(href: str, base_path: str, *, label: str = "href") -> str:
    """Resolve a local document reference, retaining the package root boundary."""
    if not isinstance(href, str) or not href or "\\" in href:
        raise ValueError(f"Invalid {label}: {href!r}")
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith("/"):
        raise ValueError(f"Unsafe local {label}: {href}")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base_path), parsed.path))
    return str(safe_relative(path, label=label))


def metadata_bytes(rel: str, data: bytes) -> None:
    if PurePosixPath(rel).suffix.lower() not in METADATA_SUFFIXES:
        raise ValueError(f"Refusing non-metadata file: {rel}")
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError(f"Metadata file exceeds 10 MB limit: {rel}")
    suffix = PurePosixPath(rel).suffix.lower()
    if suffix == ".json":
        try:
            json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON metadata {rel}: {exc}") from exc
    elif suffix in (".md", ".css", ".svg"):
        if b"\x00" in data or data.startswith((b"PAR1", b"PMTiles", b"PK\x03\x04", b"\x89PNG")):
            raise ValueError(f"Disguised bulk data in metadata file: {rel}")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Non-text metadata file: {rel}") from exc
    elif suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Invalid PNG metadata file: {rel}")
    elif suffix in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError(f"Invalid JPEG metadata file: {rel}")
    elif suffix == ".webp" and not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        raise ValueError(f"Invalid WebP metadata file: {rel}")


def _tracked_provenance(root: Path, dataset_id: str, record: dict) -> tuple[dict, dict, dict[str, dict], str | None]:
    pub = record.get("publication") or {}
    release = pub.get("release") or (record.get("build") or {}).get("release_id")
    manifest_path = pub.get("manifest_path")
    expected = pub.get("manifest_sha256")
    if not manifest_path or not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise ValueError(f"{dataset_id} lacks pinned publication manifest path/hash")
    manifest_file = inside(root, manifest_path)
    manifest_data = manifest_file.read_bytes()
    if sha256_bytes(manifest_data) != expected:
        raise ValueError(f"Tracked package manifest SHA-256 mismatch: {dataset_id}")
    manifest = read_json(manifest_file)
    if manifest.get("dataset_id", manifest.get("dataset")) != dataset_id or manifest.get("release_id", manifest.get("release")) != release:
        raise ValueError(f"Tracked package manifest identity/release mismatch: {dataset_id}")
    receipt_path = pub.get("release_receipt_path")
    if not receipt_path:
        raise ValueError(f"{dataset_id} lacks tracked release receipt")
    receipt = read_json(inside(root, receipt_path))
    if receipt.get("manifest_sha256") != expected:
        raise ValueError(f"Tracked release receipt manifest mismatch: {dataset_id}")
    if receipt.get("dataset_id", dataset_id) != dataset_id or receipt.get("release_id", release) != release:
        raise ValueError(f"Tracked release receipt identity mismatch: {dataset_id}")
    assets: dict[str, dict] = {}
    raw = manifest.get("assets")
    if isinstance(raw, dict):
        assets.update(raw)
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or not item.get("href"):
                raise ValueError(f"Malformed manifest asset for {dataset_id}")
            assets[item["href"]] = item
            if item.get("field_dictionary"):
                assets[item["field_dictionary"]] = {"sha256": item.get("field_dictionary_sha256")}
    else:
        raise ValueError(f"Malformed manifest assets for {dataset_id}")
    for key in ("supporting_files", "display_derivatives"):
        for item in manifest.get(key, []):
            if not isinstance(item, dict) or not item.get("path"):
                raise ValueError(f"Malformed manifest {key} for {dataset_id}")
            assets[item["path"]] = item
    binding_hash = receipt.get("package_binding_sha256")
    if binding_hash is not None and (not isinstance(binding_hash, str) or not SHA256_RE.fullmatch(binding_hash)):
        raise ValueError(f"Invalid package binding hash for {dataset_id}")
    return manifest, receipt, assets, binding_hash


def _expected_file(rel: str, assets: dict[str, dict], binding: dict | None, dataset_id: str) -> dict:
    info = assets.get(rel)
    if info is None and binding is not None:
        info = (binding.get("bound_files") or {}).get(rel)
    if not isinstance(info, dict) or not isinstance(info.get("sha256"), str) or not SHA256_RE.fullmatch(info["sha256"]):
        raise ValueError(f"Metadata/asset is not bound to immutable package: {dataset_id}/{rel}")
    return info


def _check_bound_file(rel: str, data: bytes, assets: dict[str, dict], binding: dict | None, dataset_id: str) -> None:
    info = _expected_file(rel, assets, binding, dataset_id)
    if info["sha256"] != sha256_bytes(data) or (info.get("size_bytes") is not None and info["size_bytes"] != len(data)):
        raise ValueError(f"Immutable package file checksum/size mismatch: {dataset_id}/{rel}")


def _display_package(root: Path, dataset_id: str, record: dict) -> dict | None:
    """Load only the pinned display manifest and its small style documents."""
    publication = record.get("publication") or {}
    pin = publication.get("display")
    if pin is None:
        return None
    if not isinstance(pin, dict):
        raise ValueError(f"{dataset_id} publication.display must be an object")
    display_release = pin.get("release")
    manifest_path = pin.get("manifest_path")
    manifest_hash = pin.get("manifest_sha256")
    expected_path = f"datasets/{dataset_id}/display/{display_release}/manifest.json"
    if (not isinstance(display_release, str) or not isinstance(manifest_path, str)
            or manifest_path != expected_path or not isinstance(manifest_hash, str)
            or not SHA256_RE.fullmatch(manifest_hash)):
        raise ValueError(f"{dataset_id} has an invalid publication.display manifest pin")
    manifest_file = inside(root, manifest_path)
    if manifest_file.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError(f"Display manifest exceeds 10 MB limit: {dataset_id}")
    manifest_data = manifest_file.read_bytes()
    if sha256_bytes(manifest_data) != manifest_hash:
        raise ValueError(f"Display manifest SHA-256 mismatch: {dataset_id}")
    manifest = read_json(manifest_file)
    analytic_release = publication.get("release") or (record.get("build") or {}).get("release_id")
    if (manifest.get("schema_version") != 1 or manifest.get("dataset_id") != dataset_id
            or manifest.get("display_release") != display_release
            or manifest.get("analytic_release") != analytic_release or manifest.get("status") != "prepared"):
        raise ValueError(f"Display manifest identity/release mismatch: {dataset_id}")
    files = manifest.get("files")
    assets = manifest.get("assets")
    if not isinstance(files, dict) or not isinstance(assets, list) or not assets:
        raise ValueError(f"Display manifest has no valid file/asset inventory: {dataset_id}")

    def file_info(rel: str, label: str) -> dict:
        rel = str(safe_relative(rel, label=label))
        info = files.get(rel)
        if (not isinstance(info, dict) or not isinstance(info.get("sha256"), str)
                or not SHA256_RE.fullmatch(info["sha256"])
                or not isinstance(info.get("size_bytes"), int) or info["size_bytes"] < 0):
            raise ValueError(f"Display manifest has invalid file binding: {dataset_id}/{rel}")
        return info

    displayed = []
    seen_ids: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError(f"Malformed display asset: {dataset_id}")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id or asset_id in seen_ids:
            raise ValueError(f"Invalid or duplicate display asset ID: {dataset_id}")
        seen_ids.add(asset_id)
        asset_path = str(safe_relative(asset.get("path", ""), label="display asset path"))
        style_path = str(safe_relative(asset.get("style_path", ""), label="display style path"))
        asset_info = file_info(asset_path, "display asset path")
        if (asset_info["sha256"] != asset.get("sha256")
                or asset_info["size_bytes"] != asset.get("size_bytes")):
            raise ValueError(f"Display asset metadata disagrees with manifest file inventory: {dataset_id}/{asset_path}")
        style_info = file_info(style_path, "display style path")
        style_file = inside(manifest_file.parent, style_path)
        if style_file.stat().st_size > MAX_METADATA_BYTES:
            raise ValueError(f"Display style exceeds 10 MB limit: {dataset_id}/{style_path}")
        style_data = style_file.read_bytes()
        if (len(style_data) != style_info["size_bytes"] or sha256_bytes(style_data) != style_info["sha256"]
                or len(style_data) > MAX_METADATA_BYTES):
            raise ValueError(f"Display style checksum/size mismatch: {dataset_id}/{style_path}")
        try:
            style = json.loads(style_data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid display style JSON: {dataset_id}/{style_path}") from exc
        if not isinstance(style, dict):
            raise ValueError(f"Display style must be a JSON object: {dataset_id}/{style_path}")
        source_layer = asset.get("source_layer")
        layers = [source_layer] if isinstance(source_layer, str) and source_layer else []
        overview = asset.get("overview")
        if isinstance(overview, dict) and isinstance(overview.get("source_layer"), str):
            layers.append(overview["source_layer"])
        layers = list(dict.fromkeys(layers))
        if not layers:
            raise ValueError(f"Display asset has no PMTiles layer declaration: {dataset_id}/{asset_id}")
        displayed.append({"id": asset_id, "title": asset.get("title") or asset_id,
                          "path": asset_path, "style_path": style_path,
                          "sha256": asset["sha256"], "size_bytes": asset["size_bytes"],
                          "layers": layers, "style": style})
    return {"release": display_release, "manifest_sha256": manifest_hash, "assets": displayed}


def _display_hosting_base(root: Path, dataset_id: str, record: dict) -> str | None:
    """Require published display metadata to have a manifest-bound host report."""
    publication = record.get("publication") or {}
    display = publication.get("display")
    if display is None or publication.get("status") != "published":
        return None
    base = display.get("package_base_url")
    https_url(base, f"{dataset_id} display package_base_url")
    if not base.endswith("/") or urlsplit(base).query or urlsplit(base).fragment:
        raise ValueError(f"{dataset_id} display package_base_url must be an HTTPS prefix ending in /")
    report_path = display.get("hosting_report_path")
    report_hash = display.get("hosting_report_sha256")
    if not report_path or not isinstance(report_hash, str) or not SHA256_RE.fullmatch(report_hash):
        raise ValueError(f"Published dataset {dataset_id} requires checksum-bound display hosting evidence")
    report_file = inside(root, report_path)
    report_data = report_file.read_bytes()
    if sha256_bytes(report_data) != report_hash:
        raise ValueError(f"Display hosting report SHA-256 mismatch: {dataset_id}")
    report = read_json(report_file)
    if (report.get("schema_version") != 1 or report.get("dataset_id") != dataset_id
            or report.get("display_release") != display.get("release")
            or report.get("display_manifest_sha256") != display.get("manifest_sha256")
            or report.get("display_package_base_url") != base or report.get("status") != "passed"):
        raise ValueError(f"Display hosting report identity/status mismatch: {dataset_id}")
    checked_at = report.get("checked_at")
    try:
        parsed_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError("timezone required")
    except (AttributeError, ValueError):
        raise ValueError(f"Display hosting report has invalid checked_at: {dataset_id}")
    checks = report.get("checks") or {}
    if any(checks.get(name) != "passed" for name in PASSING_CHECKS):
        raise ValueError(f"Display hosting report has missing/failed required checks: {dataset_id}")
    return base


def _set_public_host(collection: dict, dataset_id: str, record: dict) -> None:
    publication = record.get("publication") or {}
    source_coop = publication.get("source_coop")
    if not isinstance(source_coop, dict):
        raise ValueError(f"Published dataset {dataset_id} lacks canonical publication.source_coop")
    owner = source_coop.get("owner")
    product = source_coop.get("product_id")
    if (source_coop.get("owner_status") != "confirmed" or not isinstance(owner, str)
            or not owner or not isinstance(product, str) or not product):
        raise ValueError(f"Published dataset {dataset_id} lacks a confirmed Source Cooperative maintainer")
    host_url = f"https://source.coop/{owner}/{product}"
    https_url(host_url, f"{dataset_id} Source Cooperative host URL")
    providers = collection.setdefault("providers", [])
    if not isinstance(providers, list):
        raise ValueError(f"Malformed Collection providers: {dataset_id}")
    correction = (publication.get("catalog") or {}).get("processor_correction")
    if correction:
        if correction["to"] != owner or correction["from"].casefold() == owner.casefold():
            raise ValueError(f"Processor correction must name the confirmed maintainer: {dataset_id}")
        if any(isinstance(provider, dict) and isinstance(provider.get("name"), str)
               and provider["name"].casefold() == owner.casefold() for provider in providers):
            raise ValueError(f"Processor correction conflicts with an existing maintainer provider: {dataset_id}")
        matches = [provider for provider in providers
                   if isinstance(provider, dict) and provider.get("name") == correction["from"]]
        if (len(matches) != 1 or "processor" not in matches[0].get("roles", [])
                or set(matches[0]["roles"]) - {"host", "processor"}):
            raise ValueError(f"Processor correction must match exactly one converter-only provider: {dataset_id}")
        # Copy, never mutate the immutable source provider or its producer/licensor credits.
        providers = [dict(provider, name=owner) if provider is matches[0] else provider
                     for provider in providers]
    updated = []
    owner_found = False
    for provider in providers:
        if not isinstance(provider, dict):
            raise ValueError(f"Malformed provider: {dataset_id}")
        roles = provider.get("roles", [])
        if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
            raise ValueError(f"Malformed provider roles: {dataset_id}")
        provider = dict(provider)
        remaining = [role for role in roles if role != "host"]
        is_owner = isinstance(provider.get("name"), str) and provider["name"].casefold() == owner.casefold()
        if is_owner and not owner_found:
            provider.update({"name": owner, "roles": list(dict.fromkeys([*remaining, "host"])), "url": host_url})
            if "processor" in remaining and "producer" not in remaining:
                provider["description"] = "Independent data processing and hosting on Source Cooperative."
            updated.append(provider)
            owner_found = True
        elif remaining:
            provider["roles"] = remaining
            updated.append(provider)
    if not owner_found:
        updated.append({"name": owner, "roles": ["host"], "url": host_url})
    collection["providers"] = updated



def _catalog_thumbnail(root: Path, dataset_id: str, record: dict) -> tuple[dict, bytes] | None:
    spec = ((record.get("publication") or {}).get("catalog") or {}).get("thumbnail")
    if spec is None:
        return None
    path = inside(root, spec["path"])
    if path.suffix != ".png" or path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError(f"Catalog thumbnail must be a PNG under 10 MB: {dataset_id}")
    data = path.read_bytes()
    metadata_bytes(spec["path"], data)
    if sha256_bytes(data) != spec["sha256"]:
        raise ValueError(f"Catalog thumbnail SHA-256 mismatch: {dataset_id}")
    return spec, data


def _set_catalog_thumbnail(collection: dict, thumbnail: tuple[dict, bytes], dataset_id: str, put) -> None:
    spec, data = thumbnail
    href = "presentation/thumbnail.png"
    assets = collection.setdefault("assets", {})
    if "thumbnail" in assets and "thumbnail" not in assets["thumbnail"].get("roles", []):
        raise ValueError(f"Catalog thumbnail conflicts with a non-thumbnail asset: {dataset_id}")
    collection["assets"] = {key: asset for key, asset in assets.items()
                            if "thumbnail" not in asset.get("roles", [])}
    collection["assets"]["thumbnail"] = {
        "href": href, "type": "image/png", "roles": ["thumbnail"], "title": spec["title"],
        "file:size": len(data), "file:checksum": "1220" + sha256_bytes(data),
    }
    collection["links"] = [link for link in collection["links"] if link.get("rel") != "thumbnail"]
    collection["links"].append({"rel": "thumbnail", "href": href, "type": "image/png", "title": spec["title"]})
    extensions = collection.setdefault("stac_extensions", [])
    file_schema = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
    if file_schema not in extensions:
        extensions.append(file_schema)
    put(f"{dataset_id}/{href}", data)


def _add_display_publication(collection: dict, display: dict, display_base: str,
                             dataset_id: str, put) -> None:
    assets = collection.setdefault("assets", {})
    links = collection.setdefault("links", [])
    extensions = collection.setdefault("stac_extensions", [])
    if not isinstance(assets, dict) or not isinstance(links, list) or not isinstance(extensions, list):
        raise ValueError(f"Malformed Collection assets/links/extensions: {dataset_id}")
    if WEB_MAP_LINKS_SCHEMA not in extensions:
        extensions.append(WEB_MAP_LINKS_SCHEMA)
    for index, item in enumerate(display["assets"]):
        pmtiles_href = urljoin(display_base, quote(item["path"], safe="/-._~"))
        pmtiles_asset_id = f"display_tiles_{item['id']}"
        style_asset_id = f"display_style_{item['id']}"
        if pmtiles_asset_id in assets or style_asset_id in assets:
            raise ValueError(f"Display asset ID conflicts with Collection asset: {dataset_id}/{item['id']}")
        assets[pmtiles_asset_id] = {
            "href": pmtiles_href,
            "type": "application/vnd.pmtiles",
            "roles": ["visual"],
            "title": item["title"],
            "file:size": item["size_bytes"],
            "file:checksum": "1220" + item["sha256"],
        }
        links.append({"rel": "pmtiles", "href": pmtiles_href, "type": "application/vnd.pmtiles",
                      "title": item["title"], "pmtiles:layers": item["layers"]})

        style_path = item["style_path"]
        rewritten = _rewrite_style(item["style"], style_path, display_base, "collection.json")
        style_data = canonical_json(rewritten)
        staged_style_path = f"display/{display['release']}/{style_path}"
        put(f"{dataset_id}/{staged_style_path}", style_data)
        style_roles = ["style"] + (["default"] if index == 0 else [])
        assets[style_asset_id] = {
            "href": staged_style_path,
            "type": "application/vnd.mapbox.style+json",
            "roles": style_roles,
            "title": item["title"] + " display style",
            "file:size": len(style_data),
            "file:checksum": "1220" + sha256_bytes(style_data),
        }
        links.append({"rel": "style", "href": staged_style_path,
                      "type": "application/vnd.mapbox.style+json", "title": item["title"] + " display style"})


def _binding_from_package(package: Path, expected_hash: str | None, manifest_hash: str) -> tuple[dict | None, bytes | None]:
    if not expected_hash:
        return None, None
    path = inside(package, "evidence/package-binding.json")
    data = path.read_bytes()
    if sha256_bytes(data) != expected_hash:
        raise ValueError("Package binding SHA-256 does not match tracked receipt")
    binding = read_json(path)
    if binding.get("manifest_sha256") != manifest_hash:
        raise ValueError("Package binding does not bind tracked manifest")
    return binding, data


def _check_collection_assets(collection: dict, collection_path: str, assets: dict[str, dict],
                             binding: dict | None, dataset_id: str) -> None:
    if not isinstance(collection.get("assets", {}), dict):
        raise ValueError(f"Malformed Collection assets: {dataset_id}")
    for asset_id, asset in collection.get("assets", {}).items():
        if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
            raise ValueError(f"Malformed Collection asset: {dataset_id}/{asset_id}")
        href = asset["href"]
        if local_url(href):
            rel = package_path(href, collection_path, label=f"asset {asset_id} href")
            info = _expected_file(rel, assets, binding, dataset_id)
            expected_size = info.get("size_bytes")
            actual_size = asset.get("file:size")
            if (not isinstance(actual_size, int) or actual_size < 0
                    or (expected_size is not None and actual_size != expected_size)
                    or asset.get("file:checksum") != "1220" + info["sha256"]):
                raise ValueError(f"Collection asset size/checksum does not match immutable manifest: {dataset_id}/{asset_id}")
        else:
            https_reference(href, f"{dataset_id}/{asset_id} asset href")


def asset_base(package_base: str, collection_path: str) -> str:
    prefix = package_base.rstrip("/") + "/"
    return urljoin(prefix, quote(collection_path, safe="/-._~"))


def _find_collection(package: Path) -> str:
    direct = package / "collection.json"
    if direct.is_file():
        return "collection.json"
    catalog_path = package / "catalog.json"
    if not catalog_path.is_file():
        raise ValueError("Package must contain collection.json or catalog.json")
    catalog = read_json(catalog_path)
    children = [l for l in catalog.get("links", []) if l.get("rel") == "child"]
    if len(children) != 1:
        raise ValueError("Package catalog must link exactly one child collection")
    return path_from_href(children[0].get("href", ""), label="collection href")


def export_metadata(dataset_id: str, package: Path, output: Path, root: Path) -> dict:
    records = validated_records(root)
    if dataset_id not in records:
        raise ValueError(f"Unknown dataset ID: {dataset_id}")
    record = records[dataset_id]
    publication = record.get("publication") or {}
    expected_release = publication.get("release") or (record.get("build") or {}).get("release_id")
    _, _, bound_assets, binding_hash = _tracked_provenance(root, dataset_id, record)
    if package.is_symlink():
        raise ValueError("Package root must not be a symlink")
    package = package.resolve(strict=True)
    if not package.is_dir():
        raise ValueError("Package root must be a directory")
    try:
        relative_output = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Snapshot output must be inside repository root") from exc
    output = inside(root, PurePosixPath(relative_output.as_posix()), must_exist=False)
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}")
    resolved_output = output.resolve(strict=False)
    if package == resolved_output or package in resolved_output.parents:
        raise ValueError("Snapshot output must not be inside immutable package")
    if output == root / "catalog" or root / "catalog" in output.parents:
        raise ValueError("Snapshot output must not be inside generated catalog")
    manifest_path = package / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Package root must contain a regular manifest.json")
    manifest_data = manifest_path.read_bytes()
    manifest = read_json(manifest_path)
    if manifest.get("dataset_id", manifest.get("dataset")) != dataset_id:
        raise ValueError("Package manifest dataset ID does not match canonical record")
    manifest_release = manifest.get("release_id", manifest.get("release"))
    if manifest_release != expected_release:
        raise ValueError(f"Package release mismatch: expected {expected_release!r}, got {manifest_release!r}")
    expected_manifest_hash = publication.get("manifest_sha256")
    if not isinstance(expected_manifest_hash, str) or not SHA256_RE.fullmatch(expected_manifest_hash):
        raise ValueError(f"Canonical record {dataset_id} must bind publication.manifest_sha256 before export")
    if expected_manifest_hash != sha256_bytes(manifest_data):
        raise ValueError("Package manifest SHA-256 does not match canonical publication.manifest_sha256")
    binding, binding_data = _binding_from_package(package, binding_hash, expected_manifest_hash)
    collection_path = _find_collection(package)
    package_catalog = package / "catalog.json"
    if package_catalog.is_file():
        _check_bound_file("catalog.json", inside(package, "catalog.json").read_bytes(),
                          bound_assets, binding, dataset_id)
    collection_file = inside(package, collection_path)
    collection = read_json(collection_file)
    if collection.get("type") != "Collection" or collection.get("id") != dataset_id:
        raise ValueError("Package collection type/id does not match canonical dataset")
    if collection.get("items") or any(link.get("rel") in ("child", "item") for link in collection.get("links", [])):
        raise ValueError("Nested collections and items are not supported")
    prepared: dict[str, bytes] = {}

    def collect(rel: str) -> None:
        rel = str(safe_relative(rel, label="metadata href"))
        if rel in prepared:
            return
        source = inside(package, rel)
        if not source.is_file():
            raise ValueError(f"Metadata file is missing: {rel}")
        if source.stat().st_size > MAX_METADATA_BYTES:
            raise ValueError(f"Metadata file exceeds 10 MB limit: {rel}")
        data = source.read_bytes()
        metadata_bytes(rel, data)
        _check_bound_file(rel, data, bound_assets, binding, dataset_id)
        prepared[rel] = data

    collect(collection_path)
    for link in collection.get("links", []):
        rel = link.get("rel")
        href = link.get("href")
        if rel in ("root", "parent"):
            continue
        if rel in ("describedby", "agents", "style", "stylesheet", "thumbnail") and isinstance(href, str) and local_url(href):
            collect(package_path(href, collection_path, label=f"{rel} href"))
    # Also collect local style/thumbnail assets when represented as collection assets.
    for asset in collection.get("assets", {}).values():
        roles = asset.get("roles", []) if isinstance(asset, dict) else []
        href = asset.get("href") if isinstance(asset, dict) else None
        if any(role in ("style", "thumbnail") for role in roles) and isinstance(href, str) and local_url(href):
            collect(package_path(href, collection_path, label="style/thumbnail href"))
    _check_collection_assets(collection, collection_path, bound_assets, binding, dataset_id)
    output.mkdir(parents=True)
    for rel, data in sorted(prepared.items()):
        dest = output / "files" / Path(*PurePosixPath(rel).parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    if binding_data is not None:
        proof = output / "proof/package-binding.json"
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_bytes(binding_data)
    snapshot = {"schema_version": 1, "dataset_id": dataset_id, "release": expected_release,
                "package_manifest_sha256": sha256_bytes(manifest_data), "collection_path": collection_path,
                "files": [{"path": k, "sha256": sha256_bytes(prepared[k]), "size_bytes": len(prepared[k])} for k in sorted(prepared)]}
    if binding_data is not None:
        snapshot["binding_proof"] = {"path": "proof/package-binding.json", "sha256": sha256_bytes(binding_data)}
    (output / "snapshot.json").write_bytes(canonical_json(snapshot))
    return snapshot


def _load_publication_snapshot(root: Path, dataset_id: str, record: dict) -> tuple[dict, Path]:
    pub = record.get("publication") or {}
    contract = pub.get("catalog")
    status = pub.get("status", "candidate")
    if not isinstance(contract, dict):
        if status == "published":
            raise ValueError(f"Published dataset {dataset_id} lacks publication.catalog metadata")
        return {}, Path()
    snapshot_rel = contract.get("snapshot_path")
    if not snapshot_rel:
        raise ValueError(f"Configured publication.catalog metadata for {dataset_id} lacks snapshot_path")
    snapshot_path = inside(root, snapshot_rel)
    snapshot_data = snapshot_path.read_bytes()
    expected = contract.get("snapshot_sha256")
    if not isinstance(expected, str) or expected != sha256_bytes(snapshot_data):
        raise ValueError(f"Snapshot SHA-256 mismatch for {dataset_id}")
    snapshot = read_json(snapshot_path)
    release = pub.get("release") or (record.get("build") or {}).get("release_id")
    if snapshot.get("schema_version") != 1 or snapshot.get("dataset_id") != dataset_id or snapshot.get("release") != release:
        raise ValueError(f"Snapshot identity/release mismatch for {dataset_id}")
    manifest_sha = pub.get("manifest_sha256")
    if not isinstance(manifest_sha, str) or not SHA256_RE.fullmatch(manifest_sha):
        raise ValueError(f"Canonical record {dataset_id} lacks publication.manifest_sha256")
    if snapshot.get("package_manifest_sha256") != manifest_sha:
        raise ValueError(f"Snapshot package-manifest hash mismatch for {dataset_id}")
    tracked_manifest, _, bound_assets, binding_hash = _tracked_provenance(root, dataset_id, record)
    binding = None
    if binding_hash:
        proof = snapshot.get("binding_proof")
        if not isinstance(proof, dict) or proof.get("path") != "proof/package-binding.json" or proof.get("sha256") != binding_hash:
            raise ValueError(f"Snapshot lacks tracked package binding proof: {dataset_id}")
        proof_path = inside(snapshot_path.parent, proof["path"])
        if sha256_bytes(proof_path.read_bytes()) != binding_hash:
            raise ValueError(f"Snapshot package binding proof checksum mismatch: {dataset_id}")
        binding = read_json(proof_path)
        if binding.get("manifest_sha256") != manifest_sha:
            raise ValueError(f"Snapshot binding proof manifest mismatch: {dataset_id}")
    elif snapshot.get("binding_proof"):
        raise ValueError(f"Unexpected snapshot binding proof: {dataset_id}")
    files_root = snapshot_path.parent / "files"
    files = snapshot.get("files")
    if not isinstance(files, list):
        raise ValueError(f"Snapshot files must be a list for {dataset_id}")
    seen = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError(f"Malformed snapshot file entry for {dataset_id}")
        rel = str(safe_relative(entry.get("path", ""), label="snapshot file path"))
        if rel in seen:
            raise ValueError(f"Duplicate snapshot file path: {dataset_id}/{rel}")
        seen.add(rel)
        path = inside(files_root, rel)
        if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
            raise ValueError(f"Missing or oversized snapshot metadata file: {dataset_id}/{rel}")
        data = path.read_bytes()
        metadata_bytes(rel, data)
        if entry.get("size_bytes") != len(data) or entry.get("sha256") != sha256_bytes(data):
            raise ValueError(f"Snapshot file checksum mismatch: {dataset_id}/{rel}")
        _check_bound_file(rel, data, bound_assets, binding, dataset_id)
    collection_path = str(safe_relative(snapshot.get("collection_path", ""), label="collection path"))
    if collection_path not in seen:
        raise ValueError(f"Snapshot omits collection file: {dataset_id}/{collection_path}")
    collection = read_json(inside(files_root, collection_path))
    if collection.get("type") != "Collection" or collection.get("id") != dataset_id:
        raise ValueError(f"Snapshot collection identity/type mismatch: {dataset_id}")
    expected_version = tracked_manifest.get("release_version", release)
    if collection.get("version") not in (None, expected_version):
        raise ValueError(f"Snapshot collection release mismatch: {dataset_id}")
    if collection.get("items") or any(isinstance(link, dict) and link.get("rel") in ("child", "item") for link in collection.get("links", [])):
        raise ValueError(f"Nested collections and items are unsupported: {dataset_id}")
    referenced = {collection_path}
    for link in collection.get("links", []):
        if not isinstance(link, dict):
            raise ValueError(f"Malformed Collection link: {dataset_id}")
        href = link.get("href")
        if link.get("rel") in ("describedby", "agents", "style", "stylesheet", "thumbnail") and isinstance(href, str) and local_url(href):
            referenced.add(package_path(href, collection_path))
    for asset in collection.get("assets", {}).values():
        if isinstance(asset, dict) and isinstance(asset.get("href"), str) and local_url(asset["href"]) and any(role in ("style", "thumbnail") for role in asset.get("roles", [])):
            referenced.add(package_path(asset["href"], collection_path))
    if seen != referenced:
        raise ValueError(f"Snapshot missing or unreferenced metadata: {dataset_id}; missing={sorted(referenced-seen)} extra={sorted(seen-referenced)}")
    _check_collection_assets(collection, collection_path, bound_assets, binding, dataset_id)
    package_base = contract.get("package_base_url")
    if package_base is not None:
        https_url(package_base, f"{dataset_id} package_base_url")
        if not package_base.endswith("/"):
            raise ValueError(f"{dataset_id} package_base_url must end with /")
        if urlsplit(package_base).query or urlsplit(package_base).fragment:
            raise ValueError(f"{dataset_id} package_base_url cannot have query or fragment")
    if status == "published":
        config = load_config(root)
        nav, publish = config["navigation"], config["publish"]
        for field in ("repository_url", "issues_url", "hosting_url", "browser_url_template"):
            if not nav.get(field):
                raise ValueError(f"Published dataset {dataset_id} requires navigation.{field}")
        for field in ("destination", "public_base"):
            if not publish.get(field):
                raise ValueError(f"Published dataset {dataset_id} requires publish.{field}")
        if publish["destination"] != PAGES_DESTINATION and not publish.get("region"):
            raise ValueError(f"Published dataset {dataset_id} requires publish.region for S3")
        for field in ("repository_url", "issues_url", "hosting_url"):
            https_url(nav[field], f"navigation.{field}")
        browser_template_placeholder(nav["browser_url_template"])
        https_url(publish["public_base"], "publish.public_base")
        if not publish["public_base"].endswith("/"):
            raise ValueError("publish.public_base must end with /")
        if not package_base:
            raise ValueError(f"Published dataset {dataset_id} requires package_base_url")
        hosting_path = contract.get("hosting_report_path")
        hosting_hash = contract.get("hosting_report_sha256")
        if not hosting_path or not isinstance(hosting_hash, str):
            raise ValueError(f"Published dataset {dataset_id} requires checksum-bound hosting report")
        report_path = inside(root, hosting_path)
        report_data = report_path.read_bytes()
        if sha256_bytes(report_data) != hosting_hash:
            raise ValueError(f"Hosting report SHA-256 mismatch: {dataset_id}")
        report = read_json(report_path)
        if report.get("schema_version") != 1 or report.get("dataset_id") != dataset_id or report.get("release") != release or report.get("package_manifest_sha256") != snapshot.get("package_manifest_sha256") or report.get("package_base_url") != package_base or report.get("status") != "passed":
            raise ValueError(f"Hosting report identity/status mismatch: {dataset_id}")
        checked_at = report.get("checked_at")
        try:
            parsed_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
                raise ValueError("timezone required")
        except (AttributeError, ValueError):
            raise ValueError(f"Hosting report has invalid checked_at: {dataset_id}")
        checks = report.get("checks") or {}
        if any(checks.get(name) != "passed" for name in PASSING_CHECKS):
            raise ValueError(f"Hosting report has missing/failed required checks: {dataset_id}")
        if pub.get("display") is not None:
            _display_hosting_base(root, dataset_id, record)
    return snapshot, snapshot_path


def _navigation_links(node: dict, config: dict, node_path: str) -> None:
    nav = config["navigation"]
    links = node.setdefault("links", [])
    for rel, key, title in (("vcs", "repository_url", "Repository"), ("issues", "issues_url", "Issues"),
                            ("about", "hosting_url", "Hosting")):
        url = nav.get(key)
        if url:
            https_url(url, f"navigation.{key}")
            links.append({"rel": rel, "href": url, "title": title, "type": "text/html"})
    template = nav.get("browser_url_template")
    if template:
        placeholder = browser_template_placeholder(template)
        public_base = config["publish"].get("public_base")
        if public_base:
            catalog_url = urljoin(public_base, quote(node_path, safe="/-._~"))
            replacement = (quote(catalog_url, safe="") if placeholder == "catalog_url"
                           else portolan_browser_host_path(catalog_url))
            rendered = template.replace("{" + placeholder + "}", replacement)
            parsed = urlsplit(rendered)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in rendered):
                raise ValueError("navigation.browser_url_template must render an HTTPS URL")
            links.append({"rel": "alternate", "href": rendered, "title": "Browser view", "type": "text/html"})


def _local_href(href: str, old_collection_path: str) -> str:
    return package_path(href, old_collection_path)


def _rewrite_style(style: dict, style_path: str, package_base: str, collection_path: str) -> dict:
    def rewrite(value: object) -> object:
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, str):
            return value
        pmtiles = value.startswith("pmtiles://")
        href = value[len("pmtiles://"):] if pmtiles else value
        parsed = urlsplit(href)
        if parsed.scheme:
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in href):
                raise ValueError(f"Style URL must be HTTPS: {value}")
            return value
        if parsed.netloc or href.startswith("/"):
            raise ValueError(f"Unsafe style URL: {value}")
        path = package_path(href, style_path, label="style URL")
        absolute = urljoin(package_base, quote(path, safe="/-._~{}[]"))
        if parsed.query:
            absolute += "?" + parsed.query
        if parsed.fragment:
            absolute += "#" + parsed.fragment
        return "pmtiles://" + absolute if pmtiles else absolute
    for key in ("sprite", "glyphs"):
        if key in style:
            value = style[key]
            if key == "sprite" and isinstance(value, list):
                style[key] = [{**item, "url": rewrite(item["url"])}
                              if isinstance(item, dict) and "url" in item else rewrite(item)
                              for item in value]
            else:
                style[key] = rewrite(value)
    sources = style.get("sources", {})
    if isinstance(sources, dict):
        for source in sources.values():
            if not isinstance(source, dict):
                continue
            for key in ("url",):
                value = source.get(key)
                if isinstance(value, str):
                    source[key] = rewrite(value)
            for key in ("tiles", "data"):
                if key in source:
                    source[key] = rewrite(source[key])
    return style


def _remove_portolan_fields(value: object) -> object:
    if isinstance(value, dict):
        return {key: _remove_portolan_fields(item) for key, item in value.items()
                if not (isinstance(key, str) and key.startswith("portolan:"))}
    if isinstance(value, list):
        return [_remove_portolan_fields(item) for item in value]
    return value


def _generated(root: Path, config: dict) -> dict[str, bytes]:
    records = validated_records(root)
    tree: dict[str, bytes] = {}
    published = []
    for dataset_id, record in sorted(records.items()):
        status = (record.get("publication") or {}).get("status", "candidate")
        snapshot, path = _load_publication_snapshot(root, dataset_id, record)
        if status == "published":
            published.append((dataset_id, record, snapshot, path))
    title = config["catalog"]["title"]
    description = config["catalog"]["description"]
    children: list[dict] = []
    catalog = {"stac_version": "1.1.0", "stac_extensions": [PORTOLAN_SCHEMA],
               "type": "Catalog", "id": config["catalog"]["id"],
               "title": title, "description": description,
               "links": [{"rel": "root", "href": "catalog.json", "type": "application/json"},
                         {"rel": "describedby", "href": "./README.md", "type": "text/markdown"},
                         {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown"}]}

    def put(rel: str, data: bytes) -> None:
        rel = str(safe_relative(rel, label="generated path"))
        if rel in tree:
            raise ValueError(f"Duplicate generated output path: {rel}")
        tree[rel] = data

    for dataset_id, record, snapshot, snap_path in published:
        display = _display_package(root, dataset_id, record)
        thumbnail = _catalog_thumbnail(root, dataset_id, record)
        display_base = _display_hosting_base(root, dataset_id, record)
        collection_path = snapshot["collection_path"]
        file_entries = {item["path"]: item for item in snapshot["files"]}
        source_path = snap_path.parent / "files" / Path(*PurePosixPath(collection_path).parts)
        collection = read_json(source_path)
        out_collection = _remove_portolan_fields(json.loads(json.dumps(collection)))
        out_collection["title"] = record["title"]
        if not out_collection.get("license"):
            raise ValueError(f"Published collection {dataset_id} has no license")
        base = record["publication"]["catalog"]["package_base_url"]
        local_mapping: dict[str, str] = {}
        for entry in snapshot["files"]:
            rel = entry["path"]
            if rel != collection_path:
                original_dir = PurePosixPath(collection_path).parent
                try:
                    target = str(PurePosixPath(rel).relative_to(original_dir))
                except ValueError:
                    target = "metadata/" + PurePosixPath(rel).name
                safe_relative(target, label="generated metadata path")
                if target in local_mapping.values() or target == "collection.json":
                    raise ValueError(f"Duplicate generated metadata target: {dataset_id}/{target}")
                local_mapping[rel] = target
        out_links = []
        for link in out_collection.get("links", []):
            rel = link.get("rel")
            href = link.get("href")
            if display is not None and rel in ("style", "stylesheet", "pmtiles"):
                continue
            if rel in ("root", "parent", "self", "describedby", "agents", "vcs", "issues", "about", "alternate"):
                continue
            elif isinstance(href, str) and local_url(href) and rel in ("describedby", "agents", "style", "stylesheet", "thumbnail"):
                package_rel = _local_href(href, collection_path)
                if package_rel not in local_mapping:
                    raise ValueError(f"Snapshot missing linked metadata {dataset_id}/{package_rel}")
                link["href"] = local_mapping[package_rel]
                out_links.append(link)
            elif isinstance(href, str) and local_url(href):
                package_rel = package_path(href, collection_path)
                link["href"] = urljoin(base, quote(package_rel, safe="/-._~"))
                out_links.append(link)
            else:
                if isinstance(href, str):
                    https_reference(href, f"{dataset_id} link")
                out_links.append(link)
        out_links.extend([{"rel": "root", "href": "../catalog.json", "type": "application/json"},
                          {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
                          {"rel": "describedby", "href": "./README.md", "type": "text/markdown"},
                          {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown"}])
        out_collection["links"] = out_links
        if display is not None:
            out_collection["assets"] = {
                asset_id: asset for asset_id, asset in out_collection.get("assets", {}).items()
                if not (isinstance(asset, dict)
                        and ("style" in asset.get("roles", []) or "visual" in asset.get("roles", [])
                             or asset.get("type") == "application/vnd.pmtiles"))
            }
        for asset in out_collection.get("assets", {}).values():
            if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
                continue
            href = asset["href"]
            if local_url(href):
                metadata_path = _local_href(href, collection_path)
                if any(role in ("style", "thumbnail") for role in asset.get("roles", [])) and metadata_path in local_mapping:
                    asset["href"] = local_mapping[metadata_path]
                else:
                    asset["href"] = urljoin(base, quote(metadata_path, safe="/-._~"))
        base = record["publication"]["catalog"]["package_base_url"]
        snapshot_style_paths = {package_path(link["href"], collection_path) for link in collection.get("links", [])
                                if link.get("rel") in ("style", "stylesheet") and isinstance(link.get("href"), str) and local_url(link["href"])}
        snapshot_style_paths.update(package_path(asset["href"], collection_path) for asset in collection.get("assets", {}).values()
                                    if isinstance(asset, dict) and isinstance(asset.get("href"), str) and local_url(asset["href"])
                                    and "style" in asset.get("roles", []))
        snapshot_thumbnail_paths = {
            package_path(link["href"], collection_path) for link in collection.get("links", [])
            if link.get("rel") == "thumbnail" and isinstance(link.get("href"), str) and local_url(link["href"])
        }
        snapshot_thumbnail_paths.update(
            package_path(asset["href"], collection_path) for asset in collection.get("assets", {}).values()
            if isinstance(asset, dict) and isinstance(asset.get("href"), str)
            and local_url(asset["href"]) and "thumbnail" in asset.get("roles", [])
        )
        style_paths = snapshot_style_paths if display is None else set()
        for old_rel in sorted(style_paths):
            staged_rel = local_mapping[old_rel]
            style_path = snap_path.parent / "files" / Path(*PurePosixPath(old_rel).parts)
            style = read_json(style_path)
            rewritten = _rewrite_style(style, old_rel, base, collection_path)
            data = canonical_json(rewritten)
            put(f"{dataset_id}/{staged_rel}", data)
            for asset in out_collection.get("assets", {}).values():
                if isinstance(asset, dict) and asset.get("href") == staged_rel:
                    asset["file:checksum"] = "1220" + sha256_bytes(data)
                    asset["file:size"] = len(data)
        for entry in snapshot["files"]:
            rel = entry["path"]
            guidance = any(link.get("rel") in ("describedby", "agents") and isinstance(link.get("href"), str)
                           and local_url(link["href"]) and package_path(link["href"], collection_path) == rel
                           for link in collection.get("links", []))
            if (rel == collection_path or rel in snapshot_style_paths or guidance
                    or (thumbnail is not None and rel in snapshot_thumbnail_paths)):
                continue
            staged = local_mapping[rel]
            data = (snap_path.parent / "files" / Path(*PurePosixPath(rel).parts)).read_bytes()
            put(f"{dataset_id}/{staged}", data)
        if display is not None:
            if display_base is None:
                raise ValueError(f"Published dataset {dataset_id} has no verified display package URL")
            _add_display_publication(out_collection, display, display_base, dataset_id, put)
        if thumbnail is not None:
            _set_catalog_thumbnail(out_collection, thumbnail, dataset_id, put)
        _set_public_host(out_collection, dataset_id, record)
        from flat_publication import apply_flat_layout
        flat_layout = apply_flat_layout(root, record, out_collection, tree)
        _navigation_links(out_collection, config, f"{dataset_id}/collection.json")
        children.append({"rel": "child", "href": f"{dataset_id}/collection.json", "title": record["title"], "type": "application/json"})
        put(f"{dataset_id}/collection.json", canonical_json(out_collection))
        notes = [f"# {record['title']}", "", collection.get("description", ""), "",
                 f"License: {collection['license']}.", "",
                 f"Immutable package: {base}", ""]
        correction = record["publication"]["catalog"].get("processor_correction")
        if correction:
            notes.extend(["Maintainer: " + correction["to"] + ".", ""])
        if thumbnail is not None:
            notes.extend(["Catalog preview: " + thumbnail[0]["title"] + ". Display only; use GeoParquet for analysis.", ""])
        producers = [provider.get("name", "") for provider in collection.get("providers", [])
                     if "producer" in provider.get("roles", [])]
        if producers:
            notes.extend(["Source producers: " + "; ".join(producers), ""])
        for source_link in collection.get("links", []):
            if source_link.get("rel") in ("via", "canonical"):
                notes.append("Source provenance: " + str(source_link.get("href", "")))
        for link in collection.get("links", []):
            if link.get("rel") in ("describedby", "agents") and isinstance(link.get("href"), str) and local_url(link["href"]):
                if flat_layout is None:
                    notes.append(f"Original {link['rel']} notes: {urljoin(base, quote(package_path(link['href'], collection_path), safe='/-._~'))}")
        if flat_layout is not None:
            config_source = record["publication"]["source_coop"]
            notes.extend(["", f"Data, map layers and usage: https://source.coop/{config_source['owner']}/{config_source['product_id']}", ""])
        limits = (record.get("publication") or {}).get("limits") or (record.get("publication") or {}).get("limitations")
        if limits:
            notes.extend(["", "Canonical publication limits:", "", yaml.safe_dump(limits, sort_keys=True, allow_unicode=True).strip()])
        put(f"{dataset_id}/README.md", ("\n".join(notes).rstrip() + "\n").encode())
        put(f"{dataset_id}/AGENTS.md", (f"# Dataset guidance\n\nDataset: {dataset_id}. Release: {snapshot['release']}.\n"
                                        f"Use the analytic data assets for analysis; display derivatives are presentation only. "
                                        f"Preserve producer identity, units, nulls, uncertainty and record multiplicity. "
                                        f"See README.md and the immutable package at {base}.\n").encode())
    catalog["links"].extend(children)
    if published:
        updates = [read_json_from_bytes(tree[f"{dataset_id}/collection.json"]).get("updated")
                   for dataset_id, _, _, _ in published]
        if not all(isinstance(value, str) and value for value in updates):
            raise ValueError("Published collections require an updated timestamp")
        catalog["updated"] = max(updates)
    _navigation_links(catalog, config, "catalog.json")
    put("catalog.json", canonical_json(catalog))
    summary = [f"# {title}", "", description, "", f"Published collections: {len(published)}.", "",
               "This catalog indexes published metadata with pinned package releases and prior hosting attestations.", "",
               "License: repository-authored catalog metadata and software are Apache-2.0. "
               "Each collection declares its separate data license.", "",
               "Provenance: generated from canonical dataset.yaml records and checksum-bound metadata "
               "exported from verified immutable packages. Each collection links its original source and release notes.", ""]
    for dataset_id, record, _, _ in published:
        summary.append(f"- [{record['title']}]({dataset_id}/collection.json)")
    put("README.md", ("\n".join(summary).rstrip() + "\n").encode())
    put("AGENTS.md", ROOT_AGENTS.encode())
    return tree


def _scan_tree(root: Path, expected: dict[str, bytes]) -> list[str]:
    found = set()
    if root.exists():
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Generated tree contains symlink: {path}")
            if path.is_file():
                found.add(path.relative_to(root).as_posix())
    return sorted(found ^ set(expected))


def write_tree(root: Path, expected: dict[str, bytes]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    unexpected = _scan_tree(root, expected)
    # Existing unexpected files are never silently deleted or overwritten.
    for rel in unexpected:
        path = root / rel
        if path.exists() and rel not in expected:
            raise ValueError(f"Unexpected generated file; remove or reconcile explicitly: {rel}")
    for rel, data in expected.items():
        path = inside(root, rel, must_exist=False)
        if path.exists() and path.is_dir():
            raise ValueError(f"Generated file path is a directory: {rel}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError(f"Generated path is a symlink: {rel}")
        path.write_bytes(data)
    stale = [rel for rel in _scan_tree(root, expected) if (root / rel).is_file()]
    if stale:
        raise ValueError(f"Unexpected generated files: {', '.join(stale)}")


def _export_metadata_cli(args: argparse.Namespace) -> None:
    output = args.output if args.output.is_absolute() else args.root / args.output
    export_metadata(args.dataset_id, args.package, output, args.root)
    print(f"Exported metadata snapshot for {args.dataset_id}: {output}")


def _write(args: argparse.Namespace) -> None:
    config = load_config(args.root)
    expected = _generated(args.root, config)
    write_tree(args.root / "catalog", expected)
    print(json.dumps({"published_collections": sum(1 for d in load_records(args.root).values() if (d.get("publication") or {}).get("status") == "published"), "generated_files": len(expected)}, indent=2))


def _check(args: argparse.Namespace) -> None:
    config = load_config(args.root)
    expected = _generated(args.root, config)
    catalog_dir = args.root / "catalog"
    if catalog_dir.is_symlink():
        raise ValueError("Generated catalog directory is a symlink")
    missing_or_drift = []
    for rel, data in expected.items():
        path = catalog_dir / rel
        if path.is_symlink():
            raise ValueError(f"Generated tree contains symlink: {rel}")
        if not path.is_file() or path.read_bytes() != data:
            missing_or_drift.append(rel)
    extras = []
    if catalog_dir.exists():
        for path in catalog_dir.rglob("*"):
            rel = path.relative_to(catalog_dir).as_posix()
            if path.is_symlink():
                raise ValueError(f"Generated tree contains symlink: {rel}")
            if path.is_file() and rel not in expected:
                extras.append(rel)
    if missing_or_drift or extras:
        raise ValueError(f"Generated tree drift: missing/stale={missing_or_drift}; unexpected={sorted(extras)}")
    print(f"Catalog check passed; {sum(1 for d in load_records(args.root).values() if (d.get('publication') or {}).get('status') == 'published')} published collections.")


def _stage(args: argparse.Namespace) -> None:
    config = load_config(args.root)
    expected = _generated(args.root, config)
    if not any((d.get("publication") or {}).get("status") == "published" for d in load_records(args.root).values()):
        raise ValueError("Not ready to stage: zero published collections")
    publish = config["publish"]
    destination = publish.get("destination")
    public_base = publish.get("public_base")
    if not destination or not public_base:
        raise ValueError("Not ready to stage: publish.destination and publish.public_base are required")
    https_url(public_base, "publish.public_base")
    if not public_base.endswith("/"):
        raise ValueError("publish.public_base must end with /")
    _check(args)
    output = args.output.absolute()
    catalog_dir = args.root / "catalog"
    if output == catalog_dir or catalog_dir in output.parents:
        raise ValueError("Stage output must not be inside tracked catalog")
    if output.exists() or output.is_symlink():
        raise ValueError(f"Stage output already exists: {output}")
    cursor = output
    while True:
        if cursor.is_symlink():
            raise ValueError(f"Stage output path traverses a symlink: {cursor}")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    output.mkdir(parents=True)
    files = {k: v for k, v in expected.items()}
    catalog_doc = read_json_from_bytes(files["catalog.json"])
    catalog_doc["links"].append({"rel": "self", "href": urljoin(public_base, "catalog.json"), "type": "application/json"})
    files["catalog.json"] = canonical_json(catalog_doc)
    for rel in sorted(files):
        if not rel.endswith("/collection.json"):
            continue
        node = read_json_from_bytes(files[rel])
        document_url = urljoin(public_base, quote(rel, safe="/-._~"))
        node["links"].append({"rel": "self", "href": document_url, "type": "application/json"})
        for asset in node.get("assets", {}).values():
            href = asset.get("href")
            if isinstance(href, str) and local_url(href):
                asset["href"] = urljoin(document_url, quote(href, safe="/-._~"))
        for link in node["links"]:
            href = link.get("href")
            if (link.get("rel") in ("style", "stylesheet", "thumbnail", "pmtiles")
                    and isinstance(href, str) and local_url(href)):
                link["href"] = urljoin(document_url, quote(href, safe="/-._~"))
        files[rel] = canonical_json(node)
    plan = []
    for rel, data in sorted(files.items()):
        dest = output / "catalog" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        plan.append({"path": f"catalog/{rel}", "size_bytes": len(data), "sha256": sha256_bytes(data),
                     "target_url": urljoin(public_base, quote(rel, safe="/-._~")),
                     "target_uri": destination + rel})
    (output / "publish-plan.json").write_bytes(canonical_json({"schema_version": 1, "destination": destination,
                                                               "region": publish.get("region"), "files": plan}))
    print(f"Prepared metadata-only stage: {output} ({len(files)} files). No upload was performed.")


def read_json_from_bytes(data: bytes) -> dict:
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Expected generated JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=default_root, help=argparse.SUPPRESS)
    modes = parser.add_subparsers(dest="command", required=True)
    export = modes.add_parser("export-metadata", help="copy small package metadata and write a bound snapshot")
    export.add_argument("dataset_id")
    export.add_argument("--package", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True, help="new repository-relative snapshot directory")
    export.add_argument("--root", type=Path, default=argparse.SUPPRESS)
    export.set_defaults(func=_export_metadata_cli)
    for name in ("write", "check"):
        sub = modes.add_parser(name)
        sub.add_argument("--root", type=Path, default=argparse.SUPPRESS)
        sub.set_defaults(func=_write if name == "write" else _check)
    stage = modes.add_parser("stage", help="prepare metadata-only output; does not upload or check hosting")
    stage.add_argument("output", type=Path)
    stage.add_argument("--root", type=Path, default=argparse.SUPPRESS)
    stage.set_defaults(func=_stage)
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    try:
        args.func(args)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
