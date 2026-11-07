# Global free-flowing rivers — connectivity assessment

The complete river-reach network from Mapping the world’s free-flowing rivers, preserved in GeoParquet with all producer fields and source geometry. A separately versioned PMTiles layer provides zoom-dependent map display and source-ID attribute lookup.

**Validated hosted release:** `figshare-v1-local-r2`. The canonical record binds the public Source Cooperative package and its completed hosting checks.

## Scope and formats

Analytic GeoParquet conversion of the full global free-flowing river reach network from the pinned 2019 figshare v1 source. Original source fields and WKB geometries, nulls, row order, and record multiplicity are preserved. Added columns expose the producer-stream row ordinal and per-feature EPSG:4326 bounds. This release does not assess scientific validity or update the source assessment.

Formats: `application/json`, `application/vnd.apache.parquet`, `application/vnd.pmtiles`, `image/png`.

## Producer, source, and license

- Producer attribution: Grill, G., Lehner, B., Thieme, M. et al. (2019), Mapping the world’s free-flowing rivers, DOI 10.1038/s41586-019-1111-9. Original conversion evidence retains Folia attribution.
- License: CC BY 4.0. Retain Grill, Lehner and coauthors’ attribution, source release identity and original field definitions.
- Temporal scope: Static assessment using source information assembled circa 2017; paper published in 2019.

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Producer source](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers)
- [Dataset release](https://doi.org/10.6084/m9.figshare.7688801.v1)
- [Dataset release](https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801)
- [Folia converter/host](https://folia.sh)
- [Original download](https://ndownloader.figshare.com/files/15090536)
- [Producer: Bernhard Lehner](https://orcid.org/0000-0003-3712-2581)
- [Producer: Günther Grill](https://orcid.org/0000-0003-4860-3575)

## Release files

- [ffr-reach-network-v1.parquet](releases/figshare-v1-local-r2/assets/ffr-reach-network-v1.parquet) (asset)
- [thumbnail.png](releases/figshare-v1-local-r2/display/thumbnail.png) (display_derivatives)
- [data-license.json](releases/figshare-v1-local-r2/licenses/data-license.json) (data_license)
- [source-license.json](releases/figshare-v1-local-r2/licenses/source-license.json) (source_license)
- [ffr-reach-network-v1-field-dictionary.json](releases/figshare-v1-local-r2/metadata/ffr-reach-network-v1-field-dictionary.json) (field_dictionary)
- [attribution.json](releases/figshare-v1-local-r2/source/attribution.json) (source_attribution)
- [source-field-dictionary.json](releases/figshare-v1-local-r2/source/source-field-dictionary.json) (supporting_files)
- [source-inspection.json](releases/figshare-v1-local-r2/source/source-inspection.json) (supporting_files)
- [source-metadata.json](releases/figshare-v1-local-r2/source/source-metadata.json) (supporting_files)

## Display package

Display release: `display-v1`. The manifest is pinned at SHA-256 `2f7046f914ff49749dffd20df9c6c5010706710b881af915633766da4d91fb6d`.
Display assets are separate immutable derivatives bound to this analytical release.
- [Display manifest](display/display-v1/manifest.json)
- [Ffr Reaches PMTiles](display/display-v1/assets/ffr-reaches.pmtiles) (3570445458 bytes; SHA-256 `6e248eba5ecdf58ee28705a8f567be9497836f0a1c6c078b50327a1599ecdce3`)
  - [Map style](display/display-v1/styles/ffr-reaches.json)

## Limitations

- Reach connectivity indicators are model-derived research attributes, not a current observation of every barrier or river condition.
- Retained validation establishes conversion fidelity and reproducibility; it does not independently revalidate the scientific model.
- Live GEE count and all 521 sampled IDs match. A documented erosion-field alias, numeric precision and null/empty differences remain; five selected geometry diagnostics exceed 1 m, up to 2.877 m. Strict parity fails; original source values and geometry are retained.

Public hosting checks are bound in the canonical report. Scientific validation retains its documented scope.
