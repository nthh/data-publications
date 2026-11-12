# Catalog readiness fixes

The baseline D review in `ci-r1/` remains unchanged. This revision corrects its live-hosting errors and major documentation and presentation findings. Final public-catalog revalidation is the next gate; no upstream registry PR has been submitted.

- Source hosts all six style and five thumbnail assets. Nine new versioned objects total 1,398,034 bytes; two existing styles are reused unchanged. `presentation-hosting-r1.json` records full anonymous checksums, byte ranges, and the required CORS headers/methods for all eleven objects.
- The five Source READMEs are published and generated from the same metadata as the catalog READMEs. They contain absolute-URL DuckDB queries, file/schema links, source citations, license terms and limitations. LakeATLAS includes queries for both representations.
- Collection AGENTS files provide dataset-specific constraints. The 16 GRWL and 618 LakeATLAS column entries now have definitions from checksum-bound field semantics; LakeATLAS retains its published units and separate attribute-license documentation.
- Revised styles use existing CSI or Lake_area tile attributes. Three reviewed, explicitly regional previews distinguish connectivity, polygons and pour points. GRWL width styling and the river-plastic style are unchanged. Rejected thumbnail attempts are retained with reasons.
- `data-identity-check.json` confirms all six GeoParquet and six PMTiles asset entries are byte-for-byte identical to the preceding metadata. No data was rebuilt or replaced.
- 84 focused metadata/Source tests passed; the seven presentation tests were rerun after allowing the pre-existing source-free background layer. The staged locked Rashid schema/structure gate passed. The optional stac-check advisory remains incomplete, as recorded, and is not represented as passing.
- The first staged-card check hit a detached-DOM race during asynchronous loading; the corrected check waits for all cards and retries that specific detachment. The second check and visual review passed.

The first upload attempt omitted the credential-helper argument; the second found an expired session. Neither wrote an object. After renewed sign-in, `presentation-upload-r3/` completed, as did all five `readme-upload-r1/` receipts. Original failures remain available.

See `docs/catalog-workflow.md` for the reusable publication sequence. No recurring jobs, new Source products, registry submission, data deletion, or history rewrite are part of this revision.
