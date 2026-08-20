# Pre-v1 Phase 23 — Verified Intent Export Contract Hardening

Phase 23 keeps AiNIR independent and hardens the optional VerifiedIntentPacket export surface.

The export surface must not become a weaker path around the AiNIR Trust Gate. Exported packet fields are derived from:

- `TrustGateDecision`
- normalized AiNIR draft structure
- operation and safety registries
- evidence ledger bindings
- trusted execution context

The public demo AIVL consumer profile is a **future consumer profile slot**, not an integration. In this pre-v1 public profile, it supports only `PIIExportRequest`.

## New hardening rules

1. Unsupported workflows cannot export through the AIVL consumer profile.
2. Raw `intent`, `groundings`, and `field_classifications` from the draft are not passed through.
3. `ambiguity.status: resolved` requires an empty `unresolved_ambiguities` list.
4. PII export packets must explicitly declare a PII export boundary.
5. Consumer effect and capability namespaces are separated.
6. Allowed and denied consumer labels must not overlap.
7. Receipt hashes must use `sha256:<64 lowercase hex>` form.

## Command

```bash
python -m ainir phase23-verified-intent-hardening-eval --out-dir /tmp/ainir_phase23_verified_intent
```


## Phase 24 grounding boundary

In the current pre-v1 public profile, AiNIR does not emit concrete downstream schema groundings. `VerifiedIntentPacket.slots.groundings` is empty, and `grounding_status.status` is `consumer_must_ground`. Future consumers must verify source/filter/projection grounding themselves.
