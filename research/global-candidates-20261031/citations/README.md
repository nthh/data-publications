# Citation-led global candidate review

This is a bounded discovery review of the first 50 global shared-paper groups in the frozen official Earth Engine plus community catalog ranking. It is not a universal top-cited geospatial dataset ranking. The exact group rows, order, IDs, titles, paper DOIs and citation counts are preserved in `selected-groups.json`; `reviewed.json` projects those 50 selection groups into 53 source-level candidate rows and retains each source entry reference and frozen evidence key. `supplemental-global.json` lists producer-backed global datasets outside that citation universe; citations/counts are null when no single stable paper/count is asserted.

## Frozen selection and identity

Input: `research/catalog-citations-20261030/groups-combined-active-global.json`, ordered by the frozen review. The first 50 groups are the selection. The input view is active-only and global; the extraction script asserts no deprecated official entry appears in the slice. Citation counts are not refreshed or blended. The frozen study defines the metric as the maximum OpenAlex cited-by count for associated dataset papers, never a sum. Count observation date is 2026-10-30.

A shared paper is only a candidate-discovery link. It does not make all referenced datasets equivalent. `family_identity_review`, per-entry `sources.relationship`, and `source_group_rank` preserve this distinction. Selected component/edition cases include ERA5 collections, WorldClim layers, MODIS VI/LST/MOD17 products, GLDAS models, HydroSHEDS components, GRACE variants, PML MODIS/VIIRS, Global Fishing Watch measures, and ALOS PALSAR thematic/backscatter assets. Canonical IDs are suggested only for likely same-family overlap, and explicitly do not assert release byte equivalence.

## Coverage and formats

Official Google Earth Engine entry bboxes are copied from the frozen `official-entries.json` into `reviewed.json` by `enrich_coverage.py`. The latitude interval is the union envelope of the selected official entries. Bboxes describe catalog extents; they do not prove valid data pixels everywhere, completeness, or wall-to-wall coverage. A global bbox can contain sparse features, thematic masks, swaths or no-data regions. Empty `observed_formats`, `unknown` hosting status and null license summaries mean the frozen citation records do not establish a separate native bulk format/host or legal terms. Confirm those against producer evidence before canonical promotion.

## Reproduce and check offline

From repository root, both default commands are nonmutating checks:

```sh
python3 research/global-candidates-20261031/citations/extract_frozen.py
python3 research/global-candidates-20261031/citations/enrich_coverage.py
```

`extract_frozen.py --check` compares `selected-groups.json` exactly to the first 50 frozen rows; `extract_frozen.py --write` refreshes only that selection file and never writes `reviewed.json`. `enrich_coverage.py --check` compares official catalog bboxes and derived latitude limits; its explicit `--write` option updates only source bbox, bbox evidence and latitude-limit fields. It does not regenerate candidates or replace hand-reviewed titles, geography, coverage notes or identity decisions. `reviewed.json` retains the exact paper group rank/count/DOI/work ID and frozen evidence key for each candidate. `check_review.py` is a read-only consistency check for exact group/source coverage, unique candidate IDs, preserved citations, direct community-ID-to-`audit.family_key` matches and the Free-Flowing Rivers DOI crosswalk. Run it with `python3 research/global-candidates-20261031/citations/check_review.py`.

The canonical crosswalk is built from actual community entry IDs and `datasets/*/dataset.yaml` `audit.family_key` values. Each shared paper group remains unchanged in `selected-groups.json`. Groups 14, 27 and 28 are split into per-source candidates with unique `suggested_id` evidence keys; TerraClimate +2C/+4C scenarios are separate from the historical baseline; the two Esri products and AI0/ET0 records remain independent. Official HydroSHEDS, MERIT, MODIS and related multi-component families retain component distinctions in the identity notes.

## Supplemental overlap and limits

Natural Earth, OpenStreetMap planet snapshots, Overture Maps, GBIF-mediated occurrence data, WorldPop Global2, GADM 4.1 and GEBCO_2026 are a small producer-backed addition. Overlap checks were read against current `datasets/*/dataset.yaml` records. Existing `worldpop` and `gebco` records overlap by family; WorldPop Global2 and GEBCO 2026 are newer editions, not asserted exact copies. `osm_water` is only one OSM thematic layer. No exact Natural Earth, full OSM planet, Overture, GBIF or GADM record was identified. Supplemental citation counts are deliberately null; producer DOI is recorded only for GEBCO_2026.

Primary-source identity and access checks used producer pages: Natural Earth [about](https://www.naturalearthdata.com/about/) and [data creation](https://www.naturalearthdata.com/about/data-creation/); OpenStreetMap Foundation [FAQ](https://osmfoundation.org/wiki/FAQ), [license FAQ](https://osmfoundation.org/wiki/Licence_and_Legal_FAQ), and [data access](https://osmfoundation.org/wiki/How_To_Get_OpenStreetMap_Data); Overture [cloud catalog docs](https://docs.overturemaps.org/getting-data/cloud-sources/); GBIF [citation guidelines](https://www.gbif.org/citation-guidelines) and [data use](https://www.gbif.org/data-use); WorldPop [global downloads](https://hub.worldpop.org/project/categories?id=3) and [FAQ](https://www.worldpop.org/faq/); GADM [version/access](https://www.gadm.org/version2) and [world download](https://www.gadm.org/download_world.html); GEBCO [2026 grid](https://www.gebco.net/data-products-gridded-bathymetry-data/gebco2026-grid).

No native datasets were downloaded, no live GEE request/export was made, no upload or paid request was made. This review does not verify current asset contents, licenses beyond producer declarations, COG/GeoParquet/Zarr validity, or runtime accessibility.


Canonical matches derived from exact community entry IDs equaling `audit.family_key` include `merrav2`, `river-plastic-inputs` (community key `plastic`), `terraclim`, `isric`, `glacier`, `hydrolakes`, `gfch`, `S2TSLULC`, `esrilc2020`, `ai0`, `et0`, `glc10`, `cflux`, `hwsd`, `npp_viirs_ntl`, `urban_projection`, `grwl`, `global_tcc`, `grip`, `gpm`, and `chirps_prelim`. The official Free-Flowing Rivers entry is linked to `free-flowing-rivers` by the exact shared source-paper DOI.
