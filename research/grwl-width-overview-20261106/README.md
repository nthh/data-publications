# GRWL width overview, 2026-11-06

Status: **prepared locally / not published**. Display `raw-v01.01-display-r3` is one **3,190,539,066-byte (3.19 GB)** PMTiles archive. The [global oracle](global-r2/oracle.json) passes all 64,572,998 source observations and all 26,060,623 encoded point placements in 4,439 overview tiles. The [combiner](global-r2/combine-report.json) confirms every one of the 588,355 detailed compressed tile payloads is byte-identical to r2. All [20 browser cases](browser-global-r1/report.json), the [visual review](visual-review-r1.json), the corrected regional/heldout checks and [clean replay](clean-replay-r2/report.json) pass. The [immutable finalization](../../datasets/grwl-raw/display/raw-v01.01-display-r3/reports/width-overview/finalization.json) binds those checks and the unchanged analytical release.

The user found that the r2 low-zoom coverage cells could not communicate river widths. This replacement selects original width observations at every overview zoom. It preserves the original source ID, width, validity and an anchor on the original geometry. The widest valid observation per screen-scale cell wins; ties use the smallest source ID. The map describes this sampling explicitly. It does not calculate an average or invent river connections.

The [criteria](criteria.json) are frozen before the new builds. Existing r2 reports remain valid for their stated coverage contract and remain historical evidence; they do not establish width visualization at low zoom.

Development and heldout source tiles retain the prior fixed split. Verification checks every source record against the selected winners, each encoded overview tile, and every compressed detailed tile against r2. Local browser cases cover every integer zoom, known Mississippi observations, the Amazon, dateline and the zoom-8 transition. The unchanged GeoParquet remains the complete analytical product.

No upload, push, GEE request or public-host validation is part of this local task.

The initial regional browser run remains failed because its z7 click automation used map-relative coordinates as page coordinates. Rendering and legend checks completed at every zoom. The automation now adds the canvas offset and chooses an unobstructed hit-test target; the regional rerun and full global run pass the correction. Data and width-selection criteria did not change.

The global browser harness requires the returned analytical feature ID and width-validity flag to match the clicked overview ID and flag; this stronger recorded identity assertion was added after the regional browser rerun. The finalizer requires it in the global report; the completed global run passes this assertion.

The [first global failure](global-failure-r1/diagnosis.json) occurred after scanning all 64,572,998 rows. Wide hash-aggregate states exceeded the 1 GB cap. Producer and verifier now sort externally and consume ordered cell groups with bounded memory. Selection semantics, frozen criteria and resource limits are unchanged. Fresh [regional and heldout checks](memory-correction-regional-review.json) and [clean replay](clean-replay-r2/report.json) passed for the corrected code. The full [global oracle](global-r2/oracle.json) now passes for the corrected code.

## Repeat the width overview workflow

Use a clean committed checkout and the locked `scripts/display_tools` Python environment. The recorded run uses Python 3.12.12 and the existing cached Node dependencies under `scripts/cloud_viewer`; install from the committed lockfiles for a new machine. Keep outputs in durable ignored storage. Every attempt needs a new output path. The frozen resource policy requires 40 GiB free at start, 15 GiB while running, no more than 12 GiB of new task artifacts, two workers, and a shared native-build lock. Run heavy stages sequentially.

Set paths to the complete validated raw GeoParquet and its original conversion manifest, the sealed r2 display package, the unchanged analytical package, and a verified multidataset viewer runtime. The preview preparation checks those inputs; it does not fetch or convert other datasets.

