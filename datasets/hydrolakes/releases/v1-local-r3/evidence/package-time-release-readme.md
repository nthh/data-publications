# HydroLAKES v1 local GeoParquet release candidate r3

This is a local, unpublished candidate for the complete HydroLAKES v1.0 polygon layer. The producer release is v1 (the archive filename uses v10); its composite shoreline sources are legacy observations, not a 2026 shoreline survey. The candidate contains one analytic GeoParquet asset and no PMTiles display derivative. Source fidelity establishes preservation of the producer representation, not GEE parity or independent scientific accuracy.

## Asset identity and layout

The source-validated raw GeoParquet contains 1,427,688 features and 22 original fields, including `Hylak_id` and `wkb_geometry`. It is 945,383,282 bytes with SHA-256 `4c7c83b0a91e4cbd1e31583ab89eee9721ba22250272640591f4795d186a6a76`. The candidate is a deterministic spatially ordered derivative: it preserves those 22 fields and WKB, appends a WKB-derived `bbox` struct, and orders rows by 16-bit Hilbert distance of WGS84 bbox centers with `Hylak_id` ascending as the tie-breaker. It contains the same 1,427,688 rows and is 949,598,607 bytes with SHA-256 `6f588d97c14651eb23bea2d74fdf2a85f218a00ff11519c81efa5512b916b7f8`.

The retained and clean-rebuild outputs are byte-identical. Both validated reports compare all 29,981,448 original non-geometry attribute values/nulls, compare every WKB's null state, byte length and SHA-256 keyed by native ID, and independently recompute every bbox child from WKB. Both report the same global WKB extent `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]` (west, south, east, north), `Polygon: 1,427,688`, and 128 row groups. No coordinate reprojection, geometry repair, simplification or WKB rewrite occurs. Attribute equality uses Arrow value/null comparison per original column; this does not distinguish `+0.0` and `-0.0` bit patterns and may reject unchanged NaNs. WKB comparison is per-feature SHA-256 plus byte length and null state, not a single aggregate digest.

## Reproduce the spatial-order stage

Run from a checkout pinned to spatial helper commit `100eaadad0e42a6f12d61c08de7d061eb5bac499` with a locked `scripts/release_tools` environment. Before each command, measure task-owned allocated bytes under the HydroLAKES artifact root, excluding the active input; set `HYDRO_PRIMARY_BASELINE_GB` and `HYDRO_CLEAN_BASELINE_GB` to the respective measured decimal GB values. For these runs the inputs were identical retained and clean raw builds; measured baselines were 3.64 GB and 4.60 GB respectively. The helper uses its default 1,000,000,000-byte RSS cap and refuses to exceed the 8 GB task cap or 40/10 GB free-space floors.

```sh
uv run --locked --project scripts/release_tools python scripts/release_tools/spatial_order.py \
  --input .local/hydrolakes/retained/data.parquet \
  --output .local/hydrolakes/spatial-order-r4/hydrolakes.parquet \
  --report .local/hydrolakes/spatial-order-r4/spatial-order-validation.json \
  --identifier-column Hylak_id --geometry-column wkb_geometry \
  --buckets 128 --batch-rows 128 --buffer-rows 32 --row-group-size 16384 \
  --task-owned-baseline-gb "${HYDRO_PRIMARY_BASELINE_GB:?Set measured original-run baseline in decimal GB}" --task-disk-limit-gb 8 \
  --minimum-start-free-gb 40 --minimum-remaining-free-gb 10

uv run --locked --project scripts/release_tools python scripts/release_tools/spatial_order.py \
  --input .local/hydrolakes/clean-rebuild-442460a/data.parquet \
  --output .local/hydrolakes/spatial-order-clean-r4/hydrolakes.parquet \
  --report .local/hydrolakes/spatial-order-clean-r4/spatial-order-validation.json \
  --identifier-column Hylak_id --geometry-column wkb_geometry \
  --buckets 128 --batch-rows 128 --buffer-rows 32 --row-group-size 16384 \
  --task-owned-baseline-gb "${HYDRO_CLEAN_BASELINE_GB:?Set measured clean-run baseline in decimal GB}" --task-disk-limit-gb 8 \
  --minimum-start-free-gb 40 --minimum-remaining-free-gb 10

uv run --locked --project scripts/release_tools python scripts/release_tools/check_spatial_pruning.py \
  --input .local/hydrolakes/spatial-order-r4/hydrolakes.parquet \
  --report .local/hydrolakes/spatial-order-r4/spatial-pruning-validation.json
```

Repeat the pruning command with the clean companion and its report path. Link the [source conversion workflow](../../README.md) for the pinned raw build and validation details. Use fresh output paths for a new run; failed artifacts remain inspectable and are not silently replaced.

## Local validation

Actual Rashid 0.1.8's PTL-DAT-006 predicate passes with ten chunks: adjacent bbox overlap fraction 1.0, mean chunk bbox area/global extent area 0.1310052704485944 (<0.30). The four predeclared bbox windows pass the 50% row-group pruning criterion: Europe 126/128, North America 122/128, East Africa 125/128, Australia 125/128. STAC Node, Portolan, package integrity, bounded HTTP 206/CORS reads, local/loopback DuckDB subset identity, and final immutable package verification are release gates that must be reported in the package receipt; this README draft does not predeclare those results.

The package’s tracked manifest, Catalog and Collection copies are review evidence whose links resolve within the standalone package tree; the repository copies are not a live Git-hosted STAC catalog. Bulk GeoParquet and the producer PDF remain in the ignored local package, not in Git.

## Producer terms and citation

The producer product page states CC BY 4.0. The technical document requests permission before redistributing the complete database in its original format. The package includes the transformed GeoParquet and producer technical PDF and preserves that request; this README does not make a broader legal determination. The paper DOI `10.1038/ncomms13603` is a citation DOI, not the source dataset DOI.

## Reproduce the release package

From the repository root, materialize the fidelity input and package spec from the templates in `reproduction/`. The templates point to already-built retained and clean artifacts; this workflow does not rerun the producer conversion or fetch the evicted ZIP.

```sh
python datasets/hydrolakes/releases/v1-local-r3/reproduction/materialize_release_inputs.py fidelity \
  --artifact-root /path/to/local/hydrolakes \
  --clean-checkout /path/to/detached-clean-checkout \
  --output /path/to/ignored/hydrolakes-fidelity-input.json

uv run --locked --project scripts/release_tools python research/hydro-releases-20261031/bind_fidelity.py \
  /path/to/ignored/hydrolakes-fidelity-input.json \
  --output-dir /path/to/ignored/hydrolakes-fidelity-r3

python datasets/hydrolakes/releases/v1-local-r3/reproduction/materialize_release_inputs.py package \
  --artifact-root /path/to/local/hydrolakes \
  --repo-root . \
  --fidelity-root /path/to/ignored/hydrolakes-fidelity-r3 \
  --package-output /path/to/local/hydrolakes/releases/v1-local-r3 \
  --output /path/to/ignored/hydrolakes-package-input.json

uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  /path/to/ignored/hydrolakes-package-input.json
```

Use fresh ignored output paths. The helper refuses to overwrite, retains failed reports and only marks the package prepared if all mandatory gates pass. Local preparation is not public hosting or registry submission.
