# HydroLAKES v1 polygons

## GEE review — 2026-11-06

Live GEE count and all 522 sampled IDs match. There are 508 null/empty lake-name differences, strict geometry failures and three narrow source spikes absent spatially from GEE. Source geometry is retained; no exhaustive GEE or independent scientific-accuracy claim. See the [complete comparison review](../../research/gee-release-validation-20261106/README.md) and [structured evidence](../../research/gee-release-validation-20261106/summary.json). The validated release is [public on Source Cooperative](https://source.coop/nthh/hydrolakes); hosting checks do not change these scientific-comparison findings.


This package preserves the complete 1,427,688-feature HydroLAKES polygon release
as ID-sorted GeoParquet. Producer: Lehner and Messager / HydroSHEDS. The
[canonical record](dataset.yaml) pins the original archive, license and workflow.
The current producer release is v1; its composite shoreline sources are older
than the release preparation date. It is not a 2026 shoreline observation.

## Repeat locally

From the repository root:

```sh
uv sync --locked --project datasets/hydrolakes
uv run --locked --project datasets/hydrolakes python datasets/hydrolakes/acquire.py --output .local/hydrolakes/source/HydroLAKES_polys_v10_shp.zip
uv run --locked --project datasets/hydrolakes python datasets/hydrolakes/convert.py --source .local/hydrolakes/source/HydroLAKES_polys_v10_shp.zip --output .local/hydrolakes/new-run/data.parquet --staging-dir .local/hydrolakes/new-run/staging --source-url https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip --source-sha256 9ef63498569dd7ccd0b8d8852da026e009a75f42d293f00e483f3b9fcfe8e1f9
uv run --locked --project datasets/hydrolakes python datasets/hydrolakes/validate.py --source .local/hydrolakes/source/HydroLAKES_polys_v10_shp.zip --data .local/hydrolakes/new-run/data.parquet --report .local/hydrolakes/new-run/source-validation.json
```

Use a fresh output directory. The converter retains staging for inspection and
will not overwrite it. Source attributes are preserved as decoded by GDAL/Arrow,
including nulls and producer sentinel values; no coordinate repair, reprojection,
simplification or deduplication occurs. `Hylak_id` remains the unique identifier.
The retained raw GeoParquet has 22 original columns and is sorted by `Hylak_id`; it is 945,383,282 bytes with SHA-256 `4c7c83b0a91e4cbd1e31583ab89eee9721ba22250272640591f4795d186a6a76`. It remains the source-fidelity baseline. The published r3 analytical asset is a deterministic Hilbert-ordered GeoParquet companion: it preserves all 22 original fields and WKB, appends WKB-derived GeoParquet 1.1 `bbox` covering, and is 949,598,607 bytes with SHA-256 `6f588d97c14651eb23bea2d74fdf2a85f218a00ff11519c81efa5512b916b7f8`. Both contain 1,427,688 rows. The retained and clean companions are byte-identical with 128 row groups.

Both full reports compare all original attribute values/nulls after restoring `Hylak_id` order; they compare every WKB's null state, byte length, and SHA-256 keyed by `Hylak_id`, and independently recompute every bbox child from WKB. The raw and companion global WKB extents match: `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]`. The spatial-order report passes the Rashid 0.1.8 PTL-DAT-006 predicate by area ratio `0.1310052704485944` (<0.30); the adjacent overlap fraction is 1.0. Four fixed geographic windows pass the separate row-group pruning check at 0.953–0.984. The r3 package passes STAC Node, Portolan, HTTP 206/CORS, DuckDB subset, manifest/integrity and independent immutable-package verification. Its immutable build-time manifest remains `local-candidate` and its build receipt says `packaged_locally_not_published`; current publication status is separately bound to the [hosted report](../../research/source-publication-20261106/hosted-results/hydrolakes/hosted-validation.json). No registry submission occurred. Exact portable package evidence is in [the r3 release directory](releases/v1-local-r3/README.md). The previous r1/r2 failures remain preserved evidence; none of those checks was waived.

The converter was ported from Folia's FRC11 workflow. Its historical output is
945,383,282 bytes with SHA-256
`4c7c83b0a91e4cbd1e31583ab89eee9721ba22250272640591f4795d186a6a76`.
That historical identity is evidence to verify, not a substitute for source
fidelity, clean rebuild and packaging checks in this standalone repository.

## Validation and attribution

[VALIDATION.md](VALIDATION.md) defines source fidelity and release gates. Routine
checks are local; no GEE request or upload occurs. A source match does not establish
scientific accuracy or parity with the GEE representation. The original source
reader remains part of the validation boundary.

Data: CC-BY-4.0. Cite Messager et al. (2016), *Estimating the volume and age of water
stored in global lakes using a geo-statistical approach*, Nature Communications,
[doi:10.1038/ncomms13603](https://doi.org/10.1038/ncomms13603).
The producer technical documentation also requests permission for redistributing
the whole database in its original format; preserve that request and assess the
intended transformed release specifically. Repository-authored code: Apache-2.0.

## PMTiles display

The local [display-v1 package](display/display-v1/README.md) adds generalized
PMTiles with stable source IDs and a portable style. Its generated manifest binds
the original analytical asset, complete maximum-zoom ID and selected-attribute
checks, sampled geometry validation, and browser range/attribute checks. The
GeoParquet remains authoritative for analysis and complete fields.

See the [repeatable display workflow](../../docs/display-derivatives.md) and
[local viewer](../../scripts/cloud_viewer/README.md). This is local preparation;
public hosting and GEE parity are separate validation boundaries.

## Source selection audit

Complete official polygon layer; the separate producer pour-point layer is outside this release. No summary geometry substitution found. The [2026-11-02 source audit](../../research/grwl-raw-release-20261102/source-audit/hydro-audit.md) distinguishes full source fidelity from scientific accuracy and records the limits of rebuild/GEE evidence.
