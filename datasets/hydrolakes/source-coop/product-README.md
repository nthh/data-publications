# HydroLAKES v1.0 — global lake polygons

The complete HydroLAKES v1.0 polygon layer in spatially ordered GeoParquet, preserving producer fields and geometry for lake analysis and joins. A separately versioned PMTiles layer provides generalized map display and source-ID attribute lookup.

**Validated hosted release:** `v1-local-r3`. The canonical record binds the public Source Cooperative package and its completed hosting checks.

## Scope and formats

Static global lake polygons derived from composite legacy shoreline sources. This is not a 2026 shoreline observation; no GEE parity or independent scientific-accuracy claim is made. The packaged GeoParquet is spatially ordered and preserves source attributes and raw WKB.

Formats: `application/json`, `application/pdf`, `application/vnd.apache.parquet`, `application/vnd.pmtiles`, `image/png`.

## Producer, source, and license

- Producer attribution: Lehner and Messager / HydroSHEDS. Cite Messager et al. (2016), DOI 10.1038/ncomms13603.
- License: Producer license: CC BY 4.0. Retain attribution and technical-document notices, including the producer request concerning redistribution of the complete database in its original format. This product contains transformed GeoParquet.
- Temporal scope: Static research release compiled from multiple shoreline sources; not a current inventory of lake conditions.

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Original download](https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip)
- [Research paper](https://doi.org/10.1038/ncomms13603)
- [Producer source](https://gee-community-catalog.org/projects/hydrolakes)
- [Processor: nthh](https://source.coop/nthh/hydrolakes)
- [Producer: Lehner and Messager / HydroSHEDS](https://www.hydrosheds.org/products/hydrolakes)

## Release files

- [hydrolakes-polygons.parquet](releases/v1-local-r3/assets/hydrolakes-polygons.parquet) (asset)
- [thumbnail.png](releases/v1-local-r3/display/thumbnail.png) (display_derivatives)
- [data-license.json](releases/v1-local-r3/licenses/data-license.json) (data_license)
- [source-license.json](releases/v1-local-r3/licenses/source-license.json) (source_license)
- [hydrolakes-polygons-field-dictionary.json](releases/v1-local-r3/metadata/hydrolakes-polygons-field-dictionary.json) (field_dictionary)
- [clean-rebuild-raw.json](releases/v1-local-r3/provenance/clean-rebuild-raw.json) (supporting_files)
- [evidence-provenance.json](releases/v1-local-r3/provenance/evidence-provenance.json) (supporting_files)
- [source-cache-eviction.json](releases/v1-local-r3/provenance/source-cache-eviction.json) (supporting_files)
- [source-document.json](releases/v1-local-r3/provenance/source-document.json) (supporting_files)
- [source-validation.json](releases/v1-local-r3/provenance/source-validation.json) (supporting_files)
- [spatial-order-clean-rebuild.json](releases/v1-local-r3/provenance/spatial-order-clean-rebuild.json) (supporting_files)
- [spatial-order-retained.json](releases/v1-local-r3/provenance/spatial-order-retained.json) (supporting_files)
- [spatial-pruning-clean-rebuild.json](releases/v1-local-r3/provenance/spatial-pruning-clean-rebuild.json) (supporting_files)
- [spatial-pruning-retained.json](releases/v1-local-r3/provenance/spatial-pruning-retained.json) (supporting_files)
- [HydroLAKES_TechDoc_v10.pdf](releases/v1-local-r3/source/HydroLAKES_TechDoc_v10.pdf) (supporting_files)
- [attribution.json](releases/v1-local-r3/source/attribution.json) (source_attribution)

## Display package

Display release: `display-v1`. The manifest is pinned at SHA-256 `f3dbb0d87553162a6b2a91172626eeecca9985fb8df54685ee64924ca826d841`.
Display assets are separate immutable derivatives bound to this analytical release.
- [Display manifest](display/display-v1/manifest.json)
- [Hydrolakes Polygons PMTiles](display/display-v1/assets/hydrolakes-polygons.pmtiles) (1122881121 bytes; SHA-256 `2fc61a8257322bed3c71f86e3be92ed4835023bbb23f80bc9b2bb5167cb19d46`)
  - [Map style](display/display-v1/styles/hydrolakes-polygons.json)

## Limitations

- This release contains polygons; it does not include the separate HydroLAKES pour-point source layer.
- Spatial ordering and added bounding boxes preserve original attributes and WKB; local display queries do not establish public-host performance.
- Live GEE count and all 522 sampled IDs match. There are 508 null/empty lake-name differences, strict geometry failures and three narrow source spikes absent spatially from GEE. Source geometry is retained; no exhaustive GEE or independent scientific-accuracy claim.

Public hosting checks are bound in the canonical report. Scientific validation retains its documented scope.
