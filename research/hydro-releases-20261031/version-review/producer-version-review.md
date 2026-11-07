# Producer version and additional-product review

Checked 2026-10-31 against producer pages, publisher metadata, and the source object listing. “Latest” below means the newest public version explicitly presented by the producer/source host on the check date; it does not claim that the underlying observations are contemporaneous.

## Requested releases

| Dataset | Current public version | Release/publication evidence | Data vintage and caveat | Producer terms / source |
|---|---|---|---|---|
| HydroLAKES | v1 (producer page identifies version 1; no newer version is offered there) | Technical documentation v1.0, Dec. 2016; page cites Messager et al. 2016 | Static lake polygons assembled from several auxiliary near-global and regional sources. Acquisition years vary by region/source; the product is not a single-date inventory. Do not report 2016 as the observation year. | CC BY 4.0. [Official HydroLAKES page](https://www.hydrosheds.org/products/hydrolakes); [v1.0 technical documentation](https://data.hydrosheds.org/file/technical-documentation/HydroLAKES_TechDoc_v10.pdf). |
| LakeATLAS | v1.0 (part of HydroATLAS v1; producer describes it as the current LakeATLAS product) | LakeATLAS paper, 2022; product is distributed via HydroSHEDS | Attribute vintage varies by source column. Example vintage explicitly called out in HydroSHEDS FAQ: administrative country-area data use GADM 2.0 circa 2012. The v1 label is product/version, not a common observation year. | Collective database: CC BY 4.0. Individual attribute columns: CC BY 4.0 or ODbL 1.0 as specified by the technical documentation and catalog; retain field-level license/citation notices. [HydroATLAS product page](https://www.hydrosheds.org/hydroatlas); [LakeATLAS paper](https://doi.org/10.1038/s41597-022-01425-z). |
| Free-flowing Rivers | Figshare v1; version history contains exactly version 1 | Figshare record posted 2019-05-07; underlying paper published 2019-05-09 | Static connectivity assessment with data around 2017 (HydroRIVERS network plus pressure inputs); not a live/current dam or river status layer. | CC BY 4.0. [Figshare record](https://doi.org/10.6084/m9.figshare.7688801); [Figshare versions API](https://api.figshare.com/v2/articles/7688801/versions) returned `[{'version': 1, 'url': 'https://api.figshare.com/v2/articles/7688801/versions/1'}]`; [paper](https://www.nature.com/articles/s41586-019-1111-9). |
| JRC Global Surface Water Occurrence | v1.5, aggregated Occurrence | JRC download page last updated 2026-10-15; CloudFerro tile objects last modified 2026-07-01 | Aggregated occurrence spans 1984–2024. JRC documents a processing boundary: Landsat Collection 1 for 1984–2021 and Collection 2 for 2022–2024; the full-period aggregate merges the collections. The v1.5 release label is not a one-year observation date. | Copernicus Programme; free of charge without restriction of use per JRC access page; attribution “Source: EC JRC/Google” and required citation. [JRC data access](https://global-surface-water.appspot.com/download); [CloudFerro source listing](https://s3.waw4-1.cloudferro.com/swift/v1/global-surface-water/?format=json&prefix=download2024/Aggregated/&limit=10000). |

The current CloudFerro listing response re-fetched on 2026-10-31 was 200 OK, 690,514 bytes, SHA-256 `338037170377b21953074a9163d68498048764532642ef0f44ee82c1b72e7410`; it lists 504 Occurrence TIFFs totaling 14,453,956,859 bytes. The listing response's `Last-Modified` is 2026-07-01, as are the per-object timestamps. This is source metadata freshness, not a later data vintage.

## HydroSHEDS products worth considering

| Product | Current producer statement | Recommendation for another global publication |
|---|---|---|
| HydroSHEDS core | The global core download page calls v1.1 the latest v1 release. HydroSHEDS v2 core is a real new base release at 1 arc-second, but its public coverage is currently limited to the Americas; includes DIR, ACC, ACA, RIV, and beta BAS. | Do not claim global coverage or use it as a drop-in global replacement yet. It is a useful distinct regional release if the Americas are in scope. [v1 core page](https://www.hydrosheds.org/hydrosheds-core-downloads); [v2 product page](https://www.hydrosheds.org/products/hydrosheds-v2). |
| HydroRIVERS / HydroBASINS | HydroRIVERS is explicitly version 1. HydroSHEDS v2's RIV and beta BAS are currently Americas-only; the producer says further HydroATLAS/HydroRIVERS attribute releases are future work. | No current global v2 derived-network/basin release identified. Preserve v1 lineage; do not relabel the legacy global vectors as v2. [HydroRIVERS page](https://www.hydrosheds.org/products/hydrorivers); [v2 page](https://www.hydrosheds.org/products/hydrosheds-v2). |
| RiverATLAS / BasinATLAS | Components of global HydroATLAS v1, alongside LakeATLAS. | **High-value next candidates** for attribute-rich river/basin analysis. They are separate global products and separate downloadable archives; converting LakeATLAS does not include either. First qualify exact existing cloud-native counterparts and their version, geometry fidelity, attributes and license notices. [HydroATLAS page](https://www.hydrosheds.org/hydroatlas). |
| GLWD v2 | Global, 33 inland-water/wetland classes, 15 arc-second (~500 m at equator), contemporary maximum non-overlapping extents based on 1990–2020; producer calls it v2 and makes it available via Figshare. CC BY 4.0. | **Best additional global candidate.** Adds a distinct, newer, thematic wetland/waterbody raster and fractional class layers not represented by lake polygons or river connectivity. Keep its 1990–2020 product vintage explicit. [Official GLWD page](https://www.hydrosheds.org/products/glwd); [2025 paper](https://doi.org/10.5194/essd-17-2277-2025). |
| HydroWASTE v1 | Global 58,502 wastewater treatment plant records; attributes include people served, effluent flow and treatment level; producer page links a 2.3 MB release and states CC BY 4.0. Article is 2022. | Valid but narrower optional publication if wastewater pressure / infrastructure is a target. It is a distinct vector dataset, not a replacement for hydrology layers. [Official page](https://www.hydrosheds.org/products/hydrowaste); [paper](https://doi.org/10.5194/essd-14-559-2022). |
| LakeTEMP v1 | Global lake surface-water-temperature observations and estimated ice phenology, for about 1.4 million HydroLAKES lakes; image caption describes Julian-day averages over 2013–2021; 1.27 GB; CC BY 4.0. | Distinct and useful for lake thermal/ecosystem work, but a specialized, relatively large additional release. Recommend only if temperature/ice phenology is relevant. [Official page](https://www.hydrosheds.org/products/laketemp); [2024 paper](https://doi.org/10.1016/j.rse.2024.114164). |
| HydroFALLS v1 | Producer page describes >4,000 waterfall locations, but its technical documentation, license, references, and download all still say “Coming in 2024.” | Do not prepare from this page alone: usable source files and terms are not posted on the cited producer page. Recheck if producer publishes them. [Official page](https://www.hydrosheds.org/products/hydrofalls). |

HydroSHEDS v2 is a new base-data generation, not a global update to HydroLAKES, HydroBASINS, or HydroRIVERS. The source product page explicitly says additional regions and future HydroATLAS/HydroRIVERS attributes are not yet released. Existing hosts remain the producer's HydroSHEDS pages and their linked download repositories; the FFR DOI is a Figshare record. No separate mirrors are needed to preserve source identity.

## Existing work to coordinate with

[boettiger-lab/data-workflows issue 442](https://github.com/boettiger-lab/data-workflows/issues/442), opened July 17, 2026 and still open when checked, proposes ingesting HydroRIVERS, HydroLAKES, RiverATLAS, BasinATLAS and FFR into its HydroSHEDS-family bucket. The issue has no assigned implementer or linked pull request. This is relevant planned prior art; the issue alone does not verify that the assets are hosted. Its policy statement about older HydroSHEDS v1c standalone redistribution is not a substitute for each product's current producer license and technical documentation.

[Aquascope's archive layout](https://rachidouedraogo.com/aquascope/archive-layout/) also describes BasinATLAS level-12 attribute/topology Parquet, simplified basin geometry and PMTiles. This is a candidate for reuse where its scope fits, not evidence of a verified, full-resolution, all-level BasinATLAS mirror. Exact asset/version qualification remains outstanding.

Recommended next review order: **BasinATLAS, RiverATLAS, GLWD v2, HydroWASTE**. The first two reuse the same stable identifiers across the hydrography family; GLWD adds wetlands rather than another representation of lake shorelines; HydroWASTE is a small global point product. These are recommendations for source/hosting qualification, not authorization to download or publish another four products.

## Previously prepared products

The same 2026-10-31 metadata recheck confirms the river-plastic product is still
Figshare **v6**, including the same ZIP file ID 7714864, 5,764,810 bytes and producer
MD5. This is the current release of the **Lebreton 2017 model**, not a claim that
it is the newest river-plastic model (the Meijer 2021 dataset is different).
[Producer record](https://doi.org/10.6084/m9.figshare.4725541.v6).

GRWL's `versions/latest` endpoint resolves to **Zenodo 18624542**. The selected
summary archive is still **GRWL_summaryStats_V01.02.zip**, 43,282,861 bytes, with
the same producer MD5. The record's general version label remains V01.01; exact
filename and checksum identify our V01.02 summary. The Community Catalog's
V01.01 GEE asset is older and has not been used as an equivalence oracle.
[Current record](https://zenodo.org/records/18624542).

Evidence: `current-source-metadata.json` and `grwl-latest.json`. GRIP4 remains a
deliberately deferred historical 2018 conversion, not a current-road publication.
Its latest-record check is in the prior [GRIP4 chronology review](../../local-build-two-20261030/grip-version-date-review.json); no new GRIP4 work was started.
