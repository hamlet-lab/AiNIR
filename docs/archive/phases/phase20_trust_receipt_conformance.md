# Pre-v1 Phase 20 — TrustReceipt Conformance Integration

Phase 19 made TrustReceipt issue/replay possible. Phase 20 makes that replay part of AiNIR's ordinary conformance surface.

A golden trace now passes only when the expected verification decision is reproduced, lowering is either emitted or refused as expected, and the generated TrustReceipt replays to the same decision under the same trusted context.

This phase is still pre-v1. It is not a production signature system and it is not an external integration layer.

## Commands

```bash
python -m ainir golden-trace-eval --out-dir /tmp/ainir_golden_traces
python -m ainir phase20-receipt-conformance-eval --out-dir /tmp/ainir_phase20_receipt_conformance
```

## Invariant

```text
Golden trace pass
  implies verify/lower/refuse conformance
  and TrustReceipt replay conformance.
```

If a future code change makes a draft pass or refuse differently, changes the safety registry hash, or changes trusted execution context binding, replay fails.
