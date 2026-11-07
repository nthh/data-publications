# GRWL multiscale display experiment

## Status

The global gates passed. The combined archive is **3,005,034,172 bytes**
(SHA-256 `79389270fef94a8a6359f0b7a98b3505a82ee090a7827bd13280bf1f1c178830`),
73.86% smaller than the 11,498,067,077-byte r1 display archive. Exact comparison
passed all 588,355 detail tiles and 345,749,975 feature occurrences at zooms
8–12; the largest compressed detail tile is 572,212 bytes. All 4,419 overview
tiles matched the source mask, with a 39,813-byte maximum. The independent
source oracle passed all 1,158,798 controls. [Clean replay r2](clean-replay-r2.json)
reproduced every overview mask, both archives, and all viewer files byte for
byte.

The five-case [multiscale browser r2](browser-multiscale-r2/report.json) and
three-case [dataset-switch camera check](browser-camera-r1/report.json) passed;
the multiscale case maximum was 469,789 response bytes. Detail browser r3 passed
all eleven cases and all 154 analytical-field checks, with 20,252,228–21,138,336
cold object bytes per case. The earlier r2 report's 19,783,655-byte footer body
capture failures remain retained in [its diagnosis](browser-detail-r2/diagnosis.json)
and [report](browser-detail-r2/report.json). R3 passed sequentially with the same
code, UI, and criteria; the cause of the r2 capture failure is not established.
See the [r3 report](browser-detail-r3/report.json).

The local r2 package is prepared: 213 files, 3,096,857,190 package bytes,
manifest SHA-256
`bce857fafd55c848f3d3738fc4f86e72825cb0c048a4d3e84df1cf4ea4d94988`.
Its [multiscale finalization report](../../datasets/grwl-raw/display/raw-v01.01-display-r2/reports/multiscale/finalization.json)
records the bound gates. The canonical r2 binding and all generated catalog
checks pass. [Local staging r3](source-coop-staging-r3/stage-summary.json) passed
with **258 immutable files totaling 8,638,948,624 bytes** for `nthh/grwl-raw`.
The [exact plan](source-coop-staging-r3/immutable-upload-plan.json) and
[staging review](source-coop-staging-r3/stage-review.json) bind the clean
publisher checkout and every upload byte. Source Cooperative account
verification is not recorded, so creation/upload readiness remains false. No
upload or public hosting has occurred. The archive ceiling remains
5,529,859,809 bytes.

The earlier [detail browser r1](browser-detail-r1/report.json) passed eleven
cases and all 154 analytical field checks at the same response-byte range. It
predates viewer r3; the current r3 report is the detail-browser acceptance used
by finalization.

The first multiscale browser run failed only at global z0: MapLibre's default
single-world constraint clamped the requested camera to about z1.2 on the
1500×1050 viewport. The viewer now applies an overview-specific transform
constraint that allows world margins and restores the default for other
datasets. The frozen cases, locations, zooms, viewport, and byte limits did not
change. Multiscale r2 passed. The camera check verifies z0 on initial GRWL,
restored default camera behavior on HydroLAKES, and z0 again after switching
back.

Regional development and heldout trials passed their frozen size and semantic
checks. Their records are evidence for the design, not global validation:

| Scope | Detail bytes → combined bytes | Exact detail occurrences | Coverage check |
| --- | ---: | ---: | --- |
| Development | 163,886,604 → 43,732,687 | 4,959,998 | Exact detail comparison passed |
| Heldout | 23,367,106 → 5,881,006 | 703,560 | All 1,132,814 heldout source observations matched the independent coverage oracle |

Reports and checksums are in [regional-results-r1](regional-results-r1/summary.json).
The initial two development preflight refusals and the heldout mixed-row-group
checker refusal are retained. The checker fix corrected its row-group layout
assumption and added regression coverage; it did not change the split or
thresholds. See [heldout criteria](heldout-criteria.json) and the reports beside
the summary.

## Product contract

