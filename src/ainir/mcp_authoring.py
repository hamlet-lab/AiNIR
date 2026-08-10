"""Reviewed-template authoring helpers for external MCP preflight profiles.

The scaffold is deliberately narrow: it emits one read-only workspace tool
using AiNIR's already reviewed effect/capability vocabulary.  It does not infer
semantics, contact an MCP server, or mark arbitrary contributor changes as
reviewed.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

import yaml

from .canonical import sha256_json
from .contracts import (
    MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT,
    MCP_TOOL_CALL_CONFORMANCE_PACK_KIND,
    MCP_TOOL_CALL_PROFILE_CONTRACT,
    MCP_TOOL_CALL_PROFILE_KIND,
)
from .mcp_conformance import (
    mcp_conformance_pack_projection,
    load_mcp_conformance_pack,
    validate_mcp_conformance_pack,
)
from .mcp_tool_call import (
    load_mcp_tool_call_profile,
    mcp_tool_call_profile_projection,
    validate_mcp_tool_call_profile,
)

_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:@/+\-]{1,200}$")


class MCPProfileAuthoringError(ValueError):
    """Raised when the bounded profile scaffold cannot be created safely."""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _ensure_empty_target(directory: Path) -> None:
    if directory.exists() and any(directory.iterdir()):
        raise MCPProfileAuthoringError(f"target directory is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)


def initialize_mcp_profile(
    directory: str | Path,
    *,
    profile_id: str,
    tool_name: str,
    server_id: str | None = None,
    server_origin: str | None = None,
    authorization_audience: str | None = None,
) -> tuple[Path, Path]:
    """Create a fixed-semantics read-only MCP profile and four-case pack.

    Only identity fields are configurable.  The generated tool remains a
    read-only workspace-path operation with explicit per-call consent.
    """

    if not isinstance(profile_id, str) or not _PROFILE_ID_RE.fullmatch(profile_id):
        raise MCPProfileAuthoringError("profile_id must match ^[a-z][a-z0-9_.-]{2,127}$")
    if not isinstance(tool_name, str) or not _TOOL_NAME_RE.fullmatch(tool_name):
        raise MCPProfileAuthoringError("tool_name must be a bounded MCP tool name")
    server_id = server_id or f"host.{profile_id}"
    server_origin = server_origin or f"host+local://{profile_id}"
    authorization_audience = authorization_audience or server_id
    for label, value in (
        ("server_id", server_id),
        ("server_origin", server_origin),
        ("authorization_audience", authorization_audience),
    ):
        if not isinstance(value, str) or not _SAFE_TOKEN_RE.fullmatch(value):
            raise MCPProfileAuthoringError(f"{label} must be a bounded host token")

    root = Path(directory)
    _ensure_empty_target(root)

    descriptor = {
        "name": tool_name,
        "title": "Read host-authorized workspace text",
        "description": "Read UTF-8 text from one file within the host-authorized workspace scope.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 4096},
            },
        },
        "outputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["text"],
            "properties": {"text": {"type": "string"}},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "execution": {"taskSupport": "forbidden"},
    }
    descriptor_rel = f"descriptors/{tool_name}.json"
    descriptor_path = root / descriptor_rel
    _write_json(descriptor_path, descriptor)

    profile: dict[str, Any] = {
        "kind": MCP_TOOL_CALL_PROFILE_KIND,
        "version": MCP_TOOL_CALL_PROFILE_CONTRACT,
        "profile_id": profile_id,
        "profile_version": "1.0",
        "display_name": f"AiNIR reviewed read-only template: {tool_name}",
        "description": "Fixed-semantics contributor scaffold. AiNIR never executes this tool.",
        "status": "reviewed",
        "protocol_versions": ["2026-07-28"],
        "policies": {
            "unknown_tool": "refuse",
            "tool_descriptions_are_evidence": False,
            "tool_annotations_are_evidence": False,
            "model_output_is_evidence": False,
            "ainir_executes_actions": False,
            "host_executes_actions": True,
            "raw_credentials_in_arguments": "refuse",
            "task_execution": "refuse",
            "consent_mode": "explicit_per_call",
        },
        "tools": [{
            "name": tool_name,
            "server_id": server_id,
            "server_origin": server_origin,
            "authorization_audience": authorization_audience,
            "descriptor": descriptor_rel,
            "descriptor_sha256": sha256_json(descriptor),
            "input_schema_sha256": sha256_json(descriptor["inputSchema"]),
            "output_schema_sha256": sha256_json(descriptor["outputSchema"]),
            "effects": ["effect.resource.read"],
            "capabilities": ["cap.resource.read"],
            "risk_class": "read_only",
            "mutating": False,
            "destructive": False,
            "idempotent": True,
            "resource_bindings": [{
                "pointer": "/path",
                "resource_type": "workspace_path",
                "permission": "read",
            }],
            "transaction_required": False,
            "rollback_required": False,
            "max_arguments_bytes": 8192,
            "required_host_checks": [
                "authorization_binding",
                "explicit_consent",
                "resource_resolution",
                "schema_validation",
            ],
            "decision_mode": "allow",
        }],
        "production_runtime_ready": False,
    }
    profile["profile_sha256"] = sha256_json(mcp_tool_call_profile_projection(profile))
    profile_path = root / "profile.yaml"
    _write_yaml(profile_path, profile)

    safe_call = {
        "jsonrpc": "2.0",
        "id": "authoring-safe-read",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": {"path": "docs/README.md"}, "_meta": {"client": "ainir-profile-authoring"}},
    }
    traversal_call = deepcopy(safe_call)
    traversal_call["id"] = "authoring-path-traversal"
    traversal_call["params"]["arguments"] = {"path": "../secrets.txt"}
    transport = {"protocol_version": "2026-07-28", "method_header": "tools/call", "name_header": tool_name}
    host_input = {
        "host_id": "host.profile-authoring",
        "actor_id": "human.reviewer",
        "evaluation_time": "2026-08-10T00:00:00Z",
        "server_id": server_id,
        "server_origin": server_origin,
        "authorization_audience": authorization_audience,
        "authenticated": True,
        "schema_validator_id": "host.schema-validator.v1",
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
    missing_consent = deepcopy(host_input)
    missing_consent["consent_decision"] = "denied"
    tampered_descriptor = deepcopy(descriptor)
    tampered_descriptor["title"] = "Unreviewed descriptor mutation"

    fixtures = root / "fixtures"
    _write_json(fixtures / "safe_call.json", safe_call)
    _write_json(fixtures / "traversal_call.json", traversal_call)
    _write_json(fixtures / "transport.json", transport)
    _write_json(fixtures / "host_input.json", host_input)
    _write_json(fixtures / "missing_consent_host_input.json", missing_consent)
    _write_json(fixtures / "tampered_descriptor.json", tampered_descriptor)

    def fixture_case(case_id: str, category: str, call: str, host: str, descriptor_file: str, expected: str, failed: list[str]) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "category": category,
            "fixtures": {
                "descriptor": descriptor_file,
                "call": call,
                "transport": "fixtures/transport.json",
                "host_input": host,
            },
            "expected_status": expected,
            "required_failed_checks": failed,
            "required_host_actions": ["execute_outside_ainir_core"] if expected == "passed" else ["do_not_execute"],
            "notes": "Generated by the fixed-semantics AiNIR MCP profile scaffold.",
        }

    pack: dict[str, Any] = {
        "kind": MCP_TOOL_CALL_CONFORMANCE_PACK_KIND,
        "version": MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT,
        "pack_id": f"{profile_id}.conformance",
        "profile_id": profile_id,
        "cases": [
            fixture_case("safe_read_passed", "positive", "fixtures/safe_call.json", "fixtures/host_input.json", descriptor_rel, "passed", []),
            fixture_case("path_traversal_refused", "negative", "fixtures/traversal_call.json", "fixtures/host_input.json", descriptor_rel, "refused", ["resources.normalized"]),
            fixture_case("denied_consent_refused", "negative", "fixtures/safe_call.json", "fixtures/missing_consent_host_input.json", descriptor_rel, "refused", ["host.consent.decision"]),
            fixture_case("descriptor_mutation_refused", "mutation", "fixtures/safe_call.json", "fixtures/host_input.json", "fixtures/tampered_descriptor.json", "refused", ["tool.descriptor_sha256"]),
        ],
        "production_runtime_ready": False,
    }
    pack["pack_sha256"] = sha256_json(mcp_conformance_pack_projection(pack))
    pack_path = root / "cases.yaml"
    _write_yaml(pack_path, pack)

    readme = f"""# {profile_id}\n\nThis directory was created from AiNIR's fixed-semantics read-only MCP profile template.\n\n- Tool: `{tool_name}`\n- AiNIR does not execute the tool.\n- Descriptions and annotations are not evidence.\n- Changing effects, capabilities, risk class, or descriptor semantics requires independent review and new conformance evidence.\n\nValidate and run:\n\n```bash\nainir mcp profile profile.yaml --json\nainir mcp conformance --profile profile.yaml --cases cases.yaml --json\n```\n"""
    (root / "README.md").write_text(readme, encoding="utf-8")

    loaded = load_mcp_tool_call_profile(profile_path)
    if not validate_mcp_tool_call_profile(loaded).valid:
        raise MCPProfileAuthoringError("generated MCP profile failed validation")
    loaded_pack = load_mcp_conformance_pack(pack_path)
    failed = [
        item for item in validate_mcp_conformance_pack(
            loaded_pack,
            expected_profile_id=profile_id,
            profile_root=root,
            allow_scenarios=False,
        )
        if item.get("status") != "passed"
    ]
    if failed:
        raise MCPProfileAuthoringError("generated MCP conformance pack failed validation: " + ", ".join(str(item.get("check")) for item in failed[:8]))
    return profile_path, pack_path


__all__ = ["MCPProfileAuthoringError", "initialize_mcp_profile"]
