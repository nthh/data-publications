# GRIP4 validated local build; publication deferred

The user stopped the clean-checkout rebuild on 2026-10-30 after reviewing Overture
as the preferred current-road source. The first build remains validated and is
retained for historical research. It is **not a prepared or packaged release**.

Conversion commit: `23197105f3ac45d890330a466594921fe35d8f27`.
Manifest SHA-256: `eab3b57b5bd796fa9577fb1b4512b61cc43da9fd5fd3bcf2ab2a69c6a078815d`.
The 22 first-build assets were copied to `.local/grip/grip4-2018-r1-validated` in
the primary repository and all copied asset sizes/hashes were verified against
that manifest. Source archives remain in `.local/grip-source`.

Full source comparison passed for 25,758,453 roads, 309,101,436 source cells and
286,775,634 vertices across seven GeoParquet partitions. STAC, Portolan and
loopback HTTP checks passed. Ten fixture checks comprise eight negative faults
and two positive controls; the separate workflow suite passed 19 tests.

Every tile ID and attribute was audited. At zoom 10, the display retains
18,344,569 source IDs (71.22%), with all seven regions represented at every zoom.
The 1,032 sampled display geometries stayed below the registered four-tile-unit
limit; maximum observed distance was 1.5675 tile units. GeoParquet preserves the
complete source. Both source readers use GDAL, so this is conversion-fidelity
evidence, not an independent test of the decoder or the producer's accuracy.

The seven rebuilt analytic files matched byte-for-byte before cancellation.
PMTiles regeneration and the complete manifest comparison did not finish.
The cancellation receipt inventories the discarded rebuild intermediates and
retains their hashes; the validated first build, source cache, clean checkout
and logs remain. No package, GEE request, public hosting check or registry
submission was made.

See [validation](validation.json), [STAC](stac-validation.json),
[Portolan](portolan-validation.json), [faults](fault-tests.json),
[workflow tests](workflow-tests.log), [manifest](manifest.json), and
[cancellation](cancellation.json). The [selection review](../../../../research/local-build-two-20261030/grip-overture-review.md)
explains the decision to defer current-road publication.
