# HydroLAKES r3 package input recipes

These templates reference the source-validated raw inputs, the detached clean-rebuild outputs, the completed spatial-order companions, and their fixed-window pruning receipts. They do not fetch source data or run a conversion.

Run `materialize_release_inputs.py fidelity` first. It verifies that the supplied clean worktree is detached, clean, and at the pinned `100eaad` commit before writing an ignored fidelity input. Then run the strict `bind_fidelity.py` normalizer. Only after it passes, materialize the package input and run `package_release.py`; the package helper writes immutable receipts and preserves any failed gate reports.

Use new output paths. The package output is local and unpublished.
