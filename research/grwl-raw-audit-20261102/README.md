# GRWL raw-data comparison: confirmed summary connectors

The reported edges in **15450** and **11839** are geometry errors in the
producer's simplified summary. They are present in the original summary SHP and
preserved by our conversion. They are absent from the corresponding raw river
network. The same comparison supports this conclusion for earlier examples
13164, 15394 and 15397.

The summary connects observations near where a river exits a tile and re-enters.
The raw river continues through the adjacent tile along a curved path. All ten
summary endpoints in these five examples match raw measurement coordinates
rounded to five decimals. This identifies the observations that were linked; it
does not identify the precise producer software operation that linked them.

## View the two new examples

- [15450: 110 km shortcut at 108°W](comparison-r2/feature-15450.png).
  The raw river bends west; the summary edge runs straight down the tile boundary.
- [11839: 6.2 km shortcut at 90°W](comparison-r2/feature-11839.png).
  The raw river and mapped water follow a bend west of the summary connector.

Red is the selected summary edge, orange the rest of that summary feature,
dark blue the raw centerline pieces, and light blue the GRWL connected-water mask.
These are source-data plots, not a newly corrected viewer layer.

## Measurements

Each edge was sampled at 101 evenly spaced fractions from 0.01 through 0.99.
The 90 m proximity threshold is a diagnostic allowance of three nominal 30 m
source pixels, not a published scientific acceptance standard.

| Feature | Connector length | Samples within 90 m of any raw centerline | Samples on mapped water | Samples within 90 m of mapped water | Maximum distance to any raw centerline |
| --- | ---: | ---: | ---: | ---: | ---: |
| 15450 | 110.072 km | 1/101 | 0/101 | 3/101 | 17.844 km |
| 11839 | 6.217 km | 10/101 | 26/101 | 38/101 | 1.130 km |
| 13164 | 31.281 km | 0/101 | 0/101 | 0/101 | 7.353 km |
| 15394 | 86.069 km | 0/101 | 6/101 | 9/101 | 19.420 km |
| 15397 | 48.801 km | 0/101 | 0/101 | 0/101 | 12.928 km |

The [full comparison](comparison-r2/comparison.json) records all sample positions,
nearest raw IDs, values from each overlapping raster, native CRS and metric CRS.
Distances use all records in both selected neighboring tiles, not just records
inside a narrow edge window. Nearest support can be an unrelated river, so this
is a conservative absence test rather than a channel-identity match.
[Structured findings](findings.json) provide the short machine-readable result.

## Trace of the endpoints

| Summary feature | Raw tile | Raw records (1-based) | Raw segmentID | segmentInd at the endpoints |
| --- | --- | --- | --- | --- |
| 15450 | NL13 | 41573 → 41586 | 2 | 4210 → 9712 |
| 11839 | NI16 | 56861 → 56878 | 8 | 3648 → 3859 |
| 13164 | NJ12 | 1797 → 1798 | 0 | 4015 → 5773 |
| 15394 | NL11 | 13838 → 13839 | 1 | 1159 → 4943 |
| 15397 | NL11 | 46761 → 46762 | 6 | 975 → 3190 |

[Endpoint identity checks](endpoint-identity.json) compare rounded raw measurement
coordinates with the original summary coordinates. IDs in the raw product are
local to a tile and must not be joined globally. The raw observations are short
centerline LineStrings, not channel-width transects. The four endpoint lines for
the new examples measure about 4–28 m while their recorded widths are 169–1,536 m.
The original raw geometry contains no edge ≥1 km within any of the five frozen
edge neighborhoods; [local structure checks](raw-vector-roi-structure.json)
record those subsets. Raw nearest-ID sets do not count topological components.

## Sources and acquisition

