# LakeATLAS v1.0 — global lake attributes and pour points

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `lakeatlas` (HydroATLAS LakeATLAS v1.0 — global hydro-environmental lake attributes)
- Product ID: `lakeatlas`
- Local publication status: `published`
- Local readiness: `public_catalog_verified`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `public_catalog_verified`
- Creation readiness: `true`
- Hosted: `true`

## Summary

LakeATLAS lake polygons and pour points with hydro-environmental attributes in separate spatially ordered GeoParquet files, with a versioned field-semantics supplement. Separately versioned PMTiles provide map display for both layers and source-ID attribute lookup.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: HydroSHEDS / HydroATLAS authors; Lehner, Messager, Korver and Linke (2022), DOI 10.1038/s41597-022-01425-z. Original conversion evidence retains Folia attribution.
- License note: Mixed field-level terms: the producer catalog identifies CC BY 4.0 and ODbL 1.0 attributes. Retain the catalog, source attribution and original-source notices; do not describe the entire attribute table as uniformly CC BY 4.0.
- Temporal scope: Observation and model-input dates vary by contributing attribute; use the producer catalog and field supplement for interpretation.

## Sources and DOI references

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/s41597-022-01425-z)
- [Dataset release](https://doi.org/10.6084/m9.figshare.19312001.v1)
- [Folia converter/host](https://folia.sh)
- [Producer technical documentation](https://ndownloader.figshare.com/files/35959532)
- [Producer attribute catalogue](https://ndownloader.figshare.com/files/35959535)
- [Original download](https://ndownloader.figshare.com/files/35959544)
- [Producer: HydroSHEDS / HydroATLAS authors](https://www.hydrosheds.org/products/hydroatlas)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

- [field-semantics.json](../metadata-enhancements/v1/field-semantics.json) → `metadata/field-semantics-v1/field-semantics.json`
- [README.md](../metadata-enhancements/v1/README.md) → `metadata/field-semantics-v1/README.md`
- [build_semantics.py](../metadata-enhancements/v1/build_semantics.py) → `metadata/field-semantics-v1/build_semantics.py`

## Snapshot assets

- `lakeatlas-polygons`: LakeATLAS v1.0 polygons (application/vnd.apache.parquet)
- `lakeatlas-polygons_fields`: lakeatlas-polygons field dictionary (application/json)
- `lakeatlas-pour-points`: LakeATLAS v1.0 pour points (application/vnd.apache.parquet)
- `lakeatlas-pour-points_fields`: lakeatlas-pour-points field dictionary (application/json)
- `support-1`: HydroATLAS technical documentation v1.0 (application/pdf)
- `support-10`: Pour-point spatial-order full source comparison (application/json)
- `support-11`: Polygon fixed-window bbox pruning validation (application/json)
- `support-12`: Pour-point fixed-window bbox pruning validation (application/json)
- `support-13`: Clean polygon spatial rebuild and full fidelity comparison (application/json)
- `support-14`: Clean pour-point spatial rebuild and full fidelity comparison (application/json)
- `support-15`: Clean polygon fixed-window bbox pruning validation (application/json)
- `support-16`: Clean pour-point fixed-window bbox pruning validation (application/json)
- `support-2`: LakeATLAS v1.0 catalog and attribute license dictionary (application/pdf)
- `support-3`: Pinned source archive and layer inspection (application/json)
- `support-4`: Clean rebuild interpreter, locked environment and workflow revisions (application/json)
- `support-5`: Source attribution and field-level licensing notice (text/markdown)
- `support-6`: Original and path-redacted portable report hashes (application/json)
- `support-7`: Bound source conversion fidelity report (application/json)
- `support-8`: Clean raw and final spatial rebuild report (application/json)
- `support-9`: Polygon spatial-order full source comparison (application/json)
- `thumbnail`: Sampled display-only overview; not an analytic asset (image/png)

## Versioned display package

- [Display manifest](display/display-v1/manifest.json) (SHA-256 `ed70989525111682a294b6aadf1118a1ebfaefff863d645c6c805c5e8eafb70f`)
- [Lakeatlas Polygons PMTiles](display/display-v1/assets/lakeatlas-polygons.pmtiles) (1190009288 bytes; SHA-256 `394594baa10516b5bdea3841cdbbd7f8603412475059f846f5704386a72f71be`)
  - [Map style](display/display-v1/styles/lakeatlas-polygons.json)
- [Lakeatlas Pour Points PMTiles](display/display-v1/assets/lakeatlas-pour-points.pmtiles) (409205238 bytes; SHA-256 `68c28ecb4585378e0e729a5c72902214e935fa7645a6bef68372f0ec61bc4ffb`)
  - [Map style](display/display-v1/styles/lakeatlas-pour-points.json)

## Limitations

- Polygons and pour points are distinct producer layers, each retained separately.
- Attribute codes, scaling, spatial extent and aggregation rules must be interpreted using the versioned field-semantics supplement and producer documentation.
- The metadata supplement is separate from the unchanged immutable r2 analytical package.
- Live GEE counts and 522 sampled IDs per layer match. Both layers have numeric differences including integral GEE GDP values; the polygon layer also has three narrow source spikes absent spatially from GEE. Strict parity fails. No exhaustive GEE or independent scientific-accuracy claim.

## Source Cooperative route

Hosted product: `s3://nthh/lakeatlas`. The published release is bound to a checksum-verified hosting report.
