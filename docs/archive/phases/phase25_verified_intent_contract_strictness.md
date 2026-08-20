# Pre-v1 Phase 25 — VerifiedIntentPacket Contract Strictness and Registry Consistency

Phase 25 tightens the optional `VerifiedIntentPacket` export surface so its runtime validator, JSON Schema, and consumer-profile registry express the same contract.

This is still an AiNIR-owned future-consumer export surface. It does not integrate any external compiler/runtime.

## Hardening rules

- Unknown top-level or nested packet fields are invalid.
- `AIVLConsumerProfile` is still limited to `PIIExportRequest` in this public pre-v1 profile.
- `PIIExportRequest` packets require ledger-bound authorization evidence.
- `PIIExportRequest` packets require `PIIExport` in both consumer effects and capabilities.
- `required_contracts` must include exactly the public profile's required contract set.
- `operation_constraints.allowed_operations` must stay within the profile allowlist.
- `operation_constraints.denied_operations` must be non-empty and match the profile denied set.
- `operation_constraints.requires_human_review` must be true.
- `canonical_operations` must be non-empty.
- Concrete data-schema grounding remains a consumer obligation.
- Root and package registry copies must remain byte-identical.

## Command

```bash
python -m ainir phase25-verified-intent-contract-eval \
  --out-dir /tmp/ainir_phase25_verified_intent_contract
```

This phase is a contract hardening step, not a downstream integration step.
