# Planned GRIP4 conversion validation

These are requirements for future processing. Only metadata and the remote ZIP
central directory have been inspected; no source/content validation has passed.

1. Download the pinned global FGDB ZIP from the versioned source. Verify
   2,334,355,294 bytes and MD5 `526db5eb478f4c990e27fcbc471abf4b`; compute SHA-256,
   check ZIP CRCs, and record the actual dataset layer/schema/CRS/feature count.
2. Account for every global source feature and all seven regions. Compare with
   the catalog's reported 25,758,453 features; investigate and document any
   discrepancy rather than changing the reference after observing results.
3. Register the precise field mapping, null/encoding handling and geometry/ID
   criteria after source inspection but before conversion evaluation. Use the
   producer attribute dictionary. Preserve types, source identifiers, original
   coordinate precision and all attributes in analytic output. Do not deduplicate
   coincident road lines or infer IDs from row positions across independent files.
4. Stream bounded batches and write spatial partitions. Independently compare
   per-feature values, IDs, geometry and per-region counts across source/output;
   aggregate hashes are additional integrity evidence, not substitutes for parity.
5. Predeclare PMTiles display thinning/simplification and coverage at each zoom.
   Retain the full road network in GeoParquet. Register clipping/quantization and
   maximum-zoom ID checks before tile evaluation; document display limitations.
6. Check GeoParquet/STAC/Portolan conformance, ranges/CORS/subset queries on a local
   server, deliberate lost-feature/duplicate-ID/null/geometry faults, and an
   independent same-code rebuild. Pin any paper-summary comparison separately;
   neither source parity nor a rounded global road total proves scientific truth.
7. GEE comparisons require separate task authorization and must distinguish all
   seven catalog regions from the global source archive. No live GEE call, export,
   remote publication or registry submission is part of this selection task.
8. Preserve evidence of failures and package only after the declared release gates
   actually pass. Measure working disk needs and leave headroom before starting.
