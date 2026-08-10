# Offline EvidenceProvider example

This fixture demonstrates P5's deterministic offline evidence boundary. The
provider returns a candidate record, then AiNIR independently checks issuer,
claim scope, draft binding, validity, revocation, reliability, provider policy,
and artifact integrity.

The candidate is **not** inserted into the Trust Gate Evidence Ledger and does
not authorize execution.

Run from the repository root:

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

Expected result:

- `accepted: true`
- `candidate_evidence_status: validated_candidate`
- `trust_gate_promotion_allowed: false`
- `production_runtime_ready: false`
