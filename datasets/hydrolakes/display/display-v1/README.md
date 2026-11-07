# hydrolakes display package

Display release: `display-v1`; analytical release: `v1-local-r3`.
Status: prepared local display derivatives. This finalization does not claim new GEE checks, scientific validation, public hosting, or a clean rebuild of the production archive.

Attribution: HydroLAKES v1.0, Lehner and Messager / HydroSHEDS; CC BY 4.0; Tippecanoe v2.79.0
Analytical release metadata and full data/field-license notices: [release manifest](../../releases/v1-local-r3/manifest.json).

The pinned analytical GeoParquet remains authoritative for complete field lookup. PMTiles simplify and quantize geometry for display.

## Layers

- `hydrolakes-1`: [assets/hydrolakes-polygons.pmtiles](assets/hydrolakes-polygons.pmtiles) — polygon, source layer `hydrolakes-polygons`, z0–z12; source `assets/hydrolakes-polygons.parquet` SHA-256 `6f588d97c14651eb23bea2d74fdf2a85f218a00ff11519c81efa5512b916b7f8`.
  - Style: [styles/hydrolakes-polygons.json](styles/hydrolakes-polygons.json)
  - Source rows: 1427688; unique source IDs: 1427688; decoded and attribute-checked IDs at maximum zoom: 1427688.
  - No missing source IDs were reported at maximum zoom.

## Finalization evidence

All linked reports are local evidence files included in the complete package inventory.
- [browser-validation.json](reports/finalization/browser-validation.json) (SHA-256 `a2dd496536bf4d233d77ed03c3d02746393153721a681d09ff65b7a9d0918e24`)
- [hydrolakes-1.json](reports/finalization/geometry/hydrolakes-1.json) (SHA-256 `88e0c04ce2ab5a0378cbbeba72072960d5194ea60d8f5d6b6a3d8e7b2d25ba6a`)
- [hydrolakes-1.json](reports/finalization/pmtiles-verify/hydrolakes-1.json) (SHA-256 `bf51d67535ecb9b4b638abfdce3edc04d443c5b30ead8130c9c850c030cb96a4`)
- [hydrolakes-polygons.build-report.json](reports/hydrolakes-polygons.build-report.json) (SHA-256 `62f927143ac983d4229e7ed325e991e8abf3caff350bad7202c9de9144abd815`)

The finalizer reruns `pmtiles verify` and records the executable and archive hashes. Builder reports record maximum-zoom ID/attribute accounting. Explicitly supplied geometry reports establish the sampled, bounded Web Mercator display tolerance only. Browser reports establish the tested global and North America views, nonzero rendering, ranged HTTP 206 reads, and the 128 MiB response-body limit.
