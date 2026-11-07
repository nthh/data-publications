# SoilGrids: existing coverage and alternatives — 2026-10-30

Prioritize qualifying the existing SoilGrids publication for Portolan. Its missing uncertainty layers are a more useful potential publication scope than another copy of the means. The newer OpenLandMap release deserves comparison, with matching properties, depths, dates and geographic coverage.

This extends the [previous alternatives review](../dataset-alternatives-20261030/README.md). It does not change a dataset record or begin a conversion. The comparison criteria were committed in [scope.json](scope.json) before synthesis; [review.json](review.json) contains the structured findings and primary sources.

## Existing SoilGrids publication

[Colin Hill's Source Cooperative product](https://source.coop/chill/soilgrids) documents 250 m SoilGrids v2 means in an Icechunk repository with sharded Zarr v3 arrays. It includes ten properties across six intervals to 200 cm and carbon stocks for 0–30 cm. The publisher reports about 177 GB native data plus 90 GB of display overviews.

The store explicitly excludes Q05, Q50, Q95, relative uncertainty and WRB class probabilities. Its display overviews do not supply uncertainty. Use an Icechunk-aware reader, check the native projection and pin a snapshot or immutable tag; the documented tag has not been opened in this review.

The product page was readable. A separate direct request for its README returned HTTP 403, retained in [the access receipt](evidence/soilgrids-sourcecoop-readme.json). No store read or independent pixel comparison ran. This failed metadata request does not establish that the full store is inaccessible.

## Alternatives

| Product | Coverage and depth | Distribution | Assessment for our plan |
| --- | --- | --- | --- |
| **[OpenLandMap-soildb, 2026 paper](https://essd.copernicus.org/articles/18/989/2026/)** | Global prediction domain, excluding deserts/permanent ice per producer; 30 m means; 0–30, 30–60, 60–100 cm | Producer COGs; numeric uncertainty at 120 m | Strongest new global comparison candidate. Different variable/depth/time coverage prevents automatic substitution. |
| **[HWSD v2.01](https://www.fao.org/land-water/resources/tools/databases/hwsd/en)** | Global, about 1 km; seven intervals to 200 cm | Raster mapping units linked to an MDB attribute database | Potential COG plus Parquet publication. Preserve component proportions and one-to-many attributes. Current artifacts and redistribution terms still need qualification. |
| **[iSDAsoil](https://www.isda-africa.com/isdasoil/isdasoil-on-aws/)** | Africa, 30 m; 0–20 and 20–50 cm; 20+ properties | Public AWS COGs with STAC | Useful regional registry candidate. It does not provide worldwide coverage. |

The new OpenLandMap release differs from the legacy 250 m GEE collections. Carbon and pH include period-specific predictions around 2000–2022; not every property is dynamic. Its P16/P84 intervals describe nominal 68% coverage, unlike SoilGrids' P05/P95 nominal 90% intervals. Finer grid spacing alone does not establish better predictive accuracy.

The [producer index](https://raw.githubusercontent.com/openlandmap/soildb/main/tables/OpenLandMap_soildb_COGS.csv) lists 1,082 distinct URLs: 57 numeric means at 30 m, 207 numeric products at 120 m, and 818 soil-type products at 30 m. The [saved projection](evidence/openlandmap-index.json) records counts, sample URLs and the received CSV's SHA-256. These are index claims; no linked raster was checked. Zenodo's published subset is narrower than this S3 inventory.

## Recommended sequence

1. Qualify SoilGrids access through an Icechunk-aware client and the intended Folia/Portolan reader. Check units, nulls, CRS, source versions and representative native pixels against ISRIC. Register a pinned existing publication if it meets the requirement.
2. Assess a separate release of SoilGrids quantiles for one useful property, such as soil organic carbon. Preserve all native depth intervals and distinguish quantiles from means and derived uncertainty. Confirm other hosting before starting a new mirror.
3. Qualify OpenLandMap's current COG endpoints for registry reuse. For a scientific comparison, match property, units, depth support, dates, masks and spatial support; use independent observations and fixed geographic splits, assessing prediction error and interval coverage.

[ISRIC's layer documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html) also lists water-retention properties absent from the existing store's variable list. Their exact source files/versions were not located here, so they remain a conditional lead. [WRB class probabilities](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_03.html) reuse 2017 predictions and must retain a separate product identity.

## Verification scope

The review used primary documentation, a read-only alternative-product review, and a small public metadata index. JSON parsing, source references, local links, inventory arithmetic and retained failure evidence were checked; results are in [validation.json](validation.json). No independent scientific accuracy test, raster validation, download-size measurement or complete hosting inventory ran. No data bodies, private storage or GEE jobs were accessed, and no registry or remote publication was changed.
