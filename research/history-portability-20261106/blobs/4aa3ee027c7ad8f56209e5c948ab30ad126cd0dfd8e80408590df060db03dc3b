# Release tools instructions

- Keep this helper generic. Dataset-specific source conversion and fidelity rules belong to each dataset's workflow.
- Never upload, create remote repositories, submit a registry, or edit canonical dataset records from this package helper.
- Do not overwrite an existing release output path. Preserve partial schema/range failures with explicit failed status.
- Require both source-fidelity and clean-rebuild reports to pass and bind exact asset IDs, SHA-256 values, and byte sizes before creating a package.
- Copy data with APFS clone where available; otherwise verify free space first. Never hardlink or mutate source data.
- Keep local HTTP reads capped, bounded, and streaming. Test with small fixtures and actual STAC/Portolan validators.
- Keep public hosting and registry status separate from local preparation status.
