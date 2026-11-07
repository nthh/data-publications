# LakeATLAS v1 analytic GeoParquet r2

This is the local evidence record for a source-faithful analytic conversion of both producer layers from the pinned LakeATLAS v1 File Geodatabase: polygons and pour points. The source-order assets remain available as raw conversion outputs. The package candidate uses a deterministic spatial-order derivative to support efficient spatial selection while preserving all decoded source columns, nulls, native identifiers, and WKB bytes. The helper adds/validates per-row GeoParquet bbox metadata; it does not repair source geometry.

## Validation gates

The acceptance criteria and fixed geography windows are in the dataset validation plan. The release evidence must include the raw source comparison, independent clean raw rebuild, primary and clean spatial-order reports, byte-identical asset checks, fixed-window pruning results, source/clean report binding, and package verification receipts. Reports containing machine paths must be retained locally and copied into the tracked evidence directory only after path-only redaction; `evidence/prepared-local/provenance/evidence-provenance.json` records original and portable hashes. No report may be rewritten in place.

The source conversion command and exact archive pin are documented in `datasets/lakeatlas/README.md`. The spatial-order helper and its locked environment are shared release tooling pinned by the package spec. Two processes are required per final asset: `--defer-validation --checkpoint ...` to write a candidate, then a fresh process with `--complete-stage ...` to validate and promote it. The checkpoint supplies all completion settings and does not accept overrides.

## Current status

Primary and clean-checkout spatial-order outputs are byte-identical and passed full source comparison, fixed-window row-group pruning, and Rashid PTL-DAT-006. Source/clean binding, STAC Node, Portolan, package integrity, bounded HTTP/CORS, DuckDB subset parity, and independent package verification all passed. The prepared package is local and unpublished; this record is not a publication approval. Receipt: [package-receipt.json](evidence/prepared-local/package-receipt.json). Manifest SHA-256: `32b4877b8809cabd3e2caca8da175115e8ff8317402058846ed0db06a54d52e9`. No registry mutation or upload occurred.


## Prepared local package

The candidate package is at `.local/lakeatlas/releases/lakeatlas-v1.0-r2-prepared` in the durable local artifact store. Both assets contain 1,427,688 rows and use EPSG:4326 WKB geometry with per-feature bbox metadata.

| Asset | Geometry | Extent (WGS 84) | Bytes | SHA-256 |
|---|---|---|---:|---|
| Polygons | MultiPolygon | `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]` | 1,143,992,867 | `bbef606fd8522b230efc90e2952a67c1e4265e7bf733208fa4cc31395a7277b7` |
| Pour points | Point | `[-179.99249799999998, -55.86087599999996, 179.9987920000001, 83.57118000000008]` | 283,780,050 | `ff621c1db763551cdb6ced8958eefcc9da76a73c16e7f7259c238bec3aae5720` |

The package manifest SHA-256 is `32b4877b8809cabd3e2caca8da175115e8ff8317402058846ed0db06a54d52e9`; independent verification passed with SHA-256 `aa052d84822625bed5887555c5746bd7489c88e62304c28bbb819dcf706924e3`. The [prepared-local package evidence index](evidence/prepared-local/package-evidence-index.json) matches every tracked copy to its package source hash. The evidence provenance ledger binds original report hashes to path-redacted copies. The tracked package README is review-only; its relative links resolve inside the standalone local package. The local Europe HTTP subset matched local DuckDB IDs/WKB: 5,262 polygon rows (12,517,544 bytes served) and 5,252 pour-point rows (5,366,428 bytes served).
