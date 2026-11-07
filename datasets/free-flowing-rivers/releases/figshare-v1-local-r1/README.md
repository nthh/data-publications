# Free-Flowing Rivers local analytic release r1

This directory holds the portable verification record for the local package at
`<data-publications checkout>/.local/free-flowing-rivers/releases/figshare-v1-local-r1`.
The package is local only: no public upload, hosting, registry submission, or
community audit was performed. The snapshotted dataset record remains a
candidate; canonical promotion and catalog integration are a separate parent
workflow.

## Pinned source and result

The source is Figshare article `10.6084/m9.figshare.7688801.v1`, file 15090536,
under CC BY 4.0. The File Geodatabase ZIP is 954,710,486 bytes,
SHA-256 `e45aa83a60e91840ddf6cc0820a4c32f44edf7a0318c78b62980fa9e44d6e31a`.
The inspected layer is `FFR_river_network_v1`: 8,477,883 MultiLineString
features, EPSG:4326, 38 source attributes plus producer FID `OBJECTID`. The
raw analytic build also records one-based `source_row`; the spatial release
appends `bbox` as derived [xmin, ymin, xmax, ymax] longitude/latitude bounds.
Original attributes, nulls, row order, multiplicity, and WKB are preserved.
See `source-validation.json`, the two spatial augmentation reports, and the
bound fidelity reports in `evidence/`.

The packaged analytic asset `ffr-reach-network-v1` has 8,477,883 rows, is
887,132,886 bytes, and has SHA-256
`62130e4999ba449bd2768bcdd9346bc2ba8fa4c4f06d39597e5227cd496a1a63`. The
clean checkout reproduced the raw bytes exactly; spatial augmentation from
both raw files then reproduced this final hash. Raw build code was committed at
`a6c2026768cd21cef5e59c88364dfa3ba04efacc`. The first raw build ran at the
subsequent repository HEAD `4f8ec8854a88b30441a9d5ba13bbdeb4108df3dd`, whose
parent is the FFR code commit; FFR source inputs were unchanged. The independent
clean raw rebuild used the FFR code commit `a6c2026768cd21cef5e59c88364dfa3ba04efacc`. Spatial
augmentation and packaging used helper commit
`c18b96e2f3d631089453459d158c91fc0fa31d87`.

## Reproduction commands

Run these from a clean repository checkout at the recorded revisions. All
outputs must use new empty paths. The public archive is accessed through GDAL
virtual ZIP; it is not extracted. Build and source validation need the archive
in ignored `.local/free-flowing-rivers/` storage.

```sh
uv sync --locked --project datasets/free-flowing-rivers
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/acquire.py
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/build.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip \
  --output .local/free-flowing-rivers/figshare-v1-local-r1
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/validate.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip \
  --release .local/free-flowing-rivers/figshare-v1-local-r1
uv run --locked --project datasets/free-flowing-rivers python datasets/free-flowing-rivers/fault_tests.py \
  --source .local/free-flowing-rivers/Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip \
  --release .local/free-flowing-rivers/figshare-v1-local-r1
```

For a separate clean checkout, run the same build and validation commands with a
new `--output` directory. In the first build, GeoParquet `geo` metadata is in the
Parquet footer but not in the serialized Arrow schema because the raw writer
adds footer metadata after writer construction. Spatial augmentation therefore
uses the explicitly source-verified CRS flag, `--crs EPSG:4326`; it does not
infer an unknown CRS or rewrite the source geometries.

```sh
uv sync --locked --project scripts/release_tools
uv run --locked --project scripts/release_tools python scripts/release_tools/add_spatial_bounds.py \
  --input .local/free-flowing-rivers/figshare-v1-local-r1/free-flowing-rivers/free-flowing-rivers-figshare-v1.parquet \
  --output .local/free-flowing-rivers/spatial-r1/free-flowing-rivers.parquet \
  --report .local/free-flowing-rivers/spatial-r1/augmentation-report.json \
  --geometry-column Shape --crs EPSG:4326 --batch-rows 4096
```

