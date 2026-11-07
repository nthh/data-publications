# Source Cooperative product preparation — 1 November 2026

The seven selected datasets now have canonical Source Cooperative product intent under `publication.source_coop` and generated local review JSON/READMEs plus consumer-facing product READMEs. The user confirmed **nthh** as the owner. One product represents one scientific dataset; LakeATLAS retains polygons and pour points in the same product. The [criteria](criteria.json) were committed as `07e9ef9`; the fixed uncapped browser follow-up criterion was committed as `db62a47` before evaluation.

The five retained packages have exact, local-only file plans. All package files were read and SHA-256 hashed; canonical manifest assets, supporting files, workflow snapshots, license/attribution records, snapshot files and applicable package-binding proofs were checked. Files without an earlier checksum declaration are explicitly labeled inventory-only rather than retroactively claimed as bound evidence. No analytical data or immutable package was changed or copied.

| Dataset/product | Selected release | Immutable files | Planned bytes | Current state |
|---|---|---:|---:|---|
| [grwl](../../datasets/grwl/source-coop/product-README.md) | `summary-v01.02-local-r1` | 14 | 132,896,295 | Prepared locally; exact file plan verified |
| [river-plastic-inputs](../../datasets/river-plastic-inputs/source-coop/product-README.md) | `figshare-v6-r2` | 15 | 10,323,801 | Prepared locally; exact file plan verified |
| [hydrolakes](../../datasets/hydrolakes/source-coop/product-README.md) | `v1-local-r3` | 65 | 951,304,220 | Prepared locally; exact file plan verified |
| [free-flowing-rivers](../../datasets/free-flowing-rivers/source-coop/product-README.md) | `figshare-v1-local-r2` | 62 | 887,900,186 | Prepared locally; exact file plan verified |
| [lakeatlas](../../datasets/lakeatlas/source-coop/product-README.md) | `lakeatlas-v1.0-r2` | 80 | 1,488,036,020 | Prepared locally; exact file plan verified |
| [Global Dam Watch](../../datasets/gdw/source-coop/product-README.md) | Final v1.0, proposed | — | Unknown selected archive size | Source returns HTTP 403; no converted release |
| [SWOT PLD](../../datasets/swot_prior_lake_database/source-coop/product-README.md) | Scientific v2.03, proposed | — | 29,990,277,120 original bytes by producer metadata | Sample/schema and output fit unverified; disk guard blocks acquisition |

The [current exact file plan](staging-r2/immutable-upload-plan.json) contains **236 immutable files, 3,470,460,522 bytes** (3.47 GB), plus five separate mutable product-root READMEs. That includes full package documentation and three LakeATLAS metadata supplement files, not just Parquet/PMTiles. Every entry has its source descriptor, size, SHA-256, content type, proposed bucket/object key and raw URL. Bulk data are referenced in place; staging writes only small JSON plans. The [first plan](staging-r1/stage-summary.json) is retained as an earlier review whose mutable README copy was subsequently completed; use r2 for the current proposal.

## Local work completed

The [browser evidence](render/render-evidence.json) binds all four HydroLAKES/FFR/LakeATLAS analytic files to their immutable hashes. Installed Chrome rendered five precommitted regional windows and the fixed follow-up through a repeatable local DuckDB query server: **24 successful browser feature requests, 9,872,208 loopback response bytes, zero external downloads**. The five regional controls use a clearly labeled 1,000-feature cap. The fixed southwest Europe follow-up returned all **295 HydroLAKES bbox matches** without the cap. Geometry clipping/simplification affects display responses only. This is a local render demonstration, not proof of a public viewer, complete global rendering or scientific accuracy. [Screenshot](render/hydrolakes-custom-sw-europe-browser.png); [reproduction](render/README.md).

The [LakeATLAS field supplement](../../datasets/lakeatlas/metadata-enhancements/v1/README.md) documents 305 producer attributes per layer: 281 catalog attributes and 24 inherited HydroLAKES fields. It records definitions, units, aggregation/dimension syntax, sources and license evidence. Catalog CC BY 4.0/ODbL terms remain separate from inherited HydroLAKES source-product terms; geodatabase defaults and derived geometry/bbox columns are labeled. The repeatable generator verifies the pinned manifest, schemas and producer PDFs, and uses unchanged analytical hashes. The supplement and its generator/reader guide are explicitly included under `metadata/field-semantics-v1/` in the product plan.

[GDW retry evidence](sources/retry-20261102-network.json) retains the actual HTTP 403 direct-file response. Earlier sandbox DNS failures are separate observations, not source outage evidence. The producer documentation page was reachable. [SWOT storage plan](sources/swot-storage-plan-20261102.md) uses one source tile at a time and requires a measured fit within the 8 GiB added-data budget; neither its SQLite schema nor output-size estimate is validated. Shared free space remained below the recorded 40 GiB start threshold. No files were deleted or thresholds lowered.

## Source Cooperative execution status

[Owner confirmation](owner-confirmation.json) and [successful CLI login/read access](account-access-signed-in.json) are recorded without credentials. The authenticated namespace listing returned the existing `snotel/` and `us-boundaries/` prefixes. None of the seven new products has been created, and no data or metadata have been uploaded.

The [reviewed creation route](product-creation-route.json) is Source's signed-in [new-product web form](https://source.coop/products/new). Its current API POST remains unimplemented; the CLI provides S3 credentials but no creation command. Opening the form in Chrome exposed a disabled “Allow JavaScript from Apple Events” setting. A subsequent read-only check found no tab still at the creation route; browser automation has not been re-established. The user has been offered enabling that setting or retaining manual creation. Connection selection and product-create permission remain unverified. Proposed products should start **unlisted** while preparation continues; unlisted is a discoverability setting, not a promise of private storage.

Public asset checks, consumer browser checks, generated host-provider alignment, metadata catalog deployment and Portolan registry submission remain separate unfinished publication steps. Existing packages retain historical Folia processing/host text; a generated public catalog must identify the confirmed current maintainer without erasing historical processor credits. The publication inventory still has five `prepared` releases and zero `published` releases; the generated public catalog has zero collections.

## Repeatable commands and checks

See [product tooling](../../docs/source-cooperative-products.md) for deterministic draft generation and exact-plan staging. The canonical record is the only editable inventory. Every fresh stage requires a new output directory and explicit local package mappings; neither the staging tool nor CI uploads anything.

```sh
uv run --locked python scripts/source_products.py write
uv run --locked python scripts/source_products.py check
uv run --locked python scripts/catalog.py --check
uv run --locked python scripts/publication_catalog.py check
uv run --locked python -m unittest tests.test_source_products tests.test_lakeatlas_semantics
uv run --locked --project scripts/release_tools python -m unittest tests.test_render_preview
```

The focused implementation/schema/catalog checks total **76 passing tests**. [Rashid 0.3.0](portolan-gate.json) passed the offline generated-catalog metadata check (one root, zero published collections). The separate stac-check advisory remains **incomplete** because it attempted a schema network request under the offline guard; it is not counted as a pass. No live GEE requests or scientific revalidation were run. The [clean-checkout rehearsal](clean-checkout.json) regenerated the product drafts, candidate inventory and publication catalog byte for byte with no local bulk data, reran 33 focused product/metadata/render tests, and passed the preserved-provenance check. Existing environments had byte-identical committed lock files. The [verification report](validation.json) distinguishes the 76-test implementation run from this 33-test rehearsal.
