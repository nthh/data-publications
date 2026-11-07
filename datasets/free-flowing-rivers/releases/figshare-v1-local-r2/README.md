# Free-Flowing Rivers local analytic release r2


The tracked STAC and manifest files are exact evidence copies from the standalone
package. They are not a live catalog hosted by this Git repository: their relative
asset, source-document and preview links resolve in the complete ignored package,
whose bulk files do not belong in Git. Publish and validate that complete package
before exposing its STAC entry point. `source-metadata.json` preserves the public,
unauthenticated Figshare API response, including the producer's generic account
API/HTML route fields; those fields contain no credentials and are not download
or publication endpoints.


This directory holds the portable verification record for the local package at
`<data-publications checkout>/.local/free-flowing-rivers/releases/figshare-v1-local-r2`.
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
augmentation used helper commit `c18b96e2f3d631089453459d158c91fc0fa31d87`;
r2 packaging used `7cc922857065883d1803a6892a5a160ce5a4f722`.

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
uv sync --locked --project datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/spatial-helper-c18
uv run --locked --project datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/spatial-helper-c18 python datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/spatial-helper-c18/add_spatial_bounds.py \
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
python datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/materialize_release_inputs.py fidelity \
  --template datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/fidelity-normalizer-template.json \
  --output .local/free-flowing-rivers/fidelity-normalizer-spec-r2.json \
  --clean-checkout <CLEAN_CHECKOUT_ROOT>
uv run --locked --project scripts/release_tools python research/hydro-releases-20261031/bind_fidelity.py \
  .local/free-flowing-rivers/fidelity-normalizer-spec-r2.json \
  --output-dir .local/free-flowing-rivers/fidelity-chain-r2
```

`evidence/package-spec-template.json` records the exact package metadata and
relative inputs used here. Materialize it to ignored local storage with the
owned helper below; the helper resolves each path against the tracked template
location and sets the requested fresh output path:

```sh
python datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/materialize_release_inputs.py package \
  --template datasets/free-flowing-rivers/releases/figshare-v1-local-r2/evidence/package-spec-template.json \
  --output .local/free-flowing-rivers/package-spec-r2.json \
  --package-output <NEW_ABSOLUTE_LOCAL_PACKAGE_PATH> \
  --fidelity-dir .local/free-flowing-rivers/fidelity-chain-r2
uv sync --locked --project scripts/release_tools
npm ci --prefix scripts/release_tools --ignore-scripts --no-audit --no-fund
uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  .local/free-flowing-rivers/package-spec-r2.json
```

Package r2 binds the verified analytic asset to an immutable local package. Its
manifest SHA-256 is
`756286b624de53823a2af2c26344a15dcf02070c048f5d1d02ec3f65a97d5120`; the
package-binding SHA-256 is
`f825c268c80ebafaafc37cda26557c4ad0513211d1e231f2e73c5dc282be23ad`. The
STAC, Portolan, HTTP/DuckDB, integrity, binding, and final verification reports
are saved in `evidence/`. STAC Node validated both catalog and collection;
Rashid reported zero errors, with one informational upstream-canonical-link
note. The package snapshots helper `package_release.py` at commit
`7cc922857065883d1803a6892a5a160ce5a4f722`; it pins `add_spatial_bounds.py`
and `test_spatial_bounds.py` to exact c18 source bytes. The same immutable
asset hash as r1 is used.

The raw file's GeoParquet global bounds are `[-179.99791666699997,
-55.87708333299997, 179.99791666700003, 83.58958333300006]`. All audited
geometry types are MultiLineString. The package helper made an APFS clone of
the final analytic asset and verified its hash. The source archive download
cache was removed after two successful complete source validations; it can be
reacquired from the pinned public Figshare file URL using `acquire.py`.

## Spatial helper sidecar

The r2 manifest snapshots the spatial helper and focused test from the exact
c18 revision, in addition to carrying the current locked package helper. The
sidecar in `evidence/spatial-helper-c18/` carries the exact helper source, test,
`pyproject.toml`, and `uv.lock`; its manifest and hash file make those bytes
independently verifiable. Verify the sidecar hashes by running
`shasum -a 256 -c sidecar-sha256.txt` from that directory.
