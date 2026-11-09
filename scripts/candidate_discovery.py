"""Validate cross-catalog discovery evidence and render the global backlog offline."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import html
import io
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

import dataset_availability
from record_locations import record_path

PROVIDER_LABELS = {
    "gee_official": "GEE official", "gee_community": "GEE community",
    "planetary_computer": "Planetary Computer", "esri_public": "Esri public",
    "producer": "Producer", "source_coop": "Source Cooperative", "literature": "Literature",
}
ACCESS_LABELS = {"native_available": "native format listed", "service_only": "service / export review",
                 "download_available": "download listed", "unknown": "not reviewed"}


def evidence_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (not parts or relative.startswith("/") or "\\" in relative
            or any(p in ("", ".", "..") for p in relative.split("/"))):
        raise ValueError(f"Unsafe discovery evidence path: {relative}")
    cursor = root
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"Discovery evidence contains a symlink: {relative}")
    if not cursor.is_file() or cursor.stat().st_size > 10_000_000:
        raise ValueError(f"Missing or oversized discovery evidence: {relative}")
    return cursor


def validate_discovery(root: Path, records: dict) -> None:
    cache = {}
    exact_owners = {}
    citation_counts = {}
    for record_id, record in records.items():
        review = record.get("discovery")
        if review is None:
            continue
        seen = set()
        for source in review["sources"]:
            identity = (source["provider"], source["entry_id"])
            if identity in seen:
                raise ValueError(f"Duplicate discovery catalog entry: {record_id}/{identity}")
            seen.add(identity)
            parsed = urlsplit(source["url"])
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError(f"Invalid discovery source URL: {record_id}")
            host = (parsed.hostname or "").lower().rstrip(".")
            expected_hosts = {"gee_official": "developers.google.com", "gee_community": "gee-community-catalog.org",
                              "planetary_computer": "planetarycomputer.microsoft.com", "esri_public": "arcgis.com",
                              "source_coop": "source.coop"}
            expected_host = expected_hosts.get(source["provider"])
            if expected_host and host != expected_host and not host.endswith("." + expected_host):
                raise ValueError(f"Discovery provider URL mismatch: {record_id}/{source['provider']}")
            if source["relationship"] == "exact_dataset":
                prior = exact_owners.setdefault(identity, record_id)
                if prior != record_id:
                    raise ValueError(f"Exact discovery entry assigned to two records: {prior}, {record_id}")
        refs = set()
        for ref in review["evidence"]:
            identity = (ref["path"], ref["key"])
            if identity in refs:
                raise ValueError(f"Duplicate discovery evidence reference: {record_id}")
            refs.add(identity)
            if ref["path"] not in cache:
                data = evidence_file(root, ref["path"]).read_bytes()
                doc = json.loads(data)
                if not isinstance(doc, dict):
                    raise ValueError(f"Discovery evidence must be an object: {ref['path']}")
                candidates = doc.get("candidates", doc.get("supplemental_candidates", []))
                if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
                    raise ValueError(f"Discovery evidence lacks observation objects: {ref['path']}")
                keys = [item.get("evidence_key", item.get("suggested_id")) for item in candidates]
                if not keys or any(not isinstance(key, str) or not key for key in keys) or len(set(keys)) != len(keys):
                    raise ValueError(f"Missing or duplicate discovery observation keys: {ref['path']}")
                cache[ref["path"]] = (hashlib.sha256(data).hexdigest(), set(keys))
            digest, keys = cache[ref["path"]]
            if digest != ref["sha256"]:
                raise ValueError(f"Discovery evidence checksum changed: {ref['path']}")
            if ref["key"] not in keys:
                raise ValueError(f"Unknown discovery evidence key: {record_id}/{ref['key']}")
        for citation in review["citations"]:
            if citation["cited_by_count"] is not None and not citation.get("work_id"):
                raise ValueError(f"Counted citation lacks work identity: {record_id}")
            if citation.get("work_id") and not re.fullmatch(r"https://openalex\.org/W[0-9]+", citation["work_id"]):
                raise ValueError(f"Invalid OpenAlex work identity: {record_id}")
            if citation["cited_by_count"] is not None:
                key = (citation["work_id"], citation["observed_on"])
                prior_count = citation_counts.setdefault(key, citation["cited_by_count"])
                if prior_count != citation["cited_by_count"]:
                    raise ValueError(f"Conflicting citation counts for same work/date: {record_id}/{key}")


def citation_summary(record: dict) -> tuple[int | None, str, str]:
    citations = [c for c in record.get("discovery", {}).get("citations", []) if c["cited_by_count"] is not None]
    if citations:
        newest = max(c["observed_on"] for c in citations)
        same_date = [c for c in citations if c["observed_on"] == newest]
        selected = sorted(same_date, key=lambda c: (-c["cited_by_count"], c.get("work_id") or ""))[0]
        return selected["cited_by_count"], newest, selected.get("work_id") or ""
    old = record.get("review", {}).get("citation_assessment", {})
    return old.get("max_paper_citations"), old.get("as_of", ""), old.get("top_paper_openalex_id") or ""


def rows(records: dict, root: Path | None = None) -> list[dict]:
    root = root or Path(__file__).resolve().parents[1]
    output = []
    for record_id, record in records.items():
        review = record.get("discovery", {})
        old = record.get("review", {}).get("citation_assessment", {})
        availability = record.get("review", {}).get("availability", {})
        scope = review.get("geographic_scope", availability.get("geographic_scope", old.get("geographic_scope", "unknown")))
        if scope not in ("global", "near_global"):
            continue
        count, count_date, work_id = citation_summary(record)
        providers = {s["provider"] for s in review.get("sources", [])}
        if record.get("community_url"):
            providers.add("gee_community")
        access = sorted({ACCESS_LABELS[a["status"]] for a in review.get("access", [])})
        formats = sorted({fmt for a in review.get("access", []) for fmt in a["formats"]})
        proposed = sorted({fmt for a in review.get("access", []) for fmt in a["proposed_outputs"]})
        counts = dataset_availability.summary(root, record)
        output.append({
            "id": record_id, "title": record["title"], "record_path": record_path(root, record_id).relative_to(root).as_posix(),
            "geographic_scope": scope,
            "spatial_coverage": review.get("spatial_coverage", "Global in the original citation review; coverage limits have not been re-reviewed in this expansion."),
            "decision": record["triage"]["decision"],
            "publication_status": record.get("publication", {}).get("status", "candidate"),
            "paper_citations": count, "citation_observed_on": count_date, "citation_work_id": work_id,
            "catalogs": "; ".join(PROVIDER_LABELS[p] for p in sorted(providers)),
            "access_review": "; ".join(access) or "not reviewed", "observed_formats": "; ".join(formats),
            "proposed_outputs": "; ".join(proposed), "discovery_batch": review.get("batch", ""),
            **{key: counts.get(key) for key in ("shortlist_id", "shortlist_rank", "source_download_bytes", "source_size_precision",
                "external_locations", "external_matching_locations", "gee_locations", "gee_matching_locations", "gee_asset_count",
                "prepared_analytic_bytes", "prepared_display_bytes", "prepared_data_bytes")},
        })
    return sorted(output, key=lambda row: (row["paper_citations"] is None, -(row["paper_citations"] or 0), row["id"]))


def table_text(value: object) -> str:
    text = html.escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", text)


def render_views(records: dict, root: Path | None = None) -> dict[str, str]:
    global_rows = rows(records, root)
    expanded = [row for row in global_rows if row["discovery_batch"]]
    decisions = Counter(record["triage"]["decision"] for record in records.values())
    lines = ["# Candidate backlog", "", "Generated from `candidates/<id>/dataset.yaml` and `datasets/<id>/dataset.yaml`; edit the canonical records and run `python scripts/catalog.py --write`.", "",
             "Candidates are exploratory and carry no commitment to convert or publish. Prepared datasets remain distinct from verified public releases.", "",
             f"Inventory: {len(records)} records; {len(global_rows)} classified global or near-global; {len(expanded)} covered by expanded discovery.", "",
             "Decisions: " + "; ".join(f"{key}: {value}" for key, value in sorted(decisions.items())) + ".", "",
             "[Global inventory CSV](candidates.csv) includes the existing global backlog. [Full index](index.json) also includes regional and unclassified records. [Discovery methods and coverage](research/global-candidates-20261031/README.md).", "",
             "[Publication shortlist with sizes and source counts](SHORTLIST.md) · [Structured shortlist JSON](shortlist.json) · [Shortlist CSV](shortlist.csv). Matching-scope counts are separated from older-version or partial locations.", "",
             "## Expanded global discovery", "",
             "Sorted by each record's latest available associated-paper count, with its observation date shown. Unknown is not zero. Counts retain their own observation dates, can refer to broader families, and do not establish conversion value or exact-release use; a mixed-date backlog is not a single-date global literature ranking. The frozen top-50 selection is documented separately in the discovery study.", "",
             "Native formats and downloads below are provider declarations, not byte-level or hosting validation. A listed host can cover a related edition or component; read the source relationships in the record. Service access does not establish bulk-export or redistribution rights.", "",
             "| Dataset | Coverage | Paper citations / date | Discovery catalogs | Existing access | Decision / state |",
             "| --- | --- | ---: | --- | --- | --- |"]
    for row in expanded:
        score = "unknown" if row["paper_citations"] is None else f"{row['paper_citations']:,} / {row['citation_observed_on']}"
        lines.append(f"| [{table_text(row['title'])}]({row['record_path']}) | {table_text(row['geographic_scope'])} | {score} | {table_text(row['catalogs'])} | {table_text(row['access_review'])} | {row['decision']} / {row['publication_status']} |")
    lines += ["", "## Original intake", "", "The original GEE Community Catalog intake and citation study remain archived under [research/citations](research/citations/README.md). Their 363-family snapshot is provenance for the backlog, not a count of published datasets."]
    stream = io.StringIO(newline="")
    fields = list(global_rows[0]) if global_rows else ["id", "title", "geographic_scope"]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(global_rows)
    return {"CANDIDATES.md": "\n".join(lines) + "\n", "candidates.csv": stream.getvalue()}


def check_views(root: Path, records: dict) -> None:
    for name, expected in render_views(records, root).items():
        path = root / name
        if not path.is_file() or path.read_text() != expected:
            raise ValueError(f"Generated candidate backlog is stale: {name}; run scripts/catalog.py --write")
