# GEE release comparisons

These scripts compare immutable analytical releases with existing Earth Engine
vector tables. They do not build or upload datasets. The 2026-11-06 criteria and
request plans are in `research/gee-release-validation-20261106/`.

The large collections use a systematic global sample and a separately measured
complete collection count. Counts do not prove feature-by-feature completeness.
A sample pass does not establish exhaustive parity or scientific accuracy.
River-plastic inputs retain their separate exhaustive comparator and capture.

## Reproduce the selection

Use the pinned Python 3.12 environment:

```sh
uv sync --locked --project scripts/gee_validation --python 3.12
scripts/gee_validation/.venv/bin/python scripts/gee_validation/sample.py \
  --data-root /path/to/data-publications \
  --output .local/gee-new-samples
```

`--data-root` contains the ignored release packages named in each canonical
record. The exporter checks the complete Parquet SHA-256, manifest checksum and
row count before reading samples. It selects four positions in each of 128
systematically distributed row groups, with the first ten producer identifiers
added for the lake and Free-Flowing Rivers layers. No GEE values influence
selection. Decimal source values remain exact decimal strings in sample files.
The sample records the code revision, source pins and environment lock.

The initial samples were generated at commit `883ebbf`. Later changes explicitly
bind anonymous GRWL results to individual spatial queries and permit a 180-second
synchronous count request for the two large river tables, after preserving the
first Free-Flowing Rivers timeout. Selection and scientific thresholds remain
unchanged. Regeneration under a different commit changes provenance hashes; it
must not overwrite or masquerade as the original sample.

## Capture existing GEE features

Review generated plans, copy them into a new research directory and commit them
before retrieval. Plans explicitly name the quota project; use a separately
reviewed plan when changing projects. Authentication uses existing Application
Default Credentials. Credential values are never saved in captures or reports.

```sh
scripts/gee_validation/.venv/bin/python scripts/gee_validation/capture.py \
  --plan research/your-review/plans/hydrolakes-plan.json \
  --output .local/gee-new-hydrolakes
```

Run plans sequentially. They allow only metadata/feature GET requests and a
synchronous `Collection.size` expression. No exports, batch tasks, uploads or
product creation occur. Feature requests keep a 45-second deadline. Counts for
Free-Flowing Rivers and GRWL may use 180 seconds, with no automatic retries.
Pagination, elapsed time, response size and total request limits are enforced.
Every attempt uses a new directory and retains a complete or incomplete receipt.

Raw GEE responses and local sample payloads remain in ignored `.local/` storage.
Commit small request plans, response inventories, comparison reports and failure
evidence. A Git checkout alone does not contain the raw response cache.

GRWL has no safe global identity based only on `segmentID`. The sample uses the
original longitude, latitude, segment ID and observation index as a compound key.
`grwl_key_inventory.py` checks the selected keys against the complete local file.
Each target is assigned to its original spatial query; anonymous features seen
through overlapping queries are not pooled as new records.

## Replay offline

```sh
scripts/gee_validation/.venv/bin/python scripts/gee_validation/compare.py \
  --sample .local/gee-new-samples/hydrolakes-sample.json \
  --capture .local/gee-new-hydrolakes \
  --plan research/your-review/plans/hydrolakes-plan.json \
  --criteria research/gee-release-validation-20261106/criteria.json \
  --report .local/gee-new-hydrolakes-comparison.json

scripts/gee_validation/.venv/bin/python -m unittest discover \
  -s tests -p 'test_gee_*comparison.py' -v
scripts/gee_validation/.venv/bin/python -m unittest discover \
  -s tests -p test_gee_request_contract.py -v
```

A nonzero comparison exit is retained evidence. The report separates capture
integrity, count and identity checks, attribute comparisons, strict geometry
parity, and bounded geometry diagnostics. Source float32 serialization is checked
at float32 precision; integers, nulls, strings and units are not normalized to
make discrepancies disappear. Geometry diagnostics do not replace strict failures.
The source GeoParquet and display archives remain unchanged.


## Explanatory diagnostics and the retained review

The [completed six-layer review](../../research/gee-release-validation-20261106/README.md)
keeps strict failures separate from explanations. The diagnostic criteria were
committed after the strict comparison and before running the additional geometry
and attribute analyses. A follow-up hypothesis is not a retroactive pass threshold.

With `GEE_CACHE_ROOT` pointing at the retained `gee-release-validation-20261106`
cache, for example:

```sh
scripts/gee_validation/.venv/bin/python scripts/gee_validation/diagnose_attributes.py \
  --sample "$GEE_CACHE_ROOT/samples-r1/hydrolakes-sample.json" \
  --capture "$GEE_CACHE_ROOT/hydrolakes-r1" \
  --plan research/gee-release-validation-20261106/plans/hydrolakes-plan.json \
  --report .local/new-hydrolakes-attributes.json

scripts/gee_validation/.venv/bin/python scripts/gee_validation/diagnose_geometry.py \
  --sample "$GEE_CACHE_ROOT/samples-r1/hydrolakes-sample.json" \
  --capture "$GEE_CACHE_ROOT/hydrolakes-r1" \
  --plan research/gee-release-validation-20261106/plans/hydrolakes-plan.json \
  --criteria research/gee-release-validation-20261106/criteria.json \
  --followup research/gee-release-validation-20261106/followup-criteria.json \
  --comparison "$GEE_CACHE_ROOT/comparisons-r1/hydrolakes.json" \
  --report .local/new-hydrolakes-geometry.json

python3 research/gee-release-validation-20261106/summarize.py --check
```

Use the committed `free-flowing-rivers-plan-r2.json` and `grwl-raw-plan-r2.json`
for those actual captures. Geometry diagnostics query vertices and midpoints
against independent segments, preserving line and ring breaks. They do not claim
a continuous distance bound or unchanged topology. `trace_lake_spikes.py` extracts
the source vertices at the three large lake outliers; `grwl_key_inventory.py`
checks sample-key multiplicity in the full local raw release. Neither edits data.

The report summary is generated offline by `research/gee-release-validation-20261106/summarize.py`.
Its integer-value statistics are explicitly posthoc observations from the retained
attribute diagnostics. Reports remain immutable evidence; a new evaluation uses
a new output directory. CI exercises the request, identity, precision, geometry,
provenance and diagnostic fault cases without credentials or GEE requests.
