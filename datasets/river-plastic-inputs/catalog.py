"""Create portable local STAC/Portolan metadata and a data-derived thumbnail."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
import numpy as np
import shapely

HERE = Path(__file__).resolve().parent
from dataset_config import load_config, config_sha256
CONFIG = load_config()
PALETTE = ["#4da6c8", "#76c7c0", "#f5cf72", "#e97d41", "#bd3838", "#751e39"]
CITATION = "Lebreton, L. C. M., van der Zwet, J., Damsteeg, J.-W., Slat, B., Andrady, A. & Reisser, J. (2017). River plastic emissions to the world's oceans. Nature Communications 8, 15611. https://doi.org/10.1038/ncomms15611"


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def asset(path, root, media, roles, title):
    return {"href": path.relative_to(root).as_posix(), "type": media, "roles": roles, "title": title,
            "file:size": path.stat().st_size, "file:checksum": "1220" + hashlib.sha256(path.read_bytes()).hexdigest()}


def build_catalog(root, table, schema, bbox, revision):
    folder = root / CONFIG["id"]
    styles = folder / "styles"
    styles.mkdir(exist_ok=True)
    metric = ["log10", ["+", 1, ["coalesce", ["get", "i_mid"], 0]]]
    colors = ["interpolate", ["linear"], metric]
    for value, color in enumerate(PALETTE):
        colors.extend([value, color])
    style = {"version": 8, "name": "Annual river plastic input — midpoint estimate",
             "sources": {"data": {"type": "vector", "url": "../river-plastic-inputs.pmtiles",
                                  "attribution": "Lebreton et al. (2017), CC BY 4.0; conversion by Folia"}},
             "layers": [{"id": "background", "type": "background", "paint": {"background-color": "#f1f5f7"}},
                        {"id": "river-inputs", "type": "circle", "source": "data", "source-layer": "river_inputs",
                         "paint": {"circle-color": ["case", ["==", ["get", "i_mid"], None], "#7d8994", colors], "circle-radius": ["case", ["==", ["get", "i_mid"], None], 3, ["interpolate", ["linear"], metric, 0, 1.2, 5, 6.2]],
                                   "circle-opacity": 0.8}}]}
    write_json(styles / "annual-input.json", style)
    geom = shapely.from_wkb(table["geometry"].to_pylist())
    x, lat = shapely.get_x(geom), shapely.get_y(geom)
    y = np.degrees(np.arcsinh(np.tan(np.radians(lat))))
    emissions = np.array([float(v) if v is not None else np.nan for v in table["i_mid"].to_pylist()])
    metric_values = np.log10(1 + emissions)
    order = np.flatnonzero(np.isfinite(emissions))[np.argsort(emissions[np.isfinite(emissions)])]
    fig, ax = plt.subplots(figsize=(14, 7.3), dpi=150)
    fig.patch.set_facecolor("#f1f5f7"); ax.set_facecolor("#f1f5f7")
    radius = 1.2 + np.clip(metric_values, 0, 5)
    plot = ax.scatter(x[order], y[order], c=metric_values[order], s=np.pi * radius[order]**2,
                      cmap=LinearSegmentedColormap.from_list("annual-input", PALETTE), norm=Normalize(0, 5),
                      alpha=0.8, linewidths=0)
    ax.scatter(x[~np.isfinite(emissions)], y[~np.isfinite(emissions)], s=28, color="#7d8994", linewidths=0, label="Estimate missing (4 points)")
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 100); ax.set_aspect("equal")
    ax.set_xticks([-120, -60, 0, 60, 120]); ax.set_xlabel("Longitude")
    ticks = np.array([-60, -30, 0, 30, 60])
    ax.set_yticks(np.degrees(np.arcsinh(np.tan(np.radians(ticks)))), [f"{v}°" for v in ticks])
    ax.set_ylabel("Latitude (Mercator)")
    ax.grid(alpha=0.15); ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Global river plastic inputs", loc="left", fontsize=21, fontweight="bold", pad=14)
    bar = fig.colorbar(plot, ax=ax, orientation="horizontal", shrink=0.48, pad=0.12, aspect=40)
    bar.set_ticks([0, 1, 2, 3, 4, 5], labels=["0", "9", "99", "999", "9,999", "≥99,999"])
    bar.set_label("Modeled annual input — midpoint estimate (tonnes/year)")
    fig.text(0.13, 0.025, "2010 model baseline · 40,760 river input locations · Lebreton et al. (2017) · CC BY 4.0", fontsize=9, color="#425466")
    fig.savefig(folder / "thumbnail.png", dpi=150, bbox_inches="tight", metadata={"Software": "Folia river-plastic-inputs build"})
    plt.close(fig)

    intro = """A global model of plastic inputs from rivers into the ocean, published by Lebreton et al. in 2017. This static release preserves the 40,760 river input locations and all 53 numeric attributes in the original Figshare v6 shapefile. Estimates represent the 2010 model baseline; they are not current measurements. This is distinct from the later Meijer et al. 2021 model."""
    provenance = f"""Original data: https://doi.org/{CONFIG['source_doi']} (CC BY 4.0). Original archive: {CONFIG['source_url']}.

