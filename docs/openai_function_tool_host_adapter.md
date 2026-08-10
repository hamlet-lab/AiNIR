# OpenAI function-tool host adapter

P7 includes a non-executing reference adapter for a host that has already received a finalized OpenAI Responses `function_call` item.

The adapter converts host-observed JSON into the existing P6 MCP envelope and host-preflight assessment. It deliberately has no OpenAI SDK dependency and no API, transport, credential, tool-output, or execution method.

## Accepted inputs

The host supplies four local JSON artifacts:

1. a function tool definition with `type: function`, exact reviewed `parameters`, and `strict: true`;
2. a completed `function_call` item with bounded `id`, `call_id`, `name`, and finalized JSON-string `arguments`;
3. a completed response binding with response ID and output index;
4. the existing host-owned P6 context input for server identity, authorization audience, schema validation, exact capability grants, resource resolution, consent, and transaction state.

Only a function name and input schema already present in the selected reviewed MCP profile can be bound. The OpenAI description is not evidence and is not used to redefine the profile contract.

## Commands

```bash
ainir openai function-tool normalize \
  examples/openai_function_tool/tool_definition.json \
  examples/openai_function_tool/function_call.json \
  examples/openai_function_tool/host_binding.json \
  --out-dir /tmp/ainir-openai-binding \
  --json

ainir openai function-tool assess \
  examples/openai_function_tool/tool_definition.json \
  examples/openai_function_tool/function_call.json \
  examples/openai_function_tool/host_binding.json \
  examples/openai_function_tool/host_input.json \
  --out-dir /tmp/ainir-openai-preflight \
  --json
```

## Public artifacts

- `ainir.openai-function-call-binding.v1`
- `ainir.openai-function-tool-preflight.v1`

The binding records host-observed source IDs and hashes, exact arguments hashes, selected profile identity, and the resulting MCP envelope identity. It is a deterministic local binding, not cryptographic proof that an item originated from OpenAI; the host remains responsible for preserving and authenticating its source response records. The preflight cross-binds the binding, envelope, host context, and assessment so a separately valid nested artifact cannot be substituted and accepted after merely recomputing the outer hash.

## Fail-closed rules

The adapter refuses:

- `strict` omitted or false;
- an in-progress or otherwise non-completed function call;
- a non-completed response binding;
- tool-definition and call-name mismatch;
- reviewed input-schema drift;
- duplicate JSON argument keys;
- non-object or non-finite arguments;
- any source artifact or argument payload that exceeds the public JSON size or nesting bounds;
- unsupported top-level source fields;
- unknown tools;
- credential-like field names or values through the P6 assessment;
- any host context that fails P6 authorization, consent, capability, resource, transaction, or rollback checks.

## Meaning of `passed`

`passed` means only that the host may consider handoff after revalidating authorization and resource identity at the moment of use. It does not mean that AiNIR executed the function or submitted tool output.

Every artifact fixes the following values:

```text
openai_api_called: false
tool_output_submitted: false
execution_performed: false
credentials_processed: false
production_runtime_ready: false
```

## Non-goals

- OpenAI client construction or API calls;
- streaming event assembly;
- tool-output submission;
- retries, sessions, or response lifecycle ownership;
- hosted tools or built-in tools;
- credential storage or forwarding;
- execution, sandboxing, or host authorization replacement;
- automatic Trust Gate override or Evidence Ledger promotion.
