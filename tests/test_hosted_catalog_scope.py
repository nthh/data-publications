"""Current consumer metadata graph excludes unreachable historical snapshots."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/source_publish/validate_hosted.py"
SPEC = importlib.util.spec_from_file_location("validate_hosted_catalog_scope", MODULE)
assert SPEC and SPEC.loader
hosted = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hosted)

BASE = "https://data.source.coop/nthh/grwl-raw/"
RELEASE = BASE + "releases/r1/"
DISPLAY = BASE + "display/d1/"
CATALOG = RELEASE + "catalog.json"
COLLECTION = RELEASE + "collection.json"
STYLE = DISPLAY + "styles/width.json"
ARCHIVE = DISPLAY + "reports/baseline-r2/styles/width.json"
PMTILES = DISPLAY + "assets/grwl-raw.pmtiles"


def graph(*, catalog_extra=None, style_source="pmtiles://../assets/grwl-raw.pmtiles",
          include_current=True):
    rows = [
        {"url": CATALOG, "json": {"links": [{"rel": "child", "href": "collection.json"},
            *(catalog_extra or [])]}},
        {"url": COLLECTION, "json": {"links": [{"rel": "root", "href": "catalog.json"}]}},
        {"url": ARCHIVE, "json": {"sources": {"raw": {"url": "pmtiles://../assets/grwl-raw.pmtiles"}}}},
    ]
    if include_current:
        rows.append({"url": STYLE, "json": {"sources": {"raw": {"url": style_source}}}})
    return rows


def inspect(rows):
    return hosted._json_asset_links(rows, {CATALOG, COLLECTION, STYLE, ARCHIVE, PMTILES},
        "grwl-raw", catalog_url=CATALOG, collection_urls={COLLECTION},
        style_sources={STYLE: PMTILES}, embedded_styles=False)


def test_unreachable_historical_style_does_not_block_current_style():
    links = inspect(graph())
    assert any(link["source_url"] == STYLE and link["url"] == PMTILES for link in links)
    assert not any(link["source_url"] == ARCHIVE for link in links)


@pytest.mark.parametrize("style_source", [
    "pmtiles://../assets/missing.pmtiles", "https://elsewhere.example/tiles.pmtiles",
    "pmtiles://../../reports/old.pmtiles",
])
def test_current_style_cannot_use_missing_or_offplan_pmtiles(style_source):
    with pytest.raises(hosted.HostedValidationError, match="escapes product or is absent"):
        inspect(graph(style_source=style_source))


def test_catalog_link_to_historical_style_exercises_and_rejects_it():
    with pytest.raises(hosted.HostedValidationError, match="escapes product or is absent"):
        inspect(graph(catalog_extra=[{"rel": "style", "href": ARCHIVE}]))


def test_external_child_link_is_not_treated_as_a_citation():
    with pytest.raises(hosted.HostedValidationError, match="escapes product or is absent"):
        inspect(graph(catalog_extra=[{"rel": "child", "href": "https://elsewhere.example/collection.json"}]))


def test_external_analytic_asset_is_not_treated_as_a_citation():
    rows = graph()
    rows[1]["json"]["assets"] = {"data": {"href": "https://elsewhere.example/rows.parquet"}}
    with pytest.raises(hosted.HostedValidationError, match="escapes product or is absent"):
        inspect(rows)


def test_external_source_role_is_provenance_only():
    rows = graph()
    rows[1]["json"]["assets"] = {"original": {"href": "https://producer.example/archive.zip",
                                                "roles": ["source"]}}
    links = inspect(rows)
    assert not any(link["url"] == "https://producer.example/archive.zip" for link in links)


def test_source_role_does_not_exempt_missing_internal_asset():
    rows = graph()
    rows[1]["json"]["assets"] = {"source": {
        "href": BASE + "releases/r1/missing-source.zip", "roles": ["source"]}}
    with pytest.raises(hosted.HostedValidationError, match="escapes product or is absent"):
        inspect(rows)


@pytest.mark.parametrize("roles", [None, ["data"], ["source", "data"]])
def test_external_asset_without_sole_source_role_is_rejected(roles):
    rows = graph()
    rows[1]["json"]["assets"] = {"original": {"href": "https://producer.example/archive.zip"}}
    if roles is not None:
        rows[1]["json"]["assets"]["original"]["roles"] = roles
    with pytest.raises(hosted.HostedValidationError, match="escapes product or is absent"):
        inspect(rows)


def test_historical_copy_cannot_satisfy_missing_current_style():
    with pytest.raises(hosted.HostedValidationError, match="active catalog, collection, or style"):
        inspect(graph(include_current=False))


def test_missing_current_collection_link_cannot_be_satisfied_by_style():
    rows = graph()
    rows[0]["json"]["links"] = []
    with pytest.raises(hosted.HostedValidationError, match="not linked from current catalog"):
        inspect(rows)


def test_relative_child_style_links_and_cycles_terminate():
    release = BASE + "releases/r1/"
    catalog = release + "catalog.json"
    collection = release + "river/collection.json"
    style = release + "river/styles/annual.json"
    pmtiles = release + "river/river.pmtiles"
    rows = [
        {"url": catalog, "json": {"links": [{"rel": "child", "href": "river/collection.json"}]}},
        {"url": collection, "json": {"links": [{"rel": "root", "href": "../catalog.json"}],
                                    "assets": {"annual-style": {"href": "styles/annual.json"}}}},
        {"url": style, "json": {"sources": {"river": {"url": "pmtiles://../river.pmtiles"}}}},
    ]
    links = hosted._json_asset_links(rows, {catalog, collection, style, pmtiles}, "grwl-raw",
        catalog_url=catalog, collection_urls={collection}, style_sources={style: pmtiles},
        embedded_styles=True)
    assert len(links) >= 4
    assert any(link["source_url"] == style and link["url"] == pmtiles for link in links)


def test_actual_five_manifests_select_only_current_style_roots():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "research/source-publication-20261106/staging-r2/immutable-upload-plan.json").read_text())
    choices = [
        ("river-plastic-inputs", "figshare-v6-r2", None, "river-plastic-inputs/styles/annual-input.json"),
        ("hydrolakes", "v1-local-r3", "display-v1", "styles/hydrolakes-polygons.json"),
        ("lakeatlas", "lakeatlas-v1.0-r2", "display-v1", "styles/lakeatlas-polygons.json"),
        ("free-flowing-rivers", "figshare-v1-local-r2", "display-v1", "styles/ffr-reaches.json"),
        ("grwl-raw", "raw-v01.01-local-r1", "raw-v01.01-display-r3", "styles/width.json"),
    ]
    for dataset, release, display, expected_style in choices:
        product = next(item for item in plan["products"] if item["dataset_id"] == dataset)
        manifest = (root / "datasets" / dataset / "display" / display / "manifest.json" if display
                    else root / "datasets" / dataset / "releases" / release / "manifest.json")
        sources = [(entry, manifest if entry["source"]["path"] == "manifest.json" and
                    entry["source"]["kind"] == ("display_package" if display else "package") else root)
                   for entry in plan["files"] if entry["object_key"].startswith(dataset + "/")]
        catalog, collections, styles, embedded = hosted._active_catalog_roots(
            sources, dataset_id=dataset, display_publication=product.get("display_publication"))
        assert catalog.endswith("/catalog.json")
        assert len(collections) == 1
        assert any(url.endswith("/" + expected_style) for url in styles)
        assert embedded == (display is None)
        assert all("/reports/baseline-" not in url for url in styles)
