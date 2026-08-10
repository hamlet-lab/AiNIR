# AiNIR docs

This directory contains architecture notes, conformance fixtures, release-candidate boundaries, and roadmap notes for the public demo.

Start here if you want to understand the system rather than the development history.

Contributor and maintenance entry points:

- [`../PUBLIC_SCOPE.md`](../PUBLIC_SCOPE.md)
- [`../PROTECTED_INVARIANTS.md`](../PROTECTED_INVARIANTS.md)
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- [`../SECURITY.md`](../SECURITY.md)
- [`development/baseline-2026-08-09.md`](development/baseline-2026-08-09.md)
- [`development/priority-plan-2026-08.md`](development/priority-plan-2026-08.md)
- [`development/p1-release-contracts-2026-08-10.md`](development/p1-release-contracts-2026-08-10.md)
- [`development/p2-stable-cli-contracts-2026-08-10.md`](development/p2-stable-cli-contracts-2026-08-10.md)
- [`development/p3-profile-sdk-conformance-2026-08-10.md`](development/p3-profile-sdk-conformance-2026-08-10.md)
- [`development/p4-registry-evolution-replay-2026-08-10.md`](development/p4-registry-evolution-replay-2026-08-10.md)
- [`development/p5-offline-evidence-providers-2026-08-10.md`](development/p5-offline-evidence-providers-2026-08-10.md)
- [`development/p6-mcp-tool-call-profile-2026-08-10.md`](development/p6-mcp-tool-call-profile-2026-08-10.md)
- [`development/p7-openai-host-adapter-authoring-2026-08-10.md`](development/p7-openai-host-adapter-authoring-2026-08-10.md)
- [`distribution_contracts.md`](distribution_contracts.md)

## Recommended reading path

1. [`cli.md`](cli.md) — stable user-facing commands without phase history.
2. [`artifact_contracts.md`](artifact_contracts.md) — stable identifiers and legacy replay compatibility.
3. [`legacy_cli_compatibility.md`](legacy_cli_compatibility.md) — deprecated command mapping for the RC transition.
4. [`profile_authoring.md`](profile_authoring.md) — safe additive workflow profile authoring.
5. [`profile_conformance.md`](profile_conformance.md) — standalone profile conformance reports.
6. [`trust_receipt_registry_evolution.md`](trust_receipt_registry_evolution.md) — content-bound snapshots, semantic diffs, and replay modes.
7. [`offline_evidence_providers.md`](offline_evidence_providers.md) — deterministic provider contracts and no-auto-promotion boundary.
8. [`mcp_tool_call_profile.md`](mcp_tool_call_profile.md) — bounded `tools/call` preflight and fail-closed host bindings.
9. [`mcp_profile_authoring.md`](mcp_profile_authoring.md) — fixed-semantics external MCP profile scaffolding.
10. [`openai_function_tool_host_adapter.md`](openai_function_tool_host_adapter.md) — completed Responses function-call binding without API calls or execution.
11. [`mcp_host_owned_adapter.md`](mcp_host_owned_adapter.md) — why execution remains outside AiNIR core.
12. [`v1_rc_candidate.md`](v1_rc_candidate.md) — v1.0 RC candidate decision and boundary.
9. [`v1_rc_scope.md`](v1_rc_scope.md) — what is frozen for RC review.
10. [`pre_v1_status.md`](pre_v1_status.md) — current scope and what AiNIR does not claim.
11. [`trust_gate.md`](trust_gate.md) — the unified decision surface.
12. [`trust_receipt_persistence.md`](trust_receipt_persistence.md) — issuing and replaying TrustReceipts.
13. [`negative_conformance_corpus.md`](negative_conformance_corpus.md) — synthetic fixtures that must be refused.
14. [`golden_traces.md`](golden_traces.md) — deterministic replay expectations.
15. [`lowering_gate.md`](lowering_gate.md) — when lowering is allowed or refused.
16. [`verified_intent_packet.md`](verified_intent_packet.md) — optional future export surface.
17. [`public_private_boundary.md`](public_private_boundary.md) — what belongs in the public repo.

## Core architecture docs

- [`architecture.md`](architecture.md)
- [`safety_registry.md`](safety_registry.md)
- [`strict_draft_ast.md`](strict_draft_ast.md)
- [`evidence_ledger.md`](evidence_ledger.md)
- [`operation_spec_registry.md`](operation_spec_registry.md)
- [`execution_context.md`](execution_context.md)
- [`transaction_binding.md`](transaction_binding.md)
- [`effect_contracts_and_semantic_roles.md`](effect_contracts_and_semantic_roles.md)

## Scope and extensibility docs

- [`workflow_registry_extension.md`](workflow_registry_extension.md)
- [`profile_authoring.md`](profile_authoring.md)
- [`profile_conformance.md`](profile_conformance.md)
- [`evidence_provider_interface.md`](evidence_provider_interface.md)
- [`offline_evidence_providers.md`](offline_evidence_providers.md)
- [`mcp_tool_call_profile.md`](mcp_tool_call_profile.md)
- [`mcp_profile_authoring.md`](mcp_profile_authoring.md)
- [`openai_function_tool_host_adapter.md`](openai_function_tool_host_adapter.md)
- [`mcp_host_owned_adapter.md`](mcp_host_owned_adapter.md)
- [`effect_taxonomy_and_canonical_effects.md`](effect_taxonomy_and_canonical_effects.md)
- [`trust_receipt_registry_evolution.md`](trust_receipt_registry_evolution.md)
- [`executable_claim_semantics.md`](executable_claim_semantics.md)
- [`verified_intent_packet_scope.md`](verified_intent_packet_scope.md)
- [`v1_roadmap.md`](v1_roadmap.md)

## Release and publishing docs

- [`github_launch_checklist.md`](github_launch_checklist.md)
- [`github_repo_settings.md`](github_repo_settings.md)
- [`prelaunch_check.md`](prelaunch_check.md)
- [`private_archive_boundary.md`](private_archive_boundary.md)
- [`public_launch_candidate.md`](public_launch_candidate.md)

## v1.0 RC candidate docs

- [`v1_rc_candidate.md`](v1_rc_candidate.md)
- [`v1_rc_scope.md`](v1_rc_scope.md)
- [`v1_api_surface.md`](v1_api_surface.md)
- [`v1_acceptance_criteria.md`](v1_acceptance_criteria.md)
- [`v1_known_limitations.md`](v1_known_limitations.md)

## Development history

Phase-specific documents are kept for traceability. They are not required for a first read. Read them when you need to understand why a particular gate or fixture was added.

- [v1.0 RC Candidate Patch 4 — Registry and Classifier Consistency](v1_rc_candidate_patch4.md)
- [Cross-platform output paths](cross_platform_output_paths.md)

- [v1.0 RC Candidate Patch 6 — Release Identity and Cross-platform Temp Paths](v1_rc_candidate_patch6.md)
- [v1.0 RC Candidate Patch 7 — Repo-local Temp Isolation Guard](v1_rc_candidate_patch7.md)
