# AiNIR docs

This directory is the **maintained documentation surface** for the public AiNIR RC. Historical phase-by-phase and superseded release notes live under [`archive/`](archive/) so current guidance is easier to find.

## Start here

1. [`../START_HERE.md`](../START_HERE.md) — install `ainir` from PyPI and run the bundled demo.
2. [`integration_quickstart.md`](integration_quickstart.md) — put a bounded AiNIR preflight in front of a reviewed tool call.
3. [`pre_v1_status.md`](pre_v1_status.md) — current public RC status and claim boundary.
4. [`trust_gate.md`](trust_gate.md) — the unified semantic decision surface.
5. [`cli.md`](cli.md) — stable user-facing commands.

## Integration and host boundary

- [`integration_quickstart.md`](integration_quickstart.md) — five-minute integration path.
- [`mcp_tool_call_profile.md`](mcp_tool_call_profile.md) — bounded MCP `tools/call` preflight.
- [`mcp_profile_authoring.md`](mcp_profile_authoring.md) — reviewed external MCP profile scaffolding.
- [`openai_function_tool_host_adapter.md`](openai_function_tool_host_adapter.md) — completed function-call binding without API calls or execution.
- [`mcp_host_owned_adapter.md`](mcp_host_owned_adapter.md) — why final execution remains host-owned.
- [`profile_authoring.md`](profile_authoring.md) / [`profile_conformance.md`](profile_conformance.md) — additive profile authoring and conformance.

## Contracts, evidence, and replay

- [`architecture.md`](architecture.md) — system overview.
- [`artifact_contracts.md`](artifact_contracts.md) — public artifact identifiers and compatibility expectations.
- [`safety_registry.md`](safety_registry.md) / [`operation_spec_registry.md`](operation_spec_registry.md) — reviewed semantic registries.
- [`evidence_ledger.md`](evidence_ledger.md) / [`evidence_provider_interface.md`](evidence_provider_interface.md) / [`offline_evidence_providers.md`](offline_evidence_providers.md) — evidence boundaries.
- [`trust_receipt.md`](trust_receipt.md) / [`trust_receipt_persistence.md`](trust_receipt_persistence.md) / [`trust_receipt_registry_evolution.md`](trust_receipt_registry_evolution.md) — receipt issue, storage, and replay.
- [`negative_conformance_corpus.md`](negative_conformance_corpus.md) / [`golden_traces.md`](golden_traces.md) — refusal and deterministic replay expectations.
- [`verified_intent_packet.md`](verified_intent_packet.md) / [`verified_intent_packet_scope.md`](verified_intent_packet_scope.md) — conservative export surface.

## RC scope

- [`v1_rc_candidate.md`](v1_rc_candidate.md) — current RC candidate decision and boundary.
- [`v1_rc_scope.md`](v1_rc_scope.md) — frozen RC review scope.
- [`v1_api_surface.md`](v1_api_surface.md) — public API surface.
- [`v1_acceptance_criteria.md`](v1_acceptance_criteria.md) — RC acceptance criteria.
- [`v1_known_limitations.md`](v1_known_limitations.md) — intentional limitations.
- [`v1_roadmap.md`](v1_roadmap.md) — forward work without widening present claims.
- [`positioning_and_scope.md`](positioning_and_scope.md) / [`public_private_boundary.md`](public_private_boundary.md) — positioning and public/private boundary.

## Release and repository maintenance

- [`PYPI_PUBLISHING.md`](PYPI_PUBLISHING.md) — manual Trusted Publishing and post-publication PyPI smoke.
- [`distribution_contracts.md`](distribution_contracts.md) — wheel/sdist contract checks.
- [`github_repo_settings.md`](github_repo_settings.md) — current GitHub metadata/settings.
- [`github_launch_checklist.md`](github_launch_checklist.md) — public-RC maintenance checklist.
- [`public_launch_kit.md`](public_launch_kit.md) — maintained public-facing copy.
- [`prelaunch_check.md`](prelaunch_check.md) — legacy-named but still useful release regression check.
- [`legacy_cli_compatibility.md`](legacy_cli_compatibility.md) — temporary RC compatibility routing.

## Contributor entry points

- [`../PUBLIC_SCOPE.md`](../PUBLIC_SCOPE.md)
- [`../PROTECTED_INVARIANTS.md`](../PROTECTED_INVARIANTS.md)
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- [`../SECURITY.md`](../SECURITY.md)

## Historical archive

[`archive/README.md`](archive/README.md) contains the development lineage, Phase 13–26 prose, superseded RC patch notes, and the historical public-launch candidate record. Those files are retained for traceability, **not as current installation or release instructions**.

Executable phase-named regression modules/tests remain in `src/`, `scripts/`, and `tests/` because they still verify the RC; the archive move only separates historical prose from maintained documentation.
