## Summary

Register Data Publications, an independently maintained catalog of five global water datasets.

## What changed

Add `catalogs/nthh-data-publications.yaml` with the published root URL and `data-publications@folia.sh` as the public contact.

The catalog links Free-Flowing Rivers, GRWL raw observations, HydroLAKES, LakeATLAS and river plastic inputs. Data and map assets are hosted on Source Cooperative; catalog metadata is hosted on GitHub Pages.

## Why

Make these existing publications discoverable through the Portolan registry. This is a catalog-entry addition with no registry software change.

## Verification

The [submission review CI](https://github.com/nthh/data-publications/actions/runs/43321696725) passed the registry's pinned metadata validator, Rashid 0.3.0 and stac-node-validator 2.0.0. It also confirmed that all 18 public catalog metadata files match the reviewed checkout.

The unmodified collector ran all six documented SQL blocks successfully, checked 132 links with none broken or unverified, and loaded all five thumbnails. The [catalog review is B](https://github.com/nthh/data-publications/blob/main/research/registry-submission-20261112/ci-r2/grader/report.md).

Rashid reports zero errors and two scope warnings: remote crawling cannot see unlinked files, and its live pass skips Source assets on another host. [Separate anonymous hosting checks](https://github.com/nthh/data-publications/blob/main/research/registry-submission-20261112/presentation-hosting-r1.json) verify every style and thumbnail by full checksum, byte range and CORS. Local-tree validation and the official Portolan browser check also pass. The broader stac-check advisory remains incomplete and is not counted as passing.

The data retain their documented source/GEE differences and scientific limitations; this registration is not a claim of strict GEE parity or independent scientific validation.

- [ ] I have read and complied with the [contributing guide](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/CONTRIBUTING.md) and [AI policy](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/AI_POLICY.md).
- [x] This change does not alter behavior (docs, chore, or CI only).

## Implementation notes

The entry contains only the root URL and contact email. The registry extracts dataset metadata from the catalog. The maintainer and processor are `nthh`.

## Related issues

None; this is a new catalog registration.
