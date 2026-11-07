# Alternatives to the five publication candidates — 2026-10-30

Several alternatives deserve consideration before further conversion work. LakeATLAS is a useful enrichment of our lake release; SWOT PLD offers a different inventory with much better small-lake coverage. WaterNet, CHELSA and OPERA already have cloud-native distributions. Their availability can save publication work when they meet the intended need.

These are scientific product choices, not interchangeable file sources. Our [prior shortlist](../chirps-priorities-20261030/README.md) remains a dated record. This review expands the candidate pool without changing any dataset record or starting a conversion. Detailed sources, distinctions and unresolved checks are in [alternatives.json](alternatives.json).

| Existing candidate | Strong alternatives | What changes for our plan |
| --- | --- | --- |
| HydroLAKES v1 | **[LakeATLAS](https://www.hydrosheds.org/hydroatlas)** enriches the same lake features. **[SWOT PLD](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2023WR036896)** targets smaller lakes and mission-linked observations. | Keep the validated HydroLAKES baseline; qualify LakeATLAS for richer attributes and PLD when inventory coverage is the priority. |
| Free-Flowing Rivers | **[WaterNet](https://source.coop/fika/waternet)** already provides GeoParquet, PMTiles and COGs. **[RiverATLAS](https://www.hydrosheds.org/hydroatlas)** adds environmental characteristics to a global river network. | Use these for network geometry/attributes. Keep FFR when its free-flowing/connectivity assessment is specifically needed. |
| JRC Occurrence v1.5 | **[OPERA DSWx-HLS](https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-HLS_V1)** provides frequent 30 m water classifications as COGs. **[Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)** provides 10 m land-cover probabilities, including water. | Prefer them for recent water mapping when appropriate. JRC remains useful for the 1984–2024 occurrence statistic. |
| TerraClimate v1.1 | **[CHELSA-monthly v2.1](https://www.chelsa-climate.org/datasets/chelsa_monthly)** supplies kilometer-scale climate COGs. **[ERA5-Land ARCO](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=analysis_ready_data)** offers selected variables as Zarr. | Reuse these if their period and variables meet the requirement. TerraClimate retains value for its particular monthly water-balance product and longer record than current CHELSA-monthly. |
| Hugonnet glacier elevation change | **[GlaMBIE](https://wgms.ch/data_glambie/)** supplies newer global/regional annual mass-change estimates. **[ITS_LIVE](https://its-live.jpl.nasa.gov/)** offers cloud-accessible ice velocity and separate ice-sheet elevation products. | Use GlaMBIE for aggregate statistics; keep Hugonnet for detailed global elevation-change maps. Global velocity is a different measured quantity. |

## The strongest changes to consider

**LakeATLAS should join the publication shortlist.** The [producer comparison](https://www.hydrosheds.org/faq) explains that it contains the corresponding HydroLAKES features with environmental attributes. Its ZIP is only about 1.43 GB in FileGDB or 1.5 GB in Shapefile, according to the producer. We could retain the verified HydroLAKES release and publish a separately identified enrichment after checking IDs and geometry. Being built on the same boundaries means LakeATLAS does not solve every dated-shoreline issue.

**SWOT PLD deserves a separate inventory evaluation.** The 2025 paper describes roughly 5.9 million polygons targeting lakes at least 1 ha, versus HydroLAKES' 10 ha target. PLD seeks representative stable-season extents; its count is not a fourfold improvement in lake area or a proof that every polygon is better. The [producer catalog](https://hydroweb.next.theia-land.fr/catalog/details/SWOT_PRIOR_LAKE_DATABASE) currently identifies the scientific collection as release 2.02 Sci, SQLite, ETALAB 2.0. Confirm its actual downloadable version and size; paper-era counts must not be treated as validation of that current release. The catalog was readable through indexed primary text after direct browser access timed out.

**WaterNet is a useful immediate registry candidate.** Its public Source Cooperative publication already supplies the formats we planned to build, with downstream/upstream network fields. The README also records model and vectorization limitations. It does not supply FFR's assessment of pressure on longitudinal, lateral, vertical and temporal connectivity. A new river geometry cannot update historical dam impacts merely by being newer. These should remain separate product identities.

**CHELSA could satisfy some climate needs without a new conversion.** Its current monthly catalog lists 1979–2021 and COG delivery, with CC0 terms. That period is shorter than the TerraClimate v1.1 base archive we scoped. ERA5-Land covers 1950 onward at about 9 km native resolution, distributed on a 0.1° grid, with an ARCO subset. Neither has the same grid and exact water-balance definitions as TerraClimate. TerraClimate v1.1 identifies **ERA5**, not ERA5-Land, as an input; the two reanalyses must not be conflated.

**GlaMBIE is a small, useful companion dataset.** WGMS lists 2.6 MB of zipped CSV covering 2000–2023, with annual regional solutions and global aggregates. Parquet could be sufficient; attaching region polygons would be an explicit additional join, not an inherent property of those tables. This is attractive for global trend reporting but cannot replace a 100 m map of elevation change. ITS_LIVE's global Zarr cubes describe velocity; its separate elevation products have different geographic scope and scale.

## Access and verification limits

Cloud-native storage does not always mean anonymous access. OPERA's data endpoint uses Earthdata Login, and CDS requires an API key for ERA5-Land ARCO. These credentials are an access consideration for the registry, not evidence that the products need format conversion. WaterNet is already on Source Cooperative. CHELSA's format is stated by the producer; no object-level COG checks were performed here.

The current OPERA catalog lists a 2016-present time span while its description identifies validated observations beginning April 2023. This review does not establish complete pre-2023 coverage. Dynamic World's image probabilities require choices about masking, thresholds and aggregation; they are not a ready replacement for JRC's historical occurrence layer.

The review used primary producer/distributor pages and research papers, with two read-only research tasks followed by parent verification of material claims. Searches that did not surface exact Source Cooperative entries do not establish absence. No new citation ranking, numerical accuracy comparison, geometry match, raster comparison or full inventory was run. No dataset files were downloaded, and no cloud jobs, private storage, publication or registry writes were performed.

Files:

- `scope.json`: comparison axes and limits, committed before synthesis.
- `baseline.json`: hash of the frozen previous shortlist.
- `alternatives.json`: five baseline families and ten alternatives, each with sources and remaining checks.
- `validation.json`: document/JSON consistency checks and baseline integrity. This is not a scientific-validation result.
