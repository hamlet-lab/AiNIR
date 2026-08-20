# MCP tool-call preflight example

If you use MCP, this is the shortest way to see where AiNIR can sit in the stack.

```text
agent / model
    ↓ proposes
MCP tools/call
    ↓
AiNIR semantic preflight
    ├─ passed ─────────────→ host revalidates → MCP server / tool
    ├─ review_required ────→ do not execute yet
    ├─ refused ────────────→ do not execute
    └─ invalid ────────────→ do not execute
```

AiNIR does **not** contact the MCP server or execute the tool. This example is deliberately offline: the host supplies what it observed, and AiNIR checks those observations against a reviewed semantic profile.

## The proposed call

The bundled call asks for a bounded workspace read:

```json
{
  "method": "tools/call",
  "params": {
    "name": "workspace.read_text",
    "arguments": {
      "path": "docs/README.md"
    }
  }
}
```

The bundled descriptor calls the tool `workspace.read_text`, marks it read-only, and gives it a JSON Schema. Those descriptions and annotations are preserved for audit, but AiNIR does not treat them as semantic truth by themselves.

## What the host separately supplies

The host-owned input says, among other things, that:

- the MCP server identity and origin were observed by the host;
- authentication succeeded;
- host-owned schema validation passed;
- `cap.resource.read` is granted;
- the resource is inside `scope.workspace.docs`;
- symlinks were resolved;
- explicit consent is approved and still within its validity window.

That separation is the point: **the agent proposes the call; the host supplies trusted observations; AiNIR checks whether the reviewed semantic contract is satisfied.**

## Run it

```bash
ainir mcp profile
ainir mcp normalize \
  examples/mcp_tool_call/tool_descriptor.json \
  examples/mcp_tool_call/tool_call.json \
  examples/mcp_tool_call/transport_binding.json \
  --out /tmp/mcp_envelope.json

ainir mcp assess \
  examples/mcp_tool_call/tool_descriptor.json \
  examples/mcp_tool_call/tool_call.json \
  examples/mcp_tool_call/transport_binding.json \
  examples/mcp_tool_call/host_input.json \
  --out-dir /tmp/ainir_mcp_assessment --json

ainir mcp conformance --out-dir /tmp/ainir_mcp_conformance --json
```

For the reviewed `workspace.read_text` contract, the profile permits a maximum decision of `passed` when the required bindings hold.

A passing assessment is **not** proof that the server implementation is benign and is not permission that survives forever. The host must revalidate authorization, resource identity and scope at execution time, preserve human control, and execute outside AiNIR core.

## Why this is more than schema validation

The same reference profile distinguishes different semantics even when every input is valid JSON:

| Reviewed tool | Semantic effect | Extra requirement / maximum decision |
|---|---|---|
| `workspace.read_text` | resource read | may pass when read bindings hold |
| `workspace.write_text` | resource write | transaction + rollback bindings required |
| `workspace.delete_file` | resource delete | maximum decision is `review_required` |

So the question is not merely **“Does this `tools/call` match a schema?”** It is also **“What does this call mean, what capability does it require, what evidence has the host supplied, and may this semantic action move toward execution?”**

For the precise contract and non-goals, see [`../../docs/mcp_tool_call_profile.md`](../../docs/mcp_tool_call_profile.md). For external reviewed profiles, see [`../../docs/mcp_profile_authoring.md`](../../docs/mcp_profile_authoring.md).
