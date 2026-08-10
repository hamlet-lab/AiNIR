# Stable artifact contracts and legacy replay

AiNIR RC2 uses phase-independent public identifiers while retaining exact replay for existing pre-v1 artifacts.

| Artifact | Stable identifier | Legacy identifier |
|---|---|---|
| Trust Gate decision | `ainir.trust-gate-decision.v1` | `pre_v1_phase18` |
| TrustReceipt | `ainir.trust-receipt.v1` | `pre_v1_phase18` |
| TrustReceipt replay report | `ainir.trust-receipt-replay-report.v1` | legacy report had no explicit kind/version |
| Profile manifest | `ainir.profile-manifest.v1` | none |
| Conformance pack | `ainir.conformance-pack.v1` | none |
| Conformance report | `ainir.conformance-report.v1` | none |
| Registry snapshot | `ainir.registry-snapshot.v1` | legacy provenance view remains CLI-compatible |
| Registry diff | `ainir.registry-diff.v1` | none |
| Registry migration record | `ainir.registry-migration-record.v1` | none |
| Evidence request | `ainir.evidence-request.v1` | none |
| Evidence record | `ainir.evidence-record.v1` | none |
| Evidence provider policy | `ainir.evidence-provider-policy.v1` | none |
| Evidence bundle | `ainir.evidence-bundle.v1` | none |
| Evidence resolution | `ainir.evidence-resolution.v1` | none |
| Evidence validation report | `ainir.evidence-validation-report.v1` | none |
| MCP tool-call profile | `ainir.mcp-tool-call-profile.v1` | none |
| MCP tool-call envelope | `ainir.mcp-tool-call-envelope.v1` | none |
| MCP host context | `ainir.mcp-host-context.v1` | none |
| MCP tool-call assessment | `ainir.mcp-tool-call-assessment.v1` | none |
| MCP conformance pack | `ainir.mcp-tool-call-conformance-pack.v1` | none |
| MCP conformance report | `ainir.mcp-tool-call-conformance-report.v1` | none |
| OpenAI function-call binding | `ainir.openai-function-call-binding.v1` | none |
| OpenAI function-tool preflight | `ainir.openai-function-tool-preflight.v1` | none |

The identifiers are exported from `ainir.contracts` and the package root. `ainir contracts --json` returns the same registry in machine-readable form.

## Receipt compatibility model

New user-facing commands serialize stable decision and receipt contracts. Deprecated commands continue to serialize the legacy representation for one RC cycle. Both forms preserve the same semantic decision and receipt identity.

A stable receipt records:

```json
{
  "receipt_kind": "AiNIRTrustReceipt",
  "version": "ainir.trust-receipt.v1",
  "legacy_version": "pre_v1_phase18"
}
```

The stable projection binds the stable version and its legacy serializer marker. A legacy receipt retains the exact historical projection shape, so old stored hashes are not silently reinterpreted.

## Registry evolution model

A new stable receipt is accompanied by a RegistrySnapshot sidecar whose `runtime_registry_snapshot_hash` must equal the hash already bound into the receipt. RegistryDiff and RegistryMigrationRecord artifacts bind exact snapshot self-hashes; changes cannot be substituted without invalidating the artifact.

Replay reports always keep these concepts separate:

- the immutable historical receipt and `historical_status`;
- the newly evaluated decision and `evaluated_status`;
- the semantic registry diff, when available;
- local migration-review metadata, when applicable.

An approved migration record is not a cryptographic signature. P4 marks signature support and production runtime readiness as false and requires an explicit local opt-in before unsigned migrated replay.

## Offline evidence model

A provider resolution is not trusted merely because its schema or self-hash is valid. AiNIR binds it to an exact request and policy, then independently checks provider identity, issuer, claim scope, draft binding, validity, revocation, reliability, and integrity. A successful result is only a `validated_candidate`; P5 fixes `trust_gate_promotion_allowed` and `production_runtime_ready` to false.

The HMAC signed-bundle adapter demonstrates local integrity, not public-key issuer identity or organizational authorization.

## Supported Python modules

- `ainir.contracts`: identifiers and contract manifest;
- `ainir.canonical`: canonical JSON, SHA-256 helpers, and defensive JSON-object loading;
- `ainir.contract_validation`: runtime cross-field checks that complement the packaged schemas;
- `ainir.profile_manifest`: path-aware manifest and conformance-pack validation;
- `ainir.profile_runtime`: isolated additive registry compilation with protected collision refusal;
- `ainir.conformance_runner`: deterministic profile conformance reports;
- `ainir.registry_evolution`: snapshot capture, validation, semantic diff, and migration-record APIs;
- `ainir.registry_replay`: exact/current/migrated replay orchestration;
- `ainir.evidence_provider`: offline provider artifact construction, bounded adapters, and independent validation;
- `ainir.mcp_tool_call`: descriptor/profile binding, deterministic envelopes, host contexts, and assessments;
- `ainir.mcp_host_adapter`: non-executing host-owned reference adapter;
- `ainir.mcp_conformance`: bundled and file-bound deterministic MCP preflight conformance;
- `ainir.mcp_authoring`: fixed-semantics external MCP profile scaffold;
- `ainir.openai_function_tool_adapter`: completed function-call binding and non-executing P6 preflight;
- `ainir.trust_receipt_store.convert_trust_receipt_contract`: explicit stable/legacy conversion;
- `ainir.trust_receipt_store.verify_trust_receipt_artifact`: structural and self-hash verification.

Private underscore-prefixed hash helpers remain as compatibility aliases for one RC but are no longer used by the public CLI.

## What does not change

Contract versioning, registry evolution, and offline provider validation do not make AiNIR a production runtime, do not make arbitrary code verifiable, do not provide cryptographic organizational authorization, and do not allow consumer profiles, migration records, or provider candidates to weaken or bypass the Trust Gate. MCP preflight artifacts likewise do not authorize or execute a tool; descriptions and annotations remain untrusted, and all final host controls remain outside AiNIR core.
