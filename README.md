# Data Publications

Reproducible conversions of global geospatial datasets, with documented sources, Python workflows and validation evidence. Five datasets have verified analytical and PMTiles releases on Source Cooperative, including the 64.6-million-observation GRWL raw product. The simplified GRWL summary is withheld after a source-quality review. Current hosted status and evidence are recorded in the canonical dataset records and generated catalog.

Maintained under [`nthh`](https://github.com/nthh). Explore the [global candidate backlog](CANDIDATES.md) and its [filterable CSV](candidates.csv), review the [publication shortlist with sizes and source counts](SHORTLIST.md) ([JSON](shortlist.json), [CSV](shortlist.csv)), or read the [current dataset status](#current-scope). Candidates are exploratory, with no commitment to convert or publish.

## Quick start

Install [uv](https://docs.astral.sh/uv/) and Python as pinned by the repository, then from the repository root:

```sh
uv sync --locked
uv run --locked python scripts/catalog.py --check
uv run --locked python scripts/publication_catalog.py check
uv run --locked python scripts/rank_citations.py --check
python3 scripts/rank_catalog_citations.py --check
uv run --locked python scripts/check_provenance.py
uv sync --locked --project datasets/river-plastic-inputs
uv run --locked --project datasets/river-plastic-inputs python datasets/river-plastic-inputs/build.py --help
```

The checks validate all canonical records, the generated index, candidate backlog and related-dataset README sections, the citation snapshot and the historical workflow bytes. The final commands install and show the river-plastic pilot's local build options. Dataset-specific setup and validation instructions belong in that dataset's README. See [publishing guidance](docs/publishing.md) before treating a local build as a release.

## Dataset viewers

[Browse the five published datasets in Portolan Browser](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/catalog.json). The [live catalog](https://nthh.github.io/data-publications/catalog.json) is served from GitHub Pages; analytical data and PMTiles are hosted on Source Cooperative.

The optional [local multiscale viewer](scripts/cloud_viewer/README.md) reads configured datasets from a separate HTTP object origin, using PMTiles for display and GeoParquet byte ranges for complete attribute lookup. The recorded local build includes five prepared datasets and the retained GRWL summary comparison as seven map layers. GRWL raw line thickness uses each original observation's width, with a metre-based legend and explicit display exaggeration. Dataset files stay in ignored local storage; GDW and SWOT remain visibly unavailable. GRWL uses original-width overview symbols at zooms 0–7 and detailed observations from zoom 8 in the same archive. Follow the [current GRWL width workflow](research/grwl-width-overview-20261106/README.md) and [common viewer setup](scripts/cloud_viewer/README.md) to restart it.

The [display build and validation pattern](docs/display-derivatives.md) documents
the separate versioned PMTiles packages and repeatable checks.

The [display verification](research/pmtiles-all-20261102/README.md) records the
initial six-layer checks. The later [GRWL geometry investigation](research/grwl-straight-segments-20261102/README.md)
distinguishes an upstream straight segment from a corrected dateline display
artifact and adds exact Decimal-value and dateline browser controls. The
[GEE comparison review for all five datasets](research/gee-release-validation-20261106/README.md)
is complete, with [structured findings](research/gee-release-validation-20261106/summary.json).
All live global counts match. Large collections use 512–522 source-selected samples per layer;
river-plastic retains its exhaustive historical replay plus a fresh metadata/count check.
Strict parity fails and the report documents the attribute and geometry differences.
These checks are separate from the complete producer-source fidelity checks and scientific accuracy.

The [raw GRWL release](datasets/grwl-raw/README.md) contains the lossless 5.53 GB GeoParquet and the current `raw-v01.01-display-r3` PMTiles archive, with source-width display at zooms 0–12. The [width build and browser evidence](research/grwl-width-overview-20261106/README.md) covers the current archive. The 304 enumerated tile-grid collapses remain preserved in GeoParquet. The [source-choice audit](research/grwl-raw-release-20261102/README.md) records the original-source findings for the other datasets.

## Repository layout

The shared repository contains editable dataset projects and a generated publication tree. Each dataset keeps one canonical `dataset.yaml`; generated STAC files and snapshot manifests are outputs and evidence.

| Path | Purpose |
| --- | --- |
| `datasets/<id>/` | Canonical record, source/build/validation scripts and dataset instructions |
| [`CANDIDATES.md`](CANDIDATES.md) and [`candidates.csv`](candidates.csv) | Generated global backlog, citation observations, discovery catalogs and existing-access review |
| [`SHORTLIST.md`](SHORTLIST.md), [`shortlist.json`](shortlist.json), [`shortlist.csv`](shortlist.csv) | Generated ranked scopes, source sizes, prepared asset sizes, distinct distribution services and GEE asset IDs |
| `datasets/<id>/releases/<release>/` | Small immutable analytical release evidence and exported catalog inputs |
| `datasets/<id>/display/<display-release>/` | Generated display manifest and reviewed PMTiles validation evidence |
| [`catalog/`](catalog/) | Generated publication metadata: STAC, consumer README/AGENTS, styles and thumbnails |
| `scripts/` and `scripts/release_tools/` | Shared generation, preparation and release helpers |
| [`catalog.publish.yaml`](catalog.publish.yaml) | Public navigation and confirmed GitHub Pages metadata destination |
| [`tools/portolan/`](tools/portolan/) | Locked validators and pinned upstream guidance |
| `.github/workflows/` | Record/catalog validation and manually requested publication preparation |
| `research/` | Dataset discovery, citation snapshots, comparisons and audits |
| `.local/` | Ignored source downloads, bulk data, environments and local checks |

The [generated catalog](catalog/README.md) includes only releases with verified hosted URLs and checksum-bound evidence. Candidate and prepared records stay outside it. Historical metadata snapshots remain with their release evidence. GitHub Pages serves the [live catalog](https://nthh.github.io/data-publications/catalog.json). All five collections and six display layers passed the official Browser live check and manual screenshot review; the [publication record](research/source-publication-20261107/public-release-r1.json) binds deployment, hosting and viewer evidence.

See [the catalog workflow](docs/catalog-workflow.md) for generation, validation and local preparation. Existing conversion scripts retain their paths and environment locks so historical rebuild evidence stays meaningful.

## Discovery and selection research

The [global discovery study](research/global-candidates-20261031/README.md) expands the backlog across highly cited dataset families, the official GEE catalog, Planetary Computer, Esri public data and producer sources. Sources are matched to existing records where scope permits; distinct products and editions remain explicit. Existing native formats are a reason to investigate reuse before building another copy.

The [native-publication gap review](research/native-publication-gaps-20261031/README.md) narrows the publication shortlist. The [size and availability audit](research/availability-sizes-20261101/README.md) records current source sizes, distribution locations and edition mismatches in the canonical records. Counts and tables are generated; unknown sizes remain null.

The [GDW/SWOT source and publication-readiness review](research/gdw-swot-preparation-20261101/README.md) documents GDW's overlap with Overture and AquaScope, the exact SWOT v2.03 inventory, retained source/disk failures, and the then-current integrity checks for five retained packages. GRWL summary publication was subsequently withheld following the raw-source audit.

The [Source Cooperative product preparation](research/source-products-20261101/README.md) adds generated product drafts, complete local file plans, browser evidence and versioned LakeATLAS field documentation.

The [official/community citation comparison](research/catalog-citations-20261030/README.md)
uses a fresh 1,165-entry official Earth Engine metadata snapshot and the existing
363 community documentation families. It provides all-region, global and
not-marked-deprecated views, paper groups, separate data-DOI counts, and overlap
candidates. Initial reference and geography reviews preceded scoring; documented
final audits corrected inconsistent citations and region labels. Citation rank is
separate from a decision to convert or host data. The original community
snapshot remains frozen under `research/citations/`.

The [top-30 download and format audit](research/top30-download-audit-20261030/README.md)
adds catalog membership, scoped download sizes, native formats and recommended
publication formats, with a sortable CSV and primary-source evidence.

## Data and code

Conversion code, scripts, metadata, and small evidence reports belong in Git. Bulk source archives, generated data, and raw GEE captures stay in ignored local storage. Public data releases are separate from this code repository and use immutable version prefixes. Formats should fit the data: GeoParquet and PMTiles for vector analysis and display, Cloud Optimized GeoTIFF for rasters, and Zarr for multidimensional arrays where chunked access suits the variables and use cases.

Repository-authored software is licensed under Apache-2.0. That license does not relicense upstream data, papers, source archives, embedded code, or external evidence. Each dataset record and release must state applicable data and source licenses and preserve required notices. See [NOTICE](NOTICE) and [publishing guidance](docs/publishing.md).

Useful alternatives and complementary products belong in each record’s optional
`related_datasets` field and its generated README section. See the
[record pattern](docs/dataset-template.md#related-datasets) and the
[JRC example](datasets/jrc-gsw-occurrence/README.md#related-datasets). These
references keep comparison context alongside the selected dataset.

## Current scope

Five datasets are hosted and verified: river-plastic inputs, HydroLAKES, Free-Flowing Rivers,
LakeATLAS and GRWL raw vectors. Each passed anonymous access, byte ranges, CORS,
checksums, fixed analytical subsets, catalog-link checks and browser rendering.
The generated catalog includes all five. Source listing and aggregate catalog deployment
are tracked separately in the [publication evidence](research/source-publication-20261106/README.md).
GRIP4 retains a validated historical build, with publication deferred at the user's request.
Strict GEE parity findings and source limitations remain documented alongside each release.

| Dataset | Community entry | Release / publication state | Purpose |
| --- | --- | --- | --- |
| [River-plastic inputs](https://source.coop/nthh/river-plastic-inputs) | [Catalog](https://gee-community-catalog.org/projects/plastic/) | Hosted and verified: `figshare-v6-r2` | Published research input, 40,760 river-mouth points |
| GRWL simplified network | [Catalog](https://gee-community-catalog.org/projects/grwl/) | Withheld: confirmed upstream geometry errors | Historical faithful summary, retained for comparison |
| [GRWL raw vectors](https://source.coop/nthh/grwl-raw) | [Producer](https://zenodo.org/records/18624542) | Hosted and verified: `raw-v01.01-local-r1` + `raw-v01.01-display-r3` | Separate raw observations and local width values |
| [Free-Flowing Rivers](https://source.coop/nthh/free-flowing-rivers) | [Producer record](https://doi.org/10.6084/m9.figshare.7688801.v1) | Hosted and verified: `figshare-v1-local-r2` | Global connectivity assessment, 8,477,883 reaches |
| [HydroLAKES](https://source.coop/nthh/hydrolakes) | [Catalog](https://gee-community-catalog.org/projects/hydrolakes/) | Hosted and verified: `v1-local-r3` | Global v1.0 lake polygons, 1,427,688 lakes |
| [LakeATLAS](https://source.coop/nthh/lakeatlas) | [Producer page](https://www.hydrosheds.org/hydroatlas) | Hosted and verified: `lakeatlas-v1.0-r2` | Global v1.0 polygons and pour points with hydro-environmental attributes |
| JRC GSW Occurrence | [Official source](https://global-surface-water.appspot.com/download) | Existing v1.5 source qualified by sample; reuse proposed | 504 producer TIFFs, 1984–2024; no mirror built |
| GRIP4 global roads | [Catalog](https://gee-community-catalog.org/projects/grip/) | Validated locally; publication deferred | Historical GRIP4 (2018) research input |

The [current version review](research/hydro-releases-20261031/version-review/producer-version-review.md)
checks the selected producer releases as of 2026-10-31 and distinguishes source
versions from observation dates. The [generated inventory](index.json) tracks the original community families and
supplemental producer/catalog candidates; [CANDIDATES.md](CANDIDATES.md) reports current totals.
The [FFR](datasets/free-flowing-rivers/releases/figshare-v1-local-r2/README.md),
[HydroLAKES](datasets/hydrolakes/releases/v1-local-r3/README.md) and
[LakeATLAS](datasets/lakeatlas/releases/lakeatlas-v1.0-r2/README.md) release evidence
binds complete source comparisons, clean rebuilds, exact workflow code, actual
schemas and loopback HTTP subset checks. The [JRC qualification](datasets/jrc-gsw-occurrence/README.md)
inventories all 504 source tiles but samples only eight; it does not certify every
tile or validate the pixels. See [publishing guidance](docs/publishing.md) for the
repeatable Python workflow and the remaining public-hosting gates.

The [GRWL release evidence](datasets/grwl/releases/summary-v01.02-local-r1/README.md)
records exact source comparison, display checks and a byte-identical clean rebuild.
Its newer V01.02 source has not been compared with the older catalog GEE asset.
For current roads, prefer [Overture's existing cloud-native catalog](https://docs.overturemaps.org/getting-data/cloud-sources/);
[the GRIP4 review](research/local-build-two-20261030/grip-overture-review.md) explains
why preserving a historical research release is a separate use case.

The river-plastic pilot's cached GEE comparison found exact agreement for numeric values and nulls, with a maximum coordinate displacement of 0.349456 m. The original strict-coordinate check failed; a separately documented follow-up accounted for 19 coincident-coordinate pairs while preserving their multiplicity. This is historical evidence for that captured asset, not proof of its upstream version or scientific accuracy. Routine local build and validation do not start new GEE work.

The [river-plastic workflow](datasets/river-plastic-inputs/README.md) has completed
its [standalone release rehearsal](datasets/river-plastic-inputs/releases/figshare-v6-r2/README.md):
14 generated assets reproduced identically, original data hashes were preserved,
and 39 fault checks passed. Its immutable data are hosted and verified on Source Cooperative and included in the verified live aggregate catalog.
