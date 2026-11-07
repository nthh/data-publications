# Dataset viewer

The current Source preview reads five datasets as six display layers, including both LakeATLAS polygons and pour points. PMTiles provides map display and GeoParquet provides complete source attributes through HTTP byte ranges. The local UI reads dataset bytes directly from Source Cooperative. See the [hosted preparation and validation workflow](../source_publish/README.md) for exact URL bindings, frozen cases and acceptance commands.

GRWL uses one 3.19 GB `raw-v01.01-display-r3` archive. Zooms 0–7 show selected original-width observations with source IDs; zooms 8–12 show detailed observations with width-dependent line styling. The [width workflow](../../research/grwl-width-overview-20261106/README.md) documents preparation and validation. The prepared Source preview runs at <http://127.0.0.1:8918/?dataset=grwl-raw&layer=grwl-raw-display> on the local machine.

The original local launcher below includes four prepared releases plus the retained GRWL summary comparison as six layers. The summary is withheld from publication because inspected straight connectors exist in its producer geometry but are absent from raw vectors. The separate [raw preview](../../datasets/grwl-raw/README.md) uses the complete original observations. Local servers serve static bytes and do not publish or upload datasets.

## Start or restart

Use Node.js 22 or newer and the repository's locked Python release environment.
From the repository root, install the small browser dependencies once:

```sh
npm --prefix scripts/cloud_viewer ci --ignore-scripts --no-audit --no-fund
npm --prefix scripts/cloud_viewer run setup
```

