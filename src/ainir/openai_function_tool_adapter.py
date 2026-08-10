"""Non-executing adapter for finalized OpenAI Responses function calls.

The adapter accepts host-observed JSON artifacts, binds them to an already
reviewed AiNIR MCP tool profile, and delegates to the P6 host-preflight
assessment.  It never calls the OpenAI API, imports the OpenAI SDK, submits tool
outputs, handles credentials, or executes the function.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterator, Mapping

from .canonical import (
    MAX_JSON_BYTES,
    canonical_json,
    json_depth,
    reject_duplicate_json_keys,
    sha256_json,
    sha256_text,
)
from .contracts import (
    OPENAI_FUNCTION_CALL_BINDING_CONTRACT,
    OPENAI_FUNCTION_CALL_BINDING_KIND,
    OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT,
    OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND,
)
from .mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    LoadedMCPToolCallProfile,
    MCPCheckReport,
    MCPToolCallError,
    assess_mcp_tool_call,
    build_mcp_host_context,
    build_mcp_tool_call_envelope,
    load_json_mapping,
    materialized_mcp_profile_source,
    validate_mcp_host_context,
    validate_mcp_tool_call_assessment,
    validate_mcp_tool_call_envelope,
    validate_mcp_tool_call_profile,
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_SAFE_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOOL_DEFINITION_KEYS = frozenset({"type", "name", "description", "parameters", "strict"})
_FUNCTION_CALL_KEYS = frozenset({"type", "id", "call_id", "name", "arguments", "status"})
_HOST_BINDING_KEYS = frozenset({"response_id", "response_status", "output_index"})
_BINDING_KEYS = frozenset({
    "kind", "version", "binding_id", "binding_sha256", "source_api",
    "response_id", "response_status", "output_item_id", "output_index",
    "call_id", "function_name", "source_item_status",
    "tool_definition_sha256", "function_call_item_sha256",
    "arguments_text_sha256", "arguments_sha256", "profile_id",
    "profile_sha256", "mcp_envelope_id", "mcp_envelope_sha256",
    "execution_performed", "openai_api_called", "credentials_processed",
    "production_runtime_ready",
})
_PREFLIGHT_KEYS = frozenset({
    "kind", "version", "preflight_id", "preflight_sha256", "overall_status",
    "host_handoff_allowed", "binding", "mcp_envelope", "mcp_host_context",
    "mcp_assessment", "required_host_actions", "execution_performed",
    "openai_api_called", "tool_output_submitted", "credentials_processed",
    "production_runtime_ready",
})


class OpenAIFunctionToolError(ValueError):
    """Raised when an OpenAI function-call artifact cannot be bound safely."""


def _check(name: str, passed: bool, expected: Any, actual: Any) -> dict[str, Any]:
    return {"check": name, "status": "passed" if passed else "failed", "expected": expected, "actual": actual}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_SAFE_ID_RE.fullmatch(value))


def _json_copy(value: Any) -> Any:
    try:
        text = canonical_json(value)
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            raise ValueError(f"canonical JSON exceeds {MAX_JSON_BYTES} bytes")
        copied = json.loads(text)
        json_depth(copied)
        return copied
    except (TypeError, ValueError, RecursionError, MemoryError) as exc:
        raise OpenAIFunctionToolError(f"value is not bounded canonical JSON: {exc}") from exc


def _parse_arguments_text(value: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, str):
        raise OpenAIFunctionToolError("function_call.arguments must be a finalized JSON string")
    raw = value.encode("utf-8")
    if len(raw) > MAX_JSON_BYTES:
        raise OpenAIFunctionToolError("function_call.arguments exceeds the bounded JSON size")
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=reject_duplicate_json_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(ValueError(f"non-finite JSON number {item!r} is forbidden")),
        )
        json_depth(parsed)
    except Exception as exc:
        raise OpenAIFunctionToolError(f"function_call.arguments is not bounded duplicate-key-free JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise OpenAIFunctionToolError("function_call.arguments root must decode to an object")
    return value, parsed


def _profile_tool_and_descriptor(profile: LoadedMCPToolCallProfile, tool_name: str) -> tuple[Mapping[str, Any], dict[str, Any]]:
    report = validate_mcp_tool_call_profile(profile)
    if not report.valid:
        raise OpenAIFunctionToolError("MCP tool-call profile failed validation")
    tools = [item for item in profile.data.get("tools", []) if isinstance(item, Mapping) and item.get("name") == tool_name]
    if len(tools) != 1:
        raise OpenAIFunctionToolError("function name is not uniquely present in the reviewed profile")
    tool = tools[0]
    relative = tool.get("descriptor")
    if not isinstance(relative, str) or not relative:
        raise OpenAIFunctionToolError("reviewed tool descriptor path is missing")
    path = (profile.root / relative).resolve()
    try:
        path.relative_to(profile.root.resolve())
    except ValueError as exc:
        raise OpenAIFunctionToolError("reviewed tool descriptor escapes the profile root") from exc
    descriptor = load_json_mapping(path, label="reviewed MCP tool descriptor")
    return tool, descriptor


def openai_function_call_binding_projection(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_copy(value) for key, value in binding.items() if key not in {"binding_id", "binding_sha256"}}


def openai_function_tool_preflight_projection(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_copy(value) for key, value in preflight.items() if key not in {"preflight_id", "preflight_sha256"}}


def build_openai_function_call_binding(
    profile: LoadedMCPToolCallProfile,
    tool_definition: Mapping[str, Any],
    function_call_item: Mapping[str, Any],
    host_binding: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind one finalized Responses function call to a reviewed P6 envelope."""

    tool_definition = _json_copy(dict(tool_definition))
    function_call_item = _json_copy(dict(function_call_item))
    host_binding = _json_copy(dict(host_binding))
    unknown_tool = sorted(set(tool_definition) - _TOOL_DEFINITION_KEYS)
    unknown_call = sorted(set(function_call_item) - _FUNCTION_CALL_KEYS)
    unknown_host = sorted(set(host_binding) - _HOST_BINDING_KEYS)
    if unknown_tool:
        raise OpenAIFunctionToolError(f"function tool definition contains unsupported fields: {unknown_tool}")
    if unknown_call:
        raise OpenAIFunctionToolError(f"function_call item contains unsupported fields: {unknown_call}")
    if unknown_host:
        raise OpenAIFunctionToolError(f"host binding contains unsupported fields: {unknown_host}")
    if tool_definition.get("type") != "function":
        raise OpenAIFunctionToolError("tool definition type must be function")
    name = tool_definition.get("name")
    if not isinstance(name, str) or not _SAFE_TOOL_NAME_RE.fullmatch(name):
        raise OpenAIFunctionToolError("tool definition name is invalid")
    if tool_definition.get("strict") is not True:
        raise OpenAIFunctionToolError("bounded adapter requires strict=true")
    description = tool_definition.get("description")
    if description is not None and not isinstance(description, str):
        raise OpenAIFunctionToolError("tool definition description must be a string or null")
    parameters = tool_definition.get("parameters")
    if not isinstance(parameters, Mapping):
        raise OpenAIFunctionToolError("tool definition parameters must be an object")
    if function_call_item.get("type") != "function_call":
        raise OpenAIFunctionToolError("source item type must be function_call")
    if function_call_item.get("status") != "completed":
        raise OpenAIFunctionToolError("only completed function_call items are accepted")
    if function_call_item.get("name") != name:
        raise OpenAIFunctionToolError("tool definition and function_call names differ")
    for field in ("id", "call_id"):
        if not _safe_id(function_call_item.get(field)):
            raise OpenAIFunctionToolError(f"function_call.{field} is not a bounded identifier")
    if host_binding.get("response_status") != "completed":
        raise OpenAIFunctionToolError("only completed Responses artifacts are accepted")
    if not _safe_id(host_binding.get("response_id")):
        raise OpenAIFunctionToolError("host binding response_id is invalid")
    output_index = host_binding.get("output_index")
    if isinstance(output_index, bool) or not isinstance(output_index, int) or output_index < 0:
        raise OpenAIFunctionToolError("host binding output_index must be a non-negative integer")

    arguments_text, arguments = _parse_arguments_text(function_call_item.get("arguments"))
    _tool, descriptor = _profile_tool_and_descriptor(profile, name)
    if canonical_json(parameters) != canonical_json(descriptor.get("inputSchema")):
        raise OpenAIFunctionToolError("OpenAI tool parameters do not match the reviewed profile input schema")
    protocol_versions = profile.data.get("protocol_versions")
    if not isinstance(protocol_versions, list) or not protocol_versions:
        raise OpenAIFunctionToolError("reviewed profile has no protocol version")
    protocol_version = sorted(str(item) for item in protocol_versions)[-1]
    tool_definition_sha256 = sha256_json(tool_definition)
    call_item_sha256 = sha256_json(function_call_item)
    call_request = {
        "jsonrpc": "2.0",
        "id": str(function_call_item["call_id"]),
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
            "_meta": {
                "ainir/source_api": "openai.responses",
                "ainir/response_id_sha256": sha256_text(str(host_binding["response_id"])),
                "ainir/output_item_id_sha256": sha256_text(str(function_call_item["id"])),
                "ainir/tool_definition_sha256": tool_definition_sha256,
                "ainir/function_call_item_sha256": call_item_sha256,
            },
        },
    }
    transport = {
        "protocol_version": protocol_version,
        "method_header": "tools/call",
        "name_header": name,
    }
    envelope = build_mcp_tool_call_envelope(profile, descriptor, call_request, transport)
    binding: dict[str, Any] = {
        "kind": OPENAI_FUNCTION_CALL_BINDING_KIND,
        "version": OPENAI_FUNCTION_CALL_BINDING_CONTRACT,
        "source_api": "openai.responses",
        "response_id": host_binding["response_id"],
        "response_status": host_binding["response_status"],
        "output_item_id": function_call_item["id"],
        "output_index": output_index,
        "call_id": function_call_item["call_id"],
        "function_name": name,
        "source_item_status": function_call_item["status"],
        "tool_definition_sha256": tool_definition_sha256,
        "function_call_item_sha256": call_item_sha256,
        "arguments_text_sha256": sha256_text(arguments_text),
        "arguments_sha256": envelope["arguments_sha256"],
        "profile_id": profile.profile_id,
        "profile_sha256": profile.data.get("profile_sha256"),
        "mcp_envelope_id": envelope["envelope_id"],
        "mcp_envelope_sha256": envelope["envelope_sha256"],
        "execution_performed": False,
        "openai_api_called": False,
        "credentials_processed": False,
        "production_runtime_ready": False,
    }
    digest = sha256_json(openai_function_call_binding_projection(binding))
    binding["binding_sha256"] = digest
    binding["binding_id"] = "ainir.openai.binding." + digest.removeprefix("sha256:")[:20]
    return binding, envelope


