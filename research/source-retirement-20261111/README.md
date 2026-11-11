# Flat Source layout: final catalog cutover

**The Source layout cleanup is complete.** All five products now have flat directories: 43 root files and no subdirectories. The [completed execution receipt](retirement-execution-r2.json) records deletion of 606 obsolete objects totaling 18,501,609,265 logical bytes (18.50 GB). Their verified replacements and retained Git provenance remain available. GitHub push, Pages deployment, generated README updates and post-deletion live checks are complete.

## Generated inputs and retained evidence

The original [remote inventory](remote-inventory.json) contains 603 objects totaling 18,500,215,163 bytes. The generated [retention plan](retention-plan.json) accounts for each object: 19 use verified flat replacements, 581 have exact retained Git bytes, and three producer PDFs use verified flat Source copies. The Git mappings deduplicate to 440 files. Of those, 105 files were not previously tracked and are retained in `archive/` (21,605,105 stored bytes); larger evidence is compressed losslessly. Two small PMTiles test fixtures remain identifiable as fixtures. No analytical dataset is added to Git.

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

The [catalog publish plan](catalog-publish-plan.json) freezes the exact Pages artifact. The original [execution plan](execution-plan.json), superseded by revision 2 below, has SHA-256 `53dd12e73d01fee1f966ae1330548e104774396b38f597164108eb6c6db3cb82`, pins that artifact, retention inventory, README plan, seven-case browser report and destination verification receipts.

The verified main was pushed and `publish-catalog-pages.yml` deployed the catalog. After deployment, `scripts/source_publish/retire.py --live` requires exact anonymous readback of every staged catalog file, every live Git support asset and all five Source READMEs. It confirms the retention commit is on remote main, all verified destination objects have unchanged ETags and lengths, and the complete old inventory is unchanged. Only then can `--execute` delete the exact inventoried keys with ETag guards. It records every deletion, supports an explicit resume, and requires all ten old prefixes empty at completion. A changed, unplanned or missing object stops the operation.

Generation, publication and deletion remain separate commands. The user approved publication, and the updated catalog is deployed. Automatic approval review subsequently required direct confirmation to perform deletion after the live checks; that rejected command did not run. The user then explicitly approved the final 606-object scope, and the guarded execution completed. The deployed catalog no longer depends on the retired Source prefixes.

## Live cutover and supplemental metadata

[GitHub validation and Pages deployment](github-deployment.json) passed for commit `6913e937d7292bc810efaa7c0487dd2534957198`. The [live preflight](live-preflight-r1.json) checked exact bytes for all 29 deployed catalog files, the 26 Git-hosted supporting assets, five Source READMEs, 38 unchanged verified flat objects and all 603 old object ETags/lengths. All checks passed. The [official Portolan cards](portolan-cards-live-r1/report.json) loaded five cards and all previews with no errors; [visual review](portolan-cards-visual-review.json) passed. This is an aggregate card check, not a new official Browser feature/table acceptance claim.

The complete [product-root listing](product-roots-before.json) exposed three additional LakeATLAS objects under `metadata/field-semantics-v1/`. They were outside the original ten-prefix inventory. These are a field-semantics JSON document, its README and generator, totaling 1,394,102 bytes. All three have [exact, anonymously verified copies in the existing retention commit](supplement-live-verification.json). LakeATLAS's Source README now generates direct, commit-pinned Git links for the documentation and semantics JSON; the script remains in the same Git directory. Its [README upload receipt](readme-uploads/lakeatlas-supplements-r1/summary.json) records full readback verification.

The prepared [inventory revision 2](remote-inventory-r2.json) and [retention revision 2](retention-plan-r2.json) cover **606 objects / 18,501,609,265 bytes**. [Execution plan revision 2](execution-plan-r2.json), SHA-256 `8df2a5db615027a97226673a61ef1572b1737a6159c3ddef10461435b3bd1396`, adds only those three exact canonical supplement keys and the updated generated README plan. The deletion guard accepts metadata keys only when they match the canonical supplement path and SHA-256; an unknown metadata object fails validation. No broader metadata-prefix permission is inferred.

The [automatic-review rejection](automatic-review-block.json) remains retained as historical evidence. The subsequent direct user confirmation authorized execution revision 2. Its [receipt](retirement-execution-r2.json) records all 606 deletions and successful final empty-prefix checks.

The [final live preflight](live-preflight-r2.json) passed for execution revision 2, with all 606 old objects still present and zero deletions. The supplemental change passed [58 focused checks](supplement-focused-tests.txt).

The [supplemental clean-checkout replay](supplement-clean-checkout.json) reproduced the updated README plan byte for byte, with no tracked changes. [GitHub validation](supplement-github-validation.json) also passed for commit `55723fa2ea78a9b9d4fb3fd084b77d8aa52dfd3d`.

## Completed retirement and live checks

After the final user confirmation, execution revision 2 rechecked the exact deployed catalog, Git support files, READMEs, retained bytes and source/destination ETags before deleting the inventoried keys. The [execution receipt](retirement-execution-r2.json) records completion at 2026-11-11T23:46:02Z. This is a logical remote-object byte total, not a measurement of billing or local disk savings.

The [post-retirement verification](post-retirement-verification.json), produced by [the read-only verifier](verify_retirement.py), lists each complete product inventory and confirms exactly these remaining root files:

| Source product | Files | Subdirectories |
| --- | ---: | ---: |
| Free-Flowing Rivers | 7 | 0 |
| GRWL raw | 7 | 0 |
| HydroLAKES | 8 | 0 |
| LakeATLAS | 13 | 0 |
| River plastic inputs | 8 | 0 |
| **Total** | **43** | **0** |

All 43 files passed anonymous HEAD and CORS checks. All 12 Parquet/PMTiles assets passed bounded range requests, and all five READMEs passed full SHA-256 readback with no incorrect organization credit. Every deployed catalog file and Git support asset still matches its pinned bytes. The replacement data objects retain the ETags and lengths bound to their earlier full checksum readbacks.

[All seven map cases](browser-after-retirement.json) passed again against live Source files, including GRWL overview and detail widths. The [official Portolan card check](portolan-cards-after-retirement/report.json) loaded all five collections and thumbnails without errors; its separate [visual review](portolan-cards-after-retirement/visual-review.json) passed. These are publication and rendering checks, not new scientific or GEE validation. The earlier incomplete stac-check advisory remains incomplete.