```sh
DP_ROOT=/path/to/clean/data-publications
WIDTH_ROOT=/durable/path/grwl-width-overview-next
SOURCE=/path/to/grwl-raw/global-v1/grwl-raw.parquet
SOURCE_MANIFEST=/path/to/grwl-raw/global-v1/manifest.json
BASELINE=/path/to/grwl-multiscale/raw-v01.01-display-r2
ANALYTIC_PACKAGE=/path/to/grwl-raw/release-inputs-r1-package
NATIVE_LOCK=/path/to/shared/grwl-raw/.native-build.lock
BASE_RUNTIME=/path/to/verified/multidataset-runtime.json

uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/build_width_overview.py" \
  --source "$SOURCE" --source-manifest "$SOURCE_MANIFEST" \
  --output "$WIDTH_ROOT/global" --task-root "$WIDTH_ROOT" --native-lock "$NATIVE_LOCK"

uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/validate_width_overview.py" \
  --source "$SOURCE" --source-manifest "$SOURCE_MANIFEST" \
  --overview "$WIDTH_ROOT/global" --output "$WIDTH_ROOT/global-oracle.json" \
  --task-root "$WIDTH_ROOT" --native-lock "$NATIVE_LOCK"

uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/combine_width_display.py" \
  --baseline "$BASELINE/assets/grwl-raw.pmtiles" \
  --baseline-sha256 79389270fef94a8a6359f0b7a98b3505a82ee090a7827bd13280bf1f1c178830 \
  --overview "$WIDTH_ROOT/global/overview.pmtiles" --overview-report "$WIDTH_ROOT/global-oracle.json" \
  --output "$WIDTH_ROOT/combined" --task-root "$WIDTH_ROOT" --native-lock "$NATIVE_LOCK"
```

The producer parses source WKB directly. The independent verifier uses Shapely and PROJ, scans every source row, independently chooses every cell winner and checks all eight selected-observation tables and every encoded tile. It checks ID, original width, validity, anchor, deterministic ties, buffering and dateline placements. The combiner then compares every compressed detailed tile with r2 and every new overview tile with the verified input. Do not advance on a failed receipt.

Run the same producer and verifier on the frozen development and heldout sources, using separate output paths. The existing pilot has nine tiles and 919,832 rows; the heldout source has eight tiles and 1,132,814 rows. Those manifests are hash-bound in the verifier. Combine the pilot against the retained pilot r2 archive with SHA-256 `662aae13f02ba0766f832d8c2f48c36d846383a6a4d71271258629276ccc6a64`.

Build and bind the local viewer to the candidate archive. Run the server in a separate terminal; use unused loopback ports and a new request log.

```sh
node "$DP_ROOT/scripts/cloud_viewer/build.mjs" --out "$WIDTH_ROOT/ui"
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/prepare_width_preview.py" \
  --base "$BASE_RUNTIME" --source "$SOURCE" --source-manifest "$SOURCE_MANIFEST" \
  --archive "$WIDTH_ROOT/combined/assets/grwl-raw.pmtiles" \
  --overview-report "$WIDTH_ROOT/global-oracle.json" --combine-report "$WIDTH_ROOT/combined/combine-report.json" \
  --output "$WIDTH_ROOT/runtime.json" --origin http://127.0.0.1:8923
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/scripts/cloud_viewer/serve.py" \
  --manifest "$WIDTH_ROOT/runtime.json" --ui-root "$WIDTH_ROOT/ui" \
  --ui-port 8922 --object-port 8923 --log "$WIDTH_ROOT/requests.jsonl"
```

In another terminal, run all 20 frozen browser cases. The harness verifies the actual camera, width legend, symbol diameter, displayed layer, exact-ID source lookup and all 14 analytical attributes at Mississippi z7, completed HTTP 206/CORS bodies, and a 32 MiB cold object-read ceiling. Inspect the saved world, Mississippi, Amazon, dateline and z7/z8 screenshots and retain the review. `--scope pilot` runs only the 13 regional Mississippi cases and cannot satisfy the global finalizer.

```sh
node "$DP_ROOT/scripts/cloud_viewer/width-overview-browser-check.mjs" \
  --url http://127.0.0.1:8922/ --out "$WIDTH_ROOT/browser-global"
```

