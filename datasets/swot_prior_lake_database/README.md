# SWOT Prior Lake Database scientific v2.03

Current status: metadata-qualified, not converted or prepared. The live [producer STAC collection](https://hydroweb.next.theia-land.fr/api/catalog/stac/collections/SWOT_PRIOR_LAKE_DATABASE) identifies `2.03 Sci`, SQLite and ETALAB 2.0. The saved inventory contains **61 v2.03 tiles totaling 29,990,277,120 provider-declared bytes** across nine regions. The collection total of 122 also includes 61 v2.02 tiles; those older files are excluded from the selected scope. Older HTML descriptions are stale.

This is the full scientific lake-reference database used in SWOT processing. The separate Light and Geometries variants are not equivalent. A conversion must preserve lake identifiers, geometry and the scientific auxiliary tables and relationships; it must not silently reduce the database to a polygon-only layer.

Anonymous public metadata requests and a 16-byte HTTP 206 read of the smallest tile succeeded; the latter returned a SQLite header. The metadata contains explicit per-file MD5 values and byte sizes. No complete tile or its checksum has yet been validated. A source-inspection attempt stopped before download with 39.37 GiB free, below its recorded 40 GiB start threshold. The full original source also exceeds this task's 8 GiB retained-storage budget. A streaming/retention plan must be established before selecting a full build.

Reproduce metadata capture to a new path:

```sh
python research/gdw-swot-preparation-20261101/capture_swot.py --output .local/new-swot-inventory.json
```

After the disk threshold is met, inspect the bounded AU_55 sample using a new report and ignored storage directory:

```sh
python research/gdw-swot-preparation-20261101/inspect_swot_sample.py \
  --inventory research/gdw-swot-preparation-20261101/swot-v203-inventory.json \
  --output .local/new-swot-au55-report.json \
  --storage-dir .local/swot-qualification/AU_55
```

The sample script requires exact expected size and the producer's MD5 before SQLite inspection, records SHA-256, requires a passing SQLite integrity check, and reads schema, keys and counts without loading extensions. It refuses existing files and preserves failed reports/partial downloads. It never claims global validity from one tile. [Criteria and evidence](../../research/gdw-swot-preparation-20261101/README.md); [canonical record](dataset.yaml).
