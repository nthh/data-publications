# Global River Width from Landsat — raw vector observations V01.01

Complete GRWL V01.01 raw vector observations in lossless GeoParquet, with one separately versioned zoom 0–12 PMTiles display. Zooms 0–7 show selected widest original width observations with source IDs; zooms 8–12 preserve detailed source geometry and widths. All 64,572,998 observations and ten original DBF fields remain in GeoParquet. Complete source comparison, analytical rebuild, full global overview validation, exact detailed-tile preservation, clean regional replay and all 20 browser cases passed.

Static producer release derived from Landsat observations with varying source dates; not current river conditions or a time series.

## Files

Use GeoParquet for analysis and PMTiles for maps. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [grwl-raw-v01.01.parquet](https://data.source.coop/nthh/grwl-raw/grwl-raw-v01.01.parquet) | 5.53 GB |
| [grwl-raw-v01.01.fields.json](https://data.source.coop/nthh/grwl-raw/grwl-raw-v01.01.fields.json) | 1.3 kB |
| [grwl-raw-v01.01.pmtiles](https://data.source.coop/nthh/grwl-raw/grwl-raw-v01.01.pmtiles) | 3.19 GB |
| [grwl-raw-v01.01.style.json](https://data.source.coop/nthh/grwl-raw/grwl-raw-v01.01.style.json) | 10.4 kB |
| [LICENSE.txt](https://data.source.coop/nthh/grwl-raw/LICENSE.txt) | 0.4 kB |
| [manifest-20261111.json](https://data.source.coop/nthh/grwl-raw/manifest-20261111.json) | 2.0 kB |

## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/grwl-raw/grwl-raw-v01.01.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/grwl-raw/grwl-raw-v01.01.parquet') LIMIT 5;
```

The matching `.style.json` file shows the PMTiles in a MapLibre viewer with the PMTiles protocol installed.

## Attribution and license

Allen and Pavelsky (2018), Global extent of rivers and streams, Science 361(6402), 585–588, DOI 10.1126/science.aat0636; source product GRWL_vector_V01.01.

Producer license: CC BY 4.0. Preserve producer attribution and cite Allen and Pavelsky (2018), DOI 10.1126/science.aat0636.

Independently maintained by [nthh](https://source.coop/nthh).

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Dataset release](https://doi.org/10.5281/zenodo.18624542)
- [Processor: nthh](https://source.coop/nthh/grwl-raw)
- [Original download](https://zenodo.org/api/records/18624542/files/GRWL_vector_V01.01.zip/content)
- [Dataset release](https://zenodo.org/records/18624542)

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

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/grwl-raw) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/grwl-raw/collection.json)

Existing versioned download URLs remain available. The root files provide the current consumer layout.
