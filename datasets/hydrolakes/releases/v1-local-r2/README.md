# HydroLAKES v1 local GeoParquet release candidate r2

This is a local, unpublished candidate for the complete HydroLAKES v1.0 polygon layer. The producer release is v1 (the archive filename uses v10). Its shoreline inputs are a legacy composite, not a 2026 shoreline observation. The candidate contains one analytic GeoParquet asset and no PMTiles derivative. Source fidelity and reproducibility do not establish GEE parity or independent scientific accuracy.

## Asset identity and geometry bounds

The source-validated raw GeoParquet contains 1,427,688 features and 22 original fields, including `Hylak_id` and `wkb_geometry`. Its SHA-256 is `4c7c83b0a91e4cbd1e31583ab89eee9721ba22250272640591f4795d186a6a76` (945,383,282 bytes). The bbox-covered candidate appends one derived `bbox` struct while retaining the 22 original fields, all 1,427,688 rows, decoded values, nulls and WKB. Its SHA-256 is `273f66aa591f575616e731e6f31111ddf8ecfb39c0c05eacf0e903b6ddd6944d` (1,001,702,072 bytes).

The raw build manifest and both independent spatial rereads report the same global WKB extent: `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]` (west, south, east, north). Each augmentation compared all 31,409,136 source cells, recomputed and checked all 5,710,752 bbox ordinates in batches of at most 512 rows, and found 2,789 row groups and `Polygon: 1,427,688`. No coordinate reprojection, geometry repair, simplification or WKB rewrite occurred.

## Package gate status

The source-order asset remains sorted by `Hylak_id`. Actual Rashid 0.1.8 Portolan validation fails mandatory PTL-DAT-006: the 1,427,688 rows in 2,789 row groups do not cluster spatially. STAC Node 2.0.0, package integrity, HTTP 206/CORS probes, and the DuckDB local/HTTP subset fingerprint pass. The release is therefore **failed-local-validation**, not prepared. `evidence/` carries the exact package Manifest, Catalog, Collection, receipt and validator reports; the copied source, raw rebuild and spatial receipts are under `provenance/` in the local package. No gate has been waived.

A later release candidate may use a separately identified spatially ordered derivative after its full source-field/null/WKB/bbox validation, byte-identical clean rebuild and actual Portolan gate pass. Acceptance criteria are recorded in [the dataset validation plan](../../VALIDATION.md). The source-order raw asset and failed package attempts are preserved unchanged.

## Producer terms and citation

The producer product page states CC BY 4.0. The technical document also requests permission before redistributing the complete database in its original format. The local package includes the transformed GeoParquet and producer technical PDF; this README does not make a broader legal determination. The paper DOI `10.1038/ncomms13603` is a citation DOI, not the source-dataset DOI; it is cited in metadata without `sci:doi`.

The producer source ZIP was evicted after full verification to reclaim disk. `evidence/source-cache-eviction.json` records its SHA-256, size and reacquisition command. The PDF is pinned by `evidence/source-document.json` and is kept only in the ignored local package, not duplicated in tracked Git evidence.

## Re-materialize package inputs

From the repository root, use the path-free templates under `evidence/` with the materializer. No full source conversion or clean rebuild is part of package materialization.

```sh
python datasets/hydrolakes/releases/v1-local-r2/evidence/materialize_release_inputs.py fidelity \
  --artifact-root /path/to/local/hydrolakes \
  --clean-checkout /path/to/detached-clean-checkout \
  --output /path/to/ignored/hydrolakes-fidelity-input.json

uv run --locked --project datasets/hydrolakes python research/hydro-releases-20261031/bind_fidelity.py \
  /path/to/ignored/hydrolakes-fidelity-input.json \
  --output-dir /path/to/ignored/hydrolakes-fidelity-r2

python datasets/hydrolakes/releases/v1-local-r2/evidence/materialize_release_inputs.py package \
  --artifact-root /path/to/local/hydrolakes \
  --fidelity-root /path/to/ignored/hydrolakes-fidelity-r2 \
  --package-output /path/to/local/hydrolakes/releases/v1-local-r2-reproduction \
  --output /path/to/ignored/hydrolakes-package-input.json

uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  /path/to/ignored/hydrolakes-package-input.json
```

The package helper refuses to overwrite output and records every failure. Its validation state remains failed until all mandatory checks pass. Local preparation is not public hosting or registry submission.
