# Instructions for coding agents

This repository contains a bounded semantic trust layer. Automated changes must preserve the trust boundary before optimizing convenience, coverage, or pass rates.

## Read first

1. `PUBLIC_SCOPE.md`
2. `PROTECTED_INVARIANTS.md`
3. `CONTRIBUTING.md`
4. `docs/public_private_boundary.md`
5. `docs/v1_known_limitations.md`

## Required workflow

- Work on one narrowly scoped issue per branch and pull request.
- Inspect existing tests and contracts before changing implementation code.
- Add a positive case, negative case, and mutation or tamper case for semantic changes.
- Run the full test suite, not only a phase or quick-integrity wrapper.
- Record compatibility effects on TrustReceipt, registry snapshots, and public schemas.
- Prefer the smallest fail-closed change. Unknown semantics must not become allowed by inference.

## Commands

```bash
python -m pip install -c requirements.lock.txt -e ".[dev]"
python -m pytest -q -p no:cacheprovider
python -m ainir conformance negative
python -m ainir conformance golden
python scripts/check_offline_evidence_providers.py
python scripts/check_mcp_tool_call_profile.py
python scripts/check_openai_function_tool_adapter.py
python scripts/run_phase30_v1_rc_candidate_check.py --mode quick-integrity
python scripts/check_distribution_contracts.py
```

## Forbidden shortcuts

- Do not weaken a gate merely to make a fixture pass.
- Do not treat model output, self-attestation, unbound metadata, or a provider's own trust label as evidence.
- Do not auto-promote a validated P5 provider candidate into the Trust Gate Evidence Ledger.
- Do not treat MCP descriptions, annotations, client metadata, or model claims as evidence, and do not move host-owned consent, authorization, resource, transaction, or execution into AiNIR core.
- Do not silently accept an unknown workflow, effect, capability, operation, or registry version.
- Do not add host execution, live credentials, network providers, or downstream compiler/runtime implementations to the core.
- Do not copy private archive material, enterprise policy packs, or unpublished integration details into the public repository.
- Do not claim production readiness, arbitrary-code verification, or v1 final stability without separate evidence and an explicit release decision.

## MCP boundary

Changes under `mcp_*` must preserve a non-executing host-preflight boundary. Do not add network clients, token handling, dynamic server trust, tool execution, or automatic Trust Gate/Evidence Ledger promotion. Every semantic change needs positive, refusal, mutation, and destructive-review coverage.

## Host-framework adapter boundary

Adapters under `*_host_adapter` or `openai_*_adapter` may parse and bind already observed artifacts only. Do not add SDK clients, API calls, streaming loops, credential handling, tool-output submission, retries, sessions, or execution. Require exact reviewed schema/profile binding and add cross-artifact substitution tests.
