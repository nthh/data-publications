# PMTiles display derivatives

Every prepared vector product has a PMTiles map layer. GeoParquet remains the
analytical source, with unchanged geometry, attributes, units and source IDs.
A display release can change independently from the analytical release, under
the same Source Cooperative product.

The editable inventory is `datasets/<id>/dataset.yaml`. Its optional
`publication.display` points to a checksum-bound generated manifest under
`datasets/<id>/display/<display-release>/`. Bulk archives stay in ignored local
storage. Build reports, independent validation results and reviewed screenshots
belong in Git; secrets, raw downloads and runtime paths do not.

## Build from verified sources

The shared [Python builder](../scripts/display_tools/README.md) pins its own
libraries. It checks the immutable source checksum, streams Arrow batches to
Tippecanoe, converts the intermediate MBTiles to PMTiles, then reads the actual
PMTiles archive to account for source IDs and selected attributes. It never
rewrites the analytical files.

```sh
uv sync --locked --project scripts/display_tools
uv run --locked --project scripts/display_tools python \
  scripts/display_tools/build_display.py hydrolakes \
  --data-root /absolute/data-root \
  --output /absolute/data-root/hydrolakes/display/display-v1
```

Other keys are `free-flowing-rivers`, `lakeatlas-polygons`, and
`lakeatlas-pour-points`. The two LakeATLAS layers share a display package. The
river-plastic PMTiles are reused with their original checksum. GRWL now uses a
separate display-only dateline correction, built by
`datasets/grwl/build_display.py` and validated by the independent
`datasets/grwl/validate_display_wrap.py`. Its original PMTiles remain historical
evidence. See the [GRWL workflow](../research/grwl-straight-segments-20261102/README.md)
for z0–10, exact source-ID accounting, periodic geometry checks and dateline
browser controls. The shared z12 finalizer below applies to the hydrography
packages; GRWL has its own dataset-specific finalization gate.
Native conversion uses the recorded Tippecanoe binary and PMTiles CLI; the
current production evidence is from macOS. Other native binaries need their own
recorded identity and verification, not a claim that the macOS binary was used.

The frozen [criteria](../research/pmtiles-all-20261102/criteria.json) specify
z0–12, extent 4096, simplification 1 and explicit per-feature minimum zoom.
Lake area in km² controls both lake layers; mean discharge in m³/s controls FFR.
The thresholds are 10,000→z0, 1,000→z2, 100→z4, 10→z6, 1→z8, 0.1→z10,
and 0→z12. Unknown metrics appear at z12. Arbitrary tile-size and feature-count
dropping and tiny-polygon aggregation are disabled.

All source IDs must be accounted for at z12. Any absent empty geometry,
zero-dimension geometry or quantization collapse is enumerated by ID and reported
as an exception; it must not be described as complete rendered coverage.
Unexpected losses fail. Selected attributes and original source bbox scalars
are checked against source values by ID. GeoParquet contains the full fields.

Run one production build at a time, with two Tippecanoe threads, at least 40 GiB
free at start, a 15 GiB stop floor, and a 12 GiB task storage ceiling. Retain
failed-attempt reports. Remove only inventoried, reproducible task scratch after
saving the relevant checksums; never delete validated analytical releases to
make a display build fit.

## Independently validate the actual archive

```sh
uv run --locked --project scripts/display_tools python scripts/validate_display.py \
  --manifest /absolute/display-package/manifest.json \
  --asset-id hydrolakes-1 \
  --source /absolute/analytic-package/assets/hydrolakes-polygons.parquet \
  --report /absolute/new-oracle-report.json
```

The separate validator checks input and archive hashes and decodes PMTiles MVT
geometry with a different decoder from the builder's accounting pass. It compares
fixed source-ID samples within the frozen global and five regional windows,
using the lowest eligible 32 global IDs and eight per regional window. Eligibility
limits each source bbox to 64 z12 tiles; this excludes very large geometries from
this sampled check. It records the actual IDs and limitations.

Geometry is compared in Web Mercator using a 30 m maximum Hausdorff displacement.
Each decoded fragment is clipped to its tile core, excluding buffer margins,
before reconstruction. This tests display conversion, not observational accuracy,
hydrological correctness or agreement with a GEE asset. The full ID and selected
attribute accounting is separate from this sampled geometry check.

HydroLAKES preserves `Hylak_id` as the native MVT feature ID. Its first build used
Tippecanoe's `--use-attribute-for-id`, which consumes the duplicate ID property.
The explicit [ID diagnostic](../research/pmtiles-all-20261102/id-encoding-diagnostic.json)
records this representation. The viewer restores the display property from the
checked feature ID and rejects conflicts. Other new layers preserve both forms.

## Check the viewer and finalize

Serve a provisional archive through the local static-object harness, bound to its
exact checksum. Run the [browser checks](../scripts/cloud_viewer/README.md) against
fresh global and regional contexts for every layer: Great Lakes for the new
hydrography archives and Atlantic coast for the existing river-plastic layer.
The [coastal-control diagnostic](../research/pmtiles-all-20261102/coastal-control-diagnostic.json)
records why the original inland box was unsuitable for coastal source points.
Require nonzero rendered features, HTTP 206 ranges, CORS, no whole-file data GETs,
and at most 128 MiB of
observed data response bodies per case. Test source-ID attribute lookup and
switching between LakeATLAS layers. No public-hosting claim follows from loopback
success.

After all evidence passes, the finalizer verifies the bindings, copies reviewed
reports, inventories package files and writes `status: prepared` last:

```sh
uv run --locked --project scripts/display_tools python scripts/display_tools/finalize.py \
  --package /absolute/display-package \
  --geometry-report hydrolakes-1=/absolute/new-oracle-report.json \
  --browser-report /absolute/browser-validation.json
```

Copy the generated manifest and reviewed small evidence into the dataset's display
evidence directory, set its canonical `publication.display` checksum, then run
`catalog.py --write` and `source_products.py write`. Stage the analytical package
and its `--display-package` together into a new exact upload plan. Historical
plans and analytical release evidence remain immutable. See
[Source product preparation](source-cooperative-products.md#versioned-display-packages).

The final current viewer must be prepared by the normal launcher from those
canonical records and that exact plan. Provisional runtime mappings are diagnostic
only. A clean-checkout rehearsal checks the committed code, locked environments,
fixture PMTiles reproducibility and browser integration. Production archives are
not described as independently rebuilt unless that larger rebuild actually ran.

## GRWL width styling

`width_mean` is in metres. The shared client expression distinguishes 50 m,
200 m and 1,000 m widths at every tested zoom. It has a visible thin fallback
for missing/nonpositive widths and caps the symbol at 1,000 m. The legend states
that these are exaggerated map symbols, not bank outlines at map scale.

Generate the portable style from the same expression used by the viewer:

```sh
node scripts/cloud_viewer/export-grwl-style.mjs --check
```

The original versioned supplement remains historical evidence. The current GRWL
display package contains the same measured-width expression with a relative URL
to its corrected archive. Analytical bytes are unchanged. Portable styles contain relative archive URLs, which a
client resolves against the style URL before applying its PMTiles protocol.

## Verification boundaries

CI runs record, staging, synthetic conversion, independent geometry fault and
viewer tests with locked environments, plus the frontend build and generated
style check. Native fixture roundtrips run when Tippecanoe and PMTiles are present;
a skip is not a native conversion pass. Real-data coverage, geometry and Chrome
checks require the local packages and are recorded separately. New display work
does not add GEE parity, public hosting or registry submission evidence.
