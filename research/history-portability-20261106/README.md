# Historical provenance snapshots

This archive preserves only source files needed to replay the five current strict GEE comparisons and the 100 historical workflow pins in the five existing release package templates. It contains no sample/capture payloads, bulk dataset data, or credentials.

Each index record binds the original full Git revision and repository path to a byte count and SHA-256. The file bytes are stored once at `blobs/<sha256>`. `scripts/provenance_archive.py` reads the exact historical Git blob when its commit exists. It falls back to an archive snapshot only when the commit object is unavailable; if Git has the commit but a different blob or a missing path, verification fails. Snapshot fallback requires the exact commit/path index record and valid size/hash.

Rebuild the archive while the historical Git objects are available:

```sh
python3 research/history-portability-20261106/export_snapshots.py
python3 scripts/check_provenance.py
```

`export_snapshots.py` derives comparison source pins from the checked-in comparison reports, receipts, request plans, and canonical dataset records. The sample source revision is `883ebbf0c1a157d402d7635a697bdde3822064ee`, matching the initial-sample note in `scripts/gee_validation/README.md`. It also reads only the five named package templates. Export is deterministic and never reads working tree source as historical content.
