# Supplementary global literature sample

This is a separate, bounded discovery lane for ten producer-backed global dataset families not represented by the exact frozen top-50 paper DOI set. It is a purposive addition, not a literature-wide search or a universal top-cited ranking. The 2026-10-30 catalog-citation snapshot was not changed, and these current observations must not be blended into it.

## Identity before citation counts

`paper-identities.json` was saved at 2026-11-01T00:46:11Z before any OpenAlex request. It records product edition, dataset-specific paper DOI/title, producer/publisher evidence URLs, global coverage notes and current canonical-record overlap review. Product/data-release DOIs remain separate from the paper DOIs used for counts. The OpenAlex lookups began at 00:46:49Z.

The sample covers WorldClim v2.1, CRU TS v4.10, CHELSA v2.1, GPCC Full Data Monthly v2022, EarthStat/Monfreda 2000 crop maps, GLiM v1, archived ERA-Interim, MODIS MCD12Q1 C6.1, HYDE 3.2, and GMIA v5. Editions are explicit: WorldClim v2.1 is separate from existing WorldClim v1; CRU TS v4 is separate from its v3 citation; the 2017 CHELSA paper describes the original product, not byte-equivalent v2.1; GPCC's 2013 paper describes the family rather than v2022; MODIS's paper describes Collection 5 while the candidate is Collection 6.1; ERA-Interim stopped in 2019 and was superseded by ERA5. GMIA v5's direct report DOI is retained separately from the foundational 2005 map paper.

## Counts observed

Counts below are OpenAlex `cited_by_count` values observed per DOI-resolved work on 2026-11-01 UTC. Exact request timestamps, resolved work IDs, HTTP statuses, and complete normalized API response JSON are in `openalex-responses-20261101.json`. Counts are not summed across works. The related CRU v3 and GMIA 2005 counts appear separately in `reviewed.json` and do not replace or augment their primary candidate count.

| Dataset family / edition | Associated paper DOI | OpenAlex count | Edition relation |
|---|---|---:|---|
| WorldClim v2 / v2.1 | 10.1002/joc.5086 | 17,262 | v2 paper; later v2.1 release |
| CRU TS v4 | 10.1038/s41597-020-0453-3 | 4,909 | v4.03 paper; v4.10 current release |
| CHELSA climatologies | 10.1038/sdata.2017.122 | 4,199 | 2017 v1 paper; v2.1 later release |
| GPCC Full Data Monthly v2022 | 10.5194/essd-5-71-2013 | 919 | family paper predates v2022 |
| EarthStat/Monfreda crop maps circa 2000 | 10.1029/2007GB002947 | 1,895 | directly describes 2000 maps |
| GLiM v1 | 10.1029/2012GC004370 | 1,168 | directly describes GLiM v1 |
| ERA-Interim | 10.1002/qj.828 | 24,480 | ERA-Interim-specific, archived |
| MODIS MCD12Q1 C6.1 | 10.1016/j.rse.2009.08.016 | 3,489 | paper describes Collection 5; C6.1 is later |
| HYDE 3.2 | 10.5194/essd-9-927-2017 | 1,204 | directly describes HYDE 3.2 |
| GMIA v5 | 10.13140/2.1.2660.6728 | 89 | producer v5 report; separately observed foundational 2005 paper count is 620 |

These are snapshot counts, not exact-release-use counts or conversion priorities. No data DOI citations were requested or mixed into paper counts. The product access and license fields remain metadata observations; no assets were downloaded or inspected.

## Canonical overlap review

`reviewed.json` points WorldClim v2 to existing `worldclim_v1` as a distinct release; ERA-Interim to `era5` as a superseded related product; and GMIA v5 to `global_irrigation` as a related but different product (GMIA is a circa-2005 map of equipped irrigation area and additional layers, whereas the existing record is a 2001-2015 product). Other reviewed families have no exact record in `datasets/` at the time of review. Similar subject, global extent or producer alone was not treated as identity.

## Reproduction and limits

The optional capture script uses the public OpenAlex API without a key, is capped at 40 planned requests and 10 MB of response data, and refuses to overwrite an existing output:

```sh
python3 research/global-candidates-20261031/literature/fetch_openalex.py \
  --allow-network --output openalex-responses-new-capture.json
```

The identity list must be reviewed and saved before running this opt-in network command. The script captures the primary paper DOI and explicitly listed related-paper DOIs only; no dataset assets are requested. `build_review.py --write` creates `reviewed.json` only when it does not exist; `build_review.py --check` compares the exact generated projection without writing files.

The evidence set includes producer/publisher sources: [WorldClim v2.1](https://www.worldclim.org/data/worldclim21.html), [CRU TS v4.10](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/), [CHELSA v2.1](https://www.chelsa-climate.org/datasets/chelsa_climatologies), [GPCC Full Data Monthly v2022](https://doi.org/10.5676/DWD_GPCC/FD_M_V2022_250), [EarthStat](https://www.earthstat.org/), [GLiM PANGAEA record](https://doi.pangaea.de/10.1594/PANGAEA.788537), [ECMWF reanalysis inventory](https://www.ecmwf.int/en/forecasts/datasets/browse-reanalysis-datasets), [NASA MCD12Q1 C6 guide](https://modis-land.gsfc.nasa.gov/pdf/MCD12Q1_C6_Userguide04042018.pdf), [HYDE portal](https://hyde-portal.geo.uu.nl/), and [FAO GMIA product documentation](https://www.fao.org/aquastat/en/resources/publications/reports/).
