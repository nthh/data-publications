# Candidate record layout — 2026-11-09

Moved 443 discovery-only records from `datasets/` to `candidates/`. The 10 workspaces with conversion, preparation or historical validation files stay under `datasets/`; five are published. Records remain public and retain their original IDs and exact bytes. Promotion uses `git mv candidates/<id> datasets/<id>`; validators reject duplicate IDs across roots, and Source product preparation and published records require a dataset workspace.

[plan.json](plan.json) freezes the original 443 file hashes, the 10 retained IDs, the 29 generated catalog hashes and acceptance criteria against commit `28ed3ffc7f6c2703d7f337473100c75b996d3c46`. [migration-check.json](migration-check.json) proves that only record paths changed in generated inventory values and order; all 453 records, existing workspace files, release inputs, historical observations and generated published metadata are unchanged. The staged metadata plan matches the previously deployed plan SHA-256 `884581bec5d7fd9c678cbcbbf7ee5af36a335639a48aecf7da950169a21dda4d`.

The shared lookup is `scripts/record_locations.py`. Current inventory, backlog, shortlist, related README, citation and publication tools use it. Two historical-directory validators still invoked by CI (`citations/check_review.py` and `reuse/check.py`) also use it; their observations remain frozen. Original capture/import scripts and historical reports retain their original paths and counts. To replay that historical layout, check out the base commit above in a separate worktree. Fixed conversion, viewer and GEE consumers continue using the retained dataset workspaces.

[checks.json](checks.json) records passing metadata, source-product, citation and provenance checks and 193 resolved relative documentation links. [focused-tests.txt](focused-tests.txt) records 119 passing focused tests, including nine layout/promotion regressions. The initial eight regression tests failed against the old implementation; their [baseline output](baseline-tests.txt) is retained. Machine and temporary fixture prefixes in these logs have been replaced with placeholders. CI now includes the new layout and existing availability checks.

Repeat the migration audit from a checkout containing the base commit (use a new stage destination):

```sh
uv sync --offline --locked --no-build
uv run --locked python scripts/catalog.py --check
uv run --locked python scripts/source_products.py check
uv run --locked python scripts/publication_catalog.py check
uv run --locked python scripts/publication_catalog.py stage .local/layout-review
uv run --locked python research/candidate-layout-20261109/verify.py --stage .local/layout-review
uv run --locked python -m unittest tests.test_record_layout tests.test_candidate_discovery tests.test_dataset_availability tests.test_publication_catalog tests.test_source_products -v
uv run --locked python scripts/test_catalog.py
```

The offline install requires the pinned Python and wheels in the local cache; omit `--offline` for an initial dependency install. [clean-checkout.json](clean-checkout.json) records the successful rehearsal at commit `1ec3270b6f5fa6ff334ae0eced654694b5736b2f`: all three generators ran from committed files alone, 25 layout/availability tests passed again through their CI invocation, the final Git status was clean, and the staged plan still matched the deployed bytes. This is a repository layout change; it adds no source, GEE, scientific accuracy, or live hosting validation claims. No upload or deployment is part of this migration.
