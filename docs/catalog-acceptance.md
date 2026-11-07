# Catalog workflow acceptance criteria

Recorded before implementation and evaluation on 2026-10-31.

The shared repository keeps one editable dataset record and generates its publication catalog. This change adds repository structure and local publication preparation; it does not upload data, create remote repositories, submit registries, run GEE or rebuild analytic datasets.

## GitHub Pages metadata deployment addendum (2026-11-06)

The aggregate catalog remains metadata in this repository. The five dataset products remain separate Source Cooperative products; no sixth product is required for the catalog.

- Accept only `github-pages://nthh/data-publications/` paired with `https://nthh.github.io/data-publications/` and a null or omitted region. Reject wrong owners, repositories, prefixes, query strings and non-null regions. Keep S3 destination support and its region requirement.
- Stage an exact metadata-only plan with checksums, absolute public `self` and local metadata asset URLs, and relative structural links. Never include GeoParquet, PMTiles, source archives, caches or `publish-plan.json` in the Pages artifact.
- Keep the existing manual preparation workflow. Add a separate manual Pages workflow that requires a public `nthh/data-publications` main branch, exact configuration, locked catalog and Rashid checks, and a nonempty published catalog before deploying only the staged `catalog/` directory.
- Do not dispatch the deployment, enable Pages, change repository visibility, push, or register the catalog as part of this implementation.

- Preserve the existing 366 record identities, intake and citation snapshots, triage decisions, publication statuses, conversion workflow bytes and immutable release evidence.
- Export deterministic, checksum-bound metadata snapshots from each of the five existing prepared packages without copying bulk data or editing the package. Repeating an export into a new directory must produce identical files; existing destinations must be refused.
- Generate the tracked catalog deterministically from canonical records, pinned metadata inputs and one publish configuration. An unchanged fresh checkout must reproduce it without .local data, credentials or data downloads.
- Include only records marked published with real HTTPS package URLs and checksum-bound hosting evidence. Prepared/candidate/deferred records must never become public catalog entries. A valid empty root must be explicitly reported as zero published collections, not publication readiness.
- A changed snapshot, malformed record, missing or stale generated file, unexpected generated file, unsafe path/symlink, duplicate output path, local asset URL or incomplete hosting evidence must fail the appropriate check with an actionable error.
- Publish metadata only. Bulk archives, GeoParquet, PMTiles, rasters, Zarr, credentials and caches remain outside Git and publication metadata staging. Relative structural links remain portable; production self and asset URLs are added only in a new staging directory.
- Exercise a synthetic published collection and navigation/style URL rewriting, plus refusal cases. Preserve legacy `{catalog_url}` substitution and verify `{catalog_host_path}` produces the documented Portolan Browser `/external/` route. Reject malformed, unknown or mixed placeholders; confirm URL credentials/query/fragment cannot enter the host/path value and encoded path characters remain safe. Run pinned Rashid schema/structural checks on the generated root and populated fixture, and prove the gate rejects a removed required license.
- When a published record pins a display package, generate PMTiles links/assets and hash-verified rewritten styles only from that pin; reject a changed manifest or style and missing display-host evidence. Exercise two display layers with exactly one default style, and verify the current Source Cooperative owner is the host while producer and processor credits remain.
- Run stac-check as a recorded advisory distinct from the conformance gate. Pin tool environments and the consulted upstream spec/skill revisions.
- Provide offline pull-request validation and a manual local/publication-preparation path with no uploader or credentials. Missing destinations or zero published entries must produce a clear not-ready result.
- Verify the changed Python boundary, generated-tree drift checks and a fresh-checkout rehearsal; preserve failures and report actual limits.
