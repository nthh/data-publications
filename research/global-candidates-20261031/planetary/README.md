# Microsoft Planetary Computer inventory

This lane retains the current public Microsoft Planetary Computer STAC collection listing, a deterministic normalized view, and metadata-only review suggestions. It does not modify canonical dataset records.

## Capture and reproduce

From the repository root, explicitly fetch the collection-list endpoint (collection pages only; no items or assets):

```sh
python3 research/global-candidates-20261031/planetary/capture.py --fetch --output-dir research/planetary-next
```

`--fetch` requires a new, nonexistent output directory and refuses an existing path before making requests. Keep the committed capture intact.

Offline checking from retained `retained/page-*.json` and `capture-manifest.json` (the default is read-only):

```sh
python3 research/global-candidates-20261031/planetary/capture.py
```

Offline check that the committed normalized inventory reproduces from the retained capture:

```sh
python3 research/global-candidates-20261031/planetary/capture.py --check
```

The capture uses only Python's standard library. It records the original HTTP response digest and byte count, retrieval time, HTTP date/last-modified where supplied, collection IDs and metadata, and a bounded failure list. The stored page is normalized JSON with signed URL query credentials removed; the manifest separately records its digest, bytes and redacted JSON paths. It cannot replay or independently re-hash the original response body. Two signed thumbnail URLs were redacted in this capture. Fetch limits are 120 HTTP requests and 30,000,000 response bytes; the observed capture used 1 request and 1,774,281 bytes. Query parameters and fragments are not retained in manifest URLs. No item/asset metadata, signing operation, token, job, upload, or paid request was used.

## Inventory and review

- `inventory.json`: all normalized collection records returned by the captured public STAC API, with per-page hashes and timestamps.
- `retained/page-001.json`: normalized response metadata with two signed thumbnail query strings removed, retained for offline re-normalization.
- `capture-manifest.json`: retrieval provenance and bounded failures.
- `reviewed.json`: 38 candidate suggestions plus separate lists of 64 visibly regional/latitude-limited entries, 37 broad-world-bbox entries not promoted on bbox alone, and 0 entries lacking usable bbox metadata.

Each candidate includes the PC API collection URL and official dataset overview URL, extent and coverage notes, collection-declared asset media types, MIME/role-derived `format_labels`, recommended native formats when indicated by data assets, hosting/access limitations, and license review status. Source catalog IDs in older audits are treated as counterpart evidence, not identity proof. The TerraClimate baseline is only related to the existing +2C/+4C scenario record; C3S/ESA CCI and Esri LULC records are linked as related release/component where their dates differ; Microsoft global footprints are linked to the Australia partition record as a component. MODIS snow is the same product family but has a PC sinusoidal grid versus a GEE UTM-converted representation. An `exact_dataset` relationship means the public PC collection itself is the source for that new suggestion; no such relationship asserts that an existing canonical record is identical to that source. Sentinel and Landsat archives are marked near-global with scene/swath sampling notes, not wall-to-wall coverage. No citation metrics were collected; a DOI appears only when directly present in captured collection description metadata.

## Verification performed

```sh
python3 research/global-candidates-20261031/planetary/capture.py --check
python3 -m py_compile research/global-candidates-20261031/planetary/capture.py
```

The metadata declarations are not data-byte validation: collection extents, licenses, item-asset media types and object paths have not been independently verified. Asset GETs/downloads are intentionally outside this inventory.
