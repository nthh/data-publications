# HydroLAKES v1.0 — global lake polygons

The complete HydroLAKES v1.0 polygon layer in spatially ordered GeoParquet, preserving producer fields and geometry for lake analysis and joins. A separately versioned PMTiles layer provides generalized map display and source-ID attribute lookup.

Static research release compiled from multiple shoreline sources; not a current inventory of lake conditions.

## Files

Use GeoParquet for analysis and PMTiles for maps. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [hydrolakes-polygons-v1.0.parquet](https://data.source.coop/nthh/hydrolakes/hydrolakes-polygons-v1.0.parquet) | 949.60 MB |
| [hydrolakes-polygons-v1.0.fields.json](https://data.source.coop/nthh/hydrolakes/hydrolakes-polygons-v1.0.fields.json) | 4.1 kB |
| [hydrolakes-polygons-v1.0.pmtiles](https://data.source.coop/nthh/hydrolakes/hydrolakes-polygons-v1.0.pmtiles) | 1.12 GB |
| [LICENSE.txt](https://data.source.coop/nthh/hydrolakes/LICENSE.txt) | 0.4 kB |
| [manifest-20261111.json](https://data.source.coop/nthh/hydrolakes/manifest-20261111.json) | 1.9 kB |
| [hydrolakes-polygons-v1.0-presentation-v2.style.json](https://data.source.coop/nthh/hydrolakes/hydrolakes-polygons-v1.0-presentation-v2.style.json) | 2.0 kB |
| [hydrolakes-preview-v2.png](https://data.source.coop/nthh/hydrolakes/hydrolakes-preview-v2.png) | 249.8 kB |
| [HydroLAKES_TechDoc_v10.pdf](https://data.source.coop/nthh/hydrolakes/HydroLAKES_TechDoc_v10.pdf) | 989.6 kB |

## Schema

[Column definitions in the catalog](https://nthh.github.io/data-publications/hydrolakes/collection.json) include names, storage types and descriptions. Use the field dictionaries and producer documentation above for units, coded values and limitations.


## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/hydrolakes/hydrolakes-polygons-v1.0.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/hydrolakes/hydrolakes-polygons-v1.0.parquet') LIMIT 5;
```

The `.style.json` files show the PMTiles in a MapLibre viewer with the PMTiles protocol installed. Preview images are generalized displays; they are not analytical geometry.

## Attribution and license

Lehner and Messager / HydroSHEDS. Cite Messager et al. (2016), DOI 10.1038/ncomms13603.

Producer license: CC BY 4.0. Retain attribution and technical-document notices, including the producer request concerning redistribution of the complete database in its original format. This product contains transformed GeoParquet.

Independently maintained by [nthh](https://source.coop/nthh).

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Original download](https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip)
- [Research paper](https://doi.org/10.1038/ncomms13603)
- [Producer source](https://gee-community-catalog.org/projects/hydrolakes)
- [Processor: nthh](https://source.coop/nthh/hydrolakes)
- [Producer: Lehner and Messager / HydroSHEDS](https://www.hydrosheds.org/products/hydrolakes)

## Limitations

- This release contains polygons; it does not include the separate HydroLAKES pour-point source layer.
- Spatial ordering and added bounding boxes preserve original attributes and WKB; local display queries do not establish public-host performance.
- Live GEE count and all 522 sampled IDs match. There are 508 null/empty lake-name differences, strict geometry failures and three narrow source spikes absent spatially from GEE. Source geometry is retained; no exhaustive GEE or independent scientific-accuracy claim.

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/hydrolakes) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/hydrolakes/collection.json)

Versioned filenames and checksum manifests identify the published data.
