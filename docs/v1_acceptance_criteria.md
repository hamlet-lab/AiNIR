# v1.0 RC Acceptance Criteria

A build remains within the v1.0 RC candidate boundary only if all criteria below pass.

## Required checks

```bash
python -m pytest -q
python -m ainir demo --out-dir /tmp/ainir_demo_results
python -m ainir conformance negative --out-dir /tmp/ainir_negative_conformance
python -m ainir conformance golden --out-dir /tmp/ainir_golden_traces
python -m ainir profile validate ainir.public-demo.v1
python -m ainir conformance run ainir.public-demo.v1 --out-dir /tmp/ainir_profile_conformance
python -m ainir conformance intent-contract --out-dir /tmp/ainir_intent_contract
python scripts/check_offline_evidence_providers.py --out-dir /tmp/ainir_offline_evidence
python -m ainir conformance private-trial --out-dir /tmp/ainir_private_trial
python -m ainir conformance release-candidate --out-dir /tmp/ainir_rc_candidate
```

## Required safety behavior

- Empty drafts are invalid.
- Self-attested evidence cannot verify a claim.
- Extra effects are refused.
- Extra capabilities are refused.
- Unsupported workflow export is refused.
- Concrete downstream grounding is not invented by AiNIR.
- Blocked, invalid, stale, ambiguous, or hole-containing drafts do not lower.
- Transaction metadata with unknown fields is refused by the strict draft contract.
- Unresolved ambiguity is allowed to remain a non-executable verification state, but it cannot lower.
- TrustReceipt replay detects draft/context/registry/report mismatch.
- Additive profiles cannot replace packaged registry entries or nest registry contexts.
- Additive profiles can compose only reviewed exact effects/capabilities; taxonomy aliases, external allowlists, broad families, and capability prefixes are refused.
- Positive, negative, mutation, and replay declarations are non-vacuous and profile paths cannot escape the profile root.
- Offline provider output is independently rebound to exact provider, issuer, claim, subject, validity, bounded revocation freshness, reliability, bound-bundle record membership, and integrity policy.
- Signed evidence is recomputed with host-supplied keys; a provider's own signature or validation claim is not authoritative.
- Signed-bundle key IDs are policy-allowlisted and HMAC remains explicitly non-production.
- A validated provider candidate is not automatically inserted into the Trust Gate Evidence Ledger.

- Trust Gate `lowering_allowed` matches the public lowerer preflight for input type, output type, and return expression allowlists.
- Trust-looking claim statuses such as `evidence_checked` and `evidence_attached` are not accepted as self-attested substitutes for ledger-bound `verified` evidence.
- `executable: false` drafts can remain non-executable verification artifacts, but they cannot lower.
- TrustReceipt replay is tamper-evident for stable receipt fields including failed gates, warning gates, lowering eligibility, and trusted-context source/purpose.

## Required status language

The repository must continue to say:

- not v1.0 final;
- not production runtime;
- private GitHub trial before public release.