The analytical GeoParquet remains byte-for-byte unchanged: SHA-256
`d37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb`,
5,529,859,809 bytes, 64,572,998 observations across 829 source tiles. The
sealed detail display is the r1 PMTiles archive (11,498,067,077 bytes). Frozen
source pins, development/heldout tiles, byte limits, and gates are in
[`criteria.json`](criteria.json); the heldout subset has its own source pin in
[`heldout-criteria.json`](heldout-criteria.json).

One vector PMTiles archive will contain two layers:

- `grwl_overview`, zooms 0–7: 512-cell-per-tile occupancy of source observation
  geometry. Closed-cell intersections are evaluated in continuous spherical
  Web Mercator; X wraps periodically at the dateline, and multipart pieces stay
  separate. Each coarser zoom is a 2×2 logical OR. Nonoverlapping horizontal
  cell runs encode as separate valid polygons. These cells mean observation
  coverage; they are not riverbanks, measured widths, or individual features.
- `grwl_raw`, zooms 8–12: retains r1 tile coordinates, multiplicity, source IDs,
  integer geometry commands, and `width_m`/`width_valid` exactly. Only the four
  repeated `_src_xmin`, `_src_ymin`, `_src_xmax`, `_src_ymax` properties are
  removed. Exact all-attribute lookup uses the unchanged GeoParquet by unique
  numeric `feature_id`.

The source Parquet has 8,315 ordered, nonoverlapping `feature_id` row-group
min/max ranges, with no null IDs and IDs within JavaScript's safe-integer range;
the runtime preparation gate rechecks these statistics. Never combine raster
and vector PMTiles. The already documented 304 r1 native quantization
collapses remain unchanged in the display history and all observations remain
in GeoParquet. This work makes no GEE parity or scientific-accuracy claim.

## Size and lookup changes

The old PMTiles repeated four floating-point source bounding-box properties on
rendered features across five detail zooms. Removing those display properties
accounts for the main saving. Exact feature-ID lookup now uses the unchanged
GeoParquet's ordered ID statistics; the browser still retrieves all fourteen
analytical fields. The complete comparison verifies that removing these lookup
properties did not change any detailed geometry, ID, width, or occurrence.

PMTiles and GeoParquet serve different purposes: the 5.53 GB GeoParquet retains
original coordinates and attributes, while PMTiles repeats quantized display
geometry at several zooms. Their sizes need not match. In this build, one
archive with both coverage and detail is 3.01 GB; the separate intermediate
coverage archive is only 18.82 MB. The full combined archive contains 4,419
coverage tiles and 588,355 detail tiles. Temporary build files and the retained
historical r1 archive are separate from the resulting data product.

## Frozen validation and current evidence

The frozen split is nine development tiles and eight heldout tiles. The heldout
selection was pinned from source metadata before heldout extraction or display
metrics. Criteria require exact decoded overview occupancy, independent
heldout/source-boundary checks, valid nonoverlapping grid polygons, and a
nonempty global overview at every zoom 0–7. Detail checks compare every original
detail occurrence, not just unique IDs. Overview gzip tiles are capped at
256 KiB; detail gzip tiles at 1 MiB. The global archive ceiling is the original
analytic source size. A miss requires a newly reviewed design or threshold; do
not tune criteria after results.

The independent source check covers every record in all eight heldout tiles and
the first 32 rows in each other source tile, plus frozen closed-edge, corner,
axis-aligned, zero-length, multipart, dateline, and world-edge fixtures. The
heldout all-record coverage comparison passed. The global independent source
check passed all 1,158,798 controls with zero missing or extra cells; see
[its receipt](global-overview-r1/source-validation-r1.json). The complete archive
checks, five multiscale views, dataset-switch camera check, and clean replay r2
and detail browser r3 have passed. The finalizer prepared local display r2. The
canonical binding, generated checks and local exact-file staging pass. No public
hosting or upload has occurred.

## Repeatable global workflow

Use the existing locked display environment, installed native tools, and
durable ignored work storage. No downloads, GEE jobs, network publication, or
bulk-source copies are part of this workflow. Set paths to the retained r1
packages and source files; paths below are deliberately portable placeholders.

