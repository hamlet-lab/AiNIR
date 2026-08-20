# AiNIR priority development plan — August 2026

This plan follows the reproducible baseline in `baseline-2026-08-09.md`. Work is ordered to improve public usefulness without widening the trust boundary prematurely.

## P0 — Baseline, CI truthfulness, and governance

Status: completed on branch `codex/001-baseline-scope`.

Delivered:

- full pytest gate before Phase 30 quick-integrity;
- robust recognition of locked editable installs;
- public scope and protected invariants;
- security, support, maintainer, CODEOWNERS, PR, issue, and agent guidance;
- baseline and open-source-readiness regression tests.

Exit evidence:

- 183/183 tests pass when executed in bounded groups;
- public demo, 71 negative conformance cases, 10 golden traces, TrustReceipt replay, wheel smoke, and strict TypeScript compile pass;
- packaging, structured-file, link, CI-pin, and tracked-cleanliness checks pass.

## P1 — Release identity and distributable contracts

Status: completed locally on branch `codex/002-release-contracts`; hosted Python/OS matrix evidence remains pending until push.

Why first: the built artifact currently advertises `0.1.0`, while `ainir.__version__` and the release documentation identify a v1.0 RC. Public schemas are present in the repository but absent from the wheel.

Work:

1. choose one explicit release identity for the next candidate;
2. make Python package metadata and runtime `__version__` derive from one source;
3. decide whether npm metadata tracks the Python release or remains an internal compile fixture;
4. package public schemas under importable resources;
5. expose a supported resource API for schemas and registries;
6. add wheel-content, wheel-install, and source-distribution tests;
7. add a release-identity consistency test across metadata and manifest;
8. add Python 3.10–3.13 CI and Windows/macOS smoke jobs;
9. keep TypeScript 5.8.3 during this PR; evaluate the current major separately.

Acceptance:

- one version value across public Python surfaces;
- every documented public schema is available from an installed wheel;
- clean-wheel CLI works outside the checkout;
- registry and schema hashes are stable across source and wheel installs;
- no Trust Gate decision changes.

## P2 — Stable public CLI and contract versions

Status: completed locally on branch `codex/003-stable-cli-contracts`; hosted CI evidence remains pending until push.

Why implemented: the public CLI and serialized objects expose historical phase numbers, which makes compatibility hard to understand.

Work:

- introduce user-facing command groups: `trust`, `receipt`, `profile`, `conformance`, and `registry`;
- keep historical phase commands as hidden deprecated aliases for at least one release candidate;
- publish stable identifiers for TrustGateDecision, TrustReceipt, replay report, and profile manifest;
- retain legacy parsers and exact replay for existing `pre_v1_phase*` artifacts;
- move canonicalization and schema validation into supported modules rather than private helper imports.

Acceptance evidence:

- old commands and receipts remain reproducible;
- new commands produce equivalent decisions and stable contract versions;
- deprecation messages identify the replacement command on stderr;
- stable and legacy receipts exact-replay successfully;
- public entry-point docs and the private-trial runner use phase-independent commands.

## P3 — Profile Authoring SDK and standalone conformance runner

Status: completed locally on branch `codex/004-profile-sdk-conformance`; hosted CI evidence remains pending until push.

Why: external contributors need a safe extension surface that does not require editing Trust Gate core code.

Work:

- define Profile Manifest v1;
- implement `ainir profile init|validate|inspect|list`;
- move current public workflows into a built-in profile without changing behavior;
- require operations, effects, capabilities, evidence, transactions, positive cases, negative cases, mutation cases, and replay expectations;
- implement `ainir conformance run` with console, JSON, JSONL, and JUnit output;
- make core invariants non-overridable by profiles.

Acceptance:

- a new profile can be added without modifying core verifier code;
- a profile cannot remove a required gate or widen an unknown semantic into a pass;
- existing public workflow decisions and receipt projections remain unchanged.

Delivered evidence:

- bundled public profile validates and runs 81/81 migrated cases;
- generated additive scaffold validates and runs 4/4 positive, negative, mutation, and replay cases;
- profile context is isolated and restores the packaged registry snapshot on exit;
- protected workflow collisions and fail-open policy changes are refused;
- default consumer-profile CLI output remains compatible with P2.

## P4 — Registry snapshot, semantic diff, and replay modes

