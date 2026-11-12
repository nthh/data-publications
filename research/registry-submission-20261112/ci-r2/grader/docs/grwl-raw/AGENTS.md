# Global River Width from Landsat — raw vector observations V01.01: query guidance

Static producer release derived from Landsat observations with varying source dates; not current river conditions or a time series.

Use the following dataset-specific constraints when choosing records, interpreting values, or making comparisons:

- All 64,572,998 source records passed exact independent source comparison and a byte-identical clean analytical rebuild. Complete uploaded bytes and anonymous hosting, range, CORS, subset-query and browser checks passed.
- Raw observations are separate source records and short parts, not a connected river centerline network. Records are never joined by segmentID or segmentInd.
- width_m value 1 is an unknown-width sentinel; width_valid indicates usable width without altering width_m.
- The release excludes masks, tile index, and RSSA basin supplement.
- PMTiles is a quantized display derivative. Zooms 0–7 select the widest valid original observation per screen-scale cell, retaining its source ID and anchor. Symbols are exaggerated and capped, not averages or riverbanks. Zooms 8–12 retain the original detailed tile payloads.
- All 64,572,998 source records were independently checked for overview winner selection; every selected table row and all 26,060,623 encoded point placements in 4,439 overview tiles passed. All 588,355 detailed compressed tiles exactly match r2. The same 304 enumerated 0.0013–2.93 m source fragments collapse at z12 and remain preserved in GeoParquet, with no new detail omissions.
- Twenty fixed browser cases cover Mississippi z0–12, Amazon and the dateline, including one exact-ID lookup of all fourteen source attributes at z7. The clean byte replay is regional. The viewer retains its existing non-wrapping world edge; global scientific accuracy is not established. Hosted browser checks cover the same twenty fixed views.
- Live raw-V01.01 GEE count and all 512 sampled compound keys match; all 5,120 source attribute cells are exact. Selected mixed geometry diagnostics are below 0.340 m, but strict geometry parity fails. No exhaustive GEE, topology-preservation or independent scientific-accuracy claim.
- The Parquet metadata footer is 19,783,655 bytes. The tested cold exact-ID browser lookup transferred 20,941,975 bytes, including that footer; this is one fixed-view measurement, not a universal query-cost guarantee.

[Field dictionaries, runnable queries and source citations](README.md).
[Shared catalog conventions](../AGENTS.md).
