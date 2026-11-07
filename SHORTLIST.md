# Dataset availability shortlist

Generated from canonical dataset records. Unknown size is not zero. Counts use distinct distribution services, not URLs. Older versions count toward total locations but not matching-scope locations. Documentation and request forms do not prove hosting. Prepared local output is not a public distribution host. Counts reflect the reviewed sources, not an exhaustive inventory; zero GEE matches means none identified. Sizes use decimal MB/GB except an explicitly retained producer label.

| Rank | Dataset | Current work | Scope | Source download | Prepared analytic | Prepared display | External services (matching) | GEE services (matching) | GEE assets |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | **LakeATLAS v1.0** | hosted verified pending catalog deployment | Global lake polygons AND pour points with all producer attributes; selected FileGDB representation. | 1.53 GB | 1.43 GB | 0 MB | 1 (1) | 1 (1) | 2 |
| 2 | **Free-Flowing Rivers 2019 v1** | hosted verified pending catalog deployment | Complete global reach-level connectivity and pressure assessment; original FileGDB ZIP. | 954.71 MB | 887.13 MB | 0 MB | 1 (1) | 1 (1) | 1 |
| 3 | **TerraClimate v1.1 baseline** | defer | Monthly historical baseline 1950–2025, 14 variables × 76 annual files; excludes climate-change scenarios and climatologies. | ~115.51 GB | Unknown | Unknown | 2 (1) | 1 (0) | 1 |
| 4 | **CRU-TS v4.10** | pending | Ten monthly variables over global land excluding Antarctica, 1901–2025; one full-period NetCDF.gz per variable, excluding duplicate decades and ASCII files. | 3.65 GB | Unknown | Unknown | 3 (1) | 0 (0) | 0 |
| 5 | **RiverATLAS v1.0** | pending | Complete global enriched river-reach layer, original FileGDB ZIP; excludes BasinATLAS and LakeATLAS. | 2.33 GB (producer label; exact bytes unverified) | Unknown | Unknown | 1 (1) | 1 (1) | 1 |
| 6 | **HydroLAKES v1.0 polygons** | hosted verified pending catalog deployment | Complete global original lake polygon inventory only; excludes separate pour-point layer. | 820.3 MB | 949.6 MB | 0 MB | 1 (1) | 1 (1) | 1 |
| 7 | **GRWL summary V01.02** | withheld source geometry errors | Complete simplified global summary polyline product; excludes raw vectors, masks, tile index and basin supplement. | 43.28 MB | 46.3 MB | 86.55 MB | 1 (1) | 1 (0) | 1 |
| 8 | **Lebreton river-plastic inputs, Figshare v6** | hosted verified pending catalog deployment | 40,760 modeled river inputs, historical model baseline 2010; selected original shapefile ZIP. | 5.76 MB | 6.36 MB | 3.71 MB | 1 (1) | 1 (0) | 1 |
| 9 | **Global Dam Watch consensus v1.0** | blocked source access | Consensus v1.0 barrier points and reservoir polygons; excludes separate evolving intelligence products and the JRC v1_delta edition. | Unknown | Unknown | Unknown | 3 (1) | 1 (1) | 2 |
| 10 | **SWOT Prior Lake Database v2.03** | metadata qualified sample blocked by disk | Complete scientific PLD v2.03; excludes Light/Geometries variants and previous v2.02 tiles. | 29.99 GB | Unknown | Unknown | 1 (1) | 0 (0) | 0 |


### 1. LakeATLAS v1.0

**Scope:** Global lake polygons AND pour points with all producer attributes; selected FileGDB representation. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** FileGDB ZIP.

