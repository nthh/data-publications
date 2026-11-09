# Global river and lake data

Browse five published global datasets in the [Portolan Browser](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/catalog.json), or open the [STAC catalog](https://nthh.github.io/data-publications/catalog.json). Each product is hosted on [Source Cooperative](https://source.coop/) as GeoParquet for analysis and PMTiles for map display. LakeATLAS has separate polygon and pour-point layers. Source and release identity, vintage, fields, attribution, and data-license terms are documented with each dataset below.

| Dataset | Source Cooperative | What it contains and dataset documentation |
| --- | --- | --- |
| River plastic inputs | [Open product](https://source.coop/nthh/river-plastic-inputs) | 40,760 river-mouth points with modelled annual plastic inputs for the 2010 baseline. [Dataset guide](datasets/river-plastic-inputs/README.md) |
| HydroLAKES | [Open product](https://source.coop/nthh/hydrolakes) | 1,427,688 global lake polygons from HydroLAKES v1. [Dataset guide](datasets/hydrolakes/README.md) |
| Free-Flowing Rivers | [Open product](https://source.coop/nthh/free-flowing-rivers) | 8,477,883 reaches from the WWF global river connectivity assessment. [Dataset guide](datasets/free-flowing-rivers/README.md) |
| LakeATLAS | [Open product](https://source.coop/nthh/lakeatlas) | Global v1.0 lake polygons and pour points with hydro-environmental attributes. [Dataset guide](datasets/lakeatlas/README.md) |
| GRWL raw vectors | [Open product](https://source.coop/nthh/grwl-raw) | 64.6 million detailed river observations from GRWL V01.01. The raw observations are published; the simplified GRWL summary is withheld after an upstream geometry review. [Dataset guide](datasets/grwl-raw/README.md) |

The product pages link to the hosted assets and release details. For exact source identity, edition, field definitions, null handling, and license conditions, use each guide's canonical `dataset.yaml` and release documentation. The catalog links distinguish these analytical files from the separately hosted map-display packages.

## Query the river-plastic GeoParquet

With [uv](https://docs.astral.sh/uv/getting-started/installation/) installed, this example reads the hosted 6.36 MB file directly; it does not require cloning this repository or downloading a local copy. It returns the five largest non-null `i_mid` values. `i_mid` is modelled annual input in tonnes for the 2010 baseline, and `source_row` identifies the original source record.

```sh
uv run --no-project --with duckdb==1.5.2 python - <<'PY'
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs")
con.execute("LOAD httpfs")
con.sql("""
    SELECT source_row, i_mid AS annual_input_tonnes
    FROM read_parquet('https://data.source.coop/nthh/river-plastic-inputs/releases/figshare-v6-r2/river-plastic-inputs/river-plastic-inputs.parquet')
    WHERE i_mid IS NOT NULL
    ORDER BY i_mid DESC, source_row
    LIMIT 5
""").show()
PY
```

DuckDB's [HTTP and cloud storage guide](https://duckdb.org/docs/1.5/guides/network_cloud_storage/http_import) describes remote file access. Use GeoParquet for complete analytical attributes and geometries. PMTiles are display derivatives: they may simplify or select features at lower zooms and should not be treated as complete analytical data.

## Interpretation and reuse

These releases preserve and package producer data; they are not independent scientific accuracy assessments. GEE is a comparison source, and its representation may differ from the selected producer release. The 2026 comparison found matching global counts and sampled source records, but strict representation parity failed for the published datasets. Differences in fields, nulls, numeric precision, or geometry vary by dataset; source geometry and values were retained. The [comparison review](research/gee-release-validation-20261106/README.md) explains methods and limits. The [public release record](research/source-publication-20261107/public-release-r1.json) links hosted and catalog validation evidence.

Repository-authored software is licensed under Apache-2.0. That license does not grant rights to upstream data. Dataset-specific licenses, attribution, and any redistribution conditions differ; review the linked dataset guide and canonical record (`dataset.yaml`) before reuse. See [NOTICE](NOTICE) and [publishing guidance](docs/publishing.md).

## For maintainers

The dataset guides describe dataset-specific rebuilding and validation. For catalog metadata and generation, see the [catalog workflow](docs/catalog-workflow.md). The generated [candidate backlog](CANDIDATES.md) and [shortlist](SHORTLIST.md) are research leads, not available products or commitments to publish. Discovery-only records live under `candidates/`; selected build and preparation workspaces live under `datasets/`. See the [candidate guide](candidates/README.md) and [dataset workspaces](datasets/README.md); promote a record with `git mv`.

From the repository root, the core repository checks are:

```sh
uv sync --locked
uv run --locked python scripts/catalog.py --check
uv run --locked python scripts/publication_catalog.py check
uv run --locked python scripts/check_provenance.py
```
