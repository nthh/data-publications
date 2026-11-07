# GRWL straight-segment investigation

The two reported lines have different causes. This investigation uses the pinned
producer `GRWL_summaryStats_V01.02.zip`, the existing analytical GeoParquet, and
actual decoded PMTiles. The original analytical release is unchanged.

| Viewer feature | Source identity | Finding |
| --- | --- | --- |
| 13164 | `source_row = OBJECTID = 13164`, producer `ID = 0` | The original SHP contains a 31.281 km near-horizontal edge at about 40°N. |
| 28938 | `source_row = OBJECTID = 28938`, producer `ID = 5` | A 522.69 m dateline crossing is encoded with adjacent longitudes +179.9884° and −179.999991°. The old display interpreted that discontinuity as a line across the world. |

The [raw-source trace](diagnosis.json) compares every float64 coordinate and part
boundary for these records directly with the SHP, and all ten original DBF
numeric values with GeoParquet. Both records match exactly. The viewer feature
number is the unique source row; the producer `ID` field is repeated and is not
an interchangeable identifier.

For 13164, original part 0 vertices 117→118 run from
`(-109.42177000008542, 39.99990999964683)` to
`(-109.78809000015337, 39.999949999692774)`. Normal tile quantization rounds both
latitudes to one tile row, making the upstream near-horizontal edge perfectly
horizontal on screen. Its cause in the producer's processing is not established
here; the authoritative source geometry is retained.

For 28938, original part 0 vertices 115→116 cross the dateline. The old archive
contains this feature even in tile z10/512/245 near longitude 0°. The
[preserved regression](original-wrap-regression.json) fails at every zoom 0–10.
The browser renders those tile coordinates directly; this was a display
conversion defect, not a browser join between unrelated river parts.

## Correction and controls

A scan of all 42,077 source records found exactly one part with a consecutive
longitude jump greater than 180°: [source row 28938](crossing-source-ids.json).
The new display builder splits individual line parts at ±180°, interpolating the
boundary in Web Mercator. It keeps all noncrossing vertices and original part
boundaries. Analytical coordinates and producer attributes are unchanged.

The pinned tiler's `--detect-longitude-wraparound` option alone failed eastward
and westward native fixtures; that [failure is retained](native-flag-failure.json).
The [revised correction criteria](correction-criteria-r2.json) were committed
before evaluating the explicit split. Native fixtures cover both directions,
exact boundary endpoints, a vertical boundary segment, tiny crossing tails,
independent multipart lines, and a legitimate noncrossing long line.

The independent geometry oracle uses its own longitude-unwrapping implementation.
The first corrected-archive check preserved all IDs/attributes and removed the
world chord, but [failed the geometry comparison](corrected-validation-r1-failed.json)
for the tiny western tail. That tail is about 0.4 m on the ground and becomes a
boundary point after z10 quantization. Dropping the point and comparing −180°
with +180° in a discontinuous planar frame falsely measured nearly one world
width. The [metric diagnostic](periodic-metric-diagnostic.json) was frozen before
retaining point intersections and translating whole components into a common
periodic frame. The 30 m tolerance, 74 selected IDs and all eleven chord checks
stay unchanged; the original broken archive still fails.

Browser controls include global and Great Lakes views plus an exact
[feature 28938 dateline inspection](browser-controls.json). Source-ID lookup
revealed an additional [Decimal formatting defect](decimal-inspection-diagnostic.json):
the inspector exposed a scaled integer instead of the source's 97 m mean width.
A correct field count is insufficient; the browser gate also compares the actual
analytical width with the tile's value.

## Completed local release

The corrected archive is **115,384,572 bytes** (SHA-256
`7b56696bc08daa4ed512a02fd35017f913827d60f9dc1d8fba94b1f726ba5343`).
Its [prepared manifest](../../datasets/grwl/display/display-v1/manifest.json) is
bound by the canonical GRWL record. The normal local viewer now selects it.

[Final verification](final-verification.json) records complete accounting of
42,077 source IDs and 1,754,788 tile-attribute comparisons, with zero missing IDs
or attribute failures. All 74 geometry samples pass; the maximum displacement
is 18.4383 m against the unchanged 30 m Web Mercator threshold. Feature 28938 is
7.3703 m from the periodic reference, and all eleven dateline zoom checks pass.

All [13 cold-browser cases](final-browser/browser-validation.json) pass from the
normal launcher in a clean checkout. The dateline case inspects source row 28938
and verifies **97 m** in both the tile and analytical attributes. The
[reviewed screenshot](final-browser/grwl-display-dateline.png) shows the result.
Eight focused native/geography/finalization tests, 21 viewer preparation/launcher
tests, and eleven client tests pass. The full production archive was built once;
small native fixtures were repeated in the clean checkout.

The new [exact upload plan](staging-r1/immutable-upload-plan.json) contains five
products, 296 files and 9,878,979,687 bytes. Seven PMTiles files are retained because
the original GRWL archive remains historical; six layers are active in the viewer.
Nothing was uploaded or pushed, and account-verification evidence remains pending.

The build initially stopped at its 40 GiB disk floor. Only the
[inventoried GRIP4 extraction cache](grip-extraction-cache-inventory.json) was
removed after every member matched the retained source ZIP. Its verified source
ZIP and validated release remain, and the [cleanup receipt](grip-extraction-cache-cleanup.json)
records the exact scope. No analytical release was deleted.

## Reproduce

```sh
uv run --locked --project scripts/display_tools python datasets/grwl/trace_straight_segments.py --help
uv run --locked --project scripts/display_tools python datasets/grwl/build_display.py build \
  --data-root /absolute/data-root --output /absolute/data-root/grwl/display/new-release
uv run --locked --project scripts/display_tools python datasets/grwl/validate_display_wrap.py \
  --source /absolute/data-root/grwl/summary-v01.02-local-r1/grwl/grwl-summary-v0102.parquet \
  --archive /absolute/display-package/assets/grwl.pmtiles --report /absolute/new-validation.json
GRWL_NATIVE_WRAP_TESTS=1 uv run --locked --project scripts/display_tools python \
  -m unittest tests.test_grwl_display_wrap tests.test_grwl_display_finalize -v
```

The display builder currently names its package `display-v1` internally; use a new
output directory for every attempt and never overwrite a prepared package. Before
running native fixtures, reserve the local native-build lane. No new GEE request,
public upload, observational validation or full-production rebuild is implied.
