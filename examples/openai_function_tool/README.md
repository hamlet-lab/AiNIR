# OpenAI function-tool host adapter example

This example shows the same trust-boundary idea with an already-completed OpenAI Responses `function_call` artifact.

```text
OpenAI Responses output
    ↓ completed function_call JSON
host observes + binds exact artifacts
    ↓
AiNIR preflight assessment
    ↓
host decides whether any real tool execution may happen
```

The bundled function call is:

```json
{
  "type": "function_call",
  "name": "workspace.read_text",
  "arguments": "{\"path\":\"docs/README.md\"}",
  "status": "completed"
}
```

AiNIR does **not** call OpenAI, submit tool output, or execute `workspace.read_text`. The host supplies the already-observed tool definition, function-call item, host binding, and trusted host context; AiNIR normalizes and assesses that fixed input against the reviewed profile.

Run from the repository root:

```bash
ainir openai function-tool normalize \
  examples/openai_function_tool/tool_definition.json \
  examples/openai_function_tool/function_call.json \
  examples/openai_function_tool/host_binding.json \
  --json

ainir openai function-tool assess \
  examples/openai_function_tool/tool_definition.json \
  examples/openai_function_tool/function_call.json \
  examples/openai_function_tool/host_binding.json \
  examples/openai_function_tool/host_input.json \
  --json
```

The purpose of this adapter is not to claim that an OpenAI function call is trustworthy because it came from the API. **The model-produced call remains a proposal; host-observed identity, authorization, resource scope, consent, and other reviewed bindings remain separate inputs.**

For the precise adapter boundary, see [`../../docs/openai_function_tool_host_adapter.md`](../../docs/openai_function_tool_host_adapter.md).