def validate_openai_function_call_binding(binding: Mapping[str, Any]) -> MCPCheckReport:
    checks: list[dict[str, Any]] = []
    checks.append(_check("binding.unknown_fields", not (set(binding) - _BINDING_KEYS), [], sorted(set(binding) - _BINDING_KEYS)))
    checks.append(_check("binding.kind", binding.get("kind") == OPENAI_FUNCTION_CALL_BINDING_KIND, OPENAI_FUNCTION_CALL_BINDING_KIND, binding.get("kind")))
    checks.append(_check("binding.version", binding.get("version") == OPENAI_FUNCTION_CALL_BINDING_CONTRACT, OPENAI_FUNCTION_CALL_BINDING_CONTRACT, binding.get("version")))
    expected_hash = sha256_json(openai_function_call_binding_projection(binding))
    checks.append(_check("binding.sha256", binding.get("binding_sha256") == expected_hash, expected_hash, binding.get("binding_sha256")))
    expected_id = "ainir.openai.binding." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("binding.id", binding.get("binding_id") == expected_id, expected_id, binding.get("binding_id")))
    checks.append(_check("binding.source_api", binding.get("source_api") == "openai.responses", "openai.responses", binding.get("source_api")))
    for field in ("response_id", "output_item_id", "call_id"):
        checks.append(_check(f"binding.{field}", _safe_id(binding.get(field)), "bounded identifier", binding.get(field)))
    checks.append(_check("binding.response_status", binding.get("response_status") == "completed", "completed", binding.get("response_status")))
    checks.append(_check("binding.source_item_status", binding.get("source_item_status") == "completed", "completed", binding.get("source_item_status")))
    checks.append(_check("binding.function_name", isinstance(binding.get("function_name"), str) and bool(_SAFE_TOOL_NAME_RE.fullmatch(str(binding.get("function_name")))), "bounded function name", binding.get("function_name")))
    output_index = binding.get("output_index")
    checks.append(_check("binding.output_index", isinstance(output_index, int) and not isinstance(output_index, bool) and output_index >= 0, "non-negative integer", output_index))
    for field in (
        "tool_definition_sha256", "function_call_item_sha256", "arguments_text_sha256",
        "arguments_sha256", "profile_sha256", "mcp_envelope_sha256",
    ):
        checks.append(_check(f"binding.{field}", _sha(binding.get(field)), "sha256:<64 lowercase hex>", binding.get(field)))
    expected_envelope_id = "ainir.mcp.envelope." + str(binding.get("mcp_envelope_sha256", "")).removeprefix("sha256:")[:20] if _sha(binding.get("mcp_envelope_sha256")) else None
    checks.append(_check("binding.mcp_envelope_id", binding.get("mcp_envelope_id") == expected_envelope_id, expected_envelope_id, binding.get("mcp_envelope_id")))
    checks.append(_check("binding.profile_id", isinstance(binding.get("profile_id"), str) and bool(_PROFILE_ID_RE.fullmatch(str(binding.get("profile_id")))), "bounded profile id", binding.get("profile_id")))
    for field in ("execution_performed", "openai_api_called", "credentials_processed", "production_runtime_ready"):
        checks.append(_check(f"binding.{field}", binding.get(field) is False, False, binding.get(field)))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        "AiNIROpenAIFunctionCallBindingValidationReport",
        "ainir.openai-function-call-binding-validation-report.v1",
        valid,
        tuple(checks),
        str(binding.get("binding_id")) if isinstance(binding.get("binding_id"), str) else None,
    )