- External: [Figshare](<https://doi.org/10.6084/m9.figshare.19312001.v1>), [Figshare](<https://ndownloader.figshare.com/files/35959544>) — matching_scope; Producer landing page, DOI and repository/CDN download links identify one distribution service; they are not separate hosts.
- GEE: [GEE community](<https://gee-community-catalog.org/projects/hydroatlas/>) — matching_scope; 2 asset(s); Catalog-declared edition and scope; no new live GEE requests or full content comparison in this review.

Source size basis: validated_download. Exact selected archive size from the previously downloaded, checksum-validated source pin. Excludes optional formats, separate layers and documentation.


### 2. Free-Flowing Rivers 2019 v1

**Scope:** Complete global reach-level connectivity and pressure assessment; original FileGDB ZIP. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** FileGDB ZIP.

- External: [Figshare](<https://doi.org/10.6084/m9.figshare.7688801.v1>), [Figshare](<https://ndownloader.figshare.com/files/15090536>) — matching_scope; Producer landing page, DOI and repository/CDN download links identify one distribution service; they are not separate hosts.
- GEE: [GEE official](<https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers>) — matching_scope; 1 asset(s); Catalog-declared edition and scope; no new live GEE requests or full content comparison in this review.

Source size basis: validated_download. Exact selected archive size from the previously downloaded, checksum-validated source pin. Excludes optional formats, separate layers and documentation.


### 3. TerraClimate v1.1 baseline

**Scope:** Monthly historical baseline 1950–2025, 14 variables × 76 annual files; excludes climate-change scenarios and climatologies. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** NetCDF.

- External: [Producer / NKN THREDDS](<https://tds-proxy.nkn.uidaho.edu/thredds/catalog/TERRACLIMATE_ALL/data/catalog.xml>), [Producer / NKN THREDDS](<https://tds-proxy.nkn.uidaho.edu/thredds/terraclimate_catalog.html>) — matching_scope; HTTP files, OPeNDAP and NCSS are protocols of the same producer distribution; counted once.
- External: [Microsoft Planetary Computer](<https://planetarycomputer.microsoft.com/api/stac/v1/collections/terraclimate>) — other_version_or_subset; Collection metadata covers 1958–2021, not the full reprocessed 1950–2025 v1.1 scope. Arrays not read; do not infer exact source version from collection name.
- GEE: [GEE official](<https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE>) — other_version_or_subset; 1 asset(s); Catalog describes 1958 onward with CRU/JRA-55 lineage; it does not establish the new ERA5-based v1.1 baseline. Community 2C/4C scenarios are different products and excluded.

Source size basis: producer_listing. Sum of rounded producer THREDDS Mbytes values. One ws_2025 HEAD is 43,220,665 bytes against 43.22 Mbytes, supporting decimal MB interpretation. Total remains an estimate, not a full 1064-object HEAD inventory.


### 4. CRU-TS v4.10

**Scope:** Ten monthly variables over global land excluding Antarctica, 1901–2025; one full-period NetCDF.gz per variable, excluding duplicate decades and ASCII files. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** gzip-compressed NetCDF.

- External: [CRU / University of East Anglia](<https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/>), [CRU / University of East Anglia](<https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/cruts.2604091129.v4.10/>) — matching_scope; Current producer v4.10 full-period download. The producer Google Earth interface is a subset on this same service and is not Google Earth Engine.
- External: [CEDA Archive](<https://data.ceda.ac.uk/badc/cru/data/cru_ts/cru_ts_4.09/>), [CEDA Archive](<https://crudata.uea.ac.uk/cru/data/hrg/>) — other_version_or_subset; Producer identifies older CEDA releases; v4.10 CEDA link is not yet available on the current edition page. No exact v4.10 CEDA mirror established.
- External: [World Bank CCKP / AWS](<https://registry.opendata.aws/wbg-cckp/>), [World Bank CCKP / AWS](<https://worldbank.github.io/climateknowledgeportal/docs/collections/cru-x0.5.html>) — other_version_or_subset; World Bank documentation describes four selected variables from v4.07 through 2022 in public bucket wbg-cckp. Different version and scope; no complete bucket scan. No matching GEE entry identified in bounded sources.

Source size basis: http_head. Sum of Content-Length from ten successful application/x-gzip HEAD responses. No data bodies downloaded. Producer rounded Size(MB) labels sum differently; exact header bytes take precedence. NetCDF source files include station support; do not duplicate separate ASCII .stn files.


### 5. RiverATLAS v1.0

**Scope:** Complete global enriched river-reach layer, original FileGDB ZIP; excludes BasinATLAS and LakeATLAS. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** FileGDB ZIP.

- External: [Figshare](<https://www.hydrosheds.org/hydroatlas>), [Figshare](<https://figshare.com/ndownloader/files/20087321>) — matching_scope; HydroSHEDS links to Figshare; those pages and the CDN are one distribution service.
- GEE: [GEE community](<https://gee-community-catalog.org/projects/hydroatlas/>) — matching_scope; 1 asset(s); One RiverATLAS feature collection. The family catalog also has basin/lake layers, which are not counted here.

Source size basis: producer_listing. Producer labels the GDB ZIP 2.33 GB. Both download HEAD endpoints returned 403. Exact bytes and the producer display-unit convention remain unverified; do not silently interpret the label as measured decimal bytes. Shapefile alternative excluded.


### 6. HydroLAKES v1.0 polygons

**Scope:** Complete global original lake polygon inventory only; excludes separate pour-point layer. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** Shapefile ZIP.

- External: [HydroSHEDS download](<https://www.hydrosheds.org/products/hydrolakes>), [HydroSHEDS download](<https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip>) — matching_scope; Producer landing page, DOI and repository/CDN download links identify one distribution service; they are not separate hosts.
- GEE: [GEE community](<https://gee-community-catalog.org/projects/hydrolakes/>) — matching_scope; 1 asset(s); Catalog-declared edition and scope; no new live GEE requests or full content comparison in this review.

Source size basis: validated_download. Exact selected archive size from the previously downloaded, checksum-validated source pin. Excludes optional formats, separate layers and documentation.


### 7. GRWL summary V01.02

**Scope:** Complete simplified global summary polyline product; excludes raw vectors, masks, tile index and basin supplement. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** Shapefile ZIP.

- External: [Zenodo](<https://zenodo.org/records/18624542>), [Zenodo](<https://zenodo.org/api/records/18624542/files/GRWL_summaryStats_V01.02.zip/content>) — matching_scope; Producer landing page, DOI and repository/CDN download links identify one distribution service; they are not separate hosts.
- GEE: [GEE community](<https://gee-community-catalog.org/projects/grwl/>) — other_version_or_subset; 1 asset(s); GEE summary is V01.01; selected producer file and prepared release are V01.02. It is not an exact-edition counterpart.

Source size basis: validated_download. Exact selected archive size from the previously downloaded, checksum-validated source pin. Excludes optional formats, separate layers and documentation.


### 8. Lebreton river-plastic inputs, Figshare v6

**Scope:** 40,760 modeled river inputs, historical model baseline 2010; selected original shapefile ZIP. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** Shapefile ZIP.

- External: [Figshare](<https://doi.org/10.6084/m9.figshare.4725541.v6>), [Figshare](<https://ndownloader.figshare.com/files/7714864>) — matching_scope; Producer landing page, DOI and repository/CDN download links identify one distribution service; they are not separate hosts.
- GEE: [GEE community](<https://gee-community-catalog.org/projects/plastic/>) — edition_unverified; 1 asset(s); Catalog describes the same paper/model and 40,760 watersheds, but GEE does not declare an upstream Figshare version manifest. Do not label it verified v6 bytes.

Source size basis: validated_download. Exact selected archive size from the previously downloaded, checksum-validated source pin. Excludes optional formats, separate layers and documentation.


### 9. Global Dam Watch consensus v1.0

**Scope:** Consensus v1.0 barrier points and reservoir polygons; excludes separate evolving intelligence products and the JRC v1_delta edition. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** Shapefile ZIP.

- External: [Figshare](<https://doi.org/10.6084/m9.figshare.25988293.v1>), [Figshare](<https://www.globaldamwatch.org/database>) — matching_scope; Final v1.0 release, two alternative full-layer archive formats; CC BY 4.0 verified from producer-deposited DataCite metadata. Official acquisition is currently HTTP 403; producer form redirects to the same Figshare service.
- External: [European Commission JRC](<https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GDW/>), [European Commission JRC](<https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GDW/GDW_v1_delta_shp/>) — other_version_or_subset; Directory lists v1_delta, a different edition. It contributes to identified locations, not matching consensus v1.0 locations.
- External: [AquaScope / Hugging Face](<https://huggingface.co/datasets/Rekin226/aquascope-gauges/blob/main/context/dams/gdw_barriers.parquet>), [AquaScope / Hugging Face](<https://rachidouedraogo.com/aquascope/archive-layout/>) — other_version_or_subset; Actual footer: 41,145 rows, 16 selected columns, one row group, no geometry column or geo metadata. File is 1,514,458 bytes. Reservoir polygons are absent from this documented mirror; not the complete two-layer/full-attribute GDW scope.
- GEE: [GEE community](<https://gee-community-catalog.org/projects/gdw/>) — matching_scope; 2 asset(s); Two catalog-declared v1.0 feature collections, one GEE service. No new live GEE reads.

Source size basis: not_established. Selected final v1.0 Shapefile archive has a documented direct file URL, but HEAD/GET requests return 403. DataCite registers 127,938,795 bytes for the release containing two alternative ZIP formats; this is not the selected archive size. Exact selected bytes remain null.


### 10. SWOT Prior Lake Database v2.03

**Scope:** Complete scientific PLD v2.03; excludes Light/Geometries variants and previous v2.02 tiles. **Geography:** global. **Reviewed:** 2026-11-01. **Download format:** SQLite.

- External: [Hydroweb.next / CNES-THEIA](<https://hydroweb.next.theia-land.fr/api/catalog/stac/collections/SWOT_PRIOR_LAKE_DATABASE>), [Hydroweb.next / CNES-THEIA](<https://hydroweb.next.theia-land.fr/catalog/details/SWOT_PRIOR_LAKE_DATABASE>) — matching_scope; Live STAC metadata explicitly identifies 2.03 Sci and 61 edition-specific files. Provider-declared sizes/MD5s retained. Anonymous metadata and 16-byte source range reads work. Matching is edition/scope metadata, not full SQLite/table validation. Older HTML description is stale.

Source size basis: producer_listing. Exact sum of provider-declared file:size for 61 unique scientific v2.03 tile assets. Collection total 122 includes 61 older v2.02 assets, excluded. Data bytes/checksums are not globally verified. Anonymous 206 on the smallest tile confirms a SQLite header; full source inspection stopped before download because free space was below the recorded 40 GiB start threshold.
