# Final-rehearsal failures retained

The first committed clean-checkout run (4d230a0) passed exact numeric, multipart
geometry, complete maximum-zoom ID coverage and loopback HTTP checks. Actual STAC
schema validation then rejected relative `self` links: STAC requires absolute
IRIs for that relation. The portable catalog omits optional self links instead of
inventing public URLs. Its schema report is preserved separately from the passing
source-conversion report. Review also corrected the relative PMTiles style source
and added exhaustive tile extent/type checks before the follow-up rehearsal.
No successful package or publication was claimed for this initial run.