def build_openai_function_tool_preflight(
    profile: LoadedMCPToolCallProfile,
    tool_definition: Mapping[str, Any],
    function_call_item: Mapping[str, Any],
    host_binding: Mapping[str, Any],
    host_input: Mapping[str, Any],
) -> dict[str, Any]:
    binding, envelope = build_openai_function_call_binding(profile, tool_definition, function_call_item, host_binding)
    context = build_mcp_host_context(envelope=envelope, **_json_copy(dict(host_input)))
    assessment = assess_mcp_tool_call(profile, envelope, context)
    preflight: dict[str, Any] = {
        "kind": OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND,
        "version": OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT,
        "overall_status": assessment.get("overall_status"),
        "host_handoff_allowed": assessment.get("host_handoff_allowed"),
        "binding": binding,
        "mcp_envelope": envelope,
        "mcp_host_context": context,
        "mcp_assessment": assessment,
        "required_host_actions": list(assessment.get("required_host_actions", [])),
        "execution_performed": False,
        "openai_api_called": False,
        "tool_output_submitted": False,
        "credentials_processed": False,
        "production_runtime_ready": False,
    }
    digest = sha256_json(openai_function_tool_preflight_projection(preflight))
    preflight["preflight_sha256"] = digest
    preflight["preflight_id"] = "ainir.openai.preflight." + digest.removeprefix("sha256:")[:20]
    return preflight


