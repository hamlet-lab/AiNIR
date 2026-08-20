# Pre-v1 Phase 22 — Verified Intent Export Surface and AIVL Consumer Profile

Phase 22 adds an AiNIR-owned external consumer profile slot.

This is **not** an integration with AIVL and not a downstream compiler adapter.
It is a small contract surface inside AiNIR: after a draft passes the AiNIR
Trust Gate, AiNIR may export a `VerifiedIntentPacket` for a future consumer.

The first consumer profile is `AIVLConsumerProfile`, because AiNIR and AIVL are
expected to interoperate later. AIVL is not part of AiNIR's core name and is not
required by the public demo.

## Position in the AiNIR roadmap

```text
Draft
→ Strict Draft AST
→ Safety Registry
→ Evidence Ledger
→ Operation Spec Registry
→ Trusted Execution Context
→ Transaction Binding
→ AiNIR Trust Gate
→ TrustReceipt
→ optional VerifiedIntentPacket export
```

The export surface is downstream of Trust Gate and TrustReceipt. It does not
replace verifier, receipt replay, lowering gate, or negative conformance.

## Required AIVL Consumer Profile slots

1. Trust Status Slot
2. Evidence Binding Slot
3. Capability / Effect Slot
4. Intent Slot
5. Grounding Slot
6. Ambiguity Slot
7. Operation Constraint Slot
8. Contract Requirement Slot
9. Security Classification Slot
10. Receipt Slot

## Core rule

```text
trust.status != verified
or trust.decision != allow
→ no verified intent export
```

A downstream consumer should still re-check its own program-level constraints.
AiNIR pass means “the semantic intent is eligible for handoff,” not “execution is
complete.”

## Commands

```bash
python -m ainir verified-intent-export fixtures/aivl_consumer_profile/pii_export_allowed/draft.yaml --profile AIVL --json --out-dir /tmp/ainir_verified_intent
python -m ainir phase22-verified-intent-eval --out-dir /tmp/ainir_phase22_export
```


## Phase 24 grounding boundary

In the current pre-v1 public profile, AiNIR does not emit concrete downstream schema groundings. `VerifiedIntentPacket.slots.groundings` is empty, and `grounding_status.status` is `consumer_must_ground`. Future consumers must verify source/filter/projection grounding themselves.
