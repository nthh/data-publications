#!/usr/bin/env python3
"""Generate the exact JRC Occurrence source inventory from pinned listing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research/hydro-releases-20261031/jrc"
LISTING_SHA256 = "338037170377b21953074a9163d68498048764532642ef0f44ee82c1b72e7410"
BASE = "https://s3.waw4-1.cloudferro.com/swift/v1/global-surface-water/"


def inventory():
    raw = (EVIDENCE / "occurrence-current-inventory-response.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != LISTING_SHA256:
        raise ValueError("Pinned listing evidence changed")
    listed = json.loads(raw)
    selected = sorted((obj for obj in listed
                       if "/occurrence/" in obj["name"] and obj["name"].endswith(".tif")),
                      key=lambda obj: obj["name"])
    if len(selected) != 504 or sum(obj["bytes"] for obj in selected) != 14_453_956_859:
        raise ValueError("Occurrence inventory scope differs from the qualified release")
    if len({obj["name"] for obj in selected}) != len(selected):
        raise ValueError("Duplicate object names")
    return {
        "product": "JRC Global Surface Water Occurrence v1.5 (1984–2024)",
        "producer_page": "https://global-surface-water.appspot.com/download",
        "listing_evidence": "research/hydro-releases-20261031/jrc/occurrence-current-inventory-response.json",
        "listing_sha256": LISTING_SHA256,
        "objects": len(selected),
        "size_bytes": sum(obj["bytes"] for obj in selected),
        "hash_note": "source_listing_hash is opaque source metadata, not a verified SHA-256; no full object was downloaded.",
        "assets": [{"url": BASE + quote(obj["name"], safe="/"),
                    "source_object": obj["name"], "size_bytes": obj["bytes"],
                    "source_listing_hash": obj["hash"], "last_modified": obj["last_modified"]}
                   for obj in selected],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    doc = inventory()
    content = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    target = Path(__file__).with_name("source-inventory.json")
    if args.check:
        if target.read_text() != content:
            raise SystemExit("Generated source inventory is stale")
    else:
        target.write_text(content)
    print(json.dumps({"status": "passed", "objects": doc["objects"], "size_bytes": doc["size_bytes"]}))


if __name__ == "__main__":
    main()
