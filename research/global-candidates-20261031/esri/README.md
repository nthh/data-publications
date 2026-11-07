# Esri / ArcGIS global-source inventory

This lane captures a bounded metadata-only ArcGIS Online search and a reviewed set of global or near-global dataset-family leads. It is not an exhaustive ArcGIS Online census and it does not establish byte-level coverage, output format validity, or redistribution permission.

## Capture and check

The command without flags is offline and checks the retained files:

```sh
python3 research/global-candidates-20261031/esri/capture.py --check
```

To make a new bounded public ArcGIS search capture, explicitly provide both `--fetch` and a new, nonexistent output path. It refuses an existing path and never defaults to the frozen `search-inventory.json`:

```sh
python3 research/global-candidates-20261031/esri/capture.py --fetch --output research/global-candidates-20261031/esri/search-inventory-next.json
```

The Python standard-library script calls the public ArcGIS Sharing REST `search` endpoint using unauthenticated GET requests only when `--fetch` is present. It writes a normalized inventory of item fields selected in `capture.py`, query text, page starts, reported totals, returned counts, `nextStart`, response URLs, byte counts, response SHA-256 values, and failures. **It does not retain the raw response bodies.** Hashes therefore document the response observed at capture time; the retained file cannot replay or independently re-hash the full responses.

The cap is 120 requests, 30,000,000 response bytes, and 2,000 search-result rows across all queries. Each query captures at most two 50-result pages; remaining `nextStart` values are retained and marked truncated. The query list and normalization allow the bounded search to be repeated, not guaranteed bit-identically.

`--check` performs no network access. It verifies page/request and item totals, unique item IDs, row/byte/request budgets, truncation flags, and ArcGIS item-page IDs cited by `reviewed.json` against the retained inventory.

## Current observation

Capture time: `2026-11-01T00:30:04.434754+00:00` UTC.

- 37 configured searches; 43 page requests captured.
- 902 result rows, 805 unique item IDs, 3,766,656 response bytes.
- 0 errors; no global request, byte, or result cap reached.
- Two query page limits were reached: `target_world_countries` reported total 2,035 and `target_world_cities` reported total 818. Each captured starts 1 and 51, then retained `nextStart=101`; the remaining records are unreviewed.
- Search index totals are observations from ArcGIS's indexed catalog; they may lag source edits and do not prove content completeness.

## Review rules and limits

`reviewed.json` contains 15 reviewed family leads selected from the 805 unique captured item IDs; the remaining 790 item IDs were not individually reviewed. It prioritizes producer-linked global data and Esri's curated/official accounts. Duplicate Esri item IDs and related service releases are grouped where they represent one family. Spatial extent alone is not accepted as geographic coverage; notes distinguish complete-coverage claims from selected places, partial country updates, and terrestrial-only products.

Access types are kept separate:

- `service_only` means this review observed an ArcGIS service and did not establish producer bulk access.
- `download_available` means a linked producer page lists a native download, not that this task downloaded or validated it.
- `unknown` means the public catalog did not establish the native file format or service export rights.

Per-item licenses and producer licenses are recorded separately where they differ. Export permission is item-specific; ArcGIS documentation describes that hosted feature-layer export depends on owner/admin rights or an explicit export setting. No service export or feature query was attempted. Esri's `Esri Boundaries Global Coverage` item was excluded because its terms explicitly prohibit offline export. Several arbitrary `World Rivers` and “Global Rivers Atlas” copies were also excluded for missing producer authority or source/license evidence.

No feature data, raster bytes, service exports, credentials, or paid calls were accessed; no data was uploaded or published. `format_labels` describe broad source geometry, and `recommended_formats` are limited to cases with a plausible producer-native format and license basis; they are not conversion validations or release permissions. GHSL UCDB and GPW density are marked as related components to existing records, not the same canonical dataset identity.

## Primary references

- [ArcGIS REST Search reference](https://developers.arcgis.com/rest/users-groups-and-items/search/)
- [Esri hosted-layer export documentation](https://doc.arcgis.com/en/arcgis-online/manage-data/use-hosted-layers.htm)
- [Esri Living Atlas overview/curation](https://www.esri.com/arcgis-blog/products/arcgis-living-atlas/sharing-collaboration/your-living-atlas-questions-answered)
- [Natural Earth downloads and terms](https://www.naturalearthdata.com/downloads/)
- [European Commission GHSL datasets](https://human-settlement.emergency.copernicus.eu/datasets.php)
- [WRI Global Power Plant Database](https://github.com/wri/global-power-plant-database)
- [RESOLVE Ecoregions 2017](https://ecoregions.world/)
- [NOAA NCEI NOAAGlobalTemp](https://www.ncei.noaa.gov/products/land-based-station/noaa-global-temp)
- [USGS World Ecological Land Units record](https://catalog.data.gov/dataset/world-ecological-land-units-elus-2015)
