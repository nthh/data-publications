# SWOT v2.03 bounded qualification and storage plan

Observed 2026-11-02 UTC. This is a proposed, gated plan; no SWOT source tile was acquired in this retry.

## Current evidence and gate

The filesystem had 41,599,676,416 free bytes (38.74 GiB), below the criteria's 42,949,672,960-byte (40 GiB) start floor. Therefore the guarded AU_55 retry was not run. The prior failed preflight remains in `research/gdw-swot-preparation-20261101/swot-au55-inspection.json`; it downloaded zero bytes. The only source-body evidence remains its earlier 16-byte HTTP 206 response, sufficient to identify a SQLite header, not to inspect SQLite schema or verify a file checksum.

The captured producer inventory lists 61 scientific v2.03 tiles at 29,990,277,120 provider-declared bytes. It includes an MD5 per tile, and identifies AU_55 as 14,954,496 bytes; the largest tile is NA_72 at 3,953,864,704 bytes. These values are metadata claims, not independently downloaded byte counts. The collection metadata names a single `pld`/`lakes` layer. That metadata does not establish actual SQLite tables, auxiliary-table layout, schema, IDs, relationships, or output size.

## Retention target

Budget no more than 8 GiB (8,589,934,592 bytes) of new retained bulk output. Keep existing repository files untouched. Treat source downloads as one-tile scratch, not retained package assets. Download at most one tile at a time, verify its full provider size and MD5 before opening it, record SHA-256, then inspect in immutable read-only SQLite mode with extension loading disabled. Keep a verified temporary source tile until its conversion has passed per-table checks; then remove only that task-created scratch copy. Stop if free disk approaches 10 GiB. Never start a tile transfer below the 40 GiB free-space floor.

## Proposed representation, conditional on AU_55 inspection

1. Freeze the inspected table inventory: every ordinary source table, its columns and declared types, primary-key positions, foreign keys, indexes, row count, view definitions (without executing views), and SQLite metadata tables. Record unknown/unrecognized objects; do not load virtual-table modules or source-defined extensions.
2. Convert each spatial table to one GeoParquet table per source table/tile. Preserve source table and column names, every source row, nulls, geometry coordinate values, original primary-key values and related IDs. Use lossless geometry encoding and no simplification or filtering.
3. Convert every non-spatial ordinary table—including auxiliary/lookup tables—to a Parquet table, preserving all rows, columns and key values. Preserve relevant SQLite spatial metadata (`geometry_columns`, `gpkg_contents`, and any other observed producer tables) as lossless tabular outputs plus a machine-readable schema snapshot. Do not assume these named tables exist; the sample must establish the inventory.
4. Retain one compact manifest per tile with provider filename, tile ID, byte count, MD5, SHA-256, SQLite integrity result, table inventory, row counts, and source-to-output table/column mapping. Bind all outputs to the source tile and exact checksums.
5. Validate before releasing tile scratch: source and output counts match for every source table; all primary-key values and all foreign-key/reference values are preserved; null counts and schema types match; spatial feature counts match; geometry type/CRS and bounds are recorded; and a round-trip read of each output succeeds. Preserve legitimate nulls and unmatched/orphan relationships as found. Test global IDs across tile boundaries before concatenation; keep the tile key with each row if IDs are not globally unique.
6. Measure actual output bytes tile by tile. Keep all source and auxiliary logical tables only if the complete retained result, including manifests, stays within 8 GiB. If it exceeds the cap, stop without dropping tables or fields and return a measured size estimate/retention decision; do not silently relax the budget.

This strategy deliberately retains the logical contents and identifiers of all observed SQLite tables, rather than the original SQLite container bytes, because the 29.99 GB source exceeds the 8 GiB retained-output budget. Whether this full logical-preservation representation fits 8 GiB cannot be estimated from the 16-byte header and inventory metadata; it is unvalidated until at least one whole tile is downloaded and measured. The AU_55 sample is small but may not represent large-tile schema or output compression. A global conversion remains gated on representative schema/size checks and an explicit measured fit.

## Reproduction

The next allowed sample run, once the disk floor passes, uses the existing guard and a fresh evidence destination:

```sh
python research/gdw-swot-preparation-20261101/inspect_swot_sample.py \
  --inventory research/gdw-swot-preparation-20261101/swot-v203-inventory.json \
  --report research/source-products-20261101/sources/swot-au55-inspection-<new-UTC-date>.json \
  --storage-dir .local/swot-qualification-<new-UTC-date>/AU_55
```

The run remains capped by the script at 128 MiB for the file, with the producer MD5 required before inspection. Use a new report/storage path; never overwrite the earlier failed preflight.
