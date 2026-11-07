# GRWL simplified global river network V01.02

**Publication withheld after source-quality review.** This faithful summary mirror retains confirmed upstream connector errors. The replacement work uses the separate [raw vector product](../grwl-raw/README.md); existing summary files remain unchanged for comparison.

This workflow converts the complete producer summary network to analytic GeoParquet
and a PMTiles display layer. It preserves 42,077 source records, 42,117 line parts,
3,129,821 vertices and all ten numeric fields. The canonical [dataset.yaml](dataset.yaml)
records the source pins and current publication state; a local package is not a
public upload or accepted registry entry.

Discovery: [GEE community catalog](https://gee-community-catalog.org/projects/grwl/)
→ [producer archive](https://zenodo.org/records/18624542)
→ `GRWL_summaryStats_V01.02.zip` (43,282,861 bytes, CC BY 4.0).
The associated Allen and Pavelsky paper is [Science (2018)](https://doi.org/10.1126/science.aat0636).
Its 869 citations are from the frozen 2026-10-29 prioritization snapshot.

The summary is one global component. Raw vectors, masks, tile index and basin
summaries are outside this conversion. The GEE catalog names V01.01, while the
selected summary filename is V01.02. Zenodo's descriptive version label still says
V01.01; exact DOI, filename and checksums identify the bytes. No GEE parity is
claimed or requested. See the [version review](../../research/local-next-two-20261030/grwl-version-review.json).

## Repeat the local release

From the repository root, check out the conversion commit in the release manifest
for exact reproduction. Install the Tippecanoe version and binary recorded in
[tippecanoe.lock.json](tippecanoe.lock.json), then:

```sh
uv sync --locked --project datasets/grwl
uv run --locked --project datasets/grwl python datasets/grwl/reproduce.py \
  --source /path/to/GRWL_summaryStats_V01.02.zip \
  --work .local/grwl/new-run
```

Obtain the public source from the pinned `source_url` in dataset.yaml. The script
checks the archive checksum, uses a new output directory, makes a clean Git
checkout, installs locked dependencies, builds twice, validates the full source,
runs actual STAC/Portolan schema gates and fault checks, and compares all asset
bytes before packaging. It never uploads data or calls GEE. Bulk inputs and outputs
stay in ignored `.local/` storage; code is Apache-2.0 and data remains CC BY 4.0.

## Fidelity and limits

Producer `ID` has only 383 distinct values. Keep every record; `source_row` is the
unique ordinal within this pinned archive. Some DBF values use scientific notation
with more decimal places than the nominal schema scale. The Arrow decimal scale
expands to preserve their exact numeric values. Individual line parts and every
float64 coordinate are compared independently with the source.

Width statistics are metres. `Shape_Leng` is kilometres, confirmed by the source
XML processing lineage. The SHP header slightly exceeds longitude 180, but actual
vertices stay inside the valid domain; analytic coordinates are unchanged.

The PMTiles layer uses zooms 0–10 and simplification scale 2. Complete source-row
coverage is required at maximum zoom, but tile geometry is quantized and simplified.
Use GeoParquet for analysis. A later, separately labeled displacement diagnostic
samples line geometry; it is not a continuous geometry guarantee or scientific
accuracy validation. See [VALIDATION.md](VALIDATION.md) for the precise distinction
between initial acceptance criteria and follow-up diagnostics.

Validation evidence and retained development failures live under `evidence/`.
Public hosting, Source Cooperative creation and Portolan submission remain pending.

## Measured-width viewer style

The local viewer and [portable width-v1 style](styles/width-v1.json) use
`width_mean` in metres for line thickness. The legend updates with zoom and shows
50 m, 200 m and ≥1,000 m examples. These are exaggerated display symbols, capped
at 1,000 m, with a thin fallback for missing or nonpositive widths. Original
numeric widths remain visible when a feature is selected. The existing PMTiles
and GeoParquet bytes are unchanged.

## Known source geometry and current display correction

Five reported long straight edges are already present in the producer's
summary SHP and are preserved exactly in GeoParquet:

| Viewer feature (`source_row`) | Edge location | Geodesic length |
| --- | --- | --- |
| 13164 | Near 40°N, −109.78809° to −109.42177° longitude | 31.281 km |
| 15397 | Near 48°N, −119.61322° to −118.95927° longitude | 48.801 km |
| 15394 | Near 120°W, 47.00470° to 47.77885° latitude | 86.069 km |
| 15450 | Near 108°W, 44.30909° to 45.29959° latitude | 110.072 km |
| 11839 | Near 90°W, 35.46026° to 35.51629° latitude | 6.217 km |

The [raw-vector and water-mask comparison](../../research/grwl-raw-audit-20261102/README.md)
confirms these as **summary geometry errors**. The original raw rivers continue
through neighboring tiles along curved paths, while the summary joins observations
near tile exit/re-entry locations with straight connectors. All ten selected
summary endpoints match raw measurement coordinates rounded to five decimals.
The exact producer software operation remains unidentified. This inspection covers
five examples and nine raw tiles; it is not a global scientific accuracy audit.

The prepared source-faithful GeoParquet and PMTiles retain these errors. A clean
network requires a separately versioned raw-based or explicitly corrected
derivative. The earlier [source-to-viewer investigation](../../research/grwl-source-chords-20261102/README.md)
verified that the conversion preserved the summary; the new raw comparison
establishes its source-quality defects. No source-edge cleaning was applied.

Feature **28938** crosses the dateline by about 523 m. The original release's
embedded PMTiles interpreted the longitude discontinuity as a world-spanning
line. The current [display-v1 package](display/display-v1/manifest.json) fixes that
by splitting display lines at ±180°; it supersedes the embedded PMTiles for map
use. The old tiles and width-v1 supplement remain historical evidence. The
current portable width style is [grwl-width.json](display/display-v1/styles/grwl-width.json).

The source GeoParquet keeps the producer's exact coordinates, including dateline
encoding; analytical operations must account for longitude wrapping. The
[source trace, regression failures and correction](../../research/grwl-straight-segments-20261102/README.md)
document the distinction and repeatable validation. No GEE comparison was added.
