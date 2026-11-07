# HydroLAKES v1.0: Polygons

Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.

Dataset ID: `hydrolakes`  
Release: `v1-local-r3` (`1.0.2`)  
Spatial extent: `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]`  
Source: [HydroLAKES v1 polygon dataset](https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip)

## Analytic assets

| Asset | Path | Rows | Identifier column | SHA-256 |
|---|---|---:|---|---|
| `hydrolakes-polygons` | `assets/hydrolakes-polygons.parquet` | 1427688 | `Hylak_id` | `6f588d97c14651eb23bea2d74fdf2a85f218a00ff11519c81efa5512b916b7f8` |

## Evidence

The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.

## Licenses and attribution

Source attribution: HydroLAKES v1.0, Lehner and Messager / HydroSHEDS; source archive SHA-256 9ef63498569dd7ccd0b8d8852da026e009a75f42d293f00e483f3b9fcfe8e1f9..

Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.

## Reproduction

The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.
