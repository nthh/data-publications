# PMTiles display builder

This tool has its own locked Python environment in `pyproject.toml` and
`uv.lock`. It pins PyArrow, Shapely, NumPy, PMTiles, Mapbox Vector Tile,
PyProj, and DuckDB. Tests use the standard-library `unittest` runner. It also
requires Tippecanoe v2.79.0 with the SHA-256 in
`datasets/grwl/tippecanoe.lock.json`, and the local `pmtiles` CLI. The source
GeoParquet files are never rewritten.

The builder streams Arrow batches into Tippecanoe through `/dev/stdin`; it does
not write an intermediate GeoJSON file. Tippecanoe output and its temporary
directory are inside the new display package. It enforces free-disk and task
storage ceilings while streaming. Failed runs are retained in a separate
attempt directory and must not be relabeled as a prepared release.

Run from the repository root with the prepared products in a local data root:

```sh
uv sync --locked --project scripts/display_tools
uv run --locked --project scripts/display_tools python scripts/display_tools/build_display.py \
  hydrolakes \
  --data-root /path/to/data-publications/.local \
  --output /path/to/data-publications/.local/hydrolakes/display/display-v1
```

The other keys are `free-flowing-rivers`, `lakeatlas-polygons`, and
`lakeatlas-pour-points`. Both LakeATLAS assets share the same package output.
The independent archive validator is `scripts/validate_display.py`; a package
remains provisional until that geometry and attribute validation passes.

Run the focused source-stream, fault, and native PMTiles fixture suite with:

```sh
uv run --locked --project scripts/display_tools python -m unittest discover \
  -s tests -p test_display_tools.py -v
```

Native point, line, and polygon roundtrips run when Tippecanoe and `pmtiles` are
installed; otherwise that one native test is skipped.

Before launching Tippecanoe, each build writes `reports/<layer>.input-provenance.json`
with portable command arguments, input hashes, Python/platform/package versions, and
the Tippecanoe and PMTiles binary hashes and versions. Exact builder bytes and the
active environment and Tippecanoe lock files are copied under the package's
`workflow/` directory, so the report stays tied to the code and lock files used for
that build without writing snapshots into the repository during production runs.

To save the point, line, and polygon fixture rebuild hashes for comparison
with another checkout, run:

```sh
uv run --locked --project scripts/display_tools python scripts/display_tools/fixture_roundtrip.py \
  --report .local/pmtiles-display-fixture-rebuild.json
```

The fixture runner rebuilds each synthetic archive twice with relative paths
and reports whether each PMTiles file is byte-identical. This checks fixture
reproducibility, not a clean production rebuild.

Feature properties are limited to the stable source ID, declared display
attributes, and exact source bbox scalars (`_src_xmin`, `_src_ymin`,
`_src_xmax`, `_src_ymax`). The analytic GeoParquet remains authoritative for
complete attribute lookup. Per-feature minimum zoom uses the frozen threshold
schedule in `research/pmtiles-all-20261102/criteria.json`; null and unknown
metrics appear at zoom 12.

Use `scripts/display_tools/finalize.py` only after independent geometry and real
browser checks pass. It reruns native archive verification and marks the package
prepared last. See the [complete workflow](../../docs/display-derivatives.md),
including the limits on scientific accuracy and production rebuild claims.
