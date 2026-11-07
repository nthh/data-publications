# SWOT Prior Lake Database — scientific v2.03

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `swot_prior_lake_database` (SWOT Prior Lake Database v2.03)
- Product ID: `swot-prior-lake`
- Local publication status: `candidate`
- Local readiness: `blocked`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `metadata_qualified_sample_blocked_by_disk`
- Creation readiness: `false`
- Hosted: `false`

## Summary

Planned conversion of the scientific SWOT prior-lake reference database to GeoParquet spatial tables and Parquet auxiliary tables while preserving identifiers and relationships.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: CNES / Theia and the SWOT Prior Lake Database producers; scientific PLD version 2.03, Hydroweb.next.
- License note: The current CNES/Theia producer STAC collection declares ETALAB 2.0. Preserve attribution and source notices with the conversion.
- Temporal scope: Scientific reference database edition v2.03; not a time series of SWOT satellite measurements.

## Sources and DOI references

- [Producer source](https://hydroweb.next.theia-land.fr/api/catalog/stac/collections/SWOT_PRIOR_LAKE_DATABASE)
- [Producer source](https://hydroweb.next.theia-land.fr/catalog/details/SWOT_PRIOR_LAKE_DATABASE)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

No release assets are included in this draft.

## Versioned display package

No versioned display package is recorded.

## Limitations

- The selected inventory has 61 v2.03 SQLite tiles totaling 29,990,277,120 provider-declared bytes; v2.02 and Light/Geometries variants are excluded.
- Anonymous metadata and a tiny range read succeeded; a complete tile and its SQLite schema have not been validated.
- Source acquisition remains gated by disk space and a measured streaming/retention plan; no converted release exists.

## Source Cooperative route

Planned source proxy: `s3://nthh/swot-prior-lake`. Check separate creation and hosting receipts for current state.

## Blockers

- Canonical publication review stage: metadata_qualified_sample_blocked_by_disk
- Source Cooperative account verification is not recorded
- canonical publication status is candidate, not prepared or published
