## Summary

Register Data Publications, an independently maintained catalog of five global water datasets.

## What changed

Add `catalogs/nthh-data-publications.yaml` with the published root URL and `data-publications@folia.sh` as the public contact.

The catalog links Free-Flowing Rivers, GRWL raw observations, HydroLAKES, LakeATLAS and river plastic inputs. Data stays on Source Cooperative; catalog metadata stays on GitHub Pages.

## Why

Make these existing publications discoverable through the Portolan registry. This is a catalog-entry addition with no registry software change.

## Verification

The registry's pinned submission validator passed against the live catalog, including its metadata mirror, Rashid 0.3.0 and stac-node-validator 2.0.0. It found no duplicate ID or URL.

[CI run](https://github.com/nthh/data-publications/actions/runs/43313650354)

The catalog-grader review is **D**, with the findings disclosed in the [review report](https://github.com/nthh/data-publications/blob/docs/portolan-register-20261112/research/registry-submission-20261112/ci-r1/grader/report.md). The broader live Rashid check reports two GitHub Pages CORS errors. Catalog documents lack runnable examples, agent guidance is generic, and several styles are flat. All 92 collected links answered and all five thumbnails loaded. This PR does not claim those quality gaps are fixed.

- [ ] I have read and complied with the [contributing guide](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/CONTRIBUTING.md) and [AI policy](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/AI_POLICY.md).
- [x] This change does not alter behavior (docs, chore, or CI only).

## Implementation notes

The entry contains only the root URL and contact email. The registry extracts dataset metadata from the catalog. The maintainer and processor remain `nthh`.

## Related issues

None; this is a new catalog registration.
