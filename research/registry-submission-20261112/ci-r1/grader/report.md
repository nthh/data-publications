# Catalog submission review

**Grade: D.** The registry metadata gate passes, but the broader live check reports two GitHub Pages CORS errors. Missing examples, generic agent guidance and limited thematic styles also lower the grade.

This is an advisory quality review, not a new scientific or GEE validation.

| Area | Grade | Finding |
| --- | --- | --- |
| machine-contract | C | The registry metadata gate passes, but live Pages hosting has two CORS errors; GRWL and LakeATLAS table columns lack descriptions. |
| honesty | A | Reviewed generated counts, producer/license statements and retained GEE diagnostics agree with their evidence; scientific and temporal limits are stated. |
| documentation | D | Collection READMEs lack in-place quickstarts and schema guidance; AGENTS files are generic stubs despite richer documentation elsewhere. |
| access | D | The reviewed catalog documents have no runnable examples; separate Source product examples are outside this collector result. |
| visuals | D | All images load and PMTiles start at zoom 0, but three collections use flat default styles and the lake previews are visually similar. |
| organization | A | Five clearly named dataset collections form a suitable small catalog; LakeATLAS polygon and pour-point assets are two representations of one dataset. |
| maintenance | B | Provenance and contact links are present, metadata is generated, and all 92 links answered; scheduled query/claim checks are absent. |
| concision | D | Collection AGENTS files repeat generic content with pairwise similarity above 0.9. |

The A requirements for a catalog logo and scheduled documented-query checks are unmet. No A+ requirements are awarded. Registry membership is waived for this submission review.

## Findings

- **F1 (major):** The grader live pass reports PTL-LIV-004: nthh.github.io does not expose Content-Type, Content-Length, Content-Range, Accept-Ranges and ETag for browser clients; its representative asset is the collection style JSON. Fix: Serve catalog assets from a host with the required exposed response headers and verify the live pass again.
- **F2 (major):** The grader live pass reports PTL-LIV-005: nthh.github.io answers the conditional range CORS preflight with HTTP 405 and lacks the required allowed methods and request headers. Fix: Use a host that accepts the specified GET/HEAD and conditional Range preflight requests for catalog assets.
- **F3 (minor):** The captured table:columns has no descriptions for 618 LakeATLAS entries; GRWL also has 16 undescribed entries at /nodes/2/table_columns, despite separately available producer dictionaries. Fix: Generate table:columns descriptions from the existing pinned field dictionaries and producer semantics.
- **F4 (major):** All five collection AGENTS files use the same generic guidance and omit dataset-specific query recipes, join-key rules, CRS implications and important coded-field semantics. Fix: Generate dataset-specific agent guidance from the canonical records and existing schema/provenance evidence.
- **F5 (major):** The collected root and collection documents contain no runnable code blocks; /summary/code_blocks_run is zero, so the review did not execute the examples hosted on the separate Source product pages. Fix: Include the existing published-URL quickstarts in the generated catalog READMEs and verify those exact blocks.
- **F6 (major):** Free-Flowing Rivers, HydroLAKES and LakeATLAS use constant-color default styles; GRWL width and river-plastic estimates are data-driven, but the rubric explicitly treats flat attribute-independent styles as a major defect. Fix: Add documented thematic styles for appropriate existing attributes while preserving analytical bytes.
- **F7 (minor):** Visual inspection of every saved image finds visible data, but HydroLAKES and LakeATLAS have almost identical map views and subdued fills at card size; see visual-review.json. Fix: Choose a contrasting attribute or view for LakeATLAS and increase the legibility of both lake thumbnails.
- **F8 (major):** Every pair of collection AGENTS files exceeds 0.9 similarity (0.922–0.979); the files repeat generic packaging instructions instead of dataset-specific guidance. Fix: Keep common instructions at the root and generate concise collection-specific guidance.
- **F9 (minor):** The root has no icon link; the A-grade logo requirement is unmet. Fix: Add a small recognizable catalog icon and a verified root icon link.
- **F10 (minor):** The repository validates on pull requests but has no scheduled check of documented queries and claims; the new review is an explicit submission run. Fix: Add a scheduled check of published examples and claims if recurring live checks are authorized.

## Evidence and scope

[Collector facts](facts.json), [structured grade](report.json), [reviewed claims](claim-review.json), [visual review](visual-review.json), and [registry gate result](../registry-validation.json) retain the evidence. All 12 collected documents match the generated catalog documents read in full. All five saved thumbnails were inspected.

The collector checked all 92 links and found no broken or unverified links. Separate attempts to read full Figshare and Nature source pages were refused; those source-text limitations are recorded in the structured grade. Retained producer and GEE evidence was used without claiming a fresh raw-data or GEE comparison.

The zero code-block count means no runnable examples are present in the catalog documents; it is not a successful query test. The Source product READMEs have separate examples, but the grader did not follow them as collection documentation.
