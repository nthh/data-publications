# Presentation catalog deployment

Deployment request: publish reviewed `main` commit `c2deb7f04aef6f709ad32a0f9d9d9381fdc64cce` with the existing GitHub Pages workflow. CI run 42429897527 passed before dispatch. The workflow must deploy that exact commit; Source Cooperative analytical files and PMTiles are outside this metadata deployment.

Acceptance criteria frozen before live checks:

- Workflow and deployed artifact correspond to the authorized commit and the reviewed 29-file publish plan (`884581bec5d7fd9c678cbcbbf7ee5af36a335639a48aecf7da950169a21dda4d`). Verify artifact filenames, sizes and SHA-256 values without extracting untrusted paths.
- Anonymous GETs of all 29 canonical Pages URLs return HTTP 200, matching size/SHA-256 and usable CORS. Record failures explicitly; do not use query-string cache bypasses as evidence that canonical URLs work.
- Run `check-catalog-cards.mjs --live` in an isolated browser. Allow actual Pages responses, verify their hashes against the plan, and require all five collection cards and thumbnails. Fail on missing responses or browser errors. Inspect the final screenshot and confirm each current processor/host is `nthh`.
- Keep the prior staged and full data-release validation scopes separate. This verifies metadata presentation only and does not rerun source-fidelity or GEE comparisons.

## Result

[Deployment run 42430108974](https://github.com/nthh/data-publications/actions/runs/42430108974) successfully published commit `c2deb7f`. [All 29 artifact files and canonical live responses](live-pages.json) match the reviewed plan; every response returned HTTP 200, expected content type, and CORS `*`. The [actual Browser check](live-cards.json) verified 11 public responses (catalog, five collections, five thumbnails), loaded all five cards without errors, and passed [visual review](visual-review.json). All five current processor/host entries are `nthh`.

[Open the live Portolan catalog](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/catalog.json). The [live screenshot](live-cards.png) and [summary with evidence hashes](summary.json) retain the review. A [negative control](negative-control.json) deliberately changed one expected thumbnail checksum in an ignored local stage; the live checker correctly rejected the unchanged public response. No remote object was changed for that control.

## Repeat the checks

Use a new output path for each report. Recreate the stage from the deployment commit, then download its metadata artifact and compare it with the frozen plan:

```sh
gh run download 42430108974 --repo nthh/data-publications --name github-pages --dir .local/deployed-artifact
python3 research/catalog-presentation-20261107/deployment/verify_pages.py --plan .local/deployment-stage/publish-plan.json --artifact .local/deployed-artifact/artifact.tar --report .local/live-pages-check-001.json
node scripts/cloud_viewer/check-catalog-cards.mjs --stage .local/deployment-stage --out .local/live-cards-check-001 --live
```

The verifier reads archive members without extracting them, requires the exact planned metadata inventory, and bounds each HTTP response by its expected size. The Browser's `--live` mode allows real Pages requests and compares actual responses to the stage; omitting the flag retains the earlier local-preview mode. Neither command deploys data or revalidates analytical assets. A later deployment may correctly fail an old plan comparison.
