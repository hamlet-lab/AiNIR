# v1.0 RC Candidate Patch 4 — Registry and Classifier Consistency

Patch 4 tightens several code-level consistency issues found after the v1.0 RC Candidate Patch 3 scope-boundary review.

This patch is not a feature expansion and does not change AiNIR's public-demo scope. It keeps the bounded workflow registry model, while making the registry/classifier/lowering surfaces more internally consistent.

## What changed

### Registry-driven family classification

`classify_effect()` and `classify_operation()` now derive families from registry-defined patterns instead of adding ad-hoc inline keyword fallbacks.

Matching is token-boundary based after compact normalization. This prevents false positives such as `debug` matching `db`.

### Raw token outbox false-positive reduced

The public safety registry no longer treats `outbox` as a raw-token persistence action. Outbox remains a transport/storage pattern; raw-token risk still requires raw/cleartext token terms with storage/log/persist/write-like actions.

### Lowering allowlist single source

The public TypeScript lowering type and return allowlists now live in `safety_registry.yaml`. Both `lowering_gate.py` and `lowering.py` read the same registry values.

### Trust Gate rule-prefix mapping

Trust Gate rule-to-gate mapping now extracts explicit alphabetic prefixes such as `TR`, `TX`, `S`, and `L`. It no longer relies on prefix-length sorting.

### VerifiedIntentPacket policy hash

`receipt_links.policy_hash` is now a distinct consumer-profile policy hash, not a duplicate of the safety registry hash. This keeps future policy/profile evolution separate from registry evolution.

### Demo expected status manifest

The public demo now reads expected example outcomes from `examples/demo_manifest.json` instead of inferring expected pass/block behavior from folder naming alone.

## What remains intentionally out of scope

- Enterprise workflow registry governance.
- External evidence provider adapters.
- Full canonical effect taxonomy management.
- Concurrent TrustReceipt manifest locking for server deployments.
- Production runtime integration.

Those items remain on the post-RC roadmap.