```sh
DP_ROOT=/path/to/data-publications
WORK_ROOT=/durable/path/grwl-multiscale-r2
BASELINE=/path/to/prepared/raw-v01.01-display-r1
ANALYTIC_PACKAGE=/path/to/prepared/raw-v01.01-local-r1
SOURCE=/path/to/retained/grwl-raw.parquet
SOURCE_MANIFEST="$BASELINE/reports/finalization/source-manifest.json"
SOURCE_VALIDATION="$DP_ROOT/research/grwl-raw-release-20261102/global-source-validation-r1.json"
DETAIL="$BASELINE/assets/grwl-raw.pmtiles"
CRITERIA="$DP_ROOT/research/grwl-multiscale-20261103/criteria.json"
OVERVIEW="$WORK_ROOT/global-overview-r1"
REPACK="$WORK_ROOT/global-combined-r1"
mkdir -p "$WORK_ROOT"
```

`SOURCE_MANIFEST` is the sealed source inventory used by the producer and
finalizer. `SOURCE_VALIDATION` is the separate source-validation evidence used
by the browser controls. Keep those bindings distinct. The scripts refuse to
overwrite output paths. Start with at least 40 GiB free; retain at least 15 GiB
while a job runs. Keep one heavy native job active and use the pinned
two-worker `tile-join` binary (version 2.79.0, SHA-256
`da56cb1a2ddf59b2f03798b5314db665dad87bc03cab6f86a03e630e420173fa`). The
Python stages use `scripts/display_tools/uv.lock`; the independent detail wire
oracle uses installed macOS `clang++` and zlib, with no compiler download.
These native pins describe the tested macOS/Homebrew setup, including
`/opt/homebrew/bin/tile-join`; portable data paths do not make that executable
Linux-portable. A different native environment needs recorded executable and
compiler pins plus the same replay and gates. Output formats remain portable.

```sh
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/build_overview.py" \
  --source "$SOURCE" --source-manifest "$SOURCE_MANIFEST" \
  --output "$OVERVIEW" --task-root "$WORK_ROOT"

uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/validate_overview.py" source \
  --criteria "$CRITERIA" --source "$SOURCE" --source-manifest "$SOURCE_MANIFEST" \
  --mask "$OVERVIEW/masks/z7.bin" --report "$WORK_ROOT/overview-source.json"

OVERVIEW_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifacts"]["overview.pmtiles"]["sha256"])' "$OVERVIEW/build.json")
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/repack_detail.py" \
  --detail "$DETAIL" --source-sha256 a1a7787c7ba28ffc271819bddc54339f9bc741aa9ed44ca619d93e809cbad4f5 \
  --overview "$OVERVIEW/overview.pmtiles" --overview-sha256 "$OVERVIEW_SHA256" \
  --output "$REPACK" --task-root "$WORK_ROOT" --criteria "$CRITERIA" \
  --native-lock "$WORK_ROOT/.native-build.lock"

# Bind the actual candidate checksum; keep a separate immutable report per gate.
CANDIDATE="$REPACK/assets/grwl-raw.pmtiles"
CANDIDATE_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["archive"]["sha256"])' "$REPACK/manifest.json")
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/compare_detail_fast.py" \
  --source "$DETAIL" --source-sha256 a1a7787c7ba28ffc271819bddc54339f9bc741aa9ed44ca619d93e809cbad4f5 \
  --candidate "$CANDIDATE" --candidate-sha256 "$CANDIDATE_SHA256" --allow-overview \
  --native-build-dir "$WORK_ROOT/native-oracle-r1" --report "$WORK_ROOT/detail-comparison.json" \
  --criteria "$CRITERIA" --workers 2

uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/validate_overview.py" archive \
  --criteria "$CRITERIA" --archive "$CANDIDATE" --mask "$OVERVIEW/masks/z7.bin" \
  --report "$WORK_ROOT/overview-archive.json"
```

Do not proceed unless the exact detail comparison, independent overview
archive oracle, and independent source oracle all pass. Preserve every failure
receipt. The finalizer also checks their input hashes and refuses an existing
output.

