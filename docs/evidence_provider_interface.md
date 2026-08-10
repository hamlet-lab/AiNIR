# Evidence Provider interface

The public AiNIR evidence ledger remains deterministic and bundled with the
demo. It demonstrates the rule:

> A model cannot verify its own evidence.

P5 adds a bounded offline provider interface so external candidate records can
be resolved and independently checked without being trusted or automatically
inserted into that ledger.

## Implemented public scope

The RC implements:

- `EvidenceRequest` with exact claim and draft binding;
- `EvidenceRecord` with issuer, provenance, validity, revocation, reliability,
  and self-hash fields;
- `EvidenceProviderPolicy` with explicit allowlists and minimum requirements;
- deterministic `EvidenceBundle`, `EvidenceResolution`, and
  `EvidenceValidationReport` artifacts;
- fixture, root-confined file, and HMAC-signed local bundle adapters;
- duplicate-key, size, depth, non-finite-value, path-escape, tamper, expiry,
  bounded revocation-freshness, exact bundle-record membership, and key-ID
  checks;
- host-key-based independent signature recomputation rather than trust in a
  provider's own validation or signature claim;
- a fail-closed guarantee that successful provider validation produces only a
  `validated_candidate`, never automatic Trust Gate promotion.

See [`offline_evidence_providers.md`](offline_evidence_providers.md) for the
contract, CLI, and security model.

## What remains bundled

The existing Trust Gate still accepts `verified` claims only when they bind to
known records in the active AiNIR Evidence Ledger. Fields such as
`checked: true`, `source: model`, or `evidence_checked` remain self-attestation
and do not become facts.

## Future production path

A production deployment would need separately governed provider adapters for
sources such as:

- host policy-engine decisions;
- human approval records;
- audit or event logs;
- authorization tickets;
- test or verifier reports;
- runtime observations.

It would also need public-key issuer identity, key rotation, revocation,
organizational authorization, secure transport, durable storage, ledger
promotion policy, and audit/replay governance. None of those is implied by the
P5 HMAC example.

## Boundary

The public repo does not implement a live evidence provider network. It does
not perform network I/O, store credentials, or authorize execution. The P5
adapters exist to make the evidence boundary testable and extensible while
keeping provider output untrusted by default.
