# Evidence notes: ranks 1–10

Accessed 2026-10-30. Only public producer/catalog documentation and public metadata were consulted; no dataset bodies were downloaded.

| Rank | Key evidence and amount basis |
|---|---|
| 1 ERA5 | CDS single-level form supports GRIB/experimental NetCDF4. For 2024 2 m hourly temperature, calculated payload is 1440×721×8784×4 = 36,548,505,600 bytes (36.55 decimal GB), regular 0.25° request grid; not compressed. Google Research ARCO-ERA5 README describes a separate Zarr v3 GCS mirror, approximately 5 PB publisher approximation. |
| 2 NCEP/NCAR | NOAA PSL documents 144×73 2.5° grid and NetCDF4 distribution. Monthly SLP annual payload calculated 144×73×12×4 = 504,576 bytes (0.505 MB), not compressed. NCEP GEE items are deprecated and distinct. |
| 3 WorldClim V1 | WorldClim V1 format page says ZIP collections, generic BIL/HDR and ESRI grids, BIO has 19 layers; GeoTIFF availability documented for 30-second tiles. Selected 10-minute BIO rectangular-array calculation 2160×1080×19×2 = 88,646,400 bytes (88.65 MB), including ocean nodata. |
| 4 Hansen GFC | Official GFC-2025-v1.13 page provides 10×10-degree TIFF granules and URL manifests; producer states complete global treecover2000 <50 GB, gain/lossyear/datamask <10 GB each, first/last >600 GB each. These are separate layers; not summed. |
| 5 MODIS VI | LP DAAC MOD13 guide documents HDF-EOS and fixed-area 10×10-degree granules; selected MOD13A2 is 1200×1200 tile, one int16 NDVI layer = 2,880,000 bytes raw (2.88 MB). No compressed file size inferred. |
| 6 MERRA-2 | GES DISC lists 0.5×0.625° hourly MERRA products; chosen one-field 2024 payload = 576×361×8784×4 = 7,335,728,640 bytes raw. Publisher 1.2 GB/month is for a different 42-level monthly product and is explicitly kept separate. |
| 7 SRTM | USGS/LP DAAC guide documents 3601×3601 one-arc-second 1° SRTMGL1 tiles. One tile int16 payload = 25,934,402 bytes (25.93 MB), not a file-byte measurement. |
| 8 TRMM | NASA V7 documentation: HDF archive, 3B43 monthly files approximately 5 MB uncompressed, 3B42 11 MB; 12×5 MB ≈60 MB for 3B43 2019. |
| 9 CHIRPS | CHC producer FAQ lists 50°S–50°N global 7200×2000 at 0.05°, daily steps, formats TIFF/BIL/NetCDF. Annual daily int32 raw payload 7200×2000×365×4 = 21,024,000,000 bytes (21.02 GB); not compressed. |
| 10 GLDAS | NASA GES DISC states Noah 2.1 3-hourly NetCDF, 36 fields, 19 MB/file. One day = 8×19 MB ≈152 MB publisher-based approximate sum. Separate CLSM daily and legacy Noah collections remain out of scope. |

**Rank 7 source refinement:** public NASA CMR UMM collection metadata for `SRTMGL1`, version `003`, reports `Format=HGT`, compressed ZIP distribution, `AverageFileSize=7 MB`, and `TotalCollectionFileSize=99883.2 MB`. The review now uses the publisher average for a tile and retains the collection-wide publisher total as a separate alternative; the former raw tile arithmetic is superseded.