{CITATION}

Folia converted the source to spatially ordered GeoParquet and a PMTiles display derivative. Conversion source commit: `{revision}`. `manifest.json` at the catalog root records checksums, tool versions and the exact build inputs. `dataset.yaml` at the catalog root preserves the canonical record exactly as it existed at build time; publication status can evolve later in Git without rewriting this snapshot. This bundle is prepared locally; publication and registry submission remain pending.
"""
    root_readme = f"""# {CONFIG['title']}

{intro}

Start with [the collection](river-plastic-inputs/README.md), or open [catalog.json](catalog.json) with a STAC client. The collection provides the analytic GeoParquet, a PMTiles map layer, a MapLibre style, a thumbnail, and a complete field dictionary. All catalog paths are relative so the bundle can be served without rewriting data links.

## License and provenance

{provenance}
"""
    (root / "README.md").write_text(root_readme)
    rows = ["| Field | Arrow type | Meaning |", "| --- | --- | --- |"]
    for field in schema:
        rows.append(f"| `{field['name']}` | `{field['type']}` | {field['description']} |")
    collection_readme = f"""# {CONFIG['title']}

{intro}

Use [river-plastic-inputs.parquet](river-plastic-inputs.parquet) for analysis. Numeric source values are fixed-point Decimal values at their original precision. `source_row` is the one-based source shapefile/DBF row number, not a watershed identifier; it is stable only for this pinned archive. Rows are Hilbert-sorted for spatial access. Geometry is WGS84 longitude/latitude (OGC:CRS84); bbox covering columns and row-group statistics support spatial filtering.

The [PMTiles file](river-plastic-inputs.pmtiles) contains the annual low/mid/high estimates, catchment area, mismanaged waste and source identifiers for display. Every source identifier is retained at maximum zoom; lower zooms thin points, and positions are quantized to tile coordinates. Never compute global totals or absence/presence from low-zoom display tiles. The [MapLibre style](styles/annual-input.json) maps the midpoint annual estimate to color and radius. A PMTiles-aware viewer resolves its relative source URL and registers the PMTiles protocol.

Example with DuckDB, run from this collection directory:

```sql
SELECT count(*) AS river_inputs, sum(i_mid) AS tonnes_per_year
FROM read_parquet('river-plastic-inputs.parquet');

SELECT source_row, i_low, i_mid, i_high
FROM read_parquet('river-plastic-inputs.parquet')
WHERE bbox.xmin BETWEEN 100 AND 110 AND bbox.ymin BETWEEN 0 AND 20;
```

Four source rows (22271, 36248, 36262, 36276) have missing annual/monthly emission and runoff estimates. Their numeric DBF asterisk markers are preserved as null, with the points and catchment attributes retained. They appear gray in the default style. See [quality.json](quality.json); null is not zero.

The monthly `i_*` fields are tonnes/month; annual `i_low`, `i_mid`, `i_high` are tonnes/year. Monthly runoff is mm/day, `mpw` is kg/year, and `area` is square metres. Low/mid/high fields are the model's published estimate bounds, not newly computed confidence intervals. Seasonal means and rounded published fields need not sum exactly to the annual fields.

The source has 19 coincident-coordinate pairs (38 records), leaving 40,741 distinct positions. Preserve both records at each position; different values and nulls at the same location are not a reason to deduplicate.

A captured GEE copy matches all 53 numeric fields and nulls, including the coincident groups. Strict coordinate parity failed: GEE positions differ by up to 0.3494564 metres. A separately declared one-metre geodesic diagnostic passes; this conversion retains the original Figshare coordinates. GEE metadata does not identify a source version or ingestion transform. The catalog's kg/year prose conflicts with the original tonnes/year units; observed GEE values match without scaling. See the verification reports packaged with the release. These checks establish conversion and summary consistency, not independent observational validation of the model.

## Fields

{chr(10).join(rows)}

## License and provenance

{provenance}
"""
    (folder / "README.md").write_text(collection_readme)
    guidance = """# Dataset guidance for agents

Use the GeoParquet analytic data for calculations; PMTiles is a visual derivative with thinning at lower zooms and quantized positions. Interpret the values as Lebreton et al. (2017) modeled inputs for the 2010 baseline, not present-day measured emissions or the Meijer et al. (2021) model.

Four source points have null emission/runoff estimates; retain them and never replace their nulls with zeros. Their source row numbers are 22271, 36248, 36262 and 36276.

There are 19 exact coincident-coordinate pairs in the source. Preserve multiplicity. GEE comparison found identical numeric values and nulls with sub-metre coordinate differences; the original strict coordinate check failed. Original Figshare geometry is retained.

