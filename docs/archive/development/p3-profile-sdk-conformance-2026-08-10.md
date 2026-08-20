# P3 — Profile SDK and standalone conformance runner

Status: implemented and validated locally on `codex/004-profile-sdk-conformance`.

## Delivered

- stable Profile Manifest, Conformance Pack, and Conformance Report v1 contracts;
- bundled `ainir.public-demo.v1` workflow profile;
- `profile init`, `validate`, `inspect`, and workflow-aware `list` commands;
- isolated additive profile compiler with protected-registry collision checks;
- context-local registry bundles that restore the packaged default on exit;
- standalone conformance runner with console, JSON, JSONL, JUnit, and YAML reports;
- migration adapters for the existing 10 golden traces and 71 negative cases;
- profile-bound registry snapshots and TrustReceipt replay;
- public schemas, wheel/sdist package data, docs, CI, and regression coverage.

## Preserved behavior

The packaged profile uses the existing registries without an override. Existing public decisions, the safe receipt ID, registry snapshot hash, and stable receipt projection remain unchanged. Unknown profile workflows remain refused outside an explicit profile context.

## Security boundary

Profiles are additive and conformance-only. They cannot:

- overwrite packaged workflows, operations, evidence IDs, or registry entries;
- replace core fail-closed policies or remove Trust Gate checks;
- create effect aliases, role-marker classifiers, external-effect allowlists, or effect-to-capability contracts;
- use broad effect families or capability-prefix rules in place of exact contracts;
- introduce effect/capability identifiers outside the packaged reviewed vocabulary;
- launder safety-critical operation names through profile aliases;
- use legacy corpus source adapters outside the bundled public profile;
- declare vacuous positive, refusal, mutation, or replay expectations;
- nest profile registry contexts or reuse the reserved bundled profile identity.

`profile_fixture` evidence exists only inside the isolated conformance bundle. It is not a production credential, provider assertion, signature, or runtime authorization. AiNIR core still does not execute downstream actions.

## Validation evidence

- repository tests: 225/225 passed in non-overlapping groups;
- P3-focused tests: 17/17 passed;
- bundled profile: 81/81 cases passed;
- generated additive scaffold: 4/4 cases passed;
- negative conformance corpus: 71/71 passed;
- golden traces: 10/10 passed;
- public demo: passed;
- Phase 30 quick-integrity: passed;
- Phase 30 full decision: `v1_0_rc_candidate_ready_for_private_github_trial`;
- wheel/sdist distribution-contract checks: all passed;
- installed-wheel bundled-profile validation and 81-case conformance: passed;
- source/wheel schema and registry hashes: identical;
- Draft 2020-12 schema checks for bundled and generated profiles/reports: passed;
- generated TypeScript skeleton strict compile with TypeScript 5.8.3: passed;
- 129 relative Markdown links checked with no missing target;
- Python AST scan found no direct `eval`, `exec`, or dynamic `compile` calls.

## Environment limitation

Local `npm ci` could not download the lockfile-pinned TypeScript 5.8.3 tarball because the execution environment's internal npm mirror returned HTTP 404. The lockfile still references the standard npm registry, and the matching globally installed TypeScript 5.8.3 compiler successfully performed the strict compile. Hosted GitHub Actions evidence remains pending until the branch is pushed.
