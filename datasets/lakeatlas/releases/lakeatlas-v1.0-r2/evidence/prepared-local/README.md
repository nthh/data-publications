# HydroATLAS LakeATLAS v1.0 — global hydro-environmental lake attributes

Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.

Dataset ID: `lakeatlas`  
Release: `lakeatlas-v1.0-r2` (`1.0.2`)  
Spatial extent: `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]`  
Source: [LakeATLAS v1.0 producer data and documentation](https://doi.org/10.6084/m9.figshare.19312001.v1)

## Analytic assets

| Asset | Path | Rows | Identifier column | SHA-256 |
|---|---|---:|---|---|
| `lakeatlas-polygons` | `assets/lakeatlas-polygons.parquet` | 1427688 | `OBJECTID` | `bbef606fd8522b230efc90e2952a67c1e4265e7bf733208fa4cc31395a7277b7` |
| `lakeatlas-pour-points` | `assets/lakeatlas-pour-points.parquet` | 1427688 | `OBJECTID` | `ff621c1db763551cdb6ced8958eefcc9da76a73c16e7f7259c238bec3aae5720` |

## Evidence

The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.

## Licenses and attribution

Source attribution: HydroSHEDS / HydroATLAS authors. LakeATLAS version 1.0. Cite Lehner, B., Messager, M.L., Korver, M.C., and Linke, S. (2022), Global hydro-environmental lake characteristics at high spatial resolution, Scientific Data 9, 351, DOI 10.1038/s41597-022-01425-z. Source archive SHA-256 baa4d760a163350dd6a30c21c82db1e23b150834a8b848885eba6dc9ba1175df..

Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.

## Reproduction

The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.
