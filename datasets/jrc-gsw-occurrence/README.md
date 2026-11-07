# JRC GSW Occurrence v1.5

The canonical [dataset record](dataset.yaml) qualifies the producer-hosted global
1984–2024 occurrence product for reuse. No local raster release was made and no
Source Cooperative or Portolan submission has occurred.

The generated [source inventory](source-inventory.json) lists all 504 occurrence
TIFFs and their total 14,453,956,859 bytes. Listing hashes are retained verbatim;
they are not asserted to be object SHA-256 checksums.

Eight geographically varied files passed bounded HTTP range and TIFF-structure
probes (280,640 response bytes). All sampled files are tiled and have overviews
with COG-like layout. This does not certify all files, full COG conformance, or
pixel values. See the [qualification evidence](../../research/hydro-releases-20261031/jrc/qualification.md).

Reproduce the offline inventory check from the repository root:

```sh
python3 datasets/jrc-gsw-occurrence/build_inventory.py --check
```

A deliberate live recheck is small but uses the network; supply a fresh output
path so the original evidence remains intact:

```sh
uv sync --locked --project datasets/jrc-gsw-occurrence
uv run --locked --project datasets/jrc-gsw-occurrence python research/hydro-releases-20261031/jrc/qualify_occurrence_ranges.py --output .local/jrc-occurrence/new-probes.json
```

The [producer's access page](https://global-surface-water.appspot.com/download)
identifies v1.5 as current, describes corrections to Occurrence, and explains the
Collection 1/Collection 2 processing boundary. A future registry submission
should link these exact producer assets, carry those caveats and required
EC JRC/Google attribution, and explicitly state the qualification scope.

The 2024 endpoint is the producer release cutoff checked on 2026-10-31.
Occurrence summarizes water frequency across 1984–2024; it is not a current-date
water map. The related products below provide context for more recent mapping
without changing this record’s selected product or reuse decision.

<!-- related-datasets:start -->

## Related datasets

Generated from `related_datasets` in [dataset.yaml](dataset.yaml). These references describe alternatives and complementary uses; they do not add datasets to the processing queue. The comparisons are based on the cited documentation, not an equivalence or accuracy benchmark.

### [OPERA DSWx-HLS v1](<https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-HLS_V1>)

- **Relationship:** Complement. Recent surface-water extent and change monitoring from optical observations.
- **Coverage:** Near-global land coverage, excluding Antarctica; 30 m; Validated observations begin April 2023; production is ongoing. The catalog also lists an earlier start date; historical completeness was not checked here.
- **Formats:** COG
- **Access:** NASA PO.DAAC; Earthdata Login is required for the documented direct S3 data access in us-west-2. Anonymous asset access was not tested.
- **Comparison:** Per-observation water classifications and confidence/cloud layers serve a different purpose from JRC 1984–2024 occurrence. Clouds limit optical observations; a long-term occurrence composite would require an explicit method and validation.
- **Reviewed:** 2026-10-31. **Sources:** [NASA PO.DAAC product and access documentation](<https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-HLS_V1>), [JPL OPERA product coverage](<https://www.jpl.nasa.gov/go/opera/products/>).

### [OPERA DSWx-S1 v1](<https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-S1_V1>)

- **Relationship:** Complement. Recent open-water mapping under cloud cover and at night using Sentinel-1 radar.
- **Coverage:** Near-global land coverage, excluding Antarctica; 30 m; Forward production began September 2024 and is ongoing; the catalog includes earlier dates. Coverage for a particular region and date remains to be qualified.
- **Formats:** COG
- **Access:** NASA PO.DAAC distribution; no file-level access or conformance checks performed in this comparison.
- **Comparison:** The producer targets open inland water bodies greater than 3 hectares and 200 m in width. It is a recent radar extent product, not JRC historical occurrence; OPERA products are not harmonized across sensors. Use reprocessed replacements for the documented 2025 processing anomaly.
- **Reviewed:** 2026-10-31. **Sources:** [NASA PO.DAAC product documentation and reprocessing notice](<https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-S1_V1>), [JPL DSWx suite and sensor differences](<https://www.jpl.nasa.gov/go/opera/products/dswx-product-suite/>), [NASA DSWx fact sheet and COG format](<https://www.earthdata.nasa.gov/s3fs-public/2024-04/OPERA-DSWx_Fact_Sheet.pdf>).

### [Dynamic World v1](<https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1>)

- **Relationship:** Complement. Recent water and flooded-vegetation context alongside other land-cover classes.
- **Coverage:** Global Sentinel-2 observation coverage; 10 m; June 2015 onward; near-real-time image-level predictions
- **Access:** Official Earth Engine image collection. Independent bulk hosting and anonymous cloud-native asset access were not qualified here.
- **Comparison:** The water band is a model class probability, not an observed multi-decade water-occurrence percentage. Cloud masking, probability thresholds and temporal aggregation must be specified before deriving a water product.
- **Reviewed:** 2026-10-31. **Sources:** [Official Dynamic World catalog and terms](<https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1>).

### [Copernicus Water Bodies 100 m monthly v1](<https://land.copernicus.eu/en/products/water-bodies/water-bodies-global-v1-0-100m>)

- **Relationship:** Complement. Regular global monthly inland-water monitoring at coarser resolution.
- **Coverage:** Global; 100 m; 2020 onward; monthly composites
- **Formats:** COG (CDSE catalog listing)
- **Access:** Copernicus Data Space Ecosystem lists a COG collection; individual objects, current completeness and access requirements were not tested here.
- **Comparison:** Coarser than JRC and uses JRC maximum water extent in its masking, so it is not an independent reference for validating JRC. Its monthly detections and occurrence categories differ from the JRC long-term occurrence statistic.
- **Reviewed:** 2026-10-31. **Sources:** [CLMS product description and algorithm](<https://land.copernicus.eu/en/products/water-bodies/water-bodies-global-v1-0-100m>), [CDSE COG collection listing](<https://browser.stac.dataspace.copernicus.eu/collections/clms_wb_global_100m_monthly_v1_cog>).

<!-- related-datasets:end -->
