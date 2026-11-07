# Native publication gaps — review of 31 October 2026

The corrected shortlist has **eight stronger candidates and two conditional candidates**, not ten proven absences. Ranking considers useful additional access, global scope, associated-publication demand, release readiness and maintenance. A citation leaderboard alone did not answer the publication question. No equivalent public native release was identified for the precise scopes below in the bounded checks; that does not establish universal absence.

These are dated recommendations. `datasets/<id>/dataset.yaml` remains the editable inventory. This report does not promote candidates, change existing source pins or authorize builds/publication.

| Rank | Exact proposed scope | Original access → proposed output | Why it remains / current state |
| --- | --- | --- | --- |
| 1 | [LakeATLAS v1.0](https://www.hydrosheds.org/hydroatlas): lake polygons, pour points and full attributes | FileGDB/Shapefile → GeoParquet | Useful lake enrichment; both layers prepared locally. Preserve per-attribute licensing and source documentation. |
| 2 | [WWF Free-Flowing Rivers 2019, Figshare v1](https://doi.org/10.6084/m9.figshare.7688801.v1): complete reach assessment | FileGDB → GeoParquet | Connectivity and pressure attributes are distinct from generic river lines. Prepared locally; identify the historical assessment explicitly. |
| 3 | [TerraClimate v1.1](https://www.climatologylab.org/terraclimate.html): full reprocessed monthly historical baseline, 1950–2025 | Annual NetCDF → Zarr/Icechunk | Specific edition/coverage gap. Planetary Computer already has TerraClimate Zarr, but its current metadata ends in 2021 and starts in 1958. Qualify one complete variable first; never splice versions. |
| 4 | [CRU-TS v4.10](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/): ten monthly variables, global land excluding Antarctica, 1901–2025 | Gzipped NetCDF/ASCII → Zarr/Icechunk | A current station-based climate series with no matching v4.10 native copy found. Include station-support information and follow this edition's ODbL terms. |
| 5 | [RiverATLAS v1.0](https://www.hydrosheds.org/hydroatlas): full global reach attributes | FileGDB/Shapefile → GeoParquet | Adds environmental attributes to the river network; a different scientific product from FFR. Source/schema and attribute-license qualification precedes a new build. |
| 6 | [HydroLAKES v1.0](https://www.hydrosheds.org/products/hydrolakes): complete original lake polygon inventory | FileGDB/Shapefile → GeoParquet | Prepared locally. Retain as the original base product, but it shares geometry with LakeATLAS; these are not independent shoreline surveys. |
| 7 | [GRWL summary V01.02](https://zenodo.org/records/18624542): complete simplified global centerline summary | Shapefile → GeoParquet + separate PMTiles display | Prepared locally: 42,077 records. This is the summary product, not the raw vectors or water masks. Exact filename/checksum resolve the producer record's stale V01.01 label. |
| 8 | [Lebreton et al. 2017 river-plastic inputs, Figshare v6](https://doi.org/10.6084/m9.figshare.4725541.v6) | Shapefile/CSV → GeoParquet + separate PMTiles display | Prepared locally: 40,760 modeled input points. A reproducible historical 2010-baseline product; it is not the later Meijer estimate or a current pollution survey. Small original size makes the access benefit smaller than the large archives above. |
| 9 | [Global Dam Watch consensus v1](https://www.globaldamwatch.org/database): barrier points and reservoir polygons | FileGDB/Shapefile → two GeoParquet layers | **Conditional:** better current target than superseded GRanD/GOODD; qualify exact downloadable release and transformed redistribution terms before building. The separate evolving intelligence platform is not the same pinned release. |
| 10 | [SWOT Prior Lake Database v2.03](https://hydroweb.next.theia-land.fr/news): scientific lake reference database | SQLite for preceding release; verify v2.03 assets → GeoParquet + relational tables | **Conditional:** producer announced v2.03 on 28 October 2026. Pin its assets/schema and retain identifiers/relationships before selecting a conversion. Do not carry forward the old v2.02 label. |

The immediate recommendation is to retain the five prepared local releases (ranks 1, 2, 6, 7, 8). **TerraClimate v1.1 is the next new build candidate, followed by CRU-TS v4.10.** Reader/source qualification still precedes either build. RiverATLAS is the strongest additional vector candidate from this review. Optional PMTiles are display derivatives, not substitutes for complete analytical records. No new download-size claim is made here.

## Important existing-host distinctions

- **TerraClimate:** [Planetary Computer's live collection](https://planetarycomputer.microsoft.com/api/stac/v1/collections/terraclimate) declares Zarr and 1958-01 through 2021-12 (768 monthly slices). Its current arrays were not read; an unsigned `.zmetadata` request returned HTTP 409, not proof of unavailability. The producer explicitly warns against mixing v1.0 with v1.1. The proposed release must cover the reprocessed v1.1 baseline, not append newer values to the older store.
- **CRU-TS:** [World Bank's AWS collection documentation](https://worldbank.github.io/climateknowledgeportal/docs/collections/cru-x0.5.html) describes four selected variables from v4.07 through 2022. That is not the ten-variable v4.10 scope. This check does not certify every object in the World Bank bucket.
- **HydroLAKES / LakeATLAS / GRWL:** HydroMT lists local FGB/GPKG products, but those documented `p:/wflow_global/...` paths do not establish a public range-readable host. Its HydroLAKES FGB is a natural-lakes subset. The [GDW page](https://www.globaldamwatch.org/database) mentions HydroLAKES v1.1 integration, whereas the [standalone producer download](https://www.hydrosheds.org/products/hydrolakes) still links v10 archives. A separate public v1.1 replacement was not established; do not relabel our pinned v1.0 bytes.
- **RiverATLAS:** no matching complete native host surfaced. A related AquaScope [archive](https://rachidouedraogo.com/aquascope/archive-layout/) offers simplified BasinATLAS level-12 FGB and derived tables; it is a different scope from full RiverATLAS and from all BasinATLAS levels.
- **Global Dam Watch / GROD:** GDW incorporates only part of GROD. [GROD v1.1](https://zenodo.org/records/5793918) remains a distinct reserve candidate. The primary Zenodo API confirms CC-BY-4.0 and a 2,536,955-byte CSV; its already convenient small source gives less additional access benefit than the larger archives. Do not claim GDW replaces all GROD records.

## Existing access and deferred candidates

- **Generic MERRA-2 surface weather:** [NASA POWER already distributes selected meteorology in Zarr](https://power.larc.nasa.gov/docs/tutorials/service-data-request/aws/). This is not the complete original MERRA-2 archive. A proposal must identify missing original variables/coverage before it returns to the queue. ERA5 and ERA5-Land also have existing native distributions.
- **CHIRPS v3:** [WFP daily RNL COGs](https://source.coop/wfp/chirps-rnl-daily) and [Dynamical final Zarr/Icechunk](https://dynamical.org/catalog/ucsb-chc-chirps-analysis-final/) already address useful global coverage. Prefer qualifying/referencing those releases.
- **SoilGrids means:** [Source Cooperative means](https://source.coop/chill/soilgrids) already exist. **Quantiles remain a reserve candidate with unresolved layout/access benefit.** [soilDB documentation](https://ncss-tech.github.io/soilDB/reference/fetchSoilGrids.html) calls its quantile-access path COG subsetting, but our [bounded header probe](soilgrids-quantile-header.json) found a striped first IFD, without TIFF tile tags, in one producer SOC 0–5 cm Q0.05 tile; HTTP Range returned 206. [Producer documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html) describes the 250 m VRT/OVR/tile layout and specifically calls the coarser mean aggregates COGs. We therefore do not classify all 250 m quantiles as existing COGs, or all as needing conversion. Test actual regional access across depths/statistics and other exact hosts before selecting a mirror. This also corrects the earlier exploratory suggestion in this review that documentation alone settled their native status.
- **GLiM:** [global sharded GeoParquet exists on Hugging Face](https://huggingface.co/datasets/mgalib/GLIM_GLHYMPS). Its card has conflicting top-level versus component license labels and restrictive GLiM terms; this is an existing-host lead, not an endorsement of redistribution rights or correctness.
- **EarthStat 175 crops:** [producer documentation](https://geodata.ucdavis.edu/geodata/crops/monfreda/METADATA_HarvestedAreaYield175Crops_June2018.pdf) explicitly requires permission for re-release. Do not start a public mirror without it.
- **HYDE / HWSD:** current exact editions and rights need qualification. HYDE 3.2 is not latest; newer [HYDE 3.5 source](https://doi.org/10.24416/UU01-F45D44) primary metadata could not be verified in this review. [HWSD's producer](https://www.fao.org/land-water/resources/tools/databases/hwsd/en) identifies v2.01, not merely v2.0. Neither is ready for this queue.
- **Hugonnet glacier change:** retain as a reserve pending actual TIFF layout and exact source-license qualification. Generic TIFF descriptions do not establish missing COG access. CEDA's license statement relates to the original DOI but its own small IPCC derivative is not the elevation raster release.
- **JRC Occurrence, CHELSA, RESOLVE ecoregions, WaterNet and OpenLandMap:** existing native-access leads were already identified in the earlier reviews. A second mirror needs a separately justified benefit.

## What was checked and what remains unproven

This review combined producer pages/APIs, targeted exact-name/DOI/format searches across Source Cooperative, Planetary Computer, AWS and other indexed hosts, and an offline scan of the **747-record Source Cooperative metadata snapshot retrieved 30 October 2026**. The scan checks all serialized metadata with the expressions in [check_source_snapshot.py](check_source_snapshot.py). [Results](source-coop-snapshot-matches.json) preserve every matching ID, title, term and catalog timestamp. WaterNet is the only HydroLAKES name match and is not equivalent. HYDE matches refer to downstream biodiversity/human-footprint products, not HYDE itself.

A live refresh of the Source Cooperative JSONL returned HTTP 403. Crucially, the saved snapshot has **no `chill/soilgrids` entry despite that known store**. It is demonstrably incomplete for this purpose. Zero catalog matches are supporting search evidence only. No full object inventories, exact equivalence comparisons, decoded pixel/array reads or global license/completeness audit were performed. A bounded SoilGrids TIFF header was inspected; it is not a full dataset validation. Reviewed documents remain claims by their authors until release qualification checks their bytes.

Reproduce the offline scan using the existing ignored source snapshot (or the identical bytes obtained independently):

```sh
python3 research/native-publication-gaps-20261031/check_source_snapshot.py \
  /path/to/source-coop-catalog.jsonl
```

The checker refuses a different SHA-256, byte size or record count. For a newer capture, create a new dated audit with its own input identity; do not overwrite this result. Criteria were committed before running this expanded snapshot scan. Exploratory web research had already occurred, as the criteria explicitly record.

[Validation](validation.json) records the successful deterministic replay, the modified-input refusal, relevant repository checks, and the initial mixed-schema failure. No bulk datasets were acquired, converted, uploaded or submitted to Portolan in this review. Catalog observations and recommendations do not change the fact that five releases are prepared locally and zero are published.

Repeat the bounded header check (one public metadata-range GET):

```sh
python3 research/native-publication-gaps-20261031/probe_tiff_header.py \
  https://files.isric.org/soilgrids/latest/data/soc/soc_0-5cm_Q0.05/tileSG-018-027/tileSG-018-027_2-4.tif
```
