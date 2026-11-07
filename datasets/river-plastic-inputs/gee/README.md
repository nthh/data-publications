# Reproducing GEE validation

The default workflow replays the cached, hash-pinned GEE capture entirely offline. The raw capture is about 70 MB and currently lives only in the local ignored `.local/river-plastic-inputs/gee-20261030-r1/` directory; it is not publicly hosted. The captured response bytes, strict comparison and unique-only diagnostic remain unchanged. The provenance inventory retains the original capture implementation and lockfile bytes so their receipt hashes can still be verified after this repository migration.

## Build the local source bundle

From the repository root, create the release directory from the cached source archive if it is not already available:

```sh
uv run --frozen --project datasets/river-plastic-inputs \
  python datasets/river-plastic-inputs/build.py \
  --source .local/river-plastic-inputs/PlasticRiverInputs.zip \
  --output .local/river-plastic-inputs/figshare-v6-r1
```

The build verifies the source archive against the tracked source pin. The resulting release directory is local validation input, not a public release.

## Replay the cached capture

Use the repository product environment for comparison and geometry diagnostics. Reports are written beside the cached capture but outside its response files:

```sh
uv run --frozen --project datasets/river-plastic-inputs \
  python datasets/river-plastic-inputs/gee/compare.py \
  .local/river-plastic-inputs/figshare-v6-r1 \
  .local/river-plastic-inputs/gee-20261030-r1 \
  --report .local/river-plastic-inputs/gee-strict-repeat.json \
  --details .local/river-plastic-inputs/gee-strict-repeat.jsonl

uv run --frozen --project datasets/river-plastic-inputs \
  python datasets/river-plastic-inputs/gee/diagnose_geometry.py \
  .local/river-plastic-inputs/figshare-v6-r1 \
  .local/river-plastic-inputs/gee-20261030-r1 \
  --coincident-groups \
  --report .local/river-plastic-inputs/gee-diagnostic-repeat.json \
  --details .local/river-plastic-inputs/gee-diagnostic-repeat.jsonl

uv run --frozen --project datasets/river-plastic-inputs \
  python datasets/river-plastic-inputs/gee/test_compare.py \
  --report .local/river-plastic-inputs/gee-fault-tests-repeat.json
```

The strict comparison intentionally exits nonzero because GEE coordinates differ from source coordinates beyond the strict tolerance. The unique-only geodesic diagnostic also intentionally exits nonzero because it cannot assign the 19 coincident source-coordinate pairs to individual source rows. The final diagnostic preserves both failures and checks those pairs as exact attribute multisets. It verifies 40,722 unique records and 38 records in 19 coincident groups, with all 53 attributes and nulls matching exactly. It does not assert row identity within a coincident group or establish the cause of the measured coordinate displacement; upstream ingestion provenance remains undocumented.

## Optional live capture

`fetch.py` performs bounded read-only GET requests. It requires both `--project` and an explicit quota project in the selected contract. The default contract is the historical pinned contract; use a separately reviewed and committed contract when a different project is needed. The fetcher refuses an existing output directory, follows only server-provided page tokens, and stores no credentials. No live capture is needed to replay or verify the cached evidence.

```sh
uv sync --frozen --project datasets/river-plastic-inputs/gee
datasets/river-plastic-inputs/gee/.venv/bin/python \
  datasets/river-plastic-inputs/gee/fetch.py \
  --contract path/to/committed-gee-contract.json \
  --project "$GCP_PROJECT_ID" \
  --output .local/river-plastic-inputs/gee-new-capture
```

The GEE response cache is currently local-only and has not been published. Do not treat the optional live-capture command as part of offline validation.
