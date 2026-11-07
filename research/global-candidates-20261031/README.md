# Global candidate expansion

The candidate backlog now spans highly cited dataset families, the official and community Earth Engine catalogs, Microsoft Planetary Computer, Esri public data, and producer sources. The editable inventory remains `datasets/<id>/dataset.yaml`; [CANDIDATES.md](../../CANDIDATES.md), [candidates.csv](../../candidates.csv) and [index.json](../../index.json) are generated views.

This batch adds **84 candidates** and augments **28 existing records**, for **450 records** overall. The global CSV contains **292 global or near-global records** (264 global, 28 near-global); 111 have observations from this expansion. A further existing regional Overture Buildings record receives related-host evidence without being promoted to global coverage. All new candidates remain pending. The five prepared releases, GRIP4 deferral, JRC reuse decision and zero-collection publication catalog are unchanged.

## Discovery coverage

| Lane | Retained scope | Reviewed observations | Limits |
| --- | --- | ---: | --- |
| Official + community GEE citations | Frozen official snapshot of 1,165 entries and original community intake; first 50 global paper groups after excluding deprecated official entries | 53 source/product observations | Shared papers do not imply one dataset; not every official entry was re-reviewed |
| Planetary Computer | All 139 collections returned by the public STAC collection endpoint | 38 | Four PC observations withheld from canonical promotion; catalog extents and formats are declarations |
| Esri / ArcGIS public search | 37 searches, 43 pages, 902 result rows, 805 unique item IDs | 15 family leads | Two queries truncated; most search items are unreviewed; public ArcGIS does not imply curated Living Atlas membership |
| Additional producer leads | Natural Earth, OSM, Overture, GBIF, WorldPop Global2, GADM 4.1, GEBCO 2026 | 7 | Natural Earth umbrella retained in research because scoped country/place records already exist |
| Additional literature | Ten producer-backed global families outside the frozen top-50 DOI set; 12 DOI-resolved OpenAlex requests | 10 | Purposive sample, not a literature-wide top-cited ranking |
| Prior access / hosting research | CHIRPS, SoilGrids, JRC, TerraClimate and Overture | 10 across six target records | Original observation dates retained; no fresh remote access tests |

The methodology was committed before the new capture and import. [methodology.json](methodology.json) records acceptance criteria, limits and hashes of prior inputs. Its `index.json` hash refers to the exact pre-expansion bytes retained in [baseline-index.json](baseline-index.json); [baseline-records.json](baseline-records.json) pins all 366 original canonical records. The local study date is 2026-10-31; captures made after midnight UTC correctly retain 2026-11-01 timestamps.

Metadata capture used one PC request (1,774,281 bytes), 43 Esri requests (3,766,656 response bytes) and 12 OpenAlex requests (all DOI identities resolved). Primary producer pages were also reviewed as linked in the observations. PC retains normalized collection-response metadata with two signed thumbnail query strings removed, plus separate original-response and retained-body hashes and byte counts. The original response bytes are not retained. Esri retains normalized selected fields, queries, pagination and response hashes, but **not the raw response bodies**, so a full Esri response replay is unavailable. No dataset assets, live GEE jobs, data uploads or paid services were used for this expansion.

## Identity and prioritization

[Integration mappings](integration-plan.json) join scientific products, not titles or shared paper DOIs. Important separations include TerraClimate baseline versus warming scenarios; global Microsoft buildings versus Australia; HydroSHEDS rasters versus HydroBASINS polygons; GPW population density versus administrative-unit points; GHSL urban centres versus built-up grids; MODIS GPP versus NPP; WorldClim v2.1 versus v1; and archived ERA-Interim versus ERA5.

The [independent identity review](identity-review.json) and [first import audit](integration-review.json) preserve the original findings. The follow-up [resolution audit](resolution-review.json) records their disposition. PC ALOS and Deltares observations with invalid latitude bounds remain research-only pending coverage review. Microsoft buildings has independent worldwide-scope documentation; its invalid provider bbox is explicitly labelled and country/imagery gaps remain documented. The NASA GFCC v3 component is withheld from the community v4 record.

