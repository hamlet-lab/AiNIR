# AiNIR docs

This directory contains the current architecture, integration, conformance, release-boundary, and development-history documentation for the public AiNIR RC.

Start with the current user/integration path. Phase-specific documents are historical traceability material unless a current document links to them for a specific contract.

## Start here

1. [`../START_HERE.md`](../START_HERE.md) — install the public package and run the bundled demo.
2. [`integration_quickstart.md`](integration_quickstart.md) — put a bounded AiNIR preflight in front of a reviewed tool call without giving AiNIR execution authority.
3. [`pre_v1_status.md`](pre_v1_status.md) — current public RC status and claim boundary.
4. [`trust_gate.md`](trust_gate.md) — the unified decision surface.
5. [`cli.md`](cli.md) — stable user-facing commands without phase history.

## Recommended technical reading path

1. [`architecture.md`](architecture.md) — system overview.
2. [`artifact_contracts.md`](artifact_contracts.md) — stable identifiers and compatibility expectations.
3. [`trust_gate.md`](trust_gate.md) — the decision boundary.
4. [`trust_receipt_persistence.md`](trust_receipt_persistence.md) — issuing and replaying TrustReceipts.
5. [`profile_authoring.md`](profile_authoring.md) — safe additive workflow profile authoring.
6. [`profile_conformance.md`](profile_conformance.md) — standalone profile conformance reports.
7. [`trust_receipt_registry_evolution.md`](trust_receipt_registry_evolution.md) — content-bound snapshots, semantic diffs, and replay modes.
8. [`offline_evidence_providers.md`](offline_evidence_providers.md) — deterministic provider contracts and the no-auto-promotion boundary.
9. [`mcp_tool_call_profile.md`](mcp_tool_call_profile.md) — bounded `tools/call` preflight and fail-closed host bindings.
10. [`mcp_profile_authoring.md`](mcp_profile_authoring.md) — fixed-semantics external MCP profile scaffolding.
11. [`openai_function_tool_host_adapter.md`](openai_function_tool_host_adapter.md) — completed function-call binding without API calls or execution.
12. [`mcp_host_owned_adapter.md`](mcp_host_owned_adapter.md) — why execution remains outside AiNIR core.
13. [`v1_rc_candidate.md`](v1_rc_candidate.md) — current RC candidate decision and boundary.
14. [`v1_rc_scope.md`](v1_rc_scope.md) — what is frozen for RC review.
15. [`v1_known_limitations.md`](v1_known_limitations.md) — intentional public limitations.
16. [`negative_conformance_corpus.md`](negative_conformance_corpus.md) — synthetic fixtures that must be refused.
17. [`golden_traces.md`](golden_traces.md) — deterministic replay expectations.
18. [`lowering_gate.md`](lowering_gate.md) — when lowering is allowed or refused.
19. [`verified_intent_packet.md`](verified_intent_packet.md) — conservative export surface.
20. [`public_private_boundary.md`](public_private_boundary.md) — what belongs in the public repository.
21. [`legacy_cli_compatibility.md`](legacy_cli_compatibility.md) — deprecated command mapping retained for the RC transition.

## Contributor and maintenance entry points

- [`../PUBLIC_SCOPE.md`](../PUBLIC_SCOPE.md)
- [`../PROTECTED_INVARIANTS.md`](../PROTECTED_INVARIANTS.md)
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- [`../SECURITY.md`](../SECURITY.md)
- [`distribution_contracts.md`](distribution_contracts.md)
- [`PYPI_PUBLISHING.md`](PYPI_PUBLISHING.md)
- [`github_repo_settings.md`](github_repo_settings.md)
- [`github_launch_checklist.md`](github_launch_checklist.md)

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

- [`PYPI_PUBLISHING.md`](PYPI_PUBLISHING.md) — current manual PyPI publishing path.
- [`pre_v1_status.md`](pre_v1_status.md) — current public RC state.
- [`v1_rc_candidate.md`](v1_rc_candidate.md) — current candidate boundary.
- [`github_repo_settings.md`](github_repo_settings.md) — current repository metadata and public settings.
- [`prelaunch_check.md`](prelaunch_check.md) — release regression check.
- [`private_archive_boundary.md`](private_archive_boundary.md) — public/private storage boundary.
- [`github_launch_checklist.md`](github_launch_checklist.md) — current public-RC maintenance checklist; historically the prelaunch checklist.
- [`public_launch_candidate.md`](public_launch_candidate.md) — historical pre-publication record.
- [`public_launch_kit.md`](public_launch_kit.md) — maintained public-facing copy and post-launch guidance.

## v1.0 RC candidate docs

- [`v1_rc_candidate.md`](v1_rc_candidate.md)
- [`v1_rc_scope.md`](v1_rc_scope.md)
- [`v1_api_surface.md`](v1_api_surface.md)
- [`v1_acceptance_criteria.md`](v1_acceptance_criteria.md)
- [`v1_known_limitations.md`](v1_known_limitations.md)

## Development history

Phase-specific documents are kept for traceability. They are not required for a first read.

- [`development/README.md`](development/README.md)
- [`development/baseline-2026-08-09.md`](development/baseline-2026-08-09.md)
- [`development/priority-plan-2026-08.md`](development/priority-plan-2026-08.md)
- [`development/p1-release-contracts-2026-08-10.md`](development/p1-release-contracts-2026-08-10.md)
- [`development/p2-stable-cli-contracts-2026-08-10.md`](development/p2-stable-cli-contracts-2026-08-10.md)
- [`development/p3-profile-sdk-conformance-2026-08-10.md`](development/p3-profile-sdk-conformance-2026-08-10.md)
- [`development/p4-registry-evolution-replay-2026-08-10.md`](development/p4-registry-evolution-replay-2026-08-10.md)
- [`development/p5-offline-evidence-providers-2026-08-10.md`](development/p5-offline-evidence-providers-2026-08-10.md)
- [`development/p6-mcp-tool-call-profile-2026-08-10.md`](development/p6-mcp-tool-call-profile-2026-08-10.md)
- [`development/p7-openai-host-adapter-authoring-2026-08-10.md`](development/p7-openai-host-adapter-authoring-2026-08-10.md)
- [`v1_rc_candidate_patch4.md`](v1_rc_candidate_patch4.md)
- [`v1_rc_candidate_patch6.md`](v1_rc_candidate_patch6.md)
- [`v1_rc_candidate_patch7.md`](v1_rc_candidate_patch7.md)
- [`cross_platform_output_paths.md`](cross_platform_output_paths.md)
