# Dataset guidance for agents

Use the GeoParquet analytic data for calculations; PMTiles is a visual derivative with thinning at lower zooms and quantized positions. Interpret the values as Lebreton et al. (2017) modeled inputs for the 2010 baseline, not present-day measured emissions or the Meijer et al. (2021) model.

Four source points have null emission/runoff estimates; retain them and never replace their nulls with zeros. Their source row numbers are 22271, 36248, 36262 and 36276.

There are 19 exact coincident-coordinate pairs in the source. Preserve multiplicity. GEE comparison found identical numeric values and nulls with sub-metre coordinate differences; the original strict coordinate check failed. Original Figshare geometry is retained.

Preserve the distinction between tonnes/year, tonnes/month, mm/day, kg/year and square metres. Retain the lower, midpoint and upper estimates. Decimal fields preserve source DBF numeric values; use Decimal-aware readers for lossless operations.

The geometry coordinates are longitude, latitude in WGS84 (OGC:CRS84). The bbox covering columns support remote spatial pruning. source_row is the one-based ordinal in the pinned shapefile, not a producer-issued watershed ID. The original source DOI and SHA-256 in manifest.json define its scope.

This is a locally prepared release. Check the release validation report and later hosting receipt before claiming publication or Portolan registry acceptance. Attribution and CC BY 4.0 license are in README.md. No external service or data export is needed to read the local bundle.