The [official producer record](https://zenodo.org/records/18624542) documents the
raw and simplified products. The source pins and comparison methods were
[committed before inspecting the new examples](criteria.json).

The producer-linked tile index selected **nine tiles**, including both sides of
each seam: NI15, NI16, NJ12, NK12, NL10, NL11, NL12, NL13 and NM11. The exact
[selection](selection/selection.json) uses each chosen edge's bounding box padded
by 0.02 degrees and the original index polygons. It does not infer tile locations
from filename order. All five original summary records also pass exact SHP
coordinate-bit/part and ten-field DBF comparisons with GeoParquet.

Only selected members of `GRWL_vector_V01.01.zip` and `GRWL_mask_V01.01.zip` were
acquired through strict HTTP 206 byte ranges. No full-archive fallback occurred.
The total transfer was **47,280,134 bytes**, including the 82,956-byte tile index.
All **90 vector/mask members** passed complete-member CRC checks against the ZIP
central directory; local SHA-256 hashes are recorded. Extracted members total
240,786,403 bytes. Whole-archive MD5 verification is **not claimed** for partially
read archives. See [vector acquisition](vector-extraction-r1.json),
[mask acquisition](mask-extraction-r1.json), and [tile-index capture](tile-index-fetch-r1.json).

The summary V01.02 and the raw/mask V01.01 components are the files supplied
together in the pinned producer record. The producer's record-level version label
is inconsistent with the summary filename; exact filenames and hashes identify
the inputs. No GEE comparison or independent optical validation was performed.

## Georeferencing, failed check and review

The acquired mask TIFFs use **native UTM with 30 m pixels**, despite the landing
page saying geographic WGS84. The first plotting attempt stopped at its explicit
CRS guard; its [failure](comparison-r1/failure.json) is retained. The
[follow-up](mask-projection-followup.json) uses actual TIFF georeferencing for
sampling and nearest-neighbor geographic reprojection only for plots. No
threshold, selected edge or raw input changed.

Masks have no declared NoData value. Code 0 means no connected-water class and
can include unclassified margins; it does not independently prove land. Projected
tile footprints overlap, so a point may have two center values. The table counts
water if either tile supports it. Zero missing raster coverage is a statement
about file footprints, not completeness of water mapping. The masks and raw
vectors share upstream provenance, and producer documentation explicitly says
the masks were not independently validated.

An [independent review](independent-review.json) checked the two new cases using
full-tile UTM distances, five positions per edge, native-mask windows, endpoint
identities and raw geometry semantics. It agrees with the main local-AEQD
calculation within projection differences. An initial narrow-ROI distance check
was recognized as incomplete and replaced with full-tile checks; its larger
estimates are not used in the final result.

## Publication implications

This establishes source-summary errors at five inspected locations, not an
exhaustive global error inventory. The summary mirror preserves the producer's
bytes/geometry faithfully; it must disclose these errors. A clean network should
be a separately versioned raw-based or explicitly corrected derivative with
checks for continuity across tile boundaries. Do not delete arbitrary long or
straight edges based on the earlier screening threshold.

Canonical source-quality notes and generated Source Cooperative drafts now
record these findings. Prepared release files, viewer data and immutable upload
plans remain unchanged. Earlier plans contain their historical metadata; new
publication staging must include current product copy. No upload or push occurred.

## Repeat

The existing locked `datasets/river-plastic-inputs` environment supplies the
analysis dependencies; all eight key runtime versions are recorded in the
comparison. Use new paths for reports/directories. Source-range and member caches
are reused only after integrity checks.

```sh
uv run --locked --project datasets/river-plastic-inputs python datasets/grwl/select_raw_tiles.py \
  --index /absolute/cache/official-tile-index.zip --output-dir /absolute/new-selection
python3 datasets/grwl/acquire_raw_tiles.py extract --kind vector \
  --selection research/grwl-raw-audit-20261102/selection/vector-members.json \
  --cache /absolute/cache --report /absolute/new-vector-extraction.json
python3 datasets/grwl/acquire_raw_tiles.py extract --kind mask \
  --selection research/grwl-raw-audit-20261102/selection/mask-members.json \
  --cache /absolute/cache --report /absolute/new-mask-extraction.json
uv run --locked --project datasets/river-plastic-inputs python datasets/grwl/compare_raw_tiles.py \
  --cache /absolute/cache --data-root /absolute/data-root --output-dir /absolute/new-comparison
```

The comparison binds cached inputs to the checked-in extraction reports.
It refuses to overwrite an output directory. `inventory` mode on the acquisition
script reproduces central-directory inspection; the index source URL and checksum
are in the capture report. Local data remains in ignored storage.
