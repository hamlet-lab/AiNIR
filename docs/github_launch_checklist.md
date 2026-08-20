# GitHub Release Maintenance Checklist

> **Current-state note:** AiNIR is already a public repository. This file used to be a pre-publication upload checklist; it now records the checks to preserve when maintaining the public RC. Historical private-GitHub trial steps are no longer release instructions.

## Repository state

Current public repository metadata:

```text
repository: hamlet-lab/AiNIR
visibility: public
description: Semantic trust layer that checks AI-agent actions and MCP tool calls before execution.
delete_branch_on_merge: false
allow_auto_merge: false
```

Current discovery topics:

```text
agent-governance
ai-agents
ai-safety
ai-security
conformance-testing
mcp
policy-as-code
pre-execution-validation
python
semantic-verification
tool-calling
tool-contracts
trust-layer
```

Keep [`github_repo_settings.md`](github_repo_settings.md) synchronized with the real repository settings rather than preserving older launch suggestions as if they were current.

## Files and public/private boundary

- [ ] Do not include private archive ZIPs.
- [ ] Do not include generated check folders.
- [ ] Keep `PUBLIC_SCOPE.md` and `docs/public_private_boundary.md` aligned with the public release surface.
- [ ] Confirm `LICENSE` remains Apache-2.0.
- [ ] Confirm `NOTICE` remains present.
- [ ] Keep generated scratch/check output outside committed source unless deliberately archived.

## Core release checks

Run from the repository root before a major release change:

```bash
python scripts/run_prelaunch_check.py --out-dir /tmp/ainir_prelaunch_results
```

Expected:

```text
overall_status: passed
```

The RC conformance and private-trial simulation remain useful regression checks even though the repository is already public:

```bash
python -m ainir conformance release-candidate --out-dir /tmp/ainir_phase30_v1_rc_candidate
python -m ainir conformance private-trial --out-dir /tmp/ainir_phase26_private_trial
```

## Python distribution

The public distribution identity is:

```text
distribution: ainir
current RC version: 1.0.0rc2
```

The normal first-run path is:

```bash
python -m pip install ainir
ainir demo
```

Publishing remains deliberately separate from normal repository CI. Follow [`PYPI_PUBLISHING.md`](PYPI_PUBLISHING.md): use the manual `publish-pypi` workflow, run `build-only` first, and never reuse an already-published version.

## Public wording

Use wording consistent with the current boundary:

> AiNIR is a public v1.0 RC semantic trust layer for checking bounded AI-generated workflow and tool-call proposals before host-owned execution. It is not a v1.0 final release and not a production runtime.

Avoid claims such as:

- `AiNIR v1.0 final`
- `production compiler/runtime`
- `universal arbitrary-code verifier`
- `replacement for authentication, authorization, sandboxing, or runtime controls`
- `PASS proves the external effect is safe`

## Historical pre-publication gate

The earlier process of staging the public surface in a private GitHub repository before making it visible has already served its purpose. Historical documents and the `private-trial` conformance path remain for traceability and regression testing; they are not instructions to make the current repository private again.
