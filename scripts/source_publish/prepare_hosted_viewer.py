#!/usr/bin/env python3
"""Pin a hosted viewer to the exact five-product Source Cooperative upload plan.

This prepares local UI configuration and frozen browser cases. It never uploads data.
The source object origin is always https://data.source.coop.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import yaml


DATASET_IDS = ("river-plastic-inputs", "hydrolakes", "lakeatlas", "free-flowing-rivers", "grwl-raw")
ORIGIN = "https://data.source.coop"
REGIONAL = {
    "river-plastic-inputs": "atlantic_coast",
    "hydrolakes": "north_america",
    "lakeatlas": "north_america",
    "free-flowing-rivers": "north_america",
}
RAW_VIEWS = [
    *({"name": "mississippi", "center": [-90, 35.51628964037926], "zoom": zoom} for zoom in range(13)),
    *({"name": "amazon", "center": [-60, -3], "zoom": zoom} for zoom in (0, 3, 7, 8)),
    *({"name": "dateline", "center": [-179.99965, 71.197295], "zoom": zoom} for zoom in (3, 7, 8)),
]


class HostedError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def load_prepare(root: Path):
    path = root / "scripts/cloud_viewer/prepare.py"
    spec = importlib.util.spec_from_file_location("cloud_viewer_prepare_hosted", path)
    if spec is None or spec.loader is None:
        raise HostedError(f"cannot load viewer preparer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DATASET_IDS = DATASET_IDS
    choose_id = module._choose_id_field
    read_style = module._read_style

    def choose_raw_id(names):
        return "feature_id" if "feature_id" in names else choose_id(names)

    module._choose_id_field = choose_raw_id

    def read_width_style(path):
        if path.name != "width.json" or "raw-v01.01-display-r3" not in path.parts:
            return read_style(path)
        style = json.loads(path.read_text(encoding="utf-8"))
        layers = style.get("layers", [])
        overview = next((item for item in layers if item.get("source-layer") == "grwl_width_overview"
                         and item.get("source") == "data" and item.get("type") == "circle"
                         and item.get("maxzoom") == 8), None)
        detail = next((item for item in layers if item.get("source-layer") == "grwl_raw"
                       and item.get("source") == "data" and item.get("type") == "line"
                       and item.get("minzoom") == 8), None)
        if overview is None or detail is None:
            raise HostedError("raw GRWL style lacks pinned width overview/detail layers")
        return "grwl_raw", "line"

    module._read_style = read_width_style
    return module


def adapt_config(base: dict, plan: dict, records: dict, raw_manifest: dict) -> tuple[dict, dict]:
    """Convert checked local bindings to exact hosted URLs and freeze browser views."""
    products = {item["dataset_id"]: item for item in plan["products"]}
    if set(products) != set(DATASET_IDS):
        raise HostedError("plan must contain exactly the five selected datasets")
    entries = {"/nthh/" + item["object_key"]: item for item in plan["files"]}
    if len(entries) != len(plan["files"]) or set(entries) != set(base["objects"]):
        raise HostedError("local bindings do not cover the exact immutable upload plan")
    for path, item in entries.items():
        bound = base["objects"][path]
        if (bound["sha256"], bound["size_bytes"]) != (item["sha256"], item["size_bytes"]):
            raise HostedError(f"planned object identity differs: {path}")
        if item.get("endpoint") != ORIGIN or item.get("raw_url_proposed") != ORIGIN + path:
            raise HostedError(f"planned hosted URL differs: {path}")
        if item.get("bucket") != "nthh":
            raise HostedError(f"planned bucket differs: {path}")
    config = base["viewer"]
    config["object_origin"] = ORIGIN
    config["title"] = "Source Cooperative hosted data viewer"
    if {item["id"] for item in config["datasets"]} != set(DATASET_IDS):
        raise HostedError("viewer datasets do not match selected products")
    raw_assets = raw_manifest.get("assets")
    if raw_manifest.get("dataset_id") != "grwl-raw" or not isinstance(raw_assets, list) or len(raw_assets) != 1:
        raise HostedError("raw GRWL display manifest has no unique asset")
    raw_asset = raw_assets[0]
    if raw_asset.get("overview", {}).get("mode") != "width_samples" or raw_asset.get("detail_min_zoom") != 8:
        raise HostedError("raw GRWL width overview or detail zoom is missing")
    cases = []
    products_out = []
    for dataset in config["datasets"]:
        dataset_id = dataset["id"]
        product = products[dataset_id]
        record = records[dataset_id]
        source_coop = record["publication"]["source_coop"]
        if dataset["state"] != "prepared":
            raise HostedError(f"dataset is not prepared: {dataset_id}")
        dataset["title"] = source_coop.get("title") or dataset["title"]
        dataset["attribution"] = source_coop.get("attribution") or dataset["attribution"]
        summary = source_coop.get("summary") or dataset["summary"]
        # A few canonical publication descriptions still describe the preupload
        # state; that sentence cannot be carried into a hosted review UI.
        summary = re.sub(r"These releases are prepared locally; no product has been created or uploaded\.?", "", summary)
        dataset["summary"] = summary.strip()
        license_note = source_coop.get("license_note") or dataset.get("license")
        if isinstance(license_note, str):
            dataset["license"] = re.sub(r"No public product has been created or uploaded\.?", "", license_note).strip()
        dataset["limitations"] = source_coop.get("limitations", [])
        # The previous viewer preparer reads historical supplemental evidence. The
        # canonical record is the present source for these release limitations.
        dataset["gee"] = {"status": "sampled_fail", "summary": " ".join(
            item for item in dataset["limitations"] if "GEE" in item), "evidence": []}
        if dataset_id == "grwl-raw":
            if len(dataset["layers"]) != 1:
                raise HostedError("raw GRWL requires one display layer")
            layer = dataset["layers"][0]
            if (layer["sha256"], layer["size_bytes"]) != (raw_asset["sha256"], raw_asset["size_bytes"]):
                raise HostedError("raw GRWL display asset differs from pinned manifest")
            if layer["source_layer"] != raw_asset["source_layer"] or layer["id_field"] != "feature_id":
                raise HostedError("raw GRWL source layer or feature ID differs")
            for field in ("overview", "detail_min_zoom", "attribute_fields", "id_encoding"):
                layer[field] = raw_asset[field]
            layer["width_field"] = "width_m"
            layer["analytic"]["lookup_mode"] = "exact_id"
            if "feature_id" not in layer["analytic"]["fields"]:
                raise HostedError("raw GRWL analytic source lacks feature_id")
        for layer in dataset["layers"]:
            for asset in (layer, layer.get("analytic")):
                if asset is None:
                    continue
                path = asset.get("object_path")
                item = entries.get(path)
                if not item or (asset.get("sha256"), asset.get("size_bytes")) != (item["sha256"], item["size_bytes"]):
                    raise HostedError(f"viewer asset is absent or differs from plan: {path}")
            if dataset_id != "grwl-raw":
                for region in ("global", REGIONAL[dataset_id]):
                    cases.append({"id": f"{dataset_id}-{layer['id']}-{region}", "dataset_id": dataset_id,
                                  "layer_id": layer["id"], "region": region})
        if dataset_id == "grwl-raw":
            for view in RAW_VIEWS:
                cases.append({"id": f"grwl-raw-{view['name']}-z{view['zoom']}", "dataset_id": dataset_id,
                              "layer_id": dataset["layers"][0]["id"], "view": view})
        product_id = product["product_id"]
        if product_id != source_coop.get("product_id") or product["owner"] != "nthh":
            raise HostedError(f"product identity differs: {dataset_id}")
        release = product["release"]
        display_release = record["publication"].get("display", {}).get("release")
        prefixes = [f"{product_id}/releases/{release}/"]
        if display_release:
            prefixes.append(f"{product_id}/display/{display_release}/")
        products_out.append({"dataset_id": dataset_id, "product_id": product_id, "release": release,
                             "display_release": display_release, "planned_object_prefixes": prefixes,
                             "planned_object_url_prefixes": [f"{ORIGIN}/nthh/{prefix}" for prefix in prefixes],
                             "catalog_url": f"https://source.coop/nthh/{product_id}"})
    if sum(len(item["layers"]) for item in config["datasets"]) != 6 or len(cases) != 30:
        raise HostedError("expected six display layers and thirty frozen browser cases")
    cases_doc = {"schema_version": 1, "object_origin": ORIGIN, "products": products_out,
                 "objects": {ORIGIN + path: {"size_bytes": item["size_bytes"], "sha256": item["sha256"],
                                                   "content_type": item["content_type"]} for path, item in entries.items()},
                 "cases": cases, "plan_sha256": None}
    return config, cases_doc


class HostedUIHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self._serve(False)

    def do_GET(self):
        self._serve(True)

    def _serve(self, body_allowed: bool):
        route = urlsplit(self.path).path
        if route == "/viewer-config.json":
            body, kind = self.server.config_bytes, "application/json; charset=utf-8"
        else:
            if "%" in route or "\\" in route or "\x00" in route or any(part in (".", "..") for part in route.split("/")):
                self.send_error(404)
                return
            relative = "index.html" if route == "/" else route.lstrip("/")
            base = self.server.ui_root
            candidate = base / relative
            if any(path.is_symlink() for path in (base, *candidate.parents, candidate)) or not candidate.is_file():
                self.send_error(404)
                return
            try:
                candidate.resolve().relative_to(base.resolve())
            except ValueError:
                self.send_error(404)
                return
            body = candidate.read_bytes()
            kind = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.end_headers()
        if body_allowed:
            self.wfile.write(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--root", type=Path, default=Path.cwd())
    prep.add_argument("--plan", type=Path, default=Path("research/source-publication-20261106/staging-r2/immutable-upload-plan.json"))
    prep.add_argument("--package", action="append", default=[], metavar="ID=PATH")
    prep.add_argument("--display-package", action="append", default=[], metavar="ID=PATH")
    prep.add_argument("--out", type=Path, required=True, help="new output directory")
    serve = sub.add_parser("serve")
    serve.add_argument("--ui-root", type=Path, required=True)
    serve.add_argument("--config", type=Path, required=True)
    serve.add_argument("--port", type=int, default=8918)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            config_bytes = args.config.read_bytes()
            config = json.loads(config_bytes)
            if config.get("object_origin") != ORIGIN:
                raise HostedError("hosted config does not pin the Source Cooperative origin")
            server = ThreadingHTTPServer(("127.0.0.1", args.port), HostedUIHandler)
            server.config_bytes, server.ui_root = config_bytes, args.ui_root.resolve()
            print(f"Hosted viewer UI: http://127.0.0.1:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        root = args.root.resolve()
        plan_path = args.plan if args.plan.is_absolute() else root / args.plan
        plan_bytes = plan_path.read_bytes()
        plan = json.loads(plan_bytes)
        helper = load_prepare(root)
        packages = helper._parse_packages(args.package)
        displays = helper._parse_packages(args.display_package)
        packages = {key: path if path.is_absolute() else root / path for key, path in packages.items()}
        displays = {key: path if path.is_absolute() else root / path for key, path in displays.items()}
        base = helper.build_config(root, plan_path, packages, None, displays)
        records = helper._load_records(root)
        raw_ref = records["grwl-raw"]["publication"]["display"]
        manifest_path = root / raw_ref["manifest_path"]
        manifest_bytes = manifest_path.read_bytes()
        if sha256_bytes(manifest_bytes) != raw_ref["manifest_sha256"]:
            raise HostedError("raw GRWL canonical display manifest SHA-256 differs")
        config, cases = adapt_config(base, plan, records, json.loads(manifest_bytes))
        cases["plan_sha256"] = sha256_bytes(plan_bytes)
        config_bytes = canonical_json(config)
        cases["viewer_config_sha256"] = sha256_bytes(config_bytes)
        if args.out.exists() or args.out.is_symlink():
            raise HostedError("refusing to overwrite hosted viewer output")
        args.out.mkdir(parents=True)
        (args.out / "viewer-config.json").write_bytes(config_bytes)
        (args.out / "hosted-cases.json").write_bytes(canonical_json(cases))
        print(f"Wrote hosted config and {len(cases['cases'])} frozen cases to {args.out}")
        return 0
    except (HostedError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"hosted viewer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
