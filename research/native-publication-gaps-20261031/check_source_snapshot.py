#!/usr/bin/env python3
"""Offline, hash-pinned name/DOI check of Source Cooperative metadata.

This emits discovery leads, not a proof that hosted datasets are absent or equal.
Supply the ignored original JSONL snapshot explicitly. No network calls or writes.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATTERNS = {
    "free-flowing-rivers": r"\bffr\b|free[- ]flowing rivers|7688801|s41586-019-1111-9",
    "lakeatlas": r"lakeatlas|19312001|s41597-022-01425-z",
    "hydrolakes": r"hydrolakes|ncomms13603",
    "grwl": r"\bgrwl\b|global river widths? from landsat|18624542|1297434|aat0636",
    "river-plastic-inputs": r"river plastic inputs|4725541|ncomms15611|lebreton",
    "terraclimate_baseline": r"terraclimate|sdata.?2017.?191",
    "cru_ts_v4": r"cru[- _]?ts|climatic research unit|s41597-020-0453-3",
    "grod": r"\bgrod\b|global river obstruction|5793918|2021wr030386",
    "swot_pld": r"prior lake database|swot.{0,40}\bpld\b|2023wr036896",
    "global_dam_watch": r"\bgdw\b|global dam watch|25988293|s41597-024-03752-9",
    "glacier": r"hugonnet|ww_tvol|glacier elevation change|s41586-021-03436-z",
    "earthstat_monfreda_crop_maps_2000": r"earthstat|monfreda|2007gb002947",
    "hyde": r"\bhyde\b|f45d44|history database of the global environment",
    "glim_global_lithological_map_v1": r"\bglim\b|global lithological|788537|2012gc004370",
    "hwsd": r"\bhwsd\b|harmoni.ed world soil database",
    "isric": r"soilgrids|soil-7-217-2021",
    "merra2": r"merra[- _]?2|nasa.{0,10}power",
    "riveratlas": r"riveratlas|hydroatlas|s41597-019-0300-6",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    criteria = json.loads((HERE / "criteria.json").read_text())["snapshot_acceptance"]
    body = args.snapshot.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if digest != criteria["expected_sha256"] or len(body) != criteria["expected_bytes"]:
        raise SystemExit("Snapshot bytes/hash differ from the declared input; create a new capture instead.")
    records = [json.loads(line) for line in body.splitlines() if line.strip()]
    if len(records) != criteria["expected_records"]:
        raise SystemExit("Snapshot record count differs from the declared input.")
    results = {}
    for key, expression in PATTERNS.items():
        pattern = re.compile(expression, re.I)
        hits = []
        for record in records:
            terms = sorted(set(m.group(0) for m in pattern.finditer(json.dumps(record, ensure_ascii=False))))
            if terms:
                hits.append({
                    "id": record.get("id") or f"{record['account_id']}/{record['product_id']}",
                    "title": record.get("title"),
                    "matched_terms": terms, "cataloged_at": record.get("cataloged_at"),
                })
        results[key] = {"regex": expression, "matched_records": hits}
    print(json.dumps({
        "source_url": criteria["source_url"], "source_retrieved_at": criteria["retrieved_at"],
        "source_sha256": digest, "source_bytes": len(body), "records_searched": len(records),
        "latest_cataloged_at": max(r.get("cataloged_at", "") for r in records),
        "results": results,
        "interpretation": "Name/DOI matches in a dated metadata snapshot. Hits are leads; no matches do not prove absence.",
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
