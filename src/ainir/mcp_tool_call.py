"""Consumer-neutral MCP tool-call semantic assessment.

This module does not implement an MCP client, server, transport, authorization
server, task runtime, or tool executor.  A host supplies the raw MCP tool
descriptor, proposed ``tools/call`` request, transport observations, and a
host-owned context.  AiNIR binds those inputs and emits a fail-closed semantic
assessment without performing the tool call.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import resources as importlib_resources
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
from typing import Any, Iterator, Mapping, Sequence

from .canonical import (
    canonical_json,
    json_depth,
    read_json_object_artifact,
    sha256_bytes,
    sha256_json,
)
from .contracts import (
    MCP_HOST_CONTEXT_CONTRACT,
    MCP_HOST_CONTEXT_KIND,
    MCP_TOOL_CALL_ASSESSMENT_CONTRACT,
    MCP_TOOL_CALL_ASSESSMENT_KIND,
    MCP_TOOL_CALL_ENVELOPE_CONTRACT,
    MCP_TOOL_CALL_ENVELOPE_KIND,
    MCP_TOOL_CALL_PROFILE_CONTRACT,
    MCP_TOOL_CALL_PROFILE_KIND,
)
from .core import MAX_YAML_BYTES, load_yaml_no_duplicate_keys

BUILTIN_MCP_PROFILE_ID = "ainir.mcp.reference.workspace.v1"
BUILTIN_MCP_PROFILE_PACKAGE = "ainir.mcp_profiles.reference_v1"
MCP_PROFILE_FILENAME = "profile.yaml"
MCP_CONFORMANCE_FILENAME = "cases.yaml"
SUPPORTED_MCP_PROTOCOL_VERSIONS = frozenset({"2025-11-25", "2026-07-28"})

MCP_EFFECT_VOCABULARY = frozenset({
    "effect.resource.read",
    "effect.resource.write",
    "effect.resource.delete",
    "effect.network.outbound",
    "effect.credentials.access",
    "effect.financial.charge",
    "effect.account.modify",
    "effect.compute.local",
})
MCP_CAPABILITY_VOCABULARY = frozenset({
    "cap.resource.read",
    "cap.resource.write",
    "cap.resource.delete",
    "cap.network.outbound",
    "cap.credentials.access",
    "cap.financial.charge",
    "cap.account.modify",
    "cap.compute.local",
})
MCP_RISK_CLASSES = frozenset({
    "read_only",
    "state_change",
    "destructive",
    "network",
    "credential_sensitive",
    "financial",
    "account_change",
})
MCP_PASSED_HOST_ACTIONS = tuple(sorted({
    "execute_outside_ainir_core",
    "preserve_assessment_for_audit",
    "resolve_resource_identity_and_scope_at_execution",
    "revalidate_authorization_at_execution",
}))
MCP_REVIEW_HOST_ACTIONS = tuple(sorted({
    "do_not_execute",
    "obtain_final_destructive_action_confirmation",
    "preserve_assessment_for_audit",
    "reassess_after_final_confirmation",
}))
MCP_REFUSED_HOST_ACTIONS = tuple(sorted({
    "do_not_execute",
    "preserve_assessment_for_audit",
    "review_failed_checks",
}))

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:@/+\-]{1,200}$")
_SAFE_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_SENSITIVE_ARGUMENT_TOKEN_RE = re.compile(
    r"(?:^|[_\-.])(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|credential|private[_-]?key|bearer)(?:$|[_\-.])",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+\-/=]{16,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|gh[pousr])[-_][A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)"
        r"\s*[:=]\s*[^\s]{8,}",
        re.IGNORECASE,
    ),
)
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

_PROFILE_TOP_KEYS = frozenset({
    "kind", "version", "profile_id", "profile_version", "display_name",
    "description", "status", "protocol_versions", "policies", "tools",
    "profile_sha256", "production_runtime_ready",
})
_PROFILE_POLICY_KEYS = frozenset({
    "unknown_tool", "tool_descriptions_are_evidence", "tool_annotations_are_evidence",
    "model_output_is_evidence", "ainir_executes_actions", "host_executes_actions",
    "raw_credentials_in_arguments", "task_execution", "consent_mode",
})
_PROFILE_TOOL_KEYS = frozenset({
    "name", "server_id", "server_origin", "authorization_audience", "descriptor",
    "descriptor_sha256", "input_schema_sha256", "output_schema_sha256", "effects",
    "capabilities", "risk_class", "mutating", "destructive", "idempotent",
    "resource_bindings", "transaction_required", "rollback_required",
    "max_arguments_bytes", "required_host_checks", "decision_mode",
})
_RESOURCE_BINDING_KEYS = frozenset({"pointer", "resource_type", "permission"})
_ENVELOPE_METADATA_KEYS = frozenset({"title", "description_sha256", "annotations", "execution", "client_meta_sha256"})
_ENVELOPE_TRANSPORT_KEYS = frozenset({"method_header", "name_header"})
_ENVELOPE_RESOURCE_KEYS = frozenset({
    "pointer", "resource_type", "permission", "raw_value", "normalized_value",
    "status", "error",
})
_NORMALIZATION_FINDING_KEYS = frozenset({"rule", "severity", "target", "message"})
_ENVELOPE_TOP_KEYS = frozenset({
    "kind", "version", "envelope_id", "envelope_sha256", "profile_id",
    "protocol_version", "jsonrpc_request_id", "method", "tool_name",
    "descriptor_sha256", "input_schema_sha256", "output_schema_sha256",
    "arguments", "arguments_sha256", "arguments_size", "untrusted_metadata",
    "transport_observations", "requested_resources", "requested_resources_sha256",
    "sensitive_argument_paths", "task_requested", "mrtr_input_responses_present",
    "normalization_findings", "production_runtime_ready",
})
_HOST_SERVER_BINDING_KEYS = frozenset({
    "server_id", "server_origin", "authorization_audience", "authenticated",
    "protocol_version", "method_header", "name_header",
})
_HOST_SCHEMA_VALIDATION_KEYS = frozenset({
    "status", "validator_id", "input_schema_sha256", "arguments_sha256",
})
_HOST_RESOURCE_RESOLUTION_KEYS = frozenset({
    "status", "resolver_id", "requested_resources_sha256", "scope_ids",
    "symlinks_resolved",
})
_HOST_CONSENT_KEYS = frozenset({
    "decision", "actor_id", "envelope_sha256", "arguments_sha256",
    "requested_resources_sha256", "issued_at", "valid_until", "consent_id",
})
_HOST_TRANSACTION_KEYS = frozenset({
    "transaction_id", "status", "envelope_sha256", "requested_resources_sha256",
    "rollback_available", "rollback_plan_sha256",
})
_HOST_CONTEXT_TOP_KEYS = frozenset({
    "kind", "version", "context_id", "context_sha256", "host_id", "actor_id",
    "evaluation_time", "server_binding", "schema_validation", "capability_grants",
    "resource_resolution", "consent", "transaction", "production_runtime_ready",
})
_ASSESSMENT_CHECK_KEYS = frozenset({"check", "status", "expected", "actual"})
_ASSESSMENT_TOP_KEYS = frozenset({
    "kind", "version", "assessment_id", "assessment_sha256", "overall_status",
    "host_handoff_allowed", "execution_performed", "profile_id", "profile_sha256",
    "envelope_id", "envelope_sha256", "context_id", "context_sha256", "tool_name",
    "risk_class", "effects", "capabilities", "checks", "required_host_actions",
    "production_runtime_ready",
})


class MCPToolCallError(ValueError):
    """Raised when an MCP profile or proposed call cannot be safely processed."""


@dataclass(frozen=True)
class MCPCheckReport:
    kind: str
    version: str
    valid: bool
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    subject_id: str | None = None
    production_runtime_ready: bool = False

    @property
    def overall_status(self) -> str:
        return "passed" if self.valid else "failed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "version": self.version,
            "overall_status": self.overall_status,
            "valid": self.valid,
            "subject_id": self.subject_id,
            "checks": [dict(item) for item in self.checks],
            "production_runtime_ready": self.production_runtime_ready,
        }


@dataclass(frozen=True)
class LoadedMCPToolCallProfile:
    path: Path
    root: Path
    data: Mapping[str, Any]
    raw_sha256: str
    canonical_sha256: str
    builtin: bool = False

    @property
    def profile_id(self) -> str:
        return str(self.data.get("profile_id", ""))


@dataclass(frozen=True)
class HostOwnedMCPToolCallAdapter:
    """Reference adapter that normalizes and assesses but never executes."""

    profile: LoadedMCPToolCallProfile

    def normalize(
        self,
        tool_descriptor: Mapping[str, Any],
        call_request: Mapping[str, Any],
        transport_binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        return build_mcp_tool_call_envelope(
            self.profile,
            tool_descriptor,
            call_request,
            transport_binding,
        )

    def assess(self, envelope: Mapping[str, Any], host_context: Mapping[str, Any]) -> dict[str, Any]:
        return assess_mcp_tool_call(self.profile, envelope, host_context)


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(canonical_json(value))
    except (TypeError, ValueError, RecursionError) as exc:
        raise MCPToolCallError(f"value is not bounded canonical JSON: {exc}") from exc


def _check(name: str, passed: bool, expected: Any, actual: Any, **extra: Any) -> dict[str, Any]:
    return {
        "check": name,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        **extra,
    }


def _safe_token(value: Any) -> bool:
    return isinstance(value, str) and bool(_SAFE_TOKEN_RE.fullmatch(value))


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _unique_safe_strings(value: Any, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, list) or (not allow_empty and not value):
        return False
    if any(not _safe_token(item) for item in value):
        return False
    return len(value) == len(set(value))


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def normalize_instant(value: str | datetime) -> str:
    parsed = value if isinstance(value, datetime) else _parse_instant(value)
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        raise MCPToolCallError("timestamp must be ISO-8601 with a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_yaml_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MCPToolCallError(f"cannot read {label} {path}: {exc}") from exc
    if len(raw) > MAX_YAML_BYTES:
        raise MCPToolCallError(f"{label} exceeds {MAX_YAML_BYTES} byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MCPToolCallError(f"{label} is not UTF-8: {path}") from exc
    try:
        value = load_yaml_no_duplicate_keys(text)
    except Exception as exc:
        raise MCPToolCallError(f"cannot parse {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MCPToolCallError(f"{label} root must be an object")
    try:
        json_depth(value)
        canonical_json(value)
    except Exception as exc:
        raise MCPToolCallError(f"{label} is not bounded canonical data: {exc}") from exc
    return dict(value), raw


def load_json_mapping(path: str | Path, *, label: str) -> dict[str, Any]:
    result = read_json_object_artifact(path, artifact_name=label)
    if not result.ok or result.value is None:
        raise MCPToolCallError(f"cannot load {label}: {result.reason}: {result.detail}")
    return dict(result.value)


def load_mcp_tool_call_profile(path: str | Path, *, builtin: bool = False) -> LoadedMCPToolCallProfile:
    source = Path(path).resolve()
    data, raw = _read_yaml_object(source, label="MCP tool-call profile")
    return LoadedMCPToolCallProfile(
        path=source,
        root=source.parent,
        data=data,
        raw_sha256=sha256_bytes(raw),
        canonical_sha256=sha256_json(data),
        builtin=builtin,
    )


def _copy_traversable(source: Any, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name == "__pycache__" or child.name.endswith((".pyc", ".pyo")):
            continue
        destination = target / child.name
        if child.is_dir():
            _copy_traversable(child, destination)
        else:
            destination.write_bytes(child.read_bytes())


@contextmanager
def materialized_mcp_profile_source(source: str | Path = BUILTIN_MCP_PROFILE_ID) -> Iterator[LoadedMCPToolCallProfile]:
    if str(source) != BUILTIN_MCP_PROFILE_ID:
        yield load_mcp_tool_call_profile(source)
        return
    with tempfile.TemporaryDirectory(prefix="ainir-mcp-profile-") as tmp:
        root = Path(tmp) / "reference_v1"
        _copy_traversable(importlib_resources.files(BUILTIN_MCP_PROFILE_PACKAGE), root)
        yield load_mcp_tool_call_profile(root / MCP_PROFILE_FILENAME, builtin=True)


def _safe_child(root: Path, relative: Any, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise MCPToolCallError(f"{label} must be a non-empty relative path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise MCPToolCallError(f"{label} escapes the profile root: {relative!r}") from exc
    return candidate


def mcp_tool_call_profile_projection(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_copy(value) for key, value in profile.items() if key != "profile_sha256"}


def mcp_tool_call_envelope_projection(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_copy(value) for key, value in envelope.items() if key not in {"envelope_id", "envelope_sha256"}}


def mcp_host_context_projection(context: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_copy(value) for key, value in context.items() if key not in {"context_id", "context_sha256"}}


def mcp_tool_call_assessment_projection(assessment: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_copy(value) for key, value in assessment.items() if key not in {"assessment_id", "assessment_sha256"}}


def _scan_external_refs(value: Any, *, path: str = "$", results: list[str] | None = None) -> list[str]:
    found = results if results is not None else []
    if isinstance(value, Mapping):
        ref = value.get("$ref")
        if isinstance(ref, str) and ("://" in ref or ref.startswith("file:")):
            found.append(f"{path}.$ref")
        for key, item in value.items():
            _scan_external_refs(item, path=f"{path}.{key}", results=found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_external_refs(item, path=f"{path}[{index}]", results=found)
    return found


_JSON_SCHEMA_ALLOWED_KEYS = frozenset({
    "$schema", "title", "description", "type", "properties", "required",
    "additionalProperties", "items", "minItems", "maxItems", "minLength",
    "maxLength", "minimum", "maximum", "enum", "const",
})
_JSON_SCHEMA_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})


def _schema_definition_findings(schema: Any, *, path: str = "$") -> list[str]:
    """Return unsupported or malformed features in AiNIR's bounded schema subset.

    MCP permits JSON Schema 2020-12.  This public reference adapter intentionally
    implements only a small deterministic subset and fails closed on everything
    else rather than pretending to validate a richer schema.
    """

    findings: list[str] = []
    if not isinstance(schema, Mapping):
        return [f"{path}: schema must be an object"]
    unknown = sorted(str(key) for key in schema if key not in _JSON_SCHEMA_ALLOWED_KEYS)
    if unknown:
        findings.append(f"{path}: unsupported schema keywords {unknown}")
    schema_type = schema.get("type")
    if schema_type not in _JSON_SCHEMA_TYPES:
        findings.append(f"{path}.type: expected one supported JSON type")
    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        findings.append(f"{path}.enum: expected non-empty array")
    if "const" in schema:
        try:
            _json_copy(schema.get("const"))
        except MCPToolCallError as exc:
            findings.append(f"{path}.const: {exc}")
    if schema_type == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            findings.append(f"{path}.properties: expected object")
        else:
            for key, child in properties.items():
                if not isinstance(key, str) or not key:
                    findings.append(f"{path}.properties: property names must be non-empty strings")
                    continue
                findings.extend(_schema_definition_findings(child, path=f"{path}.properties.{key}"))
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required) or len(set(required)) != len(required):
            findings.append(f"{path}.required: expected unique string array")
        elif isinstance(properties, Mapping) and not set(required).issubset(set(properties)):
            findings.append(f"{path}.required: required names must exist in properties")
        if schema.get("additionalProperties", False) is not False:
            findings.append(f"{path}.additionalProperties: bounded profile requires false")
    elif schema_type == "array":
        if "items" not in schema:
            findings.append(f"{path}.items: required for array schema")
        else:
            findings.extend(_schema_definition_findings(schema.get("items"), path=f"{path}.items"))
    for minimum_key in ("minLength", "maxLength", "minItems", "maxItems"):
        if minimum_key in schema:
            value = schema.get(minimum_key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                findings.append(f"{path}.{minimum_key}: expected non-negative integer")
    for number_key in ("minimum", "maximum"):
        if number_key in schema:
            value = schema.get(number_key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                findings.append(f"{path}.{number_key}: expected finite number")
    return findings


def _schema_value_findings(value: Any, schema: Mapping[str, Any], *, path: str = "$") -> list[str]:
    findings: list[str] = []
    schema_type = schema.get("type")
    type_ok = {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(schema_type, False)
    if not type_ok:
        return [f"{path}: expected {schema_type}, got {type(value).__name__}"]
    if "const" in schema and value != schema.get("const"):
        findings.append(f"{path}: value does not match const")
    if isinstance(schema.get("enum"), list) and value not in schema.get("enum", []):
        findings.append(f"{path}: value is outside enum")
    if schema_type == "object":
        properties = schema.get("properties", {}) if isinstance(schema.get("properties"), Mapping) else {}
        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
        missing = sorted(name for name in required if name not in value)
        if missing:
            findings.append(f"{path}: missing required properties {missing}")
        unknown = sorted(str(name) for name in value if name not in properties)
        if unknown and schema.get("additionalProperties", False) is False:
            findings.append(f"{path}: additional properties forbidden {unknown}")
        for name, child in properties.items():
            if name in value and isinstance(child, Mapping):
                findings.extend(_schema_value_findings(value[name], child, path=f"{path}/{name}"))
    elif schema_type == "array":
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            findings.append(f"{path}: array shorter than minItems")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            findings.append(f"{path}: array longer than maxItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                findings.extend(_schema_value_findings(item, item_schema, path=f"{path}/{index}"))
    elif schema_type == "string":
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            findings.append(f"{path}: string shorter than minLength")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            findings.append(f"{path}: string longer than maxLength")
    elif schema_type in {"number", "integer"}:
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            findings.append(f"{path}: number below minimum")
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            findings.append(f"{path}: number above maximum")
    return findings


def validate_mcp_tool_descriptor(descriptor: Mapping[str, Any]) -> MCPCheckReport:
    checks: list[dict[str, Any]] = []
    name = descriptor.get("name")
    checks.append(_check("descriptor.name", isinstance(name, str) and bool(_SAFE_TOOL_NAME_RE.fullmatch(name)), "MCP tool name", name))
    input_schema = descriptor.get("inputSchema")
    checks.append(_check("descriptor.input_schema.object", isinstance(input_schema, Mapping), "object", type(input_schema).__name__))
    if isinstance(input_schema, Mapping):
        checks.append(_check("descriptor.input_schema.root_type", input_schema.get("type") == "object", "object", input_schema.get("type")))
        external = _scan_external_refs(input_schema)
        checks.append(_check("descriptor.input_schema.external_refs", not external, [], external))
        subset_findings = _schema_definition_findings(input_schema)
        checks.append(_check("descriptor.input_schema.bounded_subset", not subset_findings, [], subset_findings))
    output_schema = descriptor.get("outputSchema")
    if output_schema is not None:
        checks.append(_check("descriptor.output_schema.object", isinstance(output_schema, Mapping), "object", type(output_schema).__name__))
        if isinstance(output_schema, Mapping):
            external = _scan_external_refs(output_schema)
            checks.append(_check("descriptor.output_schema.external_refs", not external, [], external))
            subset_findings = _schema_definition_findings(output_schema)
            checks.append(_check("descriptor.output_schema.bounded_subset", not subset_findings, [], subset_findings))
    annotations = descriptor.get("annotations")
    if annotations is not None:
        checks.append(_check("descriptor.annotations.object", isinstance(annotations, Mapping), "object|null", type(annotations).__name__))
    execution = descriptor.get("execution")
    if execution is not None:
        valid = isinstance(execution, Mapping) and execution.get("taskSupport") in {"forbidden", "optional", "required", None}
        checks.append(_check("descriptor.execution.task_support", valid, "forbidden|optional|required|null", execution.get("taskSupport") if isinstance(execution, Mapping) else execution))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        kind="AiNIRMCPToolDescriptorValidationReport",
        version="ainir.mcp-tool-descriptor-validation-report.v1",
        valid=valid,
        checks=tuple(checks),
        subject_id=str(name) if isinstance(name, str) else None,
    )


def _profile_tool_map(profile: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in profile.get("tools", []) or []:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            result[str(item["name"])] = item
    return result


def validate_mcp_tool_call_profile(profile: LoadedMCPToolCallProfile | Mapping[str, Any]) -> MCPCheckReport:
    loaded = profile if isinstance(profile, LoadedMCPToolCallProfile) else None
    data = loaded.data if loaded is not None else profile
    checks: list[dict[str, Any]] = []
    checks.append(_check("profile.root.object", isinstance(data, Mapping), "object", type(data).__name__))
    if not isinstance(data, Mapping):
        return MCPCheckReport("AiNIRMCPToolCallProfileValidationReport", "ainir.mcp-tool-call-profile-validation-report.v1", False, tuple(checks))
    checks.append(_check("profile.unknown_fields", not (set(data) - _PROFILE_TOP_KEYS), [], sorted(set(data) - _PROFILE_TOP_KEYS)))
    checks.append(_check("profile.kind", data.get("kind") == MCP_TOOL_CALL_PROFILE_KIND, MCP_TOOL_CALL_PROFILE_KIND, data.get("kind")))
    checks.append(_check("profile.version", data.get("version") == MCP_TOOL_CALL_PROFILE_CONTRACT, MCP_TOOL_CALL_PROFILE_CONTRACT, data.get("version")))
    profile_id = data.get("profile_id")
    checks.append(_check("profile.profile_id", isinstance(profile_id, str) and bool(_PROFILE_ID_RE.fullmatch(profile_id)), "safe profile id", profile_id))
    checks.append(_check("profile.status", data.get("status") in {"reviewed", "bundled"}, "reviewed|bundled", data.get("status")))
    versions = data.get("protocol_versions")
    versions_ok = _unique_safe_strings(versions) and set(versions).issubset(SUPPORTED_MCP_PROTOCOL_VERSIONS)
    checks.append(_check("profile.protocol_versions", versions_ok, sorted(SUPPORTED_MCP_PROTOCOL_VERSIONS), versions))
    policies = data.get("policies")
    checks.append(_check("profile.policies.object", isinstance(policies, Mapping), "object", type(policies).__name__))
    if isinstance(policies, Mapping):
        checks.append(_check("profile.policies.unknown_fields", not (set(policies) - _PROFILE_POLICY_KEYS), [], sorted(set(policies) - _PROFILE_POLICY_KEYS)))
        expected_policies = {
            "unknown_tool": "refuse",
            "tool_descriptions_are_evidence": False,
            "tool_annotations_are_evidence": False,
            "model_output_is_evidence": False,
            "ainir_executes_actions": False,
            "host_executes_actions": True,
            "raw_credentials_in_arguments": "refuse",
            "task_execution": "refuse",
            "consent_mode": "explicit_per_call",
        }
        for key, expected in expected_policies.items():
            checks.append(_check(f"profile.policies.{key}", policies.get(key) == expected, expected, policies.get(key)))
    tools = data.get("tools")
    checks.append(_check("profile.tools.array", isinstance(tools, list) and bool(tools), "non-empty array", type(tools).__name__))
    seen_names: set[str] = set()
    if isinstance(tools, list):
        for index, tool in enumerate(tools):
            prefix = f"profile.tools[{index}]"
            if not isinstance(tool, Mapping):
                checks.append(_check(prefix, False, "object", type(tool).__name__))
                continue
            checks.append(_check(f"{prefix}.unknown_fields", not (set(tool) - _PROFILE_TOOL_KEYS), [], sorted(set(tool) - _PROFILE_TOOL_KEYS)))
            name = tool.get("name")
            name_ok = isinstance(name, str) and bool(_SAFE_TOOL_NAME_RE.fullmatch(name)) and name not in seen_names
            checks.append(_check(f"{prefix}.name", name_ok, "unique MCP tool name", name))
            if isinstance(name, str):
                seen_names.add(name)
            for field_name in ("server_id", "server_origin", "authorization_audience"):
                checks.append(_check(f"{prefix}.{field_name}", _safe_token(tool.get(field_name)), "safe token", tool.get(field_name)))
            for field_name in ("descriptor_sha256", "input_schema_sha256"):
                checks.append(_check(f"{prefix}.{field_name}", _sha(tool.get(field_name)), "sha256:<64 lowercase hex>", tool.get(field_name)))
            output_hash = tool.get("output_schema_sha256")
            checks.append(_check(f"{prefix}.output_schema_sha256", output_hash is None or _sha(output_hash), "sha256:<64 lowercase hex>|null", output_hash))
            effects = tool.get("effects")
            capabilities = tool.get("capabilities")
            checks.append(_check(f"{prefix}.effects", _unique_safe_strings(effects) and set(effects).issubset(MCP_EFFECT_VOCABULARY), sorted(MCP_EFFECT_VOCABULARY), effects))
            checks.append(_check(f"{prefix}.capabilities", _unique_safe_strings(capabilities) and set(capabilities).issubset(MCP_CAPABILITY_VOCABULARY), sorted(MCP_CAPABILITY_VOCABULARY), capabilities))
            risk = tool.get("risk_class")
            checks.append(_check(f"{prefix}.risk_class", risk in MCP_RISK_CLASSES, "reviewed risk class", risk))
            decision_mode = tool.get("decision_mode")
            checks.append(_check(f"{prefix}.decision_mode", decision_mode in {"allow", "review_required"}, "allow|review_required", decision_mode))
            if risk == "destructive":
                checks.append(_check(f"{prefix}.destructive_review_required", decision_mode == "review_required", "review_required", decision_mode))
            for field_name in ("mutating", "destructive", "idempotent", "transaction_required", "rollback_required"):
                checks.append(_check(f"{prefix}.{field_name}", isinstance(tool.get(field_name), bool), "boolean", type(tool.get(field_name)).__name__))
            if tool.get("destructive") is True:
                checks.append(_check(f"{prefix}.destructive_requires_mutating", tool.get("mutating") is True, True, tool.get("mutating")))
            if tool.get("rollback_required") is True:
                checks.append(_check(f"{prefix}.rollback_requires_transaction", tool.get("transaction_required") is True, True, tool.get("transaction_required")))
            if risk == "read_only":
                checks.append(_check(f"{prefix}.read_only_not_mutating", tool.get("mutating") is False, False, tool.get("mutating")))
            max_bytes = tool.get("max_arguments_bytes")
            checks.append(_check(f"{prefix}.max_arguments_bytes", isinstance(max_bytes, int) and not isinstance(max_bytes, bool) and 1 <= max_bytes <= 1_000_000, "integer 1..1000000", max_bytes))
            bindings = tool.get("resource_bindings")
            bindings_ok = isinstance(bindings, list) and bool(bindings)
            checks.append(_check(f"{prefix}.resource_bindings", bindings_ok, "non-empty array", type(bindings).__name__))
            if isinstance(bindings, list):
                seen_pointers: set[str] = set()
                for binding_index, binding in enumerate(bindings):
                    bprefix = f"{prefix}.resource_bindings[{binding_index}]"
                    if not isinstance(binding, Mapping):
                        checks.append(_check(bprefix, False, "object", type(binding).__name__))
                        continue
                    checks.append(_check(f"{bprefix}.unknown_fields", not (set(binding) - _RESOURCE_BINDING_KEYS), [], sorted(set(binding) - _RESOURCE_BINDING_KEYS)))
                    pointer = binding.get("pointer")
                    pointer_ok = isinstance(pointer, str) and pointer.startswith("/") and pointer not in seen_pointers
                    checks.append(_check(f"{bprefix}.pointer", pointer_ok, "unique JSON pointer", pointer))
                    if isinstance(pointer, str):
                        seen_pointers.add(pointer)
                    checks.append(_check(f"{bprefix}.resource_type", binding.get("resource_type") in {"workspace_path", "uri", "opaque"}, "workspace_path|uri|opaque", binding.get("resource_type")))
                    checks.append(_check(f"{bprefix}.permission", binding.get("permission") in {"read", "write", "delete", "invoke"}, "read|write|delete|invoke", binding.get("permission")))
            required_checks = tool.get("required_host_checks")
            mandatory = {"schema_validation", "authorization_binding", "resource_resolution", "explicit_consent"}
            required_ok = _unique_safe_strings(required_checks) and mandatory.issubset(set(required_checks))
            checks.append(_check(f"{prefix}.required_host_checks", required_ok, sorted(mandatory), required_checks))
            descriptor_rel = tool.get("descriptor")
            if loaded is not None:
                try:
                    descriptor_path = _safe_child(loaded.root, descriptor_rel, label=f"{prefix}.descriptor")
                    descriptor = load_json_mapping(descriptor_path, label="MCP tool descriptor")
                    descriptor_report = validate_mcp_tool_descriptor(descriptor)
                    checks.append(_check(f"{prefix}.descriptor_valid", descriptor_report.valid, True, descriptor_report.overall_status))
                    checks.append(_check(f"{prefix}.descriptor_name_binding", descriptor.get("name") == name, name, descriptor.get("name")))
                    checks.append(_check(f"{prefix}.descriptor_sha256_binding", sha256_json(descriptor) == tool.get("descriptor_sha256"), tool.get("descriptor_sha256"), sha256_json(descriptor)))
                    checks.append(_check(f"{prefix}.input_schema_sha256_binding", sha256_json(descriptor.get("inputSchema")) == tool.get("input_schema_sha256"), tool.get("input_schema_sha256"), sha256_json(descriptor.get("inputSchema"))))
                    actual_output_hash = sha256_json(descriptor.get("outputSchema")) if descriptor.get("outputSchema") is not None else None
                    checks.append(_check(f"{prefix}.output_schema_sha256_binding", actual_output_hash == output_hash, output_hash, actual_output_hash))
                except MCPToolCallError as exc:
                    checks.append(_check(f"{prefix}.descriptor_load", False, "safe in-root descriptor", str(exc)))
    profile_hash = data.get("profile_sha256")
    calculated_profile_hash = sha256_json(mcp_tool_call_profile_projection(data))
    checks.append(_check("profile.profile_sha256", _sha(profile_hash) and profile_hash == calculated_profile_hash, calculated_profile_hash, profile_hash))
    checks.append(_check("profile.production_runtime_ready", data.get("production_runtime_ready") is False, False, data.get("production_runtime_ready")))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        kind="AiNIRMCPToolCallProfileValidationReport",
        version="ainir.mcp-tool-call-profile-validation-report.v1",
        valid=valid,
        checks=tuple(checks),
        subject_id=str(profile_id) if isinstance(profile_id, str) else None,
    )


def _json_pointer_get(value: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False, None
    current = value
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _normalize_workspace_path(value: str) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None, "workspace path must be a non-empty string without NUL"
    if any(ord(character) < 0x20 for character in value):
        return None, "workspace paths may not contain ASCII control characters"
    # The reference profile is portable across POSIX and Windows hosts.  Reject
    # path forms whose identity changes across those platforms rather than
    # allowing the host to reinterpret them after consent was bound.
    if ":" in value:
        return None, "workspace paths may not contain drive or alternate-data-stream separators"
    windows_style = "\\" in value
    path = PureWindowsPath(value) if windows_style else PurePosixPath(value)
    if path.is_absolute() or bool(getattr(path, "drive", "")) or value.startswith(("/", "\\")):
        return None, "absolute workspace paths are forbidden"
    if any(part == ".." for part in path.parts):
        return None, "workspace path traversal is forbidden"
    for part in path.parts:
        if part.endswith((" ", ".")):
            return None, "workspace path segments may not end in a space or dot"
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            return None, "workspace paths may not use Windows reserved device names"
    normalized = path.as_posix()
    if normalized in {"", "."}:
        return None, "workspace path must identify a resource"
    return normalized, None


def _looks_like_sensitive_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SENSITIVE_VALUE_PATTERNS)


def _scan_sensitive_paths(value: Any, *, path: str = "") -> list[str]:
    results: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}"
            if _SENSITIVE_ARGUMENT_TOKEN_RE.search(str(key)):
                results.append(child)
            results.extend(_scan_sensitive_paths(item, path=child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            results.extend(_scan_sensitive_paths(item, path=f"{path}/{index}"))
    elif isinstance(value, str) and _looks_like_sensitive_value(value):
        results.append(path or "/")
    return sorted(set(results))


def _client_meta_hash(params: Mapping[str, Any]) -> str | None:
    meta = params.get("_meta")
    return sha256_json(meta) if isinstance(meta, Mapping) else None


def build_mcp_tool_call_envelope(
    profile: LoadedMCPToolCallProfile,
    tool_descriptor: Mapping[str, Any],
    call_request: Mapping[str, Any],
    transport_binding: Mapping[str, Any],
) -> dict[str, Any]:
    profile_validation = validate_mcp_tool_call_profile(profile)
    if not profile_validation.valid:
        raise MCPToolCallError("MCP tool-call profile failed validation")
    descriptor = _json_copy(dict(tool_descriptor))
    request = _json_copy(dict(call_request))
    transport = _json_copy(dict(transport_binding))
    descriptor_validation = validate_mcp_tool_descriptor(descriptor)
    if not descriptor_validation.valid:
        raise MCPToolCallError("MCP tool descriptor failed structural validation")
    unknown_request_fields = sorted(set(request) - {"jsonrpc", "id", "method", "params"})
    if unknown_request_fields:
        raise MCPToolCallError(f"MCP tools/call request has unknown top-level fields: {unknown_request_fields}")
    if request.get("jsonrpc") != "2.0" or request.get("method") != "tools/call":
        raise MCPToolCallError("request must be JSON-RPC 2.0 method tools/call")
    request_id = request.get("id")
    if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
        raise MCPToolCallError("JSON-RPC request id must be a string or integer")
    params = request.get("params")
    if not isinstance(params, Mapping):
        raise MCPToolCallError("tools/call params must be an object")
    unknown_params = sorted(set(params) - {"name", "arguments", "_meta", "task", "inputResponses", "requestState"})
    if unknown_params:
        raise MCPToolCallError(f"tools/call params contain unsupported fields: {unknown_params}")
    tool_name = params.get("name")
    if not isinstance(tool_name, str) or not _SAFE_TOOL_NAME_RE.fullmatch(tool_name):
        raise MCPToolCallError("tools/call name is not a valid MCP tool name")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, Mapping):
        raise MCPToolCallError("tools/call arguments must be an object")
    protocol_version = transport.get("protocol_version")
    if not isinstance(protocol_version, str):
        raise MCPToolCallError("transport protocol_version must be a string")
    tool_contract = _profile_tool_map(profile.data).get(tool_name)
    findings: list[dict[str, Any]] = []
    requested_resources: list[dict[str, Any]] = []
    if tool_contract is None:
        findings.append({"rule": "MCP001.unknown_tool", "severity": "critical", "target": "params.name", "message": "Tool is not present in the reviewed host profile."})
    else:
        for binding in tool_contract.get("resource_bindings", []) or []:
            pointer = str(binding.get("pointer"))
            found, raw_value = _json_pointer_get(arguments, pointer)
            normalized_value: Any = raw_value
            error: str | None = None
            if not found:
                error = "resource binding pointer is missing"
            elif binding.get("resource_type") == "workspace_path":
                normalized_value, error = _normalize_workspace_path(raw_value)
            elif not isinstance(raw_value, str) or not raw_value:
                error = "resource binding value must be a non-empty string"
            requested_resources.append({
                "pointer": pointer,
                "resource_type": binding.get("resource_type"),
                "permission": binding.get("permission"),
                "raw_value": raw_value if found else None,
                "normalized_value": normalized_value if error is None else None,
                "status": "normalized" if error is None else "invalid",
                "error": error,
            })
            if error is not None:
                findings.append({"rule": "MCP002.resource_binding_invalid", "severity": "critical", "target": pointer, "message": error})
    schema_findings = _schema_value_findings(arguments, descriptor.get("inputSchema", {}))
    for finding in schema_findings:
        findings.append({"rule": "MCP004.arguments_schema_invalid", "severity": "critical", "target": "params.arguments", "message": finding})
    sensitive_paths = _scan_sensitive_paths(arguments)
    meta = params.get("_meta")
    if isinstance(meta, Mapping):
        sensitive_paths.extend("/params/_meta" + path for path in _scan_sensitive_paths(meta))
    sensitive_paths = sorted(set(sensitive_paths))
    for path in sensitive_paths:
        findings.append({"rule": "MCP003.sensitive_argument_forbidden", "severity": "critical", "target": path, "message": "Credential-like values must be supplied out of band by the host, not as tool arguments."})
    descriptor_hash = sha256_json(descriptor)
    input_hash = sha256_json(descriptor.get("inputSchema"))
    output_hash = sha256_json(descriptor.get("outputSchema")) if descriptor.get("outputSchema") is not None else None
    arguments_copy = _json_copy(arguments)
    arguments_hash = sha256_json(arguments_copy)
    resources_hash = sha256_json(requested_resources)
    annotations = descriptor.get("annotations") if isinstance(descriptor.get("annotations"), Mapping) else {}
    execution = descriptor.get("execution") if isinstance(descriptor.get("execution"), Mapping) else {}
    task_requested = "task" in params or execution.get("taskSupport") == "required"
    mrtr_present = "inputResponses" in params or "requestState" in params
    envelope: dict[str, Any] = {
        "kind": MCP_TOOL_CALL_ENVELOPE_KIND,
        "version": MCP_TOOL_CALL_ENVELOPE_CONTRACT,
        "profile_id": profile.profile_id,
        "protocol_version": protocol_version,
        "jsonrpc_request_id": request_id,
        "method": "tools/call",
        "tool_name": tool_name,
        "descriptor_sha256": descriptor_hash,
        "input_schema_sha256": input_hash,
        "output_schema_sha256": output_hash,
        "arguments": arguments_copy,
        "arguments_sha256": arguments_hash,
        "arguments_size": len(canonical_json(arguments_copy).encode("utf-8")),
        "untrusted_metadata": {
            "title": descriptor.get("title"),
            "description_sha256": sha256_json(descriptor.get("description")) if descriptor.get("description") is not None else None,
            "annotations": _json_copy(annotations),
            "execution": _json_copy(execution),
            "client_meta_sha256": _client_meta_hash(params),
        },
        "transport_observations": {
            "method_header": transport.get("method_header"),
            "name_header": transport.get("name_header"),
        },
        "requested_resources": requested_resources,
        "requested_resources_sha256": resources_hash,
        "sensitive_argument_paths": sensitive_paths,
        "task_requested": task_requested,
        "mrtr_input_responses_present": mrtr_present,
        "normalization_findings": findings,
        "production_runtime_ready": False,
    }
    digest = sha256_json(mcp_tool_call_envelope_projection(envelope))
    envelope["envelope_sha256"] = digest
    envelope["envelope_id"] = "ainir.mcp.envelope." + digest.removeprefix("sha256:")[:20]
    return envelope


def validate_mcp_tool_call_envelope(envelope: Mapping[str, Any]) -> MCPCheckReport:
    checks: list[dict[str, Any]] = []
    checks.append(_check("envelope.unknown_fields", not (set(envelope) - _ENVELOPE_TOP_KEYS), [], sorted(set(envelope) - _ENVELOPE_TOP_KEYS)))
    checks.append(_check("envelope.kind", envelope.get("kind") == MCP_TOOL_CALL_ENVELOPE_KIND, MCP_TOOL_CALL_ENVELOPE_KIND, envelope.get("kind")))
    checks.append(_check("envelope.version", envelope.get("version") == MCP_TOOL_CALL_ENVELOPE_CONTRACT, MCP_TOOL_CALL_ENVELOPE_CONTRACT, envelope.get("version")))
    checks.append(_check("envelope.id", isinstance(envelope.get("envelope_id"), str) and str(envelope.get("envelope_id")).startswith("ainir.mcp.envelope."), "AiNIR MCP envelope id", envelope.get("envelope_id")))
    expected_hash = sha256_json(mcp_tool_call_envelope_projection(envelope))
    checks.append(_check("envelope.sha256", _sha(envelope.get("envelope_sha256")) and envelope.get("envelope_sha256") == expected_hash, expected_hash, envelope.get("envelope_sha256")))
    expected_id = "ainir.mcp.envelope." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("envelope.id_binding", envelope.get("envelope_id") == expected_id, expected_id, envelope.get("envelope_id")))
    checks.append(_check("envelope.profile_id", isinstance(envelope.get("profile_id"), str) and bool(_PROFILE_ID_RE.fullmatch(str(envelope.get("profile_id")))), "safe profile id", envelope.get("profile_id")))
    checks.append(_check("envelope.protocol_version", envelope.get("protocol_version") in SUPPORTED_MCP_PROTOCOL_VERSIONS, sorted(SUPPORTED_MCP_PROTOCOL_VERSIONS), envelope.get("protocol_version")))
    request_id = envelope.get("jsonrpc_request_id")
    checks.append(_check("envelope.jsonrpc_request_id", not isinstance(request_id, bool) and isinstance(request_id, (str, int)), "string|integer", request_id))
    checks.append(_check("envelope.method", envelope.get("method") == "tools/call", "tools/call", envelope.get("method")))
    checks.append(_check("envelope.tool_name", isinstance(envelope.get("tool_name"), str) and bool(_SAFE_TOOL_NAME_RE.fullmatch(str(envelope.get("tool_name")))), "MCP tool name", envelope.get("tool_name")))
    for field_name in ("descriptor_sha256", "input_schema_sha256", "arguments_sha256", "requested_resources_sha256"):
        checks.append(_check(f"envelope.{field_name}", _sha(envelope.get(field_name)), "sha256:<64 lowercase hex>", envelope.get(field_name)))
    output_hash = envelope.get("output_schema_sha256")
    checks.append(_check("envelope.output_schema_sha256", output_hash is None or _sha(output_hash), "sha256:<64 lowercase hex>|null", output_hash))
    checks.append(_check("envelope.arguments.object", isinstance(envelope.get("arguments"), Mapping), "object", type(envelope.get("arguments")).__name__))
    if isinstance(envelope.get("arguments"), Mapping):
        checks.append(_check("envelope.arguments.hash", sha256_json(envelope.get("arguments")) == envelope.get("arguments_sha256"), envelope.get("arguments_sha256"), sha256_json(envelope.get("arguments"))))
    arguments_size = envelope.get("arguments_size")
    checks.append(_check("envelope.arguments_size", isinstance(arguments_size, int) and not isinstance(arguments_size, bool) and arguments_size >= 0, "non-negative integer", arguments_size))
    if isinstance(envelope.get("arguments"), Mapping):
        actual_size = len(canonical_json(envelope.get("arguments")).encode("utf-8"))
        checks.append(_check("envelope.arguments_size.binding", arguments_size == actual_size, actual_size, arguments_size))
    metadata = envelope.get("untrusted_metadata")
    checks.append(_check("envelope.untrusted_metadata.object", isinstance(metadata, Mapping), "object", type(metadata).__name__))
    if isinstance(metadata, Mapping):
        checks.append(_check("envelope.untrusted_metadata.unknown_fields", not (set(metadata) - _ENVELOPE_METADATA_KEYS), [], sorted(set(metadata) - _ENVELOPE_METADATA_KEYS)))
        for field_name in ("description_sha256", "client_meta_sha256"):
            value = metadata.get(field_name)
            checks.append(_check(f"envelope.untrusted_metadata.{field_name}", value is None or _sha(value), "sha256:<64 lowercase hex>|null", value))
        checks.append(_check("envelope.untrusted_metadata.annotations", isinstance(metadata.get("annotations"), Mapping), "object", type(metadata.get("annotations")).__name__))
        checks.append(_check("envelope.untrusted_metadata.execution", isinstance(metadata.get("execution"), Mapping), "object", type(metadata.get("execution")).__name__))
    transport = envelope.get("transport_observations")
    checks.append(_check("envelope.transport_observations.object", isinstance(transport, Mapping), "object", type(transport).__name__))
    if isinstance(transport, Mapping):
        checks.append(_check("envelope.transport_observations.unknown_fields", not (set(transport) - _ENVELOPE_TRANSPORT_KEYS), [], sorted(set(transport) - _ENVELOPE_TRANSPORT_KEYS)))
        for field_name in _ENVELOPE_TRANSPORT_KEYS:
            value = transport.get(field_name)
            checks.append(_check(f"envelope.transport_observations.{field_name}", value is None or isinstance(value, str), "string|null", value))
    resources = envelope.get("requested_resources")
    checks.append(_check("envelope.requested_resources.array", isinstance(resources, list), "array", type(resources).__name__))
    if isinstance(resources, list):
        checks.append(_check("envelope.requested_resources.hash", sha256_json(resources) == envelope.get("requested_resources_sha256"), envelope.get("requested_resources_sha256"), sha256_json(resources)))
        for index, resource in enumerate(resources):
            prefix = f"envelope.requested_resources[{index}]"
            if not isinstance(resource, Mapping):
                checks.append(_check(prefix, False, "object", type(resource).__name__))
                continue
            checks.append(_check(f"{prefix}.unknown_fields", not (set(resource) - _ENVELOPE_RESOURCE_KEYS), [], sorted(set(resource) - _ENVELOPE_RESOURCE_KEYS)))
            checks.append(_check(f"{prefix}.pointer", isinstance(resource.get("pointer"), str) and str(resource.get("pointer")).startswith("/"), "JSON pointer", resource.get("pointer")))
            checks.append(_check(f"{prefix}.resource_type", resource.get("resource_type") in {"workspace_path", "uri", "opaque"}, "workspace_path|uri|opaque", resource.get("resource_type")))
            checks.append(_check(f"{prefix}.permission", resource.get("permission") in {"read", "write", "delete", "invoke"}, "read|write|delete|invoke", resource.get("permission")))
            checks.append(_check(f"{prefix}.status", resource.get("status") in {"normalized", "invalid"}, "normalized|invalid", resource.get("status")))
            status = resource.get("status")
            normalized = resource.get("normalized_value")
            error = resource.get("error")
            status_consistent = (status == "normalized" and normalized is not None and error is None) or (status == "invalid" and normalized is None and isinstance(error, str) and bool(error))
            checks.append(_check(f"{prefix}.status_consistency", status_consistent, "normalized=>value/no error; invalid=>null value/error", {"status": status, "normalized_value": normalized, "error": error}))
    sensitive = envelope.get("sensitive_argument_paths")
    checks.append(_check("envelope.sensitive_argument_paths", isinstance(sensitive, list) and len(sensitive) == len(set(sensitive)) and all(isinstance(item, str) and item.startswith("/") for item in sensitive), "unique JSON-pointer array", sensitive))
    findings = envelope.get("normalization_findings")
    checks.append(_check("envelope.normalization_findings.array", isinstance(findings, list), "array", type(findings).__name__))
    if isinstance(findings, list):
        for index, finding in enumerate(findings):
            prefix = f"envelope.normalization_findings[{index}]"
            if not isinstance(finding, Mapping):
                checks.append(_check(prefix, False, "object", type(finding).__name__))
                continue
            checks.append(_check(f"{prefix}.unknown_fields", not (set(finding) - _NORMALIZATION_FINDING_KEYS), [], sorted(set(finding) - _NORMALIZATION_FINDING_KEYS)))
            checks.append(_check(f"{prefix}.severity", finding.get("severity") in {"critical", "warning", "info"}, "critical|warning|info", finding.get("severity")))
            for field_name in ("rule", "target", "message"):
                checks.append(_check(f"{prefix}.{field_name}", isinstance(finding.get(field_name), str) and bool(finding.get(field_name)), "non-empty string", finding.get(field_name)))
    for field_name in ("task_requested", "mrtr_input_responses_present", "production_runtime_ready"):
        checks.append(_check(f"envelope.{field_name}", isinstance(envelope.get(field_name), bool), "boolean", type(envelope.get(field_name)).__name__))
    checks.append(_check("envelope.production_runtime_ready.false", envelope.get("production_runtime_ready") is False, False, envelope.get("production_runtime_ready")))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        kind="AiNIRMCPToolCallEnvelopeValidationReport",
        version="ainir.mcp-tool-call-envelope-validation-report.v1",
        valid=valid,
        checks=tuple(checks),
        subject_id=str(envelope.get("envelope_id")) if isinstance(envelope.get("envelope_id"), str) else None,
    )


def build_mcp_host_context(
    *,
    envelope: Mapping[str, Any],
    host_id: str,
    actor_id: str,
    evaluation_time: str | datetime,
    server_id: str,
    server_origin: str,
    authorization_audience: str,
    authenticated: bool,
    schema_validator_id: str,
    schema_validation_status: str,
    capability_grants: Sequence[str],
    resource_scope_ids: Sequence[str],
    resource_resolution_status: str,
    symlinks_resolved: bool,
    consent_decision: str,
    consent_issued_at: str | datetime,
    consent_valid_until: str | datetime,
    transaction_status: str | None = None,
    rollback_available: bool | None = None,
    rollback_plan_sha256: str | None = None,
) -> dict[str, Any]:
    envelope_validation = validate_mcp_tool_call_envelope(envelope)
    if not envelope_validation.valid:
        raise MCPToolCallError("cannot bind an invalid MCP tool-call envelope")
    envelope_hash = str(envelope["envelope_sha256"])
    resources_hash = str(envelope["requested_resources_sha256"])
    consent: dict[str, Any] = {
        "decision": consent_decision,
        "actor_id": actor_id,
        "envelope_sha256": envelope_hash,
        "arguments_sha256": envelope.get("arguments_sha256"),
        "requested_resources_sha256": resources_hash,
        "issued_at": normalize_instant(consent_issued_at),
        "valid_until": normalize_instant(consent_valid_until),
    }
    consent_digest = sha256_json(consent)
    consent["consent_id"] = "ainir.mcp.consent." + consent_digest.removeprefix("sha256:")[:20]
    transaction: dict[str, Any] | None = None
    if transaction_status is not None:
        transaction = {
            "transaction_id": "ainir.mcp.transaction." + envelope_hash.removeprefix("sha256:")[:20],
            "status": transaction_status,
            "envelope_sha256": envelope_hash,
            "requested_resources_sha256": resources_hash,
            "rollback_available": rollback_available,
            "rollback_plan_sha256": rollback_plan_sha256,
        }
    context: dict[str, Any] = {
        "kind": MCP_HOST_CONTEXT_KIND,
        "version": MCP_HOST_CONTEXT_CONTRACT,
        "host_id": host_id,
        "actor_id": actor_id,
        "evaluation_time": normalize_instant(evaluation_time),
        "server_binding": {
            "server_id": server_id,
            "server_origin": server_origin,
            "authorization_audience": authorization_audience,
            "authenticated": authenticated,
            "protocol_version": envelope.get("protocol_version"),
            "method_header": (envelope.get("transport_observations") or {}).get("method_header"),
            "name_header": (envelope.get("transport_observations") or {}).get("name_header"),
        },
        "schema_validation": {
            "status": schema_validation_status,
            "validator_id": schema_validator_id,
            "input_schema_sha256": envelope.get("input_schema_sha256"),
            "arguments_sha256": envelope.get("arguments_sha256"),
        },
        "capability_grants": sorted(set(str(item) for item in capability_grants)),
        "resource_resolution": {
            "status": resource_resolution_status,
            "resolver_id": "host.resource-resolver.v1",
            "requested_resources_sha256": resources_hash,
            "scope_ids": sorted(set(str(item) for item in resource_scope_ids)),
            "symlinks_resolved": symlinks_resolved,
        },
        "consent": consent,
        "transaction": transaction,
        "production_runtime_ready": False,
    }
    digest = sha256_json(mcp_host_context_projection(context))
    context["context_sha256"] = digest
    context["context_id"] = "ainir.mcp.context." + digest.removeprefix("sha256:")[:20]
    return context


def validate_mcp_host_context(context: Mapping[str, Any]) -> MCPCheckReport:
    checks: list[dict[str, Any]] = []
    checks.append(_check("context.unknown_fields", not (set(context) - _HOST_CONTEXT_TOP_KEYS), [], sorted(set(context) - _HOST_CONTEXT_TOP_KEYS)))
    checks.append(_check("context.kind", context.get("kind") == MCP_HOST_CONTEXT_KIND, MCP_HOST_CONTEXT_KIND, context.get("kind")))
    checks.append(_check("context.version", context.get("version") == MCP_HOST_CONTEXT_CONTRACT, MCP_HOST_CONTEXT_CONTRACT, context.get("version")))
    expected_hash = sha256_json(mcp_host_context_projection(context))
    checks.append(_check("context.sha256", _sha(context.get("context_sha256")) and context.get("context_sha256") == expected_hash, expected_hash, context.get("context_sha256")))
    checks.append(_check("context.id", isinstance(context.get("context_id"), str) and str(context.get("context_id")).startswith("ainir.mcp.context."), "AiNIR MCP context id", context.get("context_id")))
    expected_id = "ainir.mcp.context." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("context.id_binding", context.get("context_id") == expected_id, expected_id, context.get("context_id")))
    for field_name in ("host_id", "actor_id"):
        checks.append(_check(f"context.{field_name}", _safe_token(context.get(field_name)), "safe token", context.get(field_name)))
    checks.append(_check("context.evaluation_time", _parse_instant(context.get("evaluation_time")) is not None, "ISO-8601 timestamp with timezone", context.get("evaluation_time")))
    server = context.get("server_binding")
    checks.append(_check("context.server_binding.object", isinstance(server, Mapping), "object", type(server).__name__))
    if isinstance(server, Mapping):
        checks.append(_check("context.server_binding.unknown_fields", not (set(server) - _HOST_SERVER_BINDING_KEYS), [], sorted(set(server) - _HOST_SERVER_BINDING_KEYS)))
        for field_name in ("server_id", "server_origin", "authorization_audience"):
            checks.append(_check(f"context.server_binding.{field_name}", _safe_token(server.get(field_name)), "safe token", server.get(field_name)))
        checks.append(_check("context.server_binding.authenticated", isinstance(server.get("authenticated"), bool), "boolean", type(server.get("authenticated")).__name__))
        checks.append(_check("context.server_binding.protocol_version", server.get("protocol_version") in SUPPORTED_MCP_PROTOCOL_VERSIONS, sorted(SUPPORTED_MCP_PROTOCOL_VERSIONS), server.get("protocol_version")))
        for field_name in ("method_header", "name_header"):
            value = server.get(field_name)
            checks.append(_check(f"context.server_binding.{field_name}", value is None or isinstance(value, str), "string|null", value))
    schema_validation = context.get("schema_validation")
    checks.append(_check("context.schema_validation.object", isinstance(schema_validation, Mapping), "object", type(schema_validation).__name__))
    if isinstance(schema_validation, Mapping):
        checks.append(_check("context.schema_validation.unknown_fields", not (set(schema_validation) - _HOST_SCHEMA_VALIDATION_KEYS), [], sorted(set(schema_validation) - _HOST_SCHEMA_VALIDATION_KEYS)))
        checks.append(_check("context.schema_validation.status", schema_validation.get("status") in {"passed", "failed", "not_checked"}, "passed|failed|not_checked", schema_validation.get("status")))
        checks.append(_check("context.schema_validation.validator_id", _safe_token(schema_validation.get("validator_id")), "safe token", schema_validation.get("validator_id")))
        for field_name in ("input_schema_sha256", "arguments_sha256"):
            checks.append(_check(f"context.schema_validation.{field_name}", _sha(schema_validation.get(field_name)), "sha256:<64 lowercase hex>", schema_validation.get(field_name)))
    grants = context.get("capability_grants")
    checks.append(_check("context.capability_grants", _unique_safe_strings(grants, allow_empty=True), "unique safe string array", grants))
    resolution = context.get("resource_resolution")
    checks.append(_check("context.resource_resolution.object", isinstance(resolution, Mapping), "object", type(resolution).__name__))
    if isinstance(resolution, Mapping):
        checks.append(_check("context.resource_resolution.unknown_fields", not (set(resolution) - _HOST_RESOURCE_RESOLUTION_KEYS), [], sorted(set(resolution) - _HOST_RESOURCE_RESOLUTION_KEYS)))
        checks.append(_check("context.resource_resolution.status", resolution.get("status") in {"passed", "failed", "not_checked"}, "passed|failed|not_checked", resolution.get("status")))
        checks.append(_check("context.resource_resolution.resolver_id", _safe_token(resolution.get("resolver_id")), "safe token", resolution.get("resolver_id")))
        checks.append(_check("context.resource_resolution.requested_resources_sha256", _sha(resolution.get("requested_resources_sha256")), "sha256:<64 lowercase hex>", resolution.get("requested_resources_sha256")))
        checks.append(_check("context.resource_resolution.scope_ids", _unique_safe_strings(resolution.get("scope_ids")), "non-empty unique safe string array", resolution.get("scope_ids")))
        checks.append(_check("context.resource_resolution.symlinks_resolved", isinstance(resolution.get("symlinks_resolved"), bool), "boolean", type(resolution.get("symlinks_resolved")).__name__))
    consent = context.get("consent")
    checks.append(_check("context.consent.object", isinstance(consent, Mapping), "object", type(consent).__name__))
    if isinstance(consent, Mapping):
        checks.append(_check("context.consent.unknown_fields", not (set(consent) - _HOST_CONSENT_KEYS), [], sorted(set(consent) - _HOST_CONSENT_KEYS)))
        checks.append(_check("context.consent.decision", consent.get("decision") in {"approved", "denied", "not_requested"}, "approved|denied|not_requested", consent.get("decision")))
        checks.append(_check("context.consent.actor_id", _safe_token(consent.get("actor_id")), "safe token", consent.get("actor_id")))
        for field_name in ("envelope_sha256", "arguments_sha256", "requested_resources_sha256"):
            checks.append(_check(f"context.consent.{field_name}", _sha(consent.get(field_name)), "sha256:<64 lowercase hex>", consent.get(field_name)))
        for field_name in ("issued_at", "valid_until"):
            checks.append(_check(f"context.consent.{field_name}", _parse_instant(consent.get(field_name)) is not None, "ISO-8601 timestamp with timezone", consent.get(field_name)))
        checks.append(_check("context.consent.consent_id", isinstance(consent.get("consent_id"), str) and str(consent.get("consent_id")).startswith("ainir.mcp.consent."), "AiNIR MCP consent id", consent.get("consent_id")))
        consent_projection = {key: _json_copy(value) for key, value in consent.items() if key != "consent_id"}
        expected_consent_id = "ainir.mcp.consent." + sha256_json(consent_projection).removeprefix("sha256:")[:20]
        checks.append(_check("context.consent.id_binding", consent.get("consent_id") == expected_consent_id, expected_consent_id, consent.get("consent_id")))
    transaction = context.get("transaction")
    checks.append(_check("context.transaction", transaction is None or isinstance(transaction, Mapping), "object|null", type(transaction).__name__))
    if isinstance(transaction, Mapping):
        checks.append(_check("context.transaction.unknown_fields", not (set(transaction) - _HOST_TRANSACTION_KEYS), [], sorted(set(transaction) - _HOST_TRANSACTION_KEYS)))
        checks.append(_check("context.transaction.transaction_id", isinstance(transaction.get("transaction_id"), str) and str(transaction.get("transaction_id")).startswith("ainir.mcp.transaction."), "AiNIR MCP transaction id", transaction.get("transaction_id")))
        transaction_envelope_hash = transaction.get("envelope_sha256")
        expected_transaction_id = (
            "ainir.mcp.transaction." + str(transaction_envelope_hash).removeprefix("sha256:")[:20]
            if _sha(transaction_envelope_hash)
            else None
        )
        checks.append(_check("context.transaction.id_binding", expected_transaction_id is not None and transaction.get("transaction_id") == expected_transaction_id, expected_transaction_id, transaction.get("transaction_id")))
        checks.append(_check("context.transaction.status", transaction.get("status") in {"prepared", "refused", "not_ready"}, "prepared|refused|not_ready", transaction.get("status")))
        for field_name in ("envelope_sha256", "requested_resources_sha256"):
            checks.append(_check(f"context.transaction.{field_name}", _sha(transaction.get(field_name)), "sha256:<64 lowercase hex>", transaction.get(field_name)))
        checks.append(_check("context.transaction.rollback_available", isinstance(transaction.get("rollback_available"), bool), "boolean", type(transaction.get("rollback_available")).__name__))
        rollback_hash = transaction.get("rollback_plan_sha256")
        checks.append(_check("context.transaction.rollback_plan_sha256", rollback_hash is None or _sha(rollback_hash), "sha256:<64 lowercase hex>|null", rollback_hash))
    checks.append(_check("context.production_runtime_ready", context.get("production_runtime_ready") is False, False, context.get("production_runtime_ready")))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        kind="AiNIRMCPHostContextValidationReport",
        version="ainir.mcp-host-context-validation-report.v1",
        valid=valid,
        checks=tuple(checks),
        subject_id=str(context.get("context_id")) if isinstance(context.get("context_id"), str) else None,
    )


def _annotation_checks(tool: Mapping[str, Any], envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = envelope.get("untrusted_metadata") if isinstance(envelope.get("untrusted_metadata"), Mapping) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), Mapping) else {}
    checks: list[dict[str, Any]] = []
    mutating = bool(tool.get("mutating"))
    destructive = bool(tool.get("destructive"))
    effects = set(tool.get("effects", []) or [])
    open_world = bool(effects & {"effect.network.outbound", "effect.financial.charge", "effect.account.modify", "effect.credentials.access"})
    if annotations.get("readOnlyHint") is True:
        checks.append(_check("annotations.read_only_not_understated", not mutating, False, mutating))
    if annotations.get("destructiveHint") is False:
        checks.append(_check("annotations.destructive_not_understated", not destructive, False, destructive))
    if annotations.get("openWorldHint") is False:
        checks.append(_check("annotations.open_world_not_understated", not open_world, False, open_world))
    if annotations.get("idempotentHint") is True:
        checks.append(_check("annotations.idempotence_not_overstated", tool.get("idempotent") is True, True, tool.get("idempotent")))
    return checks


def assess_mcp_tool_call(
    profile: LoadedMCPToolCallProfile,
    envelope: Mapping[str, Any],
    host_context: Mapping[str, Any],
) -> dict[str, Any]:
    profile_report = validate_mcp_tool_call_profile(profile)
    envelope_report = validate_mcp_tool_call_envelope(envelope)
    context_report = validate_mcp_host_context(host_context)
    checks: list[dict[str, Any]] = [
        _check("profile.valid", profile_report.valid, True, profile_report.overall_status),
        _check("envelope.valid", envelope_report.valid, True, envelope_report.overall_status),
        _check("context.valid", context_report.valid, True, context_report.overall_status),
    ]
    tool = _profile_tool_map(profile.data).get(str(envelope.get("tool_name")))
    checks.append(_check("profile.tool_known", tool is not None, "reviewed tool contract", envelope.get("tool_name")))
    if tool is None:
        tool = {}
    checks.append(_check("profile.binding", envelope.get("profile_id") == profile.profile_id, profile.profile_id, envelope.get("profile_id")))
    checks.append(_check("tool.descriptor_sha256", envelope.get("descriptor_sha256") == tool.get("descriptor_sha256"), tool.get("descriptor_sha256"), envelope.get("descriptor_sha256")))
    checks.append(_check("tool.input_schema_sha256", envelope.get("input_schema_sha256") == tool.get("input_schema_sha256"), tool.get("input_schema_sha256"), envelope.get("input_schema_sha256")))
    checks.append(_check("tool.output_schema_sha256", envelope.get("output_schema_sha256") == tool.get("output_schema_sha256"), tool.get("output_schema_sha256"), envelope.get("output_schema_sha256")))
    protocol = envelope.get("protocol_version")
    checks.append(_check("protocol.supported", protocol in set(profile.data.get("protocol_versions", []) or []), profile.data.get("protocol_versions"), protocol))
    transport = envelope.get("transport_observations") if isinstance(envelope.get("transport_observations"), Mapping) else {}
    if protocol == "2026-07-28":
        checks.append(_check("transport.method_header", transport.get("method_header") == "tools/call", "tools/call", transport.get("method_header")))
        checks.append(_check("transport.name_header", transport.get("name_header") == envelope.get("tool_name"), envelope.get("tool_name"), transport.get("name_header")))
    else:
        checks.append(_check("transport.method_header", transport.get("method_header") in {None, "tools/call"}, "null|tools/call", transport.get("method_header")))
        checks.append(_check("transport.name_header", transport.get("name_header") in {None, envelope.get("tool_name")}, f"null|{envelope.get('tool_name')}", transport.get("name_header")))
    checks.append(_check("task.not_requested", envelope.get("task_requested") is False, False, envelope.get("task_requested")))
    checks.append(_check("mrtr.not_present", envelope.get("mrtr_input_responses_present") is False, False, envelope.get("mrtr_input_responses_present")))
    max_bytes = tool.get("max_arguments_bytes")
    checks.append(_check("arguments.size", isinstance(max_bytes, int) and isinstance(envelope.get("arguments_size"), int) and envelope.get("arguments_size") <= max_bytes, f"<= {max_bytes}", envelope.get("arguments_size")))
    checks.append(_check("arguments.sensitive_paths", not envelope.get("sensitive_argument_paths"), [], envelope.get("sensitive_argument_paths")))
    normalization_findings = envelope.get("normalization_findings")
    critical_findings = [item for item in normalization_findings or [] if isinstance(item, Mapping) and item.get("severity") == "critical"]
    checks.append(_check("resources.normalized", not critical_findings, [], critical_findings))
    checks.extend(_annotation_checks(tool, envelope))

    server = host_context.get("server_binding") if isinstance(host_context.get("server_binding"), Mapping) else {}
    checks.append(_check("host.server.authenticated", server.get("authenticated") is True, True, server.get("authenticated")))
    checks.append(_check("host.server.id", server.get("server_id") == tool.get("server_id"), tool.get("server_id"), server.get("server_id")))
    checks.append(_check("host.server.origin", server.get("server_origin") == tool.get("server_origin"), tool.get("server_origin"), server.get("server_origin")))
    checks.append(_check("host.authorization.audience", server.get("authorization_audience") == tool.get("authorization_audience"), tool.get("authorization_audience"), server.get("authorization_audience")))
    checks.append(_check("host.protocol.binding", server.get("protocol_version") == protocol, protocol, server.get("protocol_version")))
    if protocol == "2026-07-28":
        checks.append(_check("host.method_header.binding", server.get("method_header") == "tools/call", "tools/call", server.get("method_header")))
        checks.append(_check("host.name_header.binding", server.get("name_header") == envelope.get("tool_name"), envelope.get("tool_name"), server.get("name_header")))

    schema_validation = host_context.get("schema_validation") if isinstance(host_context.get("schema_validation"), Mapping) else {}
    checks.append(_check("host.schema_validation.status", schema_validation.get("status") == "passed", "passed", schema_validation.get("status")))
    checks.append(_check("host.schema_validation.validator", _safe_token(schema_validation.get("validator_id")), "safe host validator id", schema_validation.get("validator_id")))
    checks.append(_check("host.schema_validation.schema_hash", schema_validation.get("input_schema_sha256") == envelope.get("input_schema_sha256"), envelope.get("input_schema_sha256"), schema_validation.get("input_schema_sha256")))
    checks.append(_check("host.schema_validation.arguments_hash", schema_validation.get("arguments_sha256") == envelope.get("arguments_sha256"), envelope.get("arguments_sha256"), schema_validation.get("arguments_sha256")))

    required_capabilities = sorted(set(tool.get("capabilities", []) or []))
    actual_capabilities = sorted(set(host_context.get("capability_grants", []) or []))
    checks.append(_check("host.capabilities.exact", actual_capabilities == required_capabilities, required_capabilities, actual_capabilities))

    resolution = host_context.get("resource_resolution") if isinstance(host_context.get("resource_resolution"), Mapping) else {}
    checks.append(_check("host.resource_resolution.status", resolution.get("status") == "passed", "passed", resolution.get("status")))
    checks.append(_check("host.resource_resolution.hash", resolution.get("requested_resources_sha256") == envelope.get("requested_resources_sha256"), envelope.get("requested_resources_sha256"), resolution.get("requested_resources_sha256")))
    workspace_resources = [item for item in envelope.get("requested_resources", []) or [] if isinstance(item, Mapping) and item.get("resource_type") == "workspace_path"]
    if workspace_resources:
        checks.append(_check("host.resource_resolution.symlinks", resolution.get("symlinks_resolved") is True, True, resolution.get("symlinks_resolved")))
    scope_ids = resolution.get("scope_ids")
    checks.append(_check("host.resource_resolution.scope_ids", _unique_safe_strings(scope_ids), "non-empty unique safe scope ids", scope_ids))

    evaluation_time = _parse_instant(host_context.get("evaluation_time"))
    consent = host_context.get("consent") if isinstance(host_context.get("consent"), Mapping) else {}
    checks.append(_check("host.consent.decision", consent.get("decision") == "approved", "approved", consent.get("decision")))
    checks.append(_check("host.consent.actor", consent.get("actor_id") == host_context.get("actor_id"), host_context.get("actor_id"), consent.get("actor_id")))
    checks.append(_check("host.consent.envelope", consent.get("envelope_sha256") == envelope.get("envelope_sha256"), envelope.get("envelope_sha256"), consent.get("envelope_sha256")))
    checks.append(_check("host.consent.arguments", consent.get("arguments_sha256") == envelope.get("arguments_sha256"), envelope.get("arguments_sha256"), consent.get("arguments_sha256")))
    checks.append(_check("host.consent.resources", consent.get("requested_resources_sha256") == envelope.get("requested_resources_sha256"), envelope.get("requested_resources_sha256"), consent.get("requested_resources_sha256")))
    issued_at = _parse_instant(consent.get("issued_at"))
    valid_until = _parse_instant(consent.get("valid_until"))
    consent_window_ok = evaluation_time is not None and issued_at is not None and valid_until is not None and issued_at <= evaluation_time < valid_until
    checks.append(_check("host.consent.validity", consent_window_ok, "issued_at <= evaluation_time < valid_until", {"issued_at": consent.get("issued_at"), "evaluation_time": host_context.get("evaluation_time"), "valid_until": consent.get("valid_until")}))

    transaction = host_context.get("transaction") if isinstance(host_context.get("transaction"), Mapping) else None
    if tool.get("transaction_required") is True:
        checks.append(_check("host.transaction.present", transaction is not None, "prepared transaction", None if transaction is None else transaction.get("status")))
        if transaction is not None:
            checks.append(_check("host.transaction.status", transaction.get("status") == "prepared", "prepared", transaction.get("status")))
            checks.append(_check("host.transaction.envelope", transaction.get("envelope_sha256") == envelope.get("envelope_sha256"), envelope.get("envelope_sha256"), transaction.get("envelope_sha256")))
            checks.append(_check("host.transaction.resources", transaction.get("requested_resources_sha256") == envelope.get("requested_resources_sha256"), envelope.get("requested_resources_sha256"), transaction.get("requested_resources_sha256")))
            if tool.get("rollback_required") is True:
                checks.append(_check("host.transaction.rollback_available", transaction.get("rollback_available") is True, True, transaction.get("rollback_available")))
                checks.append(_check("host.transaction.rollback_plan", _sha(transaction.get("rollback_plan_sha256")), "sha256:<64 lowercase hex>", transaction.get("rollback_plan_sha256")))
    else:
        checks.append(_check("host.transaction.not_required", transaction is None, None, type(transaction).__name__ if transaction is not None else None))

    structural_valid = profile_report.valid and envelope_report.valid and context_report.valid
    failed_checks = [item for item in checks if item["status"] == "failed"]
    if failed_checks:
        status = "invalid" if not structural_valid else "refused"
    elif tool.get("decision_mode") == "review_required":
        status = "review_required"
    else:
        status = "passed"
    if status == "passed":
        required_host_actions = list(MCP_PASSED_HOST_ACTIONS)
    elif status == "review_required":
        required_host_actions = list(MCP_REVIEW_HOST_ACTIONS)
    else:
        required_host_actions = list(MCP_REFUSED_HOST_ACTIONS)
    assessment: dict[str, Any] = {
        "kind": MCP_TOOL_CALL_ASSESSMENT_KIND,
        "version": MCP_TOOL_CALL_ASSESSMENT_CONTRACT,
        "overall_status": status,
        "host_handoff_allowed": status == "passed",
        "execution_performed": False,
        "profile_id": profile.profile_id,
        "profile_sha256": profile.data.get("profile_sha256"),
        "envelope_id": envelope.get("envelope_id"),
        "envelope_sha256": envelope.get("envelope_sha256"),
        "context_id": host_context.get("context_id"),
        "context_sha256": host_context.get("context_sha256"),
        "tool_name": envelope.get("tool_name"),
        "risk_class": tool.get("risk_class"),
        "effects": sorted(set(tool.get("effects", []) or [])),
        "capabilities": required_capabilities,
        "checks": checks,
        "required_host_actions": required_host_actions,
        "production_runtime_ready": False,
    }
    digest = sha256_json(mcp_tool_call_assessment_projection(assessment))
    assessment["assessment_sha256"] = digest
    assessment["assessment_id"] = "ainir.mcp.assessment." + digest.removeprefix("sha256:")[:20]
    return assessment


def validate_mcp_tool_call_assessment(assessment: Mapping[str, Any]) -> MCPCheckReport:
    checks: list[dict[str, Any]] = []
    checks.append(_check("assessment.unknown_fields", not (set(assessment) - _ASSESSMENT_TOP_KEYS), [], sorted(set(assessment) - _ASSESSMENT_TOP_KEYS)))
    checks.append(_check("assessment.kind", assessment.get("kind") == MCP_TOOL_CALL_ASSESSMENT_KIND, MCP_TOOL_CALL_ASSESSMENT_KIND, assessment.get("kind")))
    checks.append(_check("assessment.version", assessment.get("version") == MCP_TOOL_CALL_ASSESSMENT_CONTRACT, MCP_TOOL_CALL_ASSESSMENT_CONTRACT, assessment.get("version")))
    expected_hash = sha256_json(mcp_tool_call_assessment_projection(assessment))
    checks.append(_check("assessment.sha256", _sha(assessment.get("assessment_sha256")) and assessment.get("assessment_sha256") == expected_hash, expected_hash, assessment.get("assessment_sha256")))
    expected_id = "ainir.mcp.assessment." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("assessment.id_binding", assessment.get("assessment_id") == expected_id, expected_id, assessment.get("assessment_id")))
    status = assessment.get("overall_status")
    checks.append(_check("assessment.status", status in {"passed", "refused", "invalid", "review_required"}, "passed|refused|invalid|review_required", status))
    checks.append(_check("assessment.execution_performed", assessment.get("execution_performed") is False, False, assessment.get("execution_performed")))
    checks.append(_check("assessment.production_runtime_ready", assessment.get("production_runtime_ready") is False, False, assessment.get("production_runtime_ready")))
    handoff = assessment.get("host_handoff_allowed")
    checks.append(_check("assessment.handoff_consistency", handoff is (status == "passed"), status == "passed", handoff))
    inner = assessment.get("checks")
    checks.append(_check("assessment.checks.array", isinstance(inner, list) and bool(inner), "non-empty array", type(inner).__name__))
    if isinstance(inner, list):
        seen_checks: set[str] = set()
        for index, item in enumerate(inner):
            prefix = f"assessment.checks[{index}]"
            if not isinstance(item, Mapping):
                checks.append(_check(prefix, False, "object", type(item).__name__))
                continue
            checks.append(_check(f"{prefix}.unknown_fields", not (set(item) - _ASSESSMENT_CHECK_KEYS), [], sorted(set(item) - _ASSESSMENT_CHECK_KEYS)))
            check_name = item.get("check")
            check_name_ok = isinstance(check_name, str) and bool(check_name) and check_name not in seen_checks
            checks.append(_check(f"{prefix}.check", check_name_ok, "unique non-empty check id", check_name))
            if isinstance(check_name, str):
                seen_checks.add(check_name)
            checks.append(_check(f"{prefix}.status", item.get("status") in {"passed", "failed"}, "passed|failed", item.get("status")))
        failed = [item.get("check") for item in inner if isinstance(item, Mapping) and item.get("status") == "failed"]
        status_checks_ok = (status in {"passed", "review_required"} and not failed) or (status in {"refused", "invalid"} and bool(failed))
        checks.append(_check("assessment.status_failed_checks", status_checks_ok, "passed/review_required=>0 failed; refused/invalid=>failed check", failed))
        if status == "review_required":
            actions = assessment.get("required_host_actions")
            checks.append(_check("assessment.review_required_action", isinstance(actions, list) and "obtain_final_destructive_action_confirmation" in actions, "final destructive-action confirmation", actions))
    actions = assessment.get("required_host_actions")
    expected_actions: tuple[str, ...]
    if status == "passed":
        expected_actions = MCP_PASSED_HOST_ACTIONS
    elif status == "review_required":
        expected_actions = MCP_REVIEW_HOST_ACTIONS
    else:
        expected_actions = MCP_REFUSED_HOST_ACTIONS
    actions_valid = _unique_safe_strings(actions) and tuple(actions) == expected_actions
    checks.append(_check("assessment.required_host_actions", actions_valid, list(expected_actions), actions))
    for field_name in ("profile_sha256", "envelope_sha256", "context_sha256"):
        checks.append(_check(f"assessment.{field_name}", _sha(assessment.get(field_name)), "sha256:<64 lowercase hex>", assessment.get(field_name)))
    envelope_hash = assessment.get("envelope_sha256")
    context_hash = assessment.get("context_sha256")
    expected_envelope_id = "ainir.mcp.envelope." + str(envelope_hash).removeprefix("sha256:")[:20] if _sha(envelope_hash) else None
    expected_context_id = "ainir.mcp.context." + str(context_hash).removeprefix("sha256:")[:20] if _sha(context_hash) else None
    checks.append(_check("assessment.envelope_id_binding", expected_envelope_id is not None and assessment.get("envelope_id") == expected_envelope_id, expected_envelope_id, assessment.get("envelope_id")))
    checks.append(_check("assessment.context_id_binding", expected_context_id is not None and assessment.get("context_id") == expected_context_id, expected_context_id, assessment.get("context_id")))
    checks.append(_check("assessment.profile_id", isinstance(assessment.get("profile_id"), str) and bool(_PROFILE_ID_RE.fullmatch(str(assessment.get("profile_id")))), "safe profile id", assessment.get("profile_id")))
    checks.append(_check("assessment.tool_name", isinstance(assessment.get("tool_name"), str) and bool(_SAFE_TOOL_NAME_RE.fullmatch(str(assessment.get("tool_name")))), "MCP tool name", assessment.get("tool_name")))
    semantic_terms_required = status in {"passed", "review_required"}
    risk_class = assessment.get("risk_class")
    risk_ok = risk_class in MCP_RISK_CLASSES if semantic_terms_required else risk_class is None or risk_class in MCP_RISK_CLASSES
    checks.append(_check("assessment.risk_class", risk_ok, "reviewed risk class; non-null for passed/review_required", risk_class))
    effects = assessment.get("effects")
    capabilities = assessment.get("capabilities")
    effects_ok = _unique_safe_strings(effects, allow_empty=not semantic_terms_required) and set(effects or []).issubset(MCP_EFFECT_VOCABULARY)
    capabilities_ok = _unique_safe_strings(capabilities, allow_empty=not semantic_terms_required) and set(capabilities or []).issubset(MCP_CAPABILITY_VOCABULARY)
    checks.append(_check("assessment.effects", effects_ok, "reviewed effect vocabulary; non-empty for passed/review_required", effects))
    checks.append(_check("assessment.capabilities", capabilities_ok, "reviewed capability vocabulary; non-empty for passed/review_required", capabilities))
    valid = all(item["status"] == "passed" for item in checks)
    return MCPCheckReport(
        kind="AiNIRMCPToolCallAssessmentValidationReport",
        version="ainir.mcp-tool-call-assessment-validation-report.v1",
        valid=valid,
        checks=tuple(checks),
        subject_id=str(assessment.get("assessment_id")) if isinstance(assessment.get("assessment_id"), str) else None,
    )


def write_mcp_artifact(path: str | Path, artifact: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "BUILTIN_MCP_PROFILE_ID",
    "BUILTIN_MCP_PROFILE_PACKAGE",
    "HostOwnedMCPToolCallAdapter",
    "LoadedMCPToolCallProfile",
    "MCP_CAPABILITY_VOCABULARY",
    "MCP_EFFECT_VOCABULARY",
    "MCP_PASSED_HOST_ACTIONS",
    "MCP_REFUSED_HOST_ACTIONS",
    "MCP_REVIEW_HOST_ACTIONS",
    "MCP_RISK_CLASSES",
    "MCPCheckReport",
    "MCPToolCallError",
    "SUPPORTED_MCP_PROTOCOL_VERSIONS",
    "assess_mcp_tool_call",
    "build_mcp_host_context",
    "build_mcp_tool_call_envelope",
    "load_json_mapping",
    "load_mcp_tool_call_profile",
    "materialized_mcp_profile_source",
    "mcp_host_context_projection",
    "mcp_tool_call_assessment_projection",
    "mcp_tool_call_envelope_projection",
    "mcp_tool_call_profile_projection",
    "normalize_instant",
    "validate_mcp_host_context",
    "validate_mcp_tool_call_assessment",
    "validate_mcp_tool_call_envelope",
    "validate_mcp_tool_call_profile",
    "validate_mcp_tool_descriptor",
    "write_mcp_artifact",
]
