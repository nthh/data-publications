# Dataset record template

Create discovery-only records at `candidates/<id>/dataset.yaml`; selected records with build, preparation, or history workspaces live at `datasets/<id>/dataset.yaml`. Keep exactly one canonical record per ID. Promote a candidate with `git mv candidates/<id> datasets/<id>` before adding conversion or preparation files. Generated repository-wide views read both roots. This template retains the repository's GEE community audit fields; for another intake source, preserve equivalent source provenance and update the schema before using a different record shape.

```yaml
schema_version: 1
id: example-dataset
title: Descriptive dataset title
community_url: https://gee-community-catalog.org/projects/example
audit:
  snapshot: gee-community-audit-20261029
  family_key: example
  unique_gee_asset_count: 1
  initial_queue: research_original_source
  folia_registry_status: not_identified
  folia_registry_ids: []
  source_coop_urls: []
  source_coop_scope: null
  external_native_urls: []
  external_native_scope: null
triage:
  decision: pending
  priority: normal
  rationale: Why this record is a candidate and what review remains.
review:
  as_of: 'YYYY-MM-DD'
  source_release: release identifier
  proposed_scope: Geographic, temporal and thematic coverage.
  proposed_outputs:
    - geoparquet
  source_license:
    id: SPDX identifier or unknown
    url: https://example.org/license
    evidence: How the source license was confirmed.
  paper_citation: Full citation
  paper_doi: null
  spatial:
    extent: Geographic extent
    crs: EPSG code or grid definition
    geometry: Point, line, polygon, raster, or array
  temporal:
    extent: Observation period
    resolution: Time step or static
  field_units: Describe units or link a field dictionary.
  nulls: Explain missing-value encoding and meaning.
  uncertainty: Describe uncertainty fields or state that none are supplied.
  multiplicity: Explain duplicate or coincident record behavior.
  acceptance_criteria:
    path: validation-plan.md
    recorded_before_evaluation: true
source:
  producer: Organization or authors
  version: release identifier
  url: https://example.org/data
  doi: null
  size_bytes: 0
  checksums:
    sha256: replace-with-lowercase-hex
    provider: null
build:
  entrypoint: build.py
  environment: uv.lock
  outputs:
    - format: GeoParquet
      role: analytic vector data
publication:
  status: candidate # candidate | prepared | published
  release: null
  immutable_prefix: null
  public_catalog_url: null
  public_asset_urls: []
  verified_at: null
  portolan_registered: false
  validation_evidence: []
  limitations: []
```

Replace placeholders; do not record guessed checksums, versions, licenses or results as verified facts. Use `candidate` while source review or planning remains; use `prepared` only after a reproducible local package passes its recorded checks; use `published` only after public URLs and hosted bytes have been verified. Keep data, paper, embedded-code and evidence licenses separate from the repository's software license. Do not store credentials, local absolute paths, private account defaults or raw GEE captures in this record.

## Related datasets

Keep comparisons in the optional `related_datasets` array of the same canonical
record. External references do not create new dataset records or select more
products for processing. Add `record_id` only when the related product already has
a canonical record in this repository; the validator checks that link.

Each entry requires a stable local `id`, `title`, `relationship`, primary `url`,
`use_case`, `comparison`, `reviewed_on` date and one or more `evidence` links.
Coverage, resolution, formats and access notes are optional; state what was
actually reviewed and distinguish documentation from tested asset access.

Relationships describe the linked dataset relative to this record:

- `alternative`: another product for an overlapping use case; equivalence is not implied.
- `complement`: related information or a different period/measurement that adds context.
- `source`: an upstream input used to create this product.
- `derived_product`: a product derived from this dataset.

```yaml
related_datasets:
  - id: example-water-monitor
    title: Example water monitoring product
    relationship: complement
    url: https://example.org/water
    use_case: More recent water-extent observations.
    comparison: Different observation period and method; no equivalence assessment.
    spatial_coverage: Global
    temporal_coverage: State the documented dates and review any coverage gaps.
    resolution: State nominal spatial resolution, if applicable.
    formats: [COG]
    access: Publisher-declared format; anonymous range access has not been tested.
    reviewed_on: '2026-10-31'
    evidence:
      - title: Producer documentation
        url: https://example.org/water/documentation
```

Run `uv run --locked python scripts/catalog.py --write` to regenerate `index.json`
and the marked **Related datasets** section in each affected dataset README.
The command preserves prose outside `<!-- related-datasets:start -->` and
`<!-- related-datasets:end -->`; edit the YAML rather than the generated block.
`--check` rejects stale sections, malformed markers, invalid relationship/date/
source fields, duplicate reference IDs and missing or self-referencing `record_id`
links. Removing an entry updates the section; an empty or absent array removes
an existing generated block. Existing immutable release snapshots stay unchanged.

