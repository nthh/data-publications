#!/usr/bin/env python3
"""Resolve path-free LakeATLAS r2 fidelity and package input templates."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"template must be a JSON object: {path}")
    return value


def replace(value: Any, roots: dict[str, Path]) -> Any:
    if isinstance(value, dict):
        return {key: replace(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [replace(item, roots) for item in value]
    if isinstance(value, str):
        for token, root in roots.items():
            if value == token:
                return str(root.resolve())
            if value.startswith(token + "/"):
                return str((root / value[len(token) + 1 :]).resolve())
    return value


def write_new(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    if path.exists():
        raise FileExistsError(f"refuse to overwrite materialized input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)


def observed_clean_checkout(path: Path, expected: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=path, text=True)
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=path, text=True).strip()
    if commit != expected:
        raise ValueError(f"clean checkout HEAD {commit} differs from required {expected}")
    if status:
        raise ValueError("clean checkout has uncommitted or untracked files")
    if branch:
        raise ValueError("clean checkout must be detached")
    return {
        "commit": commit,
        "detached_checkout": True,
        "git_status_porcelain_empty": True,
        "checked_by": "datasets/lakeatlas/releases/lakeatlas-v1.0-r2/reproduction/materialize_release_inputs.py",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fidelity = sub.add_parser("fidelity")
    fidelity.add_argument("--artifact-root", type=Path, required=True)
    fidelity.add_argument("--clean-checkout", type=Path, required=True)
    fidelity.add_argument("--output", type=Path, required=True)
    package = sub.add_parser("package")
    package.add_argument("--artifact-root", type=Path, required=True)
    package.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    package.add_argument("--fidelity-root", type=Path, required=True)
    package.add_argument("--portable-evidence-root", type=Path, required=True)
    package.add_argument("--package-output", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    template_dir = Path(__file__).resolve().parent
    if args.command == "fidelity":
        value = load(template_dir / "fidelity-normalizer-template.json")
        expected = value["rebuild_context"]["clean_checkout"]["commit"]
        value["rebuild_context"]["clean_checkout"] = observed_clean_checkout(args.clean_checkout, expected)
        value = replace(value, {"__ARTIFACT_ROOT__": args.artifact_root.expanduser().resolve()})
    else:
        value = load(template_dir / "package-spec-template.json")
        value = replace(value, {
            "__ARTIFACT_ROOT__": args.artifact_root.expanduser().resolve(),
            "__REPO_ROOT__": args.repo_root.expanduser().resolve(),
            "__FIDELITY_ROOT__": args.fidelity_root.expanduser().resolve(),
            "__PORTABLE_EVIDENCE_ROOT__": args.portable_evidence_root.expanduser().resolve(),
            "__PACKAGE_OUTPUT__": args.package_output.expanduser().resolve(),
        })
    write_new(args.output, value)


if __name__ == "__main__":
    main()
