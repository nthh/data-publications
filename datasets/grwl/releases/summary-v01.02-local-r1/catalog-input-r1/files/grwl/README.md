# GRWL summary V01.02

Global River Width from Landsat (GRWL) simplified global river network summary. This is the complete V01.02 summary polyline archive, converted from the producer ZIP. It is a static derived global river network; widths and lengths are producer attributes.

Use `grwl-summary-v0102.parquet` for analysis. It has 42,077 features, all ten numeric DBF fields, producer `ID` values and one-based unique `source_row`. Numeric fields use fixed-point Arrow decimals matching source values; the storage scale expands where source scientific notation exceeds the nominal DBF scale. DBF asterisks are null. Geometry is WKB MultiLineString, EPSG:4326, retaining each SHP part and source XY vertex in order. Per-row bbox struct and GeoParquet covering metadata permit spatial pruning.

`grwl-display.pmtiles` is a display derivative (PMTiles v3, layer `grwl`, zoom 0–10). At z10 every source row occurs; producer IDs repeat and remain attributes. Line simplification and Web Mercator tile quantization alter display geometry. The SHP header bbox alone overshoots 180 by 1e-10 degrees; all feature vertices are in valid longitude bounds, so the display-only clamp is a no-op. Never use PMTiles or the PNG thumbnail for analysis. The MapLibre style stores a relative PMTiles path. Resolve it against the style URL, register the PMTiles protocol, then prepend `pmtiles://` to the resolved archive URL before loading the style.

The source has ten numeric fields. Width fields are metres; `nSegPx` is a pixel/segment count; `lakeFlag` is retained as stored; `Shape_Leng` is geodesic length in km per source XML lineage. `OBJECTID` is Esri's generated row number; `ID` is the producer feature identifier and is not unique.

| Field | Arrow type | Meaning | Unit |
|---|---|---|---|
| `source_row` | `int32` | One-based original SHP/DBF ordinal | 1 |
| `OBJECTID` | `decimal128(10, 0)` | Esri-generated source feature number | — |
| `ID` | `decimal128(10, 0)` | Producer feature identifier | — |
| `width_min_` | `decimal128(10, 0)` | Minimum river width | m |
| `width_med_` | `decimal128(19, 11)` | Median river width | m |
| `width_mean` | `decimal128(19, 11)` | Mean river width | m |
| `width_max_` | `decimal128(10, 0)` | Maximum river width | m |
| `width_sd_m` | `decimal128(19, 12)` | Standard deviation of river width | m |
| `lakeFlag` | `decimal128(19, 12)` | Lake flag as stored by producer | — |
| `nSegPx` | `decimal128(10, 0)` | Segment pixel count | — |
| `Shape_Leng` | `decimal128(19, 13)` | Geodesic feature length; source metadata lineage records kilometers | km |
| `geometry` | `binary` | WGS84 polyline geometry with source multipart structure, in source vertex order | degrees |
| `bbox` | `struct<xmin: double, ymin: double, xmax: double, ymax: double>` | Per-feature xmin/ymin/xmax/ymax envelope in WGS84 | degrees |

Source: [Zenodo record](https://zenodo.org/records/18624542), DOI https://doi.org/10.5281/zenodo.18624542, License: CC-BY-4.0. Cite Allen & Pavelsky (2018), DOI 10.1126/science.aat0636. The catalog's GEE asset corresponds to the older label V01.01; no parity is asserted.
