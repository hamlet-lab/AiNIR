# TrustReceipt Persistence and Replay

AiNIR Trust Gate decisions are not meant to be ephemeral console output.
AiNIR exposes a stable persistence and exact-replay surface for TrustReceipt artifacts.

A persisted TrustReceipt records stable hashes for:

- the canonicalized draft payload
- the safety registry
- the verifier report
- the trusted execution context, including source and purpose
- the Trust Gate status
- failed and warning gate summaries
- lowering eligibility status and stable findings

Replay recomputes the Trust Gate decision against the current draft and current
registry. A receipt is accepted only if the stable fields reproduce.

## Commands

Issue a receipt:

```bash
python -m ainir receipt issue examples/create_user_outbox_safe/draft.yaml \
  --out-dir /tmp/ainir_trust_receipts
```

Replay it:

```bash
python -m ainir receipt replay /tmp/ainir_trust_receipts/<receipt>.receipt.json
```

Run the receipt conformance check:

```bash
python -m ainir conformance receipt --out-dir /tmp/ainir_phase19_receipt_eval
```

## Important limits

A TrustReceipt is not a production signature and not a substitute for external
review. It is a deterministic RC replay artifact. If the draft, registry, verifier report, trusted context, failed gate summary, warning gate summary, or lowering eligibility projection changes, replay must fail.
