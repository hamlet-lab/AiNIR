"""Five-minute AiNIR integration example.

This example uses the bundled reviewed read-only MCP profile and a completed
OpenAI-style function call. It performs preflight only; it never executes the
tool or calls the OpenAI API.
"""
from __future__ import annotations

from ainir.openai_function_tool_adapter import bundled_openai_function_tool_adapter


TOOL_DEFINITION = {
    "type": "function",
    "name": "workspace.read_text",
    "description": "Read UTF-8 text from one file within the host-authorized workspace scope.",
    "parameters": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["path"],
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096,
            }
        },
    },
    "strict": True,
}

FUNCTION_CALL = {
    "type": "function_call",
    "id": "fc_quickstart_read_1",
    "call_id": "call_quickstart_read_1",
    "name": "workspace.read_text",
    "arguments": '{"path":"docs/README.md"}',
    "status": "completed",
}

HOST_BINDING = {
    "response_id": "resp_quickstart_read_1",
    "response_status": "completed",
    "output_index": 0,
}

# These values are host-owned facts. In a real integration, populate them from
# your authentication, authorization, scope-resolution, consent, and transaction
# systems rather than from model output.
HOST_INPUT = {
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


def main() -> int:
    with bundled_openai_function_tool_adapter() as adapter:
        preflight = adapter.assess(
            TOOL_DEFINITION,
            FUNCTION_CALL,
            HOST_BINDING,
            HOST_INPUT,
        )

    print(f"AiNIR preflight: {preflight['overall_status']}")
    print(f"host_handoff_allowed: {preflight['host_handoff_allowed']}")

    # AiNIR never performs the tool execution here. The host must revalidate
    # authorization/resource identity at time of use before doing anything real.
    assert preflight["execution_performed"] is False
    assert preflight["openai_api_called"] is False
    assert preflight["tool_output_submitted"] is False

    return 0 if preflight["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
