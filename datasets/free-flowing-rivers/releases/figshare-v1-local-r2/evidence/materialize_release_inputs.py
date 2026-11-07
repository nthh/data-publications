#!/usr/bin/env python3
"""Materialize portable FFR package/fidelity templates into ignored local inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CLEAN = "__CLEAN_CHECKOUT_ROOT__"


def read_template(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"template must contain a JSON object: {path}")
    return value


def resolve_from_template(value: str, template_dir: Path) -> str:
    path = Path(value).expanduser()
    return str((path if path.is_absolute() else template_dir / path).resolve())


def write_new(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    if path.exists():
        raise FileExistsError(f"refusing to overwrite materialized input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)


def package(args: argparse.Namespace) -> None:
    template_path = args.template.expanduser().resolve()
    spec = read_template(template_path)
    base = template_path.parent
    for key in ("dataset_record_path", "source_fidelity_report_path", "clean_rebuild_report_path"):
        spec[key] = resolve_from_template(spec[key], base)
    for asset in spec.get("assets", []):
        asset["path"] = resolve_from_template(asset["path"], base)
        if asset.get("field_dictionary_path"):
            asset["field_dictionary_path"] = resolve_from_template(asset["field_dictionary_path"], base)
    for item in spec.get("supporting_files", []):
        item["path"] = resolve_from_template(item["path"], base)
    if args.fidelity_dir:
        fidelity_root = args.fidelity_dir.expanduser().resolve()
        spec["source_fidelity_report_path"] = str(fidelity_root / "source-fidelity.json")
        spec["clean_rebuild_report_path"] = str(fidelity_root / "clean-rebuild.json")
    spec["output_dir"] = str(args.package_output.expanduser().resolve())
    write_new(args.output, spec)


def fidelity(args: argparse.Namespace) -> None:
    template_path = args.template.expanduser().resolve()
    spec = read_template(template_path)
    base = template_path.parent
    clean_root = args.clean_checkout.expanduser().resolve()
    fields = (
        "raw_asset_path", "rebuilt_raw_asset_path", "final_asset_path",
        "rebuilt_final_asset_path", "augmentation_report_path",
        "rebuilt_augmentation_report_path",
    )
    for asset in spec.get("assets", []):
        for key in fields:
            value = asset[key]
            if value.startswith(CLEAN + "/"):
                asset[key] = str(clean_root / value[len(CLEAN) + 1:])
            else:
                asset[key] = resolve_from_template(value, base)
    spec["source_validation_path"] = resolve_from_template(spec["source_validation_path"], base)
    write_new(args.output, spec)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    package_parser = sub.add_parser("package", help="resolve package template paths and set a new package output")
    package_parser.add_argument("--template", type=Path, required=True)
    package_parser.add_argument("--output", type=Path, required=True, help="new ignored spec JSON path")
    package_parser.add_argument("--package-output", type=Path, required=True, help="new package output directory")
    package_parser.add_argument("--fidelity-dir", type=Path, help="use reports from a fresh normalization run")
    package_parser.set_defaults(run=package)
    fidelity_parser = sub.add_parser("fidelity", help="resolve fidelity inputs and clean-checkout paths")
    fidelity_parser.add_argument("--template", type=Path, required=True)
    fidelity_parser.add_argument("--output", type=Path, required=True, help="new ignored spec JSON path")
    fidelity_parser.add_argument("--clean-checkout", type=Path, required=True)
    fidelity_parser.set_defaults(run=fidelity)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
