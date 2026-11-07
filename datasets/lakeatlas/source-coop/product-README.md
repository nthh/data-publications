# LakeATLAS v1.0 — global lake attributes and pour points

LakeATLAS lake polygons and pour points with hydro-environmental attributes in separate spatially ordered GeoParquet files, with a versioned field-semantics supplement. Separately versioned PMTiles provide map display for both layers and source-ID attribute lookup.

**Validated hosted release:** `lakeatlas-v1.0-r2`. The canonical record binds the public Source Cooperative package and its completed hosting checks.

## Scope and formats

Two analytic GeoParquet assets from the pinned LakeATLAS v1.0 producer File Geodatabase: the complete polygon layer and separate pour-point layer. The deterministic spatially ordered representations preserve producer OBJECTID, Hylak_id and all decoded source fields, nulls, and WKB; WGS84 bbox fields support spatial filtering. No geometries are repaired or simplified. Attribute years vary by source and do not represent a 2026 observation.

Formats: `application/json`, `application/pdf`, `application/vnd.apache.parquet`, `application/vnd.pmtiles`, `image/png`, `text/markdown`.

## Producer, source, and license

- Producer attribution: HydroSHEDS / HydroATLAS authors; Lehner, Messager, Korver and Linke (2022), DOI 10.1038/s41597-022-01425-z. Original conversion evidence retains Folia attribution.
- License: Mixed field-level terms: the producer catalog identifies CC BY 4.0 and ODbL 1.0 attributes. Retain the catalog, source attribution and original-source notices; do not describe the entire attribute table as uniformly CC BY 4.0.
- Temporal scope: Observation and model-input dates vary by contributing attribute; use the producer catalog and field supplement for interpretation.

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/s41597-022-01425-z)
- [Dataset release](https://doi.org/10.6084/m9.figshare.19312001.v1)
- [Folia converter/host](https://folia.sh)
- [Producer technical documentation](https://ndownloader.figshare.com/files/35959532)
- [Producer attribute catalogue](https://ndownloader.figshare.com/files/35959535)
- [Original download](https://ndownloader.figshare.com/files/35959544)
- [Producer: HydroSHEDS / HydroATLAS authors](https://www.hydrosheds.org/products/hydroatlas)

## Release files

- [lakeatlas-polygons.parquet](releases/lakeatlas-v1.0-r2/assets/lakeatlas-polygons.parquet) (asset)
- [lakeatlas-pour-points.parquet](releases/lakeatlas-v1.0-r2/assets/lakeatlas-pour-points.parquet) (asset)
- [thumbnail.png](releases/lakeatlas-v1.0-r2/display/thumbnail.png) (display_derivatives)
- [data-license.json](releases/lakeatlas-v1.0-r2/licenses/data-license.json) (data_license)
- [source-license.json](releases/lakeatlas-v1.0-r2/licenses/source-license.json) (source_license)
- [lakeatlas-polygons-field-dictionary.json](releases/lakeatlas-v1.0-r2/metadata/lakeatlas-polygons-field-dictionary.json) (field_dictionary)
- [lakeatlas-pour-points-field-dictionary.json](releases/lakeatlas-v1.0-r2/metadata/lakeatlas-pour-points-field-dictionary.json) (field_dictionary)
- [clean-rebuild.json](releases/lakeatlas-v1.0-r2/provenance/clean-rebuild.json) (supporting_files)
- [evidence-provenance.json](releases/lakeatlas-v1.0-r2/provenance/evidence-provenance.json) (supporting_files)
- [rebuild-environment.json](releases/lakeatlas-v1.0-r2/provenance/rebuild-environment.json) (supporting_files)
- [source-fidelity.json](releases/lakeatlas-v1.0-r2/provenance/source-fidelity.json) (supporting_files)
- [source-inspection.json](releases/lakeatlas-v1.0-r2/provenance/source-inspection.json) (supporting_files)
- [spatial-order-polygons-clean.json](releases/lakeatlas-v1.0-r2/provenance/spatial-order-polygons-clean.json) (supporting_files)
- [spatial-order-polygons-primary.json](releases/lakeatlas-v1.0-r2/provenance/spatial-order-polygons-primary.json) (supporting_files)
- [spatial-order-pour-points-clean.json](releases/lakeatlas-v1.0-r2/provenance/spatial-order-pour-points-clean.json) (supporting_files)
- [spatial-order-pour-points-primary.json](releases/lakeatlas-v1.0-r2/provenance/spatial-order-pour-points-primary.json) (supporting_files)
- [spatial-pruning-polygons-clean.json](releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-polygons-clean.json) (supporting_files)
- [spatial-pruning-polygons-primary.json](releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-polygons-primary.json) (supporting_files)
- [spatial-pruning-pour-points-clean.json](releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-pour-points-clean.json) (supporting_files)
- [spatial-pruning-pour-points-primary.json](releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-pour-points-primary.json) (supporting_files)
- [ATTRIBUTION.md](releases/lakeatlas-v1.0-r2/source/ATTRIBUTION.md) (supporting_files)
- [HydroATLAS_TechDoc_v10_1.pdf](releases/lakeatlas-v1.0-r2/source/HydroATLAS_TechDoc_v10_1.pdf) (supporting_files)
- [LakeATLAS_Catalog_v10.pdf](releases/lakeatlas-v1.0-r2/source/LakeATLAS_Catalog_v10.pdf) (supporting_files)
- [attribution.json](releases/lakeatlas-v1.0-r2/source/attribution.json) (source_attribution)
- [field-semantics.json](metadata/field-semantics-v1/field-semantics.json) (supplement)
- [README.md](metadata/field-semantics-v1/README.md) (supplement)
- [build_semantics.py](metadata/field-semantics-v1/build_semantics.py) (supplement)

## Display package

Display release: `display-v1`. The manifest is pinned at SHA-256 `ed70989525111682a294b6aadf1118a1ebfaefff863d645c6c805c5e8eafb70f`.
Display assets are separate immutable derivatives bound to this analytical release.
- [Display manifest](display/display-v1/manifest.json)
- [Lakeatlas Polygons PMTiles](display/display-v1/assets/lakeatlas-polygons.pmtiles) (1190009288 bytes; SHA-256 `394594baa10516b5bdea3841cdbbd7f8603412475059f846f5704386a72f71be`)
  - [Map style](display/display-v1/styles/lakeatlas-polygons.json)
- [Lakeatlas Pour Points PMTiles](display/display-v1/assets/lakeatlas-pour-points.pmtiles) (409205238 bytes; SHA-256 `68c28ecb4585378e0e729a5c72902214e935fa7645a6bef68372f0ec61bc4ffb`)
  - [Map style](display/display-v1/styles/lakeatlas-pour-points.json)

## Limitations

- Polygons and pour points are distinct producer layers, each retained separately.
- Attribute codes, scaling, spatial extent and aggregation rules must be interpreted using the versioned field-semantics supplement and producer documentation.
- The metadata supplement is separate from the unchanged immutable r2 analytical package.
- Live GEE counts and 522 sampled IDs per layer match. Both layers have numeric differences including integral GEE GDP values; the polygon layer also has three narrow source spikes absent spatially from GEE. Strict parity fails. No exhaustive GEE or independent scientific-accuracy claim.

Public hosting checks are bound in the canonical report. Scientific validation retains its documented scope.
