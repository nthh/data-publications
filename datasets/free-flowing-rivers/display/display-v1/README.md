# free-flowing-rivers display package

Display release: `display-v1`; analytical release: `figshare-v1-local-r2`.
Status: prepared local display derivatives. This finalization does not claim new GEE checks, scientific validation, public hosting, or a clean rebuild of the production archive.

Attribution: Source data by Günther Grill and Bernhard Lehner; CC BY 4.0; Tippecanoe v2.79.0
Analytical release metadata and full data/field-license notices: [release manifest](../../releases/figshare-v1-local-r2/manifest.json).

The pinned analytical GeoParquet remains authoritative for complete field lookup. PMTiles simplify and quantize geometry for display.

## Layers

- `free-flowing-rivers-1`: [assets/ffr-reaches.pmtiles](assets/ffr-reaches.pmtiles) — line, source layer `ffr-reaches`, z0–z12; source `assets/ffr-reach-network-v1.parquet` SHA-256 `62130e4999ba449bd2768bcdd9346bc2ba8fa4c4f06d39597e5227cd496a1a63`.
  - Style: [styles/ffr-reaches.json](styles/ffr-reaches.json)
  - Source rows: 8477883; unique source IDs: 8477883; decoded and attribute-checked IDs at maximum zoom: 8477883.
  - No missing source IDs were reported at maximum zoom.

## Finalization evidence

All linked reports are local evidence files included in the complete package inventory.
- [ffr-reaches.build-report.json](reports/ffr-reaches.build-report.json) (SHA-256 `a4fe0e815f2f4cbd985418bdbd291ef8706ccf9450ae5a713a662f39eddb2498`)
- [browser-validation.json](reports/finalization/browser-validation.json) (SHA-256 `1ab8b20ed219e2b48c3845f43c4f36953884aeecd013fb79c9e33e2e4df19396`)
- [free-flowing-rivers-1.json](reports/finalization/geometry/free-flowing-rivers-1.json) (SHA-256 `754a164186219b1fab5416e4780ca510aa99790ae3f5f006209dccc9d6abc49a`)
- [free-flowing-rivers-1.json](reports/finalization/pmtiles-verify/free-flowing-rivers-1.json) (SHA-256 `e2c4e8473652c4788f999f69774c017134634c8546c0fb59cb027c5cd1d7b2a5`)

The finalizer reruns `pmtiles verify` and records the executable and archive hashes. Builder reports record maximum-zoom ID/attribute accounting. Explicitly supplied geometry reports establish the sampled, bounded Web Mercator display tolerance only. Browser reports establish the tested global and North America views, nonzero rendering, ranged HTTP 206 reads, and the 128 MiB response-body limit.
