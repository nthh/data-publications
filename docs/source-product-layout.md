# Source product layout

For a dataset with a few assets, prefer a flat Source product directory. A small product can contain `README.md`, a matching `.parquet` and `.pmtiles` pair, its MapLibre style, field dictionary, required license information and a compact checksum manifest. LakeATLAS needs two matching pairs. Use versioned filenames when publishing changed bytes so existing references remain reproducible. Reserve subdirectories for large partitioned datasets or multiple distinct layers that need them.

The five current products each contain one analytical Parquet and one PMTiles archive, except LakeATLAS with two of each. Their aggregate Portolan catalog remains on GitHub Pages. A flat Source product does not need a second standalone catalog or an additional Source product.

## Why the current directories exist

The current `releases/<release>/` prefixes were chosen to preserve checksum-bound analytical packages. Later, the PMTiles build added independently versioned `display/<revision>/` prefixes, so rendering changes could reuse the analytical bytes. The GRWL width and dateline investigations used that separation repeatedly. The decisions are recorded in the [Source preparation workflow](source-cooperative-products.md) and [display workflow](display-derivatives.md), introduced in commits `de49569` and `313f6c7`.

These names are our packaging convention. Portolan does not require `releases/` or `display/`. Its [reference example](https://github.com/portolan-sdi/portolan-spec#what-a-catalog-looks-like) places Parquet and PMTiles beside the collection metadata. Its [Git-backed catalog guidance](https://github.com/portolan-sdi/portolan-spec/blob/main/specs/best-practices/git-backed-catalogs.md) separates published catalog files, repository-only build material, and untracked bulk data. Its [core specification](https://github.com/portolan-sdi/portolan-spec/blob/main/specs/portolan/core.md) defines STAC relationships, provenance, accessible assets and version metadata; it does not prescribe those two storage prefixes.

## Comparable Source products reviewed on 2026-11-10

| Product | Observed layout |
| --- | --- |
| [CPAD and CCED](https://source.coop/cboettig/cpad) | Matching versioned `.parquet` and `.pmtiles` filenames at the product root; extra subdirectories for other representations. |
| [OBIS](https://source.coop/cboettig/obis) | Parquet and PMTiles files at the root; filenames distinguish the snapshot and derived layers. |
| [VIDA buildings](https://source.coop/vida/google-microsoft-open-buildings) | Format directories such as `geoparquet/` and `pmtiles/`, with country/partition organization for a much larger inventory. |
| [EUBUCCO](https://source.coop/abry-tudelft/eubucco) | Separate `parquet/`, `pmtiles/`, and `flatgeobuf/` directories. |

These are examples, not a census or a single Source-wide convention. Their formats and scopes are described by their publishers; this review did not validate their analytical contents.

## Migrating the existing products

The user approved this additive migration on 2026-11-11. All 35 flat objects are now uploaded and verified, and the local catalog points to them. Execution, checksums and remaining publication steps are recorded in the [cleanup and migration report](../research/source-cleanup-20261111/README.md). The repeatable sequence is to freeze the old-to-new mapping, copy and verify the bytes, rewrite style URLs, test anonymous/range/CORS access, queries and map rendering, then pin the hosting evidence and regenerate the READMEs and catalog. Keep existing public URLs working until the generated catalog cutover is deployed and verified. The separately generated [retirement plan](../research/source-retirement-20261111/retention-plan.json) accounts for every old object; deletion is a distinct operation after the live checks pass.

Keep detailed source inventories, conversion scripts, failed attempts and validation reports in Git. Publish the data and the small amount of documentation needed to use it. Local copies of hosted releases can be evicted after matching them to the verified remote objects; raw inputs, unhosted builds, viewer dependencies and alternate revisions need separate accounting. Filesystem allocation measurements on APFS do not prove exclusive reclaimable bytes because cloned extents can be shared.

## Generated support links and retirement

`scripts/source_retirement.py` derives an object retention inventory from the frozen Source listing and verified flat publication plan. It matches report bytes to tracked Git files by SHA-256, preserves missing evidence once in a content-addressed archive, and prepares exact flat copies of producer PDFs. Large historical evidence is compressed losslessly; analytical files remain outside Git. Original release manifests and failed reports remain unchanged.

The generated `publication.source_coop.support_layout` pin maps supporting STAC assets to a committed Git file or a verified flat Source PDF. `scripts/support_publication.py` checks the original asset identity and checksum before changing its URL. The catalog generator rejects any remaining old Source URL in its generated collections, styles or Markdown. Source file tables and README upload plans are generated from the same records:

```sh
uv run --locked python scripts/source_products.py write
uv run --locked python scripts/source_products.py readme-plan --output .local/readme-plan.json
uv run --locked python scripts/publication_catalog.py write
uv run --locked python scripts/publication_catalog.py stage .local/publication-stage
```

These commands do not publish or delete. `scripts/source_publish/retire.py` consumes a separately frozen execution plan. Its live preflight requires the retention commit on remote main, exact anonymous readback of the deployed catalog and Source READMEs, available Git support files, unchanged verified flat objects, and an unchanged legacy inventory. Execution deletes exact inventoried keys with ETag guards; it never recursively deletes a guessed prefix. Receipts support an explicit resume and the final check requires all old prefixes to be empty.

Current progress and pending deployment are recorded in the [retirement report](../research/source-retirement-20261111/README.md). The `display/` paths retained inside the Git-backed catalog hold small generated styles; they are separate from the obsolete Source storage prefixes. Git release directories retain immutable provenance.
