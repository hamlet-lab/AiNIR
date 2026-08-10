# P4 — Registry evolution and TrustReceipt replay modes

Status: implemented and validated locally on `codex/005-registry-evolution-replay`.

## Delivered

- `RegistrySnapshot v1` artifacts containing canonical safety, operation, evidence, and consumer-profile registry data;
- cross-binding between the portable evolution snapshot and the existing receipt-bound runtime registry hash;
- deterministic `RegistryDiff v1` reports with conservative change classification;
- explicit `RegistryMigrationRecord v1` artifacts binding source, target, diff, reviewer, evidence reference, and self-hash;
- `exact_snapshot_replay`, `current_registry_replay`, and `migrated_registry_replay` APIs and CLI modes;
- receipt issuance sidecars that preserve the historical TrustReceipt while retaining the exact registry content used for evaluation;
- JSON Schemas, strict Python validators, wheel/sdist package data, documentation, CI, Phase 30, and installed-wheel distribution checks.

## Replay semantics

### Exact snapshot replay

Exact replay retains the historical AiNIR behavior: the draft, trusted context, registry hash, verifier report, gate result, and stable receipt projection must reproduce the stored receipt. A registry change is not silently accepted.

### Current-registry replay

Current replay does not rewrite or reinterpret the historical receipt. It reports the historical status and independently evaluates the same draft under the active registry. A successful replay means the comparison completed and passed integrity checks; it does not imply that the current Trust Gate decision is `passed`.

### Migrated-registry replay

Migrated replay requires an exact source snapshot, a target snapshot, a semantic diff, and a migration record that binds all three. AiNIR reconstructs the target registry and reruns the full Trust Gate. A migration record never directly promotes a historical refusal to a pass.

## Change classification

Registry changes are classified as:

- `tightening` — a reviewed constraint becomes stricter;
- `compatible` — canonical semantics are unchanged;
- `behavioral` — behavior changes without a defensible one-way security ordering;
- `relaxation` — an existing restriction is weakened;
- `breaking` — an existing required identity or contract is removed or replaced;
- `unknown` — AiNIR cannot safely classify the change.

Unknown changes are never treated as compatible. Boolean security-policy fields, required/forbidden sets, allowed/trusted flags, operation/evidence identity changes, and unrecognized fields receive explicit conservative handling.

## Security boundary

- historical receipt bytes are hashed before and after replay and are never rewritten;
- snapshot component data must reproduce the embedded runtime component hashes and combined registry hash;
- outer profile identity must match the runtime snapshot identity exactly;
- duplicate IDs, unknown fields, path substitution, snapshot/diff/migration cross-binding drift, and report contradictions are refused;
- exact/current/migrated mode arguments are mutually constrained rather than silently ignored;
- migration review is a bounded local authorization record, not a cryptographic signature;
- unsigned migration replay is refused by default and requires an explicit local opt-in;
- every migration report remains `production_runtime_ready: false` until cryptographic authorization and production governance are implemented;
- AiNIR continues to evaluate semantic warrant only and does not execute downstream actions.

## Validation evidence

- repository tests: 238/238 passed in non-overlapping groups;
- failures, errors, and skips: 0;
- P4-focused tests: 13/13 passed;
- public demo: passed;
- negative conformance corpus: 71/71 passed;
- golden traces: 10/10 passed;
- bundled public profile: 81/81 passed;
- preserved receipt-bound registry hash: `sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a`;
- Phase 30 full: passed;
- Phase 30 decision: `v1_0_rc_candidate_ready_for_private_github_trial`;
- wheel/sdist distribution contracts: 11/11 passed;
- installed-wheel exact/current/migrated replay: passed;
- unsigned migration default refusal and explicit local opt-in path: passed;
- historical receipt unchanged checks: passed;
- JSON 24 and YAML 34 files parsed successfully;
- Draft 2020-12 schema self-validation: 10 schemas passed;
- root/package schema and registry bytes: identical;
- relative Markdown links: 134 checked, 0 missing;
- generated TypeScript skeleton strict compile with TypeScript 5.8.3: passed;
- Python AST scan found no direct `eval`, `exec`, dynamic `compile`, or `shell=True` calls in `src/` and `scripts/`;
- embedded private-key and common hard-coded credential patterns were not found in the scanned public source set.

These checks are reproducibility and defensive-integrity evidence, not a claim of independent security certification or absence of vulnerabilities.

## Environment limitations

The local runtime is Python 3.13 on Linux. Python 3.10–3.13 and Windows/macOS workflows are defined, but hosted-runner evidence remains pending until the branch is pushed.

A global `pip check` reports an unrelated MoviePy/Pillow conflict in the shared execution environment. AiNIR's runtime metadata was checked independently and its sole runtime dependency, `PyYAML>=6`, is satisfied by PyYAML 6.0.3. The isolated wheel installation and runtime contract checks passed.

The execution environment's internal npm mirror may not serve the lockfile-pinned TypeScript 5.8.3 tarball. The matching globally installed TypeScript 5.8.3 compiler completed the strict generated-code check.

## Next bounded development target

P5 should define deterministic offline `EvidenceProvider` contracts and fixture/file/signed-bundle provider adapters. It must preserve the rule that provider output is not automatically trusted: issuer identity, scope, integrity, validity, expiry, and revocation state remain AiNIR-validated inputs.
