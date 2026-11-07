# Global free-flowing rivers — connectivity assessment

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `free-flowing-rivers` (Mapping the world's free-flowing rivers — global river reach connectivity assessment)
- Product ID: `free-flowing-rivers`
- Local publication status: `published`
- Local readiness: `hosted_verified_pending_catalog_deployment`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `hosted_verified_pending_catalog_deployment`
- Creation readiness: `true`
- Hosted: `true`

## Summary

The complete river-reach network from Mapping the world’s free-flowing rivers, preserved in GeoParquet with all producer fields and source geometry. A separately versioned PMTiles layer provides zoom-dependent map display and source-ID attribute lookup.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: Grill, G., Lehner, B., Thieme, M. et al. (2019), Mapping the world’s free-flowing rivers, DOI 10.1038/s41586-019-1111-9. Original conversion evidence retains Folia attribution.
- License note: CC BY 4.0. Retain Grill, Lehner and coauthors’ attribution, source release identity and original field definitions.
- Temporal scope: Static assessment using source information assembled circa 2017; paper published in 2019.

## Sources and DOI references

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Producer source](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers)
- [Dataset release](https://doi.org/10.6084/m9.figshare.7688801.v1)
- [Dataset release](https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801)
- [Folia converter/host](https://folia.sh)
- [Original download](https://ndownloader.figshare.com/files/15090536)
- [Producer: Bernhard Lehner](https://orcid.org/0000-0003-3712-2581)
- [Producer: Günther Grill](https://orcid.org/0000-0003-4860-3575)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

- `ffr-reach-network-v1`: Free flowing river reaches, figshare v1 (application/vnd.apache.parquet)
- `ffr-reach-network-v1_fields`: ffr-reach-network-v1 field dictionary (application/json)
- `support-1`: Pinned figshare article metadata (application/json)
- `support-2`: Source archive and layer inspection (application/json)
- `support-3`: Producer field dictionary (application/json)
- `thumbnail`: Sampled display-only overview; not an analytic asset (image/png)

## Versioned display package

- [Display manifest](display/display-v1/manifest.json) (SHA-256 `2f7046f914ff49749dffd20df9c6c5010706710b881af915633766da4d91fb6d`)
- [Ffr Reaches PMTiles](display/display-v1/assets/ffr-reaches.pmtiles) (3570445458 bytes; SHA-256 `6e248eba5ecdf58ee28705a8f567be9497836f0a1c6c078b50327a1599ecdce3`)
  - [Map style](display/display-v1/styles/ffr-reaches.json)

## Limitations

- Reach connectivity indicators are model-derived research attributes, not a current observation of every barrier or river condition.
- Retained validation establishes conversion fidelity and reproducibility; it does not independently revalidate the scientific model.
- Live GEE count and all 521 sampled IDs match. A documented erosion-field alias, numeric precision and null/empty differences remain; five selected geometry diagnostics exceed 1 m, up to 2.877 m. Strict parity fails; original source values and geometry are retained.

## Source Cooperative route

Hosted product: `s3://nthh/free-flowing-rivers`. The published release is bound to a checksum-verified hosting report.
