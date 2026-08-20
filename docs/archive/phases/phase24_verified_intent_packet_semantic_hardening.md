# Pre-v1 Phase 24 — VerifiedIntentPacket Semantic Grounding and Validator Hardening

Phase 24 tightens the optional `VerifiedIntentPacket` export surface.

The key rule is:

> A VerifiedIntentPacket must not claim semantic detail that the AiNIR Trust Gate did not verify.

In this public demo, AiNIR does **not** perform downstream data-schema grounding. Therefore:

- `groundings` is empty.
- `grounding_status.status` is `consumer_must_ground`.
- future consumers must run their own schema/filter/projection grounding checks.
- PII export packets must include ledger-bound authorization evidence.
- PII export packets must explicitly include the `PIIExport` effect and capability boundary.
- operations and semantic roles are separated in `operation_constraints`.
- packet validation rejects contradictory, under-specified, or over-claiming packets.

This is not an external integration. It is an AiNIR-owned export contract surface for future consumers.
