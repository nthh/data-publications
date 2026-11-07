# CHIRPS reuse and publication priorities — 2026-10-30

Use WFP's existing CHIRPS v3 RNL publication for new daily-v3 access. Retain the pinned v2 pentad objects for the existing benchmark. Start our public-release work with HydroLAKES, then Free-Flowing Rivers. Treat existing maintained publications as registry references wherever they satisfy the required product and access pattern.

This follow-up reviews the combined citation top 30 and the Folia benchmark directories supplied by the user. It adds current hosting and local-readiness evidence without rewriting the frozen citation/download audit. The recommendations below are candidates for qualification, not claims that five new mirrors are necessary. No data bodies, private storage, GEE jobs, cloud compute, uploads or registry mutations were used in this review.

## Which CHIRPS?

| Property | Existing Folia benchmark | WFP Source Cooperative |
| --- | --- | --- |
| Identity | CHIRPS v2.0 global pentad | CHIRPS v3.0 daily, RNL disaggregation |
| Material actually checked | Six complete original COGs for August 2020, as recorded in local receipts | Public STAC metadata: all 31 August 2020 dates, 1981-01-01, latest returned 2026-09-30; October 1–30 query empty |
| Grid | Original 0.05° v2 pentad sources | STAC declares EPSG:4326, 2,400 × 7,200, 0.05°, 60°S–60°N |
| Hosting | Original CHC public URLs; later regional cohort used private whole-object mirrors | Existing public daily COGs and a STAC GeoParquet discovery index |
| Scientific meaning | Six pentad amounts summed for the August benchmark | ERA5 daily patterns divide each v3 pentad amount among its constituent days |
| Decision | Keep source hashes and historical checks unchanged | Reuse existing publication; give v3 daily RNL its own dataset identity and validation |

