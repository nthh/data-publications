# Global river plastic inputs

## GEE review — 2026-11-06

The historical full GEE capture replay matches all 53 attributes and nulls across 40,760 rows with the documented coincident-group contract; maximum point displacement is 0.3495 m. Fresh metadata/count match, but no fresh exhaustive feature capture was made. Strict coordinate parity remains failed. See the [complete comparison review](../../research/gee-release-validation-20261106/README.md) and [structured evidence](../../research/gee-release-validation-20261106/summary.json). The validated release is [public on Source Cooperative](https://source.coop/nthh/river-plastic-inputs); hosting checks do not change these scientific-comparison findings.


Lebreton et al. (2017), [Figshare v6](https://doi.org/10.6084/m9.figshare.4725541.v6),
40,760 global river input points for the **2010 model baseline**. This is distinct
from the Meijer (2021) dataset. The canonical [dataset.yaml](dataset.yaml) holds
source checksums, licensing, build settings, triage and publication state.

The original data and derivatives are **CC BY 4.0**, attributed to the producer.
The conversion scripts use the repository's Apache-2.0 software license.
Folia is the processor; the verified release is hosted under `nthh` on Source Cooperative. Main Portolan registry submission requires a separate decision.

## Run from a clean checkout

Run the current conversion and validation workflow from a clean checkout. The
recorded `figshare-v6-r2` conversion used commit
`4c54a01451967421bf17b1346cd749c0738efdde`; this is a historical provenance
identifier, not a checkout target in the fresh public history. The
[provenance archive](provenance/README.md) preserves the exact retained source
files by checksum. A new run records its current commit and canonical record
snapshot, so package provenance metadata can differ even when data bytes match.

Run commands from the repository root. Install Python via uv, Node >=22.12,
**tippecanoe 2.79.0**, and the native `pmtiles` CLI. The Python and npm lockfiles
pin the library environments; the manifest records the native converter's hash.
The same-machine rehearsal does not establish cross-platform byte identity.

```sh
uv sync --locked --project datasets/river-plastic-inputs
npm ci --prefix datasets/river-plastic-inputs
mkdir -p .local/river-plastic-inputs
curl --fail --location https://ndownloader.figshare.com/files/7714864 \
  --output .local/river-plastic-inputs/PlasticRiverInputs.zip
uv run --locked --project datasets/river-plastic-inputs python datasets/river-plastic-inputs/reproduce.py \
  --source .local/river-plastic-inputs/PlasticRiverInputs.zip \
  --work .local/river-plastic-inputs/rehearsal-1
```

The workflow verifies the source size and both checksums, builds GeoParquet and
PMTiles, checks every original numeric cell and coordinate, validates STAC and
Portolan metadata, checks local HTTP range/CORS/subset access, evaluates the
paper's published summaries, rebuilds every asset and runs fault tests. It
refuses existing output directories and uncommitted dataset workflow changes.
Dependency installation and schema validation may read public network resources;
it makes no GEE requests or uploads.

Without `--gee-capture`, the result is explicitly `passed_conversion_only`;
GEE replay and final packaging remain unrun. The historical 70 MB GEE response
capture is retained locally but **not yet publicly hosted**. If that exact cache
is available, append `--gee-capture .local/river-plastic-inputs/gee-20261030-r1`
and choose a new `--work` directory. That replays both the expected strict
geometry failure and the separately declared diagnostic before packaging.
See [gee/README.md](gee/README.md) for capture integrity and the optional live
capture command; new live work needs a registered contract and an explicit
project, credentials and authorization.

Reports and logs appear beneath the chosen work directory. A complete run also
produces an immutable ZIP and checksum receipt. Small final reports belong in
`releases/<release>/`; the bulk data, logs, raw pages and archives remain ignored.
The original `evidence/` is historical and must not be overwritten. Each release includes its exact `dataset.yaml` snapshot; validation checks that snapshot hash and the current effective source/build settings separately, so later publication-status updates do not invalidate old data.

Individual steps are executable Python scripts: `build.py`, `validate.py`,
`check_publication.py`, `gee/compare.py`, `gee/diagnose_geometry.py`, `package.py`,
and `serve.py`. Each accepts `--help`. `reproduce.py` supplies the documented
ordering and binds the reports to the exact release manifest.

## Interpretation and validation

All 53 original numeric fields retain their DBF precision as Decimal values.
Annual `i_low`, `i_mid`, `i_high` are tonnes/year; monthly `i_*` are tonnes/month;
runoff is mm/day, `mpw` is kg/year and `area` is square metres. The four rows with
missing estimates retain 204 null cells. The source has 19 coincident-coordinate
pairs; all 40,760 records are retained, at 40,741 distinct positions. `source_row`
is the original one-based row ordinal, not a watershed identifier.

GeoParquet is the analytic representation. PMTiles is for display: it quantizes
positions, stores selected values as doubles and thins points at lower zooms.
All source IDs must occur at maximum zoom. Use GeoParquet for global totals.

The paper-summary checks pass. The captured GEE values and nulls agree exactly;
strict coordinate parity fails, with displacement up to 0.3494564 m. The separate
one-metre geodesic and exact coincident-group multiset diagnostic passes. Source
geometry remains unchanged. GEE source-version/ingestion provenance is unknown;
its catalog's kg/year prose conflicts with the source tonnes/year values.
These are consistency checks, not independent observational validation of the model.

[VALIDATION.md](VALIDATION.md) records criteria, history and limits.
[provenance/](provenance/README.md) preserves the exact prior source snapshots
by hash without importing the original repository's private Git history.

## Source selection audit

Complete Lebreton2017/2010baseline source retained. This is a historical model. Strict GEE geometry equality failed; a separately declared coincident-group comparison passed with sub-metre displacement. The [2026-11-02 source audit](../../research/grwl-raw-release-20261102/source-audit/river-audit.md) distinguishes full source fidelity from scientific accuracy and records the limits of rebuild/GEE evidence.
