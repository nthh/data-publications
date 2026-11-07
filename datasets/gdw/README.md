# Global Dam Watch consensus v1.0

Selected for local preparation: the complete barrier-point and reservoir-polygon layers, all producer attributes and shared identifiers. No GDW source archive has been downloaded or converted. Official Figshare article, API, bundle and direct-file requests returned HTTP 403 on 1 November 2026; the user independently reported the same browser failure.

The exact release is [10.6084/m9.figshare.25988293.v1](https://doi.org/10.6084/m9.figshare.25988293.v1). The [producer-deposited metadata](https://api.datacite.org/dois/10.6084%2Fm9.figshare.25988293.v1) names two equivalent-format ZIP representations and declares CC BY 4.0. Its 127,938,795-byte size is the release aggregate, not the selected archive size. The selected Shapefile ZIP is [file 47913754](https://ndownloader.figshare.com/files/47913754), identified in AquaScope's public acquisition code; its per-file size and checksum remain unverified.

Overture supplies useful map features but does not establish the complete GDW scientific product. AquaScope already hosts a 1,514,458-byte Parquet with 41,145 barrier rows and 16 selected columns. Two HTTP range reads of its footer verified the row count, one row group, latitude/longitude columns and absence of geometry/GeoParquet metadata. Its published directory contains no reservoir layer. Reuse that table when those selected attributes suffice; a complete GDW conversion would add the original reservoir geometries, full attributes and validated relationships.

Once the official source is accessible: acquire and checksum-pin the final v1.0 archive, verify its technical documentation and full schema, then preserve and validate all 41,145 barriers and 35,295 reservoir polygons. Legitimate barriers without a reservoir polygon must remain. JRC's `v1_delta` is a different edition and is not a source substitute. No current output, prepared status or registry submission is claimed.

The [dated qualification/readiness report](../../research/gdw-swot-preparation-20261101/README.md) links the exact requests, footer metadata and precommitted acceptance criteria. Canonical facts and comparisons live in [dataset.yaml](dataset.yaml).

<!-- related-datasets:start -->

## Related datasets

Generated from `related_datasets` in [dataset.yaml](dataset.yaml). These references describe alternatives and complementary uses; they do not add datasets to the processing queue. The comparisons are based on the cited documentation, not an equivalence or accuracy benchmark.

### [Overture Base infrastructure and water](<https://docs.overturemaps.org/guides/base/>)

- **Relationship:** Alternative. Generic map features for dams, barriers and water bodies.
- **Coverage:** Global mapped coverage; completeness differs by source.
- **Formats:** GeoParquet
- **Access:** Public Overture releases; follow ODbL attribution requirements.
- **Comparison:** OSM-derived features and raw source tags can cover some of the same objects. The documented schema does not supply GDW scientific attributes, paired reservoir relation or its shared IDs. No byte/feature-level equivalence test was performed.
- **Reviewed:** 2026-11-01. **Sources:** [Overture Base provenance](<https://docs.overturemaps.org/guides/base/>), [Infrastructure schema](<https://docs.overturemaps.org/schema/reference/base/infrastructure/>), [Water schema](<https://docs.overturemaps.org/schema/reference/base/water/>).

### [AquaScope GDW v1.0 selected-attribute barrier table](<https://huggingface.co/datasets/Rekin226/aquascope-gauges/blob/main/context/dams/gdw_barriers.parquet>)

- **Relationship:** Derived product. Reuse a compact public barrier table when its selected attributes and point coordinates meet the need.
- **Coverage:** Global barrier rows as declared by the mirror; source completeness not independently reconciled.
- **Formats:** Parquet, CSV.gz per cell
- **Access:** Public HTTPS range reads verified; mirror documents CC BY 4.0 and the producer DOI.
- **Comparison:** Footer inspection confirms 41,145 rows and 16 columns including lat/lon, but no geometry/GeoParquet metadata. It does not include reservoir polygons or all original GDW attributes. Full source value equivalence was not checked.
- **Reviewed:** 2026-11-01. **Sources:** [AquaScope archive contract](<https://rachidouedraogo.com/aquascope/archive-layout/>), [Public file directory](<https://huggingface.co/datasets/Rekin226/aquascope-gauges/tree/main/context/dams>).

<!-- related-datasets:end -->
