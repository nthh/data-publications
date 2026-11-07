# Official and community citation comparison

Criteria and cost limits are fixed in methodology.json before scoring.

1. Capture a fresh, bounded public STAC metadata snapshot with source URLs, timestamps and content hashes. Commit normalized citation contexts and geography; keep full raw metadata in ignored local storage.
2. Extract references and review paper/data/background roles and geographic scope without citation counts. Use bounded independent review shards with a single parent writer for scripts and synthesis.
3. Resolve reviewed references through OpenAlex. Refresh the already reviewed community identities into this new study, preserving the original snapshot. Retain responses and requests so scores can be rebuilt offline.
4. Emit official, community and combined entry rankings, global and active views, shared-paper groups, and explicitly typed overlap candidates. No automatic equivalence merge.
5. Validate coverage, roles, identity, missing values and deterministic rebuilds. Review leading groups and report gaps. Commit locally and integrate verified work into the standalone repository; no push or upload.

Delegated reviewers may write only their assigned review JSON under this study, must not view citation counts or alter scripts/records, and must report sources, assumptions, unresolved references and checks. The parent owns the final repository state.
