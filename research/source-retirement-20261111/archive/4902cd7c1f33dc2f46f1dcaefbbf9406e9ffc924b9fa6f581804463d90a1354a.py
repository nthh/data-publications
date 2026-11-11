#!/usr/bin/env python3
"""Prepare a local runtime object manifest from canonical records and an upload plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import posixpath
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml


DEFAULT_PLAN = "research/source-products-20261101/staging-r2/immutable-upload-plan.json"
DEFAULT_GEE = "research/pmtiles-all-20261102/gee-validation.json"
DATASET_IDS = (
    "grwl",
    "river-plastic-inputs",
    "hydrolakes",
    "free-flowing-rivers",
    "lakeatlas",
    "gdw",
    "swot_prior_lake_database",
)
REGIONS = [
    {"id": "global", "label": "Global", "bbox": [-170, -55, 175, 80]},
    {"id": "north_america", "label": "North America", "bbox": [-93, 47, -87, 50]},
    {"id": "atlantic_coast", "label": "Atlantic coast", "bbox": [-82, 25, -66, 45]},
    {"id": "dateline", "label": "Dateline", "bbox": [178.8, 67.85, 180, 68.01]},
    {"id": "europe", "label": "Europe", "bbox": [5, 45, 15, 55]},
    {"id": "southwest_europe", "label": "Southwest Europe", "bbox": [5, 45, 7.5, 47.5]},
    {"id": "south_america", "label": "South America", "bbox": [-65, -5, -60, 0]},
    {"id": "asia", "label": "Asia", "bbox": [100, 25, 110, 35]},
    {"id": "oceania", "label": "Oceania", "bbox": [140, -40, 150, -30]},
]


class PrepareError(ValueError):
    """Raised when the plan, source files, or canonical metadata is unsafe/inconsistent."""


DISPLAY_RELEASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _display_release(value: Any, dataset_id: str) -> str:
    if not isinstance(value, str) or len(value) > 40 or not DISPLAY_RELEASE_RE.fullmatch(value):
        raise PrepareError(f"{dataset_id}: canonical display release is not a safe version slug")
    return value


def _validate_display_style(style_path: Path, style_rel: str, asset: dict[str, Any], dataset_id: str) -> tuple[str, str]:
    source_layer, geometry = _read_style(style_path)
    try:
        style = json.loads(style_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrepareError(f"{dataset_id}: invalid display style {style_rel}: {exc}") from exc
    if not isinstance(style, dict) or style.get("version") != 8:
        raise PrepareError(f"{dataset_id}: display style must be MapLibre style v8: {style_rel}")
    sources = style.get("sources")
    data_source = sources.get("data") if isinstance(sources, dict) else None
    url = data_source.get("url") if isinstance(data_source, dict) else None
    if not isinstance(data_source, dict) or data_source.get("type") != "vector" or not isinstance(url, str) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", url):
        raise PrepareError(f"{dataset_id}: display style requires vector sources.data.url as a plain relative path: {style_rel}")
    relative = url
    if not relative or relative.startswith("/") or "?" in relative or "#" in relative:
        raise PrepareError(f"{dataset_id}: unsafe PMTiles URL in display style: {url}")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(style_rel), relative))
    resolved = _safe_route(resolved)
    if resolved != asset.get("path"):
        raise PrepareError(f"{dataset_id}: display style URL does not resolve to asset path: {url}")
    if source_layer != asset.get("source_layer"):
        raise PrepareError(f"{dataset_id}: display style source-layer disagrees with asset metadata")
    expected_geometry = asset.get("geometry_type")
    expected_style_types = {"polygon": {"fill"}, "line": {"line"}, "point": {"circle", "symbol"}}.get(expected_geometry)
    layers = style.get("layers")
    matches = [layer for layer in layers if isinstance(layer, dict)
               and layer.get("source") == "data" and layer.get("source-layer") == asset.get("source_layer")
               and layer.get("type") in expected_style_types] if isinstance(layers, list) and expected_style_types else []
    if not matches:
        raise PrepareError(f"{dataset_id}: display style has no matching source-layer/type: {style_rel}")
    return source_layer, geometry


def _mapping(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PrepareError(f"{description} must be an object")
    return value


def _safe_route(route: str) -> str:
    if not isinstance(route, str) or not route or "\\" in route or "\x00" in route:
        raise PrepareError(f"invalid object route: {route!r}")
    path = PurePosixPath(route)
    if path.is_absolute() or any(part in ("", ".", "..") for part in route.split("/")):
        raise PrepareError(f"unsafe object route: {route!r}")
    return path.as_posix()


def _resolve_regular_file(base: Path, candidate: Path) -> Path:
    """Resolve a source while rejecting symlinks in every component."""
    candidate = candidate if candidate.is_absolute() else base / candidate
    if base.is_symlink():
        raise PrepareError(f"symlink source directory is not allowed: {base}")
    try:
        relative = candidate.absolute().relative_to(base.absolute())
    except ValueError as exc:
        raise PrepareError(f"source escapes its package/repository root: {candidate}") from exc
    current = base.absolute()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PrepareError(f"symlink source is not allowed: {current}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PrepareError(f"planned source file is missing: {candidate}") from exc
    if not resolved.is_file():
        raise PrepareError(f"planned source is not a regular file: {candidate}")
    return resolved


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _load_records(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for dataset_id in DATASET_IDS:
        path = root / "datasets" / dataset_id / "dataset.yaml"
        try:
            record = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PrepareError(f"cannot read canonical record {path}: {exc}") from exc
        record = _mapping(record, f"canonical record {dataset_id}")
        if record.get("id") != dataset_id:
            raise PrepareError(f"canonical record ID mismatch at {path}")
        publication = _mapping(record.get("publication"), f"{dataset_id}.publication")
        if not publication.get("source_coop"):
            raise PrepareError(f"{dataset_id} has no publication.source_coop record")
        records[dataset_id] = record
    return records


def _selected_releases(records: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    return {
        dataset_id: _mapping(records[dataset_id].get("publication"), "publication").get("release")
        for dataset_id in DATASET_IDS
    }


def _validate_plan_products(
    plan: dict[str, Any], records: dict[str, dict[str, Any]], releases: dict[str, str | None]
) -> tuple[dict[str, str], dict[str, str]]:
    products = plan.get("products")
    if not isinstance(products, list):
        raise PrepareError("upload plan products must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for item in products:
        item = _mapping(item, "plan product")
        dataset_id = item.get("dataset_id")
        if dataset_id in by_id:
            raise PrepareError(f"duplicate product in upload plan: {dataset_id}")
        by_id[dataset_id] = item
    expected_ids = set(DATASET_IDS[:5])
    if set(by_id) != expected_ids:
        raise PrepareError(
            f"upload plan products do not match prepared viewer records: expected={sorted(expected_ids)}, actual={sorted(by_id)}"
        )
    product_ids: dict[str, str] = {}
    owners_by_product: dict[str, str] = {}
    for dataset_id in DATASET_IDS[:5]:
        canonical = records[dataset_id]["publication"]["source_coop"]
        staged = by_id[dataset_id]
        expected_product = canonical.get("product_id")
        expected_owner = canonical.get("owner")
        if not expected_product or not expected_owner:
            raise PrepareError(f"{dataset_id} canonical source_coop owner/product_id is missing")
        checks = {
            "release": releases[dataset_id],
            "owner": expected_owner,
            "product_id": expected_product,
        }
        for field, expected in checks.items():
            if staged.get(field) != expected:
                raise PrepareError(
                    f"upload plan {field} mismatch for {dataset_id}: canonical={expected!r}, plan={staged.get(field)!r}"
                )
        if staged.get("bucket") != expected_owner:
            raise PrepareError(
                f"upload plan bucket mismatch for {dataset_id}: canonical owner={expected_owner!r}, plan={staged.get('bucket')!r}"
            )
        product_ids[dataset_id] = expected_product
        owners_by_product[expected_product] = expected_owner
    return product_ids, owners_by_product


def _parse_packages(package_args: list[str]) -> dict[str, Path]:
    packages: dict[str, Path] = {}
    for item in package_args:
        dataset_id, separator, path = item.partition("=")
        if not separator or not dataset_id or not path:
            raise PrepareError(f"--package must have the form ID=PATH: {item!r}")
        if dataset_id in packages:
            raise PrepareError(f"duplicate --package for {dataset_id}")
        packages[dataset_id] = Path(path)
    return packages


def _planned_files(
    plan: dict[str, Any],
    root: Path,
    records: dict[str, dict[str, Any]],
    releases: dict[str, str | None],
    product_ids: dict[str, str],
    owners_by_product: dict[str, str],
    packages: dict[str, Path],
    display_packages: dict[str, Path] | None = None,
) -> list[tuple[str, dict[str, Any], Path]]:
    display_packages = display_packages or {}
    files = plan.get("files")
    if not isinstance(files, list):
        raise PrepareError("upload plan files must be an array")
    mapped: list[tuple[str, dict[str, Any], Path]] = []
    seen_routes: set[str] = set()
    seen_sources: set[Path] = set()
    for entry in files:
        entry = _mapping(entry, "plan file entry")
        route = _safe_route(entry.get("object_key"))
        if route in seen_routes:
            raise PrepareError(f"duplicate planned object route: /nthh/{route}")
        seen_routes.add(route)
        source = _mapping(entry.get("source"), f"source for {route}")
        kind = source.get("kind")
        if kind == "package":
            dataset_id = source.get("dataset_id")
            if dataset_id not in releases:
                raise PrepareError(f"unknown planned package dataset ID: {dataset_id!r}")
            release = releases.get(dataset_id)
            expected_prefix = f"{product_ids.get(dataset_id, '')}/releases/{release}/"
            if not release or not route.startswith(expected_prefix):
                raise PrepareError(f"planned package route does not match selected product release: {route}")
            expected_bucket = owners_by_product[product_ids[dataset_id]]
            if dataset_id not in packages:
                raise PrepareError(f"missing --package {dataset_id}=PATH for planned release")
            rel_source = _safe_route(source.get("path"))
            source_base = packages[dataset_id]
            candidate = source_base / Path(*PurePosixPath(rel_source).parts)
        elif kind == "display_package":
            dataset_id = source.get("dataset_id")
            if dataset_id not in releases:
                raise PrepareError(f"unknown planned display dataset ID: {dataset_id!r}")
            display_ref = (records[dataset_id].get("publication") or {}).get("display")
            if not isinstance(display_ref, dict):
                raise PrepareError(f"{dataset_id}: plan includes a display package without a canonical display binding")
            if dataset_id not in display_packages:
                raise PrepareError(f"missing --display-package {dataset_id}=PATH for planned display release")
            display_release = _display_release(display_ref.get("release"), dataset_id)
            expected_prefix = f"{product_ids[dataset_id]}/display/{display_release}/"
            if not route.startswith(expected_prefix):
                raise PrepareError(f"planned display route does not match selected display release: {route}")
            rel_source = _safe_route(source.get("path"))
            if route != expected_prefix + rel_source:
                raise PrepareError(f"planned display route/path mismatch: {route}")
            expected_bucket = owners_by_product[product_ids[dataset_id]]
            source_base = display_packages[dataset_id]
            candidate = source_base / Path(*PurePosixPath(rel_source).parts)
        elif kind == "repository":
            # Repository-backed planned supplements are attached under the selected products.
            product_id = next(
                (value for value in product_ids.values() if route.startswith(f"{value}/")), None
            )
            if not product_id:
                continue
            expected_bucket = owners_by_product[product_id]
            rel_source = _safe_route(source.get("path"))
            source_base = root
            candidate = root / Path(*PurePosixPath(rel_source).parts)
        else:
            raise PrepareError(f"unsupported source kind for {route}: {kind!r}")
        if entry.get("bucket") != expected_bucket:
            raise PrepareError(
                f"planned object bucket mismatch for {route}: canonical owner={expected_bucket!r}, plan={entry.get('bucket')!r}"
            )
        file_path = _resolve_regular_file(source_base, candidate)
        if file_path in seen_sources:
            raise PrepareError(f"multiple object routes map to the same file: {file_path}")
        seen_sources.add(file_path)
        expected_size = entry.get("size_bytes")
        expected_hash = entry.get("sha256")
        actual_size, actual_hash = _hash_file(file_path)
        if actual_size != expected_size:
            raise PrepareError(f"size mismatch for {route}: plan={expected_size}, actual={actual_size}")
        if actual_hash != expected_hash:
            raise PrepareError(f"SHA-256 mismatch for {route}: plan={expected_hash}, actual={actual_hash}")
        mapped.append((route, entry, file_path))
    # Every prepared product must have at least one exact release object in the plan.
    for dataset_id in DATASET_IDS[:5]:
        release = releases.get(dataset_id)
        product_id = product_ids[dataset_id]
        if not release or not any(route.startswith(f"{product_id}/releases/{release}/") for route, _, _ in mapped):
            raise PrepareError(f"upload plan has no files for selected release {dataset_id}/{release}")
    return mapped


def _validate_display_bindings(
    root: Path,
    records: dict[str, dict[str, Any]],
    releases: dict[str, str | None],
    product_ids: dict[str, str],
    mapped: list[tuple[str, dict[str, Any], Path]],
    packages: dict[str, Path],
    display_packages: dict[str, Path],
    legacy_plan: bool = False,
) -> dict[str, dict[str, Any]]:
    by_dataset: dict[str, dict[str, tuple[str, dict[str, Any], Path]]] = {}
    for route, entry, path in mapped:
        source = entry.get("source", {})
        if source.get("kind") == "display_package":
            by_dataset.setdefault(source["dataset_id"], {})[source["path"]] = (route, entry, path)
    manifests: dict[str, dict[str, Any]] = {}
    for dataset_id, planned in by_dataset.items():
        reference = (records[dataset_id].get("publication") or {}).get("display")
        if not isinstance(reference, dict):
            raise PrepareError(f"{dataset_id}: canonical display binding is missing")
        reference_release = _display_release(reference.get("release"), dataset_id)
        expected_manifest_path = f"datasets/{dataset_id}/display/{reference_release}/manifest.json"
        if reference.get("manifest_path") != expected_manifest_path:
            raise PrepareError(f"{dataset_id}: canonical display manifest path must be {expected_manifest_path}")
        manifest_entry = planned.get("manifest.json")
        if manifest_entry is None:
            raise PrepareError(f"{dataset_id}: display plan has no manifest.json")
        manifest_path = manifest_entry[2]
        if _hash_file(manifest_path)[1] != reference.get("manifest_sha256"):
            raise PrepareError(f"{dataset_id}: display manifest SHA-256 differs from canonical pin")
        canonical_path = root / reference.get("manifest_path", "")
        canonical_file = _resolve_regular_file(root, canonical_path)
        if _hash_file(canonical_file)[1] != reference.get("manifest_sha256"):
            raise PrepareError(f"{dataset_id}: tracked display manifest differs from canonical pin")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PrepareError(f"{dataset_id}: cannot read display manifest: {exc}") from exc
        if not isinstance(manifest, dict):
            raise PrepareError(f"{dataset_id}: display manifest must be an object")
        for field, expected in (("schema_version", 1), ("dataset_id", dataset_id),
                                ("display_release", reference_release),
                                ("analytic_release", releases[dataset_id]), ("status", "prepared")):
            if manifest.get(field) != expected:
                raise PrepareError(f"{dataset_id}: display manifest {field} mismatch")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(planned) != set(files) | {"manifest.json"}:
            raise PrepareError(f"{dataset_id}: planned display files do not match display manifest inventory")
        for rel, declaration in files.items():
            if not isinstance(declaration, dict) or rel not in planned:
                raise PrepareError(f"{dataset_id}: invalid display file declaration: {rel}")
            entry = planned[rel][1]
            if (declaration.get("sha256") != entry.get("sha256")
                    or declaration.get("size_bytes") != entry.get("size_bytes")):
                raise PrepareError(f"{dataset_id}: display file plan differs from manifest: {rel}")
        analytic_paths = {}
        for route, entry, path in mapped:
            source = entry.get("source", {})
            if source.get("kind") == "package" and source.get("dataset_id") == dataset_id:
                analytic_paths[source.get("path")] = (entry, path)
        assets = manifest.get("assets")
        if not isinstance(assets, list) or not assets:
            raise PrepareError(f"{dataset_id}: display manifest assets must be a non-empty array")
        seen_asset_ids: set[str] = set()
        for asset in assets:
            if not isinstance(asset, dict):
                raise PrepareError(f"{dataset_id}: display asset must be an object")
            asset_id = asset.get("id")
            if not isinstance(asset_id, str) or not asset_id or asset_id in seen_asset_ids:
                raise PrepareError(f"{dataset_id}: invalid display asset ID (missing or duplicate): {asset_id!r}")
            seen_asset_ids.add(asset_id)
            for field in ("path", "style_path"):
                rel = asset.get(field)
                if not isinstance(rel, str) or rel not in files:
                    raise PrepareError(f"{dataset_id}: display asset requires declared {field}: {rel!r}")
            asset_path = asset["path"]
            if not asset_path.lower().endswith(".pmtiles"):
                raise PrepareError(f"{dataset_id}: display asset path must name a PMTiles file")
            asset_size, asset_hash = asset.get("size_bytes"), asset.get("sha256")
            declaration = files[asset_path]
            if (not isinstance(declaration, dict) or not isinstance(asset_size, int) or isinstance(asset_size, bool)
                    or asset_size < 0 or not isinstance(asset_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", asset_hash)
                    or declaration.get("size_bytes") != asset_size or declaration.get("sha256") != asset_hash):
                raise PrepareError(f"{dataset_id}: display asset metadata disagrees with file declaration: {asset_path}")
            source_layer = asset.get("source_layer")
            geometry_type = asset.get("geometry_type")
            id_field = asset.get("id_field")
            min_zoom, max_zoom = asset.get("min_zoom"), asset.get("max_zoom")
            if not isinstance(source_layer, str) or not source_layer:
                raise PrepareError(f"{dataset_id}: display asset source_layer is required")
            if geometry_type not in ("polygon", "line", "point"):
                raise PrepareError(f"{dataset_id}: invalid display asset geometry_type")
            if not isinstance(id_field, str) or not id_field:
                raise PrepareError(f"{dataset_id}: display asset id_field is required")
            if (not isinstance(min_zoom, int) or isinstance(min_zoom, bool) or not 0 <= min_zoom <= 30
                    or not isinstance(max_zoom, int) or isinstance(max_zoom, bool) or not min_zoom <= max_zoom <= 30):
                raise PrepareError(f"{dataset_id}: invalid display asset zoom range")
            _validate_display_style(planned[asset["style_path"]][2], asset["style_path"], asset, dataset_id)
            source_asset = asset.get("source_asset")
            if not isinstance(source_asset, dict):
                raise PrepareError(f"{dataset_id}: display asset lacks source_asset binding")
            source_path = source_asset.get("path")
            analytical = analytic_paths.get(source_path)
            if (analytical is None or source_asset.get("sha256") != analytical[0].get("sha256")
                    or source_asset.get("size_bytes") != analytical[0].get("size_bytes")):
                raise PrepareError(f"{dataset_id}: display asset source identity mismatches analytical plan: {source_path}")
        manifests[dataset_id] = manifest
    required = {
        dataset_id for dataset_id in DATASET_IDS[:5]
        if isinstance((records[dataset_id].get("publication") or {}).get("display"), dict)
    }
    missing = required - set(by_dataset)
    if legacy_plan:
        missing = set()
    if missing:
        raise PrepareError(f"canonical display packages are missing from upload plan: {sorted(missing)}")
    extra_packages = set(display_packages) - required
    if extra_packages:
        raise PrepareError(f"--display-package overrides have no canonical display reference: {sorted(extra_packages)}")
    return manifests


def _object_path(route: str) -> str:
    return f"/nthh/{route}"


def _content_type(entry: dict[str, Any], path: Path) -> str:
    value = entry.get("content_type")
    if isinstance(value, str) and value:
        return value
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _asset_for(route: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "object_path": _object_path(route),
        "size_bytes": entry["size_bytes"],
        "sha256": entry["sha256"],
    }


def _read_parquet(path: Path) -> tuple[dict[str, Any], list[str], int]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    metadata = schema.metadata or {}
    try:
        geo = json.loads(metadata[b"geo"])
    except (KeyError, ValueError, TypeError) as exc:
        raise PrepareError(f"GeoParquet metadata is missing or invalid: {path}") from exc
    primary = geo.get("primary_column")
    columns = geo.get("columns", {})
    column = columns.get(primary) if isinstance(columns, dict) else None
    if not primary or not isinstance(column, dict):
        raise PrepareError(f"GeoParquet primary geometry column is missing: {path}")
    covering = column.get("covering")
    bbox_cover = covering.get("bbox") if isinstance(covering, dict) else None
    if not isinstance(bbox_cover, dict) or not all(axis in bbox_cover for axis in ("xmin", "ymin", "xmax", "ymax")):
        raise PrepareError(f"GeoParquet covering bbox is required for large viewer assets: {path}")
    for axis, field_path in bbox_cover.items():
        parts = field_path if isinstance(field_path, list) else str(field_path).split(".")
        if len(parts) < 2 or parts[-1] != axis or parts[0] not in schema.names:
            raise PrepareError(f"GeoParquet covering path for {axis} is invalid: {field_path!r} in {path}")
    geometry_types = column.get("geometry_types")
    if not isinstance(geometry_types, list) or len(geometry_types) != 1:
        raise PrepareError(f"expected one GeoParquet geometry type in {path}")
    geometry_type = str(geometry_types[0]).lower()
    for normalized in ("polygon", "line", "point"):
        if normalized in geometry_type:
            geometry_type = normalized
            break
    else:
        raise PrepareError(f"unsupported geometry type {geometry_types!r} in {path}")
    bbox = column.get("bbox")
    if not isinstance(bbox, list) or len(bbox) < 4:
        raise PrepareError(f"GeoParquet bbox is missing: {path}")
    covering_names = {str(part) for value in bbox_cover.values() for part in (value if isinstance(value, list) else [])}
    excluded = {primary, "bbox"}
    excluded.update(name for name in schema.names if name in covering_names)
    fields = [name for name in schema.names if name not in excluded]
    id_field = _choose_id_field(schema.names)
    return (
        {
            "geometry_column": primary,
            "geometry_type": geometry_type,
            "id_field": id_field,
            "fields": fields,
            "decimal_fields": [field.name for field in schema if pa.types.is_decimal(field.type)],
            "bbox": [float(v) for v in bbox[:4]],
            "row_count": int(parquet.metadata.num_rows),
            "covering": {axis: f"bbox.{axis}" for axis in ("xmin", "ymin", "xmax", "ymax")},
        },
        schema.names,
        int(parquet.metadata.num_rows),
    )


def _choose_id_field(names: list[str]) -> str:
    lookup = {name.casefold(): name for name in names}
    for option in ("objectid", "hylak_id", "source_id", "id", "fid", "lake_id", "reach_id"):
        if option in lookup:
            return lookup[option]
    raise PrepareError(f"no recognized feature identifier field in schema: {names!r}")


def _read_style(path: Path) -> tuple[str, str]:
    try:
        style = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrepareError(f"invalid PMTiles style JSON {path}: {exc}") from exc
    layers = style.get("layers") if isinstance(style, dict) else None
    if not isinstance(layers, list):
        raise PrepareError(f"PMTiles style has no layers: {path}")
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        source_layer = layer.get("source-layer") or layer.get("source_layer")
        kind = layer.get("type")
        if not source_layer:
            continue
        geometry = {"line": "line", "fill": "polygon", "circle": "point", "symbol": "point"}.get(kind)
        if geometry:
            return str(source_layer), geometry
    raise PrepareError(f"PMTiles style has no supported source-layer/type: {path}")


def _release_bbox(assets: list[tuple[str, dict[str, Any], Path]]) -> list[float] | None:
    for route, _, path in assets:
        if path.name not in ("collection.json", "metadata.json"):
            continue
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        candidates = [metadata.get("bbox")]
        extent = metadata.get("extent")
        if isinstance(extent, dict):
            candidates.extend(extent.get("spatial", {}).get("bbox", []))
        for candidate in candidates:
            if isinstance(candidate, list) and len(candidate) == 4:
                return [float(value) for value in candidate]
    return None


def _gee_by_dataset(root: Path, evidence_path: str | None, releases: dict[str, str | None]) -> dict[str, dict[str, Any]]:
    not_audited = {
        "status": "not_audited",
        "summary": "GEE evidence was not available; no validation claim is made.",
        "evidence": [],
    }
    if not evidence_path:
        return {dataset_id: not_audited.copy() for dataset_id in DATASET_IDS}
    path = root / evidence_path
    if not path.is_file():
        return {dataset_id: not_audited.copy() for dataset_id in DATASET_IDS}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrepareError(f"invalid GEE evidence JSON {path}: {exc}") from exc
    rows = report.get("datasets") if isinstance(report, dict) else None
    if not isinstance(rows, list):
        raise PrepareError("GEE evidence must contain a datasets array")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        dataset_id = row.get("dataset_id", row.get("id"))
        if dataset_id in by_id:
            raise PrepareError(f"duplicate GEE evidence dataset entry: {dataset_id}")
        by_id[dataset_id] = row
    output: dict[str, dict[str, Any]] = {}
    for dataset_id in DATASET_IDS:
        row = by_id.get(dataset_id)
        if row is None:
            output[dataset_id] = not_audited.copy()
            continue
        selected = row.get("selected_release", row.get("current_release"))
        if selected != releases[dataset_id]:
            raise PrepareError(
                f"GEE evidence release mismatch for {dataset_id}: report={selected!r}, selected={releases[dataset_id]!r}"
            )
        verified_evidence = []
        missing = False
        for item in row.get("evidence", []):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            rel = _safe_route(item["path"])
            try:
                evidence_file = _resolve_regular_file(root, root / Path(*PurePosixPath(rel).parts))
            except PrepareError:
                missing = True
                continue
            size, digest = _hash_file(evidence_file)
            expected = item.get("sha256")
            if expected and digest != expected:
                raise PrepareError(f"GEE evidence SHA-256 mismatch for {rel}")
            verified_evidence.append({"path": rel, "sha256": digest})
        if missing:
            output[dataset_id] = not_audited.copy()
        else:
            comparison = row.get("gee_comparison", {})
            status = row.get("gee_status", comparison.get("status", "not_audited"))
            summary = row.get("gee_summary", comparison.get("scope", "No GEE comparison recorded."))
            output[dataset_id] = {"status": status, "summary": summary, "evidence": verified_evidence}
    return output


def build_config(
    root: Path,
    plan_path: Path,
    packages: dict[str, Path],
    gee_evidence_path: str | None = DEFAULT_GEE,
    display_packages: dict[str, Path] | None = None,
    legacy_plan: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrepareError(f"cannot read upload plan {plan_path}: {exc}") from exc
    records = _load_records(root)
    releases = _selected_releases(records)
    plan = _mapping(plan, "upload plan")
    product_ids, owners_by_product = _validate_plan_products(plan, records, releases)
    display_packages = display_packages or {}
    mapped = _planned_files(plan, root, records, releases, product_ids, owners_by_product, packages, display_packages)
    display_manifests = _validate_display_bindings(
        root, records, releases, product_ids, mapped, packages, display_packages, legacy_plan
    )
    objects: dict[str, dict[str, Any]] = {}
    by_route = {route: (entry, path) for route, entry, path in mapped}
    for route, entry, path in mapped:
        objects[_object_path(route)] = {
            "path": str(path),
            "size_bytes": entry["size_bytes"],
            "sha256": entry["sha256"],
            "content_type": _content_type(entry, path),
        }

    gee = _gee_by_dataset(root, gee_evidence_path, releases)
    datasets = []
    for dataset_id in DATASET_IDS:
        record = records[dataset_id]
        publication = record["publication"]
        release = releases[dataset_id]
        ready = bool(release)
        source_coop = publication["source_coop"]
        title = source_coop.get("title") or record.get("title") or dataset_id
        review = record.get("review") if isinstance(record.get("review"), dict) else {}
        source_info = record.get("source") if isinstance(record.get("source"), dict) else {}
        summary = (
            source_coop.get("summary")
            or record.get("summary")
            or record.get("description")
            or review.get("proposed_scope")
            or (review.get("publication_assessment") or {}).get("scope")
            or source_coop.get("temporal_note")
            or ""
        )
        attribution = source_coop.get("attribution") or record.get("attribution") or source_info.get("producer") or source_info.get("citation")
        review_license = review.get("source_license")
        if isinstance(review_license, dict):
            review_license = review_license.get("id")
        license_value = source_info.get("license") or review_license or source_coop.get("license_note")
        dataset = {
            "id": dataset_id,
            "title": title,
            "summary": summary,
            "release": release,
            "state": "prepared" if ready else "unavailable",
            "unavailable_reason": None,
            "license": license_value,
            "attribution": attribution,
            "gee": gee[dataset_id],
            "layers": [],
            "analytical_assets": [],
        }
        if not ready:
            limitations = source_coop.get("limitations") or []
            blocker = next((text for text in limitations if any(word in text.casefold() for word in ("blocked", "not acquired", "not converted", "pending"))), None)
            dataset["unavailable_reason"] = blocker or publication.get("release_status") or publication.get("status") or "No prepared release is recorded."
            datasets.append(dataset)
            continue
        prefix = f"{product_ids[dataset_id]}/releases/{release}/"
        assets = [(route, entry, path) for route, (entry, path) in by_route.items() if route.startswith(prefix)]
        release_bbox = _release_bbox(assets)
        styles = [(route, path) for route, _, path in assets if "/styles/" in route and path.suffix.lower() == ".json"]
        display_ref = publication.get("display")
        if isinstance(display_ref, dict) and dataset_id in display_manifests:
            display_prefix = f"{product_ids[dataset_id]}/display/{display_ref['release']}/"
            display_files = [(route, entry, path) for route, entry, path in mapped if route.startswith(display_prefix)]
            manifest = display_manifests.get(dataset_id)
            if not display_files or manifest is None:
                raise PrepareError(f"{dataset_id}: canonical display package is absent from the selected plan")
            file_map = {entry.get("source", {}).get("path"): (route, entry, path) for route, entry, path in display_files}
            analytic_map = {entry.get("source", {}).get("path"): (entry, path) for _, entry, path in assets
                            if entry.get("source", {}).get("kind") == "package"}
            for asset in manifest["assets"]:
                asset_path = asset["path"]
                if asset_path not in file_map:
                    raise PrepareError(f"{dataset_id}: display asset is not in the exact plan: {asset_path}")
                route, entry, path = file_map[asset_path]
                style_path = file_map[asset["style_path"]][2]
                source_layer, geometry_type = _read_style(style_path)
                source_asset = asset["source_asset"]
                analytic_entry, analytic_path = analytic_map[source_asset["path"]]
                analytic_info, _, _ = _read_parquet(analytic_path)
                layer_id = asset["id"]
                dataset["layers"].append({
                    "id": layer_id,
                    "title": asset.get("title") or layer_id,
                    "format": "pmtiles",
                    "object_path": _object_path(route),
                    "size_bytes": entry["size_bytes"],
                    "sha256": entry["sha256"],
                    "source_layer": asset.get("source_layer") or source_layer,
                    "geometry_type": asset.get("geometry_type") or geometry_type,
                    "min_zoom": asset.get("min_zoom", 0),
                    "max_zoom": asset.get("max_zoom", 12),
                    "id_field": asset.get("id_field"),
                    "id_encoding": asset.get("id_encoding", "mvt_feature_id_and_property"),
                    "attribute_fields": asset.get("attribute_fields", []),
                    "bbox": asset.get("bbox") or analytic_info.get("bbox"),
                    "analytic": {
                        "format": "geoparquet",
                        **_asset_for(f"{product_ids[dataset_id]}/releases/{release}/{source_asset['path']}", analytic_entry),
                        **analytic_info,
                    },
                })
        render_id = 0
        for route, entry, path in assets:
            if path.suffix.lower() == ".parquet":
                asset = _asset_for(route, entry)
                dataset["analytical_assets"].append(asset)
                if dataset_id in ("hydrolakes", "free-flowing-rivers", "lakeatlas") and dataset_id not in display_manifests:
                    info, _, _ = _read_parquet(path)
                    dataset["layers"].append(
                        {
                            "id": f"{dataset_id}-{render_id + 1}",
                            "title": path.stem.replace("-", " ").replace("_", " ").title(),
                            "format": "geoparquet",
                            **asset,
                            **info,
                        }
                    )
                    render_id += 1
            elif path.suffix.lower() == ".pmtiles" and dataset_id not in display_manifests:
                if not styles:
                    raise PrepareError(f"PMTiles object has no planned style JSON: {route}")
                style_route, style_path = styles[0]
                source_layer, geometry_type = _read_style(style_path)
                # PMTiles metadata supplies an exact bbox when present; style defines source layer/type.
                bbox = release_bbox
                metadata_path = path.with_suffix(".json")
                if metadata_path.exists() and not metadata_path.is_symlink():
                    try:
                        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                        candidate_bbox = metadata.get("bbox")
                        if isinstance(candidate_bbox, list) and len(candidate_bbox) == 4:
                            bbox = candidate_bbox
                    except (OSError, ValueError):
                        pass
                dataset["layers"].append(
                    {
                        "id": f"{dataset_id}-display",
                        "title": record.get("title", dataset_id),
                        "format": "pmtiles",
                        **_asset_for(route, entry),
                        "source_layer": source_layer,
                        "geometry_type": geometry_type,
                        "bbox": bbox,
                    }
                )
        if dataset_id in ("grwl", "river-plastic-inputs") and len(dataset["layers"]) != 1:
            raise PrepareError(f"expected one styled PMTiles render layer for {dataset_id}")
        if dataset_id in ("hydrolakes", "free-flowing-rivers") and len(dataset["layers"]) != 1:
            raise PrepareError(f"expected one render layer for {dataset_id}")
        if dataset_id == "lakeatlas" and len(dataset["layers"]) != 2:
            raise PrepareError("LakeATLAS must provide separate polygon and pour-point render layers")
        datasets.append(dataset)
    return {
        "schema_version": 1,
        "objects": objects,
        "viewer": {
            "title": "Dataset viewer",
            "object_origin": None,
            "max_features": 1500,
            "regions": REGIONS,
            "datasets": datasets,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=DEFAULT_PLAN)
    parser.add_argument("--package", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--display-package", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--legacy-plan", action="store_true",
                        help="allow a historical plan without display_package entries after canonical display references are added")
    parser.add_argument("--output", required=True, help="new JSON output file; existing paths are refused")
    parser.add_argument("--gee-evidence", default=DEFAULT_GEE)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).resolve()
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        if output.exists() or output.is_symlink():
            raise PrepareError(f"refusing to overwrite existing output: {output}")
        plan_path = Path(args.plan)
        if not plan_path.is_absolute():
            plan_path = root / plan_path
        packages = _parse_packages(args.package)
        packages = {dataset_id: path if path.is_absolute() else root / path for dataset_id, path in packages.items()}
        display_packages = _parse_packages(args.display_package)
        display_packages = {dataset_id: path if path.is_absolute() else root / path for dataset_id, path in display_packages.items()}
        config = build_config(root, plan_path, packages, args.gee_evidence or None, display_packages, args.legacy_plan)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects against a racing writer/dangling symlink.
        with output.open("x", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except (PrepareError, OSError) as exc:
        print(f"prepare: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