## Local runtime and browser gates

The preview is an update to a retained, verified multidataset runtime that
already contains `grwl-raw`; it is not a self-contained viewer package. It
copies neither the large source nor archive. Use a new preview config, UI build,
server ports, and browser output directories for each attempt.

```sh
BASE_RUNTIME=/path/to/retained/verified-multidataset-runtime.json
VIEWER_DIST="$WORK_ROOT/viewer-r3/ui"
PREVIEW_CONFIG="$WORK_ROOT/runtime-preview.json"
node "$DP_ROOT/scripts/cloud_viewer/build.mjs" --out "$VIEWER_DIST"
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/prepare_multiscale_preview.py" \
  --base "$BASE_RUNTIME" --source "$SOURCE" --source-manifest "$SOURCE_MANIFEST" \
  --archive "$CANDIDATE" --detail "$WORK_ROOT/detail-comparison.json" \
  --overview "$WORK_ROOT/overview-archive.json" --source-check "$WORK_ROOT/overview-source.json" \
  --output "$PREVIEW_CONFIG" --origin http://127.0.0.1:8917

uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/scripts/cloud_viewer/serve.py" \
  --manifest "$PREVIEW_CONFIG" --ui-root "$VIEWER_DIST" --ui-port 8916 --object-port 8917 \
  --log "$WORK_ROOT/preview-requests.jsonl"

node "$DP_ROOT/scripts/cloud_viewer/raw-browser-check.mjs" \
  --url http://127.0.0.1:8916/ --out "$WORK_ROOT/browser-detail-r3" \
  --controls "$DP_ROOT/research/grwl-multiscale-20261103/browser-controls-r1.json"
cd "$DP_ROOT"
node "$DP_ROOT/scripts/cloud_viewer/multiscale-browser-check.mjs" \
  --url http://127.0.0.1:8916/ --out "$WORK_ROOT/browser-multiscale-next"
```

The detail harness checks all eleven frozen source cases and all fourteen
analytical fields. The multiscale harness checks global z0, Amazon z3, the
known z7 location, the z7→z8 transition, and a source-derived NR01 dateline
anchor. Each multiscale case uses a fresh browser context and verifies local
HTTP 206/CORS range bodies under a 32 MiB cold-read ceiling. These checks are
local runtime acceptance, not a public-host test.

The first global-z0 failure and diagnosis are retained in
[`browser-multiscale-r1`](browser-multiscale-r1/diagnosis.json); the successful
rerun is [`browser-multiscale-r2`](browser-multiscale-r2/report.json). No
criteria changed. Run the camera switch regression against the same local UI
origin with a fresh output directory:

```sh
node "$DP_ROOT/scripts/cloud_viewer/camera-browser-check.mjs" \
  --url http://127.0.0.1:8916/ --out "$WORK_ROOT/browser-camera-next"
```

The current three-case result is [browser-camera-r1](browser-camera-r1/report.json).
The retained [detail-browser r2 failure](browser-detail-r2/report.json) was
followed by a passing [detail-browser r3 run](browser-detail-r3/report.json).
R3 used the same code, UI, and criteria sequentially. Preserve r2 as failed
evidence; the two outcomes do not establish a specific cause.

## Clean replay

From a clean committed checkout with the same installed dependencies, run the
frozen nine-tile replay before finalization. The reference folders below are the
retained development pilot, including its masks and combined archive. The runner
refuses a dirty checkout and verifies identical masks, overview, combined PMTiles
and served viewer bytes. It records the exact code hashes and stage logs.

```sh
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/research/grwl-multiscale-20261103/run_clean_replay.py" \
  --source /path/to/pilot-v2/grwl-raw.parquet --source-manifest /path/to/pilot-v2/manifest.json \
  --detail /path/to/pilot-display-v3/assets/grwl-raw.pmtiles \
  --reference-overview /path/to/pilot-overview-r1 --reference-display /path/to/pilot-combined-r1 \
  --reference-viewer-build "$VIEWER_DIST/build.json" --task-root "$WORK_ROOT" \
  --output "$WORK_ROOT/clean-replay-r2" --native-lock "$WORK_ROOT/.native-build.lock"
```