Status: completed locally on branch `codex/005-registry-evolution-replay`; hosted CI evidence remains pending until push.

Delivered:

- content-addressed `ainir.registry-snapshot.v1` artifacts with full-component/runtime-hash cross-binding;
- `ainir.registry-diff.v1` semantic classification as tightening, compatible, behavioral, relaxation, breaking, or unknown;
- `ainir.registry-migration-record.v1` source, target, exact-diff, reviewer, evidence, authorization, and self-hash binding;
- exact-snapshot, current-registry, and migrated-registry replay reports;
- stable receipt issuance with a portable RegistrySnapshot sidecar;
- explicit unsigned-local-review opt-in while cryptographic signatures remain unimplemented;
- full target-registry Trust Gate re-evaluation without rewriting historical receipts.

Acceptance evidence:

- final 238/238 tests pass with zero failures/errors/skips in non-overlapping JUnit groups;
- Phase 30 full returns `v1_0_rc_candidate_ready_for_private_github_trial`;
- distribution contract checks pass 11/11, including installed-wheel snapshot/diff/current/migrated replay;
- public demo, 71/71 negative cases, 10/10 golden traces, 81/81 built-in profile cases, safe lowering, and TypeScript strict compilation pass;
- policy relaxations, breaking changes, and unknown changes remain visible; unknown is never assumed compatible;
- migrated replay is refused without an approved record and explicit unsigned-local-review opt-in;
- all replay modes preserve the historical receipt bytes.

## P5 — Offline EvidenceProvider protocol and adapters

Status: completed locally on branch `codex/006-offline-evidence-providers`; hosted CI evidence remains pending until push.

Delivered:

- six stable request/record/policy/bundle/resolution/validation-report contracts;
- packaged schemas and deterministic self-hash validation;
- fixture, root-confined file, and local HMAC-signed bundle adapters;
- issuer, scope, subject, validity, bounded revocation freshness, reliability, unique bundle-record membership, policy, and host-key integrity revalidation;
- CLI, Phase 30, CI, and installed-wheel readiness checks;
- an explicit no-auto-promotion boundary: accepted candidates remain outside the Trust Gate Evidence Ledger.

Acceptance evidence:

- final 267/267 repository tests pass with zero failures/errors/skips;
- P5-focused tests pass 29/29 and readiness checks pass 9/9;
- Phase 30 full returns `v1_0_rc_candidate_ready_for_private_github_trial`;
- distribution contracts pass 12/12, including installed-wheel provider and CLI flows;
- public demo, 71/71 negative cases, 10/10 golden traces, and 81/81 built-in profile cases pass;
- HMAC remains explicitly non-production and exact key-ID policy binding is enforced;
- provider output cannot self-identify as trusted or silently mutate the Evidence Ledger.

## P6 — MCP tool-call conformance profile

Work:

- define a consumer-neutral normalized MCP tool-call claim profile;
- bind tool/server identity, arguments hash, resource scope, declared effects, required capabilities, user consent, and transaction/rollback requirements;
- add negative cases for description/effect mismatch, capability widening, consent mismatch, token audience drift, nested-argument effect laundering, and unknown tools/effects;
- optionally provide a host-owned reference adapter where AiNIR decides but never executes the tool;
- keep all MCP networking, authentication, and execution outside AiNIR core.

Acceptance:

- the profile runs through the existing Profile SDK and conformance runner;
- unknown or unregistered tool semantics remain refused or review-required;
- the adapter cannot widen effects/capabilities or bypass the Trust Gate;
- no MCP server/client runtime or credential handling is added to core.

## P7 — Maintainability and release hardening

Work:

- split `trust_receipt_store.py` and `verified_intent_export.py` behind behavior-preserving APIs;
- add architecture decision records for canonicalization, compatibility, profile governance, provider promotion, and migration;
- add automated dependency advisory checks and release provenance when the publishing path is selected;
- publish an RC only after an external reproduction of at least one receipt and one evidence-provider test vector.

## Work discipline

Each priority is implemented as small pull requests. A semantic PR must name touched invariants, include positive and adversarial coverage, state receipt/registry compatibility, and pass the complete test suite before focused wrappers.

The following remain out of scope throughout this plan: production execution, arbitrary-code verification, private archive publication, downstream AIVL/LEP implementation, live credentials in core, and claims of production readiness without independent evidence.
