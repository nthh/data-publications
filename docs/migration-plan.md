# Standalone repository migration

This repository is extracted from the verified GEE community publication pilot. Active metadata and workflows move into a single `datasets/<id>/` tree. Historical reports, contracts and exact source bytes retain their original hashes and are identified as provenance, not active configuration. No private repository history or credentials are imported.

Acceptance criteria, recorded before implementation:

- Migrate all 363 intake families without losing triage, citations, source references or the original frozen audit. The river-plastic workflow is `datasets/river-plastic-inputs/`; its original community slug remains `plastic`.
- Use dataset.yaml for active source/build metadata. Eliminate active source.json and separate records/products directories. Derive the index from canonical records and verify it deterministically.
- Remove runtime reliance on the Folia repository layout and unavailable original Git objects. Resolve historic validator bytes by recorded content hashes. Preserve every old failed/passed report as a historical observation.
- Parameterize fresh GEE credentials/project selection. Rehearsal uses the already captured reference offline; it must not silently initiate new live GEE work.
- Make software and data licensing explicit and separate. Keep large source/output/reference files ignored. Include public-facing usage, contributor and validation documentation.
- Run the actual river-plastic build in a fresh clone from the new repository. Validate every source value/coordinate, GeoParquet/PMTiles, STAC/Portolan, research benchmarks, cached GEE comparison and relevant fault tests. Reproduce data asset hashes where expected; explain changed provenance metadata.
- Package a new immutable local release with the latest source-quality notes and validation evidence. Keep the original release unchanged. Record the new code/build revisions and receipts truthfully.
- Verify all tracked files, local documentation references, generated indexes and a source export. Configure no Git remote, upload nothing, and leave a clean locally committed checkout.

The parent owns repository state and commits. Any research/review agents are read-only unless assigned a specific non-overlapping file scope.

## Completion evidence

The standalone clean clone at `4c54a01451967421bf17b1346cd749c0738efdde`
completed `reproduce.py` with the pinned source ZIP and existing GEE capture.
All 14 generated assets and the manifest matched between two independent output
directories, while GeoParquet and PMTiles retained their original r1 hashes.
The full conversion/research/format/HTTP/cached-GEE profile passed with the strict
GEE geometry failure explicitly preserved. There were 39 passing fault checks.
See `datasets/river-plastic-inputs/releases/figshare-v6-r2/` for immutable reports.

Catalog/citation checks cover all 363 families. Five catalog mutation checks and
the 114-entry/44-blob historical source inventory check also passed. The first
migration attempt's Portolan provider failure was fixed in a separate commit
and rerun in a new output directory; its receipt remains visible. The original
Folia workspace now points to this repository and is retained as history.

Publication status and evidence links were updated after the verified build;
these are excluded from effective conversion settings. The release includes the
exact canonical record snapshot used at build time. No remote was configured,
no push or upload occurred, and no registry was contacted. Public GEE-capture
hosting and real public-host verification remain pending.
