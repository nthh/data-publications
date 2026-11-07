# River source selection and validation audit

**As of 2026-11-02.** This audit checks the prepared Free-Flowing Rivers and
river-plastic conversions against the GRWL source-selection/fidelity concern,
then records the current state of GRIP, JRC GSW Occurrence, GDW, and SWOT Prior
Lake Database. The evidence inventory with SHA-256 hashes is in
[river-audit.json](river-audit.json).

## Findings

| Dataset | Current state | Audit finding |
| --- | --- | --- |
| Free-Flowing Rivers | Prepared locally, unpublished | No simplified summary input or omitted source layer found. The pinned Figshare v1 FileGDB conversion covers the complete `FFR_river_network_v1` layer: 8,477,883 global reaches, 38 source attributes, FID, and WKB. Exact source reread and fault checks pass. Scientific accuracy and GEE parity are not assessed. |
| River plastic inputs | Prepared locally, unpublished | No lower-detail source substitution found. The conversion preserves all 40,760 records, 53 numeric fields, coordinates, null-bearing rows, and coincident records from Lebreton Figshare v6. This is the explicitly labeled Lebreton 2017 product with a 2010 baseline, not a claim to be current or the later Meijer model. |
| GRIP | Deferred after local validation; not packaged | Full GRIP4-2018 global roads conversion was validated locally, but the user stopped the complete rebuild. Seven partitions matched; full rebuild/reproducibility and package creation remain incomplete. Overture is identified as the preferred current-road source. |
| JRC GSW Occurrence | Reuse existing producer-hosted source; sample-qualified | v1.5, 1984–2024, 504 TIFFs. Eight bounded probes support tiled TIFFs with overviews and COG-like layout. No raster payload conversion, exhaustive COG check, or scientific pixel validation. |
| GDW | Candidate, blocked on source access | Intended scope is the complete consensus v1.0 barriers and reservoirs. Official Figshare/API/direct-file access returned HTTP 403; no source archive was acquired or converted. AquaScope's selected-column barriers and JRC's different `v1_delta` edition are not complete substitutes. |
| SWOT Prior Lake Database | Candidate, metadata-qualified; not converted | Scientific v2.03 inventory contains 61 SQLite tiles totaling 29,990,277,120 provider-declared bytes. Metadata and a 16-byte SQLite-header range succeeded; no complete tile, checksum, or schema was validated. Inspection stopped below the 40 GiB disk-start floor, and the original source exceeds the task's 8 GiB retained-storage ceiling. |

## Validation limits and material caveats

For Free-Flowing Rivers, `source-validation.json` reports a passed complete
source comparison. Raw rebuild, package checks, STAC/Portolan validation, and a
loopback HTTP/DuckDB subset check are recorded as passed. The
`clean-rebuild.json` summary nevertheless sets
`clean_checkout_independently_verified` to `false`, while its nested evidence
reports matching raw inputs and assets plus passed spatial augmentation. Treat
this as an unresolved report-field inconsistency; it does not negate the direct
source-fidelity report. This remains local preparation: no public upload or
remote-host check. The producer paper is [Grill et al. (2019)](https://www.nature.com/articles/s41586-019-1111-9),
and the pinned [Figshare record](https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801)
provides the selected source release.

For river plastic, source validation compared all 2,160,280 numeric cells and
all 40,760 geometries; same-machine reproducibility passed. The strict GEE
coordinate replay remains failed. A separate final comparison passes only under
the declared exact-coincident-group multiset contract: 2,160,076 exact numeric
matches, 204 matching nulls, and maximum displacement 0.349456389 m. The strict
and unique-only geodesic checks remain failed. The GEE asset's upstream release
and ingestion transform are undocumented, so the coordinate difference's cause
is unknown. These checks compare a captured dataset, not independent scientific
truth. The source paper is [Lebreton et al. (2017)](https://www.nature.com/articles/ncomms15611);
the distinct later model is [Meijer et al. (2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8087412/).

Published-summary checks for river plastic pass, but independent observational
validation and named-river/regional crosswalks are not run. The project labels
the 2010 baseline and distinguishes Meijer 2021 in canonical metadata and
readmes; preserve this labeling in any later catalog or viewer.

## Method note

The first pass mistakenly used the bulkdata FFR r2 copy and stale
`.local/clean-clone-r1` plastic/status material. I withdrew that status section
and rechecked all six canonical records and relevant reports in the current task
worktree. This audit's claims and hash inventory point only to that current
worktree; the prior stale-read correction is retained here for provenance.
No downloads, live GEE requests, builds, or tests were run for this audit, and no
scientific model was independently revalidated.

## Parent review of the rebuild flag

The normalizer writes clean_checkout_independently_verified=false unconditionally (bind_fidelity.py line351). Matching rebuilt asset hashes and saved clean-checkout observations are present. This flag is a conservative normalizer limitation, not evidence of a failed rebuild; it does not independently re-establish the saved checkout provenance. Evidence hashes above refer to Git revision `711e281`, before this audit follow-up changed canonical records.
