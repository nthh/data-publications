# HydroATLAS LakeATLAS v1.0 — global hydro-environmental lake attributes

Two analytic GeoParquet assets from the pinned LakeATLAS v1.0 producer File Geodatabase: the complete polygon layer and separate pour-point layer. The deterministic spatially ordered representations preserve producer OBJECTID, Hylak_id and all decoded source fields, nulls, and WKB; WGS84 bbox fields support spatial filtering. No geometries are repaired or simplified. Attribute years vary by source and do not represent a 2026 observation.

License: other.

Immutable package: https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/

Source producers: HydroSHEDS / HydroATLAS authors; Lehner, Messager, Korver, and Linke

Source provenance: https://doi.org/10.6084/m9.figshare.19312001.v1
Original describedby notes: https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/README.md
Original agents notes: https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/AGENTS.md

Canonical publication limits:

- Source fidelity does not establish scientific accuracy of the contributing attributes.
- Attribute observation vintage varies; this release is not a single-year observation.
- PMTiles display-v1 is published separately for polygons and pour points; use GeoParquet
  for analysis.
- Source polygon WKB is decoded using GDAL OpenFileGDB ring organization; a source
  feature with more than 100 parts emits a warning. No later geometry repair or simplification
  is applied.
- Aggregate catalog hosting has separate verification evidence; registry submission
  requires a separate decision. Dataset hosting checks are distinct from historical
  loopback checks.
- Live GEE counts and 522 sampled IDs per layer match. Both layers have numeric differences
  including integral GEE GDP values; the polygon layer also has three narrow source
  spikes absent spatially from GEE. Strict parity fails. No exhaustive GEE or independent
  scientific-accuracy claim.
