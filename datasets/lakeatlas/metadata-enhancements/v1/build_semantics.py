#!/usr/bin/env python3
"""Build a checksum-bound LakeATLAS field semantics sidecar from producer PDFs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA_FILES = {
    "lakeatlas-polygons": "lakeatlas-polygons-field-dictionary.json",
    "lakeatlas-pour-points": "lakeatlas-pour-points-field-dictionary.json",
}
PACKAGE_ASSET_HASHES = {
    "lakeatlas-polygons": "bbef606fd8522b230efc90e2952a67c1e4265e7bf733208fa4cc31395a7277b7",
    "lakeatlas-pour-points": "ff621c1db763551cdb6ced8958eefcc9da76a73c16e7f7259c238bec3aae5720",
}
PACKAGE_MANIFEST_HASH = "32b4877b8809cabd3e2caca8da175115e8ff8317402058846ed0db06a54d52e9"
EXPECTED_INPUT_HASHES = {
    "metadata/lakeatlas-polygons-field-dictionary.json": "1a5c649b83d445247dad9a1b1c98c39c3f44bb8ff05f2b0e7501f1437d392c20",
    "metadata/lakeatlas-pour-points-field-dictionary.json": "2545573e5e1a8fd2faa0e21178a1174834c3813f3e99c9e617357cb4922b966d",
    "source/LakeATLAS_Catalog_v10.pdf": "e736eedbbe32cdeb498348696b9d085b1caddd937a19c7c669501deaffe670e1",
    "source/HydroATLAS_TechDoc_v10_1.pdf": "0ad77c88140d8a0b569d79d5cceadf727b558a7e422a36b9c394cc593db2ccab",
}
HYDROLAKES_LICENSE = "Creative Commons Attribution 4.0 International License (CC-BY 4.0)"
HYDROLAKES_PRODUCT_PAGE = "https://www.hydrosheds.org/products/hydrolakes"
HYDROLAKES_TECHDOC = "https://data.hydrosheds.org/file/technical-documentation/HydroLAKES_TechDoc_v10.pdf"
HYDROLAKES_TECHDOC_SHA256 = "3d1e30abb0691750127fd8e2ff6a149c83f36b93619fb44774476663e0f01f47"

# HydroLAKES base attributes documented in Appendix 3 of the technical report.
# Units / aggregation are explicitly stated only when the producer states them.
CORE_FIELDS = {
    "Hylak_id": ("Unique HydroLAKES identifier; values 1–1,427,688.", "identifier (unitless)", "not_applicable"),
    "Lake_name": ("Name of lake or reservoir; populated for lakes >=500 km², named large reservoirs in GRanD, and smaller lakes named in GLWD.", "not applicable (text)", "not_applicable"),
    "Country": ("Country containing the lake/reservoir, assigned by the country containing its pour point; transboundary/border assignments can be arbitrary.", "not applicable (text)", "not_applicable"),
    "Continent": ("Geographic continent: Africa, Asia, Europe, North America, South America, or Oceania (Australia and Pacific Islands).", "not applicable (text category)", "not_applicable"),
    "Poly_src": ("Source of original lake polygon: CanVec, SWBD, MODIS, NHD, ECRINS, GLWD, GRanD, or Other.", "not applicable (category)", "not_applicable"),
    "Lake_type": ("Lake type: 1 lake, 2 reservoir, 3 lake control (natural lake with regulation structure). Default 1 also includes unidentified water bodies.", "categorical code", "not_applicable"),
    "Grand_id": ("Corresponding GRanD reservoir ID; 0 means no corresponding GRanD record.", "identifier", "not_applicable"),
    "Lake_area": ("Lake surface area (polygon area).", "km²", "polygon area"),
    "Shore_len": ("Length of lake polygon outline (shoreline).", "km", "polygon perimeter"),
    "Shore_dev": ("Shoreline development: shoreline length divided by circumference of a circle with equal area; 1 denotes a perfect circle.", "dimensionless ratio", "derived ratio"),
    "Vol_total": ("Total lake/reservoir volume. Usually geostatistically estimated; reported lake/reservoir values are used when available, and regulated lakes use the larger reported or estimated value.", "million m³", "reported or modeled; see definition"),
    "Vol_res": ("Reported reservoir volume or storage volume of added lake regulation; 0 means no reservoir volume.", "million m³", "reported storage"),
    "Vol_src": ("Source/type code for Vol_total: 1 reported lake volume; 2 reported reservoir volume; 3 geostatistical estimate.", "categorical code", "not_applicable"),
    "Depth_avg": ("Average lake depth, defined as Vol_total divided by Lake_area.", "m", "Vol_total / Lake_area"),
    "Dis_avg": ("Average long-term discharge flowing through lake, sampled at lake pour point from WaterGAP runoff/discharge downscaled to HydroSHEDS; considerable uncertainty for very low flows. -9999 means pour point is off HydroSHEDS landmask.", "m³/s", "long-term average at pour point"),
    "Res_time": ("Average lake-water residence time, Vol_total / Dis_avg, in days; values below 0.1 rounded up to 0.1. -1 means Dis_avg is 0; -9999 means pour point is off HydroSHEDS landmask.", "days", "Vol_total / Dis_avg"),
    "Elevation": ("Lake-surface elevation, primarily majority pixel elevation within polygon from EarthEnv-DEM90; negative values north of 60°N were replaced using GTOPO30.", "m above sea level", "majority pixel value within polygon"),
    "Slope_100": ("Average slope within a 100 m buffer around lake polygon, from EarthEnv-DEM90 (GTOPO30 for 12 lakes north of 83°N). -1 means not calculated for lakes >=500 km².", "degrees", "average within 100 m buffer"),
    "Wshd_area": ("Upstream contribution area to lake pour point measured from HydroSHEDS drainage network.", "km²", "upstream contributing area"),
    "Pour_long": ("Longitude of lake pour point.", "decimal degrees", "coordinate"),
    "Pour_lat": ("Latitude of lake pour point.", "decimal degrees", "coordinate"),
    "HYBAS_L12": ("HydroBASINS Pfafstetter level 12 sub-basin ID corresponding to the lake.", "identifier", "spatial join"),
    "HYRIV_RCH": ("HYRIV_ID of HydroRIVERS stream reach into which lake drains at pour point; 0 means pour point is not directly on a depicted reach (offstream).", "identifier", "spatial join"),
    "HYRIV_CAT": ("HYRIV_ID of HydroRIVERS reach catchment containing pour point; equals HYRIV_RCH for onstream points; 0 means not in a depicted catchment.", "identifier", "spatial join"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_text(path: Path) -> str:
    result = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True)
    return result.stdout


def one(pattern: str, block: str, default: str | None = None) -> str | None:
    match = re.search(pattern, block, re.M | re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else default


def expand_suffixes(value: str) -> list[str]:
    result: list[str] = []
    for token in (x.strip() for x in value.split("|")):
        # Catalog shorthand such as l01-s12 means l01 through l12; v01-v22 is similar.
        m = re.fullmatch(r"([a-z]+)(\d+)-([a-z])(\d+)", token, re.I)
        if m:
            prefix, start, end_prefix, end = m.groups()
            # In catalog shorthand, an endpoint marker "s" means expand the
            # starting extent code through the stated numeric period (e.g. l01-s12 -> l01..l12).
            if end_prefix.lower() not in {prefix.lower(), "s"}:
                raise ValueError(f"unsupported suffix range {token!r}")
            result.extend(f"{prefix}{n:0{len(start)}d}" for n in range(int(start), int(end) + 1))
        else:
            result.append(token)
    return result


def _data_description(page: str) -> str | None:
    lines = page.splitlines()
    start = next((i for i, line in enumerate(lines) if "Existing suffixes {xoo}:" in line), None)
    if start is None:
        return None
    content = []
    for line in lines[start + 1:]:
        if re.match(r"\s*Reference\s{2,}", line):
            break
        # Narrative starts in the right PDF column and continues under the
        # two-line "Data description" label. Strip only those labels.
        value = re.sub(r"^\s*Data\s+", "", line, flags=re.I)
        value = re.sub(r"^\s*description\s+", "", value, flags=re.I)
        if value.strip():
            content.append(value.strip())
    return re.sub(r"\s+", " ", " ".join(content)).strip() or None


def _additional_information(page: str) -> str | None:
    lines = page.splitlines()
    license_line = next((i for i, line in enumerate(lines) if re.match(r"\s*License\s{2,}", line)), None)
    if license_line is None:
        return None
    content = []
    for line in lines[license_line + 1:]:
        # Labels wrap across two lines in the source PDF; keep the prose that
        # shares each row and discard only those label tokens.
        value = re.sub(r"^\s*(?:Additional|information)\s+", "", line, flags=re.I)
        if re.fullmatch(r"\s*information\s*", value, re.I):
            value = ""
        if value.strip():
            content.append(value.strip())
    result = re.sub(r"\s+", " ", " ".join(content)).strip()
    return result or None


def parse_catalog(path: Path) -> dict[str, dict]:
    pages = pdf_text(path).split("\f")
    fields: dict[str, dict] = {}
    for page_no, page in enumerate(pages, 1):
        if "Column name" not in page:
            continue
        template = one(r"Column name\s+([a-z0-9_]+_\{xoo\})", page)
        suffixes = one(r"Existing suffixes \{xoo\}:\s*([^\n]+)", page)
        if not template or suffixes is None:
            raise ValueError(f"catalog page {page_no}: missing field template/suffix inventory")
        prefix = template.removesuffix("{xoo}")
        attr = one(r"Attribute\s+([^\n]+)", page)
        category = one(r"Category\s+(.*?)\s+ID-[A-Z]\d+", page)
        source_data = one(r"Source data\s+([^\n]+)", page)
        citation = one(r"Citation:\s*(.*?)\s+Native format:", page)
        native_format = one(r"Native format:\s*(.*?)\s+Units:", page)
        units = one(r"Units:\s*([^\n]+)", page)
        license_name = one(r"License\s+([^\n]+)", page)
        extent = one(r"Spatial extent \{x\}:\s*([^\n]+)", page)
        dimension = one(r"Dimension \{oo\}:\s*([^\n]+)", page)
        description = _data_description(page)
        additional = _additional_information(page)
        hydroatlas_license = None
        if license_name:
            marker = re.search(r"HydroATLAS:\s*(.+)$", license_name)
            hydroatlas_license = marker.group(1).strip() if marker else license_name.strip()
        doc = {
            "producer_attribute": attr,
            "category": category,
            "definition": description,
            "units_as_published": units,
            "spatial_extent_semantics": extent,
            "dimension_semantics": dimension,
            "aggregation_or_summary": "; ".join(x for x in (extent, dimension) if x),
            "source_dataset": source_data,
            "source_citation": citation,
            "source_native_format": native_format,
            "license_as_published": license_name,
            "hydroatlas_license_as_published": hydroatlas_license,
            "producer_notes": additional,
            "evidence": {"document": "LakeATLAS_Catalog_v10.pdf", "page": page_no},
            "semantics_status": "documented" if all((attr, description, units, extent, dimension, license_name)) else "incomplete_producer_documentation",
            "field_origin": "LakeATLAS_v1_hydro_environmental_catalog_attribute",
            "source_producer_field": True,
        }
        for suffix in expand_suffixes(suffixes):
            name = prefix + suffix
            if name in fields:
                raise ValueError(f"duplicate catalog field {name}")
            fields[name] = doc
    return fields


def core_record(name: str) -> dict:
    meaning, units, aggregation = CORE_FIELDS[name]
    sources = {
        "Lake_name": "HydroLAKES; named records may come from GRanD or GLWD",
        "Grand_id": "Global Reservoir and Dam (GRanD) database",
        "Vol_total": "HydroLAKES geostatistical model; reported lake-volume literature; GRanD/literature reservoir records",
        "Vol_res": "GRanD or reported reservoir/regulation storage records",
        "Vol_src": "HydroLAKES volume-source classification",
        "Depth_avg": "Derived from Vol_total and Lake_area",
        "Dis_avg": "WaterGAP discharge, downscaled to HydroSHEDS 15 arc-second network",
        "Res_time": "Derived from Vol_total and Dis_avg",
        "Elevation": "EarthEnv-DEM90; GTOPO30 substitutions north of 60°N",
        "Slope_100": "EarthEnv-DEM90; GTOPO30 for 12 lakes above 83°N",
        "Wshd_area": "HydroSHEDS drainage network",
        "HYBAS_L12": "HydroBASINS Pfafstetter level 12",
        "HYRIV_RCH": "HydroRIVERS stream reach network",
        "HYRIV_CAT": "HydroRIVERS reach catchments",
    }
    source_dataset = sources.get(name, "HydroLAKES base attribute")
    citation = "HydroATLAS Technical Documentation v1.0.1, Appendix 3; LakeATLAS development is cited to Messager et al. (2016)"
    if name in {"Dis_avg", "Wshd_area", "HYBAS_L12", "HYRIV_RCH", "HYRIV_CAT"}:
        citation += "; source dataset attribution as stated in Appendix 3"
    return {
        "producer_attribute": name,
        "definition": meaning,
        "units_as_published": units,
        "aggregation_or_summary": aggregation,
        "source_dataset": source_dataset,
        "source_citation": citation,
        "license_as_published": HYDROLAKES_LICENSE,
        "hydroatlas_license_as_published": None,
        "license_status": "explicit_inherited_HydroLAKES_source_product_license",
        "license_scope": "HydroLAKES v1 source product for this inherited base field. The LakeATLAS catalog has no separate per-column license entry for inherited base attributes; this does not assert an independently listed LakeATLAS per-column term.",
        "license_evidence": [
            {"document": "HydroLAKES_TechDoc_v10.pdf", "section": "4.1 License agreement", "printed_page": 14, "url": HYDROLAKES_TECHDOC, "sha256": HYDROLAKES_TECHDOC_SHA256, "sha256_basis": "retained-source evidence metadata; PDF was not freshly fetched or rehashed during this task"},
            {"document": "HydroLAKES producer product page", "section": "License", "url": HYDROLAKES_PRODUCT_PAGE},
        ],
        "field_origin": "HydroLAKES_v1_inherited_base_attribute",
        "source_producer_field": True,
        "evidence": {"document": "HydroATLAS_TechDoc_v10_1.pdf", "page": 15 if name in {"Hylak_id", "Lake_name", "Country", "Continent", "Poly_src", "Lake_type", "Grand_id", "Lake_area", "Shore_len"} else (16 if name in {"Shore_dev", "Vol_total", "Vol_res", "Vol_src", "Depth_avg", "Dis_avg", "Res_time", "Elevation", "Slope_100", "Wshd_area"} else 17)},
        "semantics_status": "documented",
    }


def verify_manifest_bindings(manifest: dict, manifest_hash: str) -> dict[str, dict]:
    if manifest_hash != PACKAGE_MANIFEST_HASH:
        raise ValueError(f"prepared package manifest hash mismatch: {manifest_hash}")
    manifest_assets = {asset["asset_id"]: asset for asset in manifest.get("assets", [])}
    for asset_id, expected_hash in PACKAGE_ASSET_HASHES.items():
        row = manifest_assets.get(asset_id)
        if row is None or row.get("sha256") != expected_hash:
            raise ValueError(f"manifest does not bind expected asset {asset_id}")
    return manifest_assets


def verified_package_inputs(package_root: Path) -> tuple[Path, Path, Path, Path, dict[str, str]]:
    manifest_path = package_root / "manifest.json"
    manifest_hash = sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    manifest_assets = verify_manifest_bindings(manifest, manifest_hash)
    paths = {key: package_root / key for key in EXPECTED_INPUT_HASHES}
    actual_inputs = {key: sha256(path) for key, path in paths.items()}
    for key, expected in EXPECTED_INPUT_HASHES.items():
        if actual_inputs[key] != expected:
            raise ValueError(f"prepared package input hash mismatch: {key} ({actual_inputs[key]})")
    for asset_id, expected_hash in PACKAGE_ASSET_HASHES.items():
        row = manifest_assets[asset_id]
        href = row.get("href")
        if href != f"assets/{asset_id}.parquet":
            raise ValueError(f"manifest asset path mismatch: {asset_id}")
        asset_path = package_root / href
        if not asset_path.is_file() or asset_path.stat().st_size != row.get("size_bytes"):
            raise ValueError(f"prepared package asset missing or size mismatch: {asset_id}")
        if row.get("sha256") != expected_hash:
            raise ValueError(f"manifest asset SHA-256 mismatch: {asset_id}")
    # Prior package verification binds this immutable manifest to the asset hashes.
    # Avoid rereading the >1.4 GB and 284 MB assets merely to regenerate metadata.
    return (
        paths["metadata/lakeatlas-polygons-field-dictionary.json"],
        paths["metadata/lakeatlas-pour-points-field-dictionary.json"],
        paths["source/LakeATLAS_Catalog_v10.pdf"],
        paths["source/HydroATLAS_TechDoc_v10_1.pdf"],
        PACKAGE_ASSET_HASHES.copy(),
    )


def build(polygons_schema: Path, points_schema: Path, catalog: Path, techdoc: Path, asset_hashes: dict[str, str]) -> dict:
    catalog_fields = parse_catalog(catalog)
    schemas = {"lakeatlas-polygons": polygons_schema, "lakeatlas-pour-points": points_schema}
    assets = {}
    for asset_id, schema_path in schemas.items():
        schema = json.loads(schema_path.read_text())
        names = [x["name"] for x in schema["fields"]]
        mapped = {}
        for name in names:
            if name in catalog_fields:
                mapped[name] = dict(catalog_fields[name])
                mapped[name]["license_status"] = "explicit_attribute_license_in_catalog"
            elif name in CORE_FIELDS:
                mapped[name] = core_record(name)
            elif name in {"OBJECTID", "Shape_Length", "Shape_Area", "geometry", "bbox"}:
                descriptions = {
                    "OBJECTID": "File geodatabase system object identifier; technical documentation says this ArcGIS-added field is not officially part of LakeATLAS.",
                    "Shape_Length": "ArcGIS-generated polygon perimeter field; technical documentation says this is not officially part of LakeATLAS. Units are not specified in the retained documentation for this source field.",
                    "Shape_Area": "ArcGIS-generated polygon area field; technical documentation says this is not officially part of LakeATLAS. Units are not specified in the retained documentation for this source field.",
                    "geometry": "GeoParquet geometry column encoded as WKB in EPSG:4326 by the local package; packaging representation, not a named producer attribute.",
                    "bbox": "GeoParquet per-feature bounding-box metadata generated for the package; not a named producer attribute.",
                }
                mapped[name] = {"producer_attribute": None, "definition": descriptions[name], "units_as_published": None, "aggregation_or_summary": None, "license_as_published": None, "hydroatlas_license_as_published": None, "license_status": "not_a_producer_attribute", "semantics_status": "not_a_producer_attribute", "field_origin": "source_geodatabase_default" if name in {"OBJECTID", "Shape_Length", "Shape_Area"} else ("GeoParquet_geometry_encoding" if name == "geometry" else "package_derived_bbox_metadata"), "source_producer_field": False, "evidence": {"document": "HydroATLAS_TechDoc_v10_1.pdf", "page": 15 if name in {"OBJECTID", "Shape_Length", "Shape_Area"} else None}}
            else:
                mapped[name] = {"producer_attribute": name, "definition": None, "units_as_published": None, "aggregation_or_summary": None, "license_as_published": None, "license_status": "unknown", "semantics_status": "unresolved", "evidence": None}
        assets[asset_id] = {"source_schema": schema_path.name, "source_schema_sha256": sha256(schema_path), "field_count": len(names), "fields": mapped}
    all_names = set().union(*(set(a["fields"]) for a in assets.values()))
    # Both source layers share source attributes; polygon-only Shape_Length/Area are non-producer fields.
    return {
        "schema_version": 1,
        "enhancement_version": "v1",
        "product": "LakeATLAS v1.0 analytic GeoParquet r2 prepared package",
        "package_manifest_sha256": PACKAGE_MANIFEST_HASH,
        "bound_assets": {k: {"sha256": asset_hashes[k], "binding": "immutable package manifest SHA-256 and asset entry; asset bytes not rehashed during metadata generation"} for k in schemas},
        "producer_notices": {
            "collective_database": "HydroATLAS v1.0 is described as a CC-BY-4.0 collective database, while individual contents retain their own licenses; the retained LakeATLAS catalog identifies CC-BY-4.0 or ODbL-1.0 per attribute.",
            "field_license_rule": "For the 281 catalog attributes, the full LakeATLAS catalog license notice is preserved and the explicit HydroATLAS field term is parsed separately. For 24 inherited HydroLAKES base attributes, license_as_published records the explicit CC-BY-4.0 HydroLAKES v1 source-product license from the HydroLAKES technical documentation and product page; hydroatlas_license_as_published is null because the LakeATLAS catalog has no separate column-level entry for those base fields. These scopes are not conflated.",
            "attribution": "HydroSHEDS / HydroATLAS authors. Cite Lehner, Messager, Korver & Linke (2022), Scientific Data 9:351, DOI 10.1038/s41597-022-01425-z.",
            "source_archive": "LakeATLAS_Data_v10.gdb.zip, Figshare article version 1, DOI 10.6084/m9.figshare.19312001.v1.",
        },
        "source_documents": {
            "catalog": {"filename": catalog.name, "sha256": sha256(catalog), "role": "attribute definitions, units, extent/dimension, attribution and field license"},
            "technical_documentation": {"filename": techdoc.name, "sha256": sha256(techdoc), "role": "inherited HydroLAKES base attribute definitions and LakeATLAS package field caveats"},
            "hydrolakes_source_license": {
                "product_page": HYDROLAKES_PRODUCT_PAGE,
                "technical_documentation": HYDROLAKES_TECHDOC,
                "technical_documentation_sha256": HYDROLAKES_TECHDOC_SHA256,
                "technical_documentation_sha256_basis": "retained-source evidence metadata supplied for this task; the PDF was not freshly fetched or rehashed during this generation",
                "statement": HYDROLAKES_LICENSE,
                "evidence": "HydroLAKES TechDoc v1.0 section 4.1, printed page 14; the current HydroSHEDS HydroLAKES product page repeats this license.",
                "context": "Applied only as the source-product license for the 24 inherited HydroLAKES fields. LakeATLAS per-field catalog entries and collective-database notices remain separately represented.",
            },
        },
        "assets": assets,
    }


def validate(doc: dict, *, require_resolved: bool = True) -> list[str]:
    errors = []
    for asset_id, asset in doc["assets"].items():
        if len(asset["fields"]) != asset["field_count"]:
            errors.append(f"{asset_id}: duplicate or missing fields")
        for name, field in asset["fields"].items():
            if not field.get("semantics_status"):
                errors.append(f"{asset_id}.{name}: missing semantics status")
            if require_resolved and field.get("semantics_status") == "unresolved":
                errors.append(f"{asset_id}.{name}: unresolved producer field")
            if require_resolved and field.get("semantics_status") == "incomplete_producer_documentation":
                errors.append(f"{asset_id}.{name}: incomplete producer documentation")
            if field.get("semantics_status") == "documented":
                for required in ("definition", "units_as_published", "aggregation_or_summary", "evidence"):
                    if field.get(required) is None:
                        errors.append(f"{asset_id}.{name}: documented field missing {required}")
    return errors


def ensure_new_output_path(path: Path) -> None:
    if os.path.lexists(path):
        raise FileExistsError(f"refusing to overwrite existing metadata version/output: {path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package-root", type=Path, required=True, help="Prepared local package directory containing manifest.json, assets/, metadata/, and source/")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--allow-unresolved", action="store_true")
    args = p.parse_args()
    try:
        ensure_new_output_path(args.output)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        polygons, points, catalog, techdoc, actual_assets = verified_package_inputs(args.package_root)
        doc = build(polygons, points, catalog, techdoc, actual_assets)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors = validate(doc, require_resolved=not args.allow_unresolved)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
