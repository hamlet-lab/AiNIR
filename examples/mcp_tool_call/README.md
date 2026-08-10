# MCP tool-call preflight example

This example is deliberately offline. AiNIR reads a reviewed tool descriptor,
a proposed `tools/call` request, host-observed transport bindings, and a
host-owned context. It emits a semantic assessment but never contacts the MCP
server or executes the tool.

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
  --out-dir /tmp/ainir_mcp_assessment

ainir mcp conformance --out-dir /tmp/ainir_mcp_conformance
```

A passing assessment is not proof that the server or tool is safe. The host
must revalidate authorization, resolve resource identity and scope, preserve
human control, and execute outside AiNIR core.
