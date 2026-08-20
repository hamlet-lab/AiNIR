# Pre-v1 Phase 15 — Capability Least-Privilege and Host Enforcement Contract

Phase 15 tightens two boundaries that remained after operation/effect contracts were stabilized.

## Capability least-privilege

Operation specs now define the capabilities they may use. A draft is refused when an operation declares a capability outside its spec, even if the operation has no effects.

This prevents a model-generated draft from attaching broad capabilities to otherwise harmless operations.

Rules introduced:

- `O012.operation_declares_unallowed_capability`
- default `allow_extra_capabilities: false`
- pure operations default to no allowed capabilities

## Host enforcement contract

Lowered TypeScript skeletons now call host operations through an operation envelope rather than through the local draft operation id.

The generated skeleton requires these host hooks:

- `ctx.enforceOperation(envelope, state)`
- `ctx.callOperation(envelope, state)`
- `ctx.enforceTransaction(transactionEnvelope, state)` for transaction-bound drafts
- `ctx.runTransaction(transactionEnvelope, state, body)` for transaction-bound drafts

If the hooks are missing, the skeleton returns `host_enforcement_contract_required` instead of silently executing the body.

## Status

Phase 15 is still pre-v1 hardening. It does not make AiNIR a production runtime or a v1.0 final release.
