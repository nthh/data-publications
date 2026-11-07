# GRWL raw vectors V01.01 display package

Display release `raw-v01.01-display-r1` is bound to analytical release `raw-v01.01-local-r1`.
Status: prepared local display derivative. This is not a public hosting, Source Cooperative publication, GEE parity, or scientific-accuracy claim.

The GeoParquet remains the analytical source of record. This detail-only PMTiles layer shows separate producer observations at zooms 8–12. Source records are never joined by segment identifiers or proximity. `width_m=1` is the producer unknown-width sentinel; displayed strokes are not bank outlines.

- PMTiles: `assets/grwl-raw.pmtiles` (11498067077 bytes, SHA-256 `a1a7787c7ba28ffc271819bddc54339f9bc741aa9ed44ca619d93e809cbad4f5`)
- Analytical asset: `assets/grwl-raw-observations.parquet` (5529859809 bytes, SHA-256 `d37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb`)
- Source rows: 64,572,998; source tiles: 829
- z12 missing IDs: 304, all explicitly classified as {'quantization_collapse': 304}
- Producer citation: Allen, G.H. and Pavelsky, T.M. (2018), Global extent of rivers and streams. Science 361(6402), 585–588. https://doi.org/10.1126/science.aat0636 Source record: https://zenodo.org/records/18624542
- Producer license: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/). Preserve attribution and cite the source release.

## Finalization evidence

The package inventory binds the source-fidelity evidence, full raw display oracle and missing-ID enumeration, frozen browser controls and report, PMTiles verification, builder provenance, verifier/browser code, dependency locks, and all package assets. The finalization report records the repository commit and per-file SHA-256 values for repeatable inspection. The raw oracle checks z12 ID and attribute accounting and the frozen per-tile geometry samples. Browser evidence checks the exact frozen source attributes and width presentation over local ranged requests.

No masks, optional tile index, RSSA supplement, SummaryStats aggregates, current-condition claim, GEE parity, or global scientific-accuracy assessment are included.
