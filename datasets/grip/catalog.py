"""Build a portable STAC 1.1 / Portolan v0.2 catalog for GRIP4."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw


PORTOLAN_SCHEMA = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"
FILE_SCHEMA = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
TABLE_SCHEMA = "https://stac-extensions.github.io/table/v1.2.0/schema.json"
SCIENTIFIC_SCHEMA = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
VERSION_SCHEMA = "https://stac-extensions.github.io/version/v1.2.0/schema.json"
WEB_MAP_LINKS_SCHEMA = "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"
BBOX_TOLERANCE = 1e-8
PAPER_CITATION = (
    "Meijer, J. R., Huijbregts, M. A. J., Schotten, K. C. G. J., & Schipper, A. M. "
    "(2018). Global patterns of current and future road infrastructure. "
    "Environmental Research Letters, 13(6), 064006. "
    "https://doi.org/10.1088/1748-9326/aabd42"
)
PRODUCER_REGIONS = {
    "1": "North America",
    "2": "Central and South America",
    "3": "Africa",
    "4": "Europe",
    "5": "Middle East and Central Asia",
    "6": "South and East Asia",
    "7": "Oceania",
}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(path: Path, base: Path, media: str, roles: list[str], title: str) -> dict:
    return {
        "href": path.relative_to(base).as_posix(),
        "type": media,
        "roles": roles,
        "title": title,
        "file:size": path.stat().st_size,
        "file:checksum": "1220" + _sha256(path),
    }


def _stac_bbox(raw_bbox: list) -> list[float]:
    """Clamp only sub-tolerance geographic roundoff for valid STAC extents."""
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        raise ValueError("GRIP bbox must be [west, south, east, north]")
    try:
        bbox = [float(value) for value in raw_bbox]
    except (TypeError, ValueError) as exc:
        raise ValueError("GRIP bbox values must be numeric") from exc
    if not all(math.isfinite(value) for value in bbox):
        raise ValueError("GRIP bbox values must be finite")
    west, south, east, north = bbox
    if west > east or south > north:
        raise ValueError("GRIP bbox bounds are reversed")
    for value, minimum, maximum in ((west, -180.0, 180.0), (east, -180.0, 180.0),
                                    (south, -90.0, 90.0), (north, -90.0, 90.0)):
        if value < minimum - BBOX_TOLERANCE or value > maximum + BBOX_TOLERANCE:
            raise ValueError(f"GRIP bbox exceeds geographic limits by more than {BBOX_TOLERANCE}")
    return [max(-180.0, west), max(-90.0, south), min(180.0, east), min(90.0, north)]


def _preview(folder: Path, lines: list) -> bool:
    """Write a deterministic PNG sketch from supplied source-coordinate samples."""
    valid: list[list[tuple[int, int]]] = []
    for line in lines:
        points = []
        for point in line:
            if len(point) < 2:
                continue
            try:
                lon, lat = float(point[0]), float(point[1])
            except (TypeError, ValueError):
                continue
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                x = round((lon + 180) / 360 * 1199)
                y = round((90 - lat) / 180 * 599)
                points.append((x, y))
        if len(points) > 1:
            valid.append(points)
    if not valid:
        return False
    image = Image.new("RGB", (1200, 600), "#f3f6f5")
    draw = ImageDraw.Draw(image)
    draw.text((24, 18), "GRIP4 road sample — source-derived lines", fill="#17333a")
    for points in valid[:1200]:
        draw.line(points, fill="#16697a", width=1)
    image.save(folder / "thumbnail.png", format="PNG", optimize=False, compress_level=9)
    return True


def resolve_style_pmtiles(style_path: Path, source_href: str, root: Path) -> Path:
    """Resolve a relative style source to a local tile archive without adding a protocol."""
    from urllib.parse import urlparse, unquote

    parsed = urlparse(source_href)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("MapLibre style source must be a plain relative PMTiles path")
    path = unquote(parsed.path)
    if not path or "\\" in path or Path(path).is_absolute():
        raise ValueError("Unsafe MapLibre PMTiles source path")
    target = (Path(style_path).parent / path).resolve()
    try:
        target.relative_to(Path(root).resolve())
    except ValueError as exc:
        raise ValueError("MapLibre PMTiles source escapes release root") from exc
    if not target.is_file():
        raise FileNotFoundError(target)
    with target.open("rb") as stream:
        if stream.read(8) != b"PMTiles\x03":
            raise ValueError("Resolved style source is not a PMTiles v3 archive")
    return target


def build_catalog(root: Path, summary: dict, config: dict, revision: str) -> None:
    """Write local GRIP4 data dictionaries, documentation and STAC metadata.

    ``root`` is the portable release root. Analytic parquet partitions and the
    display PMTiles file are expected at ``root/grip/data/*.parquet`` and
    ``root/grip/grip.pmtiles`` respectively.
    """
    root = Path(root)
    folder = root / "grip"
    data_dir = folder / "data"
    partitions = sorted(p for p in data_dir.glob("*.parquet") if p.is_file())
    pmtiles = folder / "grip.pmtiles"
    if not partitions:
        raise FileNotFoundError(f"No GeoParquet partitions in {data_dir}")
    if not pmtiles.is_file():
        raise FileNotFoundError(pmtiles)
    style_path = folder / "styles" / "grip.json"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(style_path, {
        "version": 8,
        "name": "GRIP4 roads overview",
        "metadata": {"folia:display_notice": "Display derivative only; use GeoParquet for analysis."},
        "sources": {"grip": {"type": "vector", "url": "../grip.pmtiles", "attribution": "Meijer et al. (2018), CC BY 4.0; conversion by Folia"}},
        "layers": [{"id": "background", "type": "background", "paint": {"background-color": "#f3f6f5"}},
                   {"id": "roads", "type": "line", "source": "grip", "source-layer": summary["display"]["layer"],
                    "paint": {"line-color": "#16697a", "line-opacity": 0.72, "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.35, 8, 1.3, 13, 2.2]}}],
    })

    schema = summary["fields"]
    source_doi = config["source_doi"]
    source_link = config["source_url"]
    license_url = config["license_url"]
    paper_doi = config.get("paper_doi", "10.1088/1748-9326/aabd42")
    portolan = config.get("portolan_schema", PORTOLAN_SCHEMA)
    citation = PAPER_CITATION

    dictionary = {
        "title": config["title"],
        "source_doi": source_doi,
        "geometry_types": summary["geometry_types"],
        "fields": schema,
        "partitioning": {"format": "GeoParquet", "path": "data/*.parquet", "partition_count": len(partitions)},
    }
    _write_json(folder / "schema.json", dictionary)
    quality = {
        "status": "conversion_summary_only",
        "rows": summary["rows"],
        "bbox": summary["bbox"],
        "stac_extent_bbox": _stac_bbox(summary["bbox"]),
        "bbox_extent_note": "STAC extent clamps only sub-1e-8 degree floating-point overshoot to geographic limits; analytic coordinates and the raw bbox above are unchanged.",
        "geometry_types": summary["geometry_types"],
        "invalid_source_geometries_preserved": summary.get("invalid_source_geometries_preserved"),
        "vertices": summary.get("vertices"),
        "regions": summary["regions"],
        "road_classes": summary.get("road_classes", {}),
        "null_counts": summary["null_counts"],
        "display": summary["display"],
        "validation_limits": [
            "The full source archive checksum, source schema, feature count and source-to-output feature parity must be verified independently.",
            "No GEE comparison or cloud export was run for this release.",
            "No independent observational validation of producer data or model outputs is claimed.",
            "GRIP4 is a historical research inventory and is not suitable for current navigation.",
        ],
    }
    _write_json(folder / "quality.json", quality)

    has_preview = _preview(folder, summary.get("preview_lines", []))
    if not has_preview:
        raise ValueError("A source-derived preview_lines sample is required for the collection thumbnail")
    extent = {"spatial": {"bbox": [_stac_bbox(summary["bbox"])]}, "temporal": {"interval": [[None, None]]}}
    extensions = [portolan, FILE_SCHEMA, TABLE_SCHEMA, SCIENTIFIC_SCHEMA, VERSION_SCHEMA, WEB_MAP_LINKS_SCHEMA]
    links = [
        {"rel": "root", "href": "../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
        {"rel": "agents", "href": "AGENTS.md", "type": "text/markdown"},
        {"rel": "license", "href": license_url, "type": "text/html"},
        {"rel": "via", "href": f"https://doi.org/{source_doi}", "type": "text/html"},
        {"rel": "cite-as", "href": f"https://doi.org/{paper_doi}", "type": "text/html"},
        {"rel": "pmtiles", "href": "grip.pmtiles", "type": "application/vnd.pmtiles", "pmtiles:layers": [summary["display"]["layer"]]},
    ]
    assets = {
        f"data-{i:03d}": _asset(path, folder, "application/vnd.apache.parquet", ["data"], f"Complete analytic GeoParquet partition {path.name}")
        for i, path in enumerate(partitions, 1)
    }
    assets.update({
        "tiles": _asset(pmtiles, folder, "application/vnd.pmtiles", ["visual"], "Simplified and thinned road display tiles; not for analytics"),
        "style": _asset(style_path, folder, "application/vnd.mapbox.style+json", ["style", "default"], "MapLibre style for the PMTiles display derivative"),
        "schema": _asset(folder / "schema.json", folder, "application/json", ["metadata"], "Complete field dictionary"),
        "attribute-codes": _asset(folder / "attribute-codes.json", folder, "application/json", ["metadata"], "Producer attribute code dictionary"),
        "quality": _asset(folder / "quality.json", folder, "application/json", ["metadata"], "Conversion summary and validation limits"),
        "original-attribute-dictionary": _asset(
            folder / "original-attribute-dictionary.xlsx", folder,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ["metadata"], "Original GRIP4 producer attribute dictionary workbook",
        ),
    })
    assets["thumbnail"] = _asset(folder / "thumbnail.png", folder, "image/png", ["thumbnail"], "Deterministic sketch of sampled source road geometries")
    assets["source"] = {
        "href": source_link,
        "type": "application/zip",
        "roles": ["source"],
        "title": "Pinned GRIP4 global vector File Geodatabase archive",
        "file:size": config["source_size"],
        "file:checksum": "1220" + config["source_sha256"],
    }

    regions = ", ".join(f"{PRODUCER_REGIONS.get(str(k), str(k))}: {v:,}" for k, v in sorted(summary["regions"].items(), key=lambda x: str(x[0])))
    description = (
        f"Complete global GRIP4 roads inventory, version 4 (2018), represented as partitioned GeoParquet. "
        f"The conversion summary contains {summary['rows']:,} features across all seven producer regions ({regions}). "
        "GeoParquet is the analytic source of truth in this bundle. PMTiles is a simplified and thinned display derivative; "
        "its coverage and geometry are not suitable for network analysis, counts, routing, or absence claims. "
        "This is a historical research inventory, not a current navigation dataset."
    )
    collection = {
        "type": "Collection", "stac_version": "1.1.0", "stac_extensions": extensions,
        "id": config["id"], "title": config["title"], "description": description,
        "license": "CC-BY-4.0", "version": config["release"],
        "created": config["metadata_timestamp"], "updated": config["metadata_timestamp"],
        "extent": extent,
        "providers": [
            {"name": "Meijer, Huijbregts, Schotten and Schipper", "roles": ["producer", "licensor"], "url": f"https://doi.org/{paper_doi}"},
            {"name": "Folia", "roles": ["processor", "host"], "url": "https://folia.sh",
             "description": "Designated host provider for this prepared catalog. Public hosting and Portolan submission are pending."},
        ],
        "sci:doi": source_doi, "sci:citation": citation,
        "keywords": ["GRIP4", "roads", "global", "road infrastructure", "transportation", "research data", "2018"],
        "table:columns": [{k: f[k] for k in ("name", "type", "description")} for f in schema],
        "links": links,
        "assets": assets,
        "portolan:version": "0.2.0",
        "portolan:status": "prepared-local",
        "portolan:revision": revision,
    }
    _write_json(folder / "collection.json", collection)
    _write_json(root / "catalog.json", {
        "type": "Catalog", "stac_version": "1.1.0", "stac_extensions": [portolan],
        "id": "folia-grip4-global", "title": config["title"], "description": description,
        "created": config["metadata_timestamp"], "updated": config["metadata_timestamp"],
        "links": [
            {"rel": "root", "href": "catalog.json", "type": "application/json"},
            {"rel": "child", "href": "grip/collection.json", "type": "application/json", "title": config["title"]},
            {"rel": "agents", "href": "AGENTS.md", "type": "text/markdown"},
            {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
            {"rel": "license", "href": license_url, "type": "text/html"},
            {"rel": "via", "href": f"https://doi.org/{source_doi}", "type": "text/html"},
        ],
    })

    field_rows = "\n".join(f"| `{f['name']}` | `{f['type']}` | {f['description']} |" for f in schema)
    provenance = (
        f"The selected [Zenodo archive record](https://zenodo.org/records/{source_doi.rsplit('.', 1)[-1]}) has a structured license field declaring CC BY 4.0, while the same record's prose description also mentions CC0. "
        f"DOI [https://doi.org/{source_doi}](https://doi.org/{source_doi}). PBL's [producer page](https://dataportaal.pbl.nl/GRIP4) "
        "separately states CC0. This catalog follows the selected record's structured CC BY 4.0 license field and preserves author attribution pending clarification.\n\n"
        f"{citation}\n\nConversion source revision: `{revision}`. No public hosting, registry submission, cloud export, or GEE validation is claimed."
    )
    (root / "README.md").write_text(
        f"# {config['title']}\n\n{description}\n\nThe complete analytic data are in [partitioned GeoParquet](grip/README.md); "
        "[catalog.json](catalog.json) is a portable relative-link STAC catalog.\n\n## Provenance and license\n\n" + provenance + "\n"
    )
    (folder / "README.md").write_text(
        f"# {config['title']}\n\n{description}\n\n"
        "Use all `data/*.parquet` partitions for analysis. They retain the complete converted road feature set and source attributes. "
        "The `grip.pmtiles` file is a simplified and thinned display derivative with quantized tile coordinates; it does not preserve "
        "complete analytic geometry or all features at every zoom. Do not calculate network metrics, feature counts, or coverage/absence from PMTiles.\n\n"
        f"Summary: {summary['rows']:,} rows; geometry types: {', '.join(summary['geometry_types'])}; "
        f"{summary.get('vertices', 0):,} vertices; {summary.get('invalid_source_geometries_preserved', 0):,} invalid source geometries preserved; raw bbox: `{summary['bbox']}`. "
        "The STAC extent clamps only sub-1e-8 degree roundoff at the geographic boundary; source coordinates and raw bounds remain unchanged.\n\n"
        "Producer attribute codes and their descriptions are in [attribute-codes.json](attribute-codes.json), derived from the included [original dictionary workbook](original-attribute-dictionary.xlsx). "
        f"Source identifier `{config.get('fid_column', 'producer ID')}` is retained as a producer field; no synthetic `source_row` identifier is added.\n\n"
        "[MapLibre style](styles/grip.json) stores the relative source path `../grip.pmtiles`. Before using it, resolve that path against the style URL, register the PMTiles protocol, then set the source URL to `pmtiles://` plus the resolved tile archive URL. The style file does not resolve PMTiles URLs by itself.\n\n"
        "| Field | Arrow type | Description |\n|---|---|---|\n" + field_rows + "\n\n"
        "The source archive is the complete GRIP4 global File Geodatabase, covering all seven regions. The original source feature count "
        "was reported as 25,758,453 by the community catalog; that reported figure is not itself source verification. See `quality.json` "
        "for summary and unresolved validation limits. This is a static 2018-era research inventory, not a current road map or navigation network.\n\n"
        "## Provenance and license\n\n" + provenance + "\n"
    )
    guidance = (
        "# Dataset guidance for agents\n\nUse every partition in `data/*.parquet` for analysis. `grip.pmtiles` is a simplified and thinned display derivative; "
        "it is not complete analytic geometry and must not be used for counts, routing, network metrics, or coverage/absence conclusions.\n\n"
        "The archive is GRIP4 global roads, version 4 (2018), and includes all seven producer regions. It is historical research data, not a current navigation network. "
        "Preserve source geometry, attributes, identifiers, feature multiplicity, and nulls. No GEE/cloud comparison or independent observational validation is asserted.\n\n"
        "The pinned Zenodo archive declares CC BY 4.0. The PBL producer page separately says CC0; retain the selected archive's CC BY attribution requirements. "
        "Public Folia hosting and Portolan submission are pending.\n"
    )
    (root / "AGENTS.md").write_text(guidance)
    (folder / "AGENTS.md").write_text(guidance)
    (root / "LICENSE.txt").write_text(
        f"GRIP4 selected archive and derived data: Creative Commons Attribution 4.0 International (CC BY 4.0), following the structured license field of the selected Zenodo record.\n{license_url}\n\n"
        f"Source DOI: https://doi.org/{source_doi}\n{citation}\n\n"
        "The selected Zenodo record's prose description also mentions CC0, as does PBL's producer page. This release follows the record's structured CC BY 4.0 field and retains attribution pending clarification.\n"
        "Changes: conversion to partitioned GeoParquet, display-only PMTiles derivative, metadata and documentation.\n"
    )
