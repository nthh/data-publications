# HydroLAKES and LakeATLAS source audit

This read-only audit checks source choice, omitted layers, analytical changes, and the limits of retained validation evidence. Structured findings and the evidence-file SHA-256 inventory are in [hydro-audit.json](hydro-audit.json).

## Findings

| Dataset | Finding | Action |
|---|---|---|
| HydroLAKES | The analytical release converts the official v1 polygon Shapefile ZIP, not a simplified summary. It omits the separately distributed pour-point layer; the release clearly limits its scope to polygons. | Keep the polygon-only scope. Include points only if claiming the complete HydroLAKES layer set. |
| LakeATLAS | The release converts the official v1 enriched File Geodatabase and includes both expected vector layers: lake polygons and pour points. No summary-for-vector substitution or ignored companion layer was found. | Preserve decoder caveats and avoid claims of independent scientific validation. |

## HydroLAKES

The pinned source is `HydroLAKES_polys_v10_shp.zip` from the [HydroSHEDS HydroLAKES page](https://www.hydrosheds.org/products/hydrolakes), 820,295,132 bytes, recorded SHA-256 `9ef63498569dd7ccd0b8d8852da026e009a75f42d293f00e483f3b9fcfe8e1f9`. It is the official v1.0 polygon product. The producer describes its global lake shoreline inventory and lists polygon and pour-point downloads separately. [HydroLAKES Technical Documentation v1.0](https://data.hydrosheds.org/file/technical-documentation/HydroLAKES_TechDoc_v10.pdf)

The prepared `v1-local-r3` analytic asset has 1,427,688 polygons and retains the 22 decoded source fields and WKB. It appends bbox covering and spatially orders rows. The release says it does not repair, simplify, reproject, deduplicate, or rewrite geometry. The missing point layer is a **disclosed scope gap**, not evidence that the polygon asset is an artifact summary. HydroATLAS/LakeATLAS supplies a separate enriched product and is not the native HydroLAKES polygon source.

The complete source-reread report records 31,409,136 compared cells and per-feature decoded-value/WKB binding. The spatial-order evidence reports recomputed bboxes and source-value/null/WKB comparison. However, comparison uses the same GDAL decoder; GEE parity and independent scientific accuracy were not tested. The clean-rebuild report records equal raw and final asset hashes, but `clean_checkout_independently_verified` is **false**. Treat this as recorded artifact equality, not an independently verified clean-checkout rebuild or an end-to-end rebuild of producer science.

## LakeATLAS

The pinned source is the official Figshare v1 record, [DOI 10.6084/m9.figshare.19312001.v1](https://doi.org/10.6084/m9.figshare.19312001.v1): `LakeATLAS_Data_v10.gdb.zip`, file ID 35959544, 1,530,962,499 bytes, producer MD5 `952e0724afc96d3a5899f08935d4a094`, and recorded SHA-256 `baa4d760a163350dd6a30c21c82db1e23b150834a8b848885eba6dc9ba1175df`. The repository pins the accompanying LakeATLAS catalog and HydroATLAS technical documentation too. The producer describes LakeATLAS as the HydroLAKES-derived lake unit with added hydro-environmental attributes. [HydroATLAS product page](https://www.hydrosheds.org/hydroatlas) · [HydroATLAS Technical Documentation v1.0.1](https://data.hydrosheds.org/file/technical-documentation/HydroATLAS_TechDoc_v10_1.pdf)

Source inspection recorded a 52-member archive and exactly the two expected layers: `LakeATLAS_v10_pol` (1,427,688 MultiPolygons, 307 attributes plus `OBJECTID`) and `LakeATLAS_v10_pnt` (1,427,688 points, 305 attributes plus `OBJECTID`). The final package preserves both and their source-decoded fields and geometries. The builder checks that the discovered layer inventory matches those expected layers.

Source-fidelity evidence reports all rows compared in source order, then source-order reconstruction, attribute/null/WKB comparisons and bbox recomputation for both spatial assets. The primary and clean candidate hashes match. This still does not establish independent scientific accuracy: source comparison uses GDAL/OpenFileGDB, and the README records an `organizePolygons()` warning for one polygon with more than 100 parts. The validation proves decoded-source fidelity, not raw FileGDB ring-record identity. The clean-rebuild report also sets `clean_checkout_independently_verified` to **false**.

Both datasets have display PMTiles that simplify and quantize geometry. Their display manifests identify those as derivatives and bind them to the analytical GeoParquet. That display generalization is separate from the analytical asset changes.

## Evidence and verification

The JSON report lists exact paths and SHA-256 values for source records, converter code, source inspection, fidelity reports, clean-rebuild reports, manifests, retained LakeATLAS failures, and display manifests. I parsed the report as JSON, checked that all 20 inventoried evidence files exist and match their listed hashes, and cross-checked each recorded source SHA against its retained source-fidelity/source-inspection record. Bulk archives and analytic assets were not rehashed during this audit. No builds, tests, downloads, or repository edits outside these two audit files were performed.

## Parent review of the rebuild flag

The normalizer writes clean_checkout_independently_verified=false unconditionally (bind_fidelity.py line351). Matching rebuilt asset hashes and saved clean-checkout observations are present. This flag is a conservative normalizer limitation, not evidence of a failed rebuild; it does not independently re-establish the saved checkout provenance. Evidence hashes above refer to Git revision `711e281`, before this audit follow-up changed canonical records.
