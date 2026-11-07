# Standalone local release: figshare-v6-r2

The clean clone of this standalone repository at commit
`4c54a01451967421bf17b1346cd749c0738efdde` completed the full rehearsal.
Two independent output directories produced identical manifests and 14 assets.
GeoParquet and PMTiles match the original r1 data hashes. The new revision adds
canonical-record provenance, source-quality notes and current validation evidence.

The source/geometry/format, STAC/Portolan, paper, HTTP loopback and cached GEE
checks ran; 39 deliberate-fault tests passed. Strict GEE coordinate parity still
fails. Its separate geodesic/coincident-group diagnostic passes without changing
source data. Read `rehearsal.json`, `validation.json`, `gee-strict-replay.json` and
`gee-validation.json` together. The receipt binds all 34 archive members.

The first migration rehearsal failed Portolan's designated-host requirement.
That failed attempt remains in the ignored local rehearsal workspace; the metadata
fix was committed before this new run. Historical research/GEE failures remain
in the versioned evidence and are also included in the package.

`release-receipt.json` retains the exact original local archive path from the
rehearsal. The ready-to-publish copy is at the repository-relative ignored path
`.local/river-plastic-inputs/river-plastic-inputs-figshare-v6-r2.zip`.
The 9,644,436-byte ZIP has SHA-256
`82e7c87b4c3101b792b6f1f2b777361f123f97933f0256b07eb7daafd7d19c77`.
No remote hosting or registry acceptance is claimed.
