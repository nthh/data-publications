# Mapping the world's free-flowing rivers — global river reach connectivity assessment

Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.

Dataset ID: `free-flowing-rivers`  
Release: `figshare-v1-local-r2` (`1.0.1`)  
Spatial extent: `[-179.99791666699997, -55.87708333299997, 179.99791666700003, 83.58958333300006]`  
Source: [Mapping the world's free-flowing rivers: data set and technical documentation (figshare v1)](https://figshare.com/articles/dataset/Mapping_the_world_s_free-flowing_rivers_data_set_and_technical_documentation/7688801)

## Analytic assets

| Asset | Path | Rows | Identifier column | SHA-256 |
|---|---|---:|---|---|
| `ffr-reach-network-v1` | `assets/ffr-reach-network-v1.parquet` | 8477883 | `OBJECTID` | `62130e4999ba449bd2768bcdd9346bc2ba8fa4c4f06d39597e5227cd496a1a63` |

## Evidence

The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.

## Licenses and attribution

Source attribution: Source data by Günther Grill and Bernhard Lehner. Funding acknowledgements: McGill University, World Wildlife Fund, and NSERC. Original source citation: Grill, G., Lehner, B., Thieme, M. et al. (2019), Mapping the world's free-flowing rivers, Nature 569, 215–221, https://doi.org/10.1038/s41586-019-1111-9..

Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.

## Reproduction

The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.
