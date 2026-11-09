# Dataset workspaces

The five published products are [Free-Flowing Rivers](free-flowing-rivers/README.md), [GRWL raw vectors](grwl-raw/README.md), [HydroLAKES](hydrolakes/README.md), [LakeATLAS](lakeatlas/README.md), and [river plastic inputs](river-plastic-inputs/README.md). Their public metadata is also listed in the generated [catalog](../catalog/README.md).

Other retained workspaces:

- [GRWL simplified summary](grwl/README.md) — publication withheld after source-quality review.
- [GRIP4](grip/README.md) — historical research retained; no prepared release or current-road claim.
- [JRC Global Surface Water Occurrence](jrc-gsw-occurrence/README.md) — sample-qualified for reuse; no local raster release.
- [Global Dam Watch](gdw/README.md) — preparation awaits access to the selected official source.
- [SWOT Prior Lake Database](swot_prior_lake_database/README.md) — metadata-qualified; conversion and preparation remain pending.

Discovery-only canonical records live under [`candidates/`](../candidates/README.md). Promote one into a workspace with `git mv candidates/<id> datasets/<id>`; keep exactly one record per ID.
