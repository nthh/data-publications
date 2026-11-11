# Global river plastic inputs — Lebreton et al. (2017)

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `river-plastic-inputs` (Global river plastic inputs — Lebreton et al. (2017))
- Product ID: `river-plastic-inputs`
- Local publication status: `published`
- Local readiness: `public_catalog_verified`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `public_catalog_verified`
- Creation readiness: `true`
- Hosted: `true`

## Summary

Modeled plastic inputs at global river outlets from the Lebreton et al. study, with analytical GeoParquet and a separate PMTiles display layer.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: Lebreton et al. (2017), River plastic emissions to the world’s oceans.
- License note: CC BY 4.0. Retain Lebreton et al. attribution and the Figshare v6 source citation.
- Temporal scope: Historical model baseline: 2010; paper published in 2017. These are modeled estimates, not current measurements.

## Sources and DOI references

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/ncomms15611)
- [Dataset release](https://doi.org/10.6084/m9.figshare.4725541.v6)
- [Producer source](https://gee-community-catalog.org/projects/plastic)
- [Original download](https://ndownloader.figshare.com/files/7714864)
- [Processor: nthh](https://source.coop/nthh/river-plastic-inputs)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

- `data`: Complete analytic data, GeoParquet 1.1 (application/vnd.apache.parquet)
- `original`: Original Figshare v6 shapefile archive (application/zip)
- `quality`: Original missing values and encoding (application/json)
- `schema`: Field dictionary (application/json)
- `style-annual-input`: Annual midpoint input style (application/vnd.mapbox.style+json)
- `thumbnail`: Annual midpoint input map (image/png)
- `tiles`: River input display tiles (application/vnd.pmtiles)

## Versioned display package

No versioned display package is recorded.

## Limitations

- This is the Lebreton dataset, not the later Meijer et al. model.
- Preserve null estimates and coincident outlet records; their multiplicity is intentional.
- The historical full GEE capture replay matches all 53 attributes and nulls across 40,760 rows with the documented coincident-group contract; maximum point displacement is 0.3495 m. Fresh metadata/count match, but no fresh exhaustive feature capture was made. Strict coordinate parity remains failed.

## Source Cooperative route

Hosted product: `s3://nthh/river-plastic-inputs`. The published release is bound to a checksum-verified hosting report.
