# Candidate records

`candidates/<id>/dataset.yaml` holds the single canonical record for a discovery-only dataset. These records are public metadata; they are not promises to build or publish a product. The generated [candidate backlog](../CANDIDATES.md) and [shortlist](../SHORTLIST.md) summarize repository-wide discovery and selection views. Do not maintain a second inventory here.

When a candidate is selected for build or preparation, move its record and directory into the dataset workspace with `git mv candidates/<id> datasets/<id>` before adding scripts, evidence, or release files. Keep one record per ID and never copy it. See [publishing guidance](../docs/publishing.md) and the [record template](../docs/dataset-template.md).

The [layout migration](../research/candidate-layout-20261109/README.md) records the 443 unchanged moves and verification. Dated research captures retain their original paths and counts; replay their original import scripts at the recorded pre-move commit. Current CI validators and generated views read both roots.