The setup step downloads the SHA-256-pinned Parquet extension from DuckDB's
[official extension service](https://duckdb.org/2023/12/18/duckdb-extensions-in-wasm).
The npm lock pins the browser libraries. Subsequent builds use that cached
extension and need no network access.

With the existing complete release packages under the main checkout's `.local`:

```sh
uv run --locked --project scripts/release_tools python scripts/cloud_viewer/run.py \
  --data-root "$HOME/projects/data-publications/.local"
```

Open <http://127.0.0.1:8910/>. The object origin is
`http://127.0.0.1:8911`. The launcher prints the server PID and creates a fresh
ignored `.local/cloud-viewer-runs/run-…/` containing its private runtime map,
built UI and logs. It verifies every file against the immutable upload plan
before serving. It reads existing packages in place, without copying bulk data.
Stop that specific server with `kill -INT <printed-PID>` before restarting on
the same ports. Alternative ports use `--ui-port` and `--object-port`.

The package locations are discovered from the canonical records and frozen plan.
For a different local layout, repeat `--package DATASET_ID=/absolute/package/path`
and `--display-package DATASET_ID=/absolute/display/package/path`. Display
packages are discovered under `<data-root>/<id>/display/<display-release>/`.
The default plan requires four versioned display packages, including the corrected GRWL display. To review an older
frozen plan explicitly, pass its `--plan` path and `--legacy-plan`; this does not
change the current product configuration.
Missing, ambiguous, mismatched or modified packages fail preparation; the launcher
does not download datasets. A new checkout therefore needs access to the retained
packages as well as the small tracked repository files.

## Browse

Select a dataset, choose a region or pan/zoom, and click a feature to inspect
attributes. All six map layers load PMTiles automatically. **Load all attributes**
reads the remaining fields for that source ID from the analytical GeoParquet.
Decimal fields are projected as exact decimal text, preserving their scale and
nulls instead of exposing Arrow storage integers.
LakeATLAS has separate polygon and pour point buttons. Expand **Source & file
details** for the release, checksum, source link, license and analytical links.

| Dataset | Map layer | Display behavior |
| --- | --- | --- |
| GRWL summary (historical comparison) | Retained PMTiles river lines | Display dateline bug fixed; producer summary connectors remain. Thickness uses `width_mean`. |
| River-plastic inputs | Existing PMTiles points | Zoom to reveal more points |
| HydroLAKES | New PMTiles polygons | Lakes appear by area; all eligible IDs at z12 |
| Free-Flowing Rivers | New PMTiles lines | Reaches appear by discharge; z12 coverage is audited |
| LakeATLAS | New PMTiles polygons and pour points | Separate layers; features appear by lake area |
| Global Dam Watch; SWOT Prior Lake | Unavailable | Current blockers shown; no substitute data |

GRWL's legend shows 50 m, 200 m and ≥1,000 m mean-width examples at the current
zoom. Thickness is a deliberately exaggerated map symbol, capped above 1,000 m;
it is not a depiction of the river banks at map scale. Missing or nonpositive
widths have a thin, muted fallback. The clicked feature retains the original
numeric width, including values above the display cap.

PMTiles geometry is quantized, simplified and split at tile boundaries. Visible
feature counts include fragments and change with zoom; they are not dataset
counts. The original GeoParquet files retain source geometry and all fields.
The new layers carry stable source IDs and exact source bbox scalars, allowing
attribute lookup without relying on generalized tile coordinates. HydroLAKES
uses its native MVT feature ID as `Hylak_id`; the other new layers also retain
an ID property. Internal bbox fields are hidden from the feature panel.

The explicit legacy GeoParquet preview retains a 1,500-feature cap, zoom guards
and **Load this view** button. That bounded preview is not a complete count or
representative sample. Source properties retain raw producer values, units and
null conventions; consult the field documentation before analysis.

The transfer counter measures data response bodies observed by the browser.
It excludes the UI, approximately 40 MB of browser runtime/context assets, HTTP
headers and local cache hits. The current cold-browser tests measure fixed global
and regional views for every PMTiles layer: Great Lakes for the hydrography
layers and Atlantic coast for river-plastic inputs. A third GRWL case selects
feature 28938 at the dateline and compares its analytical mean width with the
tile value. Transfer amounts vary with
region, cache and inspection. The 128 MiB evaluation ceiling is a test
limit, not a hard network budget for every possible interactive query.

## How it works

`prepare.py` joins canonical `dataset.yaml` records, the exact immutable upload
plan, existing package metadata and the hash-bound GEE audit. Its private runtime
file maps public-style `/nthh/<product>/releases/<release>/…` and
`/nthh/<product>/display/<display-release>/…` object paths to local files. The public config exposes dataset metadata and object URLs, never local
filesystem paths. It is a generated view, not another editable dataset registry.

`serve.py` exposes two loopback origins, with CORS, HEAD, single byte ranges,
206/416 responses and SHA-based ETags. Only explicit plan files are available.
It rejects traversal and symlinks and checks file identity/size/mtime before each
request. It has no database, feature API, upload endpoint or directory listing.
The initial full checksums establish file integrity; the server does not rehash
multi-gigabyte data on every request.

MapLibre renders the map. PMTiles reads the versioned display tiles. DuckDB-Wasm
queries GeoParquet in a browser worker using covering-bbox filters and column
selection. Both full-HTTP-read flags are explicitly disabled. The Parquet
extension, map worker and small public-domain Natural Earth context are bundled,
so viewing requires no third-party service calls. Exact pins are in
`package-lock.json`, `runtime-assets.json` and `land-source.json`.

The **Storage connection** control, or `?objects=https://YOUR-OBJECT-ORIGIN`,
can replace the origin while retaining the planned object paths. A real host must
serve the same bytes and support HTTPS, Range/HEAD, CORS and exposed response
headers. `Timing-Allow-Origin` is needed for cross-origin byte accounting. This
generic option was originally tested against the local origin. The separate
Source preview and official Portolan Browser now have retained public-host
checks. Hosting and GEE scientific equivalence remain separate from successful
visualization.

## Verification

```sh
uv run --locked --project scripts/release_tools python -m unittest \
  tests.test_cloud_viewer_prepare tests.test_cloud_viewer_run tests.test_cloud_viewer_server -v
npm --prefix scripts/cloud_viewer test
node scripts/cloud_viewer/export-grwl-style.mjs --check
npm --prefix scripts/cloud_viewer run build
node scripts/cloud_viewer/browser-check.mjs \
  --url http://127.0.0.1:8910/ --out .local/viewer-browser-NEW
```

The browser check uses installed Google Chrome on macOS; pass `--chrome PATH`
for another installed Chromium executable. It refuses an existing output directory,
opens a fresh browser context per layer, blocks external requests and whole-file
data GETs, and records screenshots, 206 ranges, transfer sizes, attribute inspection
and unavailable/zoom states. Real-data checks require the local packages; CI runs
synthetic-fixture tests and builds the pinned UI without downloading those datasets.

See the [PMTiles build and validation pattern](../../docs/display-derivatives.md),
the [current display evidence](../../research/pmtiles-all-20261102/README.md), and
the [existing GEE audit](../../research/cloud-viewer-20261101/README.md).

The [GRWL source trace and correction](../../research/grwl-straight-segments-20261102/README.md)
explain why feature 13164 retains an upstream straight segment and why the
original embedded GRWL PMTiles are superseded for display.

## Repeat the official Portolan Browser check

The [public catalog](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/catalog.json)
passed the complete live check for five collections and six PMTiles layers. The
[release record](../../research/source-publication-20261107/public-release-r1.json)
binds all deployment and visual evidence. With the locked Node dependencies
installed as above, stage metadata into a new directory, then run:

```sh
uv run --locked python scripts/publication_catalog.py stage .local/portolan-live-review
node scripts/cloud_viewer/portolan-browser-check.mjs \
  --mode live \
  --plan research/source-publication-20261107/pages/five-collections-r3/publish-plan.json \
  --expected-pages-plan-sha256 b7ddbfde936b3359820defe11abc6ba08eb37bd7f144c184492a40f3e661cd22 \
  --catalog-dir .local/portolan-live-review/catalog \
  --metadata-policy research/source-publication-20261107/pages/five-collections-r3/footer-prefix-policy-r1.json \
  --metadata-policy-sha256 01676ef3a58e04c8e37d4b72211d8a642c91cb9d7e3be85654f1beb80ab623bf \
  --out .local/portolan-live-browser-review
```

This reads actual public Pages and Source URLs; no login or local bulk data is
needed. It uses installed Google Chrome on macOS, or `--chrome PATH`, and refuses
existing output directories. Browser code, metadata and Source object identities
are pinned. The sole larger-range allowance is the exact checksum-verified GRWL
Parquet footer prefix; ordinary range and cumulative limits remain enforced.

A successful automated run ends at `rendered_pending_manual_review`. Review all
six original screenshots and retain a separate checksum-bound visual review
before claiming acceptance. Preserve failed attempts. A future Browser or dataset
revision requires a new reviewed plan; do not silently replace these frozen pins.
