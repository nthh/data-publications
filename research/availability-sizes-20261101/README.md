# Shortlist sizes and distribution locations — 1 November 2026

This audit adds normalized availability facts for the ten scopes in the [preceding publication-gap review](../native-publication-gaps-20261031/README.md). The editable facts live only in `datasets/<id>/dataset.yaml`, under `review.availability`. The [readable shortlist](../../SHORTLIST.md), [JSON](../../shortlist.json) and [CSV](../../shortlist.csv) are generated from those records. The remaining inventory has not received this availability review; blank fields do not imply zero size or no distribution.

## Method and evidence

[Criteria](criteria.json) were committed before the fresh HTTP capture. Earlier source research, prepared-release manifests and the frozen TerraClimate listing already existed. [Observations](observations.json) preserve the dated research findings, URLs, scope/edition relationships, selected representation and input identities. They are research evidence, not a second editable inventory. Each canonical availability block pins this evidence by SHA-256 and candidate key. Existing records and immutable release artifacts were preserved.

Sizes measure one selected original representation of a precisely stated scope, not the sum of alternate formats, duplicate decadal files, documentation, or all products with a similar name. Exact source bytes for the five prepared datasets come from their validated source pins. Prepared sizes are derived from checksum-bound release manifests, splitting analytical Parquet from PMTiles display files and excluding archive/package/documentation copies. No output estimate is substituted for an unbuilt release.

For CRU-TS v4.10, the [HTTP capture](source-size-headers.json) records successful HEAD responses for all ten full-period 1901–2025 compressed NetCDF files. Their exact Content-Length sum is 3,648,920,307 bytes. Rounded directory labels would understate a decimal-GB total. These headers establish transfer size, not downloaded checksums or valid decoded scientific values.

TerraClimate uses the existing frozen listing of 1,064 annual NetCDF files: 14 variables over 1950–2025. Its rounded Mbytes sum implies approximately 115.51 decimal GB. One file's successful HEAD supports the decimal unit interpretation; this is not a full object-header inventory. RiverATLAS retains the producer's “2.33 GB” label with null exact bytes because its unit convention and headers could not be confirmed. Both RiverATLAS HEAD endpoints returned HTTP 403, including the [separate follow-up](riveratlas-head-followup.json). The GDW version-specific API also returned HTTP 403; size remains unknown. SWOT PLD v2.03 is announced, but the inspected detail page still describes v2.02. No older release's file count or size is substituted.

Counts measure distinct public distribution services found in the reviewed sources. A producer landing page, DOI, repository URL and CDN alias can describe one service. Several GEE assets count as one service, while asset IDs and counts are retained separately. Documentation mirrors, request forms, private staging and local prepared files do not count as independent public hosts. Older/subset and unverified-edition services contribute to the total but not matching-scope counts. Matching scope is a metadata judgment, not a new byte/pixel equivalence test. Google Earth is not Google Earth Engine.

TerraClimate's producer distribution is the selected v1.1 source; Planetary Computer and GEE describe other coverage/lineage. CRU's producer v4.10 is distinguished from older CEDA and World Bank distributions. GDW's JRC `v1_delta` directory is a different edition. GRWL's GEE summary is V01.01 versus selected V01.02, and the river-plastic GEE entry does not establish Figshare version 6. SWOT's Hydroweb service is identified, but current-edition file availability remains unqualified. Counts are bounded findings, not proof that no other hosts or GEE assets exist. See the preceding audit for Source Cooperative search coverage and its known snapshot gaps.

## Reproduction and checks

The normal repository workflow is offline:

```sh
python scripts/catalog.py --write
python scripts/catalog.py --check
python scripts/publication_catalog.py check
python -m unittest tests.test_dataset_availability tests.test_candidate_discovery tests.test_catalog_citations -v
```

The schema validates shape, types and relationship vocabulary. Semantic checks reject duplicate services/ranks, contradictory unknown sizes, inconsistent pinned source sizes, unsafe evidence paths, missing evidence keys and changed evidence/manifest hashes. Generated views expose numeric bytes and counts as well as scope notes and source links. JSON preserves nulls; CSV represents unknown numeric values with empty cells.

Fresh metadata capture is separate and opt-in. Supply a new output path; prior captures are never overwritten:

```sh
python research/availability-sizes-20261101/capture_sizes.py --output /path/to/new-size-capture.json
```

This command sends twelve HEAD requests and one bounded JSON metadata request. The separate alternate RiverATLAS HEAD is retained as a follow-up. No data bodies, GEE jobs, conversions, uploads or registry submissions were performed for this audit. [Validation results](validation.json) retain the initial test-import failure and corrected verification, as well as the clean-checkout rehearsal status. The publication catalog still contains zero published collections; five releases remain prepared locally.