Sources: [WFP product and README](https://source.coop/wfp/chirps-rnl-daily), [live STAC collection](https://api.earthobservation.vam.wfp.org/stac/collections/chirps_rnl_daily), [CHC v3 overview](https://www.chc.ucsb.edu/data/chirps3), [CHC daily algorithm documentation](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt). Request URLs, response hashes and selected JSON metadata are retained in `evidence/`; local code/receipt identities are in `local-audit.json`.

WFP is sufficient as an existing distribution for daily v3 RNL. A second identical mirror would add little. For monthly or pentad rainfall analyses, prefer the corresponding producer temporal product when it meets the science need. Daily RNL is a temporal disaggregation, not an independently station-blended daily observation. CHC recommends pentad/monthly totals where appropriate; agreement with ERA5 is not independent validation. CHC plans to end v2 production after December 2026.

Three findings belong in any proposed registry entry:

- **Units conflict:** the README says precipitation in mm, while the collection and every sampled item's `raster:bands` say `unit: "1"`. Use producer-supported mm with an explicit metadata correction and retain the original metadata; do not silently interpret it as dimensionless.
- **Update-status conflict:** WFP advertises preliminary pentad updates for this RNL collection. CHC's current daily documentation says preliminary daily v3 uses the SAT variant. Sampled STAC items have no preliminary/final field. Resolve the status before claiming near-real-time coverage or final-only values.
- **Coverage is sampled, not certified:** the API returned all 31 August 2020 dates, an item on 1981-01-01, and no October 2026 items. It returned September 30 as the first item even for an ascending-sort request, so that request did not establish earliest coverage. A separate exact-date query established the 1981 sample. Full-history completeness, immutable object identity, actual raster values and COG conformance remain untested here.

The old benchmark establishes exact float32 agreement for four Bengaluru cells against an independent original-source oracle and GEE after casting GEE's float64 output. Its 2,799,347-byte figure is per-request range-read traffic, not the six-object archive size. None of that establishes equivalence between v2 and v3.

For a later v3 validation: pin a finite date range and object identities; compare selected WFP raster values/masks/grid to matching producer v3 RNL originals; verify daily sums against the matching v3 pentads; include ocean/nodata, wet/dry regions and dates around leap years and update boundaries. A matching GEE v3 comparison would be an additional cross-check. Temporal conservation checks product consistency, not independent daily rainfall accuracy. No new validation jobs were run for this recommendation.

## Five priorities for qualification and publication

All are global products or global terrestrial/glacier coverage. Counts below are associated-paper citations from the frozen 2026-10-30 OpenAlex study, not citations of the specific new versions or measures of dataset use. Order reflects readiness, incremental access value, utility and manageable work; it is not a citation-only ranking.

| Priority | Dataset | Catalog in prior audit | Paper citations | Input size and format | Desired access / reason |
| --- | --- | --- | ---: | --- | --- |
| 1 | [HydroLAKES v1 polygons](https://www.hydrosheds.org/products/hydrolakes) | Community | 1,775 | 820.30 MB Shapefile ZIP; **945.38 MB verified GeoParquet already built** | Prepare public GeoParquet release; optional PMTiles for display. Most ready. |
| 2 | [WWF Free-Flowing Rivers v1](https://doi.org/10.6084/m9.figshare.7688801) | Official | 2,473 | 954.71 MB FileGDB ZIP | GeoParquet + PMTiles; useful global river connectivity attributes. |
| 3 | [JRC GSW v1.5 Occurrence, 1984–2024](https://global-surface-water.appspot.com/download) | Official family | 5,374 | **14.45 GB**, 504 GeoTIFF tiles | Qualify existing tiles first; COG + STAC access. Current monthly-history mirror is a different product. |
| 4 | [TerraClimate v1.1 base, 1950–2025](https://www.climatologylab.org/terraclimate.html) | Both | 3,477 | About **116–121 GB**, 1,064 annual NetCDF files | Zarr for global monthly climate and water-balance queries; start with one full variable. |
| 5 | [Hugonnet global glacier change, 2000–2019](https://github.com/rhugonnet/ww_tvol_study) | Community | 1,910 | Approximately **15 GB** public GeoTIFF raster family | COG + STAC, keeping change and uncertainty together. Conditional on resolving exact release rights. |

Exact byte counts and scoped next steps are in `priorities.json`. MB/GB are decimal when calculated from bytes. TerraClimate's producer reports rounded Mbytes without a clear decimal/binary convention; the range preserves that ambiguity. Glacier size is the author's approximate figure. No output-size estimates are fabricated for unbuilt conversions.

**HydroLAKES:** local evidence identifies all **1,427,688 features**, complete unique IDs, preserved decoded geometry/typed attributes/nulls, 1,162 row groups, and a reopened output identity check. The source and output hashes match the privately staged release. This is substantial reusable work, but not a public Source Cooperative release or a Portolan registration. The output is sorted by `Hylak_id` and supports ID pruning; it does not provide bbox-only spatial pruning. Preserve it as the validated artifact; a spatially organized variant would be a separately checked derivative. Matching FRC11 GEE science remains pending. The next concrete task is to port the reusable acquisition/conversion/validation logic into the standalone dataset pattern and package this release.

**Free-Flowing Rivers:** the [author's Figshare record](https://api.figshare.com/v2/articles/7688801) supplies the 954,710,486-byte archive and CC-BY-4.0 term. Publish the released river network, preserving IDs, geometry and attributes. This does not include every licensed dam input required to recompute the research.

**JRC:** a fresh producer listing gives **14,453,956,859 bytes** for all 504 v1.5 Occurrence tiles. The earlier 15,972,544,704-byte total remains correct for v1.4; these are different releases. Producer notes describe corrected Occurrence calculations and a Landsat Collection 1/2 processing seam. The [existing Source Cooperative mirror](https://data.source.coop/epoch/jrc-global-surface-water-monthly/README.md) covers MonthlyHistory 2017–2024, not Occurrence. Its STAC index covers only its older 2017–2021 portion. Actual Occurrence COG layout was not checked. If current producer tiles already meet the access need, register them instead of converting or mirroring by default.

**TerraClimate:** current [OPeNDAP attributes](https://www.reacchpna.org/thredds/dodsC/TERRACLIMATE_ALL/data/TerraClimate_vap_1958.nc.html), also captured directly via `.das`, declare **V1.1**, **WorldClim v2.1 / ERA5** inputs and **CC0 1.0**. This resolves the earlier landing-page license uncertainty for that inspected file. Retain the declaration in the pinned source inventory. The producer warns against mixing v1.0 and v1.1. Preserve calendar, scale/offset, fill values, units and grid; warming/counterfactual scenarios are outside this scope.

**Glaciers:** the approximately 15 GB release is the public 100 m elevation-change raster family, not the separate multi-terabyte elevation/DEM archives. [Theia](https://www.theia-land.fr/en/blog/product/rate-of-glacier-elevation-changes-from-2000-to-2019/) documents 5-, 10- and 20-year intervals. Both change and uncertainty assets matter. Exact redistribution terms remain unresolved: the DOI's DataCite rights list is empty and the inspected publisher JSON-LD has no named license. Confirm the dataset term before publishing; the code's MIT license is not a data license.

## Existing publications to register first

- [WFP CHIRPS v3 RNL](https://source.coop/wfp/chirps-rnl-daily): daily COGs and STAC discovery. Resolve the metadata issues above; no duplicate mirror proposed.
- [SoilGrids v2.0](https://source.coop/chill/soilgrids): an existing Icechunk/Zarr publication covers mean estimates for ten depth-indexed properties plus organic carbon stock. It is not an uncertainty-quantile archive. Check the intended property/statistic and reader support, then reference the existing store.
- [Ecoregions 2017](https://source.coop/cboettig/ecoregion): existing GeoParquet and PMTiles cite **Dinerstein 2017, DOI 10.1093/biosci/bix014**, with Nature Needs Half attributes. This is likely the same RESOLVE lineage. The 847/846 count difference alone does not establish a different dataset; exact geometry/attribute equivalence remains unverified. It should not be treated as an unfilled format gap merely because the publisher calls it WWF.

No exact hosted matches surfaced in the targeted searches for the new candidates; that is not proof of absence. Registry entries can point to maintained third-party assets, with producer, publisher, product version and validation status kept explicit. Publication by Folia should be reserved for a useful maintained release we own, rather than an extra copy solely to obtain a Folia namespace.

HydroBASINS was considered but excluded from this immediate shortlist: its product page refers to the HydroSHEDS license, whose [Appendix A §2.1.2](https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf) restricts standalone distribution. A commercial-use headline is not sufficient evidence for unrestricted republication. WorldClim v1 also has version/terms questions. ERA5 and several other major archives already have public cloud-native representations; citations alone do not make them good conversion tasks.

## Evidence and repeatability

- `criteria.json`: ranking and verification scope committed before metadata synthesis.
- `local-audit.json`: file hashes and selected conclusions from the named Folia scripts and actual release receipts; private operational details are not copied into this public-ready report.
- `requests.json`, `evidence/`: bounded public metadata requests, timestamps, response hashes and selected fields. Hashes describe the received response; projected JSON is not the original wire encoding. HTML/text receipts retain URL/hash, with conclusions reviewed against linked primary documents.
- `priorities.json`: machine-readable scope, formats, citation provenance, actions and remaining checks.
- `input-manifest.json`, `validation.json`: offline evidence integrity and consistency checks.

Run the frozen checks from any checkout with Python 3.10+:

```sh
python3 research/chirps-priorities-20261030/audit.py --check
```

For a later authorized metadata refresh, use a new directory. This makes at most 20 public GETs, at most 2 MB per response, and no data-object requests. It never updates the frozen report or executes publication/conversion scripts:

```sh
python3 research/chirps-priorities-20261030/audit.py --fetch-dir /path/to/new-metadata-review
```

The offline checks verify saved evidence, date samples, identities, byte arithmetic and citation provenance. They do not rerun full conversion, prove full-archive completeness, establish COG conformance, or validate current remote availability. No publish or registry step has been performed by this follow-up.