def validate_openai_function_tool_preflight(preflight: Mapping[str, Any]) -> MCPCheckReport:
    checks: list[dict[str, Any]] = []
    checks.append(_check("preflight.unknown_fields", not (set(preflight) - _PREFLIGHT_KEYS), [], sorted(set(preflight) - _PREFLIGHT_KEYS)))
    checks.append(_check("preflight.kind", preflight.get("kind") == OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND, OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND, preflight.get("kind")))
    checks.append(_check("preflight.version", preflight.get("version") == OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT, OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT, preflight.get("version")))
    expected_hash = sha256_json(openai_function_tool_preflight_projection(preflight))
    checks.append(_check("preflight.sha256", preflight.get("preflight_sha256") == expected_hash, expected_hash, preflight.get("preflight_sha256")))
    expected_id = "ainir.openai.preflight." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("preflight.id", preflight.get("preflight_id") == expected_id, expected_id, preflight.get("preflight_id")))
    binding = preflight.get("binding")
    envelope = preflight.get("mcp_envelope")
    context = preflight.get("mcp_host_context")
    assessment = preflight.get("mcp_assessment")
    binding_report = validate_openai_function_call_binding(binding) if isinstance(binding, Mapping) else None
    envelope_report = validate_mcp_tool_call_envelope(envelope) if isinstance(envelope, Mapping) else None
    context_report = validate_mcp_host_context(context) if isinstance(context, Mapping) else None
    assessment_report = validate_mcp_tool_call_assessment(assessment) if isinstance(assessment, Mapping) else None
    checks.append(_check("preflight.binding.valid", binding_report is not None and binding_report.valid, True, None if binding_report is None else binding_report.overall_status))
    checks.append(_check("preflight.envelope.valid", envelope_report is not None and envelope_report.valid, True, None if envelope_report is None else envelope_report.overall_status))
    checks.append(_check("preflight.context.valid", context_report is not None and context_report.valid, True, None if context_report is None else context_report.overall_status))
    checks.append(_check("preflight.assessment.valid", assessment_report is not None and assessment_report.valid, True, None if assessment_report is None else assessment_report.overall_status))
    if isinstance(binding, Mapping) and isinstance(envelope, Mapping):
        checks.append(_check("preflight.binding.envelope_hash", binding.get("mcp_envelope_sha256") == envelope.get("envelope_sha256"), envelope.get("envelope_sha256"), binding.get("mcp_envelope_sha256")))
        checks.append(_check("preflight.binding.envelope_id", binding.get("mcp_envelope_id") == envelope.get("envelope_id"), envelope.get("envelope_id"), binding.get("mcp_envelope_id")))
        checks.append(_check("preflight.binding.profile_id", binding.get("profile_id") == envelope.get("profile_id"), envelope.get("profile_id"), binding.get("profile_id")))
        checks.append(_check("preflight.binding.tool_name", binding.get("function_name") == envelope.get("tool_name"), envelope.get("tool_name"), binding.get("function_name")))
        checks.append(_check("preflight.binding.arguments_hash", binding.get("arguments_sha256") == envelope.get("arguments_sha256"), envelope.get("arguments_sha256"), binding.get("arguments_sha256")))
    if isinstance(envelope, Mapping) and isinstance(context, Mapping):
        consent = context.get("consent") if isinstance(context.get("consent"), Mapping) else {}
        checks.append(_check("preflight.context.envelope_binding", consent.get("envelope_sha256") == envelope.get("envelope_sha256"), envelope.get("envelope_sha256"), consent.get("envelope_sha256")))
    if isinstance(assessment, Mapping):
        checks.append(_check("preflight.status", preflight.get("overall_status") == assessment.get("overall_status"), assessment.get("overall_status"), preflight.get("overall_status")))
        checks.append(_check("preflight.handoff", preflight.get("host_handoff_allowed") == assessment.get("host_handoff_allowed"), assessment.get("host_handoff_allowed"), preflight.get("host_handoff_allowed")))
        checks.append(_check("preflight.actions", preflight.get("required_host_actions") == assessment.get("required_host_actions"), assessment.get("required_host_actions"), preflight.get("required_host_actions")))
        if isinstance(binding, Mapping):
            checks.append(_check("preflight.assessment.profile_id", assessment.get("profile_id") == binding.get("profile_id"), binding.get("profile_id"), assessment.get("profile_id")))
            checks.append(_check("preflight.assessment.profile_hash", assessment.get("profile_sha256") == binding.get("profile_sha256"), binding.get("profile_sha256"), assessment.get("profile_sha256")))
            checks.append(_check("preflight.assessment.tool_name", assessment.get("tool_name") == binding.get("function_name"), binding.get("function_name"), assessment.get("tool_name")))
        if isinstance(envelope, Mapping):
            checks.append(_check("preflight.assessment.envelope_id", assessment.get("envelope_id") == envelope.get("envelope_id"), envelope.get("envelope_id"), assessment.get("envelope_id")))
            checks.append(_check("preflight.assessment.envelope_hash", assessment.get("envelope_sha256") == envelope.get("envelope_sha256"), envelope.get("envelope_sha256"), assessment.get("envelope_sha256")))
        if isinstance(context, Mapping):
            checks.append(_check("preflight.assessment.context_id", assessment.get("context_id") == context.get("context_id"), context.get("context_id"), assessment.get("context_id")))
            checks.append(_check("preflight.assessment.context_hash", assessment.get("context_sha256") == context.get("context_sha256"), context.get("context_sha256"), assessment.get("context_sha256")))
    for field in ("execution_performed", "openai_api_called", "tool_output_submitted", "credentials_processed", "production_runtime_ready"):
        checks.append(_check(f"preflight.{field}", preflight.get(field) is False, False, preflight.get(field)))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        "AiNIROpenAIFunctionToolPreflightValidationReport",
        "ainir.openai-function-tool-preflight-validation-report.v1",
        valid,
        tuple(checks),
        str(preflight.get("preflight_id")) if isinstance(preflight.get("preflight_id"), str) else None,
    )


