# Local GRWL and GRIP4 releases

Acceptance criteria recorded before conversion on 2026-10-30. The dataset-specific
VALIDATION.md files and selection evidence remain the source of detailed criteria.

- Download only pinned public producer inputs. Verify size, MD5, SHA-256 and archive CRCs.
- Preserve every source feature, attribute, null, geometry and source identifier in
  analytic GeoParquet. Document exact field and geometry mapping before conversion.
- Keep PMTiles a documented display derivative. Record zoom, simplification,
  thinning and coverage criteria before evaluating it.
- Validate the complete analytic conversion against a separate read of the source;
  use bounded batches for GRIP4. Hash equality supplements explicit value checks.
- Validate GeoParquet, PMTiles, relative STAC/Portolan metadata and loopback HTTP
  range/CORS/subset behavior. Exercise failures that lose/duplicate/change data.
- Rebuild from committed code in a clean checkout and compare deterministic assets.
- Bind a local immutable release manifest and package to source pins, code/locks,
  validation evidence and actual output checksums. Keep bulk inputs/outputs ignored.
- Preserve previous releases and failed evidence. Report research/GEE comparisons
  as unrun unless actually performed; no new GEE requests, remote writes or uploads.

Ownership: the GRWL worker owns only datasets/grwl and .local/grwl in this task
worktree; the parent owns GRIP4, shared repository files, commits and integration.
Read-only reviewers may inspect either. Native conversion uses at most two threads
per dataset; GRIP4 source reading/writing uses bounded Arrow batches. Check available
disk before large duplicate builds; preserve enough space for the machine's other work.

The existing river-plastic release is unchanged. Public publication remains pending.
