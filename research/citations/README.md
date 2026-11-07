# Citation snapshot

Counts reflect the **2026-10-29 OpenAlex snapshot**, not live totals. Read
[methodology.json](methodology.json) and the reviewed DOI/title matches alongside
[rankings.json](rankings.json). The metric is the maximum citation count among
associated publications for each family, not a sum of overlapping papers.
Dataset-DOI citations are separate. An unknown count is not zero. A cited parent
paper can cover a broader model or data family than the particular asset.

237 families have a matched publication count, 81 a data-DOI count, and 271 at
least one of those; 92 remain unknown. Of 206 global families, 153 have publication
counts. High citation counts help prioritize review; they do not establish reuse
rights, source quality, cloud-native availability or suitability for republishing.

The normalized provider results, title searches and reviewed identities included
here are sufficient to reproduce the ranking offline:

```sh
uv run --locked python scripts/rank_citations.py --check
```

The normalized data and identity decisions were migrated from the original audit;
raw API request logs are not included. This command checks deterministic ranking
from the saved inputs and makes no new provider request. The pilot's original
Figshare metadata and source-inspection reports are also retained in this folder.
