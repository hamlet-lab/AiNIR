# OpenAI function-tool host adapter example

This example contains host-observed JSON artifacts for one completed Responses API `function_call` item. AiNIR binds the item to the reviewed MCP profile and performs preflight assessment only. It does not call OpenAI, submit tool output, or execute the tool.

```bash
ainir openai function-tool normalize tool_definition.json function_call.json host_binding.json --json
ainir openai function-tool assess tool_definition.json function_call.json host_binding.json host_input.json --json
```
