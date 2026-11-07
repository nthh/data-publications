# Initial preflight failures

The a304e89 implementation's tiny catalog fixture failed the actual Portolan and
STAC extension schema checks: missing root README/AGENTS links and unsupported SVG
thumbnail media type. The first full GRIP4 build was interrupted after source
streaming to repair the committed workflow before final release. Its ignored
run-01 logs/partial outputs remain local; no passing release was claimed.

Independent review also found standalone package acceptance of an unrun HTTP
check, an incomplete packaged workflow layout, a relative PMTiles URL that needed
explicit client resolution, Zenodo incorrectly described as licensor, and the
producer XLSX country-code columns omitted from the derived dictionary. These
are implementation defects, not reasons to relax the source fidelity contract.
The follow-up must pass the original gates after the fixes are committed.