Preserve the distinction between tonnes/year, tonnes/month, mm/day, kg/year and square metres. Retain the lower, midpoint and upper estimates. Decimal fields preserve source DBF numeric values; use Decimal-aware readers for lossless operations.

The geometry coordinates are longitude, latitude in WGS84 (OGC:CRS84). The bbox covering columns support remote spatial pruning. source_row is the one-based ordinal in the pinned shapefile, not a producer-issued watershed ID. The original source DOI and SHA-256 in manifest.json define its scope.

This is a locally prepared release. Check the release validation report and later hosting receipt before claiming publication or Portolan registry acceptance. Attribution and CC BY 4.0 license are in README.md. No external service or data export is needed to read the local bundle.
"""
    (root / "AGENTS.md").write_text(guidance)
    (folder / "AGENTS.md").write_text(guidance)
    (root / "LICENSE.txt").write_text(f"Dataset and derived data: Creative Commons Attribution 4.0 International (CC BY 4.0).\n{CONFIG['license_url']}\n\n{CITATION}\nOriginal data release: https://doi.org/{CONFIG['source_doi']}\nChanges: format conversion, spatial ordering, source-row identifiers, metadata, visualization tiles.\n")
    extensions = [CONFIG["portolan_schema"], "https://stac-extensions.github.io/file/v2.1.0/schema.json",
                  "https://stac-extensions.github.io/table/v1.2.0/schema.json",
                  "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                  "https://stac-extensions.github.io/version/v1.2.0/schema.json",
                  "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"]
    def link(rel, href, media="application/json", **more):
        return {"rel": rel, "href": href, "type": media, **more}
    shared_links = [link("describedby", "README.md", "text/markdown"), link("agents", "AGENTS.md", "text/markdown"),
                    link("via", "https://doi.org/" + CONFIG["source_doi"], "text/html"),
                    link("license", CONFIG["license_url"], "text/html")]
    collection_assets = {
        "data": asset(folder / "river-plastic-inputs.parquet", folder, "application/vnd.apache.parquet", ["data"], "Complete analytic data, GeoParquet 1.1"),
        "tiles": asset(folder / "river-plastic-inputs.pmtiles", folder, "application/vnd.pmtiles", ["visual"], "River input display tiles"),
        "style-annual-input": asset(styles / "annual-input.json", folder, "application/vnd.mapbox.style+json", ["style", "default"], "Annual midpoint input style"),
        "thumbnail": asset(folder / "thumbnail.png", folder, "image/png", ["thumbnail"], "Annual midpoint input map"),
        "schema": asset(folder / "schema.json", folder, "application/json", ["metadata"], "Field dictionary"),
        "quality": asset(folder / "quality.json", folder, "application/json", ["metadata"], "Original missing values and encoding"),
        "original": {"href": CONFIG["source_url"], "type": "application/zip", "roles": ["source"], "title": "Original Figshare v6 shapefile archive",
                     "file:size": CONFIG["source_size"], "file:checksum": "1220" + CONFIG["source_sha256"]},
    }
    collection = {"type": "Collection", "stac_version": "1.1.0", "stac_extensions": extensions,
                  "id": CONFIG["id"], "title": CONFIG["title"], "description": intro,
                  "license": CONFIG["license"], "version": CONFIG["release"], "created": CONFIG["metadata_timestamp"], "updated": CONFIG["metadata_timestamp"],
                  "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [["2010-01-01T00:00:00Z", "2010-12-31T23:59:59Z"]]}},
                  "providers": [{"name": "Lebreton et al.", "roles": ["producer", "licensor"], "url": "https://doi.org/" + CONFIG["paper_doi"]},
                                {"name": "Folia", "roles": ["processor", "host"], "url": "https://folia.sh", "description": "Processor and designated publisher for this prepared catalog. Public hosting remains pending."}],
                  "sci:doi": CONFIG["source_doi"], "sci:citation": CITATION,
                  "keywords": ["river", "plastic", "ocean", "pollution", "global", "2010", "Lebreton"],
                  "table:columns": [{k: f[k] for k in ("name", "type", "description")} for f in schema],
                  "links": [link("root", "../catalog.json"), link("parent", "../catalog.json"), *shared_links,
                            link("pmtiles", "river-plastic-inputs.pmtiles", "application/vnd.pmtiles", **{"pmtiles:layers": ["river_inputs"]})],
                  "assets": collection_assets}
    catalog = {"type": "Catalog", "stac_version": "1.1.0", "stac_extensions": [CONFIG["portolan_schema"]],
               "id": "folia-river-plastic-inputs", "title": CONFIG["title"], "description": intro,
               "created": CONFIG["metadata_timestamp"], "updated": CONFIG["metadata_timestamp"],
               "links": [link("root", "catalog.json"), *shared_links,
                         link("child", CONFIG["id"] + "/collection.json", title=CONFIG["title"])]}
    write_json(folder / "collection.json", collection)
    write_json(root / "catalog.json", catalog)
