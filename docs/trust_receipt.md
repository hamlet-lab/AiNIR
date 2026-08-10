# AiNIR TrustReceipt

A TrustReceipt is an audit-friendly summary of an AiNIR Trust Gate decision. It records the draft hash, registry snapshot hash, verifier report hash, trusted execution context, failed gates, and lowering eligibility.

The receipt is not a production attestation and is not an external consumer integration. It explains why a bounded, registry-backed semantic draft was passed, refused, or marked invalid.

## Stable receipt projection

TrustReceipt replay compares a stable projection of the receipt. The projection includes decision status, draft and registry hashes, verifier report hash, trusted context source and purpose, failed and warning gates, evidence summary, and lowering eligibility. Runtime timestamps and checkout-specific paths are excluded.

A stable receipt uses `ainir.trust-receipt.v1`; existing `pre_v1_phase18` receipts remain exactly replayable through the compatibility path.

## RegistrySnapshot sidecar

Stable receipt issuance also writes a deterministic `ainir.registry-snapshot.v1` sidecar. The sidecar contains portable copies of the public registry components and the compact runtime snapshot hash stored in the receipt. Full component data and compact component hashes are cross-validated so the sidecar cannot present different semantics under the same receipt binding.

## Replay

AiNIR supports three explicit modes:

- `exact_snapshot_replay`: reproduce the historical decision and bound registry exactly;
- `current_registry_replay`: retain the historical receipt and report a fresh decision under the active registry;
- `migrated_registry_replay`: validate a source snapshot, target snapshot, and explicit migration record, then run the full Trust Gate under the target registry.

No replay mode rewrites the historical receipt. See [`trust_receipt_registry_evolution.md`](trust_receipt_registry_evolution.md) for the artifact and approval model.

## Production boundary

Migration signatures and a production authorization service are not implemented in the public RC. Unsigned local approval therefore requires explicit opt-in and remains marked `production_runtime_ready: false`.
