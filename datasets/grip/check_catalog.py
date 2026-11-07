#!/usr/bin/env python3
"""Verify local GRIP4 STAC links, asset checksums and provider metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _resolve_local_href(href: str, base_file: Path, root: Path) -> Path | None:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported external href scheme: {href}")
        return None
    if parsed.query or parsed.fragment:
        raise ValueError(f"Local href has query or fragment: {href}")
    decoded = unquote(parsed.path)
    if not decoded or "\\" in decoded or Path(decoded).is_absolute():
        raise ValueError(f"Unsafe local href: {href}")
    target = (base_file.parent / decoded).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Local href escapes release root: {href}") from exc
    return target


def check_catalog(root: Path) -> dict:
    root = Path(root).resolve()
    catalog_path = root / "catalog.json"
    collection_path = root / "grip" / "collection.json"
    catalog = _read(catalog_path)
    collection = _read(collection_path)
    problems: list[str] = []

    for name, obj, path in (("catalog", catalog, catalog_path), ("collection", collection, collection_path)):
        if obj.get("stac_version") != "1.1.0":
            problems.append(f"{name} must declare STAC 1.1.0")
        if not isinstance(obj.get("links"), list):
            problems.append(f"{name} has no links array")
            continue
        for link in obj["links"]:
            if not isinstance(link, dict) or not isinstance(link.get("href"), str):
                problems.append(f"{name} contains malformed link")
                continue
            try:
                target = _resolve_local_href(link["href"], path, root)
            except ValueError as exc:
                problems.append(str(exc))
                continue
            if target is not None and not target.exists():
                problems.append(f"Missing linked file: {link['href']} from {path.relative_to(root)}")

    if catalog.get("type") != "Catalog" or collection.get("type") != "Collection":
        problems.append("Expected one STAC Catalog and one STAC Collection")
    catalog_link_pairs = {(link.get("rel"), link.get("href"), link.get("type"))
                          for link in catalog.get("links", []) if isinstance(link, dict)}
    if ("agents", "AGENTS.md", "text/markdown") not in catalog_link_pairs:
        problems.append("Root catalog must link AGENTS.md with rel=agents and text/markdown")
    if ("describedby", "README.md", "text/markdown") not in catalog_link_pairs:
        problems.append("Root catalog must link README.md with rel=describedby and text/markdown")
    if collection.get("license") != "CC-BY-4.0":
        problems.append("Collection license must preserve selected Zenodo CC BY 4.0 declaration")
    providers = collection.get("providers", [])
    hosts = [p for p in providers if isinstance(p, dict) and "host" in p.get("roles", [])]
    if len(hosts) != 1 or not providers or providers[-1] is not hosts[0]:
        problems.append("Exactly one designated host provider must appear last")
    elif hosts[0].get("name") != "Folia" or "pending" not in hosts[0].get("description", "").lower():
        problems.append("Final host provider must be Folia and state public hosting is pending")
    licensors = [p for p in providers if isinstance(p, dict) and "licensor" in p.get("roles", [])]
    if len(licensors) != 1 or "producer" not in licensors[0].get("roles", []) or "zenodo" in licensors[0].get("name", "").lower():
        problems.append("Source authors must carry producer/licensor roles; Zenodo is the archive record, not a licensor")
    if collection.get("portolan:version") != "0.2.0":
        problems.append("Collection must identify Portolan v0.2.0")

    assets = collection.get("assets")
    if not isinstance(assets, dict) or not assets:
        problems.append("Collection has no assets")
        assets = {}
    verified = 0
    for key, asset in assets.items():
        if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
            problems.append(f"Malformed asset {key}")
            continue
        try:
            path = _resolve_local_href(asset["href"], collection_path, root)
        except ValueError as exc:
            problems.append(f"Asset {key}: {exc}")
            continue
        if path is None:
            if "source" not in asset.get("roles", []):
                problems.append(f"Non-source asset {key} must be locally portable")
            continue
        if path is None or not path.is_file():
            problems.append(f"Missing local asset {key}: {asset['href']}")
            continue
        if asset.get("file:size") != path.stat().st_size:
            problems.append(f"Wrong file:size for asset {key}")
            continue
        expected_hash = "1220" + _sha256(path)
        if asset.get("file:checksum") != expected_hash:
            problems.append(f"Wrong file:checksum for asset {key}")
            continue
        verified += 1

    local_assets = [a for a in assets.values() if isinstance(a, dict) and "source" not in a.get("roles", [])]
    data_assets = [a for a in local_assets if "data" in a.get("roles", [])]
    if not data_assets:
        problems.append("No partitioned GeoParquet data assets are registered")
    if not any(a.get("type") == "application/vnd.pmtiles" and "visual" in a.get("roles", []) for a in local_assets):
        problems.append("Missing PMTiles visual derivative asset")
    tile_asset = next((a for a in local_assets if a.get("type") == "application/vnd.pmtiles" and "visual" in a.get("roles", [])), None)
    if tile_asset:
        tile_path = _resolve_local_href(tile_asset["href"], collection_path, root)
        if tile_path is not None:
            try:
                with tile_path.open("rb") as stream:
                    if stream.read(8) != b"PMTiles\x03":
                        problems.append("PMTiles asset is not a PMTiles v3 archive")
            except OSError as exc:
                problems.append(f"Cannot read PMTiles asset: {exc}")
    if not any(a.get("href") == "schema.json" for a in local_assets):
        problems.append("Missing field dictionary asset")
    if not any(a.get("href") == "attribute-codes.json" for a in local_assets):
        problems.append("Missing producer attribute-code dictionary asset")
    if not any(a.get("href") == "original-attribute-dictionary.xlsx"
               and a.get("type") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
               for a in local_assets):
        problems.append("Missing original producer attribute dictionary workbook")
    thumbnails = [a for a in local_assets if "thumbnail" in a.get("roles", [])]
    if len(thumbnails) != 1 or thumbnails[0].get("type") != "image/png":
        problems.append("Collection needs one PNG thumbnail asset")
    elif thumbnails[0].get("href"):
        thumbnail_path = _resolve_local_href(thumbnails[0]["href"], collection_path, root)
        if thumbnail_path is not None:
            try:
                with thumbnail_path.open("rb") as stream:
                    if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                        problems.append("Thumbnail asset is not a PNG image")
            except OSError as exc:
                problems.append(f"Cannot read PNG thumbnail: {exc}")

    try:
        quality = _read(root / "grip" / "quality.json")
        for field in ("road_classes", "vertices", "invalid_source_geometries_preserved"):
            if field not in quality:
                problems.append(f"Quality metadata omits {field}")
        extent_boxes = collection.get("extent", {}).get("spatial", {}).get("bbox", [])
        if (not extent_boxes or quality.get("stac_extent_bbox") != extent_boxes[0]
                or "analytic coordinates" not in quality.get("bbox_extent_note", "")):
            problems.append("STAC extent normalization is not documented or differs from quality metadata")
        layer = quality.get("display", {}).get("layer")
        pmtiles_links = [link for link in collection.get("links", []) if isinstance(link, dict) and link.get("rel") == "pmtiles"]
        if len(pmtiles_links) != 1 or pmtiles_links[0].get("pmtiles:layers") != [layer]:
            problems.append("PMTiles link layer differs from display summary")
        style_asset = next((a for a in local_assets if "style" in a.get("roles", [])), None)
        if style_asset:
            style_path = _resolve_local_href(style_asset["href"], collection_path, root)
            style = _read(style_path)
            source_layer = style.get("layers", [{}, {}])[-1].get("source-layer")
            if source_layer != layer:
                problems.append("MapLibre style source-layer differs from display summary")
            source_href = style.get("sources", {}).get("grip", {}).get("url")
            try:
                from catalog import resolve_style_pmtiles
                resolved = resolve_style_pmtiles(style_path, source_href, root)
                if tile_asset is None or resolved != _resolve_local_href(tile_asset["href"], collection_path, root):
                    problems.append("MapLibre relative source does not resolve to the registered PMTiles asset")
            except (TypeError, ValueError, FileNotFoundError) as exc:
                problems.append(f"MapLibre PMTiles source cannot be resolved: {exc}")
        else:
            problems.append("Missing MapLibre style asset")
    except (OSError, ValueError, IndexError, TypeError) as exc:
        problems.append(f"Invalid GRIP quality/style metadata: {exc}")

    # External extension schemas are deliberately not fetched during an offline release check.
    # A caller may provide a local schema directory for a full JSON Schema validation pass.
    validators = ["local-links-assets-metadata"]

    result = {"status": "passed" if not problems else "failed", "assets_verified": verified,
              "data_partitions": len(data_assets), "validators": validators, "problems": problems}
    if problems:
        raise ValueError(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="portable release root containing catalog.json")
    args = parser.parse_args()
    print(json.dumps(check_catalog(args.root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
