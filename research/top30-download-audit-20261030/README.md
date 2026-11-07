# Top 30: catalog membership, download size and formats

Research date: 2026-10-30. Ranking is the frozen combined official/community paper-citation ranking, including deprecated entries. Counts do not establish conversion priority.

**22 official only · 4 community only · 4 in both catalogs.** Membership follows the reviewed citation groups. A shared paper can describe different products or versions; it does not prove identical assets.

Download size always applies to the stated scope. Static releases are sized globally where possible; time series identify product, variables and period. Approximate figures use producer totals, rounded listing sums or average-file-size estimates. Exact bytes are distinguished in the CSV. Publisher MB units are retained in detailed evidence; rounded GB summaries are planning approximations. Unknown is not zero.

Desired formats are recommendations for a future publication: COG for spatial raster maps, Zarr for time series and multidimensional grids, GeoParquet for vectors, and optional PMTiles for display. Existing cloud-native distributions may only need a registry reference. Converted output size requires a measured pilot.

| # | Dataset | Catalog | Download size / selected scope | Source format | Desired output |
|---:|---|---|---|---|---|
| 1 | [ERA5](#dataset-1) | Official | ≈5 PB, publisher archive-scale figure — Whole ERA5; selected transfer bytes vary | GRIB / NetCDF; Zarr mirrors | Zarr; reference existing store |
| 2 | [NCEP/NCAR Reanalysis](#dataset-2) | Official | 7.00 MB — 2024 global daily surface temperature only | NetCDF | Zarr |
| 3 | [WorldClim v1](#dataset-3) | Official | 1.86 GB — Global 30″ BIO: all 19 variables | ESRI grids in ZIP; BIL alternatives | COG |
| 4 | [Hansen Global Forest Change](#dataset-4) | Official | 83.91 GB — Global v1.13 core maps; imagery excluded | GeoTIFF | COG |
| 5 | [MODIS vegetation indices](#dataset-5) | Official | ≈2,191 MB — MOD13C1.061, global 0.05°, all 23 composites in 2024 | HDF-EOS2 | Zarr; COG maps optional |
| 6 | [MERRA-2](#dataset-6) | Both | ≈146,400 MB (estimate) — All SLV fields, hourly, global 2024 | NetCDF | Zarr |
| 7 | [SRTM elevation](#dataset-7) | Official | ≈99,883 MB — Entire SRTMGL1 v3 collection | HGT in ZIP | COG |
| 8 | [TRMM TMPA](#dataset-8) | Official | ≈58.8 MB (estimate) — 12 global monthly 3B43 files, 2019 | HDF4 | Zarr |
| 9 | [CHIRPS](#dataset-9) | Official | 1.36 GB — Global daily 2024; NOAA mirror | NetCDF; GeoTIFF alternatives | Zarr; COG maps optional |
| 10 | [GLDAS](#dataset-10) | Official | ≈55,632 MB (estimate) — Noah 2.1 global 3-hourly 2020, all fields | NetCDF | Zarr |
| 11 | [ERA5-Land](#dataset-11) | Official | Unknown; request-dependent — Raw example: 227 GB per hourly variable/year | GRIB / NetCDF; ARCO Zarr | Zarr; reference existing subset |
| 12 | [JRC Global Surface Water](#dataset-12) | Official | 15.97 GB — Global v1.4 Occurrence only, 504 tiles | GeoTIFF | COG; Zarr for histories |
| 13 | [CFSR](#dataset-13) | Official | 55.81 TB — NCAR six-hourly archive, 1979–2010 | GRIB2 | Zarr |
| 14 | [River plastic inputs](#dataset-14) | Community | 5.76 MB — Complete Figshare v6 source ZIP | Shapefile in ZIP | GeoParquet + PMTiles |
| 15 | [TerraClimate](#dataset-15) | Both | ≈115,507 Mbytes — v1.1 base 1950–2025, 14 variables; ≈116–121 GB | NetCDF4 | Zarr |
| 16 | [Global Mangrove Forests 2000](#dataset-16) | Official | ≈59.39 MB — All 111 global GeoTIFF ZIP tiles | GeoTIFF in ZIP | COG |
| 17 | [PRISM](#dataset-17) | Both | ≈654M, rounded listing — 800 m vpdmax, 12 monthly grids in 2024 | Raster ZIP; COG service available | COG or Zarr time series |
| 18 | [EPA Level III ecoregions](#dataset-18) | Official | ≈35 MB — CONUS vector package with state boundaries | Shapefile ZIP | GeoParquet + PMTiles |
| 19 | [USGS GAP CONUS 2011](#dataset-19) | Official | 2.00 GB — Complete CONUS producer package | Raster ZIP; inner encoding unverified | COG |
| 20 | [MODIS GPP/NPP](#dataset-20) | Official | ≈2,044 MB — Global 2024 MOD17A3HGF.061, 290 tiles | HDF-EOS2 | COG; Zarr across years |
| 21 | [Free-flowing rivers](#dataset-21) | Official | 954.71 MB — Global author-released network; excludes PDF | File geodatabase ZIP | GeoParquet + PMTiles |
| 22 | [RESOLVE Ecoregions 2017](#dataset-22) | Official | ≈150 MB — Global polygon shapefile | Shapefile ZIP | GeoParquet + PMTiles |
| 23 | [HydroSHEDS](#dataset-23) | Official | ≈16,460 MB — Global continental 3″ conditioned DEM only | GeoTIFF; HydroBASINS are shapefiles | COG; GeoParquet + PMTiles for basins |
| 24 | [SoilGrids 2.0](#dataset-24) | Community | Unknown — Global bulk-density means at six depths | Tiled GeoTIFF + VRT | COG; optional depth/property Zarr |
| 25 | [gridMET](#dataset-25) | Official | 79.53 GB — NCAR 1979–2025 archive; drought product excluded | NetCDF4; Zarr access exists | Zarr |
| 26 | [Global glacier elevation change](#dataset-26) | Community | ≈15 GB — 2000–2019 change/uncertainty raster family | GeoTIFF | COG |
| 27 | [WHRC tropical biomass](#dataset-27) | Official | Unknown — One 500 m pantropical map | GEE image; standalone format unverified | COG |
| 28 | [HydroLAKES](#dataset-28) | Community | ≈820 MB — Global v1 polygon layer | Shapefile ZIP; geodatabase alternative | GeoParquet + PMTiles |
| 29 | [MapBiomas](#dataset-29) | Both | Unknown — Brazil Collection 9 annual maps, 1985–2023 | GeoTIFF; GEE assets | COG; optional Zarr time stack |
| 30 | [MERIT DEM](#dataset-30) | Official | Unknown; registration-gated — Global v1.0.3, 3″ elevation | Float32 GeoTIFF in TAR | COG; publication rights review |

NCEP/NCAR entries are deprecated in the official snapshot. Several “Both” groups contain different versions or resolutions; see their detail records.

## Sources and scope details

<a id="dataset-1"></a>
### 1. ERA5

**Catalog:** Official. **Citation count:** 31,882.

**Scope:** Broad ERA5 archive scale, rather than a single variable-year. Exact compressed download bytes depend on which fields, levels, grid, time span and distribution are selected.

**Download amount:** Approximately 5 PB (broad publisher archive-scale estimate; compressed transfer total unverified) (`publisher_stated`).

**Evidence:** Producer-maintainer README states total ERA5 is about 5 petabytes. Compression/logical-size basis and vintage of that estimate are not specified. Do not use it as an exact transfer quote.

**Source formats:** GRIB / GRIB2; NetCDF4 download option; Zarr in ARCO distributions.

**Desired formats:** Zarr. Multidimensional hourly series suit chunked Zarr. Reference the maintained ARCO Zarr mirror when product/periods match; otherwise publish versioned Zarr preserving grid, units and metadata.

**Existing access:** Google Research ARCO-ERA5 provides public Zarr distributions. Prefer an appropriate existing store/reference; source store revisions are not assumed to identify a particular Zarr specification version.

- The full-archive approximation does not determine actual transfer bytes for a selected GEE product.
- The separately calculated 36.55 GB one-variable 2024 float32 array is uncompressed logical payload only.

Other explicitly scoped amounts:

- About 5 PB — Broad original ERA5 archive, approximate scale statement in Google Research README; not a measurement of the ARCO mirror. The introductory README gives about 5 PB for total ERA5. It separately lists sizes for different ARCO representations; these must not be conflated.
- 36.55 GB raw array payload (calculated uncompressed) — One regular 0.25° global single-level variable, 8,784 hourly records for 2024. 1,440 longitude × 721 latitude × 8,784 hours × 4 bytes/value = 36,548,505,600 bytes. Dense float32 payload only; not transfer/compressed bytes; excludes metadata, packing and coordinates. Native ERA5 grid differs (reduced Gaussian), so exact request output bytes depend on selected request representation.

Catalog entries: [ECMWF/ERA5/DAILY](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_DAILY); [ECMWF/ERA5/HOURLY](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_HOURLY); [ECMWF/ERA5/HOURLY_PRESSURE_LEVELS](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_HOURLY_PRESSURE_LEVELS); [ECMWF/ERA5/MONTHLY](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_MONTHLY).

Primary sources:

- [1](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download) — Single-level data request; GRIB and experimental NetCDF4 formats.
- [2](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-complete?tab=overview) — ERA5 native coverage, temporal scope, native grid and formats.
- [3](https://github.com/google-research/arco-era5/blob/main/README.md?plain=1) — ARCO-ERA5 Zarr v3 mirror and approximate 5 PB publisher statement.
- [4](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_HOURLY) — GEE hourly collection identity and representation.

<a id="dataset-2"></a>
### 2. NCEP/NCAR Reanalysis

**Catalog:** Official. **Citation count:** 28,374.

**Scope:** NOAA PSL NCEP/NCAR Reanalysis 1 surface air temperature at sigma 0.995, full global daily-averaged calendar-year file 2024 (air.sig995.2024.nc); a complete annual source file corresponding to the GEE surface-temperature family, not a full NCEP archive total.

**Download amount:** 7,004,162 bytes (NOAA HTTP Content-Length) (`measured`).

**Evidence:** Metadata-only HTTP HEAD to NOAA PSL THREDDS fileServer returned Content-Length: 7,004,162 for the exact annual file URL; THREDDS catalog metadata lists the same exact dataSize. No file body was read.

**Source formats:** NetCDF4 (NOAA PSL public distribution); original archive GRIB.

**Desired formats:** Zarr. Gridded reanalysis time series suit Zarr while preserving monthly coordinates, CF metadata, source grid and missing values.

**Existing access:** Not checked for a maintained cloud-native mirror; NOAA PSL provides public NetCDF access.

- This scope is one full global annual surface-temperature file, not all NCEP variables or the other two GEE entries.
- The prior raw monthly-SLP payload estimate is retained as an alternative and is not an observed download size.
- NOAA PSL stopped NCEP/NCAR production 2026-03-17; 2024 is complete.

Other explicitly scoped amounts:

- 0.505 MB raw array payload (calculated uncompressed) — 12 monthly SLP grids at 144×73 cells, 4-byte values. 144 × 73 × 12 × 4 = 504,576 bytes (0.505 decimal MB). Dense payload only, excludes NetCDF metadata/compression. NOAA documents this 2.5° grid; actual files vary with compression.

Catalog entries: [NCEP_RE/sea_level_pressure](https://developers.google.com/earth-engine/datasets/catalog/NCEP_RE_sea_level_pressure); [NCEP_RE/surface_temp](https://developers.google.com/earth-engine/datasets/catalog/NCEP_RE_surface_temp); [NCEP_RE/surface_wv](https://developers.google.com/earth-engine/datasets/catalog/NCEP_RE_surface_wv).

Primary sources:

- [1](https://psl.noaa.gov/thredds/fileServer/Datasets/ncep.reanalysis.dailyavgs/surface/air.sig995.2024.nc) — Metadata-only HEAD Content-Length=7,004,162 bytes for complete annual global NetCDF file; no body downloaded.
- [2](https://psl.noaa.gov/thredds/catalog/Datasets/ncep.reanalysis.dailyavgs/surface/catalog.html?dataset=Datasets/ncep.reanalysis.dailyavgs/surface/air.sig995.2024.nc) — TDS catalog records exact dataSize=7004162 for air.sig995.2024.nc.
- [3](https://psl.noaa.gov/data/gridded/data.ncep.reanalysis.html) — NetCDF4 distribution, 2.5° global 144×73 grid and dataset coverage.
- [4](https://psl.noaa.gov/data/reanalysis/) — PSL source collection, access and production-stop notice.
- [5](https://developers.google.com/earth-engine/datasets/catalog/NCEP_RE_sea_level_pressure) — Deprecated GEE SLP entry.

<a id="dataset-3"></a>
### 3. WorldClim v1

**Catalog:** Official. **Citation count:** 19,860.

**Scope:** WorldClim v1.4 BIO, global land, 30-arc-second (~1 km) release as represented by the GEE WORLDCLIM/V1/BIO catalog; all 19 bioclimatic variables in the worldwide ESRI-grid ZIP package.

**Download amount:** 1,862,513,222 bytes (measured Content-Length; 1.86 decimal GB) (`measured`).

**Evidence:** Metadata-only HTTP HEAD to the producer-hosted UC Davis geodata file bio_30s_esri.zip returned Content-Length: 1,862,513,222 bytes. Archive body was not downloaded.

**Source formats:** ZIP-compressed ESRI grid package (selected global release); generic BIL/HDR ZIP distribution; 30-second tiled GeoTIFF is also documented for tiled data.

**Desired formats:** COG. Static climate rasters suit COG; preserve integer precision, scaling/units, CRS and nodata; retain native grids for provenance.

**Existing access:** GEE has hosted collections; no public downloadable cloud-native COG/Zarr mirror verified.

- This is the full 30-arc-second BIO ESRI package corresponding to GEE pixel scale, not the earlier 10-minute lower-resolution proxy; that raw payload calculation is retained only as a separate alternative.
- ZIP bytes include the producer package and compression; unpacked grid size is larger. Preserve units/scaling and nodata.

Other explicitly scoped amounts:

- 35.46 GB raw array payload (calculated uncompressed at selected 30-second grid) — Dense rectangular 30-arc-second global array for all 19 BIO bands, including ocean no-data cells. 43200 longitude × 21600 latitude × 19 layers × 2 bytes/int16 = 35,458,560,000 bytes (35.46 decimal GB). This is an uncompressed payload calculation, not a source ZIP size.
- 88.65 MB raw array payload (calculated uncompressed) — 19 10-minute rasters over rectangular 360°×180° grid; includes ocean nodata cells; int16 values. 2160 rows × 1080 cols × 19 layers × 2 bytes = 88,646,400 bytes. Raw payload only, not ZIP size; excludes headers/compression.

Catalog entries: [WORLDCLIM/V1/BIO](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_BIO); [WORLDCLIM/V1/MONTHLY](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_MONTHLY).

Primary sources:

- [1](https://geodata.ucdavis.edu/climate/worldclim/1_4/grid/cur/bio_30s_esri.zip) — Producer-hosted full BIO v1.4 30s ESRI package; HEAD returned exact Content-Length 1,862,513,222 bytes.
- [2](https://geodata.ucdavis.edu/climate/worldclim/1_4/grid/cur/) — Producer directory index lists bio_30s_esri.zip (1.7G), bio1-9 and bio10-19 30s BIL packages (1.1G each), and lower-resolution alternatives.
- [3](https://worldclim.org/data/v1.4/formats.html) — V1 resolutions, 19 BIO layers, zip package layout, BIL/HDR and ESRI grids, cell type and GeoTIFF availability.
- [4](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_MONTHLY) — Separate monthly collection in same group.
- [5](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_BIO) — GEE WORLDCLIM/V1/BIO is at 927.67 m (~30 arc seconds) and includes 19 bands.

<a id="dataset-4"></a>
### 4. Hansen Global Forest Change

**Catalog:** Official. **Citation count:** 11,704.

**Scope:** GFC-2025-v1.13 global core maps: treecover2000, gain, lossyear and datamask; all 1,792 objects listed by these four producer URL manifests.

**Download amount:** 83,910,291,871 bytes (83.91 GB), four core map layers (`measured`).

**Evidence:** Exact GCS object-size sum; three listing pages, no remaining page token, unique objects, all four core URL manifests covered. Treecover2000 alone is 58,875,497,056 bytes, exceeding the stale <50GB webpage statement.

**Source formats:** GeoTIFF tiles (.tif).

**Desired formats:** COG. Already tile-based GeoTIFF; index/reference in place where possible. A necessary mirror should preserve granules and integer values, masks and grid as validated COGs.

**Existing access:** Public producer GeoTIFF granules on GCS plus layer URL-list manifests; also hosted in GEE. Prefer referencing/indexing producer files.

- Core-map manifests are complete in the captured listing. The imagery manifest fails completeness: 224 last-image URLs are absent.
- Source GeoTIFFs have not been validated as COGs.

Other explicitly scoped amounts:

- 1,676,700,778,015 bytes (1.677 TB) of TIFF objects currently listed — All 2,576 TIFFs currently listed under the version prefix, including imagery; not proof of a complete six-product release. The last-imagery URL manifest lists 504 objects but 224 are absent from the captured bucket listing. This amount is available listed bytes, not a verified complete imagery download.

Catalog entries: [UMD/hansen/global_forest_change_2025_v1_13](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13); [UMD/hansen/global_forest_change_2013](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2013); [UMD/hansen/global_forest_change_2014](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2014); [UMD/hansen/global_forest_change_2015](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2015); [UMD/hansen/global_forest_change_2015_v1_3](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2015_v1_3); [UMD/hansen/global_forest_change_2016_v1_4](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2016_v1_4); [UMD/hansen/global_forest_change_2017_v1_5](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2017_v1_5); [UMD/hansen/global_forest_change_2018_v1_6](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2018_v1_6); [UMD/hansen/global_forest_change_2019_v1_7](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2019_v1_7); [UMD/hansen/global_forest_change_2020_v1_8](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2020_v1_8); [UMD/hansen/global_forest_change_2021_v1_9](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2021_v1_9); [UMD/hansen/global_forest_change_2022_v1_10](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2022_v1_10); [UMD/hansen/global_forest_change_2023_v1_11](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2023_v1_11); [UMD/hansen/global_forest_change_2024_v1_12](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12).

Primary sources:

- [1](https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html) — Producer 10×10° granules, global URL lists, v1.13 identity and size bounds (<50 GB treecover2000, <10 GB gain/lossyear/datamask each, >600 GB first/last each).
- [2](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13) — GEE current collection, bands and scale.
- [3](https://storage.googleapis.com/storage/v1/b/earthenginepartners-hansen/o?prefix=GFC-2025-v1.13/&fields=items%28name%2Csize%29%2CnextPageToken&maxResults=1000) — Saved paginated object-size inventory and producer URL-manifest reconciliation in evidence-parent/.

<a id="dataset-5"></a>
### 5. MODIS vegetation indices

**Catalog:** Official. **Citation count:** 9,954.

**Scope:** MOD13C1.061 global 0.05-degree Terra vegetation-index collection, all 23 16-day global composite granules whose acquisition dates are in calendar year 2024; full native granules (including science and QA SDS), not an arbitrary tile/variable slice.

**Download amount:** About 2,191.46 MB (sum of NASA CMR granule size metadata) (`publisher_stated`).

**Evidence:** NASA CMR granules.umm_json query for MOD13C1, version 061, 2024 returned 24 records overlapping the year; selecting the 23 producer granule IDs A2024001 through A2024353 and summing ArchiveAndDistributionInformation.Size yields 2,191.460275 reported MB. CMR sizes have decimal precision and MB units, so display the summed publisher unit without converting to an asserted exact byte count.

**Source formats:** HDF-EOS MODIS granule files.

**Desired formats:** Zarr; COG (optional map derivative). MOD13C1 consists of global 16-day composites, so publish/index a time-chunked Zarr preserving native 0.05-degree grid, all science and QA SDS, scale factors and dates. Retain original HDF-EOS granules as provenance; COG can be a per-date map derivative.

**Existing access:** GEE image collections verified; no separate open COG/Zarr mirror verified.

- The input groups 16 catalog products across Terra/Aqua, resolutions and versions. This size is one listed product, MOD13C1.061, for one complete annual set of global composite granules.
- CMR records report file sizes in MB rounded to varying decimal precision; total preserves that unit and is not HEAD-verified object Content-Length.
- Prior single-NDVI-tile raw-array calculation is retained as an alternate illustrative payload, not a family download size.

Other explicitly scoped amounts:

- 2.88 MB raw array payload (calculated uncompressed) — One 1200×1200 tile, one 16-bit NDVI science layer. 1200 × 1200 × 2 bytes = 2,880,000 bytes. Excludes QA, EVI, ancillary SDS, HDF metadata and compression; actual file size is unknown.

Catalog entries: [MODIS/061/MOD13A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13A1); [MODIS/061/MOD13A2](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13A2); [MODIS/061/MOD13A3](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13A3); [MODIS/061/MOD13C1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13C1); [MODIS/061/MOD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1); [MODIS/061/MYD13A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD13A1); [MODIS/061/MYD13A2](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD13A2); [MODIS/061/MYD13A3](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD13A3); [MODIS/061/MYD13C1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD13C1); [MODIS/061/MYD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD13Q1); [MODIS/006/MOD13A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD13A1); [MODIS/006/MOD13A2](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD13A2); [MODIS/006/MOD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD13Q1); [MODIS/006/MYD13A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MYD13A1); [MODIS/006/MYD13A2](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MYD13A2); [MODIS/006/MYD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MYD13Q1).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/granules.umm_json?short_name=MOD13C1&version=061&temporal=2024-01-01T00%3A00%3A00Z%2C2024-12-31T23%3A59%3A59Z&page_size=30) — NASA CMR public granule manifest and each 2024 MOD13C1.061 granule ArchiveAndDistributionInformation.Size; 23 acquisition-year files sum to about 2,191.46 MB.
- [2](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13C1) — GEE listed MOD13C1.061 global 0.05-degree 16-day product, NDVI/EVI and QA bands.

<a id="dataset-6"></a>
### 6. MERRA-2

**Catalog:** Both. **Citation count:** 9,045.

**Scope:** MERRA-2 M2T1NXSLV (tavg1_2d_slv_Nx), full global hourly single-level source product for calendar year 2024, all variables in each daily NetCDF granule; one of the listed official family products.

**Download amount:** About 146,400 MB (146.4 decimal GB; publisher average summed for 366 daily files) (`bounded_estimate`).

**Evidence:** NASA CMR collection metadata reports Native NetCDF AverageFileSize=400 MB per file. Product is hourly and source files are daily. 366 × 400 MB = 146,400 MB (decimal conversion shown); this is a publisher-average estimate, not an exact sum of granule Content-Lengths.

**Source formats:** NetCDF (NASA GES DISC); hosted GEE collections.

**Desired formats:** Zarr. Hourly model fields suit chunked Zarr, preserving native grid, time, units, model version and variables.

**Existing access:** NASA GES DISC has cloud-enabled access and GEE has hosted collections; no public analysis-ready Zarr mirror verified.

- GEE entries represent distinct aerosol, flux, land, radiation and state-variable collections; community member is separate. This selected M2T1NXSLV product-wide annual size is not a sum across the GEE family.
- 400 MB is an average source granule size. Total is estimated from 366 daily granules and can vary.
- The earlier single-variable raw array estimate is retained as alternative.

Other explicitly scoped amounts:

- 1.2 GB per monthly file — Distinct MERRA-2 instM_3d_asm_Np 42-pressure-level monthly product, not SLV subset. NASA GES DISC size for the separate monthly multidimensional product; shown to demonstrate family products cannot be conflated.
- 7.34 GB raw array payload (calculated uncompressed) — One 0.5°×0.625° global T2M field, 8,784 hourly records, 4-byte values. 576 longitude × 361 latitude × 8,784 hours × 4 = 7,335,728,640 bytes (7.34 decimal GB). Dense payload only; no metadata or compression; not source-file bytes.
- 1.2 GB per monthly file — A distinct 42-pressure-level MERRA-2 monthly collection, not M2T1NXSLV. GES DISC summary size; retained only to distinguish prior comparison.

Catalog entries: [merrav2](https://gee-community-catalog.org/projects/merrav2); [NASA/GSFC/MERRA/aer/2](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_aer_2); [NASA/GSFC/MERRA/aer_nv/2](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_aer_nv_2); [NASA/GSFC/MERRA/flx/2](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_flx_2); [NASA/GSFC/MERRA/lnd/2](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_lnd_2); [NASA/GSFC/MERRA/rad/2](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_rad_2); [NASA/GSFC/MERRA/slv/2](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_slv_2).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/collections.umm_json?short_name=M2T1NXSLV&page_size=1) — NASA CMR metadata identifies M2T1NXSLV and Native NetCDF average file size of 400 MB; direct S3 distribution prefix recorded in metadata (protected).
- [2](https://disc.gsfc.nasa.gov/datasets?keywords=MERRA2&page=1&sort=timeRes) — GES DISC hourly product families, 0.5°×0.625° resolution and temporal coverage.
- [3](https://disc.gsfc.nasa.gov/datasets/M2IMNPASM_5.12.4/summary?keywords=MERRA-2) — NetCDF format and distinct 1.2 GB/month pressure-level product size.
- [4](https://developers.google.com/earth-engine/datasets/catalog/NASA_GSFC_MERRA_slv_2) — GEE SLV product bands, dates and spatial scale.

<a id="dataset-7"></a>
### 7. SRTM elevation

**Catalog:** Official. **Citation count:** 8,927.

**Scope:** Entire SRTMGL1 version 003 global 1-arc-second HGT-in-ZIP tile collection, rather than one representative tile.

**Download amount:** 99,883.2 MB (~99.9 decimal GB), publisher-stated full collection size (`publisher_stated`).

**Evidence:** NASA CMR UMM collection metadata TotalCollectionFileSize=99,883.2 MB. Byte equivalent uses decimal MB (1 MB=1,000,000 bytes); the preserved publisher display is authoritative. Not a current remeasurement.

**Source formats:** HGT distributed as compressed ZIP tile files (NASA CMR); GeoTIFF product variants also exist in USGS/LP DAAC distribution.

**Desired formats:** COG. Static elevation raster suits COG; preserve 1-arc-second postings, geoid reference, integer elevations and void/water values.

**Existing access:** GEE asset is hosted; no openly downloadable cloud-native mirror checked.

- CMR collection total is a producer metadata archive size; individual tile sizes vary.
- Keep release and void-fill provenance separate.

Other explicitly scoped amounts:

- 99,883.2 MB (~99.9 GB) — Entire SRTMGL1 version 003 collection, according to NASA CMR TotalCollectionFileSize metadata. Public CMR UMM collection metadata field TotalCollectionFileSize=99883.2 MB; publisher-stated collection size, not sum recalculated by this audit.
- About 7 MB per tile (publisher-stated average) — One SRTMGL1 V003 1°×1° HGT tile; NASA CMR metadata reports 7 MB average file size for this collection. Public NASA CMR UMM metadata for short_name=SRTMGL1, version=003 reports Format HGT, compressed ZIP download and AverageFileSize=7 MB. This is a rounded mean across files, not the exact size of a particular tile.
- 7 MB average per file — One SRTMGL1 V003 HGT tile in compressed ZIP distribution. NASA CMR reports AverageFileSize=7 MB. This is a collection average, not a particular tile size.

Catalog entries: [USGS/SRTMGL1_003](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/collections.umm_json?short_name=SRTMGL1&version=003&page_size=5) — NASA CMR collection metadata: format HGT, ZIP compression, 7 MB average file size and 99,883.2 MB total collection size.
- [2](https://lpdaac.usgs.gov/documents/179/SRTM_User_Guide_V3.pdf) — 1°×1° SRTM tiles and SRTMGL1 3601×3601 grid.
- [3](https://lpdaac.usgs.gov/documents/13/SRTM_Quick_Guide.pdf) — Product versions and global data access points.
- [4](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003) — GEE asset identity and band.

<a id="dataset-8"></a>
### 8. TRMM TMPA

**Catalog:** Official. **Citation count:** 6,773.

**Scope:** TRMM TMPA 3B43 V7 global monthly precipitation rate, year 2019 (12 monthly granules); not separate 3-hourly 3B42.

**Download amount:** About 58.8 MB (publisher average 4.9 MB × 12 monthly files) (`bounded_estimate`).

**Evidence:** NASA CMR collection metadata reports Native HDF AverageFileSize=4.9 MB. 12 × 4.9 MB = 58.8 MB (decimal MB), a publisher-average annual estimate; exact per-granule Content-Lengths not queried.

**Source formats:** HDF4, one file per monthly 3B43 granule; NASA services also offer subset output formats.

**Desired formats:** Zarr. Monthly gridded rainfall series suit Zarr; preserve 0.25° cells, units, error fields and time.

**Existing access:** NASA GES DISC cloud-enabled service; no public Zarr mirror verified.

- Input has both 3B42 and 3B43 with different timesteps and sizes. Scope is 3B43 only.
- 5 MB is producer's approximate uncompressed size; exact transfer bytes may differ.

Other explicitly scoped amounts:

- About 11 MB uncompressed per granule — Different 3-hourly 3B42 product. NASA documentation per-file amount; do not conflate with 3B43.
- Approximately 60 MB uncompressed (calculated from publisher-stated per-file size) — 12 monthly 3B43 V7 files in 2019. NASA says approximately 5 MB uncompressed per 3B43 file; 12 × approx. 5 MB = approx. 60 MB. This is rounded uncompressed size, not measured transfer bytes.

Catalog entries: [TRMM/3B42](https://developers.google.com/earth-engine/datasets/catalog/TRMM_3B42); [TRMM/3B43V7](https://developers.google.com/earth-engine/datasets/catalog/TRMM_3B43V7).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/collections.umm_json?short_name=TRMM_3B43&version=7&page_size=1) — NASA CMR identifies TRMM 3B43 V7 and reports Native HDF average file size of 4.9 MB per granule.
- [2](https://gpm.nasa.gov/sites/default/files/document_files/3B42_3B43_doc_V7.pdf) — NASA HDF archive; separate files per timestep; approximate uncompressed 11 MB 3B42 and 5 MB 3B43 sizes.
- [3](https://developers.google.com/earth-engine/datasets/catalog/TRMM_3B43V7) — GEE 3B43 V7 monthly product and cadence.
- [4](https://developers.google.com/earth-engine/datasets/catalog/TRMM_3B42) — Distinct 3-hourly member.

<a id="dataset-9"></a>
### 9. CHIRPS

**Catalog:** Official. **Citation count:** 6,459.

**Scope:** CHIRPS v2 daily, global 50°S–50°N at 0.05°, 2024; one daily field, not pentad collection or full archive.

**Download amount:** 1,359,386,943 bytes (NOAA ERDDAP file-list metadata for annual NetCDF mirror) (`measured`).

**Evidence:** NOAA CoastWatch ERDDAP file listing for its CHIRPS20GlobalDailyP05_Lon0360 mirror reports exact file length 1,359,386,943 bytes for this annual file. This is the mirror copy size, not a direct CHC Content-Length.

**Source formats:** GeoTIFF, BIL, NetCDF.

**Desired formats:** Zarr; COG (optional map derivative). Daily precipitation series suit chunked Zarr; preserve 0.05° grid, daily total units, nodata, version and provenance.

**Existing access:** CHC provides public bulk-download archives; no maintained public Zarr verified. GEE collection is separately hosted.

- CHIRPS v2 production is scheduled to end after December 2026; this scope follows v2 GEE catalog entries.
- Direct CHC metadata access attempts failed (HTTP 429 for the annual NetCDF HEAD and web directory fetch 404); the exact size is from NOAA CoastWatch ERDDAP mirror listing. Treat source-copy byte identity as unverified.
- The prior 21.02 GB dense raw-array figure is retained as an alternative and is not an observed compressed download size.

Other explicitly scoped amounts:

- 21.0816 GB raw array payload (calculated uncompressed) — 366 daily 2024 grids at 7200 × 2000 cells, 32-bit values. 7200×2000×366×4=21,081,600,000 bytes. Leapyear 2024; excludes compression/metadata, not transfer size.

Catalog entries: [UCSB-CHG/CHIRPS/DAILY](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY); [UCSB-CHG/CHIRPS/PENTAD](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_PENTAD).

Primary sources:

- [1](https://coastwatch.pfeg.noaa.gov/erddap/pt/files/chirps20GlobalDailyP05_Lon0360/) — NOAA CoastWatch ERDDAP file-list metadata gives chirps-v2.0.2024.days_p05.nc length 1,359,386,943 bytes; mirrored CHIRPS file, not direct producer listing.
- [2](https://chc.ucsb.edu/data/chirps/) — Producer v2 coverage/status and archive links.
- [3](https://wiki.chc.ucsb.edu/index.php?title=CHIRPS2_FAQ) — Producer grid domain/dimensions 7200×2000, 0.05° resolution, daily cadence and TIF/BIL/NetCDF formats.
- [4](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY) — GEE daily product identity and cadence.
- [5](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_PENTAD) — Separate pentad product.

<a id="dataset-10"></a>
### 10. GLDAS

**Catalog:** Official. **Citation count:** 5,648.

**Scope:** GLDAS-2.1 Noah 0.25° 3-hourly, full global-land leap year 2020, all eight 3-hour steps/day and all source fields; distinct from CLSM daily and legacy Noah v2.0 entries.

**Download amount:** About 55,632 MB (55.63 decimal GB; 2,928 files × 19 MB/file) (`bounded_estimate`).

**Evidence:** NASA GES DISC reports 19 MB per file and 3-hour cadence. Leap-year 2020 has 366 × 8 = 2,928 files; 2,928 × 19 MB = 55,632 MB (decimal conversion shown). This is a publisher average per-file estimate, not exact Content-Length for all granules.

**Source formats:** NetCDF.

**Desired formats:** Zarr. Land-model fields form multidimensional time series; Zarr suits time/variable chunking while preserving model version, grid, timestep bounds, units and all fields.

**Existing access:** NASA GES DISC publicly distributes NetCDF/cloud-enabled data; no maintained Zarr mirror verified.

- Input also includes separate CLSM daily and legacy Noah datasets; this estimate covers only GLDAS Noah V2.1 3-hourly.
- 19 MB/file is rounded; yearly total is an estimate. Earlier one-day estimate is retained in alternatives.

Other explicitly scoped amounts:

- About 152 MB publisher-stated (8 files × 19 MB/file) — Eight GLDAS Noah v2.1 3-hourly files for one day, all included fields. NASA GES DISC states 19 MB per file; eight 3-hour files/day × 19 MB = about 152 MB. Rounded publisher file size summed across daily granules, not measured exact transfer bytes.

Catalog entries: [NASA/GLDAS/V021/NOAH/G025/T3H](https://developers.google.com/earth-engine/datasets/catalog/NASA_GLDAS_V021_NOAH_G025_T3H); [NASA/GLDAS/V022/CLSM/G025/DA1D](https://developers.google.com/earth-engine/datasets/catalog/NASA_GLDAS_V022_CLSM_G025_DA1D); [NASA/GLDAS/V20/NOAH/G025/T3H](https://developers.google.com/earth-engine/datasets/catalog/NASA_GLDAS_V20_NOAH_G025_T3H).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/collections.umm_json?short_name=GLDAS_NOAH025_3H&version=2.1&page_size=1) — NASA CMR Native NetCDF average granule size of 19 MB for GLDAS_NOAH025_3H V2.1.
- [2](https://disc.gsfc.nasa.gov/datasets/GLDAS_NOAH025_3H_2.1/summary?keywords=GLDAS) — NASA NetCDF, 0.25°/3-hourly coverage, 36 fields and 19 MB per file.
- [3](https://developers.google.com/earth-engine/datasets/catalog/NASA_GLDAS_V021_NOAH_G025_T3H) — GEE Noah 2.1 3-hour collection identity, dates and bands.
- [4](https://developers.google.com/earth-engine/datasets/catalog/NASA_GLDAS_V022_CLSM_G025_DA1D) — Separate daily CLSM product.
- [5](https://developers.google.com/earth-engine/datasets/catalog/NASA_GLDAS_V20_NOAH_G025_T3H) — Separate legacy Noah product.

<a id="dataset-11"></a>
### 11. ERA5-Land

**Catalog:** Official. **Citation count:** 5,540.

**Scope:** Global ERA5-Land hourly reanalysis, 1950-present, as referenced by GEE hourly, daily aggregate, monthly aggregate, monthly-by-hour and static entries. Multi-product family, not one archive.

**Download amount:** unknown (`unknown`).

**Evidence:** Producer download interface exposes GRIB and experimental NetCDF4 and selectable dates/variables, but no fixed all-family archive byte total. No request submitted.

**Source formats:** GRIB (full gridded CDS product); NetCDF4 (experimental CDS download option); Zarr (subset/ARCO time-series service); NetCDF/CSV (single-point time-series service).

**Desired formats:** Zarr. Chunked Zarr fits the full grid/time dimensions where a cloud-native publication is needed; use/reference the producer ARCO Zarr for its point/limited-area scope. Preserve source units, coordinates and variable metadata.

**Existing access:** CDS publishes a maintained ARCO Zarr subset for point/limited-area long time series; the full gridded product remains distributed separately. Prefer referencing ARCO where its subset scope matches.

- GEE contains several temporal aggregations and a static image; these are not interchangeable with the hourly archive.
- Full archive size varies with requested variables, period, area and encoding.

Other explicitly scoped amounts:

- 227,185,344,000 bytes (~227 GB decimal), raw float32 array payload — Illustrative one-variable global 0.1° grid for one complete 365-day hourly year (3600 longitude cells × 1801 latitude cells × 8760 hours). Not a compressed download estimate and not whole ERA5-Land archive size. 3600 × 1801 × 8760 × 4 bytes per float32 value; grid spacing/global coverage/hourly cadence from producer product documentation. Assumes every grid/time cell is stored as a four-byte value; excludes masks, metadata, compression, packing and any missing-point optimizations.

Catalog entries: [ECMWF/ERA5_LAND/DAILY_AGGR](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR); [ECMWF/ERA5_LAND/HOURLY](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY); [ECMWF/ERA5_LAND/MONTHLY_AGGR](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR); [ECMWF/ERA5_LAND/MONTHLY_BY_HOUR](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_BY_HOUR); [ECMWF/ERA5_LAND/STATIC](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_STATIC); [ECMWF/ERA5_LAND/MONTHLY](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY).

Primary sources:

- [1](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=download) — ERA5-Land producer download interface; GRIB/NetCDF4 and configurable selection
- [2](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY) — GEE hourly product identity and cadence
- [3](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR) — GEE daily aggregated product identity
- [4](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) — Producer global coverage, regular lat-lon 0.1° grid, hourly temporal resolution, GRIB full-product format
- [5](https://confluence.ecmwf.int/pages/viewpage.action?pageId=627854121) — Producer documentation for 0.1° hourly single-point time series and ARCO Zarr storage

<a id="dataset-12"></a>
### 12. JRC Global Surface Water

**Catalog:** Official. **Citation count:** 5,374.

**Scope:** Exact size-bearing subset: JRC GSW v1.4 global Occurrence layer (1984-2021), 504 GeoTIFF tiles; other GSW products (metadata, yearly history, monthly history and recurrence) are separate and excluded from this total.

**Download amount:** 15,972,544,704 bytes (15.97 GB decimal) (`measured`).

**Evidence:** Summed exact object size metadata from the public Google Cloud Storage JSON API listing (504 items, no nextPageToken; response 56,671 bytes). No TIFF bodies downloaded.

**Source formats:** GeoTIFF tiles (10° x 10°).

**Desired formats:** COG; Zarr. Use COG for discrete global summary layers and chunked Zarr for monthly history/recurrence time dimensions, preserving class codes and masks.

**Existing access:** Google Earth Engine asset collection; JRC also serves WMS tiles. No cloud-native analytic archive verified.

- This is only the v1.4 global Occurrence layer; monthly history, metadata, yearly history, recurrence and other summary layers add separate volumes.
- The total applies to the v1.4 1984-2021 object names, not current GSW v1.5 products through 2024.
- Tile GeoTIFF compression/COG status was not inferred from the file suffix.

Catalog entries: [JRC/GSW1_4/GlobalSurfaceWater](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater); [JRC/GSW1_4/Metadata](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_Metadata); [JRC/GSW1_4/MonthlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory); [JRC/GSW1_4/MonthlyRecurrence](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyRecurrence); [JRC/GSW1_4/YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_YearlyHistory); [JRC/GSW1_0/GlobalSurfaceWater](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_0_GlobalSurfaceWater); [JRC/GSW1_0/Metadata](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_0_Metadata); [JRC/GSW1_0/MonthlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_0_MonthlyHistory); [JRC/GSW1_0/MonthlyRecurrence](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_0_MonthlyRecurrence); [JRC/GSW1_0/YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_0_YearlyHistory); [JRC/GSW1_1/GlobalSurfaceWater](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_1_GlobalSurfaceWater); [JRC/GSW1_1/Metadata](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_1_Metadata); [JRC/GSW1_1/MonthlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_1_MonthlyHistory); [JRC/GSW1_1/MonthlyRecurrence](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_1_MonthlyRecurrence); [JRC/GSW1_1/YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_1_YearlyHistory); [JRC/GSW1_2/GlobalSurfaceWater](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_2_GlobalSurfaceWater); [JRC/GSW1_2/Metadata](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_2_Metadata); [JRC/GSW1_2/MonthlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_2_MonthlyHistory); [JRC/GSW1_2/MonthlyRecurrence](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_2_MonthlyRecurrence); [JRC/GSW1_2/YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_2_YearlyHistory); [JRC/GSW1_3/GlobalSurfaceWater](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_3_GlobalSurfaceWater); [JRC/GSW1_3/Metadata](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_3_Metadata); [JRC/GSW1_3/MonthlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_3_MonthlyHistory); [JRC/GSW1_3/MonthlyRecurrence](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_3_MonthlyRecurrence); [JRC/GSW1_3/YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_3_YearlyHistory).

Primary sources:

- [1](https://global-surface-water.appspot.com/download) — JRC download mechanisms, GeoTIFF tile delivery, available product types and v1.4 period through 2021
- [2](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory) — GEE monthly-history v1.4 product identity
- [3](https://storage.googleapis.com/storage/v1/b/global-surface-water/o?prefix=downloads2021%2Foccurrence%2F&fields=items%28name%2Csize%29%2CnextPageToken&maxResults=1000) — Complete public object listing for all 504 2021 v1.4 occurrence GeoTIFF tiles and exact sizes; summed to 15,972,544,704 bytes

<a id="dataset-13"></a>
### 13. CFSR

**Catalog:** Official. **Citation count:** 5,159.

**Scope:** NCAR GDEX d093000: complete CFSR six-hourly analyzed and forecast-product archive, January 1979–December 2010, global, multiple fields/levels/resolutions. Wider than the GEE band subset.

**Download amount:** 55.81 TB (publisher-stated six-hourly archive) (`publisher_stated`).

**Evidence:** NCAR producer archive metadata reports 55.81 TB and WMO GRIB2; metadata page captured in evidence-parent/cfsr-6hourly.json.

**Source formats:** GRIB2.

**Desired formats:** Zarr. For a curated variable/time subset, chunked Zarr supports multidimensional reanalysis queries while keeping source grid, time, vertical levels and metadata.

**Existing access:** NOAA/NCEP and NCAR RDA provide public download services; cloud-native distribution not verified.

- 55.81 TB includes a broader parameter/level archive than the GEE collection.
- Separate monthly archive d093002 is 5.05 TB; do not add it as an independent dataset without considering overlap.

Other explicitly scoped amounts:

- 5.05 TB (UCAR-published total volume) — NCAR Research Data Archive d093002 monthly CFSR products, January 1979-December 2010; not the entire CFSR collection or GEE harmonized image collection. NCAR RDA reports total volume 5.05 TB and WMO GRIB2 for dataset d093002. Publisher unit retained; no byte conversion inferred.

Catalog entries: [NOAA/CFSR_HARMONIZED](https://developers.google.com/earth-engine/datasets/catalog/NOAA_CFSR_HARMONIZED); [NOAA/CFSR](https://developers.google.com/earth-engine/datasets/catalog/NOAA_CFSR).

Primary sources:

- [1](https://gdex.ucar.edu/datasets/d093000/) — Full six-hourly 1979–2010 archive 55.81 TB, WMO GRIB2.
- [2](https://rda.ucar.edu/datasets/d093002/detailed_metadata/) — CFSR monthly product period, GRIB2 format and published 5.05 TB volume
- [3](https://www.ncei.noaa.gov/products/weather-climate-models/climate-forecast-system) — NOAA CFSR period and GRIB2/BUFR distribution formats
- [4](https://developers.google.com/earth-engine/datasets/catalog/NOAA_CFSR_HARMONIZED) — GEE harmonized catalog product identity

<a id="dataset-14"></a>
### 14. River plastic inputs

**Catalog:** Community. **Citation count:** 4,009.

**Scope:** Figshare v6 PlasticRiverInputs.zip: worldwide modeled 2010 river plastic inputs, 40,760 point records. Distinct from the Meijer et al. 2021 river-plastic model.

**Download amount:** 5,764,810 bytes (5.76 MB decimal) (`measured`).

**Evidence:** Exact producer file size recorded in local source inventory/release manifest; Figshare article API metadata is primary remote source. Local prepared GeoParquet (6,360,991 bytes) and PMTiles (3,705,340 bytes) are separate unpublished derivatives and are not source download volume.

**Source formats:** ZIP archive containing ESRI Shapefile components.

**Desired formats:** GeoParquet; PMTiles (optional display derivative). GeoParquet retains point attributes and nulls for analytic filtering; PMTiles supports compact map display. Keep full-resolution analytical records separate from generalized display tiles.

**Existing access:** No exact native cloud-native counterpart established in targeted inventory; locally prepared outputs are not published.

- Source estimate is for 2010; model values are not an annually updated time series.
- Four source rows contain null emission estimates; preserve null rather than replacing with zero.
- Local derivatives have not been uploaded and are not public downloads.

Other explicitly scoped amounts:

- GeoParquet 6,360,991 bytes — Locally prepared unpublished derivative only; not a public producer download. Local releases/figshare-v6-r2/manifest.json asset size; not included in source download size.
- PMTiles 3,705,340 bytes — Locally prepared unpublished derivative only; not a public producer download. Local releases/figshare-v6-r2/manifest.json asset size; not included in source download size.

Catalog entries: [plastic](https://gee-community-catalog.org/projects/plastic).

Primary sources:

- [1](https://api.figshare.com/v2/articles/4725541) — Figshare v6 article metadata, file inventory, file size and license
- [2](https://ndownloader.figshare.com/files/7714864) — Original PlasticRiverInputs.zip producer file
- [3](https://gee-community-catalog.org/projects/plastic) — Community catalog source identity

<a id="dataset-15"></a>
### 15. TerraClimate

**Catalog:** Both. **Citation count:** 3,477.

**Scope:** Current TerraClimate v1.1 base archive:14 variables × 76 years (1950–2025) = 1,064 global annual NetCDF files. Excludes plus2C/plus4C scenarios.

**Download amount:** 115,507.4 Mbytes (sum of rounded producer catalog sizes; about 116–121 GB depending on MB convention) (`publisher_stated`).

**Evidence:** Parsed producer catalog.xml. Each of 14 variables has 76 annual files. Summed rounded dataSize values; retained Mbytes unit because exact byte values are not present. Saved file inventory and arithmetic in evidence-parent/terraclimate-base-size-summary.json.

**Source formats:** NetCDF4 (.nc annual file per variable; producer says NetCDF4).

**Desired formats:** Zarr. Monthly global variables across years fit chunked multidimensional Zarr; preserve scale/offset, CF metadata, time axis, variable units and masks.

**Existing access:** THREDDS serves current v1.1 annual NetCDF files and aggregated NetCDF; GEE hosts a TerraClimate collection, but v1.1/current-vintage parity was not verified.

- Current producer v1.1 is a different vintage from older GEE/community representations; parity has not been established.
- Producer warns against mixing v1.0 and v1.1. Warming scenarios are excluded.
- Rounded catalog sizes imply approximate total only.

Other explicitly scoped amounts:

- 135.6 Mbytes (THREDDS-published file size) — TerraClimate v1.1 global vap 2024 NetCDF file, monthly annual series for one variable only. NKN/THREDDS producer catalog lists TerraClimate_vap_2024.nc at 135.6 Mbytes. Catalog reports rounded Mbytes; no conversion to exact bytes inferred.
- about 800 GB uncompressed (original 1958-2015 all-variable archive) — Historical TerraClimate v1.0 original dataset paper’s full global multi-variable archive for 1958-2015, not current v1.1 compressed distribution. 2018 producer paper states approx. 800 GB after uncompressing the original all-variable archive. This is not a compressed download total.

Catalog entries: [terraclim](https://gee-community-catalog.org/projects/terraclim); [IDAHO_EPSCOR/TERRACLIMATE](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE).

Primary sources:

- [1](https://tds-proxy.nkn.uidaho.edu/thredds/catalog/TERRACLIMATE_ALL/data/catalog.xml) — 1,064 base NetCDF variable-year files, 1950–2025; sizes and paths.
- [2](https://www.climatologylab.org/terraclimate.html) — Current monthly global coverage, variables and annual NetCDF availability
- [3](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE) — Official GEE collection identity
- [4](https://tds-proxy.nkn.uidaho.edu/thredds/catalog/TERRACLIMATE_ALL/data/catalog.html) — Producer THREDDS v1.1 catalog listing TerraClimate_vap_2024.nc at 135.6 Mbytes
- [5](https://www.climatologylab.org/terraclimate.html) — Current v1.1, current temporal period and NetCDF4 update; warning against mixing v1.0/v1.1
- [6](https://doi.org/10.1038/sdata.2017.191) — Original TerraClimate 1958-2015 archive and ~800 GB uncompressed alternative scope

<a id="dataset-16"></a>
### 16. Global Mangrove Forests 2000

**Catalog:** Official. **Citation count:** 3,186.

**Scope:** Complete producer tile release for the global 30 m Global Mangrove Forests Distribution 2000 map: all 111 CMR granules, each a ZIP file whose data-link description identifies GeoTIFF format. Distinct from Global Mangrove Watch epochs.

**Download amount:** 59.39 MB (sum of 111 rounded CMR granule_size values) (`publisher_stated`).

**Evidence:** CMR public granule metadata lists 111 records with unique granule IDs/titles, each data-link description states GeoTIFF format, and per-granule granule_size values sum to 59.39 MB. CMR sizes are rounded per granule; no exact bytes are inferred. Parent evidence response saved at evidence-parent/mangrove-granules.json.

**Source formats:** ZIP containing GeoTIFF tile.

**Desired formats:** COG. A single categorical global raster is suited to COG for range reads, preserving 30 m grid, class value and NoData semantics.

**Existing access:** GEE asset; NASA metadata identifies WMS access. No COG-hosted source verified.

- CMR records identify 111 unique grid tile ZIPs for this global year-2000 product; size is rounded per-granule metadata, not exact byte sum.
- This is the Giri et al. year-2000 product, not later Global Mangrove Watch time series.
- Do not infer COG tiling or internal TIFF compression from .zip/.tif names.

Catalog entries: [LANDSAT/MANGROVE_FORESTS](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_MANGROVE_FORESTS).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C3550194192-ESDIS&page_size=200) — All 111 CMR granule metadata records, unique tile IDs/titles, per-granule size fields and GeoTIFF data-link descriptions
- [2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_MANGROVE_FORESTS) — GEE baseline map identity and 2000 time span
- [3](https://data.nasa.gov/dataset/global-mangrove-forests-distribution-2000) — NASA/SEDAC dataset record and global 30 m extent

<a id="dataset-17"></a>
### 17. PRISM

**Catalog:** Both. **Citation count:** 3,113.

**Scope:** For a size-bearing current producer example: CONUS 800 m monthly PRISM VPD maximum, all 12 months of 2024 (one variable-year), using PRISM time-series source. Distinct from older official GEE PRISM collection at 4,638.3 m pixel size (1981-present) and community 800 m catalog entries.

**Download amount:** Approximately 654M in producer listing units (12 monthly ZIPs) (`publisher_stated`).

**Evidence:** Producer directory 202401–202412 values 56+56+56+57+58+59+59+59+50+49+48+47=654M. Rounded listing units retained; no exact byte conversion.

**Source formats:** ZIP of raster grid(s) in legacy bulk distribution; Cloud Optimized GeoTIFF for current one-grid web service; NetCDF/ASCII/BIL available as alternate web-service formats.

**Desired formats:** COG; Zarr. COG suits independent monthly grid access; Zarr is useful for full monthly/daily series across variables. Retain PRISM release/stability metadata because grids may be re-modeled.

**Existing access:** Current PRISM web service explicitly serves COG; GEE also hosts an older 4 km collection.

- One variable and one year at 800 m. GEE official 4 km and community 800 m product variants differ.
- PRISM already provides COG web-service outputs; existing delivery may be preferable to conversion.
- Source directory sizes are rounded.

Other explicitly scoped amounts:

- 49M — One annual 2024 vpdmax grid, not a 12-month stack. Separate prism_vpdmax_us_30s_2024.zip entry.

Catalog entries: [prism_daily](https://gee-community-catalog.org/projects/prism_daily); [prism_monthly](https://gee-community-catalog.org/projects/prism_monthly); [OREGONSTATE/PRISM/ANd](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_ANd); [OREGONSTATE/PRISM/ANm](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_ANm); [OREGONSTATE/PRISM/Norm91m](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_Norm91m); [OREGONSTATE/PRISM/AN81d](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_AN81d); [OREGONSTATE/PRISM/AN81m](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_AN81m); [OREGONSTATE/PRISM/Norm81m](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_Norm81m).

Primary sources:

- [1](https://data.prism.oregonstate.edu/time_series/us/lt/800m/vpdmax/monthly/2024/) — Twelve monthly ZIP sizes total 654M; annual grid is separate 49M.
- [2](https://prism.nacse.org/documents/PRISM_downloads_web_service.pdf) — YYYY is annual; YYYYMM is monthly; current service formats.
- [3](https://data.prism.oregonstate.edu/time_series/us/lt/800m/vpdmax/monthly/2024/) — Producer listing for 2024 vpdmax monthly ZIP and rounded 49M file size
- [4](https://prism.nacse.org/documents/PRISM_downloads_web_service.pdf) — Current PRISM web service COG output and alternate formats
- [5](https://developers.google.com/earth-engine/datasets/catalog/OREGONSTATE_PRISM_ANd) — GEE PRISM pixel size, 1981-present span and AN81/AN91 distinction
- [6](https://prism.oregonstate.edu/data/) — PRISM daily/monthly/annual availability and stability notes

<a id="dataset-18"></a>
### 18. EPA Level III ecoregions

**Catalog:** Official. **Citation count:** 2,695.

**Scope:** US EPA Level III ecoregions shapefile covering continental United States, with state boundaries, as native vector analogue to GEE EPA/Ecoregions/2013/L3 feature collection.

**Download amount:** 35 MB (EPA publisher-stated) for Level III shapefile with state boundaries (`publisher_stated`).

**Evidence:** EPA producer page labels shapefile size as 35 mb; publisher unit preserved and not converted to exact byte count.

**Source formats:** ESRI Shapefile ZIP; PDF map products.

**Desired formats:** GeoParquet; PMTiles (optional display derivative). GeoParquet preserves polygon attributes and supports spatial filtering; PMTiles is useful for map display. Preserve ecoregion identifiers, boundaries and source geometry.

**Existing access:** GEE feature collection; EPA page also distributes shapefile and metadata/symbology. No cloud-native vector archive verified.

- EPA page cautions that maps and GIS files may differ and recommends GIS shapefiles for current data.
- 35 MB published value is for with-state-boundaries package, not necessarily byte-exact compressed transfer size.

Catalog entries: [EPA/Ecoregions/2013/L3](https://developers.google.com/earth-engine/datasets/catalog/EPA_Ecoregions_2013_L3).

Primary sources:

- [1](https://www.epa.gov/eco-research/level-iii-and-iv-ecoregions-continental-united-states) — EPA Level III shapefile format, with/without state-boundary package sizes and scope
- [2](https://developers.google.com/earth-engine/datasets/catalog/EPA_Ecoregions_2013_L3) — GEE 2013 Level III collection identity

<a id="dataset-19"></a>
### 19. USGS GAP CONUS 2011

**Catalog:** Official. **Citation count:** 2,589.

**Scope:** Exact size-bearing source package: USGS GAP/LANDFIRE National Terrestrial Ecosystems 2011 CONUS package (GAP/LANDFIRE 2011 raster; 30 m, 2011 imagery basis). This is GAP, not an NLCD volume.

**Download amount:** 1,998,043,721 bytes (1.998 GB decimal) (`measured`).

**Evidence:** Exact producer item-file size from the public ScienceBase item metadata JSON; only the metadata response was retrieved (24,144 bytes). The archive body was not downloaded.

**Source formats:** ZIP containing 30 m raster and ancillary files; inner raster encoding unverified.

**Desired formats:** COG. A categorical 30 m national raster is suited to tiled COG access; retain GAP class codes, native grid, masks and metadata.

**Existing access:** GEE image asset; USGS offers land-cover downloads by CONUS, state and LCC. No cloud-native download archive verified.

- The size covers the CONUS GAP/LANDFIRE 2011 package only, not state or LCC subsets and not NLCD as a separate product.
- The package is a ZIP containing the raster and associated files; the package byte count is compressed transfer size and does not describe uncompressed raster size.
- The public item metadata identifies the ZIP but not its inner raster encoding. A proposed direct-file metadata read was rejected by automatic approval review; the retained safe catalog metadata was sufficient for the size claim.

Catalog entries: [USGS/GAP/CONUS/2011](https://developers.google.com/earth-engine/datasets/catalog/USGS_GAP_CONUS_2011).

Primary sources:

- [1](https://www.usgs.gov/programs/gap-analysis-project/science/land-cover-data-download) — GAP/LANDFIRE 2011 download choices and 2011 CONUS imagery scope
- [2](https://www.usgs.gov/programs/gap-analysis-project/science/land-cover-data-overview) — 30 m raster resolution and download by state, territory or LCC
- [3](https://developers.google.com/earth-engine/datasets/catalog/USGS_GAP_CONUS_2011) — GEE GAP CONUS 2011 product identity
- [4](https://catalog.data.gov/dataset/gap-landfire-national-terrestrial-ecosystems-2011) — USGS original metadata and dataset landing page; raster dimensions/scope and landing page, but no byte-size field
- [5](https://www.sciencebase.gov/catalog/item/573cc51be4b0dae0d5e4b0c5?format=json) — USGS ScienceBase item metadata names gap_landfire_nationalterrestrialecosystems2011.zip with exact size 1,998,043,721 bytes

<a id="dataset-20"></a>
### 20. MODIS GPP/NPP

**Catalog:** Official. **Citation count:** 2,477.

**Scope:** MODIS/061 Terra MOD17A3HGF (gap-filled annual NPP with annual GPP output), complete global annual year 2024 across 290 unique CMR HDF granules, including science and QA layers. Other 8-day GPP and Aqua siblings are excluded.

**Download amount:** Approximately 2,044.36 MB (NASA CMR-reported granule-size sum) (`publisher_stated`).

**Evidence:** Summed CMR UMM DataGranule.ArchiveAndDistributionInformation Size values for all 290 unique global 2024 granules. CMR reports size unit MB; unit retained without converting to bytes or assuming decimal vs binary. Parent evidence contains three complete CMR pages and a size summary in evidence-parent/mod17-2024-*.json and mod17-2024-size-summary.json.

**Source formats:** HDF-EOS2/HDF4 .hdf granules.

**Desired formats:** COG; Zarr. COG can serve individual spatial composites; Zarr suits multi-year 8-day and annual product time axes. Preserve GPP/NPP units, QA, scale factors, projection and fill values.

**Existing access:** LP DAAC public granules are listed in CMR and LP DAAC data cloud; no maintained cloud-native analytical array distribution verified.

- This is one full annual Terra product/version/year, not the summed volume of all MOD17 products. MOD17A2H/HGF are separate 8-day GPP products; Aqua MYD17 products are separate.
- CMR lists granule sizes in MB; unit retained and no exact-byte conversion inferred.
- Preserve NPP and annual GPP science layers, QA, fill values, scale factors and native sinusoidal tiling.

Catalog entries: [MODIS/061/MOD17A2H](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD17A2H); [MODIS/061/MOD17A2HGF](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD17A2HGF); [MODIS/061/MOD17A3HGF](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD17A3HGF); [MODIS/061/MYD17A2H](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD17A2H); [MODIS/061/MYD17A3HGF](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD17A3HGF); [MODIS/006/MOD17A2H](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD17A2H); [MODIS/006/MOD17A3H](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD17A3H); [MODIS/006/MOD17A3HGF](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD17A3HGF); [MODIS/006/MYD17A2H](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MYD17A2H); [MODIS/006/MYD17A3H](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MYD17A3H); [MODIS/006/MYD17A3HGF](https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MYD17A3HGF).

Primary sources:

- [1](https://cmr.earthdata.nasa.gov/search/collections.umm_json?short_name=MOD17A3HGF&version=061&page_size=5) — Current LP DAAC MOD17A3HGF.061 collection metadata and native HDF-EOS2 collection format
- [2](https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=C2565791034-LPCLOUD&temporal=2024-01-01T00%3A00%3A00Z%2C2024-12-31T23%3A59%3A59Z&page_size=100&page_num=1) — First 100 of 290 unique global MOD17A3HGF.061 2024 granule metadata records and size fields
- [3](https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=C2565791034-LPCLOUD&temporal=2024-01-01T00%3A00%3A00Z%2C2024-12-31T23%3A59%3A59Z&page_size=100&page_num=2) — Second 100 granules in the complete 2024 size aggregation
- [4](https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=C2565791034-LPCLOUD&temporal=2024-01-01T00%3A00%3A00Z%2C2024-12-31T23%3A59%3A59Z&page_size=100&page_num=3) — Final 90 granules in the complete 2024 size aggregation
- [5](https://lpdaac.usgs.gov/documents/972/MOD17_User_Guide_V61.pdf) — Current V6.1 MOD17 HDF-EOS2 format, annual science layers and QA fields

<a id="dataset-21"></a>
### 21. Free-flowing rivers

**Catalog:** Official. **Citation count:** 2,473.

**Scope:** Global free-flowing river network and attributes in the author-released file-geodatabase ZIP; technicalPDF excluded from primary download size.

**Download amount:** 954,710,486 bytes (954.71 MB), geodatabase ZIP (`measured`).

**Evidence:** Exact Figshare articleAPI file.size; archive body not downloaded. Technical documentation PDF is1,383,410 bytes separately.

**Source formats:** File geodatabase in ZIP; Technical documentation PDF (separate).

**Desired formats:** GeoParquet; PMTiles (optional display derivative). River reaches are vector lines with reach-level pressure indicators, connectivity status, and other attributes. GeoParquet supports analytical scans and attribute access; PMTiles can serve a display copy while preserving the full-resolution source geometry separately.

**Existing access:** Not checked beyond the linked figshare ZIP; no maintained cloud-native distribution verified.

- Released network does not include every licensed dam input needed to recompute the study.

Catalog entries: [WWF/HydroSHEDS/v1/FreeFlowingRivers](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers).

Primary sources:

- [1](https://api.figshare.com/v2/articles/7688801) — Exact file names and sizes:954,710,486-byte geodatabase ZIP;1,383,410-byte PDF.
- [2](https://doi.org/10.6084/m9.figshare.7688801) — Producer/author figshare record, publication identity, and Download all 911.8 MB publisher-stated size.
- [3](https://www.nature.com/articles/s41586-019-1111-9) — Paper data availability, linked dataset contents, CC-BY-4.0 license, and excluded licensed dam inputs.
- [4](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers) — Official GEE catalog membership and hosted vector dataset identity.

<a id="dataset-22"></a>
### 22. RESOLVE Ecoregions 2017

**Catalog:** Official. **Citation count:** 2,459.

**Scope:** The global 2017 RESOLVE terrestrial ecoregion boundaries and associated attributes (846 ecoregions), matching the GEE catalog entry.

**Download amount:** 150 MB ZIP (`publisher_stated`).

**Evidence:** The producer site labels the download ‘Shapefile (150mb zip)’. Exact bytes are not exposed; publisher unit is preserved.

**Source formats:** Shapefile in ZIP archive; Earth Engine FeatureCollection.

**Desired formats:** GeoParquet; PMTiles (optional display derivative). This is a static polygon layer with stable attributes. GeoParquet offers interoperable analytical vector storage; PMTiles can provide an independently generated web-display derivative.

**Existing access:** Earth Engine FeatureCollection exists; no public cloud object distribution in a columnar vector format was verified.

- Some complex ecoregion geometries are split into multiple features in the catalog representation; preserve ECO_ID when exporting or converting.

Catalog entries: [RESOLVE/ECOREGIONS/2017](https://developers.google.com/earth-engine/datasets/catalog/RESOLVE_ECOREGIONS_2017).

Primary sources:

- [1](https://ecoregions.world/) — Producer-hosted shapefile ZIP format and stated 150 MB download size.
- [2](https://developers.google.com/earth-engine/datasets/catalog/RESOLVE_ECOREGIONS_2017) — Official GEE dataset identity, global 846-ecoregion coverage, and feature representation.

<a id="dataset-23"></a>
### 23. HydroSHEDS

**Catalog:** Official. **Citation count:** 2,411.

**Scope:** The rank group spans multiple HydroSHEDS v1 products: 3/15/30-arc-second DEM, drainage-direction and flow-accumulation rasters, plus HydroBASINS nested vector basin levels. For a defensible size example, this row sizes only the six continental 3-arc-second hydrologically conditioned DEM ZIPs (v1.1). This does not size the full group.

**Download amount:** 16,460 MB (sum of six continental 3-arc-second conditioned-DEM publisher figures; not the family total) (`bounded_estimate`).

**Evidence:** Arithmetic sum of six rounded file-size values published in the HydroSHEDS download table: 3156+4555+1458+2286+2705+2300=16460 MB. Because the source rounds sizes and does not clarify decimal/binary MB, no byte conversion is asserted. This is one raster product only; HydroBASINS and other resolutions/layers are excluded.

**Source formats:** GeoTIFF rasters (HydroSHEDS v1.1 core downloads); Shapefile vectors (HydroBASINS levels; continent packages).

**Desired formats:** COG for each raster layer/tile; GeoParquet for HydroBASINS vector layers; PMTiles (optional basin display derivative). Keep each native resolution, layer, projection, coding, and nodata semantics explicit. COG supports range-based raster access; GeoParquet preserves basin geometries and attributes for analytical access.

**Existing access:** No maintained cloud-native distribution verified. Official publisher downloads are tiled GeoTIFF and shapefile products.

- The rank group contains 21 distinct catalog assets and is not one archive or one dataset identity.
- The selected 3s conditioned DEM is listed only by continent; no global single-file download is listed. HydroBASINS has 12 nested levels and continental packages; its download page does not state their sizes.
- The publisher download page is for v1.1, while the GEE rank group includes named v1 core layers and basin assets; do not treat v1.1 file figures as the measured size of every GEE asset.

Other explicitly scoped amounts:

- 1,048 MB — HydroSHEDS void-filled DEM, global 15-arc-second download, v1.1 Official download table states Global 15s 1048MB; not additive to the selected 3s conditioned DEM and not a family total.

Catalog entries: [WWF/HydroSHEDS/03CONDEM](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_03CONDEM); [WWF/HydroSHEDS/03DIR](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_03DIR); [WWF/HydroSHEDS/03VFDEM](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_03VFDEM); [WWF/HydroSHEDS/15ACC](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_15ACC); [WWF/HydroSHEDS/15CONDEM](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_15CONDEM); [WWF/HydroSHEDS/15DIR](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_15DIR); [WWF/HydroSHEDS/30ACC](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_30ACC); [WWF/HydroSHEDS/30CONDEM](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_30CONDEM); [WWF/HydroSHEDS/30DIR](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_30DIR); [WWF/HydroSHEDS/v1/Basins/hybas_1](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_1); [WWF/HydroSHEDS/v1/Basins/hybas_10](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_10); [WWF/HydroSHEDS/v1/Basins/hybas_11](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_11); [WWF/HydroSHEDS/v1/Basins/hybas_12](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_12); [WWF/HydroSHEDS/v1/Basins/hybas_2](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_2); [WWF/HydroSHEDS/v1/Basins/hybas_3](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_3); [WWF/HydroSHEDS/v1/Basins/hybas_4](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_4); [WWF/HydroSHEDS/v1/Basins/hybas_5](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_5); [WWF/HydroSHEDS/v1/Basins/hybas_6](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_6); [WWF/HydroSHEDS/v1/Basins/hybas_7](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_7); [WWF/HydroSHEDS/v1/Basins/hybas_8](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_8); [WWF/HydroSHEDS/v1/Basins/hybas_9](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_9).

Primary sources:

- [1](https://www.hydrosheds.org/hydrosheds-core-downloads) — v1.1 core raster formats, resolutions, continental conditioned-DEM sizes, and global 15s void-filled DEM size.
- [2](https://www.hydrosheds.org/products/hydrobasins) — HydroBASINS vector polygons, 12 levels, shapefile continental packages, and product scope.
- [3](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_03CONDEM) — Official GEE rank-group representative conditioned DEM identity.

<a id="dataset-24"></a>
### 24. SoilGrids 2.0

**Catalog:** Community. **Citation count:** 2,383.

**Scope:** The community catalog page is a SoilGrids 250 m v2.0 overview, not a bulk-density-only dataset: it enumerates 11 soil properties. For the rank's title-specific measure, selected scope is bdod_mean, bulk density of fine earth at six standard depths. The wider SoilGrids property family is not sized as one archive.

**Download amount:** Unknown (`unknown`).

**Evidence:** ISRIC WebDAV exposes public per-tile GeoTIFF listings and one VRT per map, but no aggregate byte total for all tiles covering the global bdod_mean six-depth set. A complete global map needs hundreds of tile objects; VRT descriptor sizes are not map payload size. No data body was downloaded.

**Source formats:** Tiled GeoTIFF maps per property/depth/statistic; Global virtual-mosaic VRT descriptors; Earth Engine image assets for mean layers (six depth bands).

**Desired formats:** COG (one band per depth, with explicit units and nodata); Zarr (optional grouped property/depth/quantile cube if multiple SoilGrids properties are published together). Soil variables are static gridded predictions and are natural raster COGs. A multi-property Zarr grouping could serve repeated depth/property analysis, provided all prediction and uncertainty layers, scale factors, units and native 250 m grid are preserved.

**Existing access:** ISRIC WMS/WCS endpoint and WebDAV VRT mosaics exist; VRTs point to public tiled files rather than consolidating the map payload. Earth Engine assets exist for cataloged mean properties.

- The community page title begins ‘Bulk density’ but its full page enumerates bdod plus cec, cfvo, clay, nitrogen, phh2o, sand, silt, soc, ocd and ocs mean layers; this row captures that broader membership while selecting bdod for size scope.
- The ISRIC directory lists six depth intervals and mean, quantile and uncertainty variants. This selected scope is bdod mean at all six depths only; VRT/overview file size must not be mistaken for raster payload size.

Catalog entries: [isric](https://gee-community-catalog.org/projects/isric).

Primary sources:

- [1](https://gee-community-catalog.org/projects/isric/) — Full community catalog overview: all listed properties and associated SoilGrids 2.0 Earth Engine assets.
- [2](https://maps.isric.org/soilgrids.html) — ISRIC producer property menu, including separate bulk density and other SoilGrids property services.
- [3](https://maps.isric.org/generated/soilgrids/bdod.html) — ISRIC bdod mapfile, WMS/WCS access, and bulk-density layer identity.
- [4](https://docs.isric.org/globaldata/soilgrids/index.html) — Producer documentation that SoilGrids outputs global six-depth 250 m property maps and WebDAV provides complete global maps as VRT mosaics.
- [5](https://files.isric.org/soilgrids/latest/data/bdod/) — Public producer directory lists per-depth/statistic VRT descriptors and tile folders for bdod.
- [6](https://files.isric.org/soilgrids/latest/data/bdod/bdod_0-5cm_mean/tileSG-000-019/) — Public producer tile listing confirms GeoTIFF tile format and size of an individual component tile; not used as a whole-map estimate.

<a id="dataset-25"></a>
### 25. gridMET

**Catalog:** Official. **Citation count:** 1,948.

**Scope:** Two distinct datasets in the cited rank group: (1) the primary NCAR GDEX bulk distribution for daily CONUS gridMET, 1979–2025, ten listed variables in NetCDF4; (2) separate 5-day GRIDMET DROUGHT indices from 1980 to present. The publisher total below applies only to the complete NCAR base gridMET distribution, not the current 16-band GEE collection or the drought product.

**Download amount:** 79.53 GB (`publisher_stated`).

**Evidence:** NCAR GDEX dataset d761426 reports Total Volume 79.53 GB and format netCDF4. This covers that archived 10-variable distribution only; it excludes GRIDMET DROUGHT and does not cover later GEE dates/bands.

**Source formats:** NetCDF-4 daily GRIDMET variable files; GRIDMET DROUGHT Earth Engine ImageCollection (standalone native file format not specified by checked producer page); NetCDF/OPeNDAP and Zarr access options for GRIDMET.

**Desired formats:** Zarr for multidimensional time series, separately for GRIDMET variables and drought indices; COG for explicitly requested one-date raster extracts. Daily and 5-day spatial series are multidimensional in time and variable, well suited to chunked Zarr; standalone date extracts can be COG while preserving native grid and scale/offset metadata.

**Existing access:** GRIDMET is accessible from an aggregated THREDDS/OPeNDAP catalog and a USGS Geo Data Portal Zarr API; the latter is a cloud-native access path for GRIDMET. No equivalent cloud-native distribution verified for GRIDMET DROUGHT.

- NCAR GDEX dataset d761426 is an archived 1979–2025 distribution listing ten variables (including biomass burning and wildland fuels). GEE's current daily collection lists 16 bands and extends through 2026-10-26, so its total is not represented by 79.53 GB.
- GRIDMET DROUGHT is a separate 5-day derived product with SPI/EDDI/SPEI scales and PDSI/Z; it is excluded from NCAR d761426's 79.53 GB.
- NETCDF4 files use scale_factor and offset; preserve those attributes.

Other explicitly scoped amounts:

- Unknown — Current GEE IDAHO_EPSCOR/GRIDMET collection, 1979 to 2026-10-26, 16 bands GEE catalog lists 16 bands, while NCAR GDEX d761426 metadata lists ten variables through 2025-12-31; no matching current full-manifest size was found.
- Unknown — Separate GRIDMET/DROUGHT 5-day index collection, 1980 to 2026-10-22 GEE catalog identifies separate drought indices and cadence; GDEX d761426 is the base meteorology distribution and excludes this derived product.

Catalog entries: [GRIDMET/DROUGHT](https://developers.google.com/earth-engine/datasets/catalog/GRIDMET_DROUGHT); [IDAHO_EPSCOR/GRIDMET](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_GRIDMET).

Primary sources:

- [1](https://www.climatologylab.org/gridmet.html) — Publisher direct NetCDF, wget, THREDDS/OPeNDAP and USGS Zarr access; NETCDF4 encoding and scale/offset note.
- [2](https://gdex.ucar.edu/datasets/d761426/) — NCAR GDEX primary metadata: 1979–2025 coverage, ten listed variables, CONUS grid dimensions, netCDF4 format, and 79.53 GB Total Volume.
- [3](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_GRIDMET) — GRIDMET spatial extent, daily cadence, temporal coverage, and product description.
- [4](https://developers.google.com/earth-engine/datasets/catalog/GRIDMET_DROUGHT) — Separate drought-index product, 5-day cadence, available indices and time scales.

<a id="dataset-26"></a>
### 26. Global glacier elevation change

**Catalog:** Community. **Citation count:** 1,910.

**Scope:** The community GEE entry ingests only global elevation-change products, not every publication supplement. Size is for the author's publicly available elevation-change GeoTIFF raster bundle covering 5-, 10- and 20-year periods at 100 m; per-glacier/global tables and on-demand monthly elevation time series are excluded.

**Download amount:** Approximately 15 GB (`publisher_stated`).

**Evidence:** The lead author's GitHub README states elevation-change rasters (.tif) are approximately 15 GB. It separately lists public CSV products (~500 MB and ~3 GB) and monthly elevation time series (~3 TB, on demand); these are not added to this raster-only figure.

**Source formats:** GeoTIFF raster tiles (.tif); CSV tables and NetCDF monthly time series exist in the broader publication data release, but are outside the selected GEE product scope.

**Desired formats:** COG for the existing period-specific raster maps; Zarr for monthly NetCDF time series when distributed. Period-specific elevation change and uncertainty rasters fit COG. The monthly 100 m temporal stack is multidimensional and better served as chunked Zarr, while retaining original units, period definitions and uncertainty values.

**Existing access:** Theia/SEDOO provides bulk download and tile-oriented access; no cloud-native COG/Zarr object layout verified. The GEE community collection exposes image collections.

- Do not combine ~15 GB raster, ~3.5 GB public CSV tables, ~3 TB on-demand monthly series, and ~10 TB on-demand bias-corrected DEMs into one size claim.
- Theia product tiles cover 1° x 1°; author README uses approximate size and does not specify decimal/binary GB.
- Theia documents periods 2000–2004, 2005–2009, 2010–2014, 2015–2019, 2000–2009, 2010–2019, and 2000–2019; retain both elevation-change and uncertainty layers.

Other explicitly scoped amounts:

- ~500 MB + ~3 GB — Broader public CSV time-series tables at annual and period aggregation intervals; separate from the selected GEE raster product Author repository README provides approximate sizes; not included in the 15 GB raster claim.
- ~3 TB, on demand — 100 m monthly elevation time series; not included in publicly downloadable selected raster product Author repository README says available only on demand.

Catalog entries: [glacier](https://gee-community-catalog.org/projects/glacier).

Primary sources:

- [1](https://github.com/rhugonnet/ww_tvol_study) — Lead-author repository: public GeoTIFF raster family (~15 GB), separate public CSV tables, and on-demand NetCDF and raw DEM size/scope distinctions.
- [2](https://gee-community-catalog.org/projects/glacier/) — Community GEE entry's ingested scope, GeoTIFF raster format, 100 m tiles, time periods and uncertainty rasters.
- [3](https://www.theia-land.fr/en/blog/product/rate-of-glacier-elevation-changes-from-2000-to-2019/) — Producer service summary, Theia tile/period access, 100 m products and Hugonnet study provenance.
- [4](https://www.nature.com/articles/s41586-021-03436-z) — Publication data availability and 100 m 5-, 10- and 20-year elevation-change maps.

<a id="dataset-27"></a>
### 27. WHRC tropical biomass

**Catalog:** Official. **Citation count:** 1,788.

**Scope:** One static global/pantropical 500 m above-ground live woody biomass density image (2012-01-29), band Mg in megagrams per hectare, matching WHRC/biomass/tropical.

**Download amount:** Unknown (`unknown`).

**Evidence:** The official GEE catalog confirms one image, one band, 500 m pixels and units, but no public file manifest or downloadable byte total was found in the checked producer documentation.

**Source formats:** Earth Engine ee.Image hosted asset; standalone producer download format not documented in the checked source.

**Desired formats:** COG. This is a single spatial biomass raster; COG provides ranged reads while preserving biomass values, units and spatial grid. Do not infer size from the 500 m pixel size alone.

**Existing access:** Google Earth Engine hosted image is verified; no COG/COG-hosted source distribution verified.

- Static 2012 snapshot, not a time series.
- Catalog use terms state scientific, conservation and educational use; verify licensing/redistribution before mirroring.

Catalog entries: [WHRC/biomass/tropical](https://developers.google.com/earth-engine/datasets/catalog/WHRC_biomass_tropical).

Primary sources:

- [1](https://developers.google.com/earth-engine/datasets/catalog/WHRC_biomass_tropical) — Official catalog image identity, 500 m resolution, date, band and units; no standalone file-size manifest.
- [2](https://doi.org/10.1038/nclimate1354) — Associated publication and original biomass-density map context.

<a id="dataset-28"></a>
### 28. HydroLAKES

**Catalog:** Community. **Citation count:** 1,775.

**Scope:** Global polygons and all attributes for 1,427,688 lakes/reservoirs, using the HydroLAKES v1.0 shapefile download. The community GEE entry also exposes a separate point layer, not included in this polygon size.

**Download amount:** 820 MB ZIP (`publisher_stated`).

**Evidence:** HydroSHEDS producer page states lake polygons in shapefile format are 820 MB. This is not the geodatabase package, pour-point layer, or both-layer total.

**Source formats:** Shapefile in ZIP archive (polygon layer); File geodatabase in ZIP archive (polygon layer); Earth Engine FeatureCollection.

**Desired formats:** GeoParquet; PMTiles (optional display derivative). Lake boundaries and descriptive attributes are vector data. GeoParquet suits analytical joins/filtering and PMTiles can serve visualization while keeping the full polygons and attributes in the analytical release.

**Existing access:** Earth Engine FeatureCollections for lake polygons and points are verified; no public cloud object distribution in a columnar vector format was verified.

- Four distinct producer downloads exist: polygon/point crossed with shapefile/geodatabase; never conflate their sizes.
- HydroLAKES v1 includes lakes >=10 ha and about 1.4 million lakes/reservoirs; community catalog exposes both polygon and point collections.

Other explicitly scoped amounts:

- 763 MB ZIP — Same global HydroLAKES v1 polygon data and attributes in geodatabase format HydroSHEDS producer page lists separate geodatabase polygon package.
- 79 MB ZIP shapefile; 81 MB ZIP geodatabase — Separate global lake pour-point layer HydroSHEDS producer page lists pour points separately; not included in selected polygon size.

Catalog entries: [hydrolakes](https://gee-community-catalog.org/projects/hydrolakes).

Primary sources:

- [1](https://www.hydrosheds.org/products/hydrolakes) — Producer-published v1 polygon and point distribution formats and sizes.
- [2](https://gee-community-catalog.org/projects/hydrolakes/) — Community GEE membership, separate polygon/point layers and 1,427,688 feature scope.
- [3](https://data.hydrosheds.org/file/technical-documentation/HydroLAKES_TechDoc_v10.pdf) — HydroLAKES v1 technical documentation and shapefile composition.

<a id="dataset-29"></a>
### 29. MapBiomas

**Catalog:** Both. **Citation count:** 1,727.

**Scope:** The community entry is a multi-country, multi-product family and explicitly expands beyond Brazil to Pan-Amazonia, Indonesia, Bolivia, Peru and other regions. Size scope is narrowed to MapBiomas Brazil Collection 9 annual land-cover maps, 1985–2023; no full family total. The separate official GEE Brazil V1 collection is a different catalog asset/vintage (1985–2024), not the same dataset as Collection 9.

**Download amount:** Unknown (`unknown`).

**Evidence:** MapBiomas provides no complete Collection 9 byte manifest on checked producer pages; its current full-map GeoTIFF download function is temporarily suspended. Its toolkit exports clips through GEE, which does not provide a producer size for the global annual Collection 9 maps.

**Source formats:** GeoTIFF for pixel classification maps, including producer-generated regional/geometry subsets; CSV or Excel for area statistics; Earth Engine ImageCollections / publisher assets.

**Desired formats:** COG for annual categorical map rasters; Zarr only for explicitly packaged multi-year categorical time stacks, preserving class codes and year coordinate. Annual land-cover classifications are categorical raster maps and fit COG. Zarr is an optional temporal stack for multi-year operations; preserve integer class values, legend version, year, region, scale and nodata exactly.

**Existing access:** Community/official Earth Engine assets exist; producer's current toolkit exports clipped GeoTIFF through GEE. No public cloud-native COG/Zarr Collection 9 distribution verified.

- Community page's inline example is Collection 8 and its changelog says catalog links updated to v8; it describes a broad family, not a current Collection 9-only raster identity.
- The producer FAQ states Collection 9 covers 1985–2023 and Collection 10 (released 2025) covers 1985–2024. The current Brazil export toolkit lists Collection 11, while the full-map GeoTIFF function is temporarily suspended.
- Official Earth Engine projects/mapbiomas-public/assets/brazil/lulc/v1 is distinct and cataloged for 1985–2024; do not use its coverage or version to label Collection 9 or vice versa.

Catalog entries: [mapbiomas](https://gee-community-catalog.org/projects/mapbiomas); [projects/mapbiomas-public/assets/brazil/lulc/v1](https://developers.google.com/earth-engine/datasets/catalog/projects_mapbiomas-public_assets_brazil_lulc_v1).

Primary sources:

- [1](https://gee-community-catalog.org/projects/mapbiomas/) — Community family includes Brazil plus multiple regions, multi-raster scope, and stale Collection 8 code/changelog.
- [2](https://brasil.mapbiomas.org/downloads/) — Producer lists annual GeoTIFF downloads, GEE assets, clipped exports and statistics resources; linked full-map page is stale/404.
- [3](https://brasil.mapbiomas.org/downloads/baixe-mapas-recortados-geotiff-via-google-earth-engine/) — Producer says full-map downloads are temporarily suspended and its clipped export toolkit requires GEE; current toolkit lists Collection 11 and historical collections.
- [4](https://brasil.mapbiomas.org/faq/?tema=dados) — Producer-published Collection 9 1985–2023 and Collection 10 1985–2024 version coverage; GeoTIFF/CSV/Excel formats.
- [5](https://developers.google.com/earth-engine/datasets/catalog/projects_mapbiomas-public_assets_brazil_lulc_v1) — Separate official Brazil V1 ImageCollection identity and 1985–2024 coverage.

<a id="dataset-30"></a>
### 30. MERIT DEM

**Catalog:** Official. **Citation count:** 1,582.

**Scope:** One static global land elevation product at 3-arc-second (~90 m) resolution, covering 60°S–90°N, in the official Earth Engine catalog. Producer files are 5° x 5° GeoTIFF tiles bundled into 30° x 30° TAR packages.

**Download amount:** Unknown (`unknown`).

**Evidence:** The producer documents tile/package format and says a password is issued after registration, but no public file-size manifest was found without following the registration-gated download. No account was created and no data files were fetched.

**Source formats:** Float32 GeoTIFF tiles (.tif); TAR bundles of tiles; Earth Engine ee.Image hosted asset.

**Desired formats:** COG tiles (Float32). A static elevation surface is suited to tiled COG range access. Preserve EGM96-referenced elevation, original grid alignment, NoData and license metadata.

**Existing access:** Earth Engine hosted image is verified; no public open cloud COG tile distribution verified. Producer download is tiled GeoTIFF/TAR and requires registration-issued password.

- The producer page states access password is issued by email after registration; registration was not attempted.
- The calculated 311.04 GB is an uncompressed rectangular grid envelope with ocean/NoData slots, not an observed download total.
- Official catalog specifies approximately 92.77 m pixels in the dataset metadata and extent -60,-180,90,180; geographic resolution is 3 arc-seconds (~90 m at equator).
- Producer explicitly requires written permission to redistribute the complete original dataset on another website. Desired COG is a technical target; a public mirror needs a separate rights review.

Other explicitly scoped amounts:

- 311.04 GB uncompressed rectangular-grid payload (calculated upper envelope; not download size) — Rectangular 3-arc-second grid envelope covering 360° longitude by 150° latitude, one Float32 elevation value per cell, before NoData omission, headers, tiling or compression 432,000 longitude cells (360×1,200) × 180,000 latitude cells (150×1,200) × 4 bytes/Float32 = 311,040,000,000 bytes = 311.04 decimal GB. This is a rectangular payload calculation, not a measured archive or the sum of land-only tiles.

Catalog entries: [MERIT/DEM/v1_0_3](https://developers.google.com/earth-engine/datasets/catalog/MERIT_DEM_v1_0_3).

Primary sources:

- [1](https://global-hydrodynamics.github.io/MERIT_DEM/) — Producer documentation of v1.0.3, Float32 GeoTIFF 5° tiles, 30° TAR packages, and registration/password-gated access.
- [2](https://developers.google.com/earth-engine/datasets/catalog/MERIT_DEM_v1_0_3) — Official GEE asset scope, 3-arc-second resolution, pixel size, band and geographic extent.

## Reproduce and review

The three review shards retain initial source assessments; `parent-corrections.json` applies the final review. `evidence-*` holds metadata receipts and research notes. `review-findings.json` preserves failed checks and unresolved questions. `inventory.json` and `top30.csv` contain all 30 rows.

```sh
python3 scripts/report_download_audit.py --check
```

This command uses only committed files and the Python standard library. It performs no network requests. To refresh sizes, start a new dated study, retrieve producer metadata again, review scope and units, then regenerate; do not overwrite this snapshot.

Format references: [COG](https://guide.cloudnativegeo.org/cloud-optimized-geotiffs/intro.html), [Zarr](https://guide.cloudnativegeo.org/zarr/intro.html), [GeoParquet](https://geoparquet.org/), [PMTiles](https://docs.protomaps.com/pmtiles/). PMTiles is an optional display derivative; analytic geometry and attributes remain in GeoParquet.

No dataset bodies, GEE exports, conversions, uploads or registry submissions were performed. A separate rights and exact-version review precedes publication.
