# HydroLAKES v1.0 — global lake polygons

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `hydrolakes` (HydroLAKES v1.0: Polygons)
- Product ID: `hydrolakes`
- Local publication status: `published`
- Local readiness: `public_catalog_verified`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `public_catalog_verified`
- Creation readiness: `true`
- Hosted: `true`

## Summary

The complete HydroLAKES v1.0 polygon layer in spatially ordered GeoParquet, preserving producer fields and geometry for lake analysis and joins. A separately versioned PMTiles layer provides generalized map display and source-ID attribute lookup.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: Lehner and Messager / HydroSHEDS. Cite Messager et al. (2016), DOI 10.1038/ncomms13603. Original conversion evidence retains Folia attribution.
- License note: Producer license: CC BY 4.0. Retain attribution and technical-document notices, including the producer request concerning redistribution of the complete database in its original format. This product contains transformed GeoParquet.
- Temporal scope: Static research release compiled from multiple shoreline sources; not a current inventory of lake conditions.

## Sources and DOI references

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Original download](https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip)
- [Research paper](https://doi.org/10.1038/ncomms13603)
- [Folia converter/host](https://folia.sh)
- [Producer source](https://gee-community-catalog.org/projects/hydrolakes)
- [Producer: Lehner and Messager / HydroSHEDS](https://www.hydrosheds.org/products/hydrolakes)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

- `hydrolakes-polygons`: HydroLAKES v1.0 polygons (application/vnd.apache.parquet)
- `hydrolakes-polygons_fields`: hydrolakes-polygons field dictionary (application/json)
- `support-1`: HydroLAKES Technical Documentation v1.0 (application/pdf)
- `support-10`: Clean rebuild fixed-window bbox pruning report (application/json)
- `support-2`: Producer technical document identity (application/json)
- `support-3`: Complete independent source fidelity report (application/json)
- `support-4`: Clean raw conversion rebuild report (application/json)
- `support-5`: Source archive cache eviction receipt (application/json)
- `support-6`: Evidence original hashes and portable copy hashes (application/json)
- `support-7`: Retained spatial-order full fidelity report (application/json)
- `support-8`: Clean rebuild spatial-order full fidelity report (application/json)
- `support-9`: Retained fixed-window bbox pruning report (application/json)
- `thumbnail`: Sampled display-only overview; not an analytic asset (image/png)

## Versioned display package

- [Display manifest](display/display-v1/manifest.json) (SHA-256 `f3dbb0d87553162a6b2a91172626eeecca9985fb8df54685ee64924ca826d841`)
- [Hydrolakes Polygons PMTiles](display/display-v1/assets/hydrolakes-polygons.pmtiles) (1122881121 bytes; SHA-256 `2fc61a8257322bed3c71f86e3be92ed4835023bbb23f80bc9b2bb5167cb19d46`)
  - [Map style](display/display-v1/styles/hydrolakes-polygons.json)

## Limitations

- This release contains polygons; it does not include the separate HydroLAKES pour-point source layer.
- Spatial ordering and added bounding boxes preserve original attributes and WKB; local display queries do not establish public-host performance.
- Live GEE count and all 522 sampled IDs match. There are 508 null/empty lake-name differences, strict geometry failures and three narrow source spikes absent spatially from GEE. Source geometry is retained; no exhaustive GEE or independent scientific-accuracy claim.

## Source Cooperative route

Hosted product: `s3://nthh/hydrolakes`. The published release is bound to a checksum-verified hosting report.
