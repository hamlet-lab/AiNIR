"""Deterministic conformance runner for reviewed MCP tool-call profiles.

The cases exercise only host-owned preflight semantics.  No MCP transport is
opened and no tool is executed.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources as importlib_resources
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from .canonical import canonical_json, sha256_json
from .contracts import (
    MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT,
    MCP_TOOL_CALL_CONFORMANCE_PACK_KIND,
    MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT,
    MCP_TOOL_CALL_CONFORMANCE_REPORT_KIND,
)
from .core import load_yaml_no_duplicate_keys
from .mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    BUILTIN_MCP_PROFILE_PACKAGE,
    MCPToolCallError,
    assess_mcp_tool_call,
    build_mcp_host_context,
    build_mcp_tool_call_envelope,
    load_json_mapping,
    materialized_mcp_profile_source,
    validate_mcp_tool_call_assessment,
    validate_mcp_tool_call_profile,
)

_PACK_TOP_KEYS = frozenset({
    "kind", "version", "pack_id", "profile_id", "cases", "pack_sha256",
    "production_runtime_ready",
})
_CASE_KEYS = frozenset({
    "case_id", "category", "scenario", "fixtures", "expected_status",
    "required_failed_checks", "required_host_actions", "notes",
})
_FIXTURE_KEYS = frozenset({"descriptor", "call", "transport", "host_input"})
_ALLOWED_CATEGORIES = frozenset({"positive", "negative", "mutation", "review"})
_ALLOWED_STATUSES = frozenset({"passed", "refused", "invalid", "review_required"})
_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")


class MCPConformanceError(ValueError):
    """Raised when the reference conformance pack is malformed."""


def _copy_resource_tree(source: Any, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_resource_tree(item, destination)
        else:
            destination.write_bytes(item.read_bytes())


def mcp_conformance_pack_projection(pack: Mapping[str, Any]) -> dict[str, Any]:
    return {key: json.loads(canonical_json(value)) for key, value in pack.items() if key != "pack_sha256"}


def mcp_conformance_report_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    return {key: json.loads(canonical_json(value)) for key, value in report.items() if key not in {"report_sha256", "output_dir"}}


def load_bundled_mcp_conformance_pack() -> dict[str, Any]:
    resource = importlib_resources.files(BUILTIN_MCP_PROFILE_PACKAGE).joinpath("cases.yaml")
    raw = resource.read_text(encoding="utf-8")
    data = load_yaml_no_duplicate_keys(raw)
    if not isinstance(data, dict):
        raise MCPConformanceError("MCP conformance pack root must be an object")
    return data


def load_mcp_conformance_pack(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise MCPConformanceError(f"cannot read MCP conformance pack {source}: {exc}") from exc
    if len(raw) > 1_000_000:
        raise MCPConformanceError("MCP conformance pack exceeds 1000000 bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MCPConformanceError("MCP conformance pack must be UTF-8") from exc
    try:
        data = load_yaml_no_duplicate_keys(text)
    except Exception as exc:
        raise MCPConformanceError(f"invalid MCP conformance YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise MCPConformanceError("MCP conformance pack root must be an object")
    return data


def _safe_fixture_path(root: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise MCPConformanceError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise MCPConformanceError(f"{label} must remain inside the profile root")
    target = (root / relative).resolve()
    resolved_root = root.resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise MCPConformanceError(f"{label} escapes the profile root") from exc
    if not target.is_file():
        raise MCPConformanceError(f"{label} does not identify a regular file: {value}")
    return target


def validate_mcp_conformance_pack(
    pack: Mapping[str, Any],
    *,
    expected_profile_id: str = BUILTIN_MCP_PROFILE_ID,
    profile_root: str | Path | None = None,
    allow_scenarios: bool = True,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, expected: Any, actual: Any) -> None:
        checks.append({"check": name, "status": "passed" if passed else "failed", "expected": expected, "actual": actual})

    check("pack.unknown_fields", not (set(pack) - _PACK_TOP_KEYS), [], sorted(set(pack) - _PACK_TOP_KEYS))
    check("pack.kind", pack.get("kind") == MCP_TOOL_CALL_CONFORMANCE_PACK_KIND, MCP_TOOL_CALL_CONFORMANCE_PACK_KIND, pack.get("kind"))
    check("pack.version", pack.get("version") == MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT, MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT, pack.get("version"))
    profile_id = pack.get("profile_id")
    check("pack.profile_id.format", isinstance(profile_id, str) and bool(_PROFILE_ID_RE.fullmatch(profile_id)), "safe profile id", profile_id)
    check("pack.profile_id.binding", profile_id == expected_profile_id, expected_profile_id, profile_id)
    check("pack.production_runtime_ready", pack.get("production_runtime_ready") is False, False, pack.get("production_runtime_ready"))
    cases = pack.get("cases")
    check("pack.cases", isinstance(cases, list) and bool(cases), "non-empty array", type(cases).__name__)
    seen: set[str] = set()
    if isinstance(cases, list):
        for index, case in enumerate(cases):
            prefix = f"pack.cases[{index}]"
            if not isinstance(case, Mapping):
                check(prefix, False, "object", type(case).__name__)
                continue
            check(f"{prefix}.unknown_fields", not (set(case) - _CASE_KEYS), [], sorted(set(case) - _CASE_KEYS))
            case_id = case.get("case_id")
            case_id_ok = isinstance(case_id, str) and bool(case_id) and case_id not in seen
            check(f"{prefix}.case_id", case_id_ok, "unique non-empty string", case_id)
            if isinstance(case_id, str):
                seen.add(case_id)
            check(f"{prefix}.category", case.get("category") in _ALLOWED_CATEGORIES, sorted(_ALLOWED_CATEGORIES), case.get("category"))
            scenario = case.get("scenario")
            fixtures = case.get("fixtures")
            has_scenario = isinstance(scenario, str) and bool(scenario)
            has_fixtures = isinstance(fixtures, Mapping)
            check(f"{prefix}.input_mode", has_scenario ^ has_fixtures, "exactly one of scenario or fixtures", {"scenario": scenario, "fixtures": fixtures})
            if has_scenario:
                check(f"{prefix}.scenario", allow_scenarios, "scenario mode allowed only for bundled profiles", scenario)
            if has_fixtures:
                unknown_fixture_fields = sorted(set(fixtures) - _FIXTURE_KEYS)
                check(f"{prefix}.fixtures.unknown_fields", not unknown_fixture_fields, [], unknown_fixture_fields)
                missing_fixture_fields = sorted(_FIXTURE_KEYS - set(fixtures))
                check(f"{prefix}.fixtures.required", not missing_fixture_fields, sorted(_FIXTURE_KEYS), sorted(fixtures))
                for field in sorted(_FIXTURE_KEYS):
                    value = fixtures.get(field)
                    relative_ok = isinstance(value, str) and bool(value) and not Path(value).is_absolute() and ".." not in Path(value).parts
                    check(f"{prefix}.fixtures.{field}", relative_ok, "safe relative path", value)
                    if relative_ok and profile_root is not None:
                        try:
                            _safe_fixture_path(Path(profile_root), value, label=f"{prefix}.fixtures.{field}")
                        except MCPConformanceError as exc:
                            check(f"{prefix}.fixtures.{field}.exists", False, "existing in-root file", str(exc))
                        else:
                            check(f"{prefix}.fixtures.{field}.exists", True, "existing in-root file", value)
            check(f"{prefix}.expected_status", case.get("expected_status") in _ALLOWED_STATUSES, sorted(_ALLOWED_STATUSES), case.get("expected_status"))
            for field in ("required_failed_checks", "required_host_actions"):
                value = case.get(field, [])
                valid = isinstance(value, list) and all(isinstance(item, str) and item for item in value) and len(set(value)) == len(value)
                check(f"{prefix}.{field}", valid, "unique string array", value)
    expected_hash = sha256_json(mcp_conformance_pack_projection(pack))
    check("pack.sha256", pack.get("pack_sha256") == expected_hash, expected_hash, pack.get("pack_sha256"))
    return checks


def _load_descriptor(profile_root: Path, tool_name: str) -> dict[str, Any]:
    return load_json_mapping(profile_root / "descriptors" / f"{tool_name}.json", label=f"descriptor {tool_name}")


def _fixture_inputs(profile_root: Path, fixtures: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    descriptor = load_json_mapping(_safe_fixture_path(profile_root, fixtures.get("descriptor"), label="descriptor fixture"), label="MCP tool descriptor fixture")
    call = load_json_mapping(_safe_fixture_path(profile_root, fixtures.get("call"), label="call fixture"), label="MCP tools/call fixture")
    transport = load_json_mapping(_safe_fixture_path(profile_root, fixtures.get("transport"), label="transport fixture"), label="MCP transport fixture")
    host = load_json_mapping(_safe_fixture_path(profile_root, fixtures.get("host_input"), label="host_input fixture"), label="MCP host-input fixture")
    return descriptor, call, transport, host


def _scenario_inputs(profile_root: Path, scenario: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    tool_name = "workspace.read_text"
    arguments: dict[str, Any] = {"path": "docs/README.md"}
    descriptor = _load_descriptor(profile_root, tool_name)
    transport = {"protocol_version": "2026-07-28", "method_header": "tools/call", "name_header": tool_name}
    call: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": "case-" + scenario,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments, "_meta": {"client": "ainir-reference-host"}},
    }
    host: dict[str, Any] = {
        "host_id": "host.reference",
        "actor_id": "human.operator",
        "evaluation_time": "2026-08-10T00:00:00Z",
        "server_id": "mcp.server.workspace.reference",
        "server_origin": "mcp+stdio://workspace.reference",
        "authorization_audience": "mcp.server.workspace.reference",
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

    if scenario in {
        "safe_write",
        "missing_transaction",
        "missing_rollback",
        "annotation_understates_write",
        "credential_value_in_content",
    }:
        tool_name = "workspace.write_text"
        descriptor = _load_descriptor(profile_root, tool_name)
        arguments = {"path": "notes/output.txt", "content": "bounded write"}
        call["params"]["name"] = tool_name
        call["params"]["arguments"] = arguments
        transport["name_header"] = tool_name
        host["capability_grants"] = ["cap.resource.write"]
        host["resource_scope_ids"] = ["scope.workspace.notes"]
        host["transaction_status"] = "prepared"
        host["rollback_available"] = True
        host["rollback_plan_sha256"] = "sha256:" + "1" * 64
    elif scenario == "destructive_delete_review":
        tool_name = "workspace.delete_file"
        descriptor = _load_descriptor(profile_root, tool_name)
        arguments = {"path": "tmp/remove.txt"}
        call["params"]["name"] = tool_name
        call["params"]["arguments"] = arguments
        transport["name_header"] = tool_name
        host["capability_grants"] = ["cap.resource.delete"]
        host["resource_scope_ids"] = ["scope.workspace.tmp"]
        host["transaction_status"] = "prepared"
        host["rollback_available"] = True
        host["rollback_plan_sha256"] = "sha256:" + "2" * 64

    if scenario == "unknown_tool":
        descriptor = json.loads(canonical_json(descriptor))
        descriptor["name"] = "workspace.unknown"
        call["params"]["name"] = "workspace.unknown"
        transport["name_header"] = "workspace.unknown"
    elif scenario == "descriptor_mismatch":
        descriptor = _load_descriptor(profile_root, "workspace.write_text")
    elif scenario == "schema_extra_argument":
        call["params"]["arguments"] = {"path": "docs/README.md", "unexpected": True}
    elif scenario == "path_traversal":
        call["params"]["arguments"] = {"path": "../secrets.txt"}
    elif scenario == "absolute_path":
        call["params"]["arguments"] = {"path": "/etc/passwd"}
    elif scenario == "windows_ads_path":
        call["params"]["arguments"] = {"path": "docs/report.txt:secret"}
    elif scenario == "windows_reserved_device_path":
        call["params"]["arguments"] = {"path": "CON.txt"}
    elif scenario == "control_character_path":
        call["params"]["arguments"] = {"path": "docs/\nsecret.txt"}
    elif scenario == "credential_argument":
        call["params"]["arguments"] = {"path": "docs/README.md", "access_token": "not-a-real-token"}
    elif scenario == "credential_meta":
        call["params"]["_meta"] = {"access_token": "not-a-real-token"}
    elif scenario == "credential_value_in_content":
        call["params"]["arguments"]["content"] = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"
    elif scenario == "wrong_audience":
        host["authorization_audience"] = "mcp.server.other"
    elif scenario == "missing_consent":
        host["consent_decision"] = "denied"
    elif scenario == "expired_consent":
        host["consent_valid_until"] = "2026-08-09T23:59:59Z"
    elif scenario == "capability_widening":
        host["capability_grants"] = ["cap.resource.read", "cap.resource.write"]
    elif scenario == "missing_transaction":
        host["transaction_status"] = None
        host["rollback_available"] = None
        host["rollback_plan_sha256"] = None
    elif scenario == "missing_rollback":
        host["rollback_available"] = False
        host["rollback_plan_sha256"] = None
    elif scenario == "annotation_understates_write":
        descriptor = json.loads(canonical_json(descriptor))
        descriptor.setdefault("annotations", {})["readOnlyHint"] = True
    elif scenario == "task_requested":
        call["params"]["task"] = {"ttl": 60}
    elif scenario == "mrtr_present":
        call["params"]["inputResponses"] = [{"requestId": "r1", "value": "x"}]
    elif scenario == "protocol_header_mismatch":
        transport["name_header"] = "workspace.other"
    elif scenario == "unauthenticated_server":
        host["authenticated"] = False
    elif scenario == "symlink_unresolved":
        host["symlinks_resolved"] = False
    elif scenario not in {"safe_read", "safe_write", "destructive_delete_review"}:
        raise MCPConformanceError(f"unknown MCP conformance scenario {scenario!r}")
    return descriptor, call, transport, host


@dataclass(frozen=True)
class MCPConformanceCaseResult:
    case_id: str
    category: str
    scenario: str
    expected_status: str
    actual_status: str
    passed: bool
    failed_checks: tuple[str, ...]
    required_host_actions: tuple[str, ...]
    assessment_id: str | None
    assessment_sha256: str | None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "scenario": self.scenario,
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "passed": self.passed,
            "failed_checks": list(self.failed_checks),
            "required_host_actions": list(self.required_host_actions),
            "assessment_id": self.assessment_id,
            "assessment_sha256": self.assessment_sha256,
            "notes": self.notes,
        }


def run_mcp_conformance(
    profile_source: str | Path = BUILTIN_MCP_PROFILE_ID,
    *,
    pack_source: str | Path | None = None,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    results: list[MCPConformanceCaseResult] = []
    with materialized_mcp_profile_source(profile_source) as profile:
        profile_report = validate_mcp_tool_call_profile(profile)
        if not profile_report.valid:
            raise MCPConformanceError("MCP tool-call profile failed validation")
        if pack_source is None:
            pack = load_bundled_mcp_conformance_pack() if profile.builtin else load_mcp_conformance_pack(profile.root / "cases.yaml")
        else:
            pack = load_mcp_conformance_pack(pack_source)
        pack_checks = validate_mcp_conformance_pack(
            pack,
            expected_profile_id=profile.profile_id,
            profile_root=profile.root,
            allow_scenarios=profile.builtin,
        )
        failed_pack_checks = [item for item in pack_checks if item["status"] != "passed"]
        if failed_pack_checks:
            raise MCPConformanceError("MCP conformance pack failed validation: " + ", ".join(item["check"] for item in failed_pack_checks[:8]))
        for case in pack.get("cases", []):
            case_id = str(case["case_id"])
            scenario = str(case.get("scenario") or "fixture")
            expected_status = str(case["expected_status"])
            notes: list[str] = []
            try:
                fixtures = case.get("fixtures")
                if isinstance(fixtures, Mapping):
                    descriptor, call, transport, host_values = _fixture_inputs(profile.root, fixtures)
                elif profile.builtin and profile.profile_id == BUILTIN_MCP_PROFILE_ID:
                    descriptor, call, transport, host_values = _scenario_inputs(profile.root, scenario)
                else:
                    raise MCPConformanceError("external MCP profiles must use file-bound fixtures")
                envelope = build_mcp_tool_call_envelope(profile, descriptor, call, transport)
                host_context = build_mcp_host_context(envelope=envelope, **host_values)
                assessment = assess_mcp_tool_call(profile, envelope, host_context)
                assessment_validation = validate_mcp_tool_call_assessment(assessment)
                actual_status = str(assessment.get("overall_status"))
                failed_checks = tuple(sorted(str(item.get("check")) for item in assessment.get("checks", []) if isinstance(item, Mapping) and item.get("status") == "failed"))
                actions = tuple(sorted(str(item) for item in assessment.get("required_host_actions", []) if isinstance(item, str)))
                required_failed = set(str(item) for item in case.get("required_failed_checks", []))
                required_actions = set(str(item) for item in case.get("required_host_actions", []))
                passed = (
                    assessment_validation.valid
                    and actual_status == expected_status
                    and required_failed.issubset(set(failed_checks))
                    and required_actions.issubset(set(actions))
                    and assessment.get("execution_performed") is False
                    and assessment.get("production_runtime_ready") is False
                )
                if actual_status != expected_status:
                    notes.append(f"expected status {expected_status}, got {actual_status}")
                missing_checks = sorted(required_failed - set(failed_checks))
                if missing_checks:
                    notes.append(f"missing failed checks {missing_checks}")
                missing_actions = sorted(required_actions - set(actions))
                if missing_actions:
                    notes.append(f"missing host actions {missing_actions}")
                if not assessment_validation.valid:
                    notes.append("generated assessment failed its public contract validation")
                result = MCPConformanceCaseResult(
                    case_id=case_id,
                    category=str(case["category"]),
                    scenario=scenario,
                    expected_status=expected_status,
                    actual_status=actual_status,
                    passed=passed,
                    failed_checks=failed_checks,
                    required_host_actions=actions,
                    assessment_id=str(assessment.get("assessment_id")) if assessment.get("assessment_id") else None,
                    assessment_sha256=str(assessment.get("assessment_sha256")) if assessment.get("assessment_sha256") else None,
                    notes="; ".join(notes),
                )
            except (MCPToolCallError, MCPConformanceError) as exc:
                actual_status = "invalid"
                expected_exception = expected_status == "invalid"
                result = MCPConformanceCaseResult(
                    case_id=case_id,
                    category=str(case["category"]),
                    scenario=scenario,
                    expected_status=expected_status,
                    actual_status=actual_status,
                    passed=expected_exception,
                    failed_checks=("normalization.exception",),
                    required_host_actions=(),
                    assessment_id=None,
                    assessment_sha256=None,
                    notes=str(exc),
                )
            results.append(result)

        report: dict[str, Any] = {
            "kind": MCP_TOOL_CALL_CONFORMANCE_REPORT_KIND,
            "version": MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT,
            "profile_id": profile.profile_id,
            "profile_sha256": profile.data.get("profile_sha256"),
            "pack_id": pack.get("pack_id"),
            "pack_sha256": pack.get("pack_sha256"),
            "overall_status": "passed" if results and all(item.passed for item in results) else "failed",
            "case_count": len(results),
            "passed": sum(1 for item in results if item.passed),
            "failed": sum(1 for item in results if not item.passed),
            "results": [item.as_dict() for item in results],
            "execution_performed": False,
            "trust_gate_override_allowed": False,
            "production_runtime_ready": False,
        }
    report["report_sha256"] = sha256_json(mcp_conformance_report_projection(report))
    if out_dir is not None:
        output = Path(out_dir)
        output.mkdir(parents=True, exist_ok=True)
        report["output_dir"] = str(output.resolve())
        (output / "mcp_tool_call_conformance_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _write_junit(report, output / "mcp_tool_call_conformance_report.junit.xml")
    return report


def run_bundled_mcp_conformance(*, out_dir: str | Path | None = None) -> dict[str, Any]:
    return run_mcp_conformance(BUILTIN_MCP_PROFILE_ID, out_dir=out_dir)


def _write_junit(report: Mapping[str, Any], path: Path) -> None:
    suite = ET.Element("testsuite", {
        "name": "AiNIR MCP tool-call conformance",
        "tests": str(report.get("case_count", 0)),
        "failures": str(report.get("failed", 0)),
    })
    for item in report.get("results", []) or []:
        if not isinstance(item, Mapping):
            continue
        case = ET.SubElement(suite, "testcase", {"classname": str(item.get("category")), "name": str(item.get("case_id"))})
        if not item.get("passed"):
            failure = ET.SubElement(case, "failure", {"message": str(item.get("notes") or "conformance mismatch")})
            failure.text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        output = ET.SubElement(case, "system-out")
        output.text = json.dumps(item, ensure_ascii=False, sort_keys=True)
    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


__all__ = [
    "MCPConformanceError",
    "load_mcp_conformance_pack",
    "load_bundled_mcp_conformance_pack",
    "mcp_conformance_pack_projection",
    "mcp_conformance_report_projection",
    "run_mcp_conformance",
    "run_bundled_mcp_conformance",
    "validate_mcp_conformance_pack",
]
