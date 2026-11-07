# PMTiles coverage and measured GRWL width

This work adds display archives for HydroLAKES, Free-Flowing Rivers, and both
LakeATLAS layers, and changes GRWL line thickness to use `width_mean` in metres.
The existing GRWL and river-plastic PMTiles and all analytical releases retain
their original bytes. Work is local; no upload, GEE request or registry submission
is part of these display checks.

The [criteria](criteria.json), [integration contract](contract.json) and
[HydroLAKES ID representation diagnostic](id-encoding-diagnostic.json) were
committed before their associated acceptance checks. The reusable workflow is
in [display derivatives](../../docs/display-derivatives.md).

## Recorded boundaries

The builder reads actual maximum-zoom PMTiles features for complete ID and
selected-attribute accounting. The independent oracle compares a deterministic
sample against the original GeoParquet, with a 30 m Web Mercator geometry limit.
Its sample is the lowest eligible 32 IDs within the frozen global control plus
eight per regional window, with a 64-tile source-bbox cap. It does not test every
geometry or independently establish scientific accuracy.

Chrome checks use fresh contexts and real cross-origin static byte ranges. They
cover global and regional views, rendering, clicked attributes and the
128 MiB data-body ceiling. The regional browser view is Great Lakes for the
hydrography layers and Atlantic coast for river-plastic inputs; the separately
frozen geometry controls are unchanged. They do not certify a future public storage endpoint.
The scientific conclusions of the existing GEE audit are unchanged. Its original
canonical-record evidence is frozen byte for byte under [gee-context](gee-context/)
so later display metadata cannot silently change that evidence. The
[relocated audit](gee-validation.json) retains the original record checksums,
analytical-release bindings and source-audit hash; no GEE comparison was rerun.

## Preserved HydroLAKES diagnostics

The initial native build produced a structurally valid archive, but its metadata
check expected the wrong CLI header key names. An attempted rebuild was stopped;
the retained archive was independently audited and adopted without changing its
bytes. Tippecanoe had consumed the `Hylak_id` property into native MVT Feature.id.
The explicit ID diagnostic verifies that exact representation and rejects
conflicting properties; it does not waive source identity checks.

The first oracle had two reconstruction defects: it included tile buffer margins
and treated the derived ID as an undeclared property. The first core-clipping
correction then left microscopic seams between adjacent tile cores, causing
spurious polygon-boundary distances. The final validator uses identical indexed
tile-edge calculations on both sides of a seam. All 72 sampled IDs then pass,
with a maximum distance of 3.647025 m. No archive bytes or tolerance changed.

The subsequent sample-selector correction applies the tile-footprint eligibility
cap before ranking IDs within each Arrow batch. A regression fixture covers more
than 128 ineligible low IDs and reversed source order. HydroLAKES selected IDs
are unchanged. The current r3 report also binds source, archive and validator
hashes and explicitly states the geographic controls and sample exclusions.

[Reviewed diagnostic reports](diagnostics/) preserve both failed and successful
results. Each copy records the raw report SHA-256; only local data-root paths are
replaced by `<DATA_ROOT>`. Raw reports remain in ignored storage.

## Reproduction scope

Small point, line and polygon fixtures are built twice using the locked Python
libraries, Tippecanoe v2.79.0 and the recorded PMTiles binary. Production archives
receive source, coverage, geometry and browser checks; they have not been
independently rebuilt end to end during this task. The HydroLAKES initial command
was reconstructed from retained metadata/logs and is explicitly marked
retrospective; its original builder source hash was not captured.

The exact FFR launch builder bytes are retained in the checksum-named workflow
snapshot under `scripts/display_tools/snapshots/`. Later implementation changes
are separate from the running build's recorded code identity.

## Integration status

All five prepared products now have six PMTiles layers. The normal launcher from
a clean checkout verifies the canonical records and frozen upload plan, then
serves all six through static byte-range reads. GRWL uses `width_mean` in metres,
with a matching legend, thin unknown-width fallback, and a 1,000 m symbol cap.

| New archive | Source IDs accounted for at z12 | Archive bytes | Sampled IDs | Maximum sampled displacement |
| --- | ---: | ---: | ---: | ---: |
| HydroLAKES polygons | 1,427,688 | 1,122,881,121 | 72 | 3.647 m |
| Free-Flowing Rivers reaches | 8,477,883 | 3,570,445,458 | 72 | 1.655 m |
| LakeATLAS polygons | 1,427,688 | 1,190,009,288 | 72 | 3.647 m |
| LakeATLAS pour points | 1,427,688 | 409,205,238 | 72 | 1.599 m |

Each new archive has zero missing IDs, complete selected-attribute accounting,
a passing independent geometry sample against the 30 m threshold, and a passing
native `pmtiles verify` report. These counts describe the source identities at
maximum zoom; displayed fragment counts at other zooms are different.

The [final structured verification](rehearsal/final-verification.json) binds the
[12 passing browser cases](rehearsal/browser-final-r2/browser-validation.json),
archive evidence, source pins, screenshots and offline metadata checks. Every
case uses a fresh Chrome context and passes rendering, inspection, HTTP 206/CORS
and partial-read checks. The largest measured case transferred 26,151,359 bytes
of data bodies, below the 128 MiB ceiling; UI/runtime bytes are separate. The
LakeATLAS cases also switch layers and fetch all source attributes. Screenshots
are taken after that switch, so the structured screenshot index identifies the
layer actually shown. GRWL width and both LakeATLAS regional screenshots were
visually reviewed.

The [final native fixtures](rehearsal/final-fixtures.json) rebuild point, line and
polygon archives twice with the final builder. Every hash matches both earlier
checkouts. All ten frontend files from the final normal launch match the earlier
byte-identical build. Production archives were not independently rebuilt twice.

The [frozen upload plan](staging-r1/immutable-upload-plan.json) contains five
products, 279 files and 9,763,387,848 bytes; the six PMTiles total 6,382,791,934 bytes.
This is local preparation. The plan still records missing account-verification
evidence, and nothing was uploaded or entered into the public Portolan catalog.

## River-plastic browser control diagnostic

The first full browser run passed eleven cases, but the river-plastic regional
case rendered zero features in the shared inland Great Lakes box. The failed
[report](diagnostics/browser-final-r1.json) and [screenshot](diagnostics/plastic-inland-control-failure.png)
are preserved. Before inspecting source counts or rerunning a replacement case,
we committed the [coastal diagnostic criteria](coastal-control-diagnostic.json).

The pinned original GeoParquet contains zero points in the inland box and 792
in the predeclared Atlantic coast box `[-82, 25, -66, 45]`, as recorded in the
[source coverage diagnostic](diagnostics/plastic-source-coverage.json). The
replacement regional case renders 40 tile features at its fitted zoom and passes
all original transfer and inspection requirements. No dataset bytes, global
control, geometry controls, or acceptance thresholds changed.
