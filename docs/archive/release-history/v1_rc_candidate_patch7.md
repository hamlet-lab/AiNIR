# v1.0 RC Candidate Patch 7 — Repo-local Temp Isolation Guard

Patch 7 keeps the AiNIR RC candidate scope unchanged and tightens the private-trial runner around local temporary output paths.

## What changed

- Phase 26 now keeps its copied trial workspace outside the repository checkout even if `TMP` / `TEMP` points inside the repo.
- Common local temp folders such as `.codex_tmp/`, `.ainir_tmp/`, `codex_ainir_*`, `github_private_trial_results/`, and `ainir_phase*_trial_*/` are ignored during temp-copy setup.
- Repo-local temp folders are reported as warnings during private-trial simulation so they can be cleaned before publishing.
- Child commands run with a sanitized `AINIR_TEMP_ROOT` outside the source checkout and outside the copied trial repo.

Patch 7 does not add integrations, does not change verifier semantics, and does not claim production runtime readiness.
