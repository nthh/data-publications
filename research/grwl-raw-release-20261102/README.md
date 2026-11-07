# Raw GRWL rebuild and source-choice audit

The simplified GRWL summary is withheld from publication because five inspected straight connectors are present in the producer summary but absent from the corresponding raw network. Its original files remain unchanged as evidence. The new [`grwl-raw` project](../../datasets/grwl-raw/README.md) preserves individual producer vector observations; it does not join observations by segment ID or observation index.

## What the other dataset audit found

| Dataset | Source choice and retained scope | Qualification |
| --- | --- | --- |
| HydroLAKES | Complete official polygon product, 1,427,688 lakes; no summary substitution | The separate producer pour-point layer is outside the selected release. |
| LakeATLAS | Both official FileGDB layers, 1,427,688 polygons and pour points each, with source fields | Decoded geometry fidelity uses GDAL/OpenFileGDB; it does not independently validate producer science or raw FileGDB ring encoding. |
| Free-Flowing Rivers | Complete official reach network, 8,477,883 records and source attributes | No independent scientific-accuracy or GEE comparison is claimed. |
| River plastic inputs | All 40,760 points and 53 numeric fields from the selected Lebreton release | Historical 2017 model with a 2010 baseline. Strict GEE coordinate equality failed; the separate declared comparison accepts documented sub-metre displacement and preserves coincident-record multiplicity. |

The [hydro audit](source-audit/hydro-audit.json) and [river audit](source-audit/river-audit.json) contain structured findings and exact evidence paths/hashes. The [parent evidence review](source-audit/parent-evidence-review.json) checked 61 unique files against Git revision `711e281`. Evidence references describe that immutable revision; later canonical-record changes do not rewrite those source observations. The rebuild normalizer sets `clean_checkout_independently_verified=false` unconditionally. Matching rebuild hashes and saved clean-checkout observations remain evidence; that flag is not a newly failed rebuild.

GRIP is a deferred, validated historical conversion whose remaining rebuild was stopped at the user's request. JRC Occurrence is a reuse candidate with eight sampled source probes, not a complete pixel validation. GDW and SWOT remain unconverted candidates. Their current states and limits are included in the river audit.

## Pilot results

The nine tiles around the reported errors contain **919,832 records**. The [source comparison](pilot-source-validation-r2.json) checks every DBF numeric value/null, source ID, part boundary and XY float64 bit against the original files. All pass. There are 6,236 producer unknown-width values (`width_m=1`); the derived validity field and viewer distinguish them from measured widths.

The pilot analytical file is 73,203,604 bytes; the detail PMTiles is 163,886,673 bytes. The [final display check](pilot-display-validation-r3.json) accounts for 919,828 visible IDs plus four explicitly listed sub-metre grid collapses. All 998,233 decoded maximum-zoom occurrences have matching selected attributes. Of 576 frozen geometry samples, 575 pass the 30 m display tolerance; the remaining sample is one of the enumerated collapses, not a passed geometry comparison. The [native fixture](pilot-display-quantization-native-r1.json) independently reproduces all four collapses with the pinned Tippecanoe executable.

The initial failed display report and the follow-up reports remain retained. The first browser run could not inspect one short boundary observation in a wider view. The [second browser run](browser-pilot-r2/report.json) inspects the same five frozen source records at detail zoom and passes raw ID, all-attribute, width, HTTP 206 and CORS checks. Regional screenshots are retained alongside close-up views. These are conversion and display checks, not new observational or GEE validation.

