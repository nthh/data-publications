# Local release review — 2026-10-30

A read-only review checked the completed GRWL evidence while the GRIP4 build from
commit `2319710` was still running. This note records review scope and a known
metadata defect; it is not an additional source-fidelity test report.

## GRWL

The review matched the versioned manifest hash, six verification reports,
package bindings, 13 reproduced asset hashes and 15 workflow-input hashes to
conversion commit `9e2239d`. It inspected the archive's 42-member directory and
matched the embedded small manifests, reports, workflow files and dataset
snapshots. It did not rehash the bulk data or whole archive; those checks belong
to the already recorded build and package verification.

Canonical publication claims agree with the evidence: locally prepared, not
hosted or submitted; exact source comparison; a same-machine clean rebuild;
a sampled follow-up display diagnostic; and no GEE parity claim for the newer
V01.02 source. The review found no material contradiction.

## GRIP4 first-build evidence

A second read-only review checked the completed source, tile, schema, HTTP and
fault reports before the clean rebuild finished. All four reports bind to
manifest SHA-256 `eab3b57b5bd796fa9577fb1b4512b61cc43da9fd5fd3bcf2ab2a69c6a078815d`.
The canonical configuration/snapshot and all 18 workflow-input hashes agree with
conversion commit `2319710`.

Exact comparison passed for 25,758,453 records, 309,101,436 source cells and
286,775,634 vertices across seven regions. Both STAC documents passed, with none
skipped; Portolan reported no errors or warnings; local HTTP queries passed.
Display zoom 10 retains 18,344,569 source IDs (71.22%). Every region occurs at every
zoom, and the 1,032 sampled geometries meet the registered distance criterion.

The fault report contains ten fixture checks: eight negative fault cases and two
positive controls. The separate workflow test log records 19 passing tests. The
review did not repeat bulk hashing or heavy validation. Shared GDAL decoding,
sampled display geometry, and absent GEE, public-host and observational validation
remain explicit limits. At the time of this review, rebuild and packaging were
pending; their eventual reports are separate release gates.

## GRIP4 packaging metadata follow-up

At conversion commit `2319710`, `datasets/grip/package.py` populates the optional
package-manifest `release` property from a root manifest field. The build stores
that value at `manifest.source.release`, so the optional package property will
be null. Identity remains bound by the exact source/build configuration, dataset
snapshot, conversion commit, archive name and hashes. This does not fail the
registered source-fidelity or packaging gates and is treated as a nonblocking
metadata defect.

Keep the active run's inputs unchanged. A future workflow revision should read
`manifest.source.release` and add a focused assertion. Do not rewrite an already
issued archive or its evidence to hide the field. Any later package metadata
amendment must identify and checksum-bind the original archive. The eventual
GRIP4 release note should disclose the null optional property and point readers
to the authoritative nested release value.

## Selection review

The GRIP4/Overture note distinguishes exact native copies from current alternatives
and historical preservation. The saved 747-record Source Cooperative snapshot
contains `fused/overture` transportation metadata. This is evidence of an existing
representation, not proof of its latest version, availability or data quality.
The review made no fresh comparative coverage test, GEE request or upload.

## Final GRIP4 decision

The user subsequently chose to stop the remaining rebuild and retain validated
files. [The retained evidence](../../datasets/grip/evidence/validated-run-02/README.md)
records passing first-build checks and incomplete reproducibility/package gates.
GRIP4 is deferred from publication; only the river-plastic pilot and GRWL are
prepared. The unused package writer metadata defect remains a future-code issue;
no GRIP package containing it was issued.