From a clean committed checkout, reproduce the pilot and the exact served UI. This is a regional byte reproduction, not a second global display build. The replay records the commit, before/after Git status, code hashes and stage logs.

```sh
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/research/grwl-width-overview-20261106/run_width_replay.py" \
  --source /path/to/pilot-v2/grwl-raw.parquet --source-manifest /path/to/pilot-v2/manifest.json \
  --baseline /path/to/pilot-combined-r1/assets/grwl-raw.pmtiles \
  --baseline-sha256 662aae13f02ba0766f832d8c2f48c36d846383a6a4d71271258629276ccc6a64 \
  --reference-overview /path/to/passed/width-pilot --overview-report /path/to/passed/pilot-oracle.json \
  --reference-combined /path/to/passed/width-pilot-combined/assets/grwl-raw.pmtiles \
  --reference-viewer-build "$WIDTH_ROOT/ui/build.json" --output "$WIDTH_ROOT/clean-replay" \
  --task-root "$WIDTH_ROOT" --native-lock "$NATIVE_LOCK"
```

Write a new finalizer input JSON mapping with `baseline`, `analytic_package`, `archive`, `overview_build`, `overview_report`, `combine_report`, `browser_report`, `viewer_build`, and `clean_replay_report`. Each value is the exact local path from the passed stages. Optional `evidence_files` maps safe relative names to extra reports and screenshots. Preserve failed earlier attempts as evidence; they cannot substitute for passing gates. Finalize only after all gates pass:

```sh
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/finalize_width_display.py" \
  --inputs "$WIDTH_ROOT/inputs.json" --output "$WIDTH_ROOT/raw-v01.01-display-r3"
```

The finalizer verifies the sealed r2 inventory, unchanged analytical package, every report binding, current code and viewer hashes, and replay logs. It retains historical nonbulk evidence, snapshots the recipe and served viewer, exports the same width style used by the UI, and writes a new immutable manifest. It never edits canonical records or publishes data.

Bind the passed manifest in `datasets/grwl-raw/dataset.yaml`, retain the former display record as historical evidence, and generate/check repository views. Then use the root locked Python environment for a local upload plan:

```sh
uv run --locked --project "$DP_ROOT" python "$DP_ROOT/scripts/catalog.py" --write
uv run --locked --project "$DP_ROOT" python "$DP_ROOT/scripts/source_products.py" --root "$DP_ROOT" write
uv run --locked --project "$DP_ROOT" python "$DP_ROOT/scripts/publication_catalog.py" check
uv run --locked --project "$DP_ROOT" python "$DP_ROOT/scripts/source_products.py" --root "$DP_ROOT" stage \
  --package "grwl-raw=$ANALYTIC_PACKAGE" \
  --display-package "grwl-raw=$WIDTH_ROOT/raw-v01.01-display-r3" \
  --output "$WIDTH_ROOT/source-coop-plan"
```

Staging writes a checksum-bound local plan for `nthh/grwl-raw`. It does not create a product, upload, publish a catalog or submit to a registry. Public HTTP, CORS, checksum and browser verification follow an authorized upload.

## Completed local staging

The [exact local upload plan](source-coop-plan-r1/immutable-upload-plan.json) passes full package hashing and contains 342 immutable files totaling 8,871,121,787 bytes (8.87 GB) for `nthh/grwl-raw`. The [staging review](source-coop-plan-r1/stage-review.json) records clean publisher commit `df14b48`, publisher hash, analytical/display manifest hashes and plan hash. The only recorded creation/upload blocker is missing account-verification evidence. This does not assert that the user is signed out. No account change, product creation, upload, catalog publication or registry submission was performed.

The existing [viewer address](http://127.0.0.1:8916/?dataset=grwl-raw&region=global) now serves the sealed r3 archive. Its [endpoint check](viewer-release-r3-check.json) verifies the exact tested UI build, archive binding and matching HTTP 206/CORS range bytes at that address.
