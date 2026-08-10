# Offline EvidenceProvider contracts

AiNIR P5 adds a deterministic, offline provider boundary for receiving candidate
evidence without trusting the provider's own claims.

> Provider output is untrusted input until AiNIR independently validates it.

This feature is part of the bounded public RC. It is not a networked evidence
service, a production issuer-identity system, or an automatic path into the
Trust Gate Evidence Ledger.

## Artifact flow

```text
EvidenceRequest
  -> EvidenceProvider.resolve(...)
  -> EvidenceResolution (untrusted candidate)
  -> AiNIR policy + semantic + integrity validation
  -> EvidenceValidationReport
```

A successful report has:

```text
overall_status: passed
accepted: true
candidate_evidence_status: validated_candidate
trust_gate_promotion_allowed: false
production_runtime_ready: false
```

`validated_candidate` means only that the candidate satisfied the bound offline
provider policy. P5 does not mutate the bundled Evidence Ledger and does not
turn the candidate into execution authorization.

## Public contracts

| Artifact | Contract |
|---|---|
| Evidence request | `ainir.evidence-request.v1` |
| Evidence record | `ainir.evidence-record.v1` |
| Provider policy | `ainir.evidence-provider-policy.v1` |
| Evidence bundle | `ainir.evidence-bundle.v1` |
| Provider resolution | `ainir.evidence-resolution.v1` |
| Validation report | `ainir.evidence-validation-report.v1` |

JSON Schemas for all six artifacts are packaged through `ainir.resources`.
Cross-field semantic rules are also enforced by the Python validators; schema
validation alone is not treated as sufficient.

## Offline provider adapters

### FixtureEvidenceProvider

An in-memory deterministic adapter for tests and conformance fixtures. It cannot
claim to be a live or production evidence source.

### FileEvidenceProvider

Loads an unsigned JSON or YAML bundle from a local file. Callers may bind it to
an `allowed_root`; paths outside that root are refused. Duplicate JSON/YAML
keys, oversized files, excessive nesting, and non-finite values are refused.

### SignedBundleEvidenceProvider

Loads a local HMAC-SHA256 bundle and verifies it against an exact `key_id` from
the provider policy. Trusted verification key material must be supplied by the
host separately during validation; keys or signature claims supplied by an
arbitrary provider are not authoritative. This is a deterministic offline
integrity example only. HMAC does not provide public-key issuer identity,
organizational authorization, key revocation, or production-grade
non-repudiation.

## Independent checks

AiNIR revalidates at least the following before accepting a candidate:

- provider ID, provider version, and source kind;
- independent bundle and signature recomputation using host-supplied keys;
- exact signature key ID when a signature is required;
- exact equality between the resolution record and the unique matching record
  in the bound bundle;
- issuer ID and issuer kind;
- evidence kind and producer kind;
- policy version;
- module ID, workflow, claim ID, and claim statement hash;
- raw or canonical draft binding;
- validity window and host-supplied evaluation time;
- active revocation state, a non-future `checked_at` value, and a policy-bound
  maximum revocation-check age (`max_revocation_age_seconds`);
- reliability threshold;
- record self-hash, bundle hash, resolution hash, and report hash;
- unknown fields and duplicate IDs;
- the invariant that provider output cannot self-promote into the Trust Gate.

Unknown source kinds such as `network` are not accepted by the P5 public
policy validator.

## CLI example

The repository includes a deterministic fixture:

```bash
python -m ainir evidence bundle examples/offline_evidence_provider/bundle.json --json
python -m ainir evidence policy examples/offline_evidence_provider/policy.json --json
python -m ainir evidence resolve \
  examples/offline_evidence_provider/bundle.json \
  examples/offline_evidence_provider/policy.json \
  examples/create_user_outbox_safe/draft.yaml \
  --claim-id claim.create_user_uses_outbox \
  --evidence-id evidence.ainir.fixture.safe-outbox \
  --expected-kind verifier_report \
  --evaluation-time 2026-08-10T00:00:00Z \
  --out-dir /tmp/ainir_evidence_example \
  --json
```

Run the complete deterministic readiness check with:

```bash
python scripts/check_offline_evidence_providers.py --json
```

The readiness check covers fixture, root-confined file, and signed-bundle
providers plus provider self-attestation, inner-record tampering, bundle-to-
resolution record substitution, expiry, stale revocation checks, and the
no-auto-promotion boundary. It performs no network access.

## Python API

```python
from ainir.evidence_provider import (
    FixtureEvidenceProvider,
    build_evidence_provider_policy,
    build_evidence_request_from_draft,
    resolve_and_validate_evidence,
)
```

The full constructors and validators are documented by their typed function
signatures. Consumers should persist the generated request, resolution, and
validation report together when they need an auditable local trail.

## Non-goals

P5 does not provide:

- network provider discovery or retries;
- OAuth, secret storage, or token forwarding;
- enterprise issuer directories;
- public-key signatures or certificate chains;
- online revocation services;
- automatic Evidence Ledger mutation;
- Trust Gate bypass or execution authorization;
- production runtime readiness.

A future promotion path would require a separately reviewed ledger-ingestion
contract, host authorization, governance, replay behavior, and negative
conformance coverage. It must not be inferred from `accepted: true` in a P5
validation report.
