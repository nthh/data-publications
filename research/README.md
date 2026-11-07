# Frozen intake and prioritization evidence

The three `gee-community-audit-20261029` inputs are preserved byte-for-byte;
`intake.json` at the repository root pins their SHA-256 values. They describe
363 GEE Community Catalog documentation families from upstream commit
`ca7e707b8f12442630c0212564d701f81f1be203`, rather than 363 uniform data products.
Folia and native-format coverage findings are identified counterparts and
partial-coverage leads, not proven exhaustive availability.

`citations/` retains the OpenAlex snapshot and reviewed identity decisions used
for ranking. `availability/` retains the targeted source and format reviews.
These are historical inputs. References to earlier checkout paths describe the
original audit context; no access to that checkout is required for validation.
The full upstream Markdown corpus and original Folia registry were not copied.
Rebuilding the original availability search would require those source snapshots.

Canonical triage decisions now live only in `datasets/<id>/dataset.yaml`.
The frozen audit and citation files must not be edited to make a candidate look
better; record new evidence in a separate dated snapshot and update its links.
