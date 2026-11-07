# GDW, SWOT and publication readiness — 1 November 2026

The current work selects complete Global Dam Watch v1.0 for local preparation and qualifies SWOT scientific PLD v2.03. TerraClimate's full build is deferred from the current vector batch. The completed Lebreton pilot is retained with lower priority. These are local preparation decisions; no upload, repository push, visibility change, GEE request or registry submission occurred.

[Criteria](criteria.json) were committed as `62ece82` before the fresh source/overlap probes. [One-tile criteria](swot-sample-criteria.json), inspection code and tests were committed as `5ada6a2` before the attempted SWOT sample acquisition. Initial exploratory research preceded these criteria, as recorded. Canonical records remain the only editable inventory; [observations](observations.json) are dated, checksum-bound evidence and the [shortlist](../../SHORTLIST.md) is generated.

## GDW overlap and access

Overture's documented Base infrastructure and water features are OSM-derived and useful for generic mapping. They do not establish GDW source inclusion or supply its documented paired layers and full scientific attributes/shared IDs. This comparison uses [provenance](https://docs.overturemaps.org/guides/base/), [infrastructure schema](https://docs.overturemaps.org/schema/reference/base/infrastructure/) and [water schema](https://docs.overturemaps.org/schema/reference/base/water/), not a global feature-level join.

A newly identified [AquaScope mirror](https://huggingface.co/datasets/Rekin226/aquascope-gauges/blob/main/context/dams/gdw_barriers.parquet) is relevant existing access. Its [actual footer](aquascope-parquet-footer.json), read using 8- and 8,032-byte HTTP 206 responses, contains 41,145 rows, 16 selected columns and one row group, with no geometry column or GeoParquet metadata. Its latitude/longitude table is 1,514,458 bytes. The [directory](aquascope-file-tree.json) and [publisher manifest](aquascope-manifest.json) identify only the barrier product, with CC BY 4.0 attribution. Reservoir polygons and the full original attributes remain outside that mirror. No full source-equivalence validation was performed.

The [DataCite registration](gdw-datacite-v1.json) confirms final-v1.0 DOI, CC BY 4.0 and two original ZIP formats, with a release aggregate of 127,938,795 bytes. That total must not be used as the selected Shapefile ZIP size. The exact [direct file route](https://ndownloader.figshare.com/files/47913754) was identified in [AquaScope acquisition code](https://github.com/Rekin226/aquascope/blob/main/aquascope/archive/context_mirror.py). [Article/API requests](gdw-source-access.json), [bundle HEADs](gdw-direct-download-heads.json) and [direct-file range GETs](gdw-direct-file-probes.json) returned HTTP 403; the user reported the same browser failure. No form was submitted and no GDW data were acquired. JRC delta and the selected-column mirror were not substituted for the final full source.

## SWOT edition and inventory

The [current collection](hydroweb-collection.json) and [paginated inventory](swot-v203-inventory.json) resolve the stale HTML description: 122 catalog items comprise **61 v2.03 tiles and 61 v2.02 tiles**. The selected scientific v2.03 assets total **29,990,277,120 bytes by provider metadata** in nine regions. Each includes an explicit MD5 and raw multihash field. Processing-chain version 105 is not the PLD release number. The collection declares ETALAB 2.0; no extra permission requirement was inferred from the open license.

The inventory captures collection metadata and 13 item pages: 482,909 metadata bytes. A tiny unauthenticated range GET to AU_55 succeeded with HTTP 206 and a SQLite header, despite a preceding exploratory HEAD returning 404. Therefore HEAD alone did not prove authentication or download denial. These are successful metadata/range observations, not full file checksums or schema validation.

The [sample attempt](swot-au55-inspection.json) is preserved as **failed preflight**, with zero files downloaded: 42,286,661,632 bytes free was below the 42,949,672,960-byte (40 GiB) start threshold. No SQLite table/geometry assertions can be made from that attempt. Retry to a new report after sufficient space is available; the full source needs a storage/streaming plan beyond the current 8 GiB retained task budget. The scientific product must not be replaced by Light/Geometries or silently flattened to lake polygons alone.

## Existing release readiness

The [fresh streaming integrity audit](prepared-packages.json) checks all five selected local manifests against their canonical hashes, catalog snapshot hashes and declared data/display assets. It SHA-256 checked 3,407,719,487 declared asset bytes with an 8 MiB buffer. This includes some small metadata/display files; analytical Parquet plus PMTiles total 3,407,413,375 bytes. Modern manifest supporting files were outside this fresh scan; the report states its scope. Scientific and public-hosting checks were not rerun or invented.

| Dataset | Selected release | Local state | Remaining work |
|---|---|---|---|
| GRWL summary | `summary-v01.02-local-r1` | Analytic, display and package evidence prepared; fresh integrity passed | Confirm destination, then authorized upload and real public-host/browser checks |
| Lebreton river-plastic | `figshare-v6-r2` | Same local readiness; retained as a lower-priority historical pilot | Same public checks; do not present the 2010-baseline model as current observations |
| HydroLAKES polygons | `v1-local-r3` | Analytical package and source/rebuild evidence prepared; fresh integrity passed | Demonstrate a render path; complete public checks after upload |
| Free-Flowing Rivers | `figshare-v1-local-r2` | Analytical package and source/rebuild evidence prepared; fresh integrity passed | Demonstrate a render path; complete public checks after upload |
| LakeATLAS polygons and points | `lakeatlas-v1.0-r2` | Both analytical layers and source/rebuild evidence prepared; fresh integrity passed | Demonstrate a render path and enrich machine-readable field meanings, units and source/license notices; complete public checks |
| GDW complete v1.0 | No release | Selected, source access blocked | Obtain and pin official archive, then convert, validate, independently rebuild and package |
| SWOT scientific v2.03 | No release | Metadata qualified; bounded sample blocked before download | Source/schema inspection and an adequate storage plan before conversion |

A render path need not mean PMTiles: a demonstrated direct analytical-data viewer may qualify. A sampled thumbnail alone does not demonstrate browsing the dataset. Existing package snapshots and data were not modified. Current five `prepared` records remain prepared; zero records are published. The generated publication catalog therefore contains zero collections. Source Cooperative destinations, public base URLs and public-host evidence remain unset, and Portolan registry submission has not occurred.

## Repeat the checks

Use the repository's locked Python environment. Both capture and audit tools refuse existing report files. Fresh web capture is opt-in; normal tests and catalog checks are offline.

```sh
python -m unittest tests.test_audit_prepared tests.test_swot_inventory tests.test_swot_sample tests.test_dataset_availability tests.test_candidate_discovery tests.test_catalog_citations
python scripts/catalog.py --check
python scripts/publication_catalog.py check
```

The [SWOT README](../../datasets/swot_prior_lake_database/README.md) gives capture/sample commands. To repeat integrity checking, supply explicit existing package locations; for example:

```sh
python scripts/audit_prepared.py --root . \
  --package grwl=.local/grwl/summary-v01.02-local-r1 \
  --package river-plastic-inputs=.local/river-plastic-inputs/figshare-v6-r2 \
  --package hydrolakes=.local/hydrolakes/releases/v1-local-r3 \
  --package free-flowing-rivers=.local/free-flowing-rivers/releases/figshare-v1-local-r2 \
  --package lakeatlas=.local/lakeatlas/releases/lakeatlas-v1.0-r2-prepared \
  --output .local/new-prepared-integrity.json
```

[Verification results](validation.json) record offline tests, unchanged source/release pins and the clean-checkout rehearsal. The failed source requests and disk preflight are retained as failures, separately from passing metadata, footer, integrity and repository checks.
