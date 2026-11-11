# LakeATLAS v1.0 — global lake attributes and pour points

LakeATLAS lake polygons and pour points with hydro-environmental attributes in separate spatially ordered GeoParquet files, with a versioned field-semantics supplement. Separately versioned PMTiles provide map display for both layers and source-ID attribute lookup.

Observation and model-input dates vary by contributing attribute; use the producer catalog and field supplement for interpretation.

## Files

Use GeoParquet for analysis and PMTiles for maps. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [lakeatlas-polygons-v1.0.parquet](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.parquet) | 1.14 GB |
| [lakeatlas-polygons-v1.0.fields.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.fields.json) | 19.7 kB |
| [lakeatlas-pour-points-v1.0.parquet](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.parquet) | 283.78 MB |
| [lakeatlas-pour-points-v1.0.fields.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.fields.json) | 19.5 kB |
| [lakeatlas-polygons-v1.0.pmtiles](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.pmtiles) | 1.19 GB |
| [lakeatlas-polygons-v1.0.style.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.style.json) | 0.5 kB |
| [lakeatlas-pour-points-v1.0.pmtiles](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.pmtiles) | 409.21 MB |
| [lakeatlas-pour-points-v1.0.style.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.style.json) | 0.5 kB |
| [LICENSE.txt](https://data.source.coop/nthh/lakeatlas/LICENSE.txt) | 0.4 kB |
| [manifest-20261111.json](https://data.source.coop/nthh/lakeatlas/manifest-20261111.json) | 3.3 kB |
| [HydroATLAS_TechDoc_v10_1.pdf](https://data.source.coop/nthh/lakeatlas/HydroATLAS_TechDoc_v10_1.pdf) | 3.66 MB |
| [LakeATLAS_Catalog_v10.pdf](https://data.source.coop/nthh/lakeatlas/LakeATLAS_Catalog_v10.pdf) | 54.06 MB |

## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.parquet') LIMIT 5;
```

The matching `.style.json` file shows the PMTiles in a MapLibre viewer with the PMTiles protocol installed.

## Attribution and license

HydroSHEDS / HydroATLAS authors; Lehner, Messager, Korver and Linke (2022), DOI 10.1038/s41597-022-01425-z.

Mixed field-level terms: the producer catalog identifies CC BY 4.0 and ODbL 1.0 attributes. Retain the catalog, source attribution and original-source notices; do not describe the entire attribute table as uniformly CC BY 4.0.

Independently maintained by [nthh](https://source.coop/nthh).

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/s41597-022-01425-z)
- [Dataset release](https://doi.org/10.6084/m9.figshare.19312001.v1)
- [Producer technical documentation](https://ndownloader.figshare.com/files/35959532)
- [Producer attribute catalogue](https://ndownloader.figshare.com/files/35959535)
- [Original download](https://ndownloader.figshare.com/files/35959544)
- [Processor: nthh](https://source.coop/nthh/lakeatlas)
- [Producer: HydroSHEDS / HydroATLAS authors](https://www.hydrosheds.org/products/hydroatlas)

## Limitations

- Polygons and pour points are distinct producer layers, each retained separately.
- Attribute codes, scaling, spatial extent and aggregation rules must be interpreted using the versioned field-semantics supplement and producer documentation.
- The metadata supplement is separate from the unchanged immutable r2 analytical package.
- Live GEE counts and 522 sampled IDs per layer match. Both layers have numeric differences including integral GEE GDP values; the polygon layer also has three narrow source spikes absent spatially from GEE. Strict parity fails. No exhaustive GEE or independent scientific-accuracy claim.

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/lakeatlas) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/lakeatlas/collection.json)

Versioned filenames and checksum manifests identify the published data.
