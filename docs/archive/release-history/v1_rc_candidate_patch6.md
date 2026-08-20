# v1.0 RC Candidate Patch 6 — Release Identity and Cross-platform Temp Paths

Patch 6 keeps the AiNIR RC candidate scope unchanged and fixes two public-trial polish issues.

## Changes

- Updated `release/v1_0_rc_candidate_manifest.yaml` so the release identity matches Patch 6.
- Added cross-platform temp-path defaults based on `tempfile.gettempdir()`.
- Added `AINIR_TEMP_ROOT` as an optional override for review-script output.
- Updated README / START_HERE to show Windows PowerShell output-path alternatives.
- Updated GitHub Actions to rely on the script default temp path instead of hard-coding `/tmp`.

## Non-goals

Patch 6 does not add integrations, does not change verifier semantics, and does not claim production runtime readiness.
