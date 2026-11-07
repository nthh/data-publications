# LakeATLAS v1.0 validation plan

Recorded before conversion results. This plan applies to the analytic GeoParquet product only; display derivatives are out of scope.

## Source identity and scope

- Producer release: LakeATLAS version 1.0, Figshare article 19312001, immutable DOI `10.6084/m9.figshare.19312001.v1`.
- Native source: `LakeATLAS_Data_v10.gdb.zip`, Figshare file 35959544, 1,530,962,499 bytes; producer MD5 `952e0724afc96d3a5899f08935d4a094`.
- Expected scope: both producer layers, `LakeATLAS_v10_pol` (1,427,688 MultiPolygons) and `LakeATLAS_v10_pnt` (1,427,688 points). No filtering.
- Attribute observation periods vary by source and are described in the producer field catalog/technical documentation. This is a static 2022 publication, not a claim that every input was observed in 2022.
- CRS: producer geographic WGS 84. Preserve source coordinates exactly.

## Required preservation

- Keep all native fields in original order with decoded types, values, and nulls.
- Keep the native OGR FileGDB feature ID `OBJECTID`, producer lake identifier `Hylak_id`, all native attribute fields, and every row in both layers, including repeated IDs or coincident geometries.
- Store source geometry as WKB with no repair, simplification, coordinate change, or deduplication. GDAL OpenFileGDB applies its default standards-based polygon ring organization when decoding the FileGDB; do not override it. Preserve and report the known warning for a feature with more than 100 parts.
- GeoParquet metadata must declare WKB geometry and WGS 84 CRS and have valid bbox metadata.

## Checks and failure criteria

1. Verify exact Figshare article/file metadata, downloaded size, producer MD5, local SHA-256, and ZIP CRCs. Record every ZIP member's compressed and uncompressed size before extraction. Prefer direct virtual ZIP access; do not extract if GDAL can read it.
2. Inspect source layer name, complete schema, CRS, geometry types, extent, feature count, and null counts before conversion. Require these pins to match the manifest on later builds.
3. Stream conversion in bounded Arrow batches into a new empty release directory. Do not materialize all rows or a full GeoDataFrame.
4. Independently reread every source record in both layers and compare in source order with the matching GeoParquet output. Require identical field names/order/types, null bitmap, every decoded value, both `OBJECTID` and `Hylak_id`, and WKB bytes; require exact multiplicity and row count per layer.
5. Read output with PyArrow and GeoPandas. Require CRS/geometry metadata, row-group readability, and exact asset checksum. Independently recompute every bbox child from each source WKB during the complete fidelity pass; reject any child-value/null mismatch, and require the WKB global extent to match GeoParquet bbox metadata. Run the complete source pass and each GeoPandas subset check as sequential standalone processes; combine their reports only after all checks pass, and record the maximum phase RSS and both worker hashes.
6. Mutation tests must demonstrate rejection of a removed row, duplicated row, changed non-null value, changed null, changed identifier, changed geometry, and invalid or missing GeoParquet metadata.
7. Rebuild from committed workflow and locked dependencies in a clean checkout; compare analytic asset bytes exactly. No source or output overwrite is permitted.

## Limits and deferred checks

- Source fidelity does not establish scientific accuracy of upstream models or inputs.
- No display derivative is included.
- No public upload, remote hosting, or registry submission is part of this local release task.
- A complete build must remain below 1 GB process working memory and 8 GB task-owned disk, exclusive of the retained source archive and producer documentation.

## Acceptance addendum: spatial-order companion

Recorded after the source-order release failed Rashid PTL-DAT-006 and before any spatially ordered companion build. The two validated source-order GeoParquets remain immutable and remain the source-fidelity baseline. A separate companion pair may be built for spatial access; the companion does not replace or rewrite the source-order pair.

