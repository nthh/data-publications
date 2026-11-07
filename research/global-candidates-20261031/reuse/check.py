#!/usr/bin/env python3
"""Offline integrity checks for the retained reuse-observation lane."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
LANE = ROOT / "research/global-candidates-20261031/reuse"
DATA = LANE / "reviewed.json"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    doc = json.loads(DATA.read_text())
    candidates = doc.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != doc.get("candidate_count"):
        fail("candidate_count does not match candidates list")
    keys = [c.get("evidence_key") for c in candidates]
    ids = [c.get("suggested_id") for c in candidates]
    if any(not isinstance(x, str) or not x for x in keys + ids):
        fail("each observation needs nonempty suggested_id and evidence_key")
    if len(set(keys)) != len(keys) or len(set(ids)) != len(ids):
        fail("duplicate evidence_key or suggested_id")
    all_evidence = 0
    for c in candidates:
        target = c.get("target_id") or c.get("existing_record_id")
        if not target or not re.fullmatch(r"[A-Za-z0-9_-]+", target):
            fail(f"invalid or missing current target id for {c['suggested_id']}")
        record = ROOT / "datasets" / target / "dataset.yaml"
        if not record.is_file() or not re.search(rf"(?m)^id:\s*['\"]?{re.escape(target)}(?:['\"])?\s*$", record.read_text()):
            fail(f"target_id does not resolve to a canonical dataset record: {target}")
        if c.get("existing_record_id") and c["existing_record_id"] != target:
            fail(f"existing_record_id and target_id differ for {c['suggested_id']}")
        if not c.get("observed_on") or not c.get("source_evidence"):
            fail(f"missing observed_on or source_evidence for {c['suggested_id']}")
        if not isinstance(c.get("format_labels"), list) or not isinstance(c.get("recommended_formats"), list):
            fail(f"format fields must be lists for {c['suggested_id']}")
        for evidence in c["source_evidence"]:
            if evidence.get("path", "").startswith("datasets/"):
                fail(f"canonical dataset path cannot be hashed as source evidence: {evidence['path']}")
            path = ROOT / evidence["path"]
            if not path.is_file():
                fail(f"missing source evidence file: {evidence['path']}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != evidence.get("sha256"):
                fail(f"SHA-256 mismatch: {evidence['path']}")
            all_evidence += 1
        for source in c.get("sources", []):
            if not source.get("url", "").startswith("https://") or not source.get("entry_id"):
                fail(f"invalid source URL or missing entry_id in {c['suggested_id']}")
    print(f"OK: {len(candidates)} observations, {all_evidence} source file hashes, all current target IDs resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
