# GRIP4 and current road alternatives — 2026-10-30

This follow-up responds to the question raised after GRIP4 was selected and its
local conversion started. It does not rewrite the frozen intake, citation counts,
selection criteria or source-fidelity acceptance contract.

For current roads, prefer Overture upstream. Preserve GRIP4 as a historical
research input when a study needs the exact GRIP4 release. This is a use-case
recommendation, not evidence that Overture officially succeeds GRIP4 or contains
every GRIP4 road. No head-to-head coverage or positional-accuracy test was run.

## Evidence checked

- [PBL's GRIP4 page](https://dataportaal.pbl.nl/GRIP4) describes the dataset as
  harmonized input for global environmental and biodiversity modelling and links
  the 2018 publication. The selected archive is the fixed GRIP4 source, not a
  current continuously updated road map.
- [Overture transportation documentation](https://docs.overturemaps.org/guides/transportation/)
  describes global coverage, monthly releases, OSM plus TomTom and other source
  contributions, and an explicit segment/connector network. Transportation is
  distributed under ODbL; retain its own attribution and license metadata.
- [Overture's cloud access documentation](https://docs.overturemaps.org/getting-data/cloud-sources/)
  provides existing GeoParquet, a versioned STAC catalog and PMTiles. The PMTiles
  are intended for inspection, with no stable-layer or availability commitment;
  an application requiring stable tiles may need its own derivative.
- [Overture's network model](https://docs.overturemaps.org/guides/transportation/segments-and-connectors/)
  uses its own segmentation and classes, including splits at class transitions.
  Raw feature counts are not a valid coverage comparison with GRIP4. Replacing
  GRIP4 with Overture changes a study's input and requires a new methods decision.
- [Overture's mirror list](https://docs.overturemaps.org/getting-data/data-mirrors/)
  identifies Fused on Source Cooperative and retains S3/Azure as the source of
  record. [Fused's product](https://source.coop/fused/overture) includes transportation
  partitions. This review did not verify that its newest release matches upstream
  or validate its data bytes. The already saved 747-record Source Cooperative
  snapshot also includes `fused/overture`; its other Overture products include
  narrower building, boundary and regional-road scopes.

[Overture's explicit retention policy](https://docs.overturemaps.org/release-calendar/#data-retention-policy)
limits public data releases on S3/Azure to at most 60 days. A Git version pin alone
does not ensure long-term retrieval. The cloud-access page's general reference to
an archive must not be read as indefinite retention. For a study needing a fixed
Overture version, verify a durable archive or arrange preservation of the required
source bytes; a mirror's retention must be checked separately.

The local Folia registry already contains `@overture/maps/transportation`, with
preferred distribution `overture-maps-2026-10-21` using official STAC discovery for
GeoParquet segments. [The inspection receipt](overture-folia-registry.json) pins
the repository revision and two metadata-file hashes. This review did not probe
the actual data assets or change Folia. Current-road work should reuse that identity
rather than introduce a second equivalent dataset entry.

The selected GRIP archive's CC BY 4.0 metadata and PBL's CC0 statement remain a
separately recorded source-license discrepancy. Overture's license does not
replace or resolve GRIP4's metadata.

## Consequence for this repository

Complete the already authorized local GRIP4 conversion as a reproducible archival
product. Describe it as GRIP4 (2018), and link current users to Overture. Preparation
does not create a Source Cooperative product or submit a Portolan record.

For future selections, check both exact native copies and usable alternatives for
the intended task. Rank missing access to a useful, distinct product ahead of a
redundant conversion. Associated-paper citations measure research adoption; they
do not establish current map quality or the need for a new host.

Reference Overture's existing catalog for current roads. A new mirror or conversion
needs a concrete unmet need, such as a required historical version, different
partitioning or a stable application-specific tile schema. Keep an alternative
relationship in review metadata separate from exact-dataset equivalence. Do not
mark Overture as GRIP4's mirror or claim its existence proves global superiority.