- Deterministic order: compute the 16-bit Hilbert distance of each feature's WGS 84 bbox center. Clamp longitude to [-180, 180] and latitude to [-90, 90], then quantize each axis as `floor((x + 180) / 360 * 65535)` and `floor((y + 90) / 180 * 65535)`, clamped to [0, 65535]. Sort by `(hilbert_distance, OBJECTID)` ascending. All ties use the native ID, so the row order is deterministic.
- Reversible source order: both input files were independently scanned and have `OBJECTID` exactly 1 through 1,427,688 in producer source order. The full source validator compared each FID and cell in source order. The spatial builder must recheck uniqueness and contiguous values before sorting; its validator restores rows by ascending `OBJECTID` and fails if the invariant changes. No extra source ordinal field is added.
- Cell preservation: keep every source column in its original order with its Arrow type, field metadata, nulls, and WKB bytes. Do not repair, simplify, rewrite, or deduplicate geometry. The spatial pair has separate filenames and release metadata.
- Full companion reread: independently read each completed spatial Parquet and restore producer order by `OBJECTID`. Compare every non-geometry source column exactly as Arrow values, including its type and nulls. For every feature, hash the complete raw WKB byte string with SHA-256 and compare its byte length, digest, and null state with the corresponding source-order feature; this is a cryptographic comparison of every full WKB value, not a sample or aggregate geometry check. Compute those hashes per feature in bounded batches. Compare row multiplicity and all IDs. Independently recompute each bbox child from completed WKB and compare all child values/nulls, geometry-type tallies, global extent, CRS, and GeoParquet metadata.
- Spatial checks: run Rashid 0.1.8 PTL-DAT-006 against each completed companion file. Measure bbox row-group pruning for geographically separate queries and compare returned identifiers/WKB between local reads and the bounded loopback HTTP reader.
- Repeatability: rebuild both companions from a clean checkout with the same locked code and require byte-identical SHA-256 values. Bind raw, transformed, and clean-rebuild bytes/reports through the release fidelity normalizer with `final_transform: spatial_order`.
- Predeclared pruning windows: use Europe `[5,45,15,55]`, North America `[-100,40,-90,50]`, East Africa `[20,-5,35,5]`, and Australia `[135,-35,150,-20]` in WGS84. For every window with matching rows, require bbox statistics to rule out at least 50% of row groups; report empty windows as zero matches without substituting another region. Run the fixed Europe subset through local HTTP and verify returned identifiers and raw WKB against the local asset, recording requested bytes and response bytes.
- Fault tests: reject a removed or duplicate feature, changed non-null value, changed null, changed OBJECTID/source ordinal, changed WKB, altered bbox child, and a permutation that fails source-order restoration.
- Resource limits: keep every transform and full reread process under a hard cap of 1 GB RSS, with a 512 MiB target for the bucket writer and validator. The target is an optimization goal; the 1 GB cap is the pass/fail limit. Keep task-owned intermediate and output data below 8 GB, excluding the retained source archive and producer PDFs. Require at least 40 GB free before a bulk write and retain a 10 GB free-space floor. Record logical file bytes and allocated disk usage separately where APFS clones share storage.
- Process separation: write each spatial candidate in one process that records an immutable checkpoint binding the input/output byte identities, the exact helper checksum, and transform settings; record the Git revision separately in build/rebuild evidence. Do not treat this candidate or checkpoint as a passed asset. In a new sequential process, validate the checkpoint and candidate, restore all attributes by native ID, compare every WKB by its complete per-feature SHA-256/length/null identity, and recompute bbox values. Only the second process can produce the passed augmentation report. The writer and validator must each stay below the RSS cap; retain any failed stage and its hashes.
- Failure handling: immutable source-order files and prior reports stay untouched. Any failed transform, fidelity, pruning, schema, or clean-rebuild check is retained as failed evidence and blocks prepared status.

The pre-build bbox-only simulation, recorded in `releases/lakeatlas-v1.0-r1/portolan-order-analysis.json`, passed Rashid's exact 10-chunk locality predicate for the proposed key, but it was not a materialized-file result. No companion is accepted until the checks above pass against actual files.
