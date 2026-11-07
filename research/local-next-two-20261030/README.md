# Two next local conversions — 2026-10-30

Selected in processing order:

| Dataset | Scope | Frozen paper citations | Source bytes | Planned outputs |
| --- | --- | ---: | ---: | --- |
| GRWL | Current producer simplified global summary, file V01.02, 42,077 lines | 869 | 43,282,861 | GeoParquet + PMTiles |
| GRIP4 | Complete global roads FGDB, all seven regions | 817 | 2,334,355,294 | Partitioned GeoParquet + PMTiles |

Canonical decisions and source pins are in `datasets/grwl/dataset.yaml` and
`datasets/grip/dataset.yaml`. This dated review is supporting evidence, not a
second editable registry. Both remain **selected**, not converted or published.
The completed river-plastic pilot remains the sole prepared dataset.

The frozen citation counts are associated-paper counts from 2026-10-29, not live
counts or counts of exact-release users. Selection followed the recorded criteria.
GRWL is a small complete global component and GRIP4 is a larger global batch;
compressed plus extracted GRIP4 sources use about 6.5 GB before derived outputs.

## Source discovery and inspection

GRWL: [catalog](https://gee-community-catalog.org/projects/grwl/) →
[original Zenodo reference](https://zenodo.org/records/1297434) → its latest-record
pointer → [current source archive](https://zenodo.org/records/18624542).
The old summary was inspected first, then a newer filename V01.02 was discovered
in the latest archive. Both have 42,077 DBF records. The current record's descriptive
version label remains V01.01. Preserve that inconsistency, the exact filename and
checksums; do not treat it as identical to the older GEE asset. This selection uses
the current V01.02 file, with full ZIP MD5/SHA-256/CRC verified. Neither inspection
claims full attribute/geometry validation. See `grwl-version-review.json`.

GRIP4: [catalog](https://gee-community-catalog.org/projects/grip/) →
[PBL](https://dataportaal.pbl.nl/GRIP4) and
[versioned Zenodo archive](https://zenodo.org/records/6420961).
A bounded central-directory inspection transferred 6,447 bytes and identified
51 ZIP entries totaling 4,168,256,157 uncompressed bytes. Whole-download checksum,
SHA-256, layer/schema and feature count are pending. Use the chosen Zenodo CC BY
4.0 declaration; PBL separately states CC0. Preserve attribution and both sources.

`input-manifest.json` pins the saved API metadata. Raw producer HTML and the
6.25 MB Source Cooperative metadata snapshot are kept in ignored local storage.
`retrieval.json` records their original URLs, sizes and hashes. Do not mistake
metadata/header inspection for successful conversion or public-host validation.

## Existing representations and higher-citation leads

The full saved Source Cooperative JSONL snapshot contains 747 records. Searching
IDs, titles, descriptions, README text and other JSON fields for dataset names,
DOIs and associated-paper identifiers found no GRWL or GRIP match. Targeted web
searches likewise found no exact native copy. This is not proof of absence; the
catalog can be incomplete or stale. WaterNet and SWORD are different derived
river products. OSM and Overture are different road products.

Higher-citation leads were not silently treated as ready:

- MERRA-2 and TerraClimate counts refer to broad base families; the community
  entries contain derived or scenario products whose exact provenance needs work.
- SoilGrids already has a Source Cooperative Icechunk/Zarr mean-prediction product
  to inspect for reuse; missing components require a separate review.
- Glacier elevation change lacks a verified bounded manifest for the complete
  intended periods/error layers in this review.
- HydroLAKES is attractive, but its technical document's whole-original-database
  redistribution wording needs a specific review for the intended publication.
- The producer has deprecated Aridity/ET0 v3.0 and recommends corrected v3.1.
  Its current description also says non-commercial while the license field says
  CC BY 4.0; version and terms must be reconciled for a new public derivative.

The smaller global photovoltaic, HydroWASTE and GROD products remain alternatives;
the selected two have higher matched associated-paper counts. No conclusion about
scientific superiority follows from the ranking.

## Repeating the checks

From the repository root, with the saved public metadata snapshot available:

```sh
python3 research/local-next-two-20261030/check_existing_hosts.py \
  --catalog .local/selection-source-coop/catalog.jsonl \
  --report research/local-next-two-20261030/existing-hosts.json --check
python3 research/local-next-two-20261030/inspect_sources.py \
  --cache .local/next-two-sources --report .local/source-inspection-new.json
```

The second command downloads only the selected 43 MB GRWL ZIP if absent and
performs bounded remote reads on the GRIP4 ZIP. It refuses to replace a report,
validates GRWL against provider metadata and never runs conversion or GEE. To
repeat the old V01.01 inspection, supply `--grwl-record` pointing to
`research/local-next-two-20261030/upstream/grwl-zenodo.json` and
`--grwl-file GRWL_summaryStats_V01.01.zip`.
New registry values are schema/index checked with `scripts/catalog.py`; historical
audit and citation inputs remain byte-identical.
