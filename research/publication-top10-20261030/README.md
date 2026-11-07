# Expanded publication shortlist — completed 2026-10-31

Three candidates stand out for the next release work: **HydroLAKES, WWF Free-Flowing Rivers and LakeATLAS**. Expand the review list to ten while keeping the build queue small. A useful registry entry can reference an existing maintained publication; publication by Folia needs an identifiable benefit beyond another copy.

This extends the [five-candidate review](../chirps-priorities-20261030/README.md), [alternative products](../dataset-alternatives-20261030/README.md) and [SoilGrids review](../soilgrids-options-20261030/README.md). Ranking reflects useful additional access, readiness, effort and maintenance. It is not a new citation top ten. Criteria were committed before synthesis in [criteria.json](criteria.json); detailed decisions, sources, scoped sizes and remaining checks are in [priorities.json](priorities.json).

| Priority | Candidate | Recommended work | Why |
| --- | --- | --- | --- |
| 1 | [HydroLAKES v1](https://www.hydrosheds.org/products/hydrolakes) | **Package existing conversion:** GeoParquet; optional PMTiles | Complete 1,427,688-feature conversion already has substantial validation. Finish the reusable public package. |
| 2 | [WWF Free-Flowing Rivers](https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801) | **Convert:** GeoParquet; optional PMTiles | Released connectivity assessment adds information that generic river geometry does not supply. |
| 3 | [LakeATLAS](https://www.hydrosheds.org/hydroatlas) | **Convert:** GeoParquet; optional PMTiles | Environmental enrichment of HydroLAKES; share geometry checks while retaining separate product identity. |
| 4 | [SoilGrids](https://source.coop/chill/soilgrids) | **Qualify a gap:** reuse means; scope SOC quantiles | Existing Icechunk/Zarr store omits Q05/Q50/Q95 and uncertainty. Begin with one property only if exact hosting and source checks support it. |
| 5 | [TerraClimate v1.1](https://www.climatologylab.org/terraclimate.html) | **Qualify a gap:** one-variable Zarr pilot | Test whether newer-version coverage and access requirements remain unmet by existing Zarr hosting. |
| 6 | [SWOT PLD](https://hydroweb.next.theia-land.fr/catalog/details/SWOT_PRIOR_LAKE_DATABASE) | **Qualify a gap:** GeoParquet | Distinct smaller-lake inventory and SWOT links; current downloadable release and size still need confirmation. |
| 7 | [JRC v1.5 Occurrence](https://global-surface-water.appspot.com/download) | **Qualify access:** COG/STAC or existing tiles | Preserve the long-term statistic; check original layout before deciding whether conversion adds value. |
| 8 | [CHIRPS v3 daily RNL](https://source.coop/wfp/chirps-rnl-daily) | **Reuse:** qualify WFP COGs for Portolan | Already published; resolve the documented metadata discrepancies and validate the intended scope. |
| 9 | [OpenLandMap-soildb](https://github.com/openlandmap/soildb) | **Reuse:** qualify producer COGs for Portolan | Existing cloud-native distribution; keep property, depth, period and uncertainty definitions explicit. |
| 10 | [HWSD v2.01](https://www.fao.org/land-water/resources/tools/databases/hwsd/en) | **Lower-priority qualification:** COG + Parquet | Useful mapping-unit/attribute joins if there is a concrete need. Preserve component proportions and one-to-many attributes. |

## What changed the recommendation

**TerraClimate already has a Zarr distribution.** The live [Planetary Computer collection](https://planetarycomputer.microsoft.com/api/stac/v1/collections/terraclimate) declares January 1958–December 2021 and links a Zarr store. The earlier scoped producer archive is v1.1, 1950–2025. Therefore any new release should establish a version/coverage or measured access gap. The current store's actual source version and arrays were not opened, and a `.zattrs` request through the web tool failed. Catalog metadata alone does not prove byte-level coverage. The new evidence narrows the earlier conversion recommendation; historical reviews remain unchanged.

**HydroLAKES and LakeATLAS share geometry.** LakeATLAS enriches the existing inventory. Preserve both scientific identities if published, but reuse acquisition/geometry verification and do not count them as independent shoreline surveys. We already have a validated HydroLAKES output, which is a reason to finish packaging it, not a reason to rebuild it.

**Soils have one particularly interesting gap.** Reuse SoilGrids means and OpenLandMap COGs after reader checks. SoilGrids quantiles are explicitly missing from the reviewed store; exact versions and other hosts still need investigation. HWSD is lower priority without demand for its mapping-unit attributes. Africa-only iSDAsoil is a useful regional reuse option.

## Concrete next work

Finish the HydroLAKES local release package, then prepare the released FFR network, then add LakeATLAS enrichment. All retain original producer attribution and source identity, full feature/attribute checks, and separately identified display derivatives. Run a new exact-hosting check before committing to each new conversion. These are recommendations; this review did not start builds or authorize uploads.

HydroLAKES is CC-BY-4.0, and its [technical document](https://data.hydrosheds.org/file/technical-documentation/HydroLAKES_TechDoc_v10.pdf) also asks for written permission when redistributing the entire database in its original format. Preserve the wording and assess the intended transformed release specifically; do not treat it as a blanket ban on derivatives. FFR's live author metadata reconfirmed CC-BY-4.0 and a 954,710,486-byte geodatabase ZIP. LakeATLAS's producer declares CC-BY-4.0 and identifies its attribute provenance/documentation.

Defer Hugonnet public publication pending exact data terms. GlaMBIE's existing small CSV package gives less incremental format value without a specific join/query use. WaterNet already provides useful GeoParquet/PMTiles/COG assets and remains an additional registry reference. None of these judgments establishes scientific inferiority.

## Evidence and limits

[Input hashes](input-manifest.json) pin the preceding reports. [Evidence](evidence/) includes two bounded public JSON requests, response hashes and projected metadata, plus reviewed primary-page outcomes. [Validation](validation.json) covers document/JSON consistency, rank/action counts, source links, prior-input integrity and the new metadata facts. It does not test data correctness, scientific accuracy, performance, reader compatibility or complete availability. No data bodies, conversions, GEE/cloud jobs, registry submissions or uploads were performed.
