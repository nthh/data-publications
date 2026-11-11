# Global River Width from Landsat — raw vector observations V01.01

Complete GRWL V01.01 raw vector observations in lossless GeoParquet, with one separately versioned zoom 0–12 PMTiles display. Zooms 0–7 show selected widest original width observations with source IDs; zooms 8–12 preserve detailed source geometry and widths. All 64,572,998 observations and ten original DBF fields remain in GeoParquet. Complete source comparison, analytical rebuild, full global overview validation, exact detailed-tile preservation, clean regional replay and all 20 browser cases passed.

**Validated hosted release:** `raw-v01.01-local-r1`. The canonical record binds the public Source Cooperative package and its completed hosting checks.

## Scope and formats

Detailed producer GRWL vector observations with each source record, part and coordinate retained. Records are kept separate; segmentID is tile-local. width_m=1 means unknown width, and width_valid marks usable measurements. Static producer release derived from Landsat observations; source observation dates vary. This is not a current river-width observation or a time series.

Formats: `application/json`, `application/vnd.apache.parquet`, `application/vnd.pmtiles`, `image/png`.

## Producer, source, and license

- Producer attribution: Allen and Pavelsky (2018), Global extent of rivers and streams, Science 361(6402), 585–588, DOI 10.1126/science.aat0636; source product GRWL_vector_V01.01.
- License: Producer license: CC BY 4.0. Preserve producer attribution and cite Allen and Pavelsky (2018), DOI 10.1126/science.aat0636.
- Temporal scope: Static producer release derived from Landsat observations with varying source dates; not current river conditions or a time series.

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Dataset release](https://doi.org/10.5281/zenodo.18624542)
- [Processor: nthh](https://source.coop/nthh/grwl-raw)
- [Original download](https://zenodo.org/api/records/18624542/files/GRWL_vector_V01.01.zip/content)
- [Dataset release](https://zenodo.org/records/18624542)

## Release files

- [grwl-raw-observations.parquet](releases/raw-v01.01-local-r1/assets/grwl-raw-observations.parquet) (asset)
- [thumbnail.png](releases/raw-v01.01-local-r1/display/thumbnail.png) (display_derivatives)
- [data-license.json](releases/raw-v01.01-local-r1/licenses/data-license.json) (data_license)
- [source-license.json](releases/raw-v01.01-local-r1/licenses/source-license.json) (source_license)
- [grwl-raw-observations-field-dictionary.json](releases/raw-v01.01-local-r1/metadata/grwl-raw-observations-field-dictionary.json) (field_dictionary)
- [attribution.json](releases/raw-v01.01-local-r1/source/attribution.json) (source_attribution)

## Display package

Display release: `raw-v01.01-display-r3`. The manifest is pinned at SHA-256 `0910adf27da9265a9f02fb2c71f2d5b4a6e90f55330ae6d4a2d24c782d231915`.
Display assets are separate immutable derivatives bound to this analytical release.
- [Display manifest](display/raw-v01.01-display-r3/manifest.json)
- [GRWL raw width observations at every zoom PMTiles](display/raw-v01.01-display-r3/assets/grwl-raw.pmtiles) (3190539066 bytes; SHA-256 `8b7c1061bd42845a4747d53e2149ad4c0682b3066478c7d367bbab046843dd60`)
  - [Map style](display/raw-v01.01-display-r3/styles/width.json)

## Limitations

- All 64,572,998 source records passed exact independent source comparison and a byte-identical clean analytical rebuild. Complete uploaded bytes and anonymous hosting, range, CORS, subset-query and browser checks passed.
- Raw observations are separate source records and short parts, not a connected river centerline network. Records are never joined by segmentID or segmentInd.
- width_m value 1 is an unknown-width sentinel; width_valid indicates usable width without altering width_m.
- The release excludes masks, tile index, and RSSA basin supplement.
- PMTiles is a quantized display derivative. Zooms 0–7 select the widest valid original observation per screen-scale cell, retaining its source ID and anchor. Symbols are exaggerated and capped, not averages or riverbanks. Zooms 8–12 retain the original detailed tile payloads.
- All 64,572,998 source records were independently checked for overview winner selection; every selected table row and all 26,060,623 encoded point placements in 4,439 overview tiles passed. All 588,355 detailed compressed tiles exactly match r2. The same 304 enumerated 0.0013–2.93 m source fragments collapse at z12 and remain preserved in GeoParquet, with no new detail omissions.
- Twenty fixed browser cases cover Mississippi z0–12, Amazon and the dateline, including one exact-ID lookup of all fourteen source attributes at z7. The clean byte replay is regional. The viewer retains its existing non-wrapping world edge; global scientific accuracy is not established. Hosted browser checks cover the same twenty fixed views.
- Live raw-V01.01 GEE count and all 512 sampled compound keys match; all 5,120 source attribute cells are exact. Selected mixed geometry diagnostics are below 0.340 m, but strict geometry parity fails. No exhaustive GEE, topology-preservation or independent scientific-accuracy claim.
- The Parquet metadata footer is 19,783,655 bytes. The tested cold exact-ID browser lookup transferred 20,941,975 bytes, including that footer; this is one fixed-view measurement, not a universal query-cost guarantee.

## Related datasets

- [Global River Width from Landsat — simplified global river network V01.02](https://gee-community-catalog.org/projects/grwl/)
- [Producer source](https://zenodo.org/records/18624542)

Public hosting checks are bound in the canonical report. Scientific validation retains its documented scope.
