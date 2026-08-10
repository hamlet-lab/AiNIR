# External MCP profile authoring

P7 adds a bounded contributor path for MCP preflight profiles without turning AiNIR into an MCP runtime.

## Generate a reviewed template

```bash
ainir mcp init profiles/example-readonly \
  --profile-id example.workspace.readonly.v1 \
  --tool-name workspace.example_read
```

The command writes:

```text
profile.yaml
cases.yaml
descriptors/<tool>.json
fixtures/*.json
README.md
```

The generated profile has fixed read-only semantics:

- exact `effect.resource.read` and `cap.resource.read` bindings;
- one workspace-path resource pointer;
- explicit per-call consent;
- fail-closed unknown tools;
- no task execution;
- no credential handling;
- no transport or tool execution in AiNIR;
- `production_runtime_ready: false`.

Only identity fields are configurable. Changing effects, capabilities, risk class, transaction requirements, resource semantics, or descriptor meaning requires independent core review rather than treating the scaffold as automatic approval.

## Validate and run conformance

```bash
ainir mcp profile profiles/example-readonly/profile.yaml --json
ainir mcp conformance \
  --profile profiles/example-readonly/profile.yaml \
  --cases profiles/example-readonly/cases.yaml \
  --out-dir /tmp/ainir-example-mcp-conformance \
  --json
```

External profiles must use file-bound fixtures. The built-in shorthand `scenario` names are private to the bundled reference profile and cannot be reused by an external profile. Expected `invalid` cases accept only explicit AiNIR normalization/conformance errors; unexpected programming exceptions escape the runner instead of being misreported as successful conformance.

Each fixture case binds four files:

- reviewed descriptor;
- proposed `tools/call` request;
- transport observations;
- host-owned context input.

Fixture paths must be relative regular files contained by the profile root. Parent traversal, absolute paths, and symlink escape are refused before execution of the conformance case.

## Required evidence for a contribution

A contributed profile should contain at least:

1. a positive case;
2. an authorization, consent, capability, or resource refusal case;
3. a descriptor or schema mutation case;
4. deterministic report hashes across repeated runs;
5. an explicit statement that AiNIR performs no execution.

The generated four-case pack demonstrates safe read, path traversal refusal, denied-consent refusal, and descriptor mutation refusal.

## Non-goals

The authoring path does not:

- infer semantics from tool descriptions;
- discover or connect to MCP servers;
- register arbitrary effects or capabilities;
- grant production trust to a contributor profile;
- open OAuth or credential flows;
- execute a tool;
- override the core Trust Gate or promote evidence.
