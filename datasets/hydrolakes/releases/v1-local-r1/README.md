# HydroLAKES v1 local GeoParquet release candidate

This directory records a local, unpublished analytic release candidate for the complete HydroLAKES v1.0 global polygon layer. It contains one GeoParquet asset in the local package; no PMTiles derivative is included. The producer release is v1 (the archive filename says v10). Its shoreline inputs are a legacy composite; this is not a 2026 shoreline observation. Source fidelity and reproducibility do not establish GEE parity or independent scientific accuracy.

## Asset identity and geometry bounds

The source-validated raw GeoParquet contains 1,427,688 features and 22 original fields, including `Hylak_id` and `wkb_geometry`. Its SHA-256 is `4c7c83b0a91e4cbd1e31583ab89eee9721ba22250272640591f4795d186a6a76` (945,383,282 bytes). The release asset appends one derived `bbox` struct while preserving every original field, null and WKB value; it has 23 columns and the same 1,427,688 records. Its SHA-256 is `273f66aa591f575616e731e6f31111ddf8ecfb39c0c05eacf0e903b6ddd6944d` (1,001,702,072 bytes).

The raw build manifest and the augmented GeoParquet report have the same global WKB extent: `[-179.9999999999999, -55.86513888888899, 179.99999999999903, 83.57595062255876]` (west, south, east, north). The augmentation computed bounds from unchanged WKB in the source CRS. It did not sort rows, reproject, repair, simplify or rewrite geometry. The retained and clean-rebuild augmentation reports each checked all 5,710,752 bbox ordinates and compared all 31,409,136 source cells, including raw WKB and nulls, in bounded batches of at most 512 rows. They independently report 2,789 row groups and `Polygon: 1,427,688`.

The spatial bounds stage supports bbox covering statistics. The conversion remains sorted by `Hylak_id`; no spatial clustering or measured query-speed claim is made.

## Evidence and source terms

`evidence/source-validation.json` records the full independent source reread against the pinned HydroLAKES archive SHA-256 `9ef63498569dd7ccd0b8d8852da026e009a75f42d293f00e483f3b9fcfe8e1f9`. `evidence/clean-rebuild-raw.json` records an independent raw build from committed code. The two spatial reports bind the retained and clean-rebuilt augmented files. `evidence/evidence-provenance.json` records original report checksums and portable-copy checksums; machine-local paths in the spatial report copies are redacted. The producer PDF is included in the ignored local package and pinned by `evidence/source-document.json`; it is not duplicated in tracked release evidence.

The producer product page states CC BY 4.0. The technical document also requests permission before redistributing the complete database in its original format. This candidate contains transformed GeoParquet and preserves that producer wording; it does not make a broader legal determination. The source ZIP was removed after complete source verification and clean rebuild to reclaim disk. See `evidence/source-cache-eviction.json` for the retained receipt and reacquisition command.

The paper DOI `10.1038/ncomms13603` is a citation DOI, not a HydroLAKES source-dataset DOI. The STAC package records the paper under citation and omits `sci:doi`.

## Re-materialize verification inputs

No full conversion or clean rebuild is needed to inspect or repackage the retained artifacts. Put the retained local outputs under an artifact root and keep the clean committed checkout available. From the repository root:

```sh
python datasets/hydrolakes/releases/v1-local-r1/evidence/materialize_release_inputs.py fidelity \
  --artifact-root /path/to/local/hydrolakes \
  --clean-checkout /path/to/detached-clean-checkout \
  --output /path/to/ignored/hydrolakes-fidelity-input.json

uv run --locked --project datasets/hydrolakes python research/hydro-releases-20261031/bind_fidelity.py \
  /path/to/ignored/hydrolakes-fidelity-input.json \
  --output-dir /path/to/ignored/hydrolakes-fidelity-r1

python datasets/hydrolakes/releases/v1-local-r1/evidence/materialize_release_inputs.py package \
  --artifact-root /path/to/local/hydrolakes \
  --fidelity-root /path/to/ignored/hydrolakes-fidelity-r1 \
  --package-output /path/to/local/hydrolakes/releases/v1-local-r1 \
  --output /path/to/ignored/hydrolakes-package-input.json

uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  /path/to/ignored/hydrolakes-package-input.json
```

The materializer refuses to overwrite input files. The package tool refuses an existing output directory and requires both normalized reports to bind the exact release asset. It runs the STAC Node Validator, Rashid Portolan checks, local integrity checks, bounded HTTP range/CORS tests and a DuckDB HTTP subset comparison. A package is prepared locally only if all gates pass; this directory does not imply public hosting or registry submission.

The templates in `evidence/` use root placeholders and contain no machine-specific absolute paths. `evidence/materialize_release_inputs.py` checks that the supplied clean checkout is at the pinned full commit, detached and has an empty Git status before creating fidelity input. It does not rebuild data.