These pilot checks preceded the completed global release below. [localhost:8914](http://127.0.0.1:8914/?dataset=grwl-raw&region=grwl_15450) now serves the complete global files, still local and unpublished.

## Repeatability and global work

The [original criteria](criteria.json) were committed before evaluation. The [global resource revision](global-criteria.json) changes only the storage allowance after measuring the pilot and after the user freed disk space. It retains all geometry/fidelity thresholds, two native threads, the 40 GiB starting floor and the 15 GiB stop floor. It allows for the 3.10 GB producer archive, an estimated 5.14 GB analytical file, roughly 11.5 GB of detail tiles and build scratch; these are estimates, not completed-output sizes.

The global source inventory expects 829 tiles and 64,572,998 SHX records. Full archive acquisition, global conversion, independent source and display checks, clean-checkout reproduction and release packaging are separate gates. See the dataset README for the exact Python commands. Nothing is uploaded, published, or submitted to a registry by these tools.

## Global preflight and validator review

The complete 3,104,998,836-byte archive matches provider MD5 `40171f15c0fccd470db32446dda0480e`; its local SHA-256 is `78072f67991b0cf9eb3373c7a9c314c0da826857c698dd03d20421b2d0d3bbec`. The [first global preflight](global-preflight-failure-r1.json) stopped before output creation because NN29 declares decimal UTM fields, unlike the pilot tiles. The [all-tile header inventory](global-dbf-schema-inspection.json) and [complete NN29 UTM inspection](nn29-utm-decimal-inspection.json) document the difference: all 31,494 NN29 UTM values are whole-valued. The common schema now uses exact Decimal columns for both UTM fields; the historical pilot remains unchanged.

Independent review reproduced three validation false-pass paths: equal-valued Arrow type changes, missing source hash/CRS verification, and empty display sample lists. The gates now require exact schema and source bindings, and enforce the frozen sample policy and cardinality. Regression fixtures preserve the refusal cases. These were gaps in the validation gates, not evidence of changed source geometry. New global outputs must pass the tightened gates before release preparation.

The final-schema nine-tile pilot (`pilot-v2`) passes the hardened [all-row source validator](pilot-v2-source-validation-r1.json), including all 36 source-member hashes and exact Arrow types. The native controls were also repeated from a clean checkout: [both GeoParquet and PMTiles bytes match](native-fixtures-r4/rebuild-validation.json). The first two native fixture archives embedded their local output directories in `generator_options`; the builder now invokes the pinned executable with stable relative paths. That metadata-only reproducibility defect is retained in the comparison evidence.

## Additional prepared-dataset gate review

The [code-level follow-up](source-audit/validation-gate-followup-r1.json) found and closed a HydroLAKES directory-input source-pin bypass, incomplete FFR row-group statistics checks, and missing plastic decimal-precision/zoom assertions. Twelve focused rejection/positive tests pass in the locked geospatial environment. No dataset bytes were changed. The new statistics checks also pass across all 8,477,883 retained FFR rows, and all 53 plastic field types plus its zoom range pass on checksum-bound assets. HydroLAKES’ download cache had previously been evicted after verification; its new refusal gate was tested with fixtures, and its original complete source comparison was not rerun.

HydroLAKES, LakeATLAS and FFR source comparisons share their production GDAL decoder. They establish preservation of that decoded source, not a second independent FileGDB/Shapefile implementation or scientific accuracy. HydroLAKES’ full source check uses an order-independent cryptographic feature-digest sum with exact ID coverage; LakeATLAS and FFR use batchwise value/WKB comparisons. The small alternate-reader check for LakeATLAS is a smoke test, not full independent decoding.

The final-schema pilot also passes the tightened [display oracle](pilot-v2-display-validation-r1.json) and all five [browser cases](browser-pilot-v2-r1/report.json). The [attribute addendum](browser-pilot-v2-r1/attribute-values-r2.json) compares all 70 displayed values against exact Arrow values. Its retained first diagnostic used Python’s scientific notation for decimal zero; the follow-up applies the declared fixed-point display contract to the same unchanged browser observations. The current [viewer labels](browser-pilot-v2-r1/readiness-labels.json) count viewable datasets and explicitly identify the historical summary errors.

## Completed global analytical release

All **64,572,998 observations across 829 tiles** passed the [independent source comparison](global-source-validation-r1.json): exact values/nulls, source record IDs, source part/vertex order and XY float64 bits, plus all 3,316 member checksums. There are 435,987 original unknown-width sentinels and no blank width values. The global GeoParquet is 5,529,859,809 bytes, SHA-256 `d37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb`. The [observed clean rebuild](global-clean-rebuild-r1.json) produced identical bytes. Earlier pilot sizes above describe the retained first pilot; final-schema pilot-v2 is 78,903,097 bytes.

The analytical package passes STAC Node 2.0.0, Rashid 0.1.8 packaging checks and the [current Rashid 0.3.0 local-data gate](../../datasets/grwl-raw/releases/raw-v01.01-local-r1/evidence/current-portolan-validation.json). The separate offline stac-check advisory is incomplete; it is not represented as passing. A 4,821-row local/HTTP subset has identical identifier and WKB fingerprints, reading 22,467,893 bytes over HTTP. No public host or GEE comparison was tested.

The [browser controls](global-browser-controls-r2.json) retain five known-error locations and select six observations from broad geographic windows in the frozen source samples. The retained [r1 preflight failure](browser-controls-preflight-r1.json) concerns expected label text only; all selected IDs, bounds, thresholds and source values are unchanged. The corrected harness passed [all five pilot cases](browser-harness-smoke-r1.json), checking 70 exact displayed attributes. The global PMTiles remains provisional until its own oracle and browser checks pass.

## Completed global PMTiles build

The [global display build](global-display-build-r1/build-receipt.json) produced an 11,498,067,077-byte archive (SHA-256 `a1a7787c7ba28ffc271819bddc54339f9bc741aa9ed44ca619d93e809cbad4f5`) bound to the complete analytical release. The native PMTiles integrity check passed. The archive remains provisional while the independent global ID/attribute/geometry oracle and browser checks run. The global PMTiles has one build; byte-identical display reproduction was established on the pilot and native fixtures, not on a second global archive.

## Global display oracle correction

The [first full global display oracle](global-display-validation-r1/display-validation-r1.json) decoded all 333,538 maximum-zoom tiles and compared all 70,155,474 feature occurrences successfully for ID and selected attributes. It failed overall: 303 missing source IDs matched its grid-collapse model, one 4.49 cm source fragment did not, and one frozen geometry sample produced a world-sized planar distance. The failed report and all 304 missing IDs remain unchanged.

The [native diagnostic](global-display-diagnostics-r1/native-quantization-diagnostic.json) reproduces the extra collapse with the pinned Tippecanoe binary. Its zoom-32 integer projection and subsequent world-grid rounding both use half-away-from-zero behavior; a direct NumPy nearest-even grid does not model the two stages. Both tiny PMTiles fixtures are deliberately tracked, approximately 1 KB each, and tests compare all 25 native outcomes and decoded coordinates. The [targeted follow-up](global-display-diagnostics-r1/targeted-followup-r1.json) rechecks every missing source geometry hash: all 304 satisfy the native collapse rule, and exactly one classification changes. This bounded check is not a passing global oracle.

For NR01 source row 1, the opposite-world tile buffer contributes a Point at +180 degrees while the source begins at -180 degrees. Retaining that Point and framing whole components around the source changes the comparison from 40,074,938 m to 1.105 m. Tests still reject a true central-world chord, missing source lines and missing remote parts. Ambiguous references spanning half a world fail closed. A [complete source-bbox scan](global-display-diagnostics-r1/source-compactness-r1.json) finds maximum longitude span 0.002061391 degrees and no half-world records.

The [precommitted correction policy](global-display-diagnostics-r1/control-policy-r2.json) keeps the 30 m geometry tolerance, all original first-eight/longest-eight samples and complete ID/attribute accounting. It adds every source bbox within 30 projected metres of either dateline seam: 56 source-selected candidates, selected before their new display evaluation. Crossing and near-seam ID inventories are reported separately. The finalizer binds the policy, quantizer, native diagnostic and fixture bytes. A new full clean global oracle is required; neither dataset asset has been changed.

## Completed global display and browser validation

The [corrected complete oracle](global-display-validation-r2/display-validation-r2.json) passes against the unchanged data assets. Its [run review](global-display-validation-r2/run-review.json) binds clean runtime commit `b6bb430`, the failed first run, and the precommitted source-only supplement. All 333,538 maximum-zoom tiles and 70,155,474 feature occurrences pass ID and selected-attribute accounting. The 64,572,694 visible IDs plus 304 native quantization collapses account for every analytical source record. All missing geometry hashes remain identical; only NO32/21373 changes classification.

All 13,006 original geometry sample IDs remain, plus 55 unique additions from the 56 source-selected seam candidates. Of 13,061 total controls, 13,053 pass and eight are explicit quantization-collapse exceptions. The largest passing Hausdorff distance is 2.037 m against the unchanged 30 m limit. The 304 missing display fragments are 0.0013–2.93 m long and all remain unchanged in GeoParquet. The original failed report is retained.

All eleven [global browser cases](browser-global-r1/report.json) pass 154 exact displayed attributes, observation-width labels, bounded range reads and CORS. Each case transfers 21.2–22.63 MB of data, below its frozen 128 MiB limit. The [review](browser-global-r1/review.json) identifies the four visually inspected screenshots and distinguishes automated checks from visual inspection. The six broad geographic-window names are rectangular test labels, not continental polygon classifications or exhaustive geographic coverage.

The [final display manifest](../../datasets/grwl-raw/display/raw-v01.01-display-r1/manifest.json) and [finalization report](../../datasets/grwl-raw/display/raw-v01.01-display-r1/reports/finalization/report.json) bind the analytical release, PMTiles, all acceptance evidence and 37 verification-workflow snapshots from clean commit `b498399`. Both packages are prepared locally. The complete global PMTiles has one build; only the pilot and native fixtures have byte-identical display rebuilds. No public hosting, registry submission, GEE parity or new scientific-accuracy assessment is claimed.

The first [product-draft preflight](source-products-preflight-r1.json) rejected the release name because the shared setup/staging parsers accepted hyphens but not internal dots. The [compatibility follow-up](source-products-compatibility-r2.json) permits safe dotted versions while retaining path and length guards; 56 focused product/viewer fixture tests pass. The sealed display package remains unchanged and records the actual successful verification runtime. Its extra generic setup snapshots predate this parser fix; the raw-specific preparation and browser scripts used for acceptance are unchanged. The generic launcher still expects its retained five-product base plan; the documented raw helper extends that base with the complete raw product.

## Completed exact local staging

The [clean staging receipt](source-coop-staging-r1/clean-stage-receipt.json) records a successful run from clean commit `4bcaa18`. The [exact file plan](source-coop-staging-r1/immutable-upload-plan.json) contains 147 immutable files totaling 17,083,817,494 bytes for `nthh/grwl-raw`, plus a separately hashed mutable product README. Every staged file was rehashed. Five small analytical reports/receipt retain the generic planner's inventory-only label; the [parent review](source-coop-staging-r1/review.json) independently matches their bytes to the tracked analytical release at that commit.

Both data packages, the global local viewer and the exact local plan are complete. No product was created, data uploaded, public catalog populated or registry entry submitted. Account verification and public-host checks remain publication gates; the optional stac-check advisory remains incomplete.
