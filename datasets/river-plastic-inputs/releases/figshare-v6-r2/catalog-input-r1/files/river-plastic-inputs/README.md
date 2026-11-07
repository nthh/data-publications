# Global river plastic inputs — Lebreton et al. (2017)

A global model of plastic inputs from rivers into the ocean, published by Lebreton et al. in 2017. This static release preserves the 40,760 river input locations and all 53 numeric attributes in the original Figshare v6 shapefile. Estimates represent the 2010 model baseline; they are not current measurements. This is distinct from the later Meijer et al. 2021 model.

Use [river-plastic-inputs.parquet](river-plastic-inputs.parquet) for analysis. Numeric source values are fixed-point Decimal values at their original precision. `source_row` is the one-based source shapefile/DBF row number, not a watershed identifier; it is stable only for this pinned archive. Rows are Hilbert-sorted for spatial access. Geometry is WGS84 longitude/latitude (OGC:CRS84); bbox covering columns and row-group statistics support spatial filtering.

The [PMTiles file](river-plastic-inputs.pmtiles) contains the annual low/mid/high estimates, catchment area, mismanaged waste and source identifiers for display. Every source identifier is retained at maximum zoom; lower zooms thin points, and positions are quantized to tile coordinates. Never compute global totals or absence/presence from low-zoom display tiles. The [MapLibre style](styles/annual-input.json) maps the midpoint annual estimate to color and radius. A PMTiles-aware viewer resolves its relative source URL and registers the PMTiles protocol.

Example with DuckDB, run from this collection directory:

```sql
SELECT count(*) AS river_inputs, sum(i_mid) AS tonnes_per_year
FROM read_parquet('river-plastic-inputs.parquet');

SELECT source_row, i_low, i_mid, i_high
FROM read_parquet('river-plastic-inputs.parquet')
WHERE bbox.xmin BETWEEN 100 AND 110 AND bbox.ymin BETWEEN 0 AND 20;
```

Four source rows (22271, 36248, 36262, 36276) have missing annual/monthly emission and runoff estimates. Their numeric DBF asterisk markers are preserved as null, with the points and catchment attributes retained. They appear gray in the default style. See [quality.json](quality.json); null is not zero.

The monthly `i_*` fields are tonnes/month; annual `i_low`, `i_mid`, `i_high` are tonnes/year. Monthly runoff is mm/day, `mpw` is kg/year, and `area` is square metres. Low/mid/high fields are the model's published estimate bounds, not newly computed confidence intervals. Seasonal means and rounded published fields need not sum exactly to the annual fields.

The source has 19 coincident-coordinate pairs (38 records), leaving 40,741 distinct positions. Preserve both records at each position; different values and nulls at the same location are not a reason to deduplicate.

A captured GEE copy matches all 53 numeric fields and nulls, including the coincident groups. Strict coordinate parity failed: GEE positions differ by up to 0.3494564 metres. A separately declared one-metre geodesic diagnostic passes; this conversion retains the original Figshare coordinates. GEE metadata does not identify a source version or ingestion transform. The catalog's kg/year prose conflicts with the original tonnes/year units; observed GEE values match without scaling. See the verification reports packaged with the release. These checks establish conversion and summary consistency, not independent observational validation of the model.

## Fields

