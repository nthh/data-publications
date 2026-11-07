# Global river plastic inputs — Lebreton et al. (2017)

Modeled plastic inputs at global river outlets from the Lebreton et al. study, with analytical GeoParquet and a separate PMTiles display layer.

**Validated hosted release:** `figshare-v6-r2`. The canonical record binds the public Source Cooperative package and its completed hosting checks.

## Scope and formats

A global model of plastic inputs from rivers into the ocean, published by Lebreton et al. in 2017. This static release preserves the 40,760 river input locations and all 53 numeric attributes in the original Figshare v6 shapefile. Estimates represent the 2010 model baseline; they are not current measurements. This is distinct from the later Meijer et al. 2021 model.

Formats: `application/json`, `application/vnd.apache.parquet`, `application/vnd.mapbox.style+json`, `application/vnd.pmtiles`, `application/zip`, `image/png`.

## Producer, source, and license

- Producer attribution: Lebreton et al. (2017), River plastic emissions to the world’s oceans. Original conversion evidence retains Folia attribution.
- License: CC BY 4.0. Retain Lebreton et al. attribution and the Figshare v6 source citation.
- Temporal scope: Historical model baseline: 2010; paper published in 2017. These are modeled estimates, not current measurements.

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/ncomms15611)
- [Dataset release](https://doi.org/10.6084/m9.figshare.4725541.v6)
- [Folia converter/host](https://folia.sh)
- [Producer source](https://gee-community-catalog.org/projects/plastic)
- [Original download](https://ndownloader.figshare.com/files/7714864)

## Release files

- [AGENTS.md](releases/figshare-v6-r2/AGENTS.md) (asset)
- [LICENSE.txt](releases/figshare-v6-r2/LICENSE.txt) (asset)
- [README.md](releases/figshare-v6-r2/README.md) (asset)
- [catalog.json](releases/figshare-v6-r2/catalog.json) (asset)
- [dataset.yaml](releases/figshare-v6-r2/dataset.yaml) (asset)
- [AGENTS.md](releases/figshare-v6-r2/river-plastic-inputs/AGENTS.md) (asset)
- [README.md](releases/figshare-v6-r2/river-plastic-inputs/README.md) (asset)
- [collection.json](releases/figshare-v6-r2/river-plastic-inputs/collection.json) (asset)
- [quality.json](releases/figshare-v6-r2/river-plastic-inputs/quality.json) (asset)
- [river-plastic-inputs.parquet](releases/figshare-v6-r2/river-plastic-inputs/river-plastic-inputs.parquet) (asset)
- [river-plastic-inputs.pmtiles](releases/figshare-v6-r2/river-plastic-inputs/river-plastic-inputs.pmtiles) (asset)
- [schema.json](releases/figshare-v6-r2/river-plastic-inputs/schema.json) (asset)
- [annual-input.json](releases/figshare-v6-r2/river-plastic-inputs/styles/annual-input.json) (asset)
- [thumbnail.png](releases/figshare-v6-r2/river-plastic-inputs/thumbnail.png) (asset)

## Display package

No versioned display package is recorded.

## Limitations

- This is the Lebreton dataset, not the later Meijer et al. model.
- Preserve null estimates and coincident outlet records; their multiplicity is intentional.
- The historical full GEE capture replay matches all 53 attributes and nulls across 40,760 rows with the documented coincident-group contract; maximum point displacement is 0.3495 m. Fresh metadata/count match, but no fresh exhaustive feature capture was made. Strict coordinate parity remains failed.

Public hosting checks are bound in the canonical report. Scientific validation retains its documented scope.
