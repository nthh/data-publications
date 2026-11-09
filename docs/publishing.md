# Preparing and publishing a dataset

A local build is not a public release. Keep the source, conversion, evidence, release archive and hosting records tied together by checksums and an immutable version identifier.

## 1. Register the candidate

Start with one canonical `candidates/<id>/dataset.yaml` for discovery-only review. When selected for build or preparation, move the record into its workspace with `git mv candidates/<id> datasets/<id>` before adding workflow files; never copy it. Existing workspace records remain at `datasets/<id>/dataset.yaml`. [The template](dataset-template.md) describes the intended record shape. The catalog validator preserves the frozen 363-family intake. Additional producer or official-catalog products use the supplemental intake contract: `intake.kind`, `intake.reference_url`, and `intake.added_on`, with an optional `related_family` pointing to an existing audited family. They do not fabricate or alter the frozen community audit. Each still has exactly one canonical dataset record; the index is generated from those records. Record the source identity and version, download URL, size and checksums, the paper and producer, license and attribution, units, nulls, uncertainty, spatial and temporal coverage, expected record count, planned outputs, and validation criteria. Keep the audit and triage provenance. A **candidate** status means review is still under way; it does not claim a build, validation, or publication.

Before selecting a conversion, check both an exact native copy and a current
alternative that serves the intended use. Record its scope, version, formats,
maintenance, retention and remaining gap. Prefer reuse when it meets the need; a new mirror
needs a concrete purpose. Keep alternatives separate from exact-dataset matches.
Citations help prioritize demand after this check; they do not establish current
quality or a need to republish. Record useful alternatives and complements in
`related_datasets` on the canonical record, with dated primary-source links,
coverage, access and measurement differences. The catalog generator includes
these references in the index and dataset README; see the
[related dataset contract](dataset-template.md#related-datasets). Listing a
reference does not change selection, build or publication status.

A version pin identifies bytes but does not keep them available; verify durable retrieval for a reproducible research release. The [GRIP4/Overture review](../research/local-build-two-20261030/grip-overture-review.md)
illustrates the distinction between preserving a historical research input and
providing current roads.

Keep three dates separate: the producer's release/version, the observation or
model-input vintage, and our conversion date. Check producer version history and
the current source listing before choosing bytes, then record `version_checked_on`,
the versioned DOI or exact filename, byte size and checksum. A paper DOI is a
citation, not necessarily the dataset DOI. Record label/filename mismatches and
GEE asset-version differences explicitly. See the [2026-10-31 version review](../research/hydro-releases-20261031/version-review/producer-version-review.md).

A later upstream version starts a new review and immutable build. Never silently
update a source pin or claim that an unchanged research release represents current
conditions. Check alternatives separately: a newer model or partially released
base dataset may serve a different geographic or scientific purpose.

Write acceptance criteria before evaluating fresh results. Include exact comparisons where possible, tolerances and why they are appropriate, expected loss or transformation for display derivatives, geographic and temporal scope, and checks that would fail the release. Preserve every failed report; add a distinct, linked follow-up report when a new diagnostic explains a specific limitation.

## 2. Build and validate locally

Pin source bytes and software dependencies. Build into a new, empty versioned directory; never overwrite a previous output. Validate every recoverable source value, identifier, null, coordinate or grid property, output structure, metadata and checksums. Validate scientific benchmarks separately from source fidelity. Run a second build with the same committed code and locked environment and compare generated asset hashes. Keep raw inputs, bulky outputs and GEE capture pages in ignored local storage.

Choose formats for intended access: GeoParquet for vector analysis, PMTiles for vector display, Cloud Optimized GeoTIFF for tiled raster access, or Zarr for multidimensional/chunked arrays. Keep lossy display derivatives distinct from analytic data and document thinning, quantization, resampling, aggregation or other transformations.

A **prepared** status means the local release passed its stated checks and has a packageable evidence set. It does not mean the data are hosted, publicly accessible, accepted by a registry, or scientifically validated beyond those checks.

## Repeatable vector workflow

Each dataset keeps its own Python scripts and dependency lock alongside the single
canonical record. The [GRWL](../datasets/grwl/README.md) and
[GRIP4](../datasets/grip/README.md) workflows make the pilot pattern explicit:

1. Inspect and pin the original archive and producer field dictionary. Record any
   source-version mismatch with GEE before comparing results.
2. Write source-fidelity and display criteria. If a later diagnostic is added
   after output inspection, label it as follow-up evidence.
3. Commit the conversion inputs, then build to a new ignored directory. Preserve
   exact analytic values, nulls, line parts, coordinates and record multiplicity.
4. Reread the source and compare every feature. Check GeoParquet bbox metadata and
   statistics; audit display IDs and attributes separately from sampled geometry.
5. Run actual STAC and Portolan schema checks plus local HTTP range, CORS and
   spatial-subset queries. Handwritten metadata checks do not replace schemas.
6. Inject faults that remove or duplicate rows, change values/nulls or alter
   geometry. Require failure for the intended reason, not any incidental error.
7. Rebuild from committed code in a clean checkout and compare asset and manifest
   bytes. Package only reports bound to those exact bytes, with workflow source,
   source attribution and separate code/data licenses.
8. Promote `publication.status` to `prepared` and regenerate the index only after
   the release gates pass. Keep the build-time record snapshot inside the package;
   later publication-status changes must not rewrite it.

Use one analytic file for a small product when appropriate, or bounded streaming
and spatial partitions for large products. GRIP4 uses its seven producer regions;
this is one dataset record and one proposed data product, not seven competing
registry records. The source fields identify the region, and every partition is
listed in the collection. Neither pipeline starts a GEE request or uploads data.

For the large analytic-only hydrography releases, use the shared
[`scripts/release_tools`](../scripts/release_tools/README.md) packaging workflow.
It consumes exact-asset source-fidelity and clean-rebuild reports, snapshots
workflow source and dependency locks, retains producer documentation and field
notices, and runs actual STAC/Portolan, loopback range/CORS and DuckDB subset
checks. The [fidelity binder](../research/hydro-releases-20261031/bind_fidelity.py)
checks the chain from pinned archive through source-validated raw data to the
final derivative. Dataset release directories contain the input templates and
commands; bulk data stay under `.local/`.

Adding bbox columns preserves the original fields and WKB, and requires a full
comparison plus independently recomputed bounds. Spatial reordering is a separate
transformation: preserve a proven source ordinal, compare every field after
restoring source order, and repeat from a clean checkout. Spatial metadata alone
does not establish efficient pruning; check the actual layout and representative
queries. Retain source-order outputs and failed layout checks as evidence.

When build stages use different commits, pin their exact workflow files with
`workflow_revisions`; record the packaging revision separately. Keep immutable
package snapshots unchanged when the canonical record is later promoted. A sampled
PNG preview is only an orientation aid; it does not constitute a complete visual
product or a validation of geometry.

A portable MapLibre style may contain a relative PMTiles path. Clients resolve it
against the style document URL and then apply their registered PMTiles protocol;
`pmtiles://../file.pmtiles` is not a portable substitute for that resolution.

## 3. Package and review

Package a new immutable archive with the manifest, file checksums, source pins, code revision, environment/tool versions, validation reports, same-code rebuild evidence, license notices and explicit limitations. Before publication, independently inspect the archive inventory and verify every recorded hash. Confirm that no credentials, raw captures or unlicensed material entered the archive. Keep active records and instructions portable. Immutable historical evidence can retain old checkout or project identifiers; label this clearly and review it before publication.

## 4. Publish and verify

Use the [Git-backed catalog workflow](catalog-workflow.md) to export verified metadata inputs, generate `catalog/`, run the pinned checks and prepare a reviewable metadata bundle. The shared repository keeps its conversion pipelines and canonical dataset records; public metadata are generated separately.

Publish conversion code, Python scripts and small release evidence in [nthh/data-publications](https://github.com/nthh/data-publications). This independently maintained repository accepts contributions and publishes Portolan-compatible metadata. GitHub ownership is separate from Source Cooperative product ownership; the data-hosting account and product remain publication decisions. Retain Folia attribution for code and historical processing derived from that project.

Publish data separately through Source Cooperative, under a new immutable version/build prefix. Confirm the owner's account access and product scope first. After upload, use anonymous requests to verify real byte-range responses, CORS headers and a representative remote subset query against the actual public URLs. Confirm checksums from the hosted bytes. Do not register the data with Portolan until the public catalog and asset URLs have been tested. Only then mark the release published and record the exact public URLs, version, checks and date. Until those checks pass, do not make a public availability claim.

## River-plastic pilot evidence

The cached GEE capture is an offline reference. Its numeric values and nulls matched exactly; the maximum coordinate displacement was 0.349456 m. Strict coordinate parity failed. A separate follow-up checked attributes within the documented geodesic tolerance and handled 19 coincident-coordinate pairs as multisets, preserving all source records. Keep both the original failure and follow-up visible. This comparison does not establish the GEE asset's source version or scientific accuracy. Do not initiate a new GEE job as part of routine build, validation, or publication work.
