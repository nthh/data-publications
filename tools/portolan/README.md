# Publication validation tools

This locked environment runs Rashid 0.3.0 as the Portolan conformance gate and stac-check 1.14.0 as advisory linting. It is separate from the dataset conversion environments. Portolan CLI 0.8.0 requires Rashid below 0.2.0, so it cannot share this environment; the prior audit records its separate checks.

From the repository root:

```sh
uv sync --locked --project tools/portolan --python 3.12.12 --no-build
uv run --locked --project tools/portolan python scripts/check_portolan.py --catalog catalog --report .local/checks/catalog-001.json
uv run --locked --project tools/portolan python -m unittest discover -s tests -p test_portolan_gate.py -v
```

Choose a new report path for each run. Reports are never overwritten. The default check covers the Portolan profile, STAC structure and declared extension schemas, without reading data assets or probing hosts. The console entrypoints run with Python socket connections disabled; a missing schema that requires networking fails visibly. Rashid errors, warnings, missing/unparseable output and mismatched pinned tool versions fail the gate. Informational findings remain in the report.

stac-check runs with asset URL requests disabled and no link probes. Its findings, schema-fetch failures and crashes are recorded separately; an incomplete advisory run is not a passed advisory check. It does not override the Rashid result. Installation of locked dependencies is the only network-dependent setup step.

`--local-data` additionally checks assets inside the specified local catalog tree. It leaves remote assets unread, so use the existing dataset/package validation workflows for complete release-byte checks. Public-hosting verification and scientific/source-fidelity validation are separate gates.

[The pins](pins.json) record tool versions, consulted spec/skill commits, Python/uv versions and immutable CI action references. Update these intentionally and run both the positive and missing-license controls. [The lock](uv.lock) pins transitive dependencies.