Citation values measure associated publication use, not exact-release use or conversion value. The backlog uses the maximum associated-paper count at the latest available observation date for a record; unknown stays empty rather than becoming zero. The frozen top-50 catalog selection remains unchanged. Additional literature counts observed on 2026-11-01 are shown with their own dates, so the generated backlog is **not a single-date ranking of all geospatial literature**. GMIA v5's technical-report count (89) remains in evidence and is excluded from the paper metric; an older edition's paper count is not substituted. ERA-Interim is visibly labelled historical and superseded despite its high count.

Existing native formats are reuse leads. WFP CHIRPS v3 RNL differs from GEE v2 Final; the SoilGrids Icechunk publication covers means and has not passed a reader test; JRC MonthlyHistory is not Occurrence v1.5; PC TerraClimate has a shorter period than the producer v1.1 archive. Esri feature-service access does not prove bulk-export permission or redistribution rights. Each candidate records observed formats, possible outputs, access limitations and license-review notes. Selecting a conversion still requires confirming the exact release, complete coverage, successful access, license, download size and useful improvement over existing hosts.

## Repeatable Git workflow

1. Create a dated research directory and record scope, identity rules, costs and acceptance checks before querying. Preserve previous observations and decisions.
2. Capture public catalog metadata explicitly into new paths; select documented global/near-global products. Record truncation and unreviewed entries.
3. Review producer identity and edition before collecting citation counts or matching a canonical ID. Store immutable observations with source URLs, dates and hashes.
4. Append `discovery` evidence to an existing compatible record or create a pending candidate. Put distinct components/releases in separate records when their scientific scope differs. Keep related counterparts explicit.
5. Generate the backlog and index, validate evidence and run focused tests. Commit metadata and scripts in Git; keep bulk data and environments outside Git.
6. Review conversion value separately. Only selected products enter the existing build, validation and publication workflow; discovery never uploads data or changes repository visibility.

Offline reproduction from the repository root:

```sh
uv sync --locked --no-build
uv run --locked python scripts/catalog.py --check
uv run --locked python scripts/check_provenance.py
uv run --locked python scripts/publication_catalog.py check
python research/global-candidates-20261031/planetary/capture.py --check
python research/global-candidates-20261031/esri/capture.py --check
python research/global-candidates-20261031/citations/extract_frozen.py --check
python research/global-candidates-20261031/citations/enrich_coverage.py --check
python research/global-candidates-20261031/citations/check_review.py
python research/global-candidates-20261031/literature/build_review.py --check
python research/global-candidates-20261031/reuse/check.py
```

To regenerate views after editing canonical records:

```sh
uv run --locked python scripts/catalog.py --write
```

The one-batch [integrator](integrate.py) reproduces this import with `--check` and can apply it to its pinned baseline using `--write`; it refuses to overwrite a different discovery block. It is an audit tool for this batch, not a second editable inventory or a requirement that future canonical records remain frozen. CI checks current canonical records, generated views, source-observation integrity and the existing publication gate.

Optional new metadata captures require explicit flags and new destinations; see [Planetary Computer](planetary/README.md), [Esri](esri/README.md), [literature](literature/README.md), [frozen citations](citations/README.md) and [prior-host reuse](reuse/README.md). A future batch should have a new study directory and independent identity review. It should not overwrite this snapshot or quietly replace its citation dates.

## Verification

The [validation report](validation.json) records a clean-checkout rehearsal with fresh locked environments, 47 passing focused tests, all source checks, unchanged immutable release paths and a passing Rashid root-catalog gate. The optional stac-check advisory remains incomplete because its attempted remote schema request was blocked by the offline guard. This is metadata validation; no candidate dataset bytes or live hosts were newly validated.
