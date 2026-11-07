# Global River Width from Landsat — raw vector observations V01.01

Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.

Dataset ID: `grwl-raw`  
Release: `raw-v01.01-local-r1` (`1.0.0`)  
Spatial extent: `[-180.0, -54.31039221809525, 180.0, 82.31075059469364]`  
Source: [Global River Width from Landsat raw vector component V01.01](https://zenodo.org/records/18624542)

## Analytic assets

| Asset | Path | Rows | Identifier column | SHA-256 |
|---|---|---:|---|---|
| `grwl-raw-observations` | `assets/grwl-raw-observations.parquet` | 64572998 | `feature_id` | `d37d0ba791e682f279b88829897441189685af96e9106cf851aef3be861d4cbb` |

## Evidence

The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.

## Licenses and attribution

Source attribution: Allen, G.H. and Pavelsky, T.M. (2018), Global extent of rivers and streams. Science 361(6402), 585–588. https://doi.org/10.1126/science.aat0636.

Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.

## Reproduction

The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.
