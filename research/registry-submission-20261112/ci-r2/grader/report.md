# Catalog review: B

The major baseline defects are fixed. The published catalog passes its registry submission gate, all six SQL examples run, and every column is described. Remaining findings are minor documentation and presentation improvements plus disclosed validator scope limits.

[Unmodified facts](facts.json) · [Claim review](claim-review.json) · [Visual review](visual-review.json)

| Area | Grade | Reason |
| --- | --- | --- |
| machine-contract | B | The registry gate passes and Rashid has zero errors; two remote-scope warnings remain. Every column now has a description. |
| honesty | B | Checked claims agree with retained evidence and current footer/query results; historical counts and validation figures are still written in canonical prose. |
| documentation | B | All levels have accurate docs and linked agent guidance; collection guidance still lacks complete CRS explanations and join recipes. |
| access | B | All six documented SQL blocks run against published URLs; they demonstrate basic counts and row samples, without advanced joins. |
| visuals | B | All five previews load and are distinct, and every collection has data-driven styling; descriptions and small-card legends could improve. |
| organization | A | Five clearly named collections each contain one dataset; LakeATLAS keeps its polygon and pour-point representations together. |
| maintenance | A | Metadata is generated, current updated values and provenance/contact links are present, and all 132 checked links answer. |
| concision | B | Collection AGENTS no longer trigger the similarity threshold; shared sections and some README/AGENTS limitations still repeat. |

## Scope and evidence

The collector reports **0 errors and 2 warnings**. Remote crawling cannot see unlinked files (PTL-GEN-002), and the live pass skips Source assets hosted outside the Pages domain (PTL-LIV-000). This is not a claim that Rashid probed those assets. The [separate Source check](../../presentation-hosting-r1.json) verifies all eleven style/thumbnail objects by anonymous full hash, byte range and CORS; [local staged Rashid](../../staged-rashid.json) passes. Five upstream-STAC advisory notices remain; no producer STAC URL was invented.

The [CI public-metadata match](../publication-match.json) verifies all 18 staged metadata files. All 132 checked links answer, all five thumbnails load, all six documented SQL blocks pass, and AGENTS files no longer trigger the similarity threshold. The [official live browser check](../../cards-live/report.json) and its [visual review](../../cards-live/visual-review.json) pass. The prior [D review](../../ci-r1/grader/report.md) remains unchanged.

## Remaining improvements

- **F1 (machine-contract)** — PTL-GEN-002 cannot inspect unlinked remote files; PTL-LIV-000 skips cross-host Source assets. Separate local-tree Rashid and anonymous Source hash/range/CORS checks pass; the collector findings are not overridden. Continue retaining local-tree and explicit cross-host hosting checks beside the unmodified remote collector.
- **F2 (honesty)** — The count and schema are correct for this pinned release, but the sentence and other historical validation figures are maintained as canonical prose rather than derived numeric fields. Generate release counts and validation summaries from their bound evidence when introducing a new data version.
- **F3 (documentation)** — The guide explains layer distinctions, source codes and GEE limitations but does not give a Hylak_id join recipe or explicit CRS implications. Add concise collection-specific CRS and join recipes using the bound field dictionaries.
- **F4 (access)** — Six blocks pass, covering all six Parquet assets; all are count and LIMIT examples. Add a tested Hylak_id join or bounded spatial-filter example when expanding consumer recipes.
- **F5 (visuals)** — All six style entries have has_description=false even though titles and expressions identify the attributes; legends also become small at card size. Add concise style descriptions and improve legend readability in a future presentation revision.
- **F6 (concision)** — Highest flagged README similarity is 0.709, below the 0.9 major-defect threshold; some common prose and the README limitations repeat in AGENTS. Keep shared prose at the root and narrow AGENTS to actionable dataset-specific recipes.
- **F7 (documentation)** — No root icon is declared, so the optional A-grade logo requirement is unmet. Add a small recognizable catalog icon if pursuing an A-grade presentation.
- **F8 (maintenance)** — Manual live checks and pull-request validation exist, but no recurring documented-query schedule is configured. Add scheduled live query checks only if the maintainer authorizes recurring work.

## Limits

This review checks current consumer metadata and access, with historical scientific and GEE assertions checked against retained evidence. It does not rerun GEE, rebuild source data, or independently establish scientific accuracy. The six analytical and six PMTiles asset identities remain unchanged. The separate stac-check advisory is still incomplete; the registry gate additionally passed its own stac-node-validator 2.0.0 check.

A requirements still missing: scheduled query/claim checks and a catalog icon. A+ also needs warning-free Rashid, richer source-grounded usage/uncertainty guidance, stronger narrative and an advanced working example. No recurring jobs were added.
