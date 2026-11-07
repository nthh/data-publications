# Git-backed publication catalog

The repository keeps one canonical record per dataset and generates a separate publication tree. `datasets/` contains the editable project and its small evidence files; `catalog/` contains the metadata that will be served to consumers. Bulk data remain in ignored local storage until a separately authorized upload.

This implements the shared-repository choice. It follows the [Portolan Git-backed catalog guidance](https://github.com/portolan-sdi/portolan-spec/blob/a2f3380fe238aec91e016eed9429463fe2791da3/specs/best-practices/git-backed-catalogs.md). The consulted [skills revision](https://github.com/portolan-sdi/portolan-skills/tree/1714d9ab672e6a1bbc56ca12458e41b14484d426/skills) and tool versions are pinned in [`tools/portolan/pins.json`](../tools/portolan/pins.json). The guidance is non-normative; our repository checks make the chosen workflow enforceable.

## Inputs and generated files

`datasets/<id>/dataset.yaml` determines dataset identity, selected release, status and catalog inputs. `index.json` remains the generated inventory of all candidates, deferred records and prepared/published releases. It is distinct from the publication catalog.

A catalog-input snapshot copies small metadata from a validated immutable package. It includes the original collection, README, AGENTS, styles and thumbnails, with SHA-256 and size for each file. Original manifests and, for the shared packager, its receipt and package-binding evidence establish the source of those bytes. Snapshot files are generated inputs, not a second manually maintained dataset record. They contain no analytic data or PMTiles.

Snapshot exports refuse existing destinations and leave source packages unchanged. Export a new input revision when the underlying package changes. Keep original conversion code, environment locks and release evidence intact; updating metadata does not justify rebuilding scientifically equivalent analytic bytes.

For example, from the repository root with an existing local package:

```sh
uv run --locked python scripts/publication_catalog.py export-metadata hydrolakes --package .local/hydrolakes/releases/v1-local-r3 --output datasets/hydrolakes/releases/v1-local-r3/catalog-input-r1
```

The five current releases already have their first snapshot, so rerunning that exact command refuses replacement. For a new export, add its relative `snapshot_path` and SHA-256 to `publication.catalog` in the canonical record. The snapshot binds the same `publication.release`, `manifest_path` and `manifest_sha256` as the record.

## Generate and check

```sh
uv sync --locked
uv run --locked python scripts/catalog.py --check
uv run --locked python scripts/publication_catalog.py write
uv run --locked python scripts/publication_catalog.py check
uv run --locked python scripts/test_catalog.py
uv run --locked python -m unittest discover -s tests -p test_publication_catalog.py -v
uv sync --locked --project tools/portolan --no-build
uv run --locked --project tools/portolan python scripts/check_portolan.py --catalog catalog --report .local/checks/catalog-001.json
```

Choose a new report filename for each run. Generation updates only `catalog/`. Checks compare every generated file and reject stale, missing or unexpected content, unsafe paths and changed inputs. They run from a fresh checkout without local bulk data. The validator uses the actual pinned Rashid console entrypoint with bundled profile, STAC and extension schemas; Python socket access is disabled. Unknown schemas requiring network access fail visibly. stac-check is a separate recorded advisory, and incomplete advisory execution is not a pass. See [validator details](../tools/portolan/README.md).

The generated catalog includes only records whose hosted evidence passes the publication contract below. Its current collection count is listed in `catalog/README.md`. The full candidate/project inventory remains in `index.json`. A prepared status and local loopback checks never produce public catalog entries.

## Enter the published catalog

A record marked `publication.status: published` must supply:

- `publication.release`, `manifest_path` and `manifest_sha256` matching the immutable package.
- `publication.catalog.snapshot_path` and `snapshot_sha256` for the exported metadata.
- `publication.catalog.package_base_url`, the exact HTTPS package-root prefix, ending in `/`.
- `publication.catalog.hosting_report_path` and `hosting_report_sha256`, binding actual hosting verification to that same dataset, release, manifest and URL prefix.

When `publication.display` is present, the generated Collection uses its pinned display manifest rather than a display derivative embedded in the analytic snapshot. The display record must also carry `package_base_url`, `hosting_report_path`, and `hosting_report_sha256`. That report binds `display_release`, `display_manifest_sha256`, and `display_package_base_url` in addition to the analytic package fields and the required checks. PMTiles remain linked from the immutable display product; hash-verified style JSON is copied into the generated metadata catalog and rewritten to point at those PMTiles URLs. Multiple display layers produce one style per layer and exactly one default style.

Published Collections derive the current `host` provider from the confirmed `publication.source_coop.owner` and `product_id`; existing producer and processor roles remain recorded. If a prior provider was both host and processor, generation removes its stale host role while retaining its processor credit.

The hosting report has `schema_version: 1`, `dataset_id`, `release`, `package_manifest_sha256`, `package_base_url`, a timezone-aware `checked_at`, `status: passed`, and a `checks` object. Required checks are `anonymous_access`, `range_requests`, `cors`, `asset_checksums`, `subset_query`, `catalog_links` and `browser_render`, each recorded as `passed`. This is an evidence contract for completed checks; the catalog generator does not perform those checks or turn a declaration into proof. Retain the detailed underlying measurements with the release. A local or sampled check cannot stand in for the corresponding public-host check.

For a pinned display package, the same report may additionally bind `display_release`, `display_manifest_sha256`, and `display_package_base_url`; `publication.display.hosting_report_path` and its hash may point to that same report. The generator checks the report against both package contracts and reuses the required hosting checks for the display assets.

Current hosting results are retained in [the publication evidence](../research/source-publication-20261106/README.md) and bound from each canonical record. Earlier local query-server demonstrations and [integrity audits](../research/gdw-swot-preparation-20261101/README.md) remain historical evidence; they do not substitute for the current hosted checks. LakeATLAS also retains its versioned field-semantics supplement tied to unchanged analytical files.

## Configure and prepare publication

[`catalog.publish.yaml`](../catalog.publish.yaml) centralizes:

- Catalog ID, title and description.
- Repository, issues, hosting and browser navigation. A browser URL template uses exactly one `{catalog_url}` or `{catalog_host_path}` placeholder. `{catalog_url}` preserves the legacy behavior of inserting the fully percent-encoded HTTPS catalog URL. For Portolan Browser, use `https://browser.portolan-sdi.org/#/external/{catalog_host_path}`; the renderer supplies the catalog authority and path, preserving valid percent escapes and encoding path characters that could alter URL routing.
- An explicit `s3://bucket/prefix/` destination with an HTTPS `public_base` and region, or the exact GitHub Pages destination `github-pages://nthh/data-publications/` with `public_base: https://nthh.github.io/data-publications/` and a null or omitted region.

The repository and issues links point to `nthh/data-publications`; the hosting link points to the Source Cooperative owner page, and browser navigation uses the documented Portolan Browser route. The metadata destination is configured for GitHub Pages, but this does not mean Pages has been enabled or deployed. Credentials are supplied only by an authorized execution environment. Each dataset can use its own Source Cooperative product and immutable prefix; the generated catalog can link their assets from one metadata root.

For example, a metadata root at `https://nthh.github.io/data-publications/catalog.json` renders the Portolan Browser deep link `https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/catalog.json`. The `{catalog_host_path}` value contains no scheme, user information, query, or fragment. The template must not mix the two supported placeholders or include unknown placeholders.

The selected publication path is our metadata staging script. Do not run `portolan push` against this generated tree: it has a different source-of-truth and synchronization model.

After data are actually hosted and verified, records and configuration are complete, and the generated tree passes review:

```sh
uv run --locked python scripts/publication_catalog.py stage .local/publication-review-001
uv run --locked --project tools/portolan python scripts/check_portolan.py --catalog .local/publication-review-001/catalog --report .local/checks/staged-001.json
```

Staging refuses an existing output directory or an unready catalog. The new directory contains `catalog/` and `publish-plan.json`. Structural links remain relative; the staged root gets its absolute `self` URL, and staged asset links resolve against their correct public locations. The explicit plan lists metadata paths, sizes, checksums and destination URLs/keys. For GitHub Pages, `target_uri` uses the exact `github-pages://nthh/data-publications/` prefix and `region` is null. The served file list excludes bulk files, input proofs and the plan itself.

The five analytical products remain on Source Cooperative. The aggregate metadata catalog can be served separately from GitHub Pages, subject to Pages eligibility and configuration; the public site exposes the catalog even if the source repository remains private. This does not create a sixth Source Cooperative product. Verify the deployed aggregate catalog and its public links before submitting it to the Portolan registry. Dataset publication and aggregate-catalog deployment are separate events.

## CI and verification scope

`.github/workflows/validate.yml` checks canonical records, retained provenance, generator behavior, actual validator failure controls and the tracked publication tree. It needs no dataset downloads or credentials. Dependencies and GitHub Actions are pinned.

`.github/workflows/prepare-publication.yml` is manually dispatched and produces a metadata review artifact. It performs no Source Cooperative upload. It refuses to prepare a zero-collection catalog. Remote runs are available in [GitHub Actions](https://github.com/nthh/data-publications/actions); local command and fresh-checkout rehearsal results are recorded separately.

`.github/workflows/publish-catalog-pages.yml` is a separate manual deployment path. The workflow accepts only `nthh/data-publications` on `main`; it does not require the source repository to be public. Before dispatching it, confirm that the repository is eligible and configure Pages to use GitHub Actions as its source. GitHub Pages content is publicly accessible even when its source repository is private, so this deployment publishes the staged catalog metadata and links publicly while keeping the repository private. Repository visibility changes follow the separately authorized finalization sequence. Finish the published-record hosting evidence before dispatch. The workflow requires a nonempty published catalog, locked catalog generation and Rashid checks on both tracked and staged trees. Its Pages artifact contains only `.local/publication-stage/catalog/`; it excludes `publish-plan.json` and all bulk assets. The `github-pages` environment receives the deployment. This workflow has not been dispatched. The recorded configuration request returned HTTP 422 because the current GitHub plan does not support Pages from this private repository. Preflight the official Portolan Browser with exact locally staged metadata and real Source objects, explicitly recording that metadata hosting is simulated. After the already-authorized history reset and public repository release, enable Pages and repeat the check against deployed metadata without interception. The preflight does not satisfy the final live-hosting gate.

The focused acceptance criteria are in [catalog-acceptance.md](catalog-acceptance.md). Existing release source-fidelity, clean-rebuild and scientific-validation claims retain their original scope; these metadata checks do not rerun or enlarge them.

The [implementation verification report](../reports/catalog-workflow-20261031/summary.json) records 35 passing focused tests, identical metadata re-exports, clean-checkout regeneration and the actual validator reports. It also records the incomplete stac-check advisory and the remaining public-hosting work.
