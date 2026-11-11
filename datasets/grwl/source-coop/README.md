# Global River Width from Landsat — summary network V01.02

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `grwl` (Global River Width from Landsat — simplified global river network V01.02)
- Product ID: `grwl`
- Local publication status: `deferred_source_quality`
- Local readiness: `blocked`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `withheld_source_geometry_errors`
- Creation readiness: `false`
- Hosted: `false`

## Summary

Historical simplified GRWL summary mirror, retained for comparison and withheld from publication because raw-source checks confirm artificial connecting edges. The separate grwl-raw product has complete analytical and display packages prepared from original observations.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: Allen and Pavelsky; Global River Width from Landsat.
- License note: CC BY 4.0. Retain Allen and Pavelsky attribution and the source data and paper citations.
- Temporal scope: Static Landsat-derived research product. The conversion date is not the observation date; no single observation interval is asserted.

## Sources and DOI references

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Dataset release](https://doi.org/10.5281/zenodo.18624542)
- [Producer source](https://gee-community-catalog.org/projects/grwl)
- [Original download](https://zenodo.org/api/records/18624542/files/GRWL_summaryStats_V01.02.zip/content)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

No release assets are included in this draft.

## Versioned display package

- [Display manifest](display/display-v1/manifest.json) (SHA-256 `a3deb37bc36ef5f16917ff668b8cbcf33d5b2bdd6477b106f26aa0be9dfc2523`)
- [GRWL river network PMTiles](display/display-v1/assets/grwl.pmtiles) (115384572 bytes; SHA-256 `7b56696bc08daa4ed512a02fd35017f913827d60f9dc1d8fba94b1f726ba5343`)
  - [Map style](display/display-v1/styles/grwl-width.json)

## Limitations

- The scope is the simplified summary network only; raw vectors, raster masks, tile indexes and RSSA basin products are excluded.
- The selected producer filename is V01.02 while its record metadata and GEE counterpart name V01.01. Exact source DOI, filename and checksums identify this release.
- PMTiles geometry is a display derivative; use GeoParquet for analysis.
- Raw-vector and water-mask inspection confirms geometry errors in source-summary rows 11839, 13164, 15394, 15397 and 15450. Straight connectors of 6.2 to 110.1 km join observations at tile exit/re-entry locations while the raw river follows a curved path. The prepared GeoParquet and PMTiles preserve these source errors. The five examples are not an exhaustive error inventory.
- Source row28938 crosses the dateline. Use display/display-v1/assets/grwl.pmtiles for maps; original release-bundled PMTiles are retained as historical evidence and contain a world-spanning rendering artifact. Analytical GeoParquet preserves the original longitude discontinuity.

## Source Cooperative route

Planned source proxy: `s3://nthh/grwl`. Check separate creation and hosting receipts for current state.

## Blockers

- Canonical local follow-up: The separate grwl-raw analytical and display packages are prepared. Keep this summary unchanged as historical source evidence.
- Canonical publication review stage: withheld_source_geometry_errors
- Source Cooperative account verification is not recorded
- canonical publication status is deferred_source_quality, not prepared or published

## Canonical local follow-up

- The separate grwl-raw analytical and display packages are prepared. Keep this summary unchanged as historical source evidence.
