# Historical validation provenance

`index.json` maps original snapshot paths and commits to content-addressed files
in `blobs/`. These are exact historical bytes, including prior failed reports.
They are evidence, not the active workflow or a second dataset inventory.
The original repository and its private Git history are not needed to verify them.
`original-publication.json` preserves the earlier source-package inventory.
Historical files may mention the old layout, local paths and the GEE quota project;
those identifiers are provenance, not credentials or current defaults.

The active source and build settings are in `../dataset.yaml`. New reports belong
under `../releases/<release>/`; never rewrite older contracts or evidence to pass.
