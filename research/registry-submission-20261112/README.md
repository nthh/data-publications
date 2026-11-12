# Portolan registry submission

Status: technical preparation and publication checks complete; awaiting human review of the exact entry and PR text. No upstream pull request has been opened.

Review [nthh-data-publications.yaml](nthh-data-publications.yaml) and the [complete PR body](pull-request.md). The proposed title is `chore(catalogs): register nthh data publications`. The public contact is `data-publications@folia.sh`, supplied and confirmed by the user.

The latest [disposable CI run](https://github.com/nthh/data-publications/actions/runs/43321696725) passes the [registry gate](ci-r2/registry-validation.json), confirms [all 18 public metadata files](ci-r2/publication-match.json), and executes all six SQL example blocks. All 132 checked links answer. The [current catalog review is B](ci-r2/grader/report.md), with zero Rashid errors and two disclosed scope warnings. [All styles and thumbnails passed independent Source checks](presentation-hosting-r1.json), and the [official live browser review passed](cards-live/visual-review.json).

The [baseline D report](ci-r1/grader/report.md) and unmodified collector facts remain preserved. [Fixes and their scope](fixes.md), [frozen criteria](fix-criteria-r1.json), [data identity proof](data-identity-check.json) and [clean-checkout check](clean-checkout-fixes.json) document the changes. All six GeoParquet and six PMTiles asset entries are unchanged. Updated Source READMEs and presentation assets are published; the catalog fixes are on data-publications main and deployed through Pages.

The [register-catalog skill](https://github.com/portolan-sdi/portolan-skills/blob/1714d9ab672e6a1bbc56ca12458e41b14484d426/skills/register-catalog/SKILL.md) directs following the registry contribution requirements. Portolan's [AI policy](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/AI_POLICY.md#details) requires the contributor to approve both the diff and PR description before upstream review. The policy acknowledgment stays unchecked until that review; approval will authorize marking it and submitting the prepared PR.

[evidence-manifest-r2.json](evidence-manifest-r2.json) binds the latest collected review and browser artifacts. [Upstream freshness](upstream-freshness-r2.json) confirms the registry revision has not changed since the pinned validation. Scheduled checks, a logo and advanced query recipes are optional remaining improvements, not unresolved publication failures.
