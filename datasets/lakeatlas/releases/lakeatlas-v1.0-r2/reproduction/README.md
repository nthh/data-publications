# LakeATLAS r2 local package inputs

This release has two analytic assets: complete LakeATLAS lake polygons and the separate producer pour-point layer. The source-order conversions and final spatially ordered GeoParquet assets are compared independently. The spatial-order companion carries all original values and WKB, with row order deterministically derived from WGS84 bbox-center Hilbert keys and `OBJECTID` as the tie-breaker; validation restores identifier order and compares every source attribute, null, and per-feature WKB hash/length. No geometry repair or simplification is performed.

The `package-spec-template.json` and `fidelity-normalizer-template.json` use placeholders so they contain no machine-local paths. Materialize new local input files only after primary and clean final outputs have completed validation and byte-for-byte comparison:

```sh
REPO_ROOT="$(git rev-parse --show-toplevel)"
RECIPE=datasets/lakeatlas/releases/lakeatlas-v1.0-r2/reproduction
ARTIFACT_ROOT=/path/to/lakeatlas-v1.0-r2-artifacts
CLEAN_CHECKOUT=/path/to/detached-clean-lakeatlas-checkout
FIDELITY_ROOT=/path/to/portable-lakeatlas-fidelity
PORTABLE_EVIDENCE="$FIDELITY_ROOT/portable-evidence"
PACKAGE_OUTPUT=/path/to/new-lakeatlas-package
uv run --locked --project scripts/release_tools python "$RECIPE/materialize_release_inputs.py" fidelity \
  --artifact-root "$ARTIFACT_ROOT" --clean-checkout "$CLEAN_CHECKOUT" \
  --output "$FIDELITY_ROOT/normalizer-input.json"
uv run --locked --project scripts/release_tools python research/hydro-releases-20261031/bind_fidelity.py \
  "$FIDELITY_ROOT/normalizer-input.json" --output-dir "$FIDELITY_ROOT/normalized"
uv run --locked --project scripts/release_tools python "$RECIPE/prepare_portable_evidence.py" \
  --artifact-root "$ARTIFACT_ROOT" --fidelity-root "$FIDELITY_ROOT/normalized" \
  --repo-root "$REPO_ROOT" --clean-checkout "$CLEAN_CHECKOUT" \
  --output-dir "$PORTABLE_EVIDENCE"
uv run --locked --project scripts/release_tools python "$RECIPE/materialize_release_inputs.py" package \
  --artifact-root "$ARTIFACT_ROOT" --fidelity-root "$FIDELITY_ROOT/normalized" \
  --portable-evidence-root "$PORTABLE_EVIDENCE" --package-output "$PACKAGE_OUTPUT" --output "$FIDELITY_ROOT/package-spec.json"
uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  "$FIDELITY_ROOT/package-spec.json"
uv run --locked --project scripts/release_tools python scripts/release_tools/package_release.py \
  --verify "$PACKAGE_OUTPUT"
```

The fidelity binder must pass before packaging. The redactor writes a fresh immutable evidence directory under the ignored local fidelity workspace; package materialization reads that exact directory and will not overwrite tracked evidence. Package verification includes the bounded local HTTP Europe-window subset, with IDs and WKB checked against the local Parquet rows. The fixed four-window bbox row-group pruning check is separate evidence and must pass for both primary and clean outputs. Package manifests generate per-asset name/type schema inventories from the final GeoParquet files. The producer catalog and technical PDF remain the authorities for per-column units and licensing notices; no inferred column license labels are generated. A package remains unprepared until all fidelity, clean rebuild, pruning, binding and package verification gates pass. This recipe does not upload or publish it.
