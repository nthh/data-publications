#!/usr/bin/env python3
"""Prepare a fresh ignored viewer run and launch its two loopback HTTP origins."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "scripts" / "cloud_viewer"
DEFAULT_PLAN = Path("research/grwl-straight-segments-20261102/staging-r1/immutable-upload-plan.json")
DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DISPLAY_RELEASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RunError(ValueError):
    """Raised when runtime inputs or local tooling are incomplete or inconsistent."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunError(f"{label} must be an object")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunError(f"cannot read {label} at {path}: {exc}") from exc


def _canonical_plan_products(root: Path, plan_path: Path, legacy_plan: bool = False) -> list[dict[str, str]]:
    plan = _read_json(plan_path, "immutable upload plan")
    raw_products = plan.get("products")
    if not isinstance(raw_products, list) or len(raw_products) != 5:
        raise RunError("immutable plan must select exactly five prepared products")
    seen: set[str] = set()
    selected: list[dict[str, str]] = []
    for raw in raw_products:
        item = _object(raw, "plan product")
        dataset_id = item.get("dataset_id")
        if not isinstance(dataset_id, str) or not DATASET_ID.fullmatch(dataset_id):
            raise RunError(f"invalid plan dataset_id: {dataset_id!r}")
        if dataset_id in seen:
            raise RunError(f"duplicate plan product: {dataset_id}")
        seen.add(dataset_id)
        canonical_path = root / "datasets" / dataset_id / "dataset.yaml"
        try:
            import yaml

            canonical = _object(yaml.safe_load(canonical_path.read_text(encoding="utf-8")), f"{dataset_id} canonical record")
        except (OSError, yaml.YAMLError) as exc:
            raise RunError(f"cannot read canonical record {canonical_path}: {exc}") from exc
        publication = _object(canonical.get("publication"), f"{dataset_id}.publication")
        source_coop = _object(publication.get("source_coop"), f"{dataset_id}.publication.source_coop")
        release = publication.get("release")
        owner = source_coop.get("owner")
        product_id = source_coop.get("product_id")
        if not all(isinstance(value, str) and value for value in (release, owner, product_id)):
            raise RunError(f"{dataset_id} canonical release, owner, and product_id must be set")
        for field, expected in (("release", release), ("owner", owner), ("product_id", product_id), ("bucket", owner)):
            if item.get(field) != expected:
                raise RunError(
                    f"plan {field} mismatch for {dataset_id}: canonical={expected!r}, plan={item.get(field)!r}"
                )
        display = publication.get("display")
        if display is not None and not isinstance(display, dict):
            raise RunError(f"{dataset_id} canonical publication.display must be an object")
        if isinstance(display, dict):
            display_release = display.get("release")
            manifest_sha = display.get("manifest_sha256")
            if not isinstance(display_release, str) or len(display_release) > 40 or not DISPLAY_RELEASE.fullmatch(display_release) or not isinstance(manifest_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha):
                raise RunError(f"{dataset_id} canonical display release/hash is invalid")
            if display.get("manifest_path") != f"datasets/{dataset_id}/display/{display_release}/manifest.json":
                raise RunError(f"{dataset_id} canonical display manifest path does not match release")
        selected.append({"dataset_id": dataset_id, "release": release, "owner": owner, "product_id": product_id,
                         **({"display_release": display["release"], "display_manifest_sha256": display["manifest_sha256"]}
                            if isinstance(display, dict) else {})})
    files = plan.get("files")
    if not isinstance(files, list):
        raise RunError("immutable plan files must be an array")
    for product in selected:
        matches = [
            row
            for row in files
            if isinstance(row, dict)
            and isinstance(row.get("source"), dict)
            and row["source"].get("kind") == "package"
            and row["source"].get("dataset_id") == product["dataset_id"]
            and row["source"].get("path") == "manifest.json"
        ]
        if len(matches) != 1:
            raise RunError(f"plan must contain exactly one root manifest for {product['dataset_id']}")
        expected_route = f"{product['product_id']}/releases/{product['release']}/manifest.json"
        if matches[0].get("object_key") != expected_route or matches[0].get("bucket") != product["owner"]:
            raise RunError(f"plan root manifest route/bucket mismatch for {product['dataset_id']}")
        if product.get("display_release"):
            display_entries = [
                row for row in files
                if isinstance(row, dict) and isinstance(row.get("source"), dict)
                and row["source"].get("kind") == "display_package"
                and row["source"].get("dataset_id") == product["dataset_id"]
            ]
            display_manifest = [row for row in display_entries if row["source"].get("path") == "manifest.json"]
            expected_display_route = f"{product['product_id']}/display/{product['display_release']}/manifest.json"
            if not display_manifest and legacy_plan:
                product.pop("display_release", None)
                product.pop("display_manifest_sha256", None)
                continue
            if len(display_manifest) != 1 or display_manifest[0].get("object_key") != expected_display_route:
                raise RunError(f"plan is missing the canonical display package manifest for {product['dataset_id']}")
            if display_manifest[0].get("sha256") != product["display_manifest_sha256"]:
                raise RunError(f"plan display manifest hash differs from canonical pin for {product['dataset_id']}")
    return selected


