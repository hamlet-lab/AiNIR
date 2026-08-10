"""P7 readiness check for external MCP authoring and OpenAI function-call preflight.

The check is deterministic and local. It does not import the OpenAI SDK, call
an API, submit tool outputs, open an MCP transport, or execute a tool.
"""
from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
from typing import Any

from .contracts import artifact_contract_manifest
from .mcp_authoring import initialize_mcp_profile
from .mcp_conformance import run_mcp_conformance
from .mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    load_json_mapping,
    materialized_mcp_profile_source,
)
from .openai_function_tool_adapter import (
    HostOwnedOpenAIFunctionToolAdapter,
    OpenAIFunctionToolError,
    build_openai_function_call_binding,
    build_openai_function_tool_preflight,
    validate_openai_function_call_binding,
    validate_openai_function_tool_preflight,
    write_openai_function_artifact,
)
from .registry_provenance import registry_snapshot

EXPECTED_P6_REGISTRY_HASH = "sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a"
_REQUIRED_CONTRACTS = {
    "openai_function_call_binding",
    "openai_function_tool_preflight",
}


def _check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "passed" if passed else "failed", **details}


def _safe_inputs(profile):
    descriptor = load_json_mapping(
        profile.root / "descriptors/workspace.read_text.json",
        label="reviewed MCP tool descriptor",
    )
    tool_definition = {
        "type": "function",
        "name": "workspace.read_text",
        "description": descriptor.get("description"),
        "parameters": descriptor.get("inputSchema"),
        "strict": True,
    }
    function_call = {
        "type": "function_call",
        "id": "fc_p7_readiness_1",
        "call_id": "call_p7_readiness_1",
        "name": "workspace.read_text",
        "arguments": '{"path":"docs/README.md"}',
        "status": "completed",
    }
    host_binding = {
        "response_id": "resp_p7_readiness_1",
        "response_status": "completed",
        "output_index": 0,
    }
    host_input = {
        "host_id": "host.p7-readiness",
        "actor_id": "human.reviewer",
        "evaluation_time": "2026-08-10T00:00:00Z",
        "server_id": "mcp.server.workspace.reference",
        "server_origin": "mcp+stdio://workspace.reference",
        "authorization_audience": "mcp.server.workspace.reference",
        "authenticated": True,
        "schema_validator_id": "host.schema-validator.p7.v1",
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
    return descriptor, tool_definition, function_call, host_binding, host_input


def run_openai_function_tool_adapter_check(out_dir: str | Path) -> dict[str, Any]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    contracts = artifact_contract_manifest().get("contracts", {})
    checks.append(_check(
        "two_openai_host_adapter_contracts_present",
        _REQUIRED_CONTRACTS.issubset(set(contracts)),
        missing=sorted(_REQUIRED_CONTRACTS - set(contracts)),
    ))

    scaffold_root = output / "generated-mcp-profile"
    profile_path, pack_path = initialize_mcp_profile(
        scaffold_root,
        profile_id="ainir.p7.readiness.readonly.v1",
        tool_name="workspace.p7_read",
        server_id="mcp.server.p7.readiness",
        server_origin="mcp+local://p7.readiness",
        authorization_audience="mcp.server.p7.readiness",
    )
    scaffold_first = run_mcp_conformance(
        profile_path,
        pack_source=pack_path,
        out_dir=output / "scaffold-conformance-first",
    )
    scaffold_second = run_mcp_conformance(
        profile_path,
        pack_source=pack_path,
        out_dir=output / "scaffold-conformance-second",
    )
    checks.append(_check(
        "external_profile_scaffold_four_cases",
        scaffold_first.get("overall_status") == "passed"
        and scaffold_first.get("case_count") == 4
        and scaffold_first.get("passed") == 4
        and scaffold_first.get("failed") == 0
        and scaffold_first.get("report_sha256") == scaffold_second.get("report_sha256")
        and scaffold_first.get("execution_performed") is False,
        case_count=scaffold_first.get("case_count"),
        passed_cases=scaffold_first.get("passed"),
        report_sha256=scaffold_first.get("report_sha256"),
    ))

    with materialized_mcp_profile_source(BUILTIN_MCP_PROFILE_ID) as profile:
        _descriptor, tool_definition, function_call, host_binding, host_input = _safe_inputs(profile)
        binding, envelope = build_openai_function_call_binding(
            profile, tool_definition, function_call, host_binding
        )
        preflight = build_openai_function_tool_preflight(
            profile, tool_definition, function_call, host_binding, host_input
        )
        binding_second, envelope_second = build_openai_function_call_binding(
            profile, tool_definition, function_call, host_binding
        )
        preflight_second = build_openai_function_tool_preflight(
            profile, tool_definition, function_call, host_binding, host_input
        )
        write_openai_function_artifact(output / "openai_function_call_binding.json", binding)
        write_openai_function_artifact(output / "mcp_tool_call_envelope.json", envelope)
        write_openai_function_artifact(output / "openai_function_tool_preflight.json", preflight)

        checks.append(_check(
            "completed_function_call_binding_valid_and_deterministic",
            validate_openai_function_call_binding(binding).valid
            and binding == binding_second
            and envelope == envelope_second
            and binding.get("mcp_envelope_sha256") == envelope.get("envelope_sha256")
            and binding.get("execution_performed") is False
            and binding.get("openai_api_called") is False,
            binding_id=binding.get("binding_id"),
            envelope_id=envelope.get("envelope_id"),
        ))
        checks.append(_check(
            "safe_function_call_preflight_passes_without_execution",
            validate_openai_function_tool_preflight(preflight).valid
            and preflight == preflight_second
            and preflight.get("overall_status") == "passed"
            and preflight.get("host_handoff_allowed") is True
            and preflight.get("execution_performed") is False
            and preflight.get("openai_api_called") is False
            and preflight.get("tool_output_submitted") is False
            and preflight.get("credentials_processed") is False
            and preflight.get("production_runtime_ready") is False,
            preflight_id=preflight.get("preflight_id"),
            overall_status=preflight.get("overall_status"),
        ))

        strict_false = deepcopy(tool_definition)
        strict_false["strict"] = False
        strict_blocked = False
        try:
            build_openai_function_call_binding(profile, strict_false, function_call, host_binding)
        except OpenAIFunctionToolError:
            strict_blocked = True
        checks.append(_check("non_strict_tool_definition_refused", strict_blocked))

        incomplete = deepcopy(function_call)
        incomplete["status"] = "in_progress"
        incomplete_blocked = False
        try:
            build_openai_function_call_binding(profile, tool_definition, incomplete, host_binding)
        except OpenAIFunctionToolError:
            incomplete_blocked = True
        checks.append(_check("incomplete_function_call_refused", incomplete_blocked))

        credential_call = deepcopy(function_call)
        credential_call["arguments"] = json.dumps(
            {"path": "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefgh.ijklmnop"},
            separators=(",", ":"),
        )
        credential_preflight = build_openai_function_tool_preflight(
            profile, tool_definition, credential_call, host_binding, host_input
        )
        failed_checks = {
            str(item.get("check"))
            for item in credential_preflight.get("mcp_assessment", {}).get("checks", [])
            if isinstance(item, dict) and item.get("status") == "failed"
        }
        checks.append(_check(
            "credential_like_argument_value_refused",
            credential_preflight.get("overall_status") == "refused"
            and "arguments.sensitive_paths" in failed_checks
            and credential_preflight.get("host_handoff_allowed") is False
            and credential_preflight.get("execution_performed") is False,
            failed_checks=sorted(failed_checks),
        ))

        adapter = HostOwnedOpenAIFunctionToolAdapter(profile)
        forbidden_methods = (
            "execute", "send", "connect", "request", "open_transport", "authorize",
            "create_response", "submit_tool_output", "responses", "client",
        )
        checks.append(_check(
            "host_adapter_has_no_api_transport_execution_surface",
            not any(hasattr(adapter, name) for name in forbidden_methods),
            forbidden_methods_present=[name for name in forbidden_methods if hasattr(adapter, name)],
        ))

    source = inspect.getsource(__import__("ainir.openai_function_tool_adapter", fromlist=["*"]))
    forbidden_tokens = (
        "import openai", "from openai", "requests.", "httpx.", "urllib.request",
        "socket.", "subprocess.", "os.system(", "shell=True",
    )
    checks.append(_check(
        "adapter_source_contains_no_network_or_execution_primitive",
        not any(token in source for token in forbidden_tokens),
        forbidden_tokens_present=[token for token in forbidden_tokens if token in source],
    ))

    current_hash = registry_snapshot().get("combined_sha256")
    checks.append(_check(
        "p6_registry_hash_preserved",
        current_hash == EXPECTED_P6_REGISTRY_HASH,
        expected=EXPECTED_P6_REGISTRY_HASH,
        actual=current_hash,
    ))

    failed = [item for item in checks if item["status"] != "passed"]
    report = {
        "kind": "AiNIROpenAIFunctionToolAdapterReadinessReport",
        "version": "ainir.openai-function-tool-adapter-readiness-report.v1",
        "overall_status": "passed" if not failed else "failed",
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "external_profile_case_count": scaffold_first.get("case_count"),
        "openai_api_called": False,
        "tool_output_submitted": False,
        "execution_performed": False,
        "network_access_used": False,
        "mcp_transport_opened": False,
        "trust_gate_override_enabled": False,
        "evidence_ledger_promotion_enabled": False,
        "production_runtime_ready": False,
        "checks": checks,
        "output_dir": str(output.resolve()),
    }
    (output / "openai_function_tool_adapter_readiness_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


__all__ = ["EXPECTED_P6_REGISTRY_HASH", "run_openai_function_tool_adapter_check"]
