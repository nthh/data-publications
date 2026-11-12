# Global river plastic inputs — Lebreton et al. (2017)

Modeled plastic inputs at global river outlets from the Lebreton et al. study, with analytical GeoParquet and a separate PMTiles display layer.

Historical model baseline: 2010; paper published in 2017. These are modeled estimates, not current measurements.

## Files

Use GeoParquet for analysis and PMTiles for maps. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [river-plastic-inputs-figshare-v6.parquet](https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.parquet) | 6.36 MB |
| [river-plastic-inputs-figshare-v6.pmtiles](https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.pmtiles) | 3.71 MB |
| [river-plastic-inputs-figshare-v6.fields.json](https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.fields.json) | 9.5 kB |
| [river-plastic-inputs-figshare-v6.quality.json](https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.quality.json) | 2.4 kB |
| [LICENSE.txt](https://data.source.coop/nthh/river-plastic-inputs/LICENSE.txt) | 0.3 kB |
| [manifest-20261111.json](https://data.source.coop/nthh/river-plastic-inputs/manifest-20261111.json) | 2.4 kB |
| [river-plastic-inputs-figshare-v6.style.json](https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.style.json) | 2.3 kB |
| [river-plastic-inputs-preview-v2.png](https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-preview-v2.png) | 198.9 kB |

## Schema

[Column definitions in the catalog](https://nthh.github.io/data-publications/river-plastic-inputs/collection.json) include names, storage types and descriptions. Use the field dictionaries and producer documentation above for units, coded values and limitations.


## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/river-plastic-inputs/river-plastic-inputs-figshare-v6.parquet') LIMIT 5;
```

The `.style.json` files show the PMTiles in a MapLibre viewer with the PMTiles protocol installed. Preview images are generalized displays; they are not analytical geometry.

## Attribution and license

Lebreton et al. (2017), River plastic emissions to the world’s oceans.

CC BY 4.0. Retain Lebreton et al. attribution and the Figshare v6 source citation.

Independently maintained by [nthh](https://source.coop/nthh).

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/ncomms15611)
- [Dataset release](https://doi.org/10.6084/m9.figshare.4725541.v6)
- [Producer source](https://gee-community-catalog.org/projects/plastic)
- [Original download](https://ndownloader.figshare.com/files/7714864)
- [Processor: nthh](https://source.coop/nthh/river-plastic-inputs)

## Limitations

- This is the Lebreton dataset, not the later Meijer et al. model.
- Preserve null estimates and coincident outlet records; their multiplicity is intentional.
- The historical full GEE capture replay matches all 53 attributes and nulls across 40,760 rows with the documented coincident-group contract; maximum point displacement is 0.3495 m. Fresh metadata/count match, but no fresh exhaustive feature capture was made. Strict coordinate parity remains failed.

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/river-plastic-inputs) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/river-plastic-inputs/collection.json)

Versioned filenames and checksum manifests identify the published data.

[Dataset query guidance](AGENTS.md).
