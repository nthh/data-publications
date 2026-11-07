# WWF Free-Flowing Rivers local GeoParquet

## GEE review — 2026-11-06

Live GEE count and all 521 sampled IDs match. A documented erosion-field alias, numeric precision and null/empty differences remain; five selected geometry diagnostics exceed 1 m, up to 2.877 m. Strict parity fails; original source values and geometry are retained. See the [complete comparison review](../../research/gee-release-validation-20261106/README.md) and [structured evidence](../../research/gee-release-validation-20261106/summary.json). The validated release is [public on Source Cooperative](https://source.coop/nthh/free-flowing-rivers); hosting checks do not change these scientific-comparison findings.


This workflow converts the complete `FFR_river_network_v1` layer in Figshare
v1 to a single analytic GeoParquet file. It preserves source FID `OBJECTID`, all
38 attributes, nulls, source row order, and source WKB. The extra `source_row`
field records the one-based source feature ordinal. A separately versioned
PMTiles package now provides map display; the analytical release stays unchanged.

The producer published one 954,710,486-byte File Geodatabase ZIP as article
`10.6084/m9.figshare.7688801.v1`, under CC BY 4.0. Current article metadata,
archive pins, schema inspection, and the producer field dictionary are in this
directory. The producer's v1.0 technical documentation is included in the source
ZIP. It describes a global network derived from HydroSHEDS at 15 arc-seconds,
with 8,477,883 reaches averaging 4.2 km. The FFR assessment is static and uses
source datasets assembled circa 2017. The `GOID` field is the producer's global
reach identifier; `OBJECTID` is the ESRI-generated unique row id for this file.

## Repeat the conversion

The release archive is public at:
`https://ndownloader.figshare.com/files/15090536`

Download it to ignored local storage as:
`.local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip`.
The script checks exact bytes before reading it. The source is accessed through
GDAL's `/vsizip/` virtual filesystem and is never extracted.

```sh
uv sync --locked --project datasets/free-flowing-rivers
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/acquire.py
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/inspect_source.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/build.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip \
  --output .local/free-flowing-rivers/figshare-v1-local-r1
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/validate.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip \
  --release .local/free-flowing-rivers/figshare-v1-local-r1
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/fault_tests.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip \
  --release .local/free-flowing-rivers/figshare-v1-local-r1
```

The comparison reopens the producer layer and checks every field, null and WKB
value in Arrow batches of 4,096 features. The fault checker verifies that row
removal, duplication, an attribute change, a null change, and a WKB change are
each rejected. See [VALIDATION.md](VALIDATION.md) for the precommitted criteria.
The build requires at least 40 GiB free before starting, stays under the 8 GiB
FFR-owned storage budget, and stops below 10 GiB free while retaining a partial
artifact for diagnosis.

These commands build the local analytical artifact. The separate publication workflow has
now hosted and verified the release on Source Cooperative; source fidelity does not establish
scientific accuracy. Registry submission is a separate decision. Data are CC BY 4.0; conversion source code is Apache-2.0.

## Published release

[Release r2](releases/figshare-v1-local-r2/README.md) contains the complete portable
evidence and reproduction commands for the final GeoParquet. Its exact manifest
is tracked in Git; the 887,132,886-byte data asset is public on Source and also retained in ignored local storage.
The source, clean rebuild, STAC, Portolan and local HTTP/subset checks passed.
The [hosted report](../../research/source-publication-20261106/hosted-results/free-flowing-rivers/hosted-validation.json) passes all seven hosting checks. No registry submission has occurred.

## PMTiles display

The local [display-v1 package](display/display-v1/README.md) adds generalized
PMTiles with stable source IDs and a portable style. Its generated manifest binds
the original analytical asset, complete maximum-zoom ID and selected-attribute
checks, sampled geometry validation, and browser range/attribute checks. The
GeoParquet remains authoritative for analysis and complete fields.

See the [repeatable display workflow](../../docs/display-derivatives.md) and
[local viewer](../../scripts/cloud_viewer/README.md). The published display and analytical data have passed their hosted checks; GEE parity remains a separate validation boundary.

## Source selection audit

Complete official global reach layer and attributes retained. No lower-detail source substitution found. The [2026-11-02 source audit](../../research/grwl-raw-release-20261102/source-audit/river-audit.md) distinguishes full source fidelity from scientific accuracy and records the limits of rebuild/GEE evidence.
