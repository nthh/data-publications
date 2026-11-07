# GEE comparison review — 6 November 2026

**The planned comparisons are complete for all five prepared datasets (six analytical layers). They found differences; they did not establish strict GEE parity.** The original source-preserving GeoParquet and PMTiles releases are unchanged. Data products remain unpublished for repository review.

| Dataset / layer | Local and live GEE count | Feature comparison | Result |
| --- | ---: | ---: | --- |
| River-plastic inputs | 40,760 | All 40,760 in the retained October 30 capture | All 53 attributes and nulls match after the documented spatial/coincident-group association. Maximum point displacement 0.3495 m. Fresh metadata and count match; features were not downloaded again. |
| HydroLAKES polygons | 1,427,688 | 522 | Other attributes match; 508 absent lake names are null locally and empty strings in GEE. Three large lakes have narrow source spikes absent from GEE. |
| LakeATLAS polygons | 1,427,688 | 522 | 342 numeric differences in 17 fields, including GDP quantization exceptions; the same three lake-boundary differences. |
| LakeATLAS pour points | 1,427,688 | 522 | 346 numeric differences in 17 fields. All selected point displacements are below 0.301 m. |
| Free-Flowing Rivers | 8,477,883 | 521 | Documented erosion-field alias, small numeric differences and one null/empty basin name. Five selected geometries have discrete distances above 1 m; maximum 2.8765 m. |
| GRWL raw V01.01 | 64,572,998 | 512 | All 5,120 original attribute cells match exactly. Selected geometry diagnostics are below 0.340 m; strict coordinate/structure parity fails. |

All requested sample identities were found. The [structured summary](summary.json) contains exact counts, sample geography, report hashes and links to every retained evidence file. **`sampled_fail` is retained in all five new strict reports**, including both LakeATLAS layers. River-plastic also retains its historical strict failure. These results support review of a producer-preserving conversion; they are not a claim that GEE, the producer data or the scientific models are error-free.

## What the checks cover

The large datasets use four fixed positions in each of 128 systematically distributed Parquet row groups. The first ten producer IDs are also included for lakes and Free-Flowing Rivers. This yields 512–522 distinct observations per layer, spanning six continents for the lake/FFR samples and 128 source tiles for GRWL. Selection came from the checksummed local releases before reading GEE feature values. It is a coverage sample, not a random statistical sample or an exhaustive content comparison.

Each local sample is bound to the exact analytical package manifest and complete Parquet SHA-256. Each live capture records the committed plan, code, dependency lock, Git revision, response hashes, request inventory and metadata before/after. The comparator independently checks current release pins and historical Git blobs. Live collection counts match each local global count. A matching count does not prove every feature is present or unchanged.

The original strict rules are in [criteria.json](criteria.json): source-aware numerical precision, exact integers/strings/nulls, and geometry parity at `1e-8` degrees after declared ordering and singleton normalization. Source IDs, original geometry and science attributes are compared; synthetic row IDs and bounding boxes are explicitly excluded. Source geometry-derived measurements are reported separately. For raw GRWL, each selected longitude/latitude/segment/index compound key was also checked against the entire local 64,572,998-row file and occurs once. Spatial queries remain separate so overlapping anonymous GEE results do not create false duplicate records.

After strict results, [followup-criteria.json](followup-criteria.json) declared separate explanatory diagnostics. These do not change the strict gate or analytical data. Initial geometry diagnostics use aligned WGS84 vertices or bounded local projections. Every failed/incomplete initial 1 m diagnostic received a part-preserving, bidirectional vertex-and-midpoint distance check: 14 cases per lake polygon layer, 5 FFR and 23 GRWL. These are **discrete distance measurements**, not a continuous Hausdorff guarantee. The original passing rows were not all rerun with that second method. Even a small distance does not establish identical topology.

## Differences to consider in review

### Lake boundaries

Great Bear, Great Slave and Winnipeg have very narrow tips in the retained producer geometry that are absent spatially from GEE. The [vertex traces](lake-spike-traces-r1.json) retain the source coordinates and their neighboring vertices:

| Lake (`Hylak_id`) | Maximum sampled source→GEE distance | Tip base width | Source→GEE vertex-count difference |
| --- | ---: | ---: | ---: |
| Great Bear (2) | 19.612 m | 0.0112 m | 2 fewer in GEE |
| Great Slave (3) | 64.708 m | 0.0051 m | 2 fewer in GEE |
| Winnipeg (4) | 843.353 m | 0.0223 m | 2 fewer in GEE |

Reverse GEE→source distances at these lakes are under 0.30 m. The long, thin source triangles have areas of approximately 0.102, 0.169 and 10.903 square metres. The distances, dimensions and vertex counts are observations; GEE ingestion/normalization as the cause is an inference without the ingestion manifest. The count difference alone does not identify precisely which vertices were removed. Our conversion did not create or repair these features.

Other geometry structures also differ. For example, Caspian Sea has 1,266 source rings versus 1,279 GEE rings, and source/GEE validity differs, despite a discrete distance under 1 m. Yanasechosuichi (`174940`) changes from Polygon to GeometryCollection containing polygon and line geometry. See the full [HydroLAKES](geometry-diagnostics-r2/hydrolakes.json) and [LakeATLAS](geometry-diagnostics-r2/lakeatlas-polygons.json) diagnostics. Source geometry remains intact.

### Attribute representations

