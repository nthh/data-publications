# Flat Source layout: final catalog cutover

The generated local catalog no longer references Source's `releases/` or `display/` prefixes. All five Source READMEs are updated, and three producer PDFs have been copied unchanged to the product roots. **GitHub push, Pages deployment, live catalog readback and remote prefix deletion are pending.** No old Source object has been deleted.

## Generated inputs and retained evidence

The [remote inventory](remote-inventory.json) contains 603 objects totaling 18,500,215,163 bytes. The generated [retention plan](retention-plan.json) accounts for each object: 19 use verified flat replacements, 581 have exact retained Git bytes, and three producer PDFs use verified flat Source copies. The Git mappings deduplicate to 440 files. Of those, 105 files were not previously tracked and are retained in `archive/` (21,605,105 stored bytes); larger evidence is compressed losslessly. Two small PMTiles test fixtures remain identifiable as fixtures. No analytical dataset is added to Git.

The retention commit is `c0ad1cc5c18d69d3915f01bda478cb300d13b12f`. Historical report bytes, including old attribution text, remain unchanged as evidence. Current consumer documentation names the original producers and independent maintainer correctly.

[`scripts/source_retirement.py`](../../scripts/source_retirement.py) creates the retention plan, document-copy plan and support mappings from the frozen listing, verified flat file plan, original Collection snapshots, exact Git bytes and completed document receipts. It does not delete remote objects. Canonical records pin five generated support manifests; they relocate all 29 support assets without changing identity, size, checksum, media type, title or roles. Supporting JSON/Markdown files use exact Git commit URLs. The producer PDFs stay alongside the Source data files, including the large LakeATLAS attribute catalog.

[`scripts/support_publication.py`](../../scripts/support_publication.py) validates those mappings. The catalog generator rejects any old Source URL in generated collections, styles or Markdown after support relocation is enabled. README file tables and the [README-only upload plan](readme-plan-r2.json) are generated from the canonical records without restoring bulk packages. This generated plan has exactly the same five object bindings as the earlier [executed plan](readme-plan.json).

## Completed checks

- 90 focused tests passed, covering flat mappings, support relocation, unsafe or changed retirement targets, README plan generation, Source drafts and publication catalogs. See [test output](focused-checks-r2.txt).
- Canonical record, Source draft and catalog regeneration checks passed. The staged catalog contains 29 metadata files.
- [Pinned Rashid conformance passed](portolan-r1.json). The separate offline stac-check advisory remains incomplete for six objects.
- [All seven live MapLibre cases passed](browser-r1.json): six flat styles plus GRWL at detail zoom, with 2,111,361 Source bytes requested. This checks real Source objects in a local MapLibre harness, not the deployed official Portolan Browser navigation.
- [Three document copies](document-copy-r2/receipt.json) passed full anonymous checksum readback. The first attempt failed because credentials had expired; [that receipt](document-copy-r1/receipt.json) is retained.
- [Five README uploads](readme-uploads/) completed. [Fresh anonymous verification](source-final-check.json) matches their full SHA-256 values and confirms no incorrect organization credit. It also confirms unchanged ETags, lengths and CORS for all 38 verified flat objects.
- The [clean-checkout replay](clean-checkout-r2.json) reproduced all 29 catalog files and both publication plans byte for byte, with no downloaded datasets or tracked changes. Two existing test fixtures of 977 and 984 bytes are explicitly inventoried. The first inventory assertion was too broad and counted those fixtures as downloaded PMTiles; its [failure](clean-checkout-r1-failure.json) and [corrected criteria](clean-checkout-criteria-r2.json) are retained.
- The [temporary metadata cache cleanup](temporary-cache-cleanup.json) removed 584 task-created files / 212,635,667 bytes after their exact bytes were preserved in Git or verified Source PDFs.
- The [retirement dry run](retirement-dry-run.json) validates all 603 retained object bindings offline. Its status is prepared, not deleted or live-validated.

The initial metadata-download attempt encountered a transient DNS failure; its [failure record](prepare-r1-failure.json) is retained. An initial README command combined mutually exclusive CLI flags and was rejected before any network operation; the [diagnostic](readme-preflight-r1-failure.json) records the correction. Neither failure was treated as a passing check.

## Deployment and removal

The [catalog publish plan](catalog-publish-plan.json) freezes the exact Pages artifact. The [execution plan](execution-plan.json), SHA-256 `53dd12e73d01fee1f966ae1330548e104774396b38f597164108eb6c6db3cb82`, pins that artifact, retention inventory, README plan, seven-case browser report and destination verification receipts.

Push the verified local main and dispatch `publish-catalog-pages.yml`. After deployment, `scripts/source_publish/retire.py --live` requires exact anonymous readback of every staged catalog file, every live Git support asset and all five Source READMEs. It confirms the retention commit is on remote main, all verified destination objects have unchanged ETags and lengths, and the complete old inventory is unchanged. Only then can `--execute` delete the exact inventoried keys with ETag guards. It records every deletion, supports an explicit resume, and requires all ten old prefixes empty at completion. A changed, unplanned or missing object stops the operation.

Generation, publication and deletion remain separate commands. The pending push requires an explicit user request under the repository instructions. The old Source prefixes remain necessary for the currently deployed catalog until this cutover succeeds.
