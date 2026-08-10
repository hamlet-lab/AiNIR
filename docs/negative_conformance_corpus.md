# Negative Conformance Corpus and Deterministic Robustness Harness

AiNIR's public demo treats provider/model output as untrusted draft evidence.
Phase 7 turns previously discovered regression misses into a fixed negative conformance corpus plus a small deterministic robustness harness.

Run:

```bash
PYTHONPATH=src python -m ainir conformance negative --out-dir /tmp/ainir_negative_conformance
```

The harness checks three things:

1. unsafe drafts are `blocked` or `invalid`;
2. unsafe drafts cannot be lowered;
3. the safe CreateUser outbox positive control still passes and lowers.

The corpus is intentionally public-demo scoped. It is not a proof that AiNIR is secure for production; it is a guardrail against known verifier regressions.
