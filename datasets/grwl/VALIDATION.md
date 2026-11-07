# GRWL V01.02 local release acceptance contract

Scope: complete global simplified-summary polyline archive only, 42,077 records. The
V01.02 producer ZIP is pinned by DOI and SHA-256. The GEE catalog entry names
V01.01; no parity claim is made and no GEE request is in scope.

## Analytic product

- Match ZIP filename, 43,282,861 bytes, MD5, SHA-256, member CRCs, DBF schema,
  42,077 active records and 42,077 SHP records.
- Preserve all ten numeric source fields, source numeric widths/scales as fixed
  decimal values, `*` null markers as null, source row ordinal and producer IDs.
  Do not deduplicate coincident features or repair coordinates.
- Preserve every polyline part and every XY vertex in original order and binary
  float64 value; compare against an independent low-level SHP/DBF parser. Retain
  an explicit per-row bbox and GeoParquet bbox covering metadata/statistics.
- Record the SHP header bbox maximum X 180.00000000010002. Feature vertices themselves
  remain within valid longitude/latitude bounds (vertex maximum X about 179.99997);
  preserve all source vertices exactly. The display clamp is a no-op for this archive.
  STAC uses the valid global geographic envelope [-180,-54.31026,180,82.31062].

## Display derivative acceptance contract (criteria recorded before the first successful development conversion)

- PMTiles v3 vector tiles; layer `grwl`; preserve the producer `ID` attribute, which is non-unique, and use unique one-based `source_row` as tile feature ID.
- Maximum zoom 10, minimum zoom 0, no densest-feature dropping, and Tippecanoe's
  explicit `--simplification=2` line simplification (2 tile units). The display input clamps only X values to
  [-180,180] as a safety guard; this source has no out-of-domain vertices, so the
  display handling is a no-op. Analytic coordinates are untouched. Latitude is retained. No coordinate wrapping or buffer clipping is
  requested; map tile clipping is expected.
- At z10, every source row ordinal must occur in one or more decoded tiles. Lower
  zooms are overview-only; the derivative is not an analytic substitute. Check the
  full z10 ID set, feature attributes and tile coordinate bounds. These were the
  pre-conversion acceptance checks; subsequent geometric displacement work is a
  separately reported follow-up diagnostic.

## Follow-up display geometry diagnostic (added after development output inspection)

Tippecanoe 2.79.0 documentation defines its standard simplification tolerance as
one tile unit and `--simplification=2` as a scale factor. The validation samples 32
short z10 features and checks symmetric discrete Hausdorff distance in EPSG:3857, with vertices and segment
midpoints sampled (`densify=0.5`), against a format-derived bound of 2.71 tile units (2 simplification units plus the 0.71-unit
half-cell diagonal for MVT quantization; about 25.89 m at z10 equatorial scale). This
is a sampled diagnostic, not a continuous-distance guarantee.
This follow-up threshold was added after the initial development output existed; it
is not represented as preregistered acceptance criteria. Its actual result is kept
in a separate diagnostic field. The pre-conversion acceptance criteria remain the
zoom range, explicit simplification factor, no feature dropping and complete z10
source-row coverage stated above.

## Catalog, serving, package, and reproduction

- Check GeoParquet CRS/schema/row groups/statistics and execute bounded DuckDB bbox
  subset queries. Validate local STAC 1.1 catalog/collection and Portolan v0.2
  declaration, relative links, DOI, CC BY 4.0, field units, and provider order with
  Folia host last; publication remains pending.
- Exercise loopback HTTP byte ranges, CORS and DuckDB subset reads.
- Deliberately inject identifier, null, units, and geometry faults; each must be
  detected. Keep failed evidence distinct from passing follow-up diagnostics.
- Rebuild to a second clean output directory from the committed code and compare
  all manifest and asset hashes. Package an immutable local archive bound to the
  source, code, lock, reports and output checksums. No upload or registry submit.

Scientific comparison to published figures, observational accuracy, and V01.01
GEE parity are outside this conversion validation. Passing conversion checks only
establishes fidelity to the selected V01.02 archive.
