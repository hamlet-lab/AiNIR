# P5 — Offline EvidenceProvider contracts and adapters

Status: implemented and validated locally on `codex/006-offline-evidence-providers`.

## Delivered

- six stable public contracts:
  - `ainir.evidence-request.v1`;
  - `ainir.evidence-record.v1`;
  - `ainir.evidence-provider-policy.v1`;
  - `ainir.evidence-bundle.v1`;
  - `ainir.evidence-resolution.v1`;
  - `ainir.evidence-validation-report.v1`;
- packaged Draft 2020-12 JSON Schemas for all six artifacts;
- deterministic canonical JSON and self-hash binding for records, bundles,
  resolutions, policies, requests, and validation reports;
- `FixtureEvidenceProvider` for in-memory conformance fixtures;
- `FileEvidenceProvider` with optional root confinement and defensive JSON/YAML
  loading;
- `SignedBundleEvidenceProvider` with exact HMAC key-ID policy binding for local
  integrity review;
- public `evidence bundle`, `evidence policy`, and `evidence resolve` CLI
  commands;
- a deterministic public example under `examples/offline_evidence_provider/`;
- a nine-check readiness harness integrated into Phase 30, CI, and installed-
  wheel distribution verification.

## Trust boundary

P5 deliberately separates provider resolution from semantic acceptance:

```text
EvidenceRequest
  -> provider returns EvidenceResolution
  -> AiNIR independently validates candidate + policy + bundle
  -> EvidenceValidationReport
```

Provider output is untrusted input. AiNIR rechecks:

- provider ID, version, source kind, and bundle identity;
- independent signature and bundle recomputation using host-supplied key
  material;
- exact signature key ID when signatures are required;
- exact equality with the unique matching record in the bound bundle;
- issuer ID and issuer kind;
- evidence kind, producer kind, and policy version;
- module ID, workflow, claim ID, and claim statement hash;
- raw/canonical draft binding;
- host-supplied evaluation time, validity window, and expiry;
- active revocation state, non-future revocation check time, and a bounded
  policy-controlled freshness window;
- reliability threshold;
- record, bundle, resolution, policy, request, and report self-hashes;
- unknown fields, duplicate IDs, path escape, file size/depth, and non-finite
  values.

A successful result is only:

```text
candidate_evidence_status: validated_candidate
trust_gate_promotion_allowed: false
production_runtime_ready: false
```

The adapter never mutates the bundled Evidence Ledger. Ordinary Trust Gate
verification continues to refuse an external evidence ID until a separately
reviewed ledger-ingestion and governance contract exists.

## Signed-bundle boundary

The signed adapter uses HMAC-SHA256 solely as a deterministic local integrity
example. It does not provide public-key issuer identity, certificate chains,
organizational authorization, key rotation, online revocation, or
non-repudiation. Signed bundles require both a verified signature and an exact
policy-allowlisted key ID.

## Validation evidence

- repository tests: 267/267 passed in non-overlapping JUnit groups;
- failures, errors, and skips: 0;
- P5-focused tests: 29/29 passed;
- offline provider readiness: 9/9 passed;
- public demo: passed;
- negative conformance corpus: 71/71 passed;
- golden traces: 10/10 passed;
- bundled public profile: 81/81 passed;
- Phase 30 quick and full: passed;
- Phase 30 decision: `v1_0_rc_candidate_ready_for_private_github_trial`;
- wheel/sdist distribution contracts: 12/12 passed;
- installed-wheel fixture/file/signed-bundle readiness: passed;
- installed-wheel `evidence bundle`, `policy`, and `resolve`: passed;
- preserved receipt-bound registry hash:
  `sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a`;
- artifact-contract manifest entries: 15;
- network access used by P5 readiness path: false.

These checks are reproducibility and defensive-integrity evidence, not an
independent security certification or a claim that no vulnerabilities exist.

## Environment limitations

The local runtime is Linux with Python 3.13. Python 3.10–3.13 and
Windows/macOS workflows are defined; hosted-runner evidence remains pending
until the branch is pushed.

The shared environment may contain unrelated global dependency conflicts.
AiNIR's wheel is installed into a separate target with `--no-deps --no-index`
for distribution checks, and the installed runtime/resource/provider checks
pass there.

The local HMAC key used by the readiness harness is deterministic public fixture
material, not a credential.

## Next bounded development target

P6 should add a consumer-neutral MCP tool-call conformance profile and optional
host-owned reference adapter. It must normalize proposed tool calls into AiNIR
claims, effects, capabilities, consent, resource scope, and transaction
requirements without adding an MCP runtime or tool execution to AiNIR core.
