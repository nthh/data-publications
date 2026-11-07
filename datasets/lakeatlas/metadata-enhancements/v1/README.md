# LakeATLAS metadata enhancement v1

This sidecar adds field meanings, published units, spatial aggregation/dimension rules, source citations and producer license notices to the prepared LakeATLAS v1.0 r2 polygons and pour-points package. It does not alter or copy either analytic asset. `field-semantics.json` records the two package SHA-256 values and manifest SHA-256 to bind this metadata version to the unchanged assets.

The 281 HydroATLAS attributes are expanded from the producer's LakeATLAS catalog field patterns and suffix inventories. Each expanded field retains the producer attribute name, definition, unit wording, spatial extent, statistic/dimension, source data, citation, catalog page and full license notice. `hydroatlas_license_as_published` records the catalog's explicit HydroATLAS license term separately from any notice about an upstream original license.

The 24 inherited HydroLAKES attributes are documented from Appendix 3 of the retained HydroATLAS technical documentation. The HydroLAKES v1 technical documentation (section 4.1, printed page 14) and the HydroSHEDS HydroLAKES product page explicitly license the HydroLAKES database CC-BY-4.0. The sidecar records that as `license_as_published` for these inherited source-product fields, and keeps `hydroatlas_license_as_published` null because the LakeATLAS catalog has no separate per-column entry for them. This source-product license evidence is not conflated with the LakeATLAS catalog's per-column notices or HydroATLAS collective-database license. The retained-source evidence supplies the HydroLAKES technical-documentation SHA-256 `3d1e30abb0691750127fd8e2ff6a149c83f36b93619fb44774476663e0f01f47`; this is recorded as source evidence metadata and was not freshly fetched or rehashed during generation.

`OBJECTID`, `Shape_Length`, and `Shape_Area` are source geodatabase defaults; the producer technical documentation says they are not officially part of LakeATLAS. Their units are left unspecified because the retained producer documentation does not specify them for those fields. `geometry` is the GeoParquet WKB encoding and `bbox` is package-derived metadata.

## Rebuild to a new output

Requires Python 3 and `pdftotext`. Set `LAKEATLAS_PACKAGE` to the prepared local package directory that contains `manifest.json`, `assets/`, `metadata/`, and `source/`. The script verifies the immutable manifest hash and its two expected asset SHA-256 entries, confirms both asset files exist at the recorded byte sizes, and checks both field dictionaries and both retained LakeATLAS producer PDFs against pinned SHA-256 values before generating. It relies on the existing package verification bound to that immutable manifest; it does not reread the large analytic assets to recompute their hashes. The output must be a new, nonexistent path; the script refuses to overwrite an existing version.

```sh
mkdir -p .local/lakeatlas/metadata-enhancements/v1
export LAKEATLAS_PACKAGE=/path/to/lakeatlas-v1.0-r2-prepared
python3 datasets/lakeatlas/metadata-enhancements/v1/build_semantics.py \
  --package-root "$LAKEATLAS_PACKAGE" \
  --output .local/lakeatlas/metadata-enhancements/v1/field-semantics-rebuild-20261101.json
cmp datasets/lakeatlas/metadata-enhancements/v1/field-semantics.json \
  .local/lakeatlas/metadata-enhancements/v1/field-semantics-rebuild-20261101.json
```

The generator rejects unresolved and incomplete producer semantics by default. Pass `--allow-unresolved` only for exploratory schema changes; incomplete or unresolved fields remain visible and fail strict focused semantics validation. Producer source files are identified by their SHA-256 values in the output. Neither source documents nor data assets are copied into this metadata sidecar.

## Authority and attribution

LakeATLAS authority: HydroSHEDS / HydroATLAS authors, *LakeATLAS Attributes (version 1.0)* and *HydroATLAS Technical Documentation version 1.0.1* (June 2022), retained with the prepared local package. HydroLAKES inherited-field license authority: [HydroLAKES Technical Documentation v1.0, section 4.1](https://data.hydrosheds.org/file/technical-documentation/HydroLAKES_TechDoc_v10.pdf) and the current [HydroSHEDS HydroLAKES product page](https://www.hydrosheds.org/products/hydrolakes). Cite Lehner, B., Messager, M.L., Korver, M.C., and Linke, S. (2022), “Global hydro-environmental lake characteristics at high spatial resolution,” *Scientific Data* 9, 351, DOI [10.1038/s41597-022-01425-z](https://doi.org/10.1038/s41597-022-01425-z). Dataset source record: LakeATLAS v1.0, Figshare article version 1, DOI [10.6084/m9.figshare.19312001.v1](https://doi.org/10.6084/m9.figshare.19312001.v1).