| Field | Arrow type | Meaning |
| --- | --- | --- |
| `source_row` | `int32` | One-based original shapefile/DBF row number; stable within the pinned source archive. |
| `i_mid` | `decimal128(13, 6)` | Annual modeled plastic input, midpoint estimate (tonnes/year). |
| `i_low` | `decimal128(13, 6)` | Annual modeled plastic input, lower estimate (tonnes/year). |
| `i_high` | `decimal128(13, 6)` | Annual modeled plastic input, upper estimate (tonnes/year). |
| `i_mid_jan` | `decimal128(11, 6)` | Modeled plastic input for jan, mid estimate (tonnes/month). |
| `i_low_jan` | `decimal128(11, 6)` | Modeled plastic input for jan, low estimate (tonnes/month). |
| `i_high_jan` | `decimal128(12, 6)` | Modeled plastic input for jan, high estimate (tonnes/month). |
| `i_mid_feb` | `decimal128(11, 6)` | Modeled plastic input for feb, mid estimate (tonnes/month). |
| `i_low_feb` | `decimal128(11, 6)` | Modeled plastic input for feb, low estimate (tonnes/month). |
| `i_high_feb` | `decimal128(12, 6)` | Modeled plastic input for feb, high estimate (tonnes/month). |
| `i_mid_mar` | `decimal128(12, 6)` | Modeled plastic input for mar, mid estimate (tonnes/month). |
| `i_low_mar` | `decimal128(11, 6)` | Modeled plastic input for mar, low estimate (tonnes/month). |
| `i_high_mar` | `decimal128(12, 6)` | Modeled plastic input for mar, high estimate (tonnes/month). |
| `i_mid_apr` | `decimal128(12, 6)` | Modeled plastic input for apr, mid estimate (tonnes/month). |
| `i_low_apr` | `decimal128(12, 6)` | Modeled plastic input for apr, low estimate (tonnes/month). |
| `i_high_apr` | `decimal128(12, 6)` | Modeled plastic input for apr, high estimate (tonnes/month). |
| `i_mid_may` | `decimal128(12, 6)` | Modeled plastic input for may, mid estimate (tonnes/month). |
| `i_low_may` | `decimal128(12, 6)` | Modeled plastic input for may, low estimate (tonnes/month). |
| `i_high_may` | `decimal128(12, 6)` | Modeled plastic input for may, high estimate (tonnes/month). |
| `i_mid_jun` | `decimal128(12, 6)` | Modeled plastic input for jun, mid estimate (tonnes/month). |
| `i_low_jun` | `decimal128(12, 6)` | Modeled plastic input for jun, low estimate (tonnes/month). |
| `i_high_jun` | `decimal128(12, 6)` | Modeled plastic input for jun, high estimate (tonnes/month). |
| `i_mid_jul` | `decimal128(12, 6)` | Modeled plastic input for jul, mid estimate (tonnes/month). |
| `i_low_jul` | `decimal128(12, 6)` | Modeled plastic input for jul, low estimate (tonnes/month). |
| `i_high_jul` | `decimal128(13, 6)` | Modeled plastic input for jul, high estimate (tonnes/month). |
| `i_mid_aug` | `decimal128(12, 6)` | Modeled plastic input for aug, mid estimate (tonnes/month). |
| `i_low_aug` | `decimal128(12, 6)` | Modeled plastic input for aug, low estimate (tonnes/month). |
| `i_high_aug` | `decimal128(12, 6)` | Modeled plastic input for aug, high estimate (tonnes/month). |
| `i_mid_sep` | `decimal128(12, 6)` | Modeled plastic input for sep, mid estimate (tonnes/month). |
| `i_low_sep` | `decimal128(12, 6)` | Modeled plastic input for sep, low estimate (tonnes/month). |
| `i_high_sep` | `decimal128(12, 6)` | Modeled plastic input for sep, high estimate (tonnes/month). |
| `i_mid_oct` | `decimal128(12, 6)` | Modeled plastic input for oct, mid estimate (tonnes/month). |
| `i_low_oct` | `decimal128(12, 6)` | Modeled plastic input for oct, low estimate (tonnes/month). |
| `i_high_oct` | `decimal128(12, 6)` | Modeled plastic input for oct, high estimate (tonnes/month). |
| `i_mid_nov` | `decimal128(12, 6)` | Modeled plastic input for nov, mid estimate (tonnes/month). |
| `i_low_nov` | `decimal128(11, 6)` | Modeled plastic input for nov, low estimate (tonnes/month). |
| `i_high_nov` | `decimal128(12, 6)` | Modeled plastic input for nov, high estimate (tonnes/month). |
| `i_mid_dec` | `decimal128(11, 6)` | Modeled plastic input for dec, mid estimate (tonnes/month). |
| `i_low_dec` | `decimal128(11, 6)` | Modeled plastic input for dec, low estimate (tonnes/month). |
| `i_high_dec` | `decimal128(11, 6)` | Modeled plastic input for dec, high estimate (tonnes/month). |
| `runoff_jan` | `decimal128(9, 6)` | Mean catchment runoff for jan (mm/day). |
| `runoff_feb` | `decimal128(9, 6)` | Mean catchment runoff for feb (mm/day). |
| `runoff_mar` | `decimal128(9, 6)` | Mean catchment runoff for mar (mm/day). |
| `runoff_apr` | `decimal128(9, 6)` | Mean catchment runoff for apr (mm/day). |
| `runoff_may` | `decimal128(9, 6)` | Mean catchment runoff for may (mm/day). |
| `runoff_jun` | `decimal128(9, 6)` | Mean catchment runoff for jun (mm/day). |
| `runoff_jul` | `decimal128(9, 6)` | Mean catchment runoff for jul (mm/day). |
| `runoff_aug` | `decimal128(9, 6)` | Mean catchment runoff for aug (mm/day). |
| `runoff_sep` | `decimal128(9, 6)` | Mean catchment runoff for sep (mm/day). |
| `runoff_oct` | `decimal128(9, 6)` | Mean catchment runoff for oct (mm/day). |
| `runoff_nov` | `decimal128(9, 6)` | Mean catchment runoff for nov (mm/day). |
| `runoff_dec` | `decimal128(9, 6)` | Mean catchment runoff for dec (mm/day). |
| `mpw` | `decimal128(17, 6)` | Mismanaged plastic waste produced in the catchment (kg/year). |
| `area` | `decimal128(20, 6)` | Upstream catchment area (m²). |
| `geometry` | `binary` | River input point; WKB Point, WGS84 longitude/latitude (OGC:CRS84). |
| `bbox` | `struct<xmin: double, ymin: double, xmax: double, ymax: double>` | Per-feature xmin, ymin, xmax, ymax covering bounds in longitude/latitude. |

## License and provenance

Original data: https://doi.org/10.6084/m9.figshare.4725541.v6 (CC BY 4.0). Original archive: https://ndownloader.figshare.com/files/7714864.

Lebreton, L. C. M., van der Zwet, J., Damsteeg, J.-W., Slat, B., Andrady, A. & Reisser, J. (2017). River plastic emissions to the world's oceans. Nature Communications 8, 15611. https://doi.org/10.1038/ncomms15611

Folia converted the source to spatially ordered GeoParquet and a PMTiles display derivative. Conversion source commit: `4c54a01451967421bf17b1346cd749c0738efdde`. `manifest.json` at the catalog root records checksums, tool versions and the exact build inputs. `dataset.yaml` at the catalog root preserves the canonical record exactly as it existed at build time; publication status can evolve later in Git without rewriting this snapshot. This bundle is prepared locally; publication and registry submission remain pending.

