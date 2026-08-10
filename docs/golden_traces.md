# Pre-v1 Phase 8 — Conformance Golden Traces

Phase 8 adds a deterministic replay harness for the public AiNIR demo pipeline.

The harness does not claim production runtime execution. It checks that fixed trace inputs produce fixed safety decisions through the public pipeline:

```text
Draft YAML
→ Strict Draft AST
→ Normalization
→ Verification
→ Lowering or refusal
→ Replay report
```

Golden traces include both safe and unsafe drafts. Unsafe traces pass only when the verifier blocks them and lowering is refused. The safe CreateUser outbox trace passes only when lowering emits host enforcement hooks such as `ctx.enforceModule` and `ctx.enforceOperation`.

Run:

```bash
PYTHONPATH=src python -m ainir conformance golden --out-dir /tmp/ainir_golden_traces
```

Outputs:

```text
/tmp/ainir_golden_traces/golden_trace_report.yaml
```

This phase turns the learned examples into a conformance contract: future changes must reproduce the same decisions before the public demo can be considered launch-ready.
