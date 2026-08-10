# Changelog

All notable public changes will be recorded here. AiNIR remains a bounded release candidate, not a v1.0 final release or production runtime.

## Unreleased

### Added

- fixed-semantics read-only external MCP profile scaffold with file-bound, root-confined fixtures;
- generic bundled-or-external MCP conformance runner while keeping internal scenario shortcuts private to the bundled profile;
- stable OpenAI function-call binding and function-tool preflight contracts with packaged schemas;
- host-owned adapter for completed Responses function-call JSON with exact reviewed schema binding and no SDK/API/execution surface;
- cross-artifact substitution checks binding OpenAI source identity, MCP envelope, host context, and assessment;
- deterministic P7 readiness, CLI examples, Phase 30, and installed-wheel coverage;
- full Python test-suite gate in GitHub Actions before the Phase 30 quick-integrity check;
- robust CI static recognition of locked editable installs;
- public scope, protected invariants, security reporting, support, maintainer, agent, and pull-request guidance;
- reproducible baseline report for the 2026-08-09 uploaded source snapshot;
- single-source Python release identity for `1.0.0rc2`;
- packaged public schema resources and supported `ainir.resources` accessors;
- deterministic public-resource manifests with SHA-256 metadata;
- wheel/sdist build, clean-wheel install, Trust Gate, and TrustReceipt replay contract checks;
- Python 3.10–3.13 compatibility and Windows/macOS distribution smoke workflows;
- phase-independent `trust`, `receipt`, `profile`, `conformance`, and `registry` CLI groups;
- stable Trust Gate decision, TrustReceipt, replay-report, profile-manifest, conformance-pack, and conformance-report identifiers;
- supported canonical JSON, artifact validation, stable/legacy receipt conversion, and receipt verification APIs;
- hidden one-RC compatibility routing for historical flat and phase-tagged commands;
- read-only bundled profile and registry inspection commands.
- Profile Manifest v1, Conformance Pack v1, and Conformance Report v1 schemas and runtime contracts;
- bundled `ainir.public-demo.v1` workflow profile over the existing public registries and corpora;
- additive `profile init`, `validate`, `inspect`, and workflow-profile listing commands;
- context-local profile registry compilation with protected-base collision refusal;
- standalone `conformance run` with console, JSON, JSONL, JUnit, and YAML output;
- portable RegistrySnapshot v1 artifacts cross-bound to receipt runtime hashes and emitted as receipt sidecars;
- conservative RegistryDiff v1 classification as `tightening`, `compatible`, `behavioral`, `relaxation`, `breaking`, or `unknown`;
- explicit RegistryMigrationRecord v1 artifacts binding source, target, diff, reviewer, evidence, and self-hash;
- exact, current-registry, and migrated TrustReceipt replay modes that preserve historical receipt bytes and report historical/evaluated statuses separately;
- fail-closed unsigned migration handling with an explicit bounded local opt-in and `production_runtime_ready: false`;
- installed-wheel and cross-platform distribution checks for registry evolution and replay modes;
- six stable offline EvidenceProvider artifact contracts and packaged JSON Schemas;
- fixture, root-confined file, and local HMAC-signed bundle provider adapters;
- host-key-based independent signature recomputation, exact bundle-record
  binding, and policy-bounded revocation freshness;
- independent issuer, claim, subject, validity, revocation, reliability, policy, and integrity validation;
- `evidence bundle`, `evidence policy`, and `evidence resolve` CLI commands;
- installed-wheel and Phase 30 readiness checks that keep provider candidates out of the Trust Gate ledger.
- six MCP tool-call preflight contracts and packaged JSON Schemas;
- bundled `ainir.mcp.reference.workspace.v1` profile with exact descriptor/schema/effect/capability bindings;
- non-executing host-owned MCP reference adapter and `mcp profile`, `normalize`, `assess`, and `conformance` CLI commands;
- 26-case deterministic MCP conformance pack covering authorization audience, consent, capabilities, resource paths, credentials, transactions, rollback, annotations, Tasks, and multi-round input refusal;
- Phase 30 and installed-wheel verification preserving the P5 registry hash and no-execution boundary.
- six stable MCP tool-call preflight artifact contracts and packaged schemas;
- consumer-neutral reviewed workspace-tool profile with a host-owned, non-executing adapter;
- exact descriptor/schema/effect/capability, audience, resource, consent, transaction, and rollback bindings;
- destructive-call `review_required` ceiling and explicit refusal of MCP Task/multi-round input in P6;
- 26-case deterministic MCP conformance pack plus CLI, Phase 30, and installed-wheel checks.

### Fixed

- P7 host-source artifacts now enforce the public canonical JSON byte and depth bounds before normalization;
- external MCP conformance no longer masks unexpected programming exceptions as an expected `invalid` case;
- Phase 26 CI scanning no longer rejects a valid constrained pip install because of option ordering;
- README expected output now matches the current payment-refusal finding count;
- wheel metadata no longer reports the unrelated `0.1.0` version;
- public schemas are no longer omitted from built distributions;
- private npm metadata is clearly separated from the Python release identity;
- current documentation and private-trial commands no longer require historical phase names;
- stable and legacy receipts both preserve exact replay and receipt identity;
- the installed-wheel profile/conformance distribution check no longer collides with its own `passed` argument;
- packaging metadata now uses an SPDX license expression and explicit license files without the deprecated license table.

### Known follow-up work

- add cryptographic registry-migration authorization and externally reviewed governance;
- add public-key evidence issuer identity and a separately reviewed ledger-promotion/governance contract.
- externally review the bounded MCP profile and add separately governed profiles without introducing an execution runtime.
- add externally reviewed MCP server identity/provenance, complete schema evaluation, and production host authorization adapters without moving execution into AiNIR core.
