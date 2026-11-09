# Contributing

This repository manages datasets as reproducible, reviewable releases. Keep one canonical record per ID: discovery-only records live at `candidates/<id>/dataset.yaml`, while selected build, preparation, and history workspaces live under `datasets/<id>/`. Promote with `git mv candidates/<id> datasets/<id>` before adding workflow files. Generated repository-wide views read both roots; edit source records and regenerate them instead of hand-editing indexes.

## Before evaluating a dataset

Write down the question, acceptance criteria, comparison method, tolerances, data split or geographic scope where relevant, and known limitations before examining new results. Keep the dated criteria with the dataset's research or validation notes. Report failures as results: do not erase or relabel a failed check when adding a justified follow-up diagnostic. State what a check establishes and what it does not.

## Dataset changes

For each dataset change:

1. Pin the original source by stable URL or identifier, version, size and cryptographic checksum. Record provider checksums separately from SHA-256.
2. Confirm redistribution terms for the source, paper, code and any external evidence. Record attribution, license URL, units, null meaning, uncertainty, geometry/grid, temporal coverage and record multiplicity.
3. Keep conversion code, scripts, lockfiles, metadata and concise receipts in Git. Keep bulk inputs, outputs, credentials and raw captures out of Git.
4. Build to a new output path. Never overwrite a released version or replace a historical report in place.
5. Validate source parity, format structure, catalog metadata, and any research claims against written criteria. Rebuild with the same code and compare asset hashes.
6. Package a new immutable release with the manifest and latest reviewed evidence. Review the archive contents, checksums, license notices and public-facing documentation before publication.

Use dataset-specific commands and locked environments in each dataset README. Keep commands offline by default. Do not start live GEE retrievals, exports, cloud jobs, uploads or registry submissions unless the task explicitly authorizes them.

## License boundary

Repository-authored software and documentation are offered under Apache-2.0, subject to retained notices. This does not automatically apply to imported scripts or datasets: identify their original license and preserve its terms and attribution. Dataset-specific terms must remain visible in `dataset.yaml`, release metadata and any distributed bundle.