@dataclass(frozen=True)
class HostOwnedOpenAIFunctionToolAdapter:
    """Translate and assess finalized function calls without executing them."""

    profile: LoadedMCPToolCallProfile

    def normalize(
        self,
        tool_definition: Mapping[str, Any],
        function_call_item: Mapping[str, Any],
        host_binding: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return build_openai_function_call_binding(self.profile, tool_definition, function_call_item, host_binding)

    def assess(
        self,
        tool_definition: Mapping[str, Any],
        function_call_item: Mapping[str, Any],
        host_binding: Mapping[str, Any],
        host_input: Mapping[str, Any],
    ) -> dict[str, Any]:
        return build_openai_function_tool_preflight(self.profile, tool_definition, function_call_item, host_binding, host_input)


@contextmanager
def bundled_openai_function_tool_adapter(
    profile_source: str | Path = BUILTIN_MCP_PROFILE_ID,
) -> Iterator[HostOwnedOpenAIFunctionToolAdapter]:
    with materialized_mcp_profile_source(profile_source) as profile:
        yield HostOwnedOpenAIFunctionToolAdapter(profile)


def write_openai_function_artifact(path: str | Path, artifact: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "HostOwnedOpenAIFunctionToolAdapter",
    "OpenAIFunctionToolError",
    "build_openai_function_call_binding",
    "build_openai_function_tool_preflight",
    "bundled_openai_function_tool_adapter",
    "openai_function_call_binding_projection",
    "openai_function_tool_preflight_projection",
    "validate_openai_function_call_binding",
    "validate_openai_function_tool_preflight",
    "write_openai_function_artifact",
]
