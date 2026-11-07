# GRWL source chords: 15397, 15394 and the 40°N control

The horizontal and vertical chords in the reported Washington view are already
in the original `GRWL_summaryStats_V01.02.zip`. The current PMTiles faithfully
retain them. This is a source-geometry limitation, separate from the previously
fixed dateline display defect in feature 28938.

| Native viewer feature | Original part / edge (zero-based) | Endpoints (longitude, latitude; rounded) | WGS84 geodesic length | Largest sampled z10 deviation from source edge |
| --- | --- | --- | --- | --- |
| 15397 | 0 / 3 | (−119.61322, 47.99998) → (−118.95927, 47.99988) | 48,801.171 m | 3.629 m |
| 15394 | 0 / 34 | (−119.99992, 47.77885) → (−119.99980, 47.00470) | 86,068.820 m | 4.758 m |
| 13164 | 0 / 117 | (−109.42177, 39.99991) → (−109.78809, 39.99995) | 31,281.488 m | 4.188 m |

The viewer ID is the unique `source_row`, also matching `OBJECTID` for these
records. The producer's repeated `ID` is not the viewer ID. All parts and every
float64 coordinate bit match the original SHP for all three records. All ten DBF
numeric values match GeoParquet exactly. [Structured follow-up evidence](followup.json)
contains the full endpoint precision, source pins, field values and decoded tile
checks for both the original and current archives at every zoom 0–10.

## Why the lines appear

An original polyline directly connects each listed pair of distant vertices.
The renderer draws those existing edges. Tile quantization can make a nearly
horizontal or vertical edge exactly aligned on screen. It did not introduce the
long connections in these three records.

The [producer documentation](https://zenodo.org/records/18624542) describes raw
vector and raster tiles covering 4° latitude by 6° longitude. These examples lie
near 48°N, 40°N and 120°W, consistent with that grid. The original SHP XML's
resource title is `GRWL_merged_SimplifyLine`. Together, these observations strongly
suggest artifacts from upstream tile-boundary processing in the summary network.
**This is an inference:** the retained processing history records a length-field
calculation, not the operation that inserted the edges. We have not checked the
unsimplified vector tiles or source raster masks, so we cannot yet isolate the
fault to clipping, stitching, vectorization or simplification.

Feature 15397 has mean width **1,237 m** and `lakeFlag = 1` (lake/reservoir);
feature 15394 has mean width **655 m**. The width-based display therefore makes
these inherited straight edges prominent. The displayed thickness is an
exaggerated symbol, not literal mapped banks.

## The 40°N line remains

The current archive retains the 13164 edge at 40°N. It also renders in a fresh
browser session near **−109.60°, 40.00°**:

- [Washington view: 15397 horizontal chord and 15394 vertical chord](browser/feature-15397.png)
- [Current viewer: 13164 at 40°N](browser/feature-13164.png)

The earlier correction removed the globe-spanning interpretation of feature
28938's short dateline crossing near 68°N. It did not remove 13164. We cannot
establish why the user's particular view stopped showing the 40°N edge without
its exact camera state. At broad zooms, simplification and pixel scale can make
individual edges less recognizable. The source feature is present at all eleven
tested tile zooms; coarse zooms do not satisfy the z10 positional tolerance and
are not evaluated against that threshold.

The two [browser cases](browser/browser-evidence.json) used the running viewer
with its current archive SHA-256
`7b56696bc08daa4ed512a02fd35017f913827d60f9dc1d8fba94b1f726ba5343`.
Only the test browser's configuration response was intercepted to add the frozen
view regions; app code and the user's session were unchanged. Both exact-ID
inspections and full analytical attribute lookups passed. Every data response was
an HTTP 206 range response with CORS. Each case read less than 0.8 MB, and no
external browser request was made.

## Broader screen and limits

[Criteria](criteria.json) were committed before evaluating the new feature.
The original [diagnosis](diagnosis.json) screens 3,087,704 edges across all 42,077
records for edges ≥1 km with the smaller coordinate delta ≤0.0001° and without a
longitude jump >180°. It finds 6,127 edges in 5,036 records. Of these, 493 edges
in 429 records have both endpoints within 0.0001° of the provisional 4°/6° grid.
These are **screening candidates, not confirmed errors**; legitimate straight
reaches can qualify.

This strict screen misses the reported 15397 chord: its latitude delta is
0.000100000114898°, and an endpoint is 0.00012° from 48°N. The original threshold
and results remain unchanged. [Follow-up criteria](followup-criteria.json),
committed before the follow-up, explicitly select its longest edge and search
all orientations for edges ≥10 km within a frozen Washington region. That search
identifies the neighboring 15394 vertical edge. Both it and 15397 are outside the
original tight axis screen. This is why the screening count is not an inventory
of all seam artifacts.

The follow-up checks 101 samples along each selected source edge against decoded
and tile-core-clipped geometry. All three pass the existing 30 m Web Mercator
z10 bound. This verifies preservation, not whether the lines follow real water.
No source geometry, prepared release, manifest, upload plan or live viewer was
modified. No GEE request, data publication or remote push was performed.

Before offering a corrected river network, compare these locations against the
raw GRWL vector tiles and water masks. Any removal or replacement should be an
explicit, versioned derivative with its own validation. Do not automatically
remove all long or axis-aligned edges.

## Reproduce

Use a new report path each time. The scripts refuse to overwrite evidence and
verify input hashes against the frozen criteria.

```sh
uv run --locked --project scripts/display_tools python datasets/grwl/trace_source_chords.py \
  --data-root /absolute/data-root --output /absolute/new-screen.json
uv run --locked --project scripts/display_tools python datasets/grwl/trace_chord_followup.py \
  --data-root /absolute/data-root --output /absolute/new-followup.json
# With the normal local viewer running and viewer Node dependencies installed:
node research/grwl-source-chords-20261102/browser-evidence.mjs \
  --url http://127.0.0.1:8910/ --out /absolute/new-browser-directory
```

The browser script accepts `--playwright /absolute/path/to/playwright-core/index.mjs`
when reusing a separate locked viewer environment. New scripts and documentation
were checked locally; the full production datasets were not rebuilt.
