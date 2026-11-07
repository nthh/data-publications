#!/usr/bin/env python3
"""Prepare an immutable, local GRWL r3 display after bound width gates pass.

Inputs are an immutable JSON mapping. This finalizer never edits canonical
publication metadata or uploads data. The r2 package remains a sealed baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / "research/grwl-width-overview-20261106/criteria.json"
BASELINE_MANIFEST_SHA = "bce857fafd55c848f3d3738fc4f86e72825cb0c048a4d3e84df1cf4ea4d94988"
BASELINE_ARCHIVE_SHA = "79389270fef94a8a6359f0b7a98b3505a82ee090a7827bd13280bf1f1c178830"
BASELINE_ARCHIVE_SIZE = 3_005_034_172
ANALYTIC_MANIFEST_SHA = "ef2a063cb54327b50d47e8ad17c735cadde87fb9ba3136d6b39fe43126863c8c"
SOURCE_SHA = "d37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb"
SOURCE_MANIFEST_SHA = "160dfaf91ede202da57172ff16492601ca349d43e0b629819a7e4eb82222acda"
SOURCE_SIZE = 5_529_859_809
SOURCE_ROWS = 64_572_998
SOURCE_TILES = 829
PILOT_SHA = "1c7177cc55b732dc7e609ed22ae50c46d677548da98c4b39e4f1ab76996ca509"
PILOT_ROWS = 919_832
DETAIL_TILES = 588_355
ARCHIVE_REL = "assets/grwl-raw.pmtiles"
RELEASE = "raw-v01.01-display-r3"
REPORTS = ("overview_build", "overview_report", "combine_report", "browser_report", "viewer_build", "clean_replay_report")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load("grwl_r1_finalizer", ROOT / "datasets/grwl-raw/finalize_display.py")
replay_script = load("grwl_width_replay", ROOT / "research/grwl-width-overview-20261106/run_width_replay.py")
WORKFLOW = tuple(replay_script.CODE_PATHS)
CORE_CODE = {
    "datasets/grwl-raw/build_width_overview.py", "datasets/grwl-raw/validate_width_overview.py",
    "datasets/grwl-raw/combine_width_display.py", "datasets/grwl-raw/prepare_width_preview.py",
    "datasets/grwl-raw/finalize_width_display.py", "scripts/cloud_viewer/src/core.js",
    "scripts/cloud_viewer/src/app.js", "scripts/cloud_viewer/build.mjs",
    "scripts/cloud_viewer/width-overview-browser-check.mjs",
    "scripts/cloud_viewer/export-raw-width-style.mjs", "scripts/cloud_viewer/package-lock.json",
    "scripts/display_tools/uv.lock", "research/grwl-width-overview-20261106/criteria.json",
}


class FinalizeError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise FinalizeError(message)


def regular(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f"Missing or unsafe regular file: {path}")
    return path


def digest(path):
    return old._sha256(regular(path))


def identity(path):
    path = regular(path)
    return {"sha256": digest(path), "size_bytes": path.stat().st_size}


def bound(actual, expected, label):
    require(isinstance(actual, dict) and actual.get("sha256") == expected["sha256"]
            and actual.get("size_bytes") == expected["size_bytes"], f"Unbound {label}")


def read(path, label):
    return old._json(regular(path), label)


def resources(output, criteria, *, start=False):
    free = shutil.disk_usage(output).free
    floor = criteria["resources"]["minimum_start_free_gib" if start else "minimum_running_free_gib"] * (1 << 30)
    require(free >= floor, f"Free space {free} below frozen floor {floor}")
    if not start:
        used = sum(p.stat().st_size for p in output.rglob("*") if p.is_file() and not p.is_symlink())
        maximum = criteria["resources"]["maximum_new_artifacts_gib"] * (1 << 30)
        require(used <= maximum, f"Final package {used} exceeds task artifact ceiling {maximum}")
    return {"free_bytes": free}


def validate_baseline(directory):
    directory = Path(directory)
    manifest_path = regular(directory / "manifest.json")
    require(digest(manifest_path) == BASELINE_MANIFEST_SHA, "Sealed r2 manifest SHA differs")
    manifest = read(manifest_path, "r2 baseline manifest")
    require((manifest.get("status"), manifest.get("dataset_id"), manifest.get("display_release"),
             manifest.get("source_rows"), manifest.get("source_tiles"))
            == ("prepared", "grwl-raw", "raw-v01.01-display-r2", SOURCE_ROWS, SOURCE_TILES),
            "r2 baseline release identity differs")
    files = manifest.get("files")
    require(isinstance(files, dict) and ARCHIVE_REL in files, "r2 file inventory missing archive")
    bound(files[ARCHIVE_REL], {"sha256": BASELINE_ARCHIVE_SHA, "size_bytes": BASELINE_ARCHIVE_SIZE}, "r2 archive pin")
    found = set()
    for current, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs:
            require(not (Path(current) / name).is_symlink(), "r2 baseline has symlink directory")
        for name in names:
            path = Path(current) / name
            regular(path)
            relative = path.relative_to(directory).as_posix()
            old._safe_relative(relative, "r2 inventory")
            if relative != "manifest.json":
                found.add(relative)
    require(found == set(files), "r2 baseline file inventory differs")
    for relative, pin in files.items():
        bound(identity(directory / relative), pin, f"r2 file {relative}")
    return manifest


def validate_analytic(package, baseline):
    package = Path(package)
    require(digest(package / "manifest.json") == ANALYTIC_MANIFEST_SHA, "Analytic manifest differs from sealed pin")
    base = Path(baseline) / "reports/baseline-r1/reports/finalization"
    source_manifest_path = base / "source-manifest.json"
    fidelity_path = base / "source-fidelity.normalized.json"
    source_manifest = read(source_manifest_path, "sealed source manifest")
    require(digest(source_manifest_path) == SOURCE_MANIFEST_SHA, "Sealed source manifest SHA differs")
    fidelity = read(fidelity_path, "sealed source fidelity")
    old._validate_fidelity(fidelity, source_manifest_path, source_manifest,
                           SOURCE_SHA, SOURCE_SIZE, SOURCE_TILES, SOURCE_ROWS)
    analytic = old._validate_analytic_package(package, SOURCE_SHA, SOURCE_SIZE,
                                               SOURCE_ROWS, digest(fidelity_path))
    require(analytic["manifest_sha256"] == ANALYTIC_MANIFEST_SHA, "Analytic package manifest changed")
    return analytic


def validate_overview(build, report, build_path, report_path, criteria, archive):
    criteria_sha = digest(CRITERIA)
    require(build.get("status") == "built_unvalidated" and build.get("source_sha256") == SOURCE_SHA
            and build.get("criteria_sha256") == criteria_sha and build.get("rows") == SOURCE_ROWS,
            "Global overview producer build does not bind source/criteria")
    require(report.get("status") == "passed" and report.get("scope") == "global"
            and report.get("source_sha256") == SOURCE_SHA and report.get("source_records") == SOURCE_ROWS
            and report.get("criteria_sha256") == criteria_sha
            and report.get("verifier_sha256") == digest(ROOT / "datasets/grwl-raw/validate_width_overview.py"),
            "Global overview oracle report is absent or unbound")
    require(report.get("source_manifest_sha256") == build.get("source_manifest_sha256") == SOURCE_MANIFEST_SHA,
            "Overview source manifest differs between build and oracle")
    samples = report.get("samples_sha256")
    selected, tiles = report.get("selected_by_zoom"), report.get("tiles_by_zoom")
    require(isinstance(samples, dict) and isinstance(selected, dict) and isinstance(tiles, dict)
            and all(isinstance(selected.get(str(z)), int) and selected[str(z)] > 0
                    and isinstance(tiles.get(str(z)), int) and tiles[str(z)] > 0 for z in range(8)),
            "Overview oracle does not cover all eight zooms")
    require(0 < report.get("maximum_compressed_tile_bytes", 0)
            <= criteria["gates"]["maximum_compressed_overview_tile_bytes"], "Overview tile byte gate failed")
    require(report.get("point_occurrences") == report.get("expected_point_occurrences")
            and isinstance(report.get("point_occurrences"), int) and report["point_occurrences"] > 0,
            "Overview point occurrence gate failed")
    artifacts = build.get("artifacts", {})
    require(isinstance(artifacts, dict), "Overview build artifact list missing")
    for relative in ["overview.pmtiles", *(f"samples/z{z}.parquet" for z in range(8)),
                     "workflow/build_width_overview.py"]:
        pin = artifacts.get(relative)
        require(isinstance(pin, dict), f"Overview build lacks artifact {relative}")
        path = build_path.parent / relative
        bound(identity(path), pin, f"overview build artifact {relative}")
    require(artifacts["overview.pmtiles"]["sha256"] == report.get("archive_sha256")
            and artifacts["overview.pmtiles"]["size_bytes"] == report.get("archive_size_bytes")
            and all(artifacts[f"samples/z{z}.parquet"]["sha256"] == samples.get(str(z)) for z in range(8))
            and artifacts["workflow/build_width_overview.py"]["sha256"] == digest(ROOT / "datasets/grwl-raw/build_width_overview.py"),
            "Overview build artifacts differ from current code or oracle")
    require([row.get("selected_observations") for row in build.get("per_zoom", [])]
            == [selected[str(z)] for z in range(8)]
            and [row.get("tiles") for row in build["per_zoom"]] == [tiles[str(z)] for z in range(8)],
            "Overview build counts differ from oracle")
    require(report.get("archive_sha256") != archive["sha256"], "Overview input must be separate from combined archive")
    return {"overview_archive": artifacts["overview.pmtiles"], "source_manifest_sha256": report["source_manifest_sha256"]}


def validate_combine(combine, combine_path, report_path, overview, archive, criteria):
    require(combine.get("status") == "built_unvalidated" and combine.get("combine_status") == "passed"
            and combine.get("scope") == "global", "Global combine gate did not pass")
    baseline = combine.get("baseline", {})
    require(baseline.get("sha256") == BASELINE_ARCHIVE_SHA
            and baseline.get("sha256_pin") == BASELINE_ARCHIVE_SHA
            and baseline.get("size_bytes") == BASELINE_ARCHIVE_SIZE
            and baseline.get("detail_tiles") == DETAIL_TILES and baseline.get("archive_tiles") == 592_774
            and baseline.get("discarded_old_overview_tiles") == 4_419,
            "Combine baseline is not sealed r2")
    bound(combine.get("combined"), archive, "combined output")
    overview_info = combine.get("overview", {})
    bound(overview_info, overview["overview_archive"], "combined overview input")
    require(overview_info.get("receipt_sha256") == digest(report_path)
            and overview_info.get("receipt_status") == "passed"
            and overview_info.get("scope") == "global"
            and overview_info.get("verifier_sha256") == digest(ROOT / "datasets/grwl-raw/validate_width_overview.py")
            and overview_info.get("source_sha256") == SOURCE_SHA
            and overview_info.get("source_manifest_sha256") == overview["source_manifest_sha256"],
            "Combine does not bind passed global overview oracle")
    verification = combine.get("verification", {})
    require(verification.get("status") == "passed" and verification.get("detail") == DETAIL_TILES
            and verification.get("overview") == sum(combine.get("overview", {}).get("tile_counts_by_zoom", {}).values())
            and combine.get("combined", {}).get("tiles") == verification.get("overview") + DETAIL_TILES
            and all(verification.get(key) is True for key in (
                "detail_raw_payloads_byte_identical", "overview_raw_payloads_byte_identical",
                "no_extra_or_overlapping_coordinates")), "Combine payload gates failed")
    require(combine.get("criteria", {}).get("sha256") == digest(CRITERIA)
            and combine.get("code", {}).get("sha256") == digest(ROOT / "datasets/grwl-raw/combine_width_display.py"),
            "Combine code/criteria pins differ")
    require(archive["size_bytes"] <= criteria["gates"]["maximum_combined_archive_bytes"],
            "Combined archive exceeds frozen byte ceiling")


def validate_browser(browser, viewer_pin, viewer, archive, criteria):
    require(browser.get("schema_version") == 1 and browser.get("status") == "passed"
            and browser.get("viewer_build_sha256") == viewer_pin["sha256"]
            and browser.get("app_js_sha256") == viewer["files"]["app.js"]["sha256"]
            and browser.get("archive_sha256") == archive["sha256"]
            and browser.get("source_sha256") == SOURCE_SHA,
            "Browser report is failed or unbound")
    ceiling = criteria["gates"]["browser_cold_object_byte_ceiling"]
    require(browser.get("transfer_ceiling_bytes") == ceiling, "Browser transfer policy changed")
    expected = [(view["name"], zoom, view["center"]) for view in criteria["gates"]["browser_fixed_views"]
                for zoom in view["zooms"]]
    cases = browser.get("cases")
    require(isinstance(cases, list) and len(cases) == len(expected) == 20, "Browser fixed case count differs")
    for case, (name, zoom, center) in zip(cases, expected, strict=True):
        require(case.get("status") == "passed" and case.get("view") == name
                and case.get("requested_zoom") == zoom and case.get("requested_center") == center
                and abs(case.get("actual_zoom", math.inf) - zoom) <= 1e-6,
                f"Browser camera/zoom failed for {name} z{zoom}")
        actual = case.get("actual_center")
        require(isinstance(actual, list) and len(actual) == 2
                and abs(((actual[0] - center[0] + 540) % 360) - 180) <= 1e-6
                and abs(actual[1] - center[1]) <= 1e-6,
                f"Browser camera center failed for {name} z{zoom}")
        require(case.get("archive_sha256") == archive["sha256"] and case.get("legend_visible") is True
                and case.get("source_layer") == "grwl_width_overview"
                and "release-coverage" not in case.get("style_layers", [])
                and case.get("expected_layer") == ("release-lines" if zoom >= 8 else "release-width-samples")
                and ("grwl_raw" if zoom >= 8 else "grwl_width_overview") in case.get("rendered_source_layers", []),
                f"Browser width layer/legend failed for {name} z{zoom}")
        require(isinstance(case.get("transferred_bytes"), int) and 0 < case["transferred_bytes"] <= ceiling
                and case.get("page_errors") == [] and case.get("external_requests") == []
                and isinstance(case.get("requests"), list) and case["requests"],
                f"Browser transfer or local-request gate failed for {name} z{zoom}")
        transferred = 0
        for request in case["requests"]:
            if request.get("method") != "GET":
                continue
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", request.get("range") or "")
            require(match is not None and request.get("status") == 206
                    and request.get("cors") == "*" and request.get("completed") is True,
                    f"Browser range response failed for {name} z{zoom}")
            first, last = map(int, match.groups())
            size = request.get("object_size_bytes")
            length = last - first + 1
            require(type(size) is int and 0 <= first <= last < size
                    and request.get("content_range") == f"bytes {first}-{last}/{size}"
                    and request.get("body_bytes") == length
                    and request.get("content_length") == length,
                    f"Browser byte-range accounting failed for {name} z{zoom}")
            transferred += length
        require(transferred == case["transferred_bytes"], f"Browser body count differs for {name} z{zoom}")
        if zoom < 8:
            sample = case.get("sample")
            require(isinstance(sample, dict) and isinstance(sample.get("featureID"), int)
                    and sample.get("sourceLayer") == "grwl_width_overview"
                    and sample.get("properties", {}).get("width_valid") in (True, False)
                    and abs(sample.get("diameter_px", math.inf) - sample.get("expected_diameter_px", -math.inf)) <= 1e-9,
                    f"Browser measured width sample failed for {name} z{zoom}")
        if name == "mississippi" and zoom == 7:
            lookup = case.get("exact_id_lookup", {})
            overview_width = lookup.get("overview_width")
            source_width = lookup.get("displayed_width")
            width_matches = (source_width in (None, "null") if overview_width is None
                             else str(source_width) == str(overview_width))
            require(lookup.get("featureID") == case["sample"]["featureID"]
                    and type(lookup.get("source_feature_id")) is int
                    and 0 < lookup["source_feature_id"] <= (1 << 53) - 1
                    and lookup["source_feature_id"] == case["sample"]["featureID"]
                    and type(lookup.get("source_width_valid")) is bool
                    and type(lookup.get("overview_width_valid")) is bool
                    and lookup["source_width_valid"] == lookup["overview_width_valid"]
                    == case["sample"]["properties"]["width_valid"]
                    and lookup.get("attribute_count") == 14
                    and str(lookup.get("note", "")).startswith("All source attributes")
                    and width_matches
                    and abs(case.get("click_zoom", math.inf) - 7) <= 1e-9,
                    "Overview exact-ID full-attribute lookup failed")


def validate_viewer(viewer, viewer_path, browser):
    require(viewer.get("schema_version") == 1 and viewer.get("package_lock_sha256") == digest(ROOT / "scripts/cloud_viewer/package-lock.json"),
            "Viewer build/lock differs")
    files = viewer.get("files")
    require(isinstance(files, dict) and "app.js" in files and files, "Viewer build file inventory missing")
    for relative, pin in files.items():
        old._safe_relative(relative, "viewer build file")
        bound(identity(viewer_path.parent / relative), pin, f"viewer file {relative}")
    require(browser.get("app_js_sha256") == files["app.js"]["sha256"], "Browser app differs from viewer build")


def validate_replay(replay, viewer_pin):
    require(replay.get("schema_version") == 1 and replay.get("status") == "passed", "Clean replay failed")
    checkout = replay.get("clean_checkout", {})
    commit = checkout.get("commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)
            and checkout.get("before") == "" and checkout.get("after") == ""
            and checkout.get("after_commit") == commit, "Clean replay checkout was dirty")
    require(replay.get("source_sha256") == PILOT_SHA and replay.get("source_rows") == PILOT_ROWS,
            "Clean replay source differs from frozen pilot")
    require(replay.get("byte_equal") == {"samples": True, "overview_archive": True,
            "combined_archive": True, "viewer_build": True, "viewer_files": True}
            and replay.get("reference_viewer_build_sha256") == viewer_pin["sha256"],
            "Clean replay byte equality or viewer binding failed")
    code_pins = replay.get("code_pins")
    require(CORE_CODE <= set(WORKFLOW), "Finalizer replay contract omits core code")
    require(isinstance(code_pins, dict) and set(code_pins) == set(WORKFLOW), "Clean replay code pin set differs")
    for relative in WORKFLOW:
        bound(code_pins[relative], identity(ROOT / relative), f"clean replay code {relative}")
    stages = replay.get("stages")
    require(isinstance(stages, list) and [stage.get("name") for stage in stages]
            == ["width-overview", "combine", "viewer"], "Clean replay stages differ")
    for stage in stages:
        log = stage.get("log", {})
        require(stage.get("exit_code") == 0 and isinstance(log.get("path"), str),
                "Clean replay stage failed or lacks log")
        bound(identity(Path(log["path"])), log, f"clean replay {stage['name']} log")


def make_asset(archive):
    return {"id": "grwl-raw-display", "title": "GRWL raw width observations at every zoom",
            "path": ARCHIVE_REL, **archive, "source_layer": "grwl_raw", "geometry_type": "line",
            "id_field": "feature_id", "id_encoding": "mvt_feature_id",
            "attribute_fields": ["width_m", "width_valid"], "min_zoom": 0, "max_zoom": 12,
            "detail_min_zoom": 8, "style_path": "styles/width.json",
            "source_asset": {"path": "assets/grwl-raw-observations.parquet", "sha256": SOURCE_SHA,
                             "size_bytes": SOURCE_SIZE},
            "overview": {"source_layer": "grwl_width_overview", "mode": "width_samples",
                         "geometry_type": "point", "min_zoom": 0, "max_zoom": 7,
                         "extent": 4096, "cells_per_tile": 1024, "has_feature_ids": True,
                         "id_encoding": "mvt_feature_id", "attribute_fields": ["width_m", "width_valid"],
                         "meaning": "Selected observations; widest measured width per screen-scale cell."}}


def export_style():
    command = ["node", str(ROOT / "scripts/cloud_viewer/export-raw-width-style.mjs")]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    style = json.loads(completed.stdout)
    layers = style.get("layers")
    require(isinstance(layers, list) and len(layers) == 2
            and layers[0].get("type") == "circle"
            and layers[0].get("source-layer") == "grwl_width_overview"
            and layers[0].get("maxzoom") == 8
            and layers[0].get("paint", {}).get("circle-stroke-width") in (0, None)
            and layers[1].get("type") == "line"
            and layers[1].get("source-layer") == "grwl_raw"
            and layers[1].get("minzoom") == 8,
            "Exported style does not contain the expected width point/detail layers")
    require(style.get("sources", {}).get("data", {}).get("url") == "../assets/grwl-raw.pmtiles",
            "Exported style does not reference the packaged archive")
    return completed.stdout


def finalize(inputs_path, output):
    inputs_path, output = Path(inputs_path), Path(output)
    require(not os.path.lexists(output), "Refusing existing immutable output")
    inputs = read(inputs_path, "r3 finalizer inputs")
    required = ("baseline", "analytic_package", "archive", *REPORTS)
    require(all(isinstance(inputs.get(key), str) for key in required), "Finalizer input mapping is incomplete")
    paths = {key: Path(inputs[key]) for key in required}
    for name, path in paths.items():
        resolved = path.resolve(strict=True)
        require(not output.resolve().is_relative_to(resolved)
                and not resolved.is_relative_to(output.resolve()),
                f"Output overlaps protected input {name}")
    criteria = read(CRITERIA, "frozen width criteria")
    require(criteria.get("status") == "frozen_before_build"
            and criteria.get("source", {}).get("sha256") == SOURCE_SHA
            and criteria.get("source", {}).get("rows") == SOURCE_ROWS,
            "Width criteria source/status differs")
    output.parent.mkdir(parents=True, exist_ok=True)
    resources(output.parent, criteria, start=True)
    output.mkdir(parents=True)
    old._write_json(output / "partial.json", {"status": "partial", "usable_release": False})
    try:
        baseline = validate_baseline(paths["baseline"])
        analytic = validate_analytic(paths["analytic_package"], paths["baseline"])
        archive = identity(paths["archive"])
        require(archive["size_bytes"] <= criteria["gates"]["maximum_combined_archive_bytes"],
                "Combined archive exceeds frozen ceiling")
        reports = {name: read(paths[name], name) for name in REPORTS}
        pins = {name: identity(paths[name]) for name in REPORTS}
        overview = validate_overview(reports["overview_build"], reports["overview_report"],
                                     paths["overview_build"], paths["overview_report"], criteria, archive)
        validate_combine(reports["combine_report"], paths["combine_report"],
                         paths["overview_report"], overview, archive, criteria)
        validate_viewer(reports["viewer_build"], paths["viewer_build"], reports["browser_report"])
        validate_browser(reports["browser_report"], pins["viewer_build"], reports["viewer_build"], archive, criteria)
        validate_replay(reports["clean_replay_report"], pins["viewer_build"])
        for name in REPORTS:
            bound(identity(paths[name]), pins[name], f"unchanged input {name}")
        asset = make_asset(archive)
        pmtiles = old._verify_pmtiles(asset, paths["archive"])
        copy_mode = old._copy_file(paths["archive"], output / ARCHIVE_REL, clone=True)
        bound(identity(output / ARCHIVE_REL), archive, "cloned r3 archive")
        resources(output, criteria)
        # Copy the entire sealed r2 nonbulk inventory, including its manifest.
        for relative in ["manifest.json", *baseline["files"]]:
            if relative == ARCHIVE_REL:
                continue
            old._safe_relative(relative, "baseline r2 file")
            source = paths["baseline"] / relative
            target = output / "reports/baseline-r2" / relative
            old._copy_file(source, target)
            bound(identity(target), identity(source), f"copied baseline r2 {relative}")
        for name in REPORTS:
            target = output / "reports/width-overview" / (name.replace("_", "-") + ".json")
            old._copy_file(paths[name], target)
            bound(identity(target), pins[name], f"copied {name}")
        for stage in reports["clean_replay_report"]["stages"]:
            log = stage["log"]
            target = output / "reports/width-overview/clean-replay-logs" / (stage["name"] + ".log")
            old._copy_file(Path(log["path"]), target)
            bound(identity(target), log, f"copied clean replay {stage['name']} log")
        old._copy_file(inputs_path, output / "reports/width-overview/inputs.json")
        old._write_json(output / "reports/width-overview/pmtiles-verify.json", pmtiles)
        for relative in WORKFLOW:
            old._copy_file(regular(ROOT / relative), output / "workflow" / relative)
        for relative, pin in reports["overview_build"]["artifacts"].items():
            if relative.startswith("workflow/"):
                old._safe_relative(relative, "overview workflow snapshot")
                source = paths["overview_build"].parent / relative
                bound(identity(source), pin, f"overview workflow {relative}")
                old._copy_file(source, output / "reports/width-overview/overview-build" / relative)
        for relative, pin in reports["viewer_build"]["files"].items():
            old._copy_file(paths["viewer_build"].parent / relative,
                           output / "reports/width-overview/viewer-runtime" / relative)
        evidence = inputs.get("evidence_files", {})
        require(isinstance(evidence, dict), "Evidence file map must be an object")
        for relative, filename in evidence.items():
            old._safe_relative(relative, "r3 evidence path")
            old._copy_file(regular(Path(filename)), output / "reports/width-overview/evidence" / relative)
        style = export_style()
        style_path = output / "styles/width.json"
        style_path.parent.mkdir(parents=True, exist_ok=True)
        style_path.write_text(style)
        finalization = {"schema_version": 1, "status": "passed", "dataset_id": "grwl-raw",
                        "display_release": RELEASE, "archive": archive, "pmtiles_copy_mode": copy_mode,
                        "source_asset": asset["source_asset"], "analytic_manifest_sha256": ANALYTIC_MANIFEST_SHA,
                        "analytic_receipt_sha256": analytic["receipt_sha256"],
                        "source_fidelity_sha256": digest(paths["baseline"] / "reports/baseline-r1/reports/finalization/source-fidelity.normalized.json"),
                        "historical_baseline": {"manifest_sha256": BASELINE_MANIFEST_SHA,
                                                "archive_sha256": BASELINE_ARCHIVE_SHA,
                                                "archive_size_bytes": BASELINE_ARCHIVE_SIZE,
                                                "external_binary_path": str((paths["baseline"] / ARCHIVE_REL).resolve()),
                                                "external_binary_not_packaged": True,
                                                "nonbulk_chain": "reports/baseline-r2"},
                        "criteria": identity(CRITERIA), "input_reports": pins,
                        "style_exporter_sha256": digest(ROOT / "scripts/cloud_viewer/export-raw-width-style.mjs"),
                        "resources": resources(output, criteria), "publicly_published": False, "hosted": False}
        old._write_json(output / "reports/width-overview/finalization.json", finalization)
        (output / "README.md").write_text(
            "GRWL source width observations at all zooms\n\n"
            "Local immutable display r3. Zooms 0–7 show selected original observations, "
            "the widest valid measured width per screen-scale cell, at source anchors. "
            "Zooms 8–12 retain the sealed detailed tile payloads. Symbols are exaggerated, "
            "not riverbanks. The unchanged GeoParquet retains all 64,572,998 observations "
            "and exact analytical attributes. No upload or public hosting is claimed.\n\n"
            "The sealed r2 nonbulk files and manifest are retained under reports/baseline-r2; "
            "its historical PMTiles binary is an external reference.\n")
        manifest = {"schema_version": 1, "dataset_id": "grwl-raw", "display_release": RELEASE,
                    "analytic_release": "raw-v01.01-local-r1", "source_rows": SOURCE_ROWS,
                    "source_tiles": SOURCE_TILES, "attribution": baseline["attribution"],
                    "source_license": baseline["source_license"], "assets": [asset], "status": "prepared"}
        (output / "partial.json").unlink()
        manifest["files"] = old._inventory(output)
        old._atomic_json(output / "manifest.json", manifest)
        return {"status": "prepared", "output": str(output.resolve()),
                "manifest_sha256": digest(output / "manifest.json"), "archive": archive}
    except BaseException as exc:
        old._write_json(output / "failure.json", {"status": "failed_partial", "usable_release": False,
                                                 "error": f"{type(exc).__name__}: {exc}"})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.inputs, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
