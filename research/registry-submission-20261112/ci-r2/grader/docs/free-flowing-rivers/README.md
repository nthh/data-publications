# Global free-flowing rivers — connectivity assessment

The complete river-reach network from Mapping the world’s free-flowing rivers, preserved in GeoParquet with all producer fields and source geometry. A separately versioned PMTiles layer provides zoom-dependent map display and source-ID attribute lookup.

Static assessment using source information assembled circa 2017; paper published in 2019.

## Files

Use GeoParquet for analysis and PMTiles for maps. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [free-flowing-rivers-v1.parquet](https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-v1.parquet) | 887.13 MB |
| [free-flowing-rivers-v1.fields.json](https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-v1.fields.json) | 12.3 kB |
| [free-flowing-rivers-v1.pmtiles](https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-v1.pmtiles) | 3.57 GB |
| [LICENSE.txt](https://data.source.coop/nthh/free-flowing-rivers/LICENSE.txt) | 0.3 kB |
| [manifest-20261111.json](https://data.source.coop/nthh/free-flowing-rivers/manifest-20261111.json) | 2.0 kB |
| [free-flowing-rivers-v1-presentation-v2.style.json](https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-v1-presentation-v2.style.json) | 1.9 kB |
| [free-flowing-rivers-preview-v2.png](https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-preview-v2.png) | 509.3 kB |

## Schema

[Column definitions in the catalog](https://nthh.github.io/data-publications/free-flowing-rivers/collection.json) include names, storage types and descriptions. Use the field dictionaries and producer documentation above for units, coded values and limitations.


## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-v1.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/free-flowing-rivers/free-flowing-rivers-v1.parquet') LIMIT 5;
```

The `.style.json` files show the PMTiles in a MapLibre viewer with the PMTiles protocol installed. Preview images are generalized displays; they are not analytical geometry.

## Attribution and license

Grill, G., Lehner, B., Thieme, M. et al. (2019), Mapping the world’s free-flowing rivers, DOI 10.1038/s41586-019-1111-9.

CC BY 4.0. Retain Grill, Lehner and coauthors’ attribution, source release identity and original field definitions.

Independently maintained by [nthh](https://source.coop/nthh).

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Producer source](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers)
- [Dataset release](https://doi.org/10.6084/m9.figshare.7688801.v1)
- [Dataset release](https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801)
- [Original download](https://ndownloader.figshare.com/files/15090536)
- [Producer: Bernhard Lehner](https://orcid.org/0000-0003-3712-2581)
- [Producer: Günther Grill](https://orcid.org/0000-0003-4860-3575)
- [Processor: nthh](https://source.coop/nthh/free-flowing-rivers)

## Limitations

- Reach connectivity indicators are model-derived research attributes, not a current observation of every barrier or river condition.
- Retained validation establishes conversion fidelity and reproducibility; it does not independently revalidate the scientific model.
- Live GEE count and all 521 sampled IDs match. A documented erosion-field alias, numeric precision and null/empty differences remain; five selected geometry diagnostics exceed 1 m, up to 2.877 m. Strict parity fails; original source values and geometry are retained.

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/free-flowing-rivers) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/free-flowing-rivers/collection.json)

Versioned filenames and checksum manifests identify the published data.

[Dataset query guidance](AGENTS.md).
