# Mapping the world's free-flowing rivers — global river reach connectivity assessment

Analytic GeoParquet conversion of the full global free-flowing river reach network from the pinned 2019 figshare v1 source. Original source fields and WKB geometries, nulls, row order, and record multiplicity are preserved. Added columns expose the producer-stream row ordinal and per-feature EPSG:4326 bounds. This release does not assess scientific validity or update the source assessment.

License: CC-BY-4.0.

Immutable package: https://data.source.coop/nthh/free-flowing-rivers/releases/figshare-v1-local-r2/

Source producers: Günther Grill; Bernhard Lehner

Source provenance: https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801
Original describedby notes: https://data.source.coop/nthh/free-flowing-rivers/releases/figshare-v1-local-r2/README.md
Original agents notes: https://data.source.coop/nthh/free-flowing-rivers/releases/figshare-v1-local-r2/AGENTS.md

Canonical publication limits:

- Immutable analytical and display releases are hosted and verified. Aggregate catalog
  hosting has separate verification evidence; registry submission requires a separate
  decision.
- The 2019 publication is a static assessment, not current river connectivity.
- Source fidelity and same-machine reproducibility do not establish independent scientific
  accuracy.
- PMTiles display-v1 is published separately; use the unchanged GeoParquet release
  for analysis.
- Live GEE count and all 521 sampled IDs match. A documented erosion-field alias,
  numeric precision and null/empty differences remain; five selected geometry diagnostics
  exceed 1 m, up to 2.877 m. Strict parity fails; original source values and geometry
  are retained.