def _parse_overrides(values: list[str], root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        dataset_id, separator, raw_path = value.partition("=")
        if not separator or not dataset_id or not raw_path:
            raise RunError(f"--package must have the form ID=PATH: {value!r}")
        if dataset_id in result:
            raise RunError(f"duplicate --package override for {dataset_id}")
        path = Path(raw_path).expanduser()
        result[dataset_id] = (path if path.is_absolute() else root / path)
    return result


def _manifest_matches(package: Path, product: dict[str, str]) -> Path:
    if package.is_symlink() or not package.is_dir():
        raise RunError(f"package directory is missing or a symlink: {package}")
    manifest_path = package / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RunError(f"package root manifest is missing or a symlink: {manifest_path}")
    manifest = _read_json(manifest_path, f"{product['dataset_id']} package manifest")
    dataset_names = [manifest.get(key) for key in ("dataset", "dataset_id") if manifest.get(key) is not None]
    releases = [manifest.get(key) for key in ("release", "release_id") if manifest.get(key) is not None]
    if not dataset_names or any(value != product["dataset_id"] for value in dataset_names):
        raise RunError(f"package manifest dataset mismatch for {product['dataset_id']}: {dataset_names!r}")
    if not releases or any(value != product["release"] for value in releases):
        raise RunError(f"package manifest release mismatch for {product['dataset_id']}: {releases!r}")
    return package.resolve(strict=True)


def resolve_packages(
    data_root: Path,
    products: list[dict[str, str]],
    overrides: dict[str, Path] | None = None,
) -> dict[str, Path]:
    overrides = overrides or {}
    known_ids = {product["dataset_id"] for product in products}
    unexpected = set(overrides) - known_ids
    if unexpected:
        raise RunError(f"--package overrides are not selected by the plan: {sorted(unexpected)}")
    resolved: dict[str, Path] = {}
    for product in products:
        dataset_id = product["dataset_id"]
        if dataset_id in overrides:
            resolved[dataset_id] = _manifest_matches(overrides[dataset_id], product)
            continue
        release = product["release"]
        candidates = [
            data_root / dataset_id / release,
            data_root / dataset_id / "releases" / release,
            data_root / dataset_id / "releases" / f"{release}-prepared",
        ]
        present = [candidate for candidate in candidates if os.path.lexists(candidate)]
        if not present:
            raise RunError(
                f"no package directory found for {dataset_id}/{release}; checked: "
                + ", ".join(str(path) for path in candidates)
            )
        if len(present) > 1:
            raise RunError(
                f"ambiguous package directories for {dataset_id}/{release}; pass --package {dataset_id}=PATH: "
                + ", ".join(str(path) for path in present)
            )
        resolved[dataset_id] = _manifest_matches(present[0], product)
    return resolved


def resolve_display_packages(
    data_root: Path,
    products: list[dict[str, str]],
    overrides: dict[str, Path] | None = None,
) -> dict[str, Path]:
    overrides = overrides or {}
    display_products = {product["dataset_id"]: product for product in products if product.get("display_release")}
    unexpected = set(overrides) - set(display_products)
    if unexpected:
        raise RunError(f"--display-package overrides have no canonical display reference: {sorted(unexpected)}")
    resolved: dict[str, Path] = {}
    for dataset_id, product in display_products.items():
        if dataset_id in overrides:
            package = overrides[dataset_id]
        else:
            package = data_root / dataset_id / "display" / product["display_release"]
            if not os.path.lexists(package):
                raise RunError(f"no display package directory found for {dataset_id}/{product['display_release']}: {package}")
        if package.is_symlink() or not package.is_dir():
            raise RunError(f"display package directory is missing or a symlink: {package}")
        manifest = package / "manifest.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise RunError(f"display package manifest is missing or a symlink: {manifest}")
        try:
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        except OSError as exc:
            raise RunError(f"cannot read display package manifest {manifest}: {exc}") from exc
        if digest != product["display_manifest_sha256"]:
            raise RunError(f"display package manifest hash differs from canonical pin for {dataset_id}")
        resolved[dataset_id] = package.resolve(strict=True)
    return resolved


def _check_frontend(no_build: bool) -> tuple[str | None, Path | None]:
    if no_build:
        dist = FRONTEND / "dist"
        if not (dist / "index.html").is_file():
            raise RunError(f"--no-build requires an existing built UI at {dist}")
        return None, dist
    npm = shutil.which("npm")
    required = [
        FRONTEND / "node_modules" / "esbuild" / "package.json",
        FRONTEND / "node_modules" / "@duckdb" / "duckdb-wasm" / "dist" / "duckdb-eh.wasm",
        FRONTEND / "node_modules" / "@duckdb" / "duckdb-wasm" / "dist" / "duckdb-browser-eh.worker.js",
        FRONTEND / "node_modules" / "maplibre-gl" / "dist" / "maplibre-gl-worker.mjs",
    ]
    if not npm or not shutil.which("node") or any(not path.is_file() for path in required):
        raise RunError(
            "frontend dependencies/build tooling are missing. From the repository root, run:\n"
            "  cd scripts/cloud_viewer\n"
            "  npm ci --ignore-scripts --no-audit --no-fund\n"
            "  npm run setup"
        )
    return npm, None


def _new_run_dir(repo: Path) -> Path:
    parent = repo / ".local" / "cloud-viewer-runs"
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        destination = parent / f"run-{stamp}-{secrets.token_hex(4)}"
        try:
            destination.mkdir()
            return destination
        except FileExistsError:
            continue
    raise RunError(f"could not allocate a unique viewer run directory under {parent}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO), help="repository root (defaults to this checkout)")
    parser.add_argument("--data-root", default=".local", help="local package root, commonly repo/.local")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN), help="immutable Source Cooperative upload plan")
    parser.add_argument("--package", action="append", default=[], metavar="ID=PATH", help="override one package location")
    parser.add_argument("--display-package", action="append", default=[], metavar="ID=PATH", help="override one display package location")
    parser.add_argument("--legacy-plan", action="store_true",
                        help="allow a historical plan without display_package entries after canonical display references are added")
    parser.add_argument("--ui-port", type=int, default=8910)
    parser.add_argument("--object-port", type=int, default=8911)
    parser.add_argument("--no-build", action="store_true", help="serve the existing scripts/cloud_viewer/dist bundle")
    args = parser.parse_args(argv)
    if not (1 <= args.ui_port <= 65535 and 1 <= args.object_port <= 65535):
        parser.error("ports must be between 1 and 65535")
    if args.ui_port == args.object_port:
        parser.error("--ui-port and --object-port must differ")
    root = Path(args.root).expanduser().resolve()
    data_root = Path(args.data_root).expanduser()
    data_root = (data_root if data_root.is_absolute() else root / data_root).resolve()
    plan_path = Path(args.plan).expanduser()
    plan_path = (plan_path if plan_path.is_absolute() else root / plan_path).resolve()
    try:
        products = _canonical_plan_products(root, plan_path, args.legacy_plan)
        packages = resolve_packages(data_root, products, _parse_overrides(args.package, root))
        display_packages = resolve_display_packages(data_root, products, _parse_overrides(args.display_package, root))
        npm, existing_ui = _check_frontend(args.no_build)
        run_dir = _new_run_dir(root)
        manifest = run_dir / "runtime-config.json"
        ui_root = existing_ui or run_dir / "ui"
        prepare_cmd = [
            sys.executable,
            str(FRONTEND / "prepare.py"),
            "--root",
            str(root),
            "--plan",
            str(plan_path),
            "--output",
            str(manifest),
        ]
        prepare_cmd.extend(f"--package={dataset_id}={path}" for dataset_id, path in packages.items())
        prepare_cmd.extend(f"--display-package={dataset_id}={path}" for dataset_id, path in display_packages.items())
        if args.legacy_plan:
            prepare_cmd.append("--legacy-plan")
        subprocess.run(prepare_cmd, cwd=root, check=True)
        if not args.no_build:
            subprocess.run(
                [npm, "run", "build", "--", "--out", str(ui_root)], cwd=FRONTEND, check=True
            )
        stdout_log = run_dir / "server.log"
        request_log = run_dir / "requests.jsonl"
        serve_cmd = [
            sys.executable,
            str(FRONTEND / "serve.py"),
            "--manifest",
            str(manifest),
            "--ui-root",
            str(ui_root),
            "--host",
            "127.0.0.1",
            "--ui-port",
            str(args.ui_port),
            "--object-port",
            str(args.object_port),
            "--log",
            str(request_log),
        ]
        with stdout_log.open("x", encoding="utf-8") as stream:
            process = subprocess.Popen(
                serve_cmd,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                close_fds=True,
                start_new_session=True,
            )
        time.sleep(0.25)
        if process.poll() is not None:
            raise RunError(f"viewer server exited during startup; inspect {stdout_log}")
    except (RunError, OSError, subprocess.CalledProcessError) as exc:
        print(f"cloud-viewer run: {exc}", file=sys.stderr)
        return 2
    print(f"Run directory: {run_dir}")
    print(f"Viewer: http://127.0.0.1:{args.ui_port}/")
    print(f"Objects: http://127.0.0.1:{args.object_port}/")
    print(f"Server PID: {process.pid}")
    print(f"Logs: {stdout_log} and {request_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
