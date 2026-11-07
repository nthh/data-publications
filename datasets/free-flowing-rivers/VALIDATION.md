# Free-Flowing Rivers release acceptance criteria

These criteria were recorded before inspecting or converting the new source archive.

## Source and scope

- Confirm the latest Figshare article version, file inventory, license, authors,
  producer documentation, ZIP size, and provider checksum from the public API.
- Keep the complete selected File Geodatabase archive immutable. Record SHA-256,
  MD5, CRC status, GDAL layer names, row counts, CRS, field order/types/nullability,
  geometry type, and feature extent before conversion.
- Confirm the chosen layer is the published full global reach assessment described
  by Grill et al. (2019); do not substitute a table, subset, or derived layer.

## Analytic preservation

- Emit a single GeoParquet file. Preserve every selected source feature and source
  field in its original order, values, nulls, data types, and WKB geometry bytes.
  Add only an explicit one-based `source_row` ordinal after the source fields.
- Preserve row order and multiplicity. Do not repair, simplify, reproject, round,
  normalize or deduplicate geometry or attributes.
- Verify Parquet reads successfully, GeoParquet metadata identifies the actual
  source CRS and geometry column, and bounding-box metadata and per-row-group
  statistics are present and consistent.
- Independently reopen the source and compare every source field, null, geometry
  WKB, and row ordinal against the output in bounded Arrow batches.
- Inject mutations that remove a row, duplicate a row, change an attribute, alter
  a null, and alter a geometry; each must be rejected for the corresponding
  fidelity check.

## Repeatability and limits

- Build only after conversion code and its locked environment are committed.
  Rebuild in a clean checkout into a different empty directory and compare the
  GeoParquet SHA-256 byte-for-byte.
- Keep peak memory at or below 1 GiB and owned local data under 8 GiB. Read the
  File Geodatabase through GDAL virtual ZIP paths; do not extract the archive.
- This release establishes exact conversion fidelity to the pinned Figshare
  archive only. It does not independently validate the scientific assessment or
  its circa-2017 observation vintage.
- Display derivatives, hosting, remote range checks and registry submission are
  outside this analytic-only local build.