The source/native lock must be shared by all local builds. Wait for a running
native job to finish before starting this replay. The completed
[clean-replay-r2 receipt](clean-replay-r2.json) records byte equality for the
overview masks, overview archive, combined archive, viewer build, and every
viewer file.

## Finalize and stage locally

The sealed r2 package retains the producer and verifier snapshots used at
finalization (`8d0f4fe`). The first local upload-plan attempt then exposed missing
MIME mappings for `.log`, `.cpp`, `.wasm` and extensionless compiled checkers
under `workflow/native-oracle/`; its [failed receipt and diagnosis](source-coop-staging-r2/diagnosis.json)
are retained. The corrected publisher is tested and pinned separately in the
[staging review](source-coop-staging-r3/stage-review.json) (`d46a942`). All 35
publisher tests pass, including evidence MIME coverage and tamper rejection.
This publisher-only correction leaves the prepared package,
converter, archive and browser evidence unchanged. An exact production replay
uses the recorded production checkout; staging uses its recorded publisher
checkout. Fresh builds with changed recipe code require fresh replay receipts.

The finalizer passed and prepared the local r2 package. Its
[finalization receipt](../../datasets/grwl-raw/display/raw-v01.01-display-r2/reports/multiscale/finalization.json)
binds the archive and reports. For a replay, write an explicit `inputs.json`
mapping for `datasets/grwl-raw/finalize_multiscale.py`. Required
keys are `archive`, `baseline`, `analytic_package`, `detail_report`,
`overview_build`, `overview_archive_report`, `overview_source_report`,
`finest_mask`, `browser_detail_report`, `browser_multiscale_report`, and
`viewer_build`, and `clean_replay_report`. Use the current passing reports:
[`detail-comparison-r1.json`](global-combined-r1/detail-comparison-r1.json),
[`build.json`](global-overview-r1/build.json),
[`overview-validation-r1.json`](global-combined-r1/overview-validation-r1.json),
[`source-validation-r1.json`](global-overview-r1/source-validation-r1.json),
[`browser-multiscale-r2/report.json`](browser-multiscale-r2/report.json), and
[`clean-replay-r2.json`](clean-replay-r2.json). Bind `viewer_build` to the r3
UI build used by browser runs r2/r3 and clean replay r2. Use
[`browser-detail-r3/report.json`](browser-detail-r3/report.json) for
`browser_detail_report`; the r2 body-capture failure remains in the record but
does not replace the passing r3 report. Optional keys include
`source_manifest`, `repack_manifest`, `repack_provenance`, and `evidence_files`
(the camera report may be retained there). Keep `$OVERVIEW/masks/z7.bin` and all
report paths exact and immutable. Then run:

```sh
uv run --locked --project "$DP_ROOT/scripts/display_tools" python "$DP_ROOT/datasets/grwl-raw/finalize_multiscale.py" \
  --inputs "$WORK_ROOT/inputs.json" --output "$WORK_ROOT/raw-v01.01-display-r2-replay"
```

The successful output is the prepared local r2 package described above. The
canonical r2 binding and generated checks pass. `scripts/source_products.py
stage` verifies the analytic and display packages and writes an exact local plan:

```sh
python3 "$DP_ROOT/scripts/source_products.py" --root "$DP_ROOT" stage \
  --package "grwl-raw=$ANALYTIC_PACKAGE" \
  --display-package "grwl-raw=$WORK_ROOT/raw-v01.01-display-r2" \
  --output "$WORK_ROOT/source-coop-plan-next"
```

Staging is not uploading. Do not run an upload or push as part of this workflow.
For original acquisition, conversion, and r1 gates, use the established
[GRWL raw workflow](../../datasets/grwl-raw/README.md). For the viewer runtime
and local server contract, see [cloud viewer documentation](../../scripts/cloud_viewer/README.md).
