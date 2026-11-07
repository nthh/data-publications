#!/usr/bin/env python3
"""Check frozen metadata offline; --fetch-dir performs bounded public metadata GETs."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from html.parser import HTMLParser

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

def read(path):
    return json.loads(path.read_text())

def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")

def require(condition, message):
    if not condition:
        raise ValueError(message)

def check():
    manifest = read(HERE / "input-manifest.json")
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        require(path.is_file(), f"Missing evidence: {path}")
        raw = path.read_bytes()
        require(len(raw) == entry["bytes"], f"Length changed: {path}")
        require(hashlib.sha256(raw).hexdigest() == entry["sha256"], f"Hash changed: {path}")
    def body(name):
        receipt = read(HERE / "evidence" / (name + ".json"))
        require(receipt.get("status") == 200 and "error" not in receipt, f"Failed receipt: {name}")
        return receipt["body"]
    items = body("wfp-items-august-2020")["features"]
    dates = {f["properties"]["datetime"][:10] for f in items}
    require(len(items) == 31 and dates == {f"2020-08-{day:02d}" for day in range(1, 32)}, "August 2020 incomplete")
    require(not any(x["rel"] == "next" for x in body("wfp-items-august-2020")["links"]), "Unfollowed August pagination")
    for item in items:
        asset = item["assets"]["band"]
        band = asset["raster:bands"][0]
        require(band == {"unit": "1", "nodata": -9999, "data_type": "float32"}, "Revisit recorded units discrepancy")
        require(item["properties"]["proj:shape"] == [2400, 7200], "Unexpected grid")
        require(item["properties"]["proj:transform"] == [0.05, 0, -180, 0, -0.05, 60], "Unexpected transform")
        require("/wfp/chirps-rnl-daily/v3.0/" in asset["href"], "Unexpected product identity")
    require(body("wfp-items-1981-01-01")["features"][0]["properties"]["datetime"][:10] == "1981-01-01", "First-day sample changed")
    require(body("wfp-items-latest")["features"][0]["properties"]["datetime"][:10] == "2026-09-30", "Last-day snapshot changed")
    require(body("wfp-items-october")["features"] == [], "October snapshot changed")
    # The ascending sort was ineffective; retain this failed discovery attempt.
    require(body("wfp-items-earliest")["features"][0]["properties"]["datetime"][:10] == "2026-09-30", "Ascending-sort observation changed")
    ecoregion = body("ecoregion-stac")
    require(any(x.get("rel") == "cite-as" and x["href"] == "https://doi.org/10.1093/biosci/bix014" for x in ecoregion["links"]), "Ecoregion lineage changed")
    require({"ecoregion-parquet", "ecoregion-pmtiles"} <= ecoregion["assets"].keys(), "Ecoregion formats missing")
    jrc = read(HERE / "evidence/jrc-v15-aggregated-list.json")
    tiles = jrc["body"]
    require(jrc["listed_objects"] < jrc["requested_limit"], "Listing might be truncated")
    require(len(tiles) == len({r["name"] for r in tiles}) == 504, "Occurrence count differs")
    require(all(r["name"].startswith("download2024/Aggregated/VER1-5/occurrence/") and r["name"].endswith(".tif") for r in tiles), "Mixed JRC product versions")
    jrc_bytes = sum(r["bytes"] for r in tiles)
    require(jrc_bytes == 14453956859, "JRC byte sum differs")
    tc = read(HERE / "evidence/terraclimate-v11-attributes.json")["selected_attributes"]
    require(tc["version"] == "V1.1" and tc["license"].startswith("CC0 1.0"), "Revisit TerraClimate release/license")
    local = read(HERE / "local-audit.json")
    lake = local["hydrolakes"]
    require(not local["reviewed_paths_dirty"], "Source audit includes uncommitted changes")
    require(lake["feature_count"] == 1427688 and lake["hylak_id"] == {"contiguous": True, "maximum": 1427688, "minimum": 1, "unique": True}, "HydroLAKES coverage changed")
    require(lake["staged_data_identity"] == {"sha256": lake["output_sha256"], "bytes": lake["output_bytes"]}, "Staging and conversion identities differ")
    previous = {r["rank"]: r for r in read(ROOT / "research/top30-download-audit-20261030/inventory.json")}
    priorities = read(HERE / "priorities.json")["recommendations"]
    require([r["priority"] for r in priorities] == [1, 2, 3, 4, 5], "Expected five priorities")
    for row in priorities:
        old = previous[row["top30_rank"]]
        require(row["paper_citations_as_of_2026_10_30"] == old["citations"] and row["work_id"] == old["work_id"] and row["catalogs_in_frozen_top30"] == old["catalogs"], "Citation provenance mismatch")
    require(priorities[2]["source_bytes"] == jrc_bytes, "Priority table uses wrong JRC version size")
    return {"status": "pass", "network_requests": 0, "pinned_files_checked": len(manifest["files"]), "august_2020_stac_items": len(items), "jrc_v15_occurrence_tiles": len(tiles), "jrc_v15_occurrence_bytes": jrc_bytes, "priorities_checked": len(priorities), "scope": "Offline receipt integrity, metadata consistency, arithmetic and citation provenance; no raster/geometry validation executed."}

class BasinLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href", "")
        if tag == "a" and "/hybas_" in href and "lev01-12_v1c.zip" in href and "/hybas_lake_" not in href:
            self.links.append(href)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None

def fetch(destination):
    # Never replace the frozen study. Later reviews get their own directories.
    destination.mkdir(parents=True, exist_ok=False)
    config = read(HERE / "requests.json")
    require(len(config["requests"]) <= 20, "Metadata request budget exceeded")
    failures = []
    opener = urllib.request.build_opener(NoRedirect)
    for job in config["requests"]:
        url = job["url"]
        require(url.startswith("https://") and not re.search(r"\.(tif|tiff|zip|nc|parquet|cog)(?:\?|$)", url), "Only metadata endpoints allowed")
        receipt = {"url": url, "method": "GET", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "data-publications-metadata-audit/1.0"})
            with opener.open(request, timeout=config["timeout_seconds"]) as response:
                raw = response.read(config["max_response_bytes"] + 1)
                require(len(raw) <= config["max_response_bytes"], "Response exceeded metadata cap")
                receipt.update(status=response.status, final_url=response.url, headers={k: v for k, v in response.headers.items() if k.lower() in ("content-type", "content-length", "etag", "last-modified")}, response_bytes=len(raw), response_sha256=hashlib.sha256(raw).hexdigest())
            projection = job["projection"]
            if projection == "json":
                receipt["body"] = json.loads(raw)
            elif projection == "jrc_occurrence":
                rows = json.loads(raw)
                receipt.update(listed_objects=len(rows), requested_limit=10000, body=[r for r in rows if r.get("name", "").startswith("download2024/Aggregated/VER1-5/occurrence/") and r["name"].endswith(".tif")])
            elif projection == "hydrobasins_links":
                parser = BasinLinks()
                parser.feed(raw.decode())
                receipt["selected_links"] = sorted(set(parser.links))
            elif projection == "terraclimate_attributes":
                text = raw.decode()
                receipt["selected_attributes"] = {key: match.group(1) if (match := re.search(r'String ' + key + r' "([^"]*)"', text)) else None for key in ("version", "source", "license", "creator_url", "date_modified")}
            elif projection == "receipt_only":
                receipt["text_saved"] = False
            else:
                raise ValueError(f"Unknown projection: {projection}")
        except Exception as exc:
            receipt["error"] = str(exc)
            failures.append(job["name"])
        dump(destination / (job["name"] + ".json"), receipt)
    return {"status": "incomplete" if failures else "collected", "requests": len(config["requests"]), "failed": failures, "output": str(destination), "note": "New observations need review; they do not update the frozen report or prove data quality."}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Verify frozen evidence offline (default)")
    group.add_argument("--fetch-dir", type=Path, help="Explicitly fetch bounded public metadata into a new directory")
    args = parser.parse_args()
    result = fetch(args.fetch_dir) if args.fetch_dir else check()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["status"] == "incomplete" else 0)
