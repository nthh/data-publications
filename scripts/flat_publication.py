"""Apply a pinned, verified flat Source Cooperative asset layout.

The legacy collection and its immutable package are validated before this
module is called. This module only validates the additive flat-layout receipt
and rewrites the generated Collection and small local outputs to point at it.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FLAT_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
HOSTING_CHECKS = (
    "anonymous_access", "range_requests", "cors", "asset_checksums",
    "subset_query", "catalog_links", "browser_render",
)
LAYOUT_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


def _fail(message: str) -> None:
    raise ValueError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relpath(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail(f"Invalid {label}: {value!r}")
    if any(part in ("", ".", "..") for part in value.split("/")):
        _fail(f"Unsafe {label}: {value!r}")
    p = PurePosixPath(value)
    w = PureWindowsPath(value)
    if (p.is_absolute() or w.is_absolute() or w.drive
            or any(part in ("", ".", "..") for part in value.split("/"))):
        _fail(f"Unsafe {label}: {value!r}")
    return p.as_posix()


def _basename(value: Any) -> str:
    rel = _relpath(value, "flat filename")
    if "/" in rel or not FLAT_FILENAME_RE.fullmatch(rel):
        _fail(f"Flat filename must be a basename: {value!r}")
    return rel


def _repo_file(root: Path, value: Any, label: str) -> Path:
    if root.is_symlink():
        _fail(f"Symlink repository root is not allowed for {label}")
    rel = _relpath(value, label)
    candidate = root
    for part in PurePosixPath(rel).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(f"Symlink is not allowed in {label}: {rel}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Missing {label}: {rel}") from exc
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        _fail(f"{label} is not an in-repository regular file: {rel}")
    return resolved


def _read_json(root: Path, path: Any, label: str) -> tuple[dict[str, Any], bytes]:
    file = _repo_file(root, path, label)
    data = file.read_bytes()
    try:
        result = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {label}: {path}") from exc
    if not isinstance(result, dict):
        _fail(f"{label} must be a JSON object")
    return result, data


def _pin_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(f"Invalid {label} SHA-256")
    return value


def _positive_size(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        _fail(f"Invalid {label} size_bytes")
    return value


def _asset_sha(asset: dict[str, Any], label: str) -> str:
    checksum = asset.get("file:checksum")
    if not isinstance(checksum, str) or not checksum.startswith("1220"):
        _fail(f"{label} lacks a SHA-256 STAC checksum")
    digest = checksum[4:]
    return _pin_sha(digest, label)


def _https_asset_url(owner: str, product_id: str, filename: str) -> str:
    return f"https://data.source.coop/{owner}/{product_id}/{filename}"


def load_flat_layout(root: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    """Load and verify a record's optional flat-layout manifest and hosting receipt."""
    publication = record.get("publication") or {}
    source = publication.get("source_coop") or {}
    layout_pin = source.get("flat_layout")
    if layout_pin is None:
        return None
    if not isinstance(layout_pin, dict):
        _fail(f"{record.get('id')}: publication.source_coop.flat_layout must be an object")
    dataset_id = record.get("id")
    owner, product_id = source.get("owner"), source.get("product_id")
    release = publication.get("release")
    manifest_path = layout_pin.get("manifest_path")
    manifest_sha = _pin_sha(layout_pin.get("manifest_sha256"), "flat layout manifest")
    manifest, manifest_bytes = _read_json(root, manifest_path, "flat layout manifest")
    if _sha256(manifest_bytes) != manifest_sha:
        _fail(f"{dataset_id}: flat layout manifest hash mismatch")
    layout_id = manifest.get("layout_id")
    if (manifest.get("schema_version") != 1 or manifest.get("dataset_id") != dataset_id
            or not isinstance(layout_id, str) or not LAYOUT_ID_RE.fullmatch(layout_id)
            or manifest.get("owner") != owner
            or manifest.get("product_id") != product_id or manifest.get("source_release") != release):
        _fail(f"{dataset_id}: flat layout manifest identity/release mismatch")
    updated = manifest.get("updated")
    try:
        parsed_updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{dataset_id}: flat layout updated must be a UTC ISO timestamp ending in Z") from exc
    if not isinstance(updated, str) or not updated.endswith("Z") or parsed_updated.utcoffset() is None:
        _fail(f"{dataset_id}: flat layout updated must be a UTC ISO timestamp ending in Z")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        _fail(f"{dataset_id}: flat layout files must be a non-empty array")
    seen_filenames: set[str] = set()
    seen_assets: set[str] = set()
    seen_sources: set[str] = set()
    for index, item in enumerate(files):
        label = f"{dataset_id} flat file {index}"
        if not isinstance(item, dict):
            _fail(f"{label} must be an object")
        filename = _basename(item.get("filename"))
        if filename in seen_filenames:
            _fail(f"{dataset_id}: duplicate flat filename: {filename}")
        seen_filenames.add(filename)
        digest = _pin_sha(item.get("sha256"), label)
        size = _positive_size(item.get("size_bytes"), label)
        if not isinstance(item.get("media_type"), str) or not item["media_type"]:
            _fail(f"{label} media_type is required")
        if not isinstance(item.get("roles"), list) or not all(isinstance(role, str) for role in item["roles"]):
            _fail(f"{label} roles must be a string array")
        if not isinstance(item.get("title"), str) or not item["title"]:
            _fail(f"{label} title is required")
        operation = item.get("operation")
        if operation not in {"copy", "rewrite_style", "pmtiles_attribution", "generated"}:
            _fail(f"{label} has unsupported operation")
        asset_id, source_href = item.get("asset_id"), item.get("source_href")
        if asset_id is None and source_href is None:
            if operation != "generated":
                _fail(f"{label} without an asset source must use generated operation")
            if item.get("source_sha256") is not None or item.get("source_size_bytes") is not None:
                _fail(f"{label} generated file cannot declare source checksums")
        else:
            if not isinstance(asset_id, str) or not asset_id:
                _fail(f"{label} asset_id is required for a catalog asset")
            if asset_id in seen_assets:
                _fail(f"{dataset_id}: duplicate mapped asset_id: {asset_id}")
            seen_assets.add(asset_id)
            if not isinstance(source_href, str) or not source_href:
                _fail(f"{label} source_href is required for a catalog asset")
            if source_href in seen_sources:
                _fail(f"{dataset_id}: duplicate mapped source_href: {source_href}")
            seen_sources.add(source_href)
            _pin_sha(item.get("source_sha256"), f"{label} source")
            _positive_size(item.get("source_size_bytes"), f"{label} source")
        if operation in ("rewrite_style", "generated"):
            local_path = item.get("local_path")
            local_file = _repo_file(root, local_path, f"{label} local file")
            local_bytes = local_file.read_bytes()
            if len(local_bytes) != size or _sha256(local_bytes) != digest:
                _fail(f"{label} local file hash/size mismatch")
        if operation == "pmtiles_attribution":
            proof_ref = item.get("transformation_proof")
            if not isinstance(proof_ref, dict):
                _fail(f"{label} requires a transformation_proof pin")
            proof_sha = _pin_sha(proof_ref.get("sha256"), f"{label} transformation proof")
            proof, proof_bytes = _read_json(root, proof_ref.get("path"), f"{label} transformation proof")
            if _sha256(proof_bytes) != proof_sha:
                _fail(f"{label} transformation proof checksum mismatch")
            if (proof.get("status") != "passed"
                    or proof.get("source_sha256") != item.get("source_sha256")
                    or proof.get("source_size_bytes") != item.get("source_size_bytes")
                    or proof.get("target_sha256") != digest or proof.get("target_size_bytes") != size
                    or proof.get("geometry_payload_unchanged") is not True):
                _fail(f"{label} transformation proof does not bind the source and target")
            sections = proof.get("encoded_sections")
            if not isinstance(sections, dict) or not {"root", "leaf", "tile_data"}.issubset(sections):
                _fail(f"{label} transformation proof lacks byte-section comparisons")
            for section_name in ("root", "leaf", "tile_data"):
                section = sections.get(section_name)
                if (not isinstance(section, dict) or section.get("identical") is not True
                        or type(section.get("bytes")) is not int or section["bytes"] < 0
                        or not isinstance(section.get("sha256"), str)
                        or not SHA256_RE.fullmatch(section["sha256"])):
                    _fail(f"{label} transformation proof has no verified {section_name} bytes")

    report_path = layout_pin.get("hosting_report_path")
    report_sha = _pin_sha(layout_pin.get("hosting_report_sha256"), "flat layout hosting report")
    report, report_bytes = _read_json(root, report_path, "flat layout hosting report")
    if _sha256(report_bytes) != report_sha:
        _fail(f"{dataset_id}: flat layout hosting report checksum mismatch")
    if (report.get("schema_version") != 1 or report.get("dataset_id") != dataset_id
            or report.get("layout_id") != layout_id or report.get("manifest_sha256") != manifest_sha
            or report.get("status") != "passed"):
        _fail(f"{dataset_id}: flat layout hosting report identity mismatch")
    checks = report.get("checks")
    if not isinstance(checks, dict) or any(checks.get(name) != "passed" for name in HOSTING_CHECKS):
        _fail(f"{dataset_id}: flat layout hosting report is missing required passing checks")
    proof_files = report.get("files")
    if not isinstance(proof_files, list):
        _fail(f"{dataset_id}: flat layout hosting report files must be an array")
    proofs: dict[str, dict[str, Any]] = {}
    for proof in proof_files:
        if not isinstance(proof, dict) or not isinstance(proof.get("filename"), str):
            _fail(f"{dataset_id}: malformed flat layout hosting file proof")
        name = _basename(proof["filename"])
        if name in proofs:
            _fail(f"{dataset_id}: duplicate hosted proof for {name}")
        proofs[name] = proof
    expected_names = {item["filename"] for item in files}
    if set(proofs) != expected_names:
        _fail(f"{dataset_id}: hosted proof file set differs from flat layout manifest")
    for item in files:
        proof = proofs[item["filename"]]
        if (proof.get("status") != "verified" or proof.get("sha256") != item["sha256"]
                or proof.get("size_bytes") != item["size_bytes"]):
            _fail(f"{dataset_id}: hosted proof mismatch for {item['filename']}")
    return manifest