HydroLAKES has **508 null→empty-string `Lake_name` differences**, with all other sampled source attribute cells exact. LakeATLAS preserves the selected lake-name nulls but has numeric differences: 263/342 polygon differences and 271/346 point differences fit the exploratory six-significant-digit bound. The remaining **79 polygon and 75 point cases** are in `gdp_ud_vsu` and `gdp_ud_usu`, where GEE values are integral. Of those 154 cases, 148 equal nearest-integer rounding of the retained source value; six do not, with maximum absolute discrepancy 0.5391 in the recorded field units. Small denominators produce relative differences as large as 10.2%, so these should not all be described as negligible floating-point noise. The source values are retained. This observed pattern does not prove which upstream format or ingestion step introduced it.

Free-Flowing Rivers exposes `ERO_YLD_TO` in GEE where the producer field is `ERO_YLD_TON`; the [official GEE schema](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers) describes its erosion-yield meaning. The separate alias diagnostic finds all 521 values: 115 exact and 406 compatible with 12-significant-digit rounding. The original missing-field failure remains. Among the other source fields, 392 of 402 numeric differences follow that exact rounding pattern; the remaining ten differ by at most `5e-16`. One `BAS_NAME` null becomes an empty string. The source `Shape_Length` is reported separately, including its 518 numerical differences; it is not silently treated as a scientific length measurement.

All five remaining FFR geometry differences exceed the declared 1 m diagnostic reference: GOIDs `1671168`, `8075947`, `8404993`, `8406358`, `8407723` (1.371–2.876 m). Their cause is not established. These findings remain disclosed; GEE parity has not been relabeled as passed.

### GRWL source identity and license

The matching community asset is **`projects/sat-io/open-datasets/GRWL/water_vector_v01_01`**, not the simplified GRWL summary. The [community catalog](https://gee-community-catalog.org/projects/grwl/) documents that raw collection. The old Zenodo record cited by GEE and the newer record used for our download name the same V01.01 raw ZIP and MD5. Both primary Zenodo metadata records declare **CC BY 4.0**, resolving the conflicting CC-BY-SA text in the GEE asset description. Exact primary responses and the review are retained in [zenodo-metadata](zenodo-metadata/review.json).

### River-plastic capture age

The November 6 replay checks all 40,760 source records and 2,160,280 attribute cells against the retained October 30 GEE capture: 2,160,076 exact numeric values and 204 matching nulls. Its 19 coincident-coordinate groups are checked as content multisets. Fresh GEE metadata equals the historical metadata and its fresh count is 40,760. That does **not** establish that every current GEE feature value is unchanged; no fresh exhaustive content capture was performed. See [strict](plastic-replay-r1/strict.json) and [diagnostic](plastic-replay-r1/diagnostic.json) reports.

## Reproduce and inspect

The shared [Python workflow](../../scripts/gee_validation/README.md) covers deterministic selection, bounded live capture, offline comparison and explanatory diagnostics. It uses its own locked environment. Raw feature pages, complete samples, credentials and bulk data stay outside Git. Replaying actual comparisons requires the retained local cache or a separately authorized new capture; a clone alone contains the reports and runnable fault tests.

```sh
uv sync --locked --project scripts/gee_validation --python 3.12.12
uv run --locked --project scripts/gee_validation python -m unittest \
  tests.test_gee_request_contract tests.test_gee_release_comparison \
  tests.test_gee_provenance tests.test_gee_geometry_diagnostic \
  tests.test_gee_attribute_diagnostics -v
python3 research/gee-release-validation-20261106/summarize.py --check
```

To replay the actual five new strict comparisons from a clean checkout, use the retained local cache and the same pinned environment:

```sh
uv run --locked --project scripts/gee_validation python \
  research/gee-release-validation-20261106/rehearse.py \
  --cache /path/to/data-publications/.local/gee-release-validation-20261106 \
  --output .local/gee-rehearsal-new
```

The rehearsal requires a clean Git tree, runs the 25 focused tests and checks that each strict comparison reproduces the retained report byte for byte, including its expected nonzero exit and `sampled_fail` status. This verifies reproducibility of the findings, not a parity pass.

Requests were read-only metadata/feature retrieval plus bounded synchronous collection counts, with no exports or batch jobs. The initial FFR count exceeded 45 seconds; its [incomplete receipt](receipts/free-flowing-rivers-r1.json) is retained, followed by a separately committed plan allowing one 180-second count attempt. A geometry report-writer error is also retained in [geometry-diagnostic-attempt-r1.json](geometry-diagnostic-attempt-r1.json); corrected reports use a new directory. Failed checks were not overwritten.

## Verification

The [verification record](verification.json) records 88 passing focused tests and metadata/provenance checks. A fresh persistent checkout with the locked Python environment reproduced all five new strict reports byte for byte, including their `sampled_fail` status. This verifies the tooling and reproducibility of the findings; it does not convert those findings into GEE parity passes. GitHub Actions now includes the offline GEE fault tests, but remote CI was not run for this review branch.

## Publication boundary

The repository is ready for review of these GEE findings alongside the existing full producer-source fidelity and display evidence. The user review precedes product publication. Public anonymous access, hosted checksums, HTTP ranges/CORS, actual cloud queries/rendering, deployed catalog links and registry submission remain separate checks after an authorized upload. No Source Cooperative products or registry entries were published by this validation work.