Repeat that augmentation from the independently rebuilt raw Parquet to a
separate output/report path. The locked helper environment used PyArrow 23.0.1,
DuckDB 1.5.2, PyYAML 6.0.3, Rashid 0.1.8, Shapely 2.2.0, and pyproj 3.8.0.
The conversion environment pins PyArrow 23.0.1, pyogrio 0.11.1, pyproj 3.8.0,
Shapely 2.1.2, and PyYAML 6.0.3. Node STAC validation used
`stac-node-validator` 2.0.0 from the locked npm package.

The tracked `evidence/fidelity-normalizer-template.json` includes both raw and
final assets, source validation, and both spatial augmentation reports. The
materializer resolves repository-relative inputs and fills the independent
checkout root.

```sh
python datasets/free-flowing-rivers/releases/figshare-v1-local-r1/evidence/materialize_release_inputs.py fidelity \
  --template datasets/free-flowing-rivers/releases/figshare-v1-local-r1/evidence/fidelity-normalizer-template.json \
  --output .local/free-flowing-rivers/fidelity-normalizer-spec-r1.json \
  --clean-checkout <CLEAN_CHECKOUT_ROOT>
uv run --locked --project scripts/release_tools python research/hydro-releases-20261031/bind_fidelity.py \
  .local/free-flowing-rivers/fidelity-normalizer-spec-r1.json \
  --output-dir .local/free-flowing-rivers/fidelity-chain-r1
```

`evidence/package-spec-template.json` records the exact package metadata and
relative inputs used here. Materialize it to ignored local storage with the
owned helper below; the helper resolves each path against the tracked template
location and sets the requested fresh output path:

```sh
python datasets/free-flowing-rivers/releases/figshare-v1-local-r1/evidence/materialize_release_inputs.py package \
  --template datasets/free-flowing-rivers/releases/figshare-v1-local-r1/evidence/package-spec-template.json \
  --output .local/free-flowing-rivers/package-spec-r1.json \
  --package-output <NEW_ABSOLUTE_LOCAL_PACKAGE_PATH>
npm ci --prefix scripts/release_tools --ignore-scripts --no-audit --no-fund
uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  .local/free-flowing-rivers/package-spec-r1.json
```

For the completed local package, the package manifest SHA-256 is
`09d5713df59baee88721911a0eef017629f814430b5c84c83eb1a5b92d8960ce`; its
package binding SHA-256 is
`cd81cacd31382ee98b7d7468aed463b25bd2bc51830a6197afd0595e0c00bfef`. The
final package verification, STAC validation, Portolan validation, local HTTP
range/CORS checks, DuckDB remote/local subset comparison, integrity report, and
binding report are copied into this directory. STAC Node validated both
`catalog.json` and `collection.json`; Rashid reported zero errors and one
informational note that no upstream STAC canonical link exists.

The raw file's GeoParquet global bounds are `[-179.99791666699997,
-55.87708333299997, 179.99791666700003, 83.58958333300006]`. All audited
geometry types are MultiLineString. The package helper made an APFS clone of
the final analytic asset and verified its hash. The source archive download
cache was removed after two successful complete source validations; it can be
reacquired from the pinned public Figshare file URL using `acquire.py`.

## Spatial helper sidecar

The immutable local package r1 includes a workflow snapshot of the shared
spatial helper at `verification/workflow/scripts/release_tools/add_spatial_bounds.py`
and its locked runtime. A separately tracked sidecar is also provided at
`evidence/spatial-helper-c18/`, including its source, `pyproject.toml`, and
`uv.lock`. `evidence/spatial-helper-c18/sidecar-manifest.json` gives each file's
SHA-256 and binds those bytes to helper commit
`c18b96e2f3d631089453459d158c91fc0fa31d87`. Verify those hashes with
`shasum -a 256 -c sidecar-sha256.txt` from that directory.
