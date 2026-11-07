#!/usr/bin/env python3
"""Import this reviewed discovery batch without changing prior dataset decisions.

--check compares the imported discovery blocks offline; --write refuses to replace
an existing different block. Later edits belong in canonical dataset.yaml records.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
STUDY = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import candidate_discovery as cd

MARKER = "\n# Cross-catalog discovery: global-candidates-20261031\n"
BATCH = "global-candidates-20261031"


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provider(source):
    url = source["url"]
    host = urlsplit(url).hostname or ""
    if host == "developers.google.com" and "/earth-engine/" in url:
        return "gee_official"
    if host == "gee-community-catalog.org":
        return "gee_community"
    if host == "planetarycomputer.microsoft.com":
        return "planetary_computer"
    if host.endswith("arcgis.com") or host.endswith("arcgis.com."):
        return "esri_public"
    if host == "source.coop" or host.endswith(".source.coop"):
        return "source_coop"
    return "producer"


def prose(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return "; ".join(f"{key}: {prose(item)}" for key, item in value.items() if item is not None)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def unique(items):
    result = []
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            result.append(item); seen.add(key)
    return result


def plan_records():
    plan = load(STUDY / "integration-plan.json")
    assert digest(STUDY / "identity-review.json") == plan["identity_review_sha256"]
    baseline = load(STUDY / "baseline-records.json")["record_sha256"]
    current = {p.parent.name: yaml.safe_load(p.read_text()) for p in (ROOT / "datasets").glob("*/dataset.yaml")}
    for record_id, expected in baseline.items():
        path = ROOT / "datasets" / record_id / "dataset.yaml"
        prior = path.read_text().split(MARKER, 1)[0].encode()
        if hashlib.sha256(prior).hexdigest() != expected:
            raise ValueError(f"Pre-expansion canonical bytes changed: {record_id}")
    paths = {lane: STUDY / lane / "reviewed.json" for lane in ("citations", "planetary", "esri", "literature", "reuse")}
    paths["supplemental"] = STUDY / "citations/supplemental-global.json"
    observations = {}
    for lane, path in paths.items():
        doc = load(path)
        items = doc.get("candidates", doc.get("supplemental_candidates", []))
        for item in items:
            key = item.get("evidence_key", item["suggested_id"])
            assert (lane, key) not in observations
            observations[lane, key] = item
    assigned = defaultdict(set)
    for selection in [*plan["mappings"], *plan["withheld"]]:
        identity = selection["lane"], selection["key"]
        item = observations[identity]
        available = {source["entry_id"] for source in item["sources"]}
        selected = set(selection.get("source_entry_ids", available))
        if not selected <= available or assigned[identity] & selected:
            raise ValueError(f"Invalid or duplicated source partition: {identity}")
        assigned[identity].update(selected)
    for identity, item in observations.items():
        if assigned[identity] != {source["entry_id"] for source in item["sources"]}:
            raise ValueError(f"Unreviewed source partition: {identity}")
    buckets = defaultdict(list)
    for mapping in plan["mappings"]:
        item = observations[mapping["lane"], mapping["key"]]
        sources = [s for s in item["sources"] if s["entry_id"] in mapping["source_entry_ids"]]
        if not sources or set(s["entry_id"] for s in sources) != set(mapping["source_entry_ids"]):
            raise ValueError(f"Incomplete source partition: {mapping['lane']}/{mapping['key']}")
        buckets[mapping["target_id"]].append((mapping, item, sources))
    planned = {}
    for record_id, entries in sorted(buckets.items()):
        first_mapping, first, first_sources = entries[0]
        title = plan["title_overrides"].get(record_id, first_mapping.get("title", first["title"]))
        record = copy.deepcopy(current.get(record_id))
        if record is None:
            record = {"schema_version": 1, "id": record_id, "title": title,
                      "intake": {"kind": "producer" if first_mapping["lane"] in {"supplemental", "literature"} else "official_catalog",
                                 "reference_url": first_sources[0]["url"], "added_on": "2026-10-31"},
                      "triage": {"decision": "pending", "priority": "normal", "rationale": "Global discovery candidate. Review exact product scope, existing native access, license and publication value before selecting work."},
                      "publication": {"status": "candidate"}}
        review = {"batch": BATCH, "reviewed_on": "2026-10-31", "geographic_scope": "global", "spatial_coverage": "",
                  "sources": [], "access": [], "citations": [], "evidence": []}
        coverage = []
        source_keys = set()
        for mapping, item, sources in entries:
            lane = mapping["lane"]
            if item.get("geographic_scope") == "near_global":
                review["geographic_scope"] = "near_global"
            coverage.append(f"{lane}: {prose(item.get('spatial_coverage', item.get('access_summary', 'See retained evidence.')))} {mapping['notes']}")
            if mapping.get("related_record_ids"):
                coverage.append("Related canonical records, with distinct scope: " + ", ".join(mapping["related_record_ids"]) + ".")
            for source in sources:
                normalized = {"provider": provider(source), "entry_id": source["entry_id"], "url": source["url"],
                              "relationship": mapping.get("relationship", source.get("relationship", "same_family"))}
                if mapping.get("title"):
                    normalized["relationship"] = "component"
                identity = normalized["provider"], normalized["entry_id"]
                if identity not in source_keys:
                    review["sources"].append(normalized); source_keys.add(identity)
            labels = item.get("format_labels", [fmt for fmt in item.get("observed_formats", []) if isinstance(fmt, str)])
            outputs = item.get("recommended_formats", [fmt for fmt in item.get("proposed_outputs", []) if fmt in {"COG", "Zarr", "GeoParquet", "Parquet", "PMTiles", "NetCDF", "GeoTIFF"}])
            status = item.get("hosting_status", "unknown")
            status = {"metadata_only": "unknown", "documented_native": "native_available"}.get(status, status)
            if status == "native_available" and labels and not any(fmt in {"COG", "Zarr", "GeoParquet", "Parquet", "PMTiles", "COPC"} for fmt in labels):
                status = "download_available"
            if record_id == "overture_global_maps":
                status = "native_available"
            urls = unique([*item.get("evidence_urls", []), *(s["url"] for s in sources)])
            if lane == "citations":
                # The frozen group can include other products; keep only this partition's entry URLs plus its paper.
                urls = unique([*(s["url"] for s in sources), *(u for u in urls if "doi.org/" in u)])
            urls = [u for u in urls if isinstance(u, str) and u.startswith("https://")]
            review["access"].append({"provider": mapping.get("access_provider") or {"citations": "literature", "literature": "literature", "supplemental": "producer", "reuse": "producer", "planetary": "planetary_computer", "esri": "esri_public"}[lane],
                                     "status": status, "formats": sorted(set(labels)),
                                     "summary": item.get("access_summary", "Metadata observation only.") + " " + mapping["notes"],
                                     **({"observed_on": item["observed_on"]} if item.get("observed_on") else {}),
                                     "license_summary": prose(item.get("license_summary", "Unreviewed")),
                                     "proposed_outputs": sorted(set(outputs)),
                                     "rationale": item.get("conversion_rationale", "Review exact source, existing native hosts and redistribution terms before selecting a conversion."),
                                     "evidence_urls": urls})
            c = item.get("citation") or {}
            if c.get("count") is not None and mapping.get("include_paper_citation", True):
                review["citations"].append({"provider": "OpenAlex", "paper_doi": c.get("doi"), "work_id": c.get("work_id"),
                                            "cited_by_count": c["count"], "observed_on": c["count_date"],
                                            "scope": c.get("citation_scope") or c.get("count_scope") or "associated dataset paper; exact-release use unproven"})
            path = paths[lane]
            review["evidence"].append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "key": mapping["key"]})
        review["sources"].sort(key=lambda s: (s["provider"], s["entry_id"]))
        for field in ("access", "citations", "evidence"):
            review[field] = unique(review[field])
        review["spatial_coverage"] = " ".join(unique(coverage))
        if record_id == "hydrosheds":
            review["geographic_scope"] = "near_global"
            review["spatial_coverage"] += " Core raster resolutions have different footprints; SRTM-derived high-resolution coverage is latitude-limited. HydroBASINS polygons are a separate record."
        if record_id == "usgs-world-ecological-land-units-2015":
            review["geographic_scope"] = "near_global"
        if record_id in plan.get("scope_overrides", {}):
            review["geographic_scope"] = plan["scope_overrides"][record_id]
        record["discovery"] = review
        planned[record_id] = record
    schema = Draft202012Validator(load(ROOT / "schemas/dataset.schema.json"), format_checker=FormatChecker())
    complete = {**current, **planned}
    for record in planned.values():
        schema.validate(record)
    cd.validate_discovery(ROOT, complete)
    return planned, baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    planned, baseline = plan_records()
    changes = []
    for record_id, record in planned.items():
        path = ROOT / "datasets" / record_id / "dataset.yaml"
        if path.exists():
            current = yaml.safe_load(path.read_text())
            if current.get("discovery") == record["discovery"]:
                continue
            if current.get("discovery") is not None:
                raise ValueError(f"Refusing to replace edited discovery metadata: {record_id}")
            changes.append((path, path.read_text() + MARKER + yaml.safe_dump({"discovery": record["discovery"]}, sort_keys=False, allow_unicode=True, width=100)))
        else:
            changes.append((path, yaml.safe_dump(record, sort_keys=False, allow_unicode=True, width=100)))
    if args.check and changes:
        raise ValueError(f"Discovery import is incomplete: {len(changes)} canonical records differ")
    if args.write:
        for path, text in changes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    print(json.dumps({"reviewed_records": len(planned), "new_records": sum(key not in baseline for key in planned),
                      "existing_records_augmented": sum(key in baseline for key in planned), "files_written": len(changes) if args.write else 0}, indent=2))


if __name__ == "__main__":
    main()
