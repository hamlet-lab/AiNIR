# TrustReceipt registry evolution

A TrustReceipt records the runtime registry hash used by the Trust Gate. That historical binding is immutable: replay may evaluate the same draft under another registry, but it never rewrites the stored receipt or silently changes what the historical decision meant.

## Public artifact contracts

P4 defines three portable, content-bound artifacts:

- `ainir.registry-snapshot.v1` — the full canonical registry data, component hashes, profile identity, and the receipt-bound runtime registry hash;
- `ainir.registry-diff.v1` — a deterministic semantic comparison between two snapshots;
- `ainir.registry-migration-record.v1` — an explicit review record binding one exact source snapshot, target snapshot, and diff.

`ainir receipt issue` writes a RegistrySnapshot sidecar next to every new stable receipt. The sidecar runtime hash must equal the registry hash already bound into the receipt.

```bash
ainir receipt issue examples/create_user_outbox_safe/draft.yaml --out-dir /tmp/ainir-receipts --json
ainir registry snapshot --evolution --out /tmp/current-registry.json --json
ainir registry diff /tmp/source-registry.json /tmp/current-registry.json --json
```

The older `ainir registry snapshot` output remains available without `--evolution` for compatibility with the pre-P4 provenance view.

## Semantic diff classifications

Registry changes are classified conservatively as:

- `tightening` — the target narrows permissions or adds required safeguards;
- `compatible` — no semantic change, or metadata-only change with the same trust meaning;
- `behavioral` — behavior changes but is not safely reducible to tightening or relaxation;
- `relaxation` — the target removes or weakens a safeguard;
- `breaking` — an existing workflow, operation, evidence record, or required contract is removed or made incompatible;
- `unknown` — AiNIR cannot prove a safer classification.

`unknown` is never treated as compatible.

## Replay modes

### `exact_snapshot_replay`

Replays the historical receipt against the same draft, trusted context, verifier result, and receipt-bound registry hash. This preserves the pre-P4 exact replay behavior.

```bash
ainir receipt replay receipt.json --draft draft.yaml --mode exact_snapshot_replay --json
```

### `current_registry_replay`

Keeps the historical receipt unchanged, evaluates the draft against the currently active registry, and reports both statuses separately:

- `historical_status` — the status stored in the receipt;
- `evaluated_status` — the fresh status under the current registry;
- `decision_changed` — whether the stable decision projection changed;
- `registry_diff` — the semantic change report when a source snapshot is supplied.

```bash
ainir receipt replay receipt.json \
  --draft draft.yaml \
  --mode current_registry_replay \
  --source-snapshot source-registry.json \
  --json
```

A successful replay report means the replay procedure and bindings were valid. It does not mean `evaluated_status` is necessarily `passed`.

### `migrated_registry_replay`

Requires an exact source snapshot, exact target snapshot, and a migration record binding their deterministic diff. The target registry is fully rehydrated and the Trust Gate is run again; the migration record cannot convert a refused historical receipt into a passed receipt by declaration.

```bash
ainir registry migration create source.json target.json \
  --authorized-by reviewer-id \
  --reason "reviewed local registry transition" \
  --approve \
  --out migration.json

ainir receipt replay receipt.json \
  --draft draft.yaml \
  --mode migrated_registry_replay \
  --source-snapshot source.json \
  --target-snapshot target.json \
  --migration-record migration.json \
  --accept-unsigned-local-approval \
  --json
```

## Deliberate signature limitation

P4 records explicit local review metadata but does not implement cryptographic signing or organizational authorization. Every migration record therefore contains:

```text
cryptographic_signature_status: not_implemented
production_runtime_ready: false
```

An approved local migration is still refused by default. The caller must pass `--accept-unsigned-local-approval` to acknowledge that limitation for a bounded local replay. This option is not a production authorization mechanism.

## Invariants

- Historical receipt bytes are checked before and after replay and must remain unchanged.
- Snapshot component data must match its component hashes and receipt-bound runtime hash.
- A diff or migration record with a changed self-hash, snapshot binding, or change list is refused.
- Current and migrated replay keep historical and evaluated statuses separate.
- Registry evolution does not execute downstream actions and is not a production registry service.
