# Pre-v1 Phase 19 — TrustReceipt Persistence and Replay

Phase 18 consolidated the AiNIR Trust Gate decision surface.
Phase 19 makes that decision reproducible by adding TrustReceipt persistence and
replay.

This is still AiNIR-only work. It does not add an external consumer integration.

## New surfaces

- `ainir trust-receipt-issue`
- `ainir trust-receipt-replay`
- `ainir phase19-trust-receipt-eval`
- `src/ainir/trust_receipt_store.py`
- `schemas/trust_receipt_replay_report.schema.json`

## Conformance expectations

The Phase 19 evaluation verifies:

1. A passing TrustReceipt replays successfully.
2. A refused TrustReceipt replays as the same refused decision.
3. A tampered receipt fails replay.
4. A receipt replayed against a modified draft fails.
5. A receipt replayed under a mismatched trusted context fails.

## Status

AiNIR remains pre-v1. This phase does not claim production runtime readiness,
external human review completion, or v1 final status.
