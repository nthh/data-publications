# Catalog presentation review — 2026-11-07

Frozen before rendering: [`plan.json`](plan.json) pins four global PMTiles previews, exact style and land-context inputs, a 1200 × 720 viewport, and bounds of 180°W–180°E, 60°S–82°N. Polar caps are outside this Mercator orientation preview. The existing river-plastic analytical plot remains unchanged.

Acceptance criteria:

- Render the published PMTiles with the pinned display style, not the first rows of a spatially sorted analytical file. Retain width-dependent GRWL styling. Do not change or rebuild any analytical or PMTiles asset.
- Bound requests to the exact planned object, require HTTP 206 with correct byte ranges and object length, retain response hashes, and fail on browser/map/network errors. Require rendered dataset features, not just a basemap. This run checks the rendered ranges, not a fresh full-object SHA-256.
- Visually inspect all four PNGs at card size: recognizable global land context, visible data on multiple continents, legible dataset identity, and honest display/generalization labels. No scientific completeness or accuracy claim. LakeATLAS shares HydroLAKES geometry and need not look geographically different; its title identifies the attribute product.
- Bind reviewed PNGs by SHA-256 in each canonical record. Regenerate both STAC thumbnail assets and links. Catalog generation and staging must reject changed/unsafe inputs; original package snapshots, manifests and source attribution must remain unchanged.
- Correct the four inherited Folia converter labels to the confirmed maintainer, nthh, explicitly in canonical metadata. Preserve all producer/licensor roles, code notices and immutable historical evidence. GRWL already names nthh.
- Run the README query verbatim outside the checkout, focused metadata regressions, generation/staging and locked Rashid validation. Record incomplete checks as incomplete. No deployment or push is part of this review.

The old shared packager drew the first 50,000 records or 500,000 vertices against the complete dataset extent. That selected a small spatial cluster in sorted files. Portolan Browser displays our supplied PNG directly through its thumbnail asset/link; it did not create the sparse previews. The river-plastic thumbnail uses its own global plotting workflow.

The first rendered camera cropped the frozen southern/northern bounds; those PNGs were rejected. The second run fits the bounds, but the overview tiles contain only 18 major lakes and sparse rivers at this scale. [`plan-r2.json`](plan-r2.json), frozen before the third render, requests zoom-3 source tiles for HydroLAKES, LakeATLAS polygons and Free-Flowing Rivers while retaining the same global camera and paint styles. GRWL keeps its original overview zoom and width-dependent symbols. This is a thumbnail-only detail choice, not a change to the PMTiles packages. Titles and labels still describe a generalized display overview. Response limits remain 8 MiB per request and 64 MiB per case.

The third attempt failed its nonempty-data gate for the three explicit zoom-3 cases: MapLibre's vector `minzoom` hides a source below that camera zoom. [`plan-r3.json`](plan-r3.json) retains the desired tile level and fixed camera. The renderer now decodes all available zoom-3 tiles to transient GeoJSON display fragments before drawing them with the existing paint styles. Tile buffers and clipping remain presentation details; counts of rendered fragments are not analytical row counts. GRWL continues through the original PMTiles protocol and width style. This approach is bounded to 64 possible display tiles per case and never reads complete analytical files.

The fourth attempt read the intended tiles but the MapLibre worker rejected the decoder's null-prototype property dictionaries. The renderer now copies those dictionaries into ordinary objects, preserving their values, before passing the transient display features to the worker. The data-nonempty gate rejected all three affected previews; no failed image is selected for publication.

## Repeat the current workflow

From a checkout, install the locked renderer dependencies, generate previews to a new local directory, and inspect every image:

```sh
npm --prefix scripts/cloud_viewer ci --ignore-scripts --no-audit --no-fund
node scripts/cloud_viewer/render-thumbnails.mjs --plan research/catalog-presentation-20261107/plan-r3.json --out .local/catalog-thumbnails-review-001
```

The renderer uses an isolated headless Chrome (default macOS application path; override with `CHROME_PATH`), local bundled MapLibre, pinned Natural Earth land, and anonymous bounded PMTiles reads. It records exact response hashes, byte totals, camera, feature counts, output checksums, browser version, and source/lock hashes. It refuses an existing output directory and saves failed attempts. PNG pixels can vary across browsers, GPUs and fonts; a different render must be inspected and explicitly rebound, not silently substituted.

Copy only reviewed images into a new `datasets/<id>/presentation/<revision>/` directory and set that dataset's `publication.catalog.thumbnail` path, SHA-256 and title. The initial corrected previews are `global-v1`. Regenerate with `scripts/catalog.py --write` and `scripts/publication_catalog.py write`, then `check` and `stage` as documented in the [catalog workflow](../../docs/catalog-workflow.md). When a generated thumbnail path changes, the generator refuses the obsolete output path; reconcile only that generated copy after verifying the original release snapshot remains intact. No analytical or PMTiles rebuild is needed.

Preview the official Browser against the local stage:

```sh
node scripts/cloud_viewer/check-catalog-cards.mjs --stage .local/catalog-presentation-stage-r1 --out .local/catalog-cards-review-001
```

This intercepts catalog requests with checksum-verified staged bytes; it does **not** deploy or verify new public hosting. It refuses Source data requests because this check concerns only catalog cards. The [card screenshot](catalog-cards.png), [browser report](portolan-cards.json), [render report](render/render-r5.json), and [visual review](visual-review.json) document the selected previews. The [staged Rashid report](rashid-staged.json) passes conformance; the separate offline stac-check advisory remains incomplete because external schema access is denied.

The root README now starts with the published products and a direct DuckDB query. The query was extracted verbatim and run from outside the checkout against the 6,360,991-byte river-plastic file. Its first draft incorrectly called `.show()` on a connection; the corrected `.sql(...).show()` command passed. It returned source rows 7311, 7805, 8002, 7383 and 2052 with the five largest non-null modeled annual inputs. No GEE job, data rebuild, upload or deployment is part of this task.

## Final verification

[Verification summary](verification.json): 25 focused publication-catalog tests and 19 canonical-catalog tests passed. The 453-record inventory and 186 historical provenance entries passed their checks. All five generated Collections now name `nthh` as processor and host, while every original producer/licensor entry matches the prior catalog exactly. Immutable release snapshots and `NOTICE` are unchanged.

A clean checkout of the implementation commit, with a fresh locked dependency install and no local analytical data, regenerated all 29 staged files without tracked drift. A fresh render reproduced all four selected PNGs byte-for-byte on the same machine/browser; this is not a cross-platform pixel-identity guarantee. The final card checker loaded all five images and produced the identical reviewed official Browser screenshot. [Clean-checkout evidence](clean-checkout/) includes both passing Rashid conformance checks and the incomplete STAC advisories. The public catalog remains at the previous deployment until a separate push/deployment is requested.
