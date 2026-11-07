# JRC Global Surface Water Occurrence v1.5 qualification

Checked 2026-10-31. Scope was source metadata and bounded source-TIFF structure/range access only; no raster payload was downloaded or converted.

## Source identity and complete object scope

- Producer/source version: JRC Global Surface Water v1.5, aggregated `Occurrence`, filename edition `v1_5_2024`.
- Observation interval: 1984–2024. The JRC access page states that the aggregate merges Landsat Collection 1 (1984–2021) with Collection 2 (2022–2024); v1.5 is therefore a release label over a mixed processing period, not a single-year acquisition.
- Producer page: <https://global-surface-water.appspot.com/download> (page states last updated 2026-10-15); source object host: <https://s3.waw4-1.cloudferro.com/swift/v1/global-surface-water/>.
- The earlier complete inventory at `research/chirps-priorities-20261030/evidence/jrc-v15-aggregated-list.json` was reverified against the live public CloudFerro list endpoint on 2026-10-31. It still resolves to 504 `.tif` objects totaling 14,453,956,859 bytes. Current listing response: 200, 690,514 bytes, SHA-256 `338037170377b21953074a9163d68498048764532642ef0f44ee82c1b72e7410`; listing `Last-Modified` is 2026-07-01; tile timestamps span 2026-07-01 10:25:02–10:45:03 UTC. See `occurrence-current-inventory-metadata.json` and `occurrence-current-inventory-response.json`.
- The listing's per-object `hash` field is retained as source metadata, not claimed as SHA-256. Some values have multipart-style suffixes. The listing does not provide verified per-object SHA-256 checksums.

## Bounded source probes

Reusable script: `qualify_occurrence_ranges.py`. It reads the prior full 504-object inventory, permits no more than 8 named tiles, imposes a configurable aggregate response cap that cannot exceed 8 MiB and a per-tile cap that cannot exceed 1 MiB, and sets connect/read timeouts (defaults 8/12 seconds). It requests TIFF metadata/index ranges only, records status and failed probes, and never requests pixel ranges or falls back to full downloads. Command run:

```sh
python3 research/hydro-releases-20261031/jrc/qualify_occurrence_ranges.py
```

Probe evidence: `occurrence-range-probes.json`. Eight geographically varied objects were checked (North America, Africa, Asia, Australia, tropical Atlantic, sparse South Pacific, high Arctic, and higher-latitude North America). Aggregate response body bytes read: 280,640 of a 4,194,304-byte configured cap. All requested ranges returned HTTP 206 with matching Content-Range. Each TIFF's first IFD parsed as little-endian classic TIFF; base raster is 40,000×40,000, 8-bit, with 512×512 tiles. All eight samples expose the same complete linked IFD pyramid: 40,000, 20,000, 10,000, 5,000, 2,500, 1,250, 625, and 312 pixel overviews. Full tile-offset arrays were range-read from each sample's IFDs (no image payloads); offsets are monotonically ascending within each IFD, and overview payload ranges are ordered from smallest overview through largest overview before the full-resolution base payload. These are strong sampled layout signals consistent with a Cloud-Optimized GeoTIFF (COG), and confirm HTTP range access on the sampled objects.

The source host and a prior JRC republication also explicitly describe v1.5 files as Cloud-Optimized and as containing overviews. This local sample corroborates those claims, but is not a full COG conformance validation and cannot certify all 504 files. No GDAL `validate_cloud_optimized_geotiff.py` or independent full-tile validation was run.

## Qualification outcome

The complete public inventory and sampled access/layout checks are good enough to preserve JRC v1.5 Occurrence as a candidate external source. They do not establish a need for a 14.45 GB local mirror. Keep the source inventory and range evidence; do not convert or mirror the raster in this preparation unless an analytic use case is specified. If conversion is later justified, first choose a reproducible region/time/pixel-value validation that checks the JRC merge semantics and NoData/percent-occurrence interpretation, then verify sampled and eventually all 504 source objects as required by the release claim. Sample evidence must stay labeled as sample-only.

## Caveats and limitations

- Producer release date and observation interval differ: public v1.5 access page timestamp is 2026-10-15, object metadata is July 2026, and the aggregate covers 1984–2024.
- A sample of eight tiles is a qualification signal, not exhaustive certification for all 504 objects.
- Current object listing metadata repeats the prior inventory's 2026-07-01 object metadata, but provides no source-declared SHA-256 values per TIFF.
- No data pixels, overview pixels, or full TIFF bodies were downloaded; no scientific value comparison was attempted.
