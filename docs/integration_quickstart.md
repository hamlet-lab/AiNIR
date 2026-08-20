# 5-minute integration quick start

This is the shortest path from `pip install ainir` to putting an AiNIR preflight in front of a tool call.

AiNIR does **not** execute the tool. It evaluates a model-proposed call together with host-owned facts, then returns a bounded preflight decision. Your host still owns authorization, time-of-use revalidation, and execution.

## 1. Install

Requires Python 3.10+.

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install ainir
```

### Windows PowerShell

```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
python -m pip install ainir
```

If an older or custom resolver refuses the RC prerelease, use `python -m pip install --pre ainir`.

You can confirm the package is alive with:

```bash
ainir demo
```

## 2. Put AiNIR in front of a completed function call

The example below uses AiNIR's bundled reviewed, read-only `workspace.read_text` profile. It models the point where a host has already observed a completed OpenAI-style function-call artifact but has **not** executed the tool yet.

Create `ainir_preflight.py`:

```python
from ainir.openai_function_tool_adapter import bundled_openai_function_tool_adapter

# Model/API-produced proposal. This is a claim, not trusted host state.
tool_definition = {
    "type": "function",
    "name": "workspace.read_text",
    "description": "Read UTF-8 text from one file within the host-authorized workspace scope.",
    "parameters": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["path"],
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 4096}
        },
    },
    "strict": True,
}

function_call = {
    "type": "function_call",
    "id": "fc_example_read_1",
    "call_id": "call_example_read_1",
    "name": "workspace.read_text",
    "arguments": '{"path":"docs/README.md"}',
    "status": "completed",
}

# Host-observed binding for the completed response artifact.
host_binding = {
    "response_id": "resp_example_read_1",
    "response_status": "completed",
    "output_index": 0,
}

# Trusted host facts. In a real system these must come from your own auth,
# authorization, scope-resolution, consent, and transaction systems — never
# from model output.
host_input = {
    "host_id": "host.reference",
    "actor_id": "human.user",
    "evaluation_time": "2026-08-10T00:00:00Z",
    "server_id": "mcp.server.workspace.reference",
    "server_origin": "mcp+stdio://workspace.reference",
    "authorization_audience": "mcp.server.workspace.reference",
    "authenticated": True,
    "schema_validator_id": "host.schema.v1",
    "schema_validation_status": "passed",
    "capability_grants": ["cap.resource.read"],
    "resource_scope_ids": ["scope.workspace.docs"],
    "resource_resolution_status": "passed",
    "symlinks_resolved": True,
    "consent_decision": "approved",
    "consent_issued_at": "2026-08-09T23:59:00Z",
    "consent_valid_until": "2026-08-10T00:05:00Z",
    "transaction_status": None,
    "rollback_available": None,
    "rollback_plan_sha256": None,
}

with bundled_openai_function_tool_adapter() as adapter:
    preflight = adapter.assess(
        tool_definition,
        function_call,
        host_binding,
        host_input,
    )

print("status:", preflight["overall_status"])
print("host handoff allowed:", preflight["host_handoff_allowed"])

if preflight["overall_status"] == "passed":
    # This is where YOUR host may consider the next step.
    # Revalidate authorization/resource identity at time of use before any
    # real execution. AiNIR has not executed anything here.
    pass
```

Run it:

```bash
python ainir_preflight.py
```

For this reviewed read-only example the expected result is:

```text
status: passed
host handoff allowed: True
```

The repository also keeps the executable reference version at [`../examples/integration_quickstart.py`](../examples/integration_quickstart.py).

## 3. What belongs to the model, and what belongs to the host?

Keep this boundary explicit:

```text
model / API output
  └─ proposed function/tool call
            ↓
trusted host systems
  ├─ authentication
  ├─ authorization / capability grants
  ├─ resource identity + scope
  ├─ consent
  └─ transaction / rollback state
            ↓
        AiNIR preflight
       ↙             ↘
 passed/review      refused/invalid
       ↓
 host revalidates at time of use
       ↓
 host decides whether to execute
```

A `passed` result is **not** a command to execute. It means the proposal satisfied the reviewed AiNIR profile and host bindings supplied for that preflight. The host remains responsible for enforcing the real operation.

## 4. Make it yours

The bundled example is intentionally closed-world. Your own tool is not automatically trusted just because its JSON looks similar.

For an MCP-style tool, start by creating a reviewed profile skeleton:

```bash
ainir mcp init profiles/my-tool --profile-id my.tool.v1 --tool-name my_tool
```

Then validate its semantics and conformance cases before using it for preflight. See [`mcp_profile_authoring.md`](mcp_profile_authoring.md) and [`mcp_tool_call_profile.md`](mcp_tool_call_profile.md).

Once you have a reviewed profile, the Python adapter accepts it explicitly:

```python
with bundled_openai_function_tool_adapter(profile_source="profiles/my-tool/profile.yaml") as adapter:
    preflight = adapter.assess(tool_definition, function_call, host_binding, host_input)
```

That is the intended RC integration model: **AiNIR supplies the Trust Gate machinery; your host supplies trustworthy facts and remains the execution authority.**
