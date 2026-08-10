# Start here

AiNIR is a **v1.0 RC candidate semantic trust layer** for bounded public review and final scope review.

The public demo is built around one rule:

> **Model output is a claim, not a fact.**

AiNIR is not trying to make every model draft pass. It is trying to expose unsupported or unsafe program semantics before they can be lowered or handed to a host runtime.

## 0. Understand the scope

Read [`docs/positioning_and_scope.md`](docs/positioning_and_scope.md) if you want the precise claim: this is a bounded v1.0 RC candidate demo, not a production verifier for arbitrary AI-generated code.

## 1. Install

Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## 2. Run the demo

```bash
python -m ainir demo --out-dir /tmp/ainir_demo_results  # Windows PowerShell: $env:TEMP\ainir_demo_results
```

You should see one safe example pass and four negative conformance examples refused.

## 3. Inspect a Trust Gate decision

```bash
python -m ainir trust evaluate examples/create_user_outbox_safe/draft.yaml --json --out-dir /tmp/ainir_trust_gate
```

A Trust Gate decision answers:

- Is the draft structurally valid?
- Which gates passed or failed?
- Is lowering allowed?
- Can a TrustReceipt be issued and replayed?

## 4. Run the release-readiness simulation

```bash
python -m ainir conformance private-trial
```

This checks the public candidate in a fresh temporary copy and confirms the checkout stays clean.

## 5. Run focused checks

```bash
python -m ainir conformance negative --out-dir /tmp/ainir_negative_conformance  # Windows: $env:TEMP\ainir_negative_conformance
python -m ainir conformance golden --out-dir /tmp/ainir_golden_traces  # Windows: $env:TEMP\ainir_golden_traces
python scripts/run_prelaunch_check.py
python scripts/run_release_candidate_review.py
```

## 6. Create and validate a workflow profile

```bash
python -m ainir profile init profiles/example-audit --profile-id example.audit.v1 --workflow-id AuditRequest
python -m ainir profile validate profiles/example-audit/profile.yaml
python -m ainir conformance run profiles/example-audit/profile.yaml --out-dir /tmp/ainir_example_profile
```

The generated profile is an isolated conformance extension, not a production registry or execution authorization. It can compose only the reviewed exact effect/capability vocabulary.

## 7. Inspect registry evolution and replay

```bash
python -m ainir receipt issue examples/create_user_outbox_safe/draft.yaml --out-dir /tmp/ainir_receipts --json
python -m ainir registry snapshot --evolution --out /tmp/ainir_registry.json --json
python -m ainir registry diff /tmp/ainir_registry.json /tmp/ainir_registry.json --json
```

`receipt issue` writes a RegistrySnapshot sidecar. Current and migrated replay never rewrite the historical receipt. Migrated replay uses explicit local review records; cryptographic signing and production registry authorization are not implemented. Read `docs/trust_receipt_registry_evolution.md` before using those modes.

## 8. Validate an offline evidence candidate

```bash
python -m ainir evidence bundle examples/offline_evidence_provider/bundle.json --json
python -m ainir evidence policy examples/offline_evidence_provider/policy.json --json
python -m ainir evidence resolve examples/offline_evidence_provider/bundle.json examples/offline_evidence_provider/policy.json examples/create_user_outbox_safe/draft.yaml --claim-id claim.create_user_uses_outbox --evidence-id evidence.ainir.fixture.safe-outbox --expected-kind verifier_report --evaluation-time 2026-08-10T00:00:00Z --json
```

The result is a validated candidate only. It is not inserted into the Trust Gate Evidence Ledger. Read `docs/offline_evidence_providers.md` before implementing another provider.

## 9. Assess a bounded MCP tool call

```bash
python -m ainir mcp profile
python -m ainir mcp assess examples/mcp_tool_call/tool_descriptor.json examples/mcp_tool_call/tool_call.json examples/mcp_tool_call/transport_binding.json examples/mcp_tool_call/host_input.json --json
python -m ainir mcp conformance
```

AiNIR emits a preflight assessment and never contacts or executes the tool. Read `docs/mcp_tool_call_profile.md` and `docs/mcp_host_owned_adapter.md`.

## 10. Inspect the examples

- `examples/password_reset_raw_token_blocked/draft.yaml`
- `examples/order_payment_real_payment_blocked/draft.yaml`
- `examples/pii_export_raw_pii_blocked/draft.yaml`
- `examples/account_deletion_hard_delete_blocked/draft.yaml`
- `examples/create_user_outbox_safe/draft.yaml`

## 11. Read the docs in order

1. `docs/README.md`
2. `docs/cli.md`
3. `docs/profile_authoring.md`
4. `docs/profile_conformance.md`
5. `docs/artifact_contracts.md`
6. `docs/trust_gate.md`
7. `docs/trust_receipt_persistence.md`
8. `docs/trust_receipt_registry_evolution.md`
9. `docs/offline_evidence_providers.md`
10. `docs/mcp_tool_call_profile.md`
11. `docs/mcp_host_owned_adapter.md`
12. `docs/negative_conformance_corpus.md`
13. `docs/golden_traces.md`
14. `docs/public_private_boundary.md`

## 12. Read the RC candidate scope and roadmap

- `docs/v1_rc_candidate.md`
- `docs/v1_rc_scope.md`
- `docs/v1_api_surface.md`
- `docs/v1_known_limitations.md`
- `docs/v1_acceptance_criteria.md`
- `docs/v1_roadmap.md`
- `docs/workflow_registry_extension.md`
- `docs/evidence_provider_interface.md`
- `docs/effect_taxonomy_and_canonical_effects.md`
- `docs/trust_receipt_registry_evolution.md`

## 13. Read before publishing

- `docs/pre_v1_status.md`
- `docs/public_private_boundary.md`
- `docs/private_archive_boundary.md`
- `docs/github_launch_checklist.md`

Before publishing a prerelease, confirm README rendering, GitHub Actions, and the v1.0 RC candidate check.


## Windows PowerShell output paths

Most examples use `/tmp/...` for brevity. On Windows PowerShell, use `$env:TEMP\...` instead, or set `AINIR_TEMP_ROOT` before running review scripts. See `docs/cross_platform_output_paths.md`.

## 14. Create an external MCP profile and assess a completed function call

```bash
python -m ainir mcp init profiles/example-readonly --profile-id example.workspace.readonly.v1 --tool-name workspace.example_read
python -m ainir mcp conformance --profile profiles/example-readonly/profile.yaml --cases profiles/example-readonly/cases.yaml --json
python -m ainir openai function-tool assess examples/openai_function_tool/tool_definition.json examples/openai_function_tool/function_call.json examples/openai_function_tool/host_binding.json examples/openai_function_tool/host_input.json --json
```

The OpenAI adapter consumes already observed JSON only. It does not create a client, call the API, submit tool output, or execute the tool.
