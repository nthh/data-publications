# HydroLAKES v1 local release criteria

The pre-build contract is `research/hydro-releases-20261031/contract.json`.
Preserve every decoded attribute type/value/null and original GDAL WKB. Require
1,427,688 unique contiguous Hylak_id values from 1 to 1,427,688. Preserve the
native geographic CRS and every geometry without repair or simplification.

The retained FRC11 converter is copied from Folia commit 100d1d061b00b4a427db6bd891d7c05ff20f4056.
It sorts by Hylak_id and uses per-feature digests plus complete output reread.
Independently reread the original source after conversion for the standalone
release. A clean committed-code build must reproduce analytic bytes. The
historical output hash is comparison evidence; an environment-dependent difference
must be documented and cannot be silently equated with the old artifact.

Validate GeoParquet metadata, actual STAC/Portolan schemas, manifest identities,
local HTTP range/CORS reads and a subset query. Mutation tests must reject dropped
or duplicated records, value/null edits and geometry edits. No GEE parity or
scientific accuracy claim follows from source fidelity. Display derivatives are
optional and excluded from this analytic-only release.

## Spatially ordered derivative acceptance addendum (2026-10-31)

The source-order GeoParquet remains retained as the raw fidelity baseline. A full local package attempt with the bbox-covered, `Hylak_id`-ordered asset passed STAC Node, asset integrity, HTTP 206/CORS and DuckDB local/HTTP subset checks, but actual Rashid 0.1.8 Portolan validation failed MUST rule PTL-DAT-006: 1,427,688 rows in 2,789 row groups did not cluster spatially. The package remains failed and is not prepared. A spatially ordered companion is now the only candidate for the next release version; this layout change does not alter the pinned HydroLAKES source or raw baseline.

Before promotion, the companion must meet every check below:

1. Preserve the complete raw baseline and add only the derived `bbox` struct required by GeoParquet 1.1. Compute the 16-bit Hilbert key from each WKB-derived bbox center in WGS84, clamping longitude/latitude to the documented coordinate bounds; break key ties by `Hylak_id` ascending. Do not repair, simplify, reproject, or rewrite WKB. `Hylak_id` must remain unique and contiguous from 1 through 1,427,688.
2. After restoring companion rows to ascending `Hylak_id`, compare every original attribute value, decoded type and null exactly against the raw baseline. For every feature, compare geometry null state, WKB byte length and SHA-256 digest keyed by `Hylak_id`; this is a per-feature cryptographic byte binding, not an aggregate-only or sampled comparison. Independently decode every companion WKB, recompute all four bbox children, and verify global extent and geometry-type counts.
3. Run the same deterministic stage on `clean-rebuild-442460a/data.parquet` from the detached clean checkout using the same full spatial-order code revision and lock. Require byte-identical final companion hashes and sizes. Record the observed detached HEAD and empty Git status. Do not rerun the producer conversion or fetch the evicted source ZIP for this stage.
4. Run actual Rashid 0.1.8 `check --schema --data-scope local --json` on the candidate. PTL-DAT-006 passes only when the validator's actual 10 contiguous equal-count bbox chunks meet its installed threshold: adjacent overlap fraction `< 0.30` **or** mean chunk-bbox area/global-extent area `< 0.30`. Also require PTL-DAT-007 covering statistics, PTL-DAT-008 row-group size, and PTL-DAT-012 GeoParquet version to pass. No advisory downgrade or metadata-only substitute satisfies this gate.
5. Require the actual STAC Node Validator 2.0.0 checks, exact manifest and supporting-file integrity, bounded HTTP 206/CORS probes, and order-independent identifier/WKB fingerprint equality for a local versus loopback DuckDB subset. Keep the transfer count and selected subset window in the validation report.
6. Keep the sort's memory and staging usage bounded: peak resident memory at or below 1 GiB, preflight at least 40 GB free, preserve at least 10 GB during writes, and retain failed output/reports. Do not label the candidate prepared if a limit or gate fails.

The retained source-order raw asset, source-fidelity report, and failed v1-local-r1 and v1-local-r2 package attempts remain unchanged evidence. The new spatial order is a separately identified derived layout. It is not evidence of improved analytical accuracy or GEE parity.
