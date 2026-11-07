# GRIP4 conversion and display contract

Registered before evaluating converted output, 2026-10-30. The original selection
requirements remain in VALIDATION.md; this file makes their implementation precise.

## Source and analytics

Require the complete pinned global File Geodatabase and producer dictionary. Verify
ZIP size/MD5/SHA-256/CRC and extracted member size/CRC. A source inspection records
layer, field order/types, CRS and feature count before the first conversion.

Preserve all original source columns and the File Geodatabase feature identifier.
Only the geometry column is renamed `geometry`; preserve its original WKB bytes.
Add per-feature `bbox` with xmin/ymin/xmax/ymax. Never normalize coordinate precision,
repair invalid lines, deduplicate features, or reinterpret zero codes as missing.
Keep original integer, float and string Arrow types and explicit null masks.

Write seven regional GeoParquet 1.1 files, ordered by a 16-bit Morton key of the
feature envelope center, then source ID. Row groups contain at most 65,536 rows;
WKB CRS is OGC:CRS84 and bbox covering statistics must be present. A conservative
whole-source envelope is valid metadata for each partition; per-feature and row
group envelopes remain exact and support spatial pruning.

Compare every output source field and WKB against a fresh source read in source-ID
order. Exact checks include null masks and floating-point bits, not aggregate totals
alone. Both readers use the GDAL OpenFileGDB decoder; this is independent execution,
not an independent implementation of the proprietary encoding. Account for all seven
producer regions and compare the source count with the community's 25,758,453.
Source-invalid geometry may be retained and reported; introduced changes may not.

## Display (not an analytic inventory)

All source features enter Tippecanoe 2.79.0. Build zooms 0–10 with layer `roads`,
4096 units per tile at every zoom, simplification scale 1, 5 screen-pixel buffer,
500,000-byte / 200,000-feature tile limits, and `drop-densest-as-needed`. The map may
omit short or dense roads at any zoom. No completeness percentage is promised for
PMTiles; the complete inventory is GeoParquet. Require nonzero representation of
all seven source regions at every zoom and report exact unique-ID retention by
zoom and region, with buffered duplicates counted separately.

Exhaustively parse all tiles: require valid source IDs, line geometry, and exact
producer region/road-class properties. Verify PMTiles v3 directory structure.
For geometry, choose the 16 tiles with lowest SHA-256(z/x/y) at each zoom (all tiles
if fewer), then up to eight features with lowest SHA-256(source ID) per tile.
Compare every sampled output vertex and segment midpoint to the original line
projected into the tile; allow 4 tile units for simplification (nominal 1 unit),
quantization and boundary clipping. Test neighboring world copies at the dateline.
Require geometry within the declared clipping buffer. This sampled metric cannot
certify every rendered vertex or network topology; disclose its exact scope.

## Release gates

Verify every asset checksum, build-input hash and immutable dataset.yaml snapshot;
STAC schema validation must pass both documents with none skipped. Portolan v0.2
schema/local-data validation must pass. Test local HTTP byte ranges/CORS and a
DuckDB geographic query spanning all seven partition URLs. Run deliberate dropped,
duplicated, changed-value, changed-null and changed-geometry fixtures. Rebuild in a
clean Git checkout from the same commit and locked environment, comparing every
asset and manifest byte. No cross-platform determinism claim is made.

Package only passing, manifest-bound reports, exact workflow source and separate
software/data licenses. No source upload, remote host test, registry submission,
GEE query, current navigation claim or independent observational validation is
included. Preserve any failed run and document follow-up changes before retrying.

## Source inspection addendum (before first conversion)

The full producer ZIP passed size, MD5, SHA-256 and CRC checks. SHA-256 is
`851c26a530950f24252465bc67d18fc10ce735d10a1a3d11a06ebfff45c4c8cc`.
Layer `GRIP4_GlobalRoads`, EPSG:4326, contains exactly 25,758,453 features,
matching the catalog count. Original columns are `OBJECTID` (int64 FID),
`GP_RTP`, `GP_REX`, `GP_RAV`, `GP_RRG`, `GP_RCY`, `GP_RSE`, `GP_RSI`,
`GP_RSY` (int32), `Shape_Length` (float64), `gp_gripreg` (int16), and
`Shape` (binary WKB, renamed `geometry`). Preserve names and types otherwise.

The source envelope ends at longitude 180.0000000000001. Preserve those actual
coordinates and analytic bounds. Only STAC's envelope may normalize an overshoot
of at most 1e-8 degree to its legal longitude/latitude limits; reject larger
overshoots. Record the original envelope in quality metadata. This changes no
analytic coordinate and does not justify increasing any geometry-error tolerance.
