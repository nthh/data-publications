# Global Dam Watch v1.0 — barriers and reservoirs

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `gdw` (Global Dam Watch consensus v1.0 — barriers and reservoirs)
- Product ID: `global-dam-watch`
- Local publication status: `candidate`
- Local readiness: `blocked`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `blocked_source_access`
- Creation readiness: `false`
- Hosted: `false`

## Summary

Planned complete GeoParquet conversion of the final Global Dam Watch v1.0 barrier and reservoir layers, preserving scientific attributes and shared identifiers.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: Global Dam Watch consortium; final consensus database version 1.0, DOI 10.6084/m9.figshare.25988293.v1.
- License note: The producer-deposited final v1.0 DataCite record declares CC BY 4.0; preserve producer attribution and the release DOI.
- Temporal scope: Static consensus database release; individual dam and reservoir attributes have varying observation dates.

## Sources and DOI references

- [Producer source](https://gee-community-catalog.org/projects/gdw)

## Related datasets

- [Overture Base infrastructure and water](https://docs.overturemaps.org/guides/base/)
- [Producer source](https://docs.overturemaps.org/schema/reference/base/infrastructure/)
- [Producer source](https://docs.overturemaps.org/schema/reference/base/water/)
- [AquaScope GDW v1.0 selected-attribute barrier table](https://huggingface.co/datasets/Rekin226/aquascope-gauges/blob/main/context/dams/gdw_barriers.parquet)
- [Producer source](https://huggingface.co/datasets/Rekin226/aquascope-gauges/tree/main/context/dams)
- [Producer source](https://rachidouedraogo.com/aquascope/archive-layout/)

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

No release assets are included in this draft.

## Versioned display package

No versioned display package is recorded.

## Limitations

- No source archive has been acquired or converted: official Figshare API and direct-file requests return HTTP 403.
- Overture and AquaScope offer useful related access; the selected scope includes full original attributes and reservoir polygons beyond the reviewed AquaScope table.
- Planned formats and destinations are proposals, not available data.

## Source Cooperative route

Planned source proxy: `s3://nthh/global-dam-watch`. Check separate creation and hosting receipts for current state.

## Blockers

- Canonical publication review stage: blocked_source_access
- Source Cooperative account verification is not recorded
- canonical publication status is candidate, not prepared or published
