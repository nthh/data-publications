#!/usr/bin/env python3
"""Export only GEE comparison and release-template historical Git blobs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from provenance_archive import export_archive

SAMPLE_REVISION = "883ebbf0c1a157d402d7635a697bdde3822064ee"
COMPARISONS = {
    "hydrolakes": "hydrolakes",
    "lakeatlas-polygons": "lakeatlas",
    "lakeatlas-points": "lakeatlas",
    "free-flowing-rivers": "free-flowing-rivers",
    "grwl-raw": "grwl-raw",
}
RELEASE_TEMPLATES = [
    "datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/package-spec-template.json",
    "datasets/hydrolakes/releases/v1-local-r1/evidence/package-spec-template.json",
    "datasets/hydrolakes/releases/v1-local-r2/evidence/package-spec-template.json",
    "datasets/hydrolakes/releases/v1-local-r3/reproduction/package-spec-template.json",
    "datasets/lakeatlas/releases/lakeatlas-v1.0-r2/reproduction/package-spec-template.json",
]
GEE = ROOT / "research/gee-release-validation-20261106"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_bindings() -> set[tuple[str, str]]:
    bindings: set[tuple[str, str]] = set()
    receipts = [json.loads(path.read_text()) | {"_path": path}
                for path in (GEE / "receipts").glob("*.json")]
    plans = list((GEE / "plans").glob("*.json"))

    for layer, dataset in COMPARISONS.items():
        report = json.loads((GEE / f"comparisons-r1/{layer}.json").read_text())
        provenance = report["provenance"]
        manifest = yaml.safe_load((ROOT / f"datasets/{dataset}/dataset.yaml").read_text())["publication"]
        if provenance["sample_manifest_sha256"] != manifest["manifest_sha256"]:
            raise ValueError(f"Manifest pin mismatch for {layer}")
        bindings.update({
            (SAMPLE_REVISION, "scripts/gee_validation/sample.py"),
            (SAMPLE_REVISION, "scripts/gee_validation/uv.lock"),
            (SAMPLE_REVISION, manifest["manifest_path"]),
        })

        plan_sha = provenance["capture_plan_sha256"]
        candidates = [r for r in receipts
                      if r.get("git_commit") == provenance["capture_git_commit"]
                      and r.get("plan_sha256") == plan_sha
                      and r.get("script_sha256") == provenance["capture_script_sha256"]]
        if len(candidates) != 1:
            raise ValueError(f"Could not uniquely identify capture receipt for {layer}")
        receipt = candidates[0]
        matching_plans = [path for path in plans if sha(path) == plan_sha]
        if len(matching_plans) != 1:
            raise ValueError(f"Could not uniquely identify request plan for {layer}")
        bindings.update({
            (receipt["git_commit"], "scripts/gee_validation/capture.py"),
            (receipt["git_commit"], "scripts/gee_validation/uv.lock"),
            (receipt["git_commit"], matching_plans[0].relative_to(ROOT).as_posix()),
        })

    pin_count = 0
    for template in RELEASE_TEMPLATES:
        spec = json.loads((ROOT / template).read_text())
        pins = spec.get("workflow_revisions", {})
        pin_count += len(pins)
        bindings.update((revision, path) for path, revision in pins.items())
    if pin_count != 100:
        raise ValueError(f"Expected 100 release workflow pins, found {pin_count}")
    return bindings


if __name__ == "__main__":
    result = export_archive(ROOT, sorted(collect_bindings()))
    result["git_bindings"] = len(collect_bindings())
    result["release_workflow_pins"] = 100
    result["gee_comparisons"] = len(COMPARISONS)
    print(json.dumps(result, indent=2))
