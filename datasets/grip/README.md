# GRIP4 global roads — 2018

The selected product is the complete global vector archive, covering all seven
producer regions. The original archive contains **25,758,453 road features**,
matching the community catalog's reported count. This is a historical research
inventory, not a current road or navigation service.

- Discovery: [GEE community catalog](https://gee-community-catalog.org/projects/grip/).
- Producer: [PBL GRIP4](https://dataportaal.pbl.nl/GRIP4).
- Pinned archive: [Zenodo 6420961](https://zenodo.org/records/6420961),
  `GRIP4_global_vector_fgdb.zip`, 2,334,355,294 bytes.
- Source DOI: `10.5281/zenodo.6420961`; associated paper:
  [Meijer et al. (2018)](https://doi.org/10.1088/1748-9326/aabd42).
- Canonical source pins, build settings and publication state: [dataset.yaml](dataset.yaml).

The selected Zenodo record's structured license is CC BY 4.0. Its prose and PBL's
website also state CC0. This release follows the selected archive's attribution
terms and preserves the discrepancy rather than claiming the evidence agrees.
Source code in this repository is Apache-2.0; that does not replace the data license.

## Current state

Publication is deferred. The [validated first-build evidence](evidence/validated-run-02/README.md)
covers every source road and the format checks. The user stopped the clean rebuild;
its seven analytic partitions matched, but full reproducibility and packaging did
not finish. The retained files are not a prepared release.

The source publication date is May 23, 2018. Zenodo deposited this release on
April 7, 2022; the [latest-version check](../../research/local-build-two-20261030/grip-version-date-review.json)
still resolves to the same record. For current roads, reuse Overture, already
represented by `@overture/maps/transportation` in Folia. See the
[alternative review](../../research/local-build-two-20261030/grip-overture-review.md).

## Repeat the local release

Run from the repository root, using the conversion commit recorded in the release
manifest for exact reproduction. Python dependencies and native Tippecanoe 2.79.0
are pinned. Install Tippecanoe and the PMTiles CLI before running these commands.
Do not change source/build settings when reproducing a previous release.

```sh
uv sync --locked --project datasets/grip
npm ci --prefix datasets/grip --ignore-scripts --no-audit --no-fund
uv run --locked --project datasets/grip python datasets/grip/source.py \
  --cache .local/grip-source --download \
  --report .local/grip-source/inspection.json
uv run --locked --project datasets/grip python datasets/grip/reproduce.py \
  --source-cache .local/grip-source --work .local/grip/new-run
```

A run refuses existing work/output paths. It checks the pinned ZIP and extracted
members, streams batches, writes seven GeoParquet 1.1 regional files ordered by
spatial location, and builds PMTiles overview tiles. The complete analytic files
preserve source identifiers, all attributes/nulls, line parts and WKB coordinates.
`bbox` supports spatial pruning. The producer code dictionary and original workbook
accompany the data. `Shape_Length` remains the original field; it is not a newly
calculated length in metres.

PMTiles is simplified and thinned at zooms 0–10. The report measures actual source
ID retention per zoom and region. Use GeoParquet for counts, connectivity or other
analysis. Catalog envelope normalization at longitude 180 affects metadata only;
original coordinates and analytic bounds are unchanged.

The validation compares every original source field and WKB on a fresh read,
checks GeoParquet statistics, audits all tile IDs/attributes, samples tile geometry
using the rule fixed in [CONTRACT.md](CONTRACT.md), runs real STAC/Portolan schemas
and HTTP spatial queries, and exercises deliberate faults. A second build runs in
a clean local Git checkout and compares all asset and manifest bytes. Only passing,
manifest-bound reports can be packaged. No live GEE request, upload, public-host
verification or registry submission is part of this command.

The source download and extraction use about 6.5 GB before outputs. Conversion uses
65,536-feature batches, a 1 GB DuckDB sort budget and two native threads. Temporary
sort/tile inputs and a separate reproduction need additional disk; the builder
stops below 40 GB of free space to preserve headroom on the shared machine.

## Evidence and limits

The full source inspection is in
[grip-source-inspection.json](../../research/local-build-two-20261030/grip-source-inspection.json).
The planned requirements remain in [VALIDATION.md](VALIDATION.md); precise criteria
are in [CONTRACT.md](CONTRACT.md). Failed preflight evidence is retained under
[evidence/failures](evidence/failures/README.md). Successful release receipts are
added only after the complete rehearsal passes.

Both source readers use GDAL's OpenFileGDB decoder. Explicit row-level equality
checks establish conversion fidelity; they are not independent proof of the
producer's geographic accuracy. PMTiles geometry checks are sampled; its ID and
attribute audits are exhaustive. GEE parity and scientific observational validation
have not been performed for this release. Public publication remains pending.
