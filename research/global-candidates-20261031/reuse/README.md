# Prior public-access observations

This lane carries forward selected observations from the repository's October 2026 CHIRPS, publication-priority, SoilGrids, download-audit, availability and canonical-record research. It makes no network requests and does not read dataset assets. `reviewed.json` keys each observation to an existing canonical target ID; a link is a reuse/counterpart observation, not proof of release equivalence.

## Reproduce the offline checks

From the repository root:

```sh
python3 research/global-candidates-20261031/reuse/check.py
```

The checker verifies every retained evidence-file SHA-256, unique observation keys/IDs, HTTPS source references, and that each `target_id` still resolves to a canonical dataset record. It does not validate current remote availability or dataset bytes.

## Observation limits

- CHIRPS WFP v3 daily RNL is a related release to the current GEE CHIRPS v2.0 candidate; its STAC samples and asset declarations are metadata evidence only. CHIRPS v2 August 2020 benchmark evidence concerns six pentad COGs, not a full archive.
- SoilGrids producer docs and Source Cooperative mean-only Icechunk/Zarr are separate evidence. The saved Source Coop README request returned HTTP 403; no asset/store reader was tested. The cloud publication omits quantiles and other product components listed in the review.
- JRC v1.5 Occurrence producer tiles are a separate product from the Source Cooperative MonthlyHistory mirror. Eight range probes on v1.5 support a sampled COG-like layout only; no image pixels or complete files were read.
- TerraClimate PC Zarr spans STAC dates 1958–2021, while the producer v1.1 archive inventory is 1950–2025. One `.das` response's CC0 declaration is not an archive-wide license audit.
- Overture observations retain producer-documented cloud access and the older Source Cooperative buildings counterpart with version parity unverified. No theme asset was opened.

Original observation dates and evidence paths/hashes are retained per entry. Evidence hashes point only to saved research snapshots, not mutable canonical dataset YAML or generated README files. Overture Buildings remains explicitly regional CONUS in this observation. No new dates, citations, data fetches, conversions, or license clearances are introduced.
