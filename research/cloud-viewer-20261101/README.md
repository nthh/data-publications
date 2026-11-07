# Local viewer and GEE evidence audit

Five prepared products render as six layers directly from static HTTP object
storage: GRWL and river-plastic inputs use existing PMTiles; HydroLAKES,
Free-Flowing Rivers, and LakeATLAS polygons/pour points use existing GeoParquet.
GDW and SWOT have no prepared release and show their actual blockers.

[Start or restart the viewer](../../scripts/cloud_viewer/README.md). This work
changes no dataset files and performs no uploads, new conversions or live GEE work.
The Python server serves only static bytes. GeoParquet queries run in the browser.

## Have all five been validated against GEE?

**No. Only river-plastic inputs has a recorded GEE data comparison.**
[The structured audit](gee-validation.json) binds each conclusion to its selected
release, manifests and exact evidence SHA-256 values.

| Prepared release | Existing GEE comparison |
| --- | --- |
| River-plastic inputs `figshare-v6-r2` | All 40,760 records and 53 fields compared; numeric values and nulls match. Coordinate differences remain, up to 0.349456 m. |
| GRWL `summary-v01.02-local-r1` | None. The selected producer V01.02 differs from the catalog's V01.01 counterpart. |
| HydroLAKES `v1-local-r3` | None. Producer-source fidelity and rebuild evidence exist. |
| Free-Flowing Rivers `figshare-v1-local-r2` | None. Producer-source fidelity and rebuild evidence exist. |
| LakeATLAS `lakeatlas-v1.0-r2` | None for either polygons or pour points. Producer-source fidelity and rebuild evidence exist. |

The original river-plastic strict-coordinate check failed for every location and
compared no attributes in that failed pass. A separate 1 m diagnostic matched
40,722 unique records; a further coincident-coordinate multiset control accounted
for 19 groups / 38 records, preserving their multiplicity without asserting
individual identity within each group. The complete follow-up accounts for
2,160,076 numeric and 204 null cells. These are documented follow-up diagnostics,
not a strict geometry pass. The captured GEE asset lacks an ingestion/version
manifest, so agreement cannot establish exact Figshare edition identity or
scientific truth. The other producer comparisons do not substitute for GEE checks.

## Browser verification

[Criteria](criteria.json) were committed before evaluating the viewer. The
[final browser run](browser-r8/browser-validation.json) uses a fresh installed
Chrome context for each layer, separate UI/object origins, and blocks external
requests and whole-file data GETs. Every data GET completed as HTTP 206 with the
requested Content-Range, exact object size and CORS headers. No page errors or
external requests occurred. Each case stayed below the predeclared 128 MiB limit.

| Layer | Visible features | Initial data read | Including attribute inspection |
| --- | ---: | ---: | ---: |
| GRWL display, global | 40,917 tile features | 2,259,157 B | 2,259,157 B |
| River-plastic display, global | 67 tile features | 20,353 B | 20,353 B |
| HydroLAKES, southwest Europe | 606 | 5,020,112 B | 5,621,080 B |
| Free-Flowing Rivers, southwest Europe | 1,500, display capped | 14,499,221 B | 15,139,907 B |
| LakeATLAS polygons, southwest Europe | 606 | 9,606,003 B | 15,042,360 B |
| LakeATLAS pour points, southwest Europe | 603 | 7,294,565 B | 12,384,072 B |

These are viewport results, not global source feature counts. PMTiles can simplify,
filter or split source features. Analytical bbox queries cap the display at 1,500
records, and geometry is shown in 2D. Byte totals exclude the approximately 40 MB
static UI/runtime/context bundle and HTTP headers. The exact fitted viewport is
recorded in each result; other regions and future cloud hosts are not certified
by this run.

All four GeoParquet cases successfully loaded all attributes for a selected ID
(21, 40, 308 and 306 non-geometry fields), and the wide-view guard cleared the map
before refusing a global scan. Both unavailable datasets showed zero features.
The UI's byte counter matched completed data response sizes in every case.
Screenshots accompany the report; [LakeATLAS](browser-r8/lakeatlas-1.png) shows the
attribute panel and [GRWL](browser-r8/grwl-display.png) shows the global display.

Earlier failed checks remain under `browser-r1` through `browser-r6`; the first
successful HydroLAKES diagnostic is `browser-r7`. [Development findings](development-findings.json)
explain missing worker/extension assets and the forced-full-read configuration
failure. The final implementation bundles pinned runtime assets and explicitly
disables full HTTP reads. No criteria or data were changed to make the checks pass.

## Repeatability and boundaries

The immutable Source Cooperative plan was prepared with **236 exact files,
3,470,460,522 bytes**, verified by SHA-256. Runtime configuration is generated from
the canonical records, plan and GEE evidence; it is ignored and contains local
paths. The public config contains no filesystem paths or credentials. No new
editable dataset inventory was introduced.

Twenty focused Python tests cover exact plan/evidence binding, package discovery,
changed or missing files, symlink/traversal handling, CORS, ranges and public-config
redaction. Seven client tests cover coordinate decoding, bounded SQL, origin
validation, exact IDs/nulls and range-response validation. Existing record,
publication-catalog, product-draft and historical-provenance checks also pass.
CI runs the synthetic checks and builds the browser bundle; real-data browser
checks require the retained local packages. Remote CI has not been run in this task.

`ui-build.json` records the exact built asset hashes, and `verification.json`
records checks and evidence bindings. The [clean-checkout rehearsal](clean-checkout.json)
passed using cached dependencies and a fresh locked Python environment. All ten UI
assets reproduced byte for byte; all 236 object pins and generated public metadata
matched. The documented launcher started a detached server, all six layers returned
correct partial ranges, and a fresh HydroLAKES browser smoke check passed. No bulk
data were copied.

Successful rendering is a transport/UI check. It does not establish scientific
accuracy, GEE equivalence, exhaustive geographic validation, or public-hosting
readiness. No Source Cooperative data endpoints were changed or asserted live.
