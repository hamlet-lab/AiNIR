> Please do not weaken gates simply to make a draft pass.

# Contributing

AiNIR is useful only if unsafe or unsupported semantics remain visible and blocked. Read `PUBLIC_SCOPE.md`, `PROTECTED_INVARIANTS.md`, and `AGENTS.md` before changing code or contracts.

## Set up

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: . .venv\Scripts\Activate.ps1
python -m pip install -c requirements.lock.txt -e ".[dev]"
```

## Validate

Run the full suite before focused release wrappers:

```bash
python -m pytest -q -p no:cacheprovider
python -m ainir conformance negative
python -m ainir conformance golden
python -m ainir profile validate ainir.public-demo.v1
python -m ainir conformance run ainir.public-demo.v1
python scripts/check_offline_evidence_providers.py
python scripts/check_mcp_tool_call_profile.py
python scripts/check_openai_function_tool_adapter.py
python scripts/run_phase30_v1_rc_candidate_check.py --mode quick-integrity
```

A quick-integrity pass is not a substitute for the full test suite.

## Good contribution paths

- clearer unsafe draft examples;
- smaller reproductions of model-generated hazards;
- negative, mutation, and tamper conformance cases;
- profile or registry proposals with explicit effects, capabilities, evidence, and transaction requirements;
- deterministic receipt and replay test vectors;
- documentation, portability, packaging, and contributor-experience improvements;
- stricter fail-closed predicates with compatibility analysis.

The preferred first profile contribution is generated and validated with:

```bash
ainir profile init profiles/<name> --profile-id <id> --workflow-id <workflow>
ainir profile validate profiles/<name>/profile.yaml
ainir conformance run profiles/<name>/profile.yaml
```

Do not edit a base registry merely to make a profile pass. Profile extensions must be additive and include positive, negative, mutation, and replay cases. P3 profiles may use only exact effect/capability identifiers already present in the packaged reviewed vocabulary; new aliases, role markers, external-effect allowlists, effect families, capability prefixes, or safety-critical operation aliases require a separate core-registry proposal.

Avoid changes that silently turn an unsafe or unknown draft into a passing draft. A repair must be explicit and followed by a fresh Trust Gate decision.

EvidenceProvider contributions must include issuer/scope, subject-binding, validity, revocation, reliability, tamper, and no-auto-promotion coverage. A provider must not mutate the Trust Gate Evidence Ledger as a side effect, and network or credential handling is outside the P5 public scope.

## Semantic-change requirements

A pull request that changes decisions, registries, schemas, evidence, lowering, handoff, receipts, replay, or consumer profiles must include:

1. protected invariants touched;
2. positive coverage;
3. negative or refusal coverage;
4. mutation or tamper coverage;
5. compatibility impact on existing receipts and registry snapshots;
6. documentation of any new public field or rule;
7. confirmation that unknown semantics still fail closed.

## Scope and security

AiNIR core does not execute downstream actions or provide production runtime security. Do not add credentials, live provider secrets, private archives, or enterprise-only policy material. Report vulnerabilities through `SECURITY.md`.

## MCP profile and host-adapter contributions

Use `ainir mcp init` for the first external profile proposal. External conformance cases must use in-root fixture files and must not reuse bundled scenario names. The scaffold's read-only effects, capabilities, resource type, and decision ceiling are reviewed constants, not editable trust labels.

Host-framework adapters may translate finalized, host-observed artifacts into existing AiNIR contracts, but must not import a provider SDK into core, call remote APIs, obtain or forward credentials, submit tool outputs, or execute tools. Include strict-schema, incomplete-artifact, credential-value, nested-substitution, and no-execution tests.
