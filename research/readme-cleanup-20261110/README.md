# README cleanup — 2026-11-10

The five published product READMEs had incorrect attribution from an old packaging default and hard-coded provider labels. Canonical producer attribution now names only the original data authors. The Source generator uses actual provider names and applies the same explicit current maintainer correction as the Portolan catalog, without editing the bound source snapshots. The withheld GRWL summary draft receives the same prose cleanup. The current river-plastic workspace README and publishing guide also separate dataset attribution from applicable software notices. Publisher names in a source snapshot remain historical evidence rather than a current attribution instruction.

[before.json](before.json) records anonymous HTTP 200 reads, sizes, hashes and counts of incorrect attribution lines for 14 product/release/display READMEs. All five product-root READMEs matched the prior committed copies exactly. Downloaded bodies are kept in ignored local storage. The original river-plastic release README also contains an incorrect converter sentence; it is a checksum-bound package artifact. It is not selected by this five-product-root update and must be superseded through a metadata/release revision rather than silently invalidating its manifest.

[verification.json](verification.json) records 66 passing Source product and publication tests, canonical and generated metadata checks, and the actual pinned Rashid conformance pass. The separate offline STAC advisory remains incomplete. The published catalog bytes, data, display archives, licenses and pinned historical inputs are unchanged.

[clean-checkout.json](clean-checkout.json) records regeneration from committed files alone: generated records, product READMEs and catalog bytes did not drift, and the new README-only plan matched the frozen plan exactly.

The exact [upload-plan.json](upload-plan.json) contains five mutable root READMEs totaling 24,996 bytes, with no immutable data objects. Its SHA-256 is `4c8f4756ee789aa369dcb58c75e54bd4b0a186ca213761811de00e0aaab1819e`. [prepare.py](prepare.py) can create a new plan from the current generated records and validate its five README-only selections. The user authorized the correction; Source CLI login expired and refresh failed, so live publication awaits login. There has been no data relocation or local deletion.

The [layout review](../../docs/source-product-layout.md) explains the earlier independent analytical/display revisions and compares flat and format-directory examples. A flat public layout is appropriate for these five small asset inventories. Local cache sizes, remote availability and a deletion inventory are reviewed separately before removing any files.

## Local copies and cleanup choices

The entire project `.local` directory measured 89.774 GiB by `du`; the eight targeted dataset/work directories account for 81.251 GiB. Nine current package directories hold 603 files that map to recorded Source uploads, totaling 18,500,215,163 logical bytes (17.23 GiB). The 12 actual published Parquet/PMTiles assets account for 18,287,510,721 bytes.

[local-cache-inventory.json](local-cache-inventory.json) lists 22 exact bulk-file paths, their SHA-256 values, canonical remote URLs, receipt mappings, dependencies and stat guards. Twelve are the current local data assets; ten are extra copies. [local-cache-hashes.json](local-cache-hashes.json) records fresh local hashes for all 22: all matched, with stable pre/post stats. [remote-assets.json](remote-assets.json) records fresh anonymous HEAD checks against the prior full remote-readback checksums: all 14 data/control URLs exist with the expected lengths (12 published assets plus two tiny diagnostic PMTiles). This is not a fresh complete remote download.

The ten redundant copies total **19,892,134,618 bytes / 18.53 GiB**. Removing all 22 would evict **38,179,645,339 bytes / 35.56 GiB**, retaining all small manifests, reports and source archives. Current disk-based previews would require restoration of the data; the Source/Portolan viewers read remote objects. The larger raw sources and old unmatched display builds are outside this plan. APFS clones and snapshots mean file allocation does not establish uniquely recoverable space.

The cleanup selection is pending user input. No local files have been deleted.
