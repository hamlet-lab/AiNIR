# v1.0 RC API surface

This is the public-facing API surface frozen for v1.0 RC review.

## Release identity

- Python distribution: `ainir-public-demo`
- Runtime version: `ainir.__version__`
- Release tag: `ainir.__release_tag__`
- Current candidate: Python `1.0.0rc2`, tag `v1.0.0-rc.2`

Python package metadata derives from `src/ainir/_version.py`. The private npm package is only a TypeScript compile fixture and is not a release identity.

## Stable CLI surface

- `ainir verify`
- `ainir trust evaluate`
- `ainir receipt issue`
- `ainir receipt verify`
- `ainir receipt replay`
- `ainir profile list`
- `ainir profile show`
- `ainir profile init`
- `ainir profile validate`
- `ainir profile inspect`
- `ainir profile export-intent`
- `ainir conformance negative`
- `ainir conformance golden`
- `ainir conformance run`
- `ainir conformance trust-gate`
- `ainir conformance receipt`
- `ainir conformance receipt-integration`
- `ainir conformance release-readiness`
- `ainir conformance intent-export`
- `ainir conformance intent-hardening`
- `ainir conformance intent-semantics`
- `ainir conformance intent-contract`
- `ainir conformance private-trial`
- `ainir conformance release-candidate`
- `ainir evidence bundle`
- `ainir evidence policy`
- `ainir evidence resolve`
- `ainir mcp profile`
- `ainir mcp normalize`
- `ainir mcp assess`
- `ainir mcp conformance`
- `ainir registry list`
- `ainir registry show`
- `ainir registry snapshot`
- `ainir registry diff`
- `ainir registry migration create`
- `ainir registry migration validate`
- `ainir contracts`
- `ainir lower`
- `ainir demo`

Historical flat and phase-tagged commands are hidden from help but accepted for one RC transition. Legacy receipt replay remains exact-only. See [`legacy_cli_compatibility.md`](legacy_cli_compatibility.md).

## Stable Python contract surface

- `ainir.contracts`
- `ainir.canonical`
- `ainir.contract_validation`
- `ainir.profiles` read-only bundled profile access
- `ainir.profile_manifest` workflow-profile loading, authoring, validation, and inspection
- `ainir.profile_runtime` isolated additive registry compilation
- `ainir.conformance_runner` profile conformance execution and report rendering
- `ainir.registry_evolution` snapshot, diff, migration, validation, and serialization APIs
- `ainir.registry_replay` exact/current/migrated replay APIs
- `ainir.evidence_provider` deterministic offline provider and independent validation APIs
- `ainir.mcp_tool_call` deterministic MCP descriptor/envelope/context/assessment APIs
- `ainir.mcp_host_adapter` host-owned non-executing reference adapter
- `ainir.mcp_conformance` deterministic MCP preflight conformance
- `TrustGateDecision.as_public_dict()`
- `convert_trust_receipt_contract()`
- `verify_trust_receipt_artifact()`
- `ReceiptReplayReport.as_public_dict()` for the legacy exact implementation
- `RegistryReplayReport.as_dict()` for the public replay-mode report

Stable identifiers:

- `ainir.trust-gate-decision.v1`
- `ainir.trust-receipt.v1`
- `ainir.trust-receipt-replay-report.v1`
- `ainir.profile-manifest.v1`
- `ainir.conformance-pack.v1`
- `ainir.conformance-report.v1`
- `ainir.registry-snapshot.v1`
- `ainir.registry-diff.v1`
- `ainir.registry-migration-record.v1`
- `ainir.evidence-request.v1`
- `ainir.evidence-record.v1`
- `ainir.evidence-provider-policy.v1`
- `ainir.evidence-bundle.v1`
- `ainir.evidence-resolution.v1`
- `ainir.evidence-validation-report.v1`
- `ainir.mcp-tool-call-profile.v1`
- `ainir.mcp-tool-call-envelope.v1`
- `ainir.mcp-host-context.v1`
- `ainir.mcp-tool-call-assessment.v1`
- `ainir.mcp-tool-call-conformance-pack.v1`
- `ainir.mcp-tool-call-conformance-report.v1`

## Python resource surface

The supported `ainir.resources` module exposes allowlisted installed resources:

- `PUBLIC_SCHEMA_NAMES`
- `PUBLIC_REGISTRY_NAMES`
- `read_schema_bytes` / `read_schema_text`
- `read_registry_bytes` / `read_registry_text`
- `schema_info` / `registry_info`
- `public_resource_manifest`

Consumers should use this API instead of deriving paths from `ainir.__file__`. Unknown names and path traversal attempts are rejected.

## Artifact surface

- stable and legacy `TrustGateDecision`
- stable and legacy `TrustReceipt`
- stable `TrustReceiptReplayReport` with exact/current/migrated mode fields
- content-bound `RegistrySnapshot`
- semantic `RegistryDiff`
- explicit local-review `RegistryMigrationRecord`
- offline evidence request/record/policy/bundle/resolution/validation-report artifacts
- legacy-compatible `VerifiedIntentPacket`
- TypeScript host-enforcement skeleton for eligible safe drafts
- bundled `ainir.public-demo.v1` profile and additive conformance-only profile packs
- bundled `ainir.mcp.reference.workspace.v1` profile and 26-case non-executing MCP conformance pack

A RegistryMigrationRecord is not a cryptographic signature or production authorization. `production_runtime_ready` remains false.

## Schema surface

- `schemas/draft_packet.schema.yaml`
- `schemas/profile_manifest.schema.json`
- `schemas/conformance_pack.schema.json`
- `schemas/conformance_report.schema.json`
- `schemas/trust_gate_decision.schema.json`
- `schemas/trust_receipt.schema.json`
- `schemas/trust_receipt_replay_report.schema.json`
- `schemas/registry_snapshot.schema.json`
- `schemas/registry_diff.schema.json`
- `schemas/registry_migration_record.schema.json`
- `schemas/evidence_request.schema.json`
- `schemas/evidence_record.schema.json`
- `schemas/evidence_provider_policy.schema.json`
- `schemas/evidence_bundle.schema.json`
- `schemas/evidence_resolution.schema.json`
- `schemas/evidence_validation_report.schema.json`
- `schemas/mcp_tool_call_profile.schema.json`
- `schemas/mcp_tool_call_envelope.schema.json`
- `schemas/mcp_host_context.schema.json`
- `schemas/mcp_tool_call_assessment.schema.json`
- `schemas/mcp_tool_call_conformance_pack.schema.json`
- `schemas/mcp_tool_call_conformance_report.schema.json`
- `schemas/verified_intent_packet.schema.json`

The same bytes are packaged under `ainir.schemas` in wheel installations.

## Registry surface

- `registries/safety_registry.yaml`
- `registries/operation_spec_registry.yaml`
- `registries/evidence_ledger.yaml`
- `registries/external_consumer_profiles.yaml`

The same bytes are packaged under `ainir.registries`. The public RC candidate can capture, diff, and locally replay content-bound snapshots of these registries. Production registry storage, signing, revocation, and delegated governance remain out of scope.

## P7 provisional public modules

- `ainir.mcp_authoring` fixed-semantics external MCP profile scaffolding;
- `ainir.mcp_conformance.run_mcp_conformance` for bundled or file-bound fixture packs;
- `ainir.openai_function_tool_adapter` for local binding and preflight of completed OpenAI Responses function calls;
- `ainir.openai_function_tool_eval` deterministic release-readiness evidence.

These modules expose no API client or execution surface.
