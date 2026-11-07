# GRWL raw vectors V01.01

## GEE review — 2026-11-06

Live raw-V01.01 GEE count and all 512 sampled compound keys match; all 5,120 source attribute cells are exact. Selected mixed geometry diagnostics are below 0.340 m, but strict geometry parity fails. No exhaustive GEE, topology-preservation or independent scientific-accuracy claim. See the [complete comparison review](../../research/gee-release-validation-20261106/README.md) and [structured evidence](../../research/gee-release-validation-20261106/summary.json). The validated release is [public on Source Cooperative](https://source.coop/nthh/grwl-raw); hosting checks do not change these scientific-comparison findings.


This is a separate producer-intake record for the raw GRWL vector component, not a replacement or new version of [`datasets/grwl`](../grwl/dataset.yaml). The two records have different scientific scopes. The existing `grwl` record covers the producer's simplified global SummaryStats network and its segment-level summary fields. This record covers the detailed tiled vector observations with their original source records and ten DBF fields.

The raw component is `GRWL_vector_V01.01.zip` from the [official Zenodo record](https://zenodo.org/records/18624542). Its pinned size is 3,104,998,836 bytes and provider MD5 is `40171f15c0fccd470db32446dda0480e`. The complete global conversion contains **64,572,998 observations in 829 tiles**, and is **5,529,859,809 bytes**. Every source record passed an independent comparison of geometry, attributes and identity; all 3,316 SHP/SHX/DBF/PRJ checksums passed. A complete rebuild from an observed clean checkout produced identical GeoParquet bytes. These checks establish conversion fidelity, not independent scientific accuracy or GEE parity.

Both global releases are **publicly hosted and verified on Source Cooperative**: analytical `raw-v01.01-local-r1` and display `raw-v01.01-display-r3`. One **3,190,539,066-byte (3.19 GB)** PMTiles archive shows source widths at zooms 0–12. The 5,529,859,809-byte analytical GeoParquet is unchanged and retains its passed STAC, standalone Portolan and bounded HTTP/DuckDB checks. The optional stac-check advisory remains incomplete. Both releases passed all seven [hosted checks](../../research/source-publication-20261106/hosted-results/grwl-raw/hosted-validation.json). No registry submission has been made.

## Data contract

The GeoParquet workflow preserves each SHP record independently, its tile and original 1-based record ordinal, all parts and vertices in original order, and all XY float64 bits. It preserves all ten DBF fields—`utm_east`, `utm_north`, `width_m`, `nchannels`, `segmentID`, `segmentInd`, `lakeFlag`, `lon`, `lat`, and `elev_m`—using exact integer or decimal values and nulls. The common schema stores UTM east/north as decimal128(38,18), along with the other decimal-valued fields; `width_m`, `segmentID`, `segmentInd` and `elev_m` remain int64. All 829 DBF headers were inspected before the global build. NN29 declares decimal UTM fields even though its 31,494 coordinate values are whole-valued; the retained first pilot used integer UTM columns. IDs derive from tile identity plus source ordinal; `segmentID` is not globally unique. Do not connect records by `segmentID`, `segmentInd`, tile, or proximity.

`width_m=1` remains the producer's unknown-width sentinel. `width_valid` records whether a width is usable; it does not change the original value. The raw record contains per-source observations, not the summary product's segment-level means or other aggregate statistics. No value such as `width_mean` is fabricated.

The PMTiles is a separate display derivative following the [width overview contract](../../research/grwl-width-overview-20261106/criteria.json). At zooms 0–7 it selects the widest valid original observation per screen-scale cell; ties use the smallest source ID. A point is anchored on the original geometry and retains the source ID, original width and validity. Circle diameter uses the same width scale as detailed lines. The symbols are exaggerated and capped at the legend maximum; they do not represent averages or mapped riverbanks. At zooms 8–12 all detailed compressed tile payloads are byte-identical to r2. Source records remain independent; no connecting lines are invented. Dateline splitting remains display-only. The record excludes masks, the optional tile index and the RSSA basin supplement.

## Current status and gates

Status is **published and hosted-verified**. The complete raw source comparison and byte-identical analytical rebuild are recorded in [global-source-validation-r1.json](../../research/grwl-raw-release-20261102/global-source-validation-r1.json) and [global-clean-rebuild-r1.json](../../research/grwl-raw-release-20261102/global-clean-rebuild-r1.json).

The new [independent global overview oracle](../../research/grwl-width-overview-20261106/global-r2/oracle.json) checks **all 64,572,998 source records**, every selected ID/width/anchor at eight zooms, and **all 26,060,623 encoded point placements in 4,439 tiles**. The largest compressed overview tile is 823,771 bytes. The [combined-archive comparison](../../research/grwl-width-overview-20261106/global-r2/combine-report.json) confirms all **588,355 detailed tile payloads are unchanged**. Their earlier complete semantic comparison covers 345,749,975 detailed feature occurrences. The same **304 enumerated source fragments** collapse to tile-grid points at z12 and remain preserved in GeoParquet; this update introduces no new detailed omissions.

All **20 [global browser cases](../../research/grwl-width-overview-20261106/browser-global-r1/report.json)** pass: Mississippi at every integer zoom 0–12, plus Amazon and dateline controls. The z7 click resolves the original source ID, width, validity and all fourteen analytical attributes. Every object read is a completed HTTP 206/CORS range, with a maximum of **20,941,975 bytes (20.94 MB)** for a cold case. The [visual review](../../research/grwl-width-overview-20261106/visual-review-r1.json) confirms width differences and the z7/z8 transition in the reviewed views. The viewer retains its existing non-wrapping world edge; dateline checks do not claim a continuous two-sided viewport. These are local conversion and rendering checks, not public-host, GEE or independent scientific validation.

The corrected pilot and heldout builds pass their full source/tile checks. A [clean regional replay](../../research/grwl-width-overview-20261106/clean-replay-r2/report.json) reproduces all selected-observation tables, overview and combined PMTiles, and served viewer files byte-for-byte from committed code. There is one successful global display build; no second successful global display byte rebuild is claimed. The [immutable finalization report](display/raw-v01.01-display-r3/reports/width-overview/finalization.json) binds the analytical package, display, independent reports, recipe, tool pins and exact served UI. The first global memory-limit failure and regional click-automation failure remain documented in the [width workflow](../../research/grwl-width-overview-20261106/README.md).

[Open the local UI reading Source objects](http://127.0.0.1:8918/?dataset=grwl-raw&layer=grwl-raw-display). The historical summary remains available as a labeled comparison with known errors. The local r3 package is `.local/grwl-width-overview/raw-v01.01-display-r3`. Public hosting has passed; registry submission remains a separate decision.

The [published Source product](https://source.coop/nthh/grwl-raw) contains the unchanged analytical release, r3 display and retained evidence. The exact [upload plan](../../research/source-publication-20261106/staging-r2/immutable-upload-plan.json), [complete upload receipts](../../research/source-publication-20261106/upload-receipts/grwl-raw/summary.json), [hosted validation](../../research/source-publication-20261106/hosted-results/grwl-raw/hosted-validation.json) and [public-listing receipt](../../research/source-publication-20261107/public-listings-r1/grwl-raw.json) record the completed publication. The original local staging review remains historical evidence. The aggregate catalog deployment and registry decision are separate.

## Repeat the current width workflow

Use the [committed width overview commands](../../research/grwl-width-overview-20261106/README.md) for bounded selection, independent source and tile checks, exact detailed-payload preservation, clean replay, browser acceptance, immutable finalization and local Source Cooperative staging. The [r2 coverage workflow](../../research/grwl-multiscale-20261103/README.md) remains a historical baseline. Original source acquisition, conversion and first display-building commands follow below.

## Repeat raw conversion and r1 baseline

Use durable ignored storage for the large source and outputs. Set new paths for each run; the tools refuse to overwrite prior output. Commands below use the repository's locked GIS/display environment for the Python geospatial tools.

```sh
DATA_PUBLICATIONS_ROOT=/path/to/data-publications
GRWL_RAW_TASK_ROOT=/durable/path/grwl-raw
GRWL_RAW_SOURCE_ROOT="$GRWL_RAW_TASK_ROOT/source"
GRWL_RAW_OUTPUT_ROOT="$GRWL_RAW_TASK_ROOT/releases/raw-v01.01-r1"
GRWL_RAW_DISPLAY_ROOT="$GRWL_RAW_TASK_ROOT/display/raw-v01.01-display-r1"
GRWL_RAW_ARCHIVE="$GRWL_RAW_SOURCE_ROOT/GRWL_vector_V01.01.zip"

mkdir -p "$GRWL_RAW_SOURCE_ROOT"
uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/acquire.py" \
  --output "$GRWL_RAW_SOURCE_ROOT"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/build_global.py" \
  --archive "$GRWL_RAW_ARCHIVE" --output "$GRWL_RAW_OUTPUT_ROOT" \
  --criteria "$DATA_PUBLICATIONS_ROOT/research/grwl-raw-release-20261102/global-criteria.json"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/validate.py" \
  --archive "$GRWL_RAW_ARCHIVE" \
  --parquet "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --report "$GRWL_RAW_OUTPUT_ROOT/source-validation.json"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/build_display.py" \
  --source "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --source-manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --fidelity "$GRWL_RAW_OUTPUT_ROOT/source-validation.json" \
  --output "$GRWL_RAW_DISPLAY_ROOT" --task-root "$GRWL_RAW_TASK_ROOT" \
  --criteria "$DATA_PUBLICATIONS_ROOT/research/grwl-raw-release-20261102/global-criteria.json"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/validate_display.py" \
  --parquet "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --source-manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --fidelity "$GRWL_RAW_OUTPUT_ROOT/source-validation.json" \
  --pmtiles "$GRWL_RAW_DISPLAY_ROOT/assets/grwl-raw.pmtiles" \
  --report "$GRWL_RAW_DISPLAY_ROOT/display-validation.json"
```

### Clean analytical rebuild and package

Repeat the same conversion from a clean detached checkout before packaging. The runner records observed Git cleanliness, code and lock hashes, exit status, manifest identity and resulting Parquet hash. Reuse an existing environment only when it matches the committed lock.

```sh
GRWL_RAW_CLEAN_CHECKOUT="$HOME/.folia-fleets/grwl-raw-reproduction/tree"
git -C "$DATA_PUBLICATIONS_ROOT" worktree add --detach "$GRWL_RAW_CLEAN_CHECKOUT" HEAD
uv sync --locked --project "$GRWL_RAW_CLEAN_CHECKOUT/scripts/display_tools"
python "$DATA_PUBLICATIONS_ROOT/research/grwl-raw-release-20261102/run_clean_global.py" \
  --checkout "$GRWL_RAW_CLEAN_CHECKOUT" \
  --python "$GRWL_RAW_CLEAN_CHECKOUT/scripts/display_tools/.venv/bin/python" \
  --archive "$GRWL_RAW_ARCHIVE" --output "$GRWL_RAW_TASK_ROOT/rebuild-r1" \
  --receipt "$GRWL_RAW_TASK_ROOT/rebuild-r1-clean.json"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/release_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/prepare_release.py" \
  --original-manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --rebuild-manifest "$GRWL_RAW_TASK_ROOT/rebuild-r1/manifest.json" \
  --original-parquet "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --rebuild-parquet "$GRWL_RAW_TASK_ROOT/rebuild-r1/grwl-raw.parquet" \
  --source-validation "$GRWL_RAW_OUTPUT_ROOT/source-validation.json" \
  --clean-receipt "$GRWL_RAW_TASK_ROOT/rebuild-r1-clean.json" \
  --output-dir "$GRWL_RAW_TASK_ROOT/release-inputs-r1"

npm --prefix "$DATA_PUBLICATIONS_ROOT/scripts/release_tools" ci --ignore-scripts --no-audit --no-fund
uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/release_tools" \
  python "$DATA_PUBLICATIONS_ROOT/scripts/release_tools/package_release.py" \
  "$GRWL_RAW_TASK_ROOT/release-inputs-r1/release-spec.json"
```

The package specification is generated only after all source evidence and both actual Parquet files match. The packager independently checks copied bytes, STAC, Portolan, local HTTP ranges and a nonempty local/remote subset. `release-inputs-r1-package` is a new immutable output; source data and earlier failed attempts remain unchanged. The current standalone Portolan gate is under `tools/portolan`; its optional advisory is reported separately.

### Display and browser release gate

Generate browser controls from the passed source report with `research/grwl-raw-release-20261102/prepare_global_browser_controls.py`. Its policy fixes five reported-error observations and six observations selected from broad geographic windows before evaluating display output. Run `prepare_preview.py` against a base local viewer runtime, then `scripts/cloud_viewer/raw-browser-check.mjs` against the generated loopback viewer. The report binds the exact source, PMTiles and controls, checks all fourteen displayed fields and width labels, and caps each case at 128 MiB of data response bodies. It makes no request to public data hosts.

`finalize_display.py` consumes the provisional PMTiles, independent display oracle and missing-ID enumeration, the eleven-case browser report, and the prepared analytical package. Its `--fidelity` input is the normalized `release-inputs-r1/source-fidelity.normalized.json`; the oracle and display builder use the original source-validation report. Finalization creates a separate output and preserves the original build. It refuses incomplete evidence, wrong asset hashes, missing controls and unexpected ID loss. Only the finalized manifest may be pinned under `publication.display` and included in a local Source Cooperative upload plan. Upload, public-host checks and registry submission are separate actions.

Use an existing verified base viewer runtime that does not already include `grwl-raw`. The [viewer launcher](../../scripts/cloud_viewer/README.md) explains how to generate that base from the other retained packages. Each path below must be new for a new attempt.

```sh
GRWL_RAW_BASE_VIEWER=/absolute/path/to/base/runtime-config.json
GRWL_RAW_VIEWER_ROOT="$GRWL_RAW_TASK_ROOT/viewer-r1"
GRWL_RAW_BROWSER_CONTROLS="$GRWL_RAW_TASK_ROOT/browser-controls-r1.json"
GRWL_RAW_FINAL_DISPLAY_ROOT="$GRWL_RAW_TASK_ROOT/raw-v01.01-display-r1"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/research/grwl-raw-release-20261102/prepare_global_browser_controls.py" \
  --source-validation "$GRWL_RAW_OUTPUT_ROOT/source-validation.json" \
  --source-manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --parquet "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --output "$GRWL_RAW_BROWSER_CONTROLS"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/prepare_preview.py" \
  --base "$GRWL_RAW_BASE_VIEWER" \
  --source "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --source-manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --display "$GRWL_RAW_DISPLAY_ROOT" \
  --validation "$GRWL_RAW_DISPLAY_ROOT/display-validation.json" \
  --output "$GRWL_RAW_VIEWER_ROOT/runtime-config.json" \
  --origin http://127.0.0.1:8915

npm --prefix "$DATA_PUBLICATIONS_ROOT/scripts/cloud_viewer" ci --ignore-scripts --no-audit --no-fund
npm --prefix "$DATA_PUBLICATIONS_ROOT/scripts/cloud_viewer" run setup
node "$DATA_PUBLICATIONS_ROOT/scripts/cloud_viewer/build.mjs" --out "$GRWL_RAW_VIEWER_ROOT/ui"
```

Run the following server in a separate terminal with the same variables. Stop only that server before reusing its ports. Browser dependency setup can download pinned runtime files; the viewer and browser checks serve data from loopback only.

```sh
uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/release_tools" \
  python "$DATA_PUBLICATIONS_ROOT/scripts/cloud_viewer/serve.py" \
  --manifest "$GRWL_RAW_VIEWER_ROOT/runtime-config.json" \
  --ui-root "$GRWL_RAW_VIEWER_ROOT/ui" --ui-port 8914 --object-port 8915 \
  --log "$GRWL_RAW_VIEWER_ROOT/requests.jsonl"
```

Then check the global display and finalize a separate package:

```sh
node "$DATA_PUBLICATIONS_ROOT/scripts/cloud_viewer/raw-browser-check.mjs" \
  --url http://127.0.0.1:8914 --controls "$GRWL_RAW_BROWSER_CONTROLS" \
  --out "$GRWL_RAW_TASK_ROOT/browser-r1"

uv run --locked --project "$DATA_PUBLICATIONS_ROOT/scripts/display_tools" \
  python "$DATA_PUBLICATIONS_ROOT/datasets/grwl-raw/finalize_display.py" \
  --source-manifest "$GRWL_RAW_OUTPUT_ROOT/manifest.json" \
  --fidelity "$GRWL_RAW_TASK_ROOT/release-inputs-r1/source-fidelity.normalized.json" \
  --source-parquet "$GRWL_RAW_OUTPUT_ROOT/grwl-raw.parquet" \
  --provisional-display "$GRWL_RAW_DISPLAY_ROOT" \
  --oracle "$GRWL_RAW_DISPLAY_ROOT/display-validation.json" \
  --missing-ids "$GRWL_RAW_DISPLAY_ROOT/display-validation.maxzoom-missing.jsonl" \
  --browser-controls "$GRWL_RAW_BROWSER_CONTROLS" \
  --browser-report "$GRWL_RAW_TASK_ROOT/browser-r1/report.json" \
  --analytic-package "$GRWL_RAW_TASK_ROOT/release-inputs-r1-package" \
  --output-dir "$GRWL_RAW_FINAL_DISPLAY_ROOT"
```

After reviewing the final manifest, pin its repository path and SHA-256 under `publication.display` in the canonical record, regenerate drafts, and use `scripts/source_products.py stage --package grwl-raw=… --display-package grwl-raw=… --output …` to produce a local file plan. See [Source Cooperative staging](../../docs/source-cooperative-products.md) for the exact contract. That command transfers no data and creates no remote product.

The raw analytical acceptance contract is [`criteria.json`](../../research/grwl-raw-release-20261102/criteria.json); the current display contract is the separate [width overview criteria](../../research/grwl-width-overview-20261106/criteria.json). The current source pins, completed release evidence, current Source Cooperative publication, and related-summary comparison are recorded in [`dataset.yaml`](dataset.yaml). The public product is [`nthh/grwl-raw`](https://source.coop/nthh/grwl-raw).

The final-schema pilot produced 78.90 MB of analytical Parquet and 163.89 MB of PMTiles. The complete analytical file is 5.53 GB. [The global resource plan](../../research/grwl-raw-release-20261102/global-criteria.json) records the resulting storage estimate and a 48 GiB ceiling for source, outputs and temporary files. The two-thread native limit and 40/15 GiB disk floors are unchanged.

<!-- related-datasets:start -->

## Related datasets

Generated from `related_datasets` in [dataset.yaml](dataset.yaml). These references describe alternatives and complementary uses; they do not add datasets to the processing queue. The comparisons are based on the cited documentation, not an equivalence or accuracy benchmark.

### [Global River Width from Landsat — simplified global river network V01.02](<https://gee-community-catalog.org/projects/grwl/>)

- **Relationship:** Derived product. The summary retains historical segment-level aggregate statistics. Its inspected geometry contains erroneous connectors and is withheld from publication; use the raw record for detailed per-observation geometry and original DBF fields.
- **Local record:** [dataset.yaml](../grwl/dataset.yaml)
- **Coverage:** Global simplified network with 42,077 generalized records; the separate raw component has 829 tiles and 64,572,998 source observations.; Individual source observations nominally represent approximately 30 m Landsat-derived river-width segments; this description does not assert uniform positional accuracy.; Static Landsat-derived producer release V01.01; underlying observation dates vary.
- **Formats:** Producer simplified-vector Shapefile source, Historical summary GeoParquet and PMTiles; publication withheld after geometry review
- **Access:** Producer raw vectors are available from the Zenodo record. The related summary product is a separate canonical record and scope.
- **Comparison:** The summary product has 42,077 generalized records and segment-level statistics, unlike the raw component's many tiled source records and per-record widths. Nine-tile comparison confirmed straight summary connectors absent from raw vectors at source rows 11839, 13164, 15394, 15397, and 15450. Those findings establish known sampled discrepancies, not a global accuracy result. The raw conversion does not invent summary statistics such as width\_mean.
- **Reviewed:** 2026-11-03. **Sources:** [Producer GRWL V01.01 Zenodo record](<https://zenodo.org/records/18624542>), [Frozen raw-versus-summary discrepancy findings](<https://gee-community-catalog.org/projects/grwl/>).

<!-- related-datasets:end -->
