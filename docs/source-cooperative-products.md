# Source Cooperative product drafts and upload plans

`scripts/source_products.py` prepares local metadata drafts and exact file plans from canonical dataset records and verified local packages. It is an offline preparation tool. It does not contact Source Cooperative, create products, upload files, publish records, or submit Portolan registry entries.

## Canonical input and generated drafts

Promote a discovery record from `candidates/<id>/` to `datasets/<id>/` before preparing a Source product. The only editable product intent belongs in `publication.source_coop` in that canonical `datasets/<id>/dataset.yaml`. Generated drafts and local product review files live in its `datasets/<id>/source-coop/` workspace:

```yaml
publication:
  source_coop:
    owner: nthh
    owner_status: proposed # proposed | confirmed
    product_id: example-product # 3–40 lowercase letters/digits/hyphens; no consecutive hyphens
    title: Example product
    summary: Product-level description.
    tags: [hydrology]
    license_note: CC BY 4.0
    attribution: Producer name
    temporal_note: Edition and temporal scope.
    limitations:
      - Known validation limitation.
    supplements: []
    account_verification: null
```

Product IDs and non-null owners use 3–40 character lowercase slugs with letters, digits, and single hyphens. Duplicate YAML keys fail closed. Each optional `supplements` entry has `path`, `sha256`, and a package-relative `destination` under `metadata/<version>/`. Supplement bytes are not copied into plans; staging re-hashes them and records portable repository paths.

Run from a checkout:

```sh
python scripts/source_products.py write
python scripts/source_products.py check
```

The commands create or check `datasets/<id>/source-coop/product-draft.json`, `README.md`, and `product-README.md` for records that have `publication.source_coop`. Other records, including historical `publication.source_cooperative`, are skipped. `README.md` is the local review document with readiness and blockers. `product-README.md` is consumer-facing copy for the product root, with scope, formats, credits, limitations, related links, and relative release-file links. A candidate or unbound record receives `local_readiness: blocked`, an empty asset list, and copy that says the product is planned with no converted release; the generator does not invent package files.

An owner and `owner_status: confirmed` alone do not make a product creation-ready. The optional `account_verification` object must have `status: confirmed`, the exact `owner`, and repository-relative `evidence_path` plus `evidence_sha256`. The evidence file must hash correctly and be JSON containing the same confirmed owner. The resulting maintainer proposal is independent of existing immutable package metadata; it does not rewrite historical producer or converter credits. Even when the local creation prerequisites pass, `created` and `hosted` stay false until a separate authorized workflow actually does those things. Proposed `s3://<owner>/<product_id>` routes are labels for review, not hosting evidence.

## Exact local staging

For each prepared dataset, pass the exact local package directory. The chosen output directory must not exist, including as a dangling symlink:

```sh
python scripts/source_products.py stage \
  --package grwl=/path/to/grwl-summary-v01.02-local-r1 \
  --package hydrolakes=/path/to/hydrolakes-v1-local-r3 \
  --output /path/to/new-source-coop-plan
```

Repeat `--package ID=PATH` for each product. The command checks the tracked canonical manifest hash and identity, the local root `manifest.json`, the canonical catalog snapshot hash and identity, snapshot collection files, every declared asset and display derivative, supporting files, workflow files, dataset/license/attribution/fidelity/rebuild evidence, optional release receipt/package binding proofs, and every regular file in each package. Package contents are streamed and hashed once; manifest, snapshot, receipt, and workflow-bound paths are compared to that inventory. Repeated declarations are accepted only when checksums and any specified sizes agree. Files covered only by inventory are explicitly marked `inventory_only_unbound`, not treated as provenance-verified. `LICENSE` and `NOTICE` are recognized extensionless text files. Hidden and credential-like paths, symlinks, traversal, unknown extensions, missing files, duplicate mappings, and duplicate object keys are rejected. If a newly created plan directory encounters a failure, `failure.json` records the error. Existing output paths are never changed.

Successful output includes `products/<id>/upload-plan.json` and `immutable-upload-plan.json`. Every file entry carries the proposed bucket/owner, endpoint, S3 URI, raw URL, object key, byte count, SHA-256, content type, binding status, and portable source descriptor. Package files map to `{product_id}/releases/{release}/{path}`. The aggregate compares collisions by `(bucket, object_key)`. Generated consumer copy maps to `{product_id}/README.md` in a separate mutable metadata section and is excluded from immutable totals. It is marked `upload_allowed: false` pending account access and an authorized execution workflow; wording finalization is not a separate blocker. Plans contain no local absolute package paths and copy no bulk bytes. Their integrity/readiness fields describe local metadata and package checks only; scientific and public-host validation is not rerun. `stage-summary.json` reports local readiness and blockers without changing canonical publication status.

The S3-compatible proxy form is `s3://<owner>/<product>`. Raw object URLs use the `https://data.source.coop/<owner>/<product>/...` host; the human-facing product page uses `https://source.coop/<owner>/<product>/`. Treat both as proposed until a real account route and successful public hosting checks are verified. No link is emitted as a confirmed public URL by this tool.

Product staging is separate from Portolan. Do not use `portolan push`, catalog publishing, or another metadata-rewriting upload path for these plans. Keep account checks, product creation, upload, public URL verification and registry submission as separate recorded steps within the user’s authorized scope. Read-only checks and local preparation can proceed; uploads and registry submission require explicit publication authorization, and existing authorization continues to apply.

## Creating the prepared products

The owner is `nthh`, confirmed by the user. The current CLI login works, but that grants S3 credentials and does not itself prove product-creation permission. Source's supported creation interface is the [new-product form](https://source.coop/products/new). The reviewed official v1.7.0 API POST is unimplemented. Choose an eligible Source data connection in the form and initially select `unlisted` while preparation continues; unlisted does not mean private data. The [creation-route evidence](../research/source-products-20261101/product-creation-route.json) records the exact upstream source revision and browser restriction. No product is claimed created until a real success receipt is recorded.

## Versioned display packages

A dataset still has one canonical record and one proposed Source product. Add an
optional `publication.display` to that record when a separately versioned display
package is prepared:

```yaml
publication:
  display:
    release: display-v1
    manifest_path: datasets/example/display/display-v1/manifest.json
    manifest_sha256: <SHA-256 of generated manifest>
```

The manifest is generated evidence, not another editable registry. It binds each
PMTiles archive to the existing analytical release and source-asset checksum,
with its layer name, stable ID, retained attributes, zoom range and portable
MapLibre style. The original analytical release stays immutable.

Pass `--display-package ID=/absolute/display/package` alongside that dataset's
`--package` argument to `stage`. Every file must match the prepared display
manifest, including report and style bytes. The stage command rejects an omitted
required display package, source mismatches, symlinks, extras and modified bytes.
Display objects use `<product>/display/<display-release>/...` in the same product.
The older immutable upload plans remain usable only for their original scope.

Portable styles use a relative archive URL, such as `../assets/lakes.pmtiles`.
A MapLibre client resolves it against the style URL and registers the PMTiles
protocol. Do not store a protocol-specific `pmtiles://../...` URL in the portable
style. Existing GRWL tiles are reused; the generated measured-width style is a
versioned supplement under `metadata/grwl-width-v1/style.json`.

See [display builds and checks](display-derivatives.md) for the complete process.
