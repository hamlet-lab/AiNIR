# Start here

> **Model output is a claim, not a fact.**

AiNIR is a bounded semantic trust layer for checking AI-generated workflow semantics before a host runtime is allowed to lower, hand off, or execute them.

If you only want to understand whether AiNIR is relevant to you, do the first four steps below. The deeper RC, registry, evidence-provider, MCP, and release documents remain available under `docs/`.

## 1. Install

Run from the repository root. The public demo only needs the package's runtime dependencies; contributor/test tooling is optional.

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Windows PowerShell

```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -e .
```

If you plan to run the full test suite or contributor checks, install the development extras instead with `pip install -e ".[dev]"`.

## 2. Run the public demo

### macOS / Linux

```bash
python -m ainir demo --out-dir "${TMPDIR:-/tmp}/ainir_demo_results"
```

### Windows PowerShell

```powershell
python -m ainir demo --out-dir "$env:TEMP\ainir_demo_results"
```

You should see unsafe examples refused and the transaction-bound outbox example pass.

```text
AiNIR public demo: passed
- account_deletion_hard_delete_blocked: blocked (10 critical)
- create_user_outbox_safe: passed (0 critical)
- order_payment_real_payment_blocked: blocked (16 critical)
- password_reset_raw_token_blocked: blocked (11 critical)
- pii_export_raw_pii_blocked: blocked (17 critical)
```

## 3. Inspect one refusal

The account-deletion example proposes a destructive hard-delete operation:

```yaml
workflow: AccountDeletion
operations:
  - op: auth.check_account_deletion_authorization
  - op: db.hard_delete_user
    effects: [effect.destructive.account.hard_delete]
    capabilities: [cap.account.delete.hard]
```

Evaluate it directly:

```bash
python -m ainir trust evaluate examples/account_deletion_hard_delete_blocked/draft.yaml --json
```

AiNIR treats the draft as a semantic claim and refuses it according to the registered public-demo contracts instead of treating the model proposal as executable truth.

## 4. Inspect one pass

Evaluate the safe transaction-bound outbox example:

```bash
python -m ainir trust evaluate examples/create_user_outbox_safe/draft.yaml --json
```

A passed decision may become eligible for a `TrustReceipt` and lowering. It still does not mean AiNIR itself executes the workflow.

At this point you have seen the core behavior: **refuse unsupported or unsafe semantics, and allow a bounded safe path to move forward.**

## 5. Pick your path

### I want to understand the architecture

Read:

1. [`docs/positioning_and_scope.md`](docs/positioning_and_scope.md)
2. [`docs/trust_gate.md`](docs/trust_gate.md)
3. [`docs/artifact_contracts.md`](docs/artifact_contracts.md)
4. [`docs/trust_receipt_persistence.md`](docs/trust_receipt_persistence.md)

### I want to use or extend workflow profiles

Read:

1. [`docs/profile_authoring.md`](docs/profile_authoring.md)
2. [`docs/profile_conformance.md`](docs/profile_conformance.md)
3. [`docs/workflow_registry_extension.md`](docs/workflow_registry_extension.md)
4. [`docs/evidence_provider_interface.md`](docs/evidence_provider_interface.md)

Then create an additive profile:

```bash
python -m ainir profile init profiles/example-audit --profile-id example.audit.v1 --workflow-id AuditRequest
python -m ainir profile validate profiles/example-audit/profile.yaml
python -m ainir conformance run profiles/example-audit/profile.yaml
```

### I want MCP or tool-call preflight

Start with the guided examples:

- [`examples/mcp_tool_call/README.md`](examples/mcp_tool_call/README.md)
- [`examples/openai_function_tool/README.md`](examples/openai_function_tool/README.md)

Then read the precise contracts:

- [`docs/mcp_tool_call_profile.md`](docs/mcp_tool_call_profile.md)
- [`docs/mcp_profile_authoring.md`](docs/mcp_profile_authoring.md)
- [`docs/openai_function_tool_host_adapter.md`](docs/openai_function_tool_host_adapter.md)

Run the bundled MCP example:

```bash
python -m ainir mcp assess \
  examples/mcp_tool_call/tool_descriptor.json \
  examples/mcp_tool_call/tool_call.json \
  examples/mcp_tool_call/transport_binding.json \
  examples/mcp_tool_call/host_input.json \
  --json
```

AiNIR does not contact or execute the MCP server.

### I want to inspect verification depth

Run:

```bash
python -m ainir conformance negative
python -m ainir conformance golden
python -m ainir conformance private-trial
```

Then read:

- [`docs/negative_conformance_corpus.md`](docs/negative_conformance_corpus.md)
- [`docs/golden_traces.md`](docs/golden_traces.md)
- [`docs/trust_receipt_registry_evolution.md`](docs/trust_receipt_registry_evolution.md)

### I want to contribute

Read:

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`PROTECTED_INVARIANTS.md`](PROTECTED_INVARIANTS.md)
- [`PUBLIC_SCOPE.md`](PUBLIC_SCOPE.md)
- [`SECURITY.md`](SECURITY.md)

## Scope note

This repository is a **v1.0 RC candidate public demo**, not a production runtime or a verifier for arbitrary AI-generated code. Unknown workflows are refused rather than guessed. The precise public claim and current limitations are documented in [`docs/positioning_and_scope.md`](docs/positioning_and_scope.md) and [`docs/v1_known_limitations.md`](docs/v1_known_limitations.md).

For a guided tour of the bundled scenarios, see [`examples/README.md`](examples/README.md).
