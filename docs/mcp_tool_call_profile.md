# MCP tool-call semantic profile

AiNIR P6 adds a bounded, consumer-neutral profile for inspecting a proposed MCP `tools/call` before a host decides whether to execute it.

## Boundary

AiNIR does not open an MCP transport, discover servers, obtain credentials, run Tasks, perform elicitation, or execute a tool. The host supplies:

1. the exact tool descriptor it observed;
2. the proposed JSON-RPC `tools/call` request;
3. protocol and transport observations;
4. a host-owned context for authentication, authorization audience, schema validation, capabilities, resource resolution, consent, and transaction state.

AiNIR returns a self-hashed `AiNIRMCPToolCallAssessment`. Only `overall_status: passed` permits a host handoff. Even then, `execution_performed` and `production_runtime_ready` remain false, and the host must revalidate authorization and resource identity at execution time.

Host actions are status-bound. A `passed` assessment may instruct the host to execute outside AiNIR only after time-of-use revalidation. A `review_required`, `refused`, or `invalid` assessment carries `do_not_execute`; destructive review requires a new assessment after final confirmation rather than silently converting the old assessment into permission.

## Public contracts

- `ainir.mcp-tool-call-profile.v1`
- `ainir.mcp-tool-call-envelope.v1`
- `ainir.mcp-host-context.v1`
- `ainir.mcp-tool-call-assessment.v1`
- `ainir.mcp-tool-call-conformance-pack.v1`
- `ainir.mcp-tool-call-conformance-report.v1`

The corresponding JSON Schemas are packaged under `ainir.schemas` and exposed through `ainir.resources`.

## Reviewed reference profile

The bundled `ainir.mcp.reference.workspace.v1` profile contains three exact descriptor contracts:

| Tool | Effect | Capability | Maximum decision |
|---|---|---|---|
| `workspace.read_text` | `effect.resource.read` | `cap.resource.read` | `passed` |
| `workspace.write_text` | `effect.resource.write` | `cap.resource.write` | `passed` with transaction and rollback bindings |
| `workspace.delete_file` | `effect.resource.delete` | `cap.resource.delete` | `review_required` |

The descriptor, input schema, output schema, effects, capabilities, server identity, authorization audience, resource pointers, transaction requirement, rollback requirement, and risk class are all profile-bound. Unknown tools fail closed.

## Untrusted metadata

Tool descriptions and annotations are preserved for audit but do not establish semantic truth. AiNIR refuses an annotation that understates a reviewed contract, such as marking a write tool read-only. Model output and client metadata are not evidence.

## Host-owned checks

The host context binds:

- authenticated server identity and origin;
- authorization audience;
- protocol version and observed method/name headers;
- a host-owned JSON Schema validation result bound to the exact schema and arguments hashes;
- exact capability grants, with widening refused;
- normalized resources and host scope IDs;
- symlink-resolution status;
- explicit per-call consent bound to the envelope, arguments, and resources;
- validity timestamps from a host-controlled clock;
- prepared transaction and rollback evidence when required.

Credential-like field names and common credential value forms inside arguments or request metadata are refused. Workspace paths reject absolute paths, drive/alternate-data-stream separators, parent traversal, ASCII control characters, Windows reserved device names, trailing space/dot segments, and NUL bytes.

## Protocol scope

The reference profile recognizes the bounded request shapes used by MCP protocol versions `2025-11-25` and `2026-07-28`. P6 treats Tasks and multi-round tool input responses as unsupported and refuses them instead of implying that AiNIR implements those runtimes.

## Commands

```bash
ainir mcp profile --json
ainir mcp normalize \
  examples/mcp_tool_call/tool_descriptor.json \
  examples/mcp_tool_call/tool_call.json \
  examples/mcp_tool_call/transport_binding.json \
  --out /tmp/mcp-envelope.json

ainir mcp assess \
  examples/mcp_tool_call/tool_descriptor.json \
  examples/mcp_tool_call/tool_call.json \
  examples/mcp_tool_call/transport_binding.json \
  examples/mcp_tool_call/host_input.json \
  --out-dir /tmp/mcp-assessment --json

ainir mcp conformance --out-dir /tmp/mcp-conformance --json
```

The conformance pack contains 26 deterministic positive, refusal, mutation, and review cases. It performs no network access and executes no tool.

## Non-goals

- MCP client or server implementation;
- transport/session ownership;
- OAuth or credential handling;
- tool discovery trust;
- production JSON Schema engine;
- Tasks, elicitation, sampling, or multi-round tool runtime;
- automatic Trust Gate override or Evidence Ledger promotion;
- proof that an MCP server or tool implementation is benign.

## External contributor profiles

P7 adds `ainir mcp init` and file-bound external conformance packs. The scaffold fixes reviewed read-only semantics and lets contributors change identity fields only. External cases must bind descriptor, call, transport, and host-input files inside the profile root; built-in scenario names cannot be reused. See [`mcp_profile_authoring.md`](mcp_profile_authoring.md).
