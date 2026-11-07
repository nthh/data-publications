# Validation contract and preserved history

The pilot checks distinct questions separately: source fidelity, output usability,
published-summary consistency, and agreement with one captured GEE asset.
A passing conversion does not establish the scientific accuracy of the model.

## Release gates

- Verify the original ZIP's pinned 5,764,810-byte size, MD5 and SHA-256 before use.
- Compare every one of 2,160,280 original numeric cells, including nulls, and all
  40,760 source geometries. Preserve all 53 numeric fields, exact fixed-point
  values, original units, uncertainty and record multiplicity.
- Check GeoParquet metadata, row groups, bbox statistics and spatial ordering;
  inspect PMTiles structure and maximum-zoom identities, attributes and declared
  quantization tolerance. Verify the 19 source coincident-coordinate pairs.
- Validate STAC/Portolan metadata with pinned tools, verify every manifest asset,
  and test loopback byte ranges, CORS and a DuckDB spatial subset against source.
- Apply [publication-benchmarks.json](publication-benchmarks.json), registered
  before the original paper-summary evaluation. Check annual lower/upper totals,
  May–October share, nonnegative fields and ordered uncertainty triplets.
- Rebuild with the same committed workflow/environment into a separate directory;
  require all generated assets and the manifest to match. Require the migrated
  GeoParquet and PMTiles hashes to equal the original release's data hashes.
- Detect deliberate units, month-label, uncertainty, sign and null errors;
  run GEE matching/capture/provenance and package evidence-binding fault tests.
- When the raw GEE reference cache is available, verify every response hash,
  pagination chain, source-code hash, environment lock and stable metadata,
  then replay the historical strict failure and separately declared diagnostic.
  Package only when the complete profile has run.

## GEE history — failures remain failures

The original [strict contract](gee-parity-contract.json) required unique matches
within 1e-8 degrees per axis. All 40,760 GEE positions exceeded that threshold;
39 emission totals and null counts agreed. Its
[failed report](evidence/gee-strict-validation.json) is immutable.

A separately registered [one-metre diagnostic](gee-geometry-diagnostic.json)
associated 40,722 unique points, but failed for 38 records at the source's 19
coincident positions. Its [unique-only report](evidence/gee-unique-geodesic-validation.json)
also remains failed.

The [coincident-group diagnostic](gee-coincident-diagnostic.json) groups only
exactly coincident source coordinates and compares complete 53-field tuples as
multisets, preserving multiplicity. It does not match unrelated positions by
attributes. The [historical final report](evidence/gee-validation.json) records
2,160,076 exact numeric matches and 204 matching nulls. No numeric tolerance was
needed. Median displacement was 0.1787186 m; maximum was 0.3494564 m.

Google documents a default one-metre table-ingestion transformation allowance:
[table manifest guide](https://developers.google.com/earth-engine/guides/table_manifest).
This is a plausible explanation, not a demonstrated cause: the captured asset
metadata lacks an ingestion manifest, DOI or upstream version. The converter
retains Figshare geometry. No live GEE task is part of routine validation.

## Evidence and reproducibility limits

`evidence/` and the three GEE contracts preserve original bytes. Their historical
paths/commits refer to the prior workflow. `provenance/index.json` maps its 114
source/evidence entries to 44 content-addressed blobs, verifiable by
`python scripts/check_provenance.py` without the former Git repository.
New standalone reports live under `releases/figshare-v6-r2/` after rehearsal.

The research checks compare published summaries, not raw observations or
independent river/catchment truth. Named-river and regional crosswalk checks have
not run. The GEE capture is a dated reference with incomplete upstream provenance.
The raw response cache is local-only until separately published. Byte-identical
reproduction has only been demonstrated on this machine. Loopback HTTP checks
must be repeated against the actual public host after upload. No Source
Cooperative, Portolan or Folia registration acceptance is claimed.
