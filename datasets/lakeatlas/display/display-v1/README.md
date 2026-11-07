# lakeatlas display package

Display release: `display-v1`; analytical release: `lakeatlas-v1.0-r2`.
Status: prepared local display derivatives. This finalization does not claim new GEE checks, scientific validation, public hosting, or a clean rebuild of the production archive.

Attribution: HydroSHEDS / HydroATLAS authors; Lehner et al. (2022), DOI 10.1038/s41597-022-01425-z; CC BY 4.0, with some field-level ODbL 1.0 notices; Tippecanoe v2.79.0
Analytical release metadata and full data/field-license notices: [release manifest](../../releases/lakeatlas-v1.0-r2/manifest.json).

The pinned analytical GeoParquet remains authoritative for complete field lookup. PMTiles simplify and quantize geometry for display.

## Layers

- `lakeatlas-1`: [assets/lakeatlas-polygons.pmtiles](assets/lakeatlas-polygons.pmtiles) — polygon, source layer `lakeatlas-polygons`, z0–z12; source `assets/lakeatlas-polygons.parquet` SHA-256 `bbef606fd8522b230efc90e2952a67c1e4265e7bf733208fa4cc31395a7277b7`.
  - Style: [styles/lakeatlas-polygons.json](styles/lakeatlas-polygons.json)
  - Source rows: 1427688; unique source IDs: 1427688; decoded and attribute-checked IDs at maximum zoom: 1427688.
  - No missing source IDs were reported at maximum zoom.
- `lakeatlas-2`: [assets/lakeatlas-pour-points.pmtiles](assets/lakeatlas-pour-points.pmtiles) — point, source layer `lakeatlas-pour-points`, z0–z12; source `assets/lakeatlas-pour-points.parquet` SHA-256 `ff621c1db763551cdb6ced8958eefcc9da76a73c16e7f7259c238bec3aae5720`.
  - Style: [styles/lakeatlas-pour-points.json](styles/lakeatlas-pour-points.json)
  - Source rows: 1427688; unique source IDs: 1427688; decoded and attribute-checked IDs at maximum zoom: 1427688.
  - No missing source IDs were reported at maximum zoom.

## Finalization evidence

All linked reports are local evidence files included in the complete package inventory.
- [browser-validation.json](reports/finalization/browser-validation.json) (SHA-256 `d71525c48e549a6100556e4b706cddb948a19e25ed9a1af8d1c357777e4e27bb`)
- [lakeatlas-1.json](reports/finalization/geometry/lakeatlas-1.json) (SHA-256 `d3859211d5b0e913b83341553fafadfe698c82b5ae4a427bbe2f1cb5ffa96bf7`)
- [lakeatlas-2.json](reports/finalization/geometry/lakeatlas-2.json) (SHA-256 `f186802e66ae4801c5438d4c88b2dcb8c6c2eb165a8f721b6d402895923d5962`)
- [lakeatlas-1.json](reports/finalization/pmtiles-verify/lakeatlas-1.json) (SHA-256 `9c3cf7a3d37ed3fa5fd8f0fbd47e574a1a32ad7f3cd3a12e4b9fb4ae3ca3a081`)
- [lakeatlas-2.json](reports/finalization/pmtiles-verify/lakeatlas-2.json) (SHA-256 `afaaa9f3f92e5e7d23c989fc339e1bf045a79e307fa7a6530186262b07277844`)
- [lakeatlas-polygons.build-report.json](reports/lakeatlas-polygons.build-report.json) (SHA-256 `63defdf43eee21af2d879843956fdbc18c95404d27b5463da36c1e7187e8774d`)
- [lakeatlas-pour-points.build-report.json](reports/lakeatlas-pour-points.build-report.json) (SHA-256 `884b11ea8e3719ead7488ac67ceddd081a9dcef519ab495f33d3545b132c2810`)

The finalizer reruns `pmtiles verify` and records the executable and archive hashes. Builder reports record maximum-zoom ID/attribute accounting. Explicitly supplied geometry reports establish the sampled, bounded Web Mercator display tolerance only. Browser reports establish the tested global and North America views, nonzero rendering, ranged HTTP 206 reads, and the 128 MiB response-body limit.