def _style_url(value: Any, dataset_id: str) -> tuple[str, str]:
    if not isinstance(value, str) or not value:
        _fail(f"{dataset_id}: style source URL must be non-empty text")
    prefix = "pmtiles://" if value.startswith("pmtiles://") else ""
    url = value.removeprefix(prefix)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        _fail(f"{dataset_id}: style source must use a clean HTTPS PMTiles URL")
    return prefix, url


def _rewrite_style_bytes(root: Path, record: dict[str, Any], style_file: dict[str, Any],
                         source_to_target: dict[str, str], tree: dict[str, bytes]) -> bytes:
    dataset_id = record["id"]
    old_href = style_file["source_href"]
    old_bytes = tree.get(f"{dataset_id}/{old_href}")
    if old_bytes is None:
        _fail(f"{dataset_id}: generated tree lacks original style {old_href}")
    if _sha256(old_bytes) != style_file["source_sha256"] or len(old_bytes) != style_file["source_size_bytes"]:
        _fail(f"{dataset_id}: original style differs from flat-layout source pin")
    try:
        old_style = json.loads(old_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{dataset_id}: original style is invalid JSON") from exc
    if not isinstance(old_style, dict) or old_style.get("version") != 8:
        _fail(f"{dataset_id}: original style must be MapLibre style version 8")
    expected = copy.deepcopy(old_style)
    sources = expected.get("sources")
    if not isinstance(sources, dict) or not sources:
        _fail(f"{dataset_id}: style must contain sources")
    rewrites = 0
    for source in sources.values():
        if not isinstance(source, dict):
            _fail(f"{dataset_id}: style source must be an object")
        if "url" in source:
            _, url = _style_url(source["url"], dataset_id)
            target = source_to_target.get(url)
            if target is None:
                _fail(f"{dataset_id}: style references an unmapped PMTiles URL: {url}")
            source["url"] = target
            rewrites += 1
        if "tiles" in source:
            tiles = source["tiles"]
            if not isinstance(tiles, list) or not tiles:
                _fail(f"{dataset_id}: style source tiles must be a non-empty array")
            rewritten_tiles = []
            for value in tiles:
                _, url = _style_url(value, dataset_id)
                target = source_to_target.get(url)
                if target is None:
                    _fail(f"{dataset_id}: style references an unmapped PMTiles URL: {url}")
                rewritten_tiles.append(target)
                rewrites += 1
            source["tiles"] = rewritten_tiles
    if rewrites == 0:
        _fail(f"{dataset_id}: style has no mapped PMTiles source URL")
    local_file = _repo_file(root, style_file["local_path"], "rewritten style")
    rewritten = local_file.read_bytes()
    try:
        actual = json.loads(rewritten)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{dataset_id}: rewritten style is invalid JSON") from exc
    configured = (record.get("publication") or {}).get("source_coop") or {}
    for name, source in expected["sources"].items():
        old_credit = source.get("attribution")
        new_credit = actual.get("sources", {}).get(name, {}).get("attribution")
        if isinstance(old_credit, str) and "folia" in old_credit.lower():
            allowed_credit = configured.get("attribution", "") + " " + configured.get("license_note", "")
            if new_credit != allowed_credit.strip() or "folia" in new_credit.lower():
                _fail(f"{dataset_id}: style attribution correction must retain canonical producer/license credit")
        elif new_credit != old_credit:
            _fail(f"{dataset_id}: style changed an unrelated source attribution")
    # Some consumers require pmtiles:// before an absolute PMTiles URL. It is
    # transport syntax rather than a different tile address. Permit source-level
    # attribution corrections while enforcing all other style fields exactly.
    def semantic_style(style: dict[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(style)
        for source in value.get("sources", {}).values():
            if "attribution" in source and (not isinstance(source["attribution"], str) or not source["attribution"]):
                _fail(f"{dataset_id}: corrected style attribution must be non-empty text")
            for key in ("url",):
                if isinstance(source.get(key), str):
                    source[key] = source[key].removeprefix("pmtiles://")
            if isinstance(source.get("tiles"), list):
                source["tiles"] = [tile.removeprefix("pmtiles://") if isinstance(tile, str) else tile
                                   for tile in source["tiles"]]
            source.pop("attribution", None)
        return value

    if semantic_style(actual) != semantic_style(expected):
        _fail(f"{dataset_id}: rewritten style changes rendering fields beyond mapped PMTiles URLs")
    if len(rewritten) != style_file["size_bytes"] or _sha256(rewritten) != style_file["sha256"]:
        _fail(f"{dataset_id}: rewritten style target hash/size mismatch")
    return rewritten


def apply_flat_layout(root: Path, record: dict[str, Any], collection: dict[str, Any],
                      tree: dict[str, bytes]) -> dict[str, Any] | None:
    """Rewrite a previously generated Collection using its verified flat layout."""
    manifest = load_flat_layout(root, record)
    if manifest is None:
        return None
    dataset_id = record["id"]
    if collection.get("id") != dataset_id:
        _fail(f"{dataset_id}: generated Collection ID does not match canonical record")
    source = (record.get("publication") or {}).get("source_coop") or {}
    owner, product_id = source["owner"], source["product_id"]
    assets = collection.get("assets")
    if not isinstance(assets, dict):
        _fail(f"{dataset_id}: generated Collection assets must be an object")
    files = manifest["files"]
    by_asset: dict[str, dict[str, Any]] = {}
    source_to_target: dict[str, str] = {}
    for item in files:
        asset_id = item.get("asset_id")
        if asset_id is None:
            continue
        asset = assets.get(asset_id)
        if not isinstance(asset, dict):
            _fail(f"{dataset_id}: flat layout references missing Collection asset {asset_id}")
        if asset.get("href") != item.get("source_href"):
            _fail(f"{dataset_id}: source href changed for asset {asset_id}")
        if (_asset_sha(asset, f"{dataset_id}/{asset_id}") != item.get("source_sha256")
                or asset.get("file:size") != item.get("source_size_bytes")):
            _fail(f"{dataset_id}: source checksum/size mismatch for asset {asset_id}")
        if (asset.get("type") != item.get("media_type") or asset.get("roles") != item.get("roles")
                or asset.get("title") != item.get("title")):
            _fail(f"{dataset_id}: flat metadata differs from Collection asset {asset_id}")
        by_asset[asset_id] = item
        if item["operation"] == "pmtiles_attribution":
            source_to_target[item["source_href"]] = _https_asset_url(owner, product_id, item["filename"])
    required_assets = {
        asset_id for asset_id, asset in assets.items()
        if isinstance(asset, dict) and (
            any(role in (asset.get("roles") or []) for role in ("data", "visual", "style"))
            or asset_id.endswith("_fields") or asset_id == "schema"
        )
    }
    missing = required_assets - set(by_asset)
    if missing:
        _fail(f"{dataset_id}: flat layout omits Collection assets: {', '.join(sorted(missing))}")
    if set(by_asset) - set(assets):
        _fail(f"{dataset_id}: flat layout references unknown Collection assets")

    pmtiles_files = {item["source_href"]: item for item in files
                     if item.get("media_type") == "application/vnd.pmtiles"}
    source_to_target.update({href: _https_asset_url(owner, product_id, item["filename"])
                             for href, item in pmtiles_files.items()})
    # Styles are validated against the original generated style bytes, rewritten only
    # at PMTiles source URLs, and copied to a distinct flat root object for Source.
    for item in files:
        if item["operation"] == "rewrite_style":
            style_bytes = _rewrite_style_bytes(root, record, item, source_to_target, tree)
            tree[f"{dataset_id}/{item['source_href']}"] = style_bytes

    for asset_id, item in by_asset.items():
        operation = item["operation"]
        asset = assets[asset_id]
        if operation == "copy":
            if (item.get("sha256") != item.get("source_sha256")
                    or item.get("size_bytes") != item.get("source_size_bytes")):
                _fail(f"{dataset_id}: copy operation must preserve bytes for {asset_id}")
            asset["href"] = _https_asset_url(owner, product_id, item["filename"])
        elif operation == "pmtiles_attribution":
            asset["href"] = _https_asset_url(owner, product_id, item["filename"])
            asset["file:checksum"] = "1220" + item["sha256"]
            asset["file:size"] = item["size_bytes"]
        elif operation == "rewrite_style":
            # Keep the local catalog style href; the separate flat copy is for Source.
            asset["file:checksum"] = "1220" + item["sha256"]
            asset["file:size"] = item["size_bytes"]
        else:
            _fail(f"{dataset_id}: generated file cannot replace an existing Collection asset")

    links = collection.get("links")
    if not isinstance(links, list):
        _fail(f"{dataset_id}: generated Collection links must be an array")
    for link in links:
        if not isinstance(link, dict):
            continue
        if link.get("rel") == "pmtiles" and isinstance(link.get("href"), str):
            target = source_to_target.get(link["href"])
            if target is None:
                _fail(f"{dataset_id}: PMTiles link has no verified flat mapping: {link['href']}")
            link["href"] = target
    collection["updated"] = manifest["updated"]

    # Source licenses and compact manifests remain in their verified Source
    # product and tracked publication inputs. The catalog only needs its existing
    # style paths, avoiding duplicate unreferenced metadata files here.
    return manifest