[JRC Occurrence](../datasets/jrc-gsw-occurrence/README.md#related-datasets) is the
first populated example. Its four references complement the selected historical
baseline; they are not new builds or publication commitments.

## Catalog metadata inputs

An optional `publication.catalog` object binds generated catalog inputs without changing candidate or prepared status:

```yaml
publication:
  status: prepared
  release: v1-local-r1
  manifest_path: datasets/example/releases/v1-local-r1/manifest.json
  manifest_sha256: <actual manifest SHA-256>
  catalog:
    snapshot_path: datasets/example/releases/v1-local-r1/catalog-input-r1/snapshot.json
    snapshot_sha256: <actual snapshot SHA-256>
    package_base_url: null
    hosting_report_path: null
    hosting_report_sha256: null
```

The angle-bracket values are explanatory placeholders, not valid records. Export snapshots from verified immutable packages with `scripts/publication_catalog.py export-metadata`; never hand-write or edit their file inventories. Only a published record with actual HTTPS package URLs and matching hosting evidence enters the public catalog. See [the full contract](catalog-workflow.md#enter-the-published-catalog).

## Cross-catalog discovery

Optional `discovery` metadata records a dated global-scope review, exact provider entry IDs and URLs, relationships to the canonical dataset, existing access and formats, citation observations and checksum-bound research evidence. The [schema](../schemas/dataset.schema.json) defines the fields; [the discovery study](../research/global-candidates-20261031/README.md) describes the evidence and identity rules.

Use `exact_dataset` only when the provider entry describes the selected product; use `same_family`, `component`, `related_release` or `related_product` to preserve differences. Shared titles, citation papers and world-sized bounding boxes do not establish equivalence. A broad worldwide source must not replace an existing regional product or selected layer silently.

Keep the original `audit` and citation snapshot intact. Add new provider observations under `discovery`; do not rewrite the frozen intake. New records use the existing supplemental `intake` contract and remain `triage.decision: pending` and `publication.status: candidate` until separately selected. An available COG or service is a metadata observation, not completed data or licensing validation.

`python scripts/catalog.py --write` regenerates `index.json`, `CANDIDATES.md` and `candidates.csv` from canonical records. The Markdown table highlights the expanded discovery; the CSV includes all currently classified global/near-global records. The views are generated and must not be maintained as a second inventory. Citation counts retain their observation dates, and missing counts remain unknown.


## Availability, sizes and source counts

The optional `review.availability` block records one precisely scoped publication candidate. It includes the shortlist rank, observation date, selected original representation, source-download size and evidence quality, distinct data-distribution services, edition/scope relationships and GEE asset IDs. See the [LakeATLAS example](../datasets/lakeatlas/dataset.yaml) and [CRU-TS example](../candidates/cru_ts_v4/dataset.yaml).

- `download.bytes` is an integer or null; `precision` distinguishes exact metadata/measured sizes, rounded estimates and unknowns. `basis` distinguishes downloaded validation from HTTP headers or a producer listing. Preserve a producer's unresolved unit label in `reported_size` rather than inventing exact bytes.
- Each location has a stable `service_id`, `platform`, `relationship`, formats and evidence URLs. A producer homepage, DOI and CDN alias do not create three locations. Two GEE asset IDs remain one GEE service. Keep older/partial and edition-unverified locations distinct from `matching_scope`; that label is a metadata judgment, not byte-level equivalence.
- `output_manifest` references immutable prepared-release evidence by path and SHA-256. The generator sums analytical Parquet and display PMTiles separately, excluding source archives, docs and packaging duplicates. Missing output evidence remains null.
- Hash-bound `evidence` refers to dated observation snapshots. Preserve frozen observations and create new evidence for new reviews. Existing source pins and immutable release records remain unchanged.

Run `python scripts/catalog.py --write` after editing canonical records, then `--check`. The command validates the schema, evidence, manifest hashes and counting rules and generates `shortlist.json`, `shortlist.csv`, `SHORTLIST.md`, `index.json` and the broader candidate views. Do not maintain another editable shortlist inventory. New records use the existing supplemental `intake` mechanism when the scientific component is distinct from an existing family.

The initial coverage is the ten reviewed publication scopes; missing availability fields elsewhere mean unreviewed, not zero size or no hosts. Bulk-data downloads and live GEE validation remain separate from metadata review.

Generated shortlist views also expose the current triage decision, publication status and preparation stage. A `review.publication_readiness` assessment can reference a dated integrity report and list remaining local/public checks; it is exported to `index.json`. A passing local audit or an upload-review stage never changes `publication.status` to `published`. Source/access failures stay visible in dated evidence, and existing immutable release selections remain unchanged.
