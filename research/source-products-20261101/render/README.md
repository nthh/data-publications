# Local browser render gate

This is a real Chrome view backed by query requests to the retained analytic GeoParquet
files. It does not read a pre-rendered dataset thumbnail. The viewer requests one bbox
per enabled layer from a loopback Python server; DuckDB evaluates each request directly
against the immutable Parquet path. The server returns at most 1,000 features per layer,
ordered by the stable producer/source ID. It separately reports the exact bbox match
count. This deterministic lowest-ID cap is a display sample, not a representative
sample, and does not establish complete rendering of any region.

## Reproduce locally

From the repository root, start the server (startup hashes every complete source file
against its immutable release manifest):

```sh
python3 -B scripts/render_preview/server.py \
  --data-root "$HOME/projects/data-publications/.local" \
  --host 127.0.0.1 --port 8765 \
  --log research/source-products-20261101/render/http-requests.jsonl
```

Open <http://127.0.0.1:8765/> in a browser. The geographic control selector requests
one of the five bboxes frozen in `criteria.json`; layer checkboxes fetch or hide an
individual asset. A custom bbox field accepts `xmin,ymin,xmax,ymax`; a URL may provide it
as `?bbox=`. The query button sends that extent to the same analytic API. To reproduce
the screenshots with the installed macOS Chrome app:

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --no-first-run --no-default-browser-check --disable-gpu \
  --hide-scrollbars --user-data-dir=.local/render-preview/chrome-profile \
  --window-size=1600,1100 --force-device-scale-factor=1 \
  --virtual-time-budget=30000 \
  --screenshot=research/source-products-20261101/render/europe-browser.png \
  'http://127.0.0.1:8765/?region=europe'
```

The other screenshots use the `north_america`, `south_america`, `asia`, and `oceania`
URL region values. Run the focused failure-control tests with the existing locked
release-tools Python environment (Python 3.12, PyArrow, DuckDB, and Shapely are already
installed):

```sh
PYTHONPATH=. "$HOME/.folia-fleets/hydro-releases-20261031/tree/scripts/release_tools/.venv/bin/python" \
  -m unittest discover -s tests -p test_render_preview.py -v
```

For the fixed uncapped follow-up screenshot, keep the same Chrome flags and change the
destination and URL as shown here:

```sh
--screenshot=research/source-products-20261101/render/hydrolakes-custom-sw-europe-browser.png \
  'http://127.0.0.1:8765/?bbox=5%2C45%2C7.5%2C47.5'
```

## Scope and hosting limits

The preview requires access to all four local Parquet files. It verifies the full
file SHA-256 against the release manifest at startup, then runs local bbox queries;
it never edits those files. The browser receives only the capped, clipped and
simplified GeoJSON returned by the local server. Attribute values are unchanged for
the small set shown in each layer. The returned WKB is transformed only for display:
features are clipped to the requested bbox and non-point geometry is topology-preserving
simplified at 1/1,200 of the larger bbox dimension. The source WKB and attributes remain
untouched.

The server binds to loopback only and intentionally has no public deployment path. It
is not a public-host browser check. Public delivery would require confirmed HTTPS hosting
for the complete immutable files plus a browser-compatible range-query engine or an
authorized query API. No bytes were downloaded from the network for this demonstration;
the HTTP query evidence records loopback response sizes. Public render coverage remains
incomplete.

`http-requests.jsonl` preserves the first observed request history. The final browser
run has its own request log so the custom bbox follow-up is easy to audit. Both logs
retain Chrome `/favicon.ico` 404s. All 20 feature requests across the five committed
controls returned HTTP 200 in the initial run; the final capture returned HTTP 200 for
those same controls plus four requests for the fixed custom extent. That follow-up was
recorded and committed before querying in
`followup-control-criterion.json` (commit `db62a47`): the southwest tile of a 4×4 grid
over Europe, `[5,45,7.5,47.5]`, for HydroLAKES polygons. It returned 295 of 295 matches
with no cap. `render-evidence.json` summarizes the final screenshots, source manifest
bindings, per-control match counts, feature caps, runtime versions, implementation script
hashes, follow-up result, and loopback response bytes. The ignored Chrome profile in
`.local/render-preview/` is a 3 MB runtime artifact; no browser or Python packages were
downloaded for this run.
