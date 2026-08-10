"""Profile Manifest v1 loading, validation, inspection, and scaffolding.

A workflow profile is an additive, non-executing semantic extension surface.
It may add workflow and operation contracts for isolated conformance runs, but
it cannot replace packaged registries, remove core gates, or turn unknown
semantics into an allow decision.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from hashlib import sha256
from importlib import resources as importlib_resources
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Iterator, Mapping

import yaml

from .canonical import sha256_bytes, sha256_json
from .contracts import (
    CONFORMANCE_PACK_CONTRACT,
    CONFORMANCE_PACK_KIND,
    PROFILE_MANIFEST_CONTRACT,
    PROFILE_MANIFEST_KIND,
)
from .core import MAX_YAML_BYTES, load_yaml_no_duplicate_keys
from .resources import read_registry_text
from .safety_registry import SafetyRegistry

BUILTIN_PROFILE_ID = "ainir.public-demo.v1"
BUILTIN_PROFILE_PACKAGE = "ainir.profile_packs.public_demo_v1"
PROFILE_MANIFEST_FILENAME = "profile.yaml"
REQUIRED_CONFORMANCE_CATEGORIES = frozenset({"positive", "negative", "mutation", "replay"})

_SAFE_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_SAFE_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.+-]{0,63}$")
_SAFE_WORKFLOW_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")

_TOP_LEVEL_KEYS = {
    "kind",
    "version",
    "profile_id",
    "profile_version",
    "display_name",
    "description",
    "status",
    "registry_mode",
    "base_profile",
    "policies",
    "coverage",
    "extensions",
    "conformance",
}
_POLICY_KEYS = {
    "unknown_workflow",
    "unknown_operation",
    "unknown_effect",
    "model_output_is_evidence",
    "consumer_can_override_trust_gate",
    "core_executes_actions",
}
_COVERAGE_KEYS = {
    "workflows",
    "operations",
    "effects",
    "capabilities",
    "evidence_records",
    "transaction_workflows",
}
_EXTENSION_KEYS = {
    "workflows",
    "operations",
    "effect_capability_contracts",
    "effect_aliases",
    "capabilities",
    "evidence_records",
    "role_markers",
    "allowed_external_effects",
}
_CONFORMANCE_KEYS = {"pack", "required_categories"}
_ALLOWED_STATUSES = {"draft", "reviewed", "bundled"}
_SEMANTIC_PROFILE_KEYS = {
    "required_roles",
    "required_policies",
    "required_effects",
    "forbidden_families",
    "forbidden_roles",
    "required_transaction_roles",
    "required_transaction_policies",
    "transaction_order_roles",
    "transaction_contract",
}
_OPERATION_KEYS = {
    "id",
    "aliases",
    "trust_level",
    "pure",
    "semantic_roles",
    "allowed_workflows",
    "required_effects",
    "allowed_effects",
    "required_effect_families",
    "allowed_effect_families",
    "allow_extra_effects",
    "required_capabilities",
    "allowed_capabilities",
    "required_capability_any",
    "required_capability_prefixes",
    "allowed_capability_prefixes",
    "allow_extra_capabilities",
    "requires_policy_any",
    "forbidden_families",
    "forbidden_roles",
    "forbidden_in_public_demo",
    "notes",
}
_EVIDENCE_KEYS = {
    "id",
    "kind",
    "status",
    "producer_kind",
    "produced_by",
    "checked_by",
    "reliability",
    "min_reliability",
    "supports_module",
    "supports_workflow",
    "supports_claims",
    "claim_statement_sha256",
    "artifact_ref",
    "artifact_sha256",
}
_PACK_KEYS = {"kind", "version", "profile_id", "cases", "sources"}
_PACK_CASE_KEYS = {"id", "category", "description", "draft", "raw_yaml", "draft_ref", "expected"}
_PACK_EXPECTED_KEYS = {"trust_status", "lowering_allowed", "required_findings", "forbidden_findings", "receipt_replay"}
_PACK_SOURCE_KEYS = {"id", "type", "path"}
_ALLOWED_CONFORMANCE_CATEGORIES = frozenset({"positive", "negative", "mutation", "replay"})
_P3_RESERVED_EXTENSION_FIELDS = frozenset({
    "effect_capability_contracts",
    "effect_aliases",
    "role_markers",
    "allowed_external_effects",
})
_P3_FORBIDDEN_OPERATION_FAMILY_FIELDS = frozenset({
    "required_effect_families",
    "allowed_effect_families",
    "required_capability_prefixes",
    "allowed_capability_prefixes",
})


@dataclass(frozen=True)
class ProfileValidationIssue:
    code: str
    path: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class LoadedProfileManifest:
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
class ProfileValidationReport:
    profile_id: str | None
    valid: bool
    manifest_path: str
    manifest_raw_sha256: str | None
    manifest_canonical_sha256: str | None
    issues: tuple[ProfileValidationIssue, ...] = field(default_factory=tuple)
    conformance_categories: tuple[str, ...] = field(default_factory=tuple)
    production_runtime_ready: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "AiNIRProfileValidationReport",
            "version": "ainir.profile-validation-report.v1",
            "profile_id": self.profile_id,
            "valid": self.valid,
            "manifest_path": self.manifest_path,
            "manifest_raw_sha256": self.manifest_raw_sha256,
            "manifest_canonical_sha256": self.manifest_canonical_sha256,
            "conformance_categories": list(self.conformance_categories),
            "issues": [issue.as_dict() for issue in self.issues],
            "production_runtime_ready": self.production_runtime_ready,
        }


class ProfileManifestError(ValueError):
    """Raised when a profile manifest cannot be safely loaded."""


@lru_cache(maxsize=1)
def _base_profile_vocabulary() -> tuple[frozenset[str], frozenset[str], SafetyRegistry]:
    """Return the packaged, reviewed effect/capability vocabulary.

    P3 profiles compose this vocabulary. They do not create a new effect
    taxonomy, capability namespace, classifier alias, or external-effect
    allowlist; those changes require core registry governance.
    """

    safety_data = load_yaml_no_duplicate_keys(read_registry_text("safety_registry.yaml")) or {}
    operation_data = load_yaml_no_duplicate_keys(read_registry_text("operation_spec_registry.yaml")) or {}
    safety = SafetyRegistry(safety_data if isinstance(safety_data, Mapping) else {})
    effects: set[str] = set()
    capabilities: set[str] = set()
    if isinstance(operation_data, Mapping):
        for item in operation_data.get("operations", []) or []:
            if not isinstance(item, Mapping):
                continue
            for field_name in ("required_effects", "allowed_effects"):
                effects.update(str(value) for value in item.get(field_name, []) or [] if isinstance(value, str))
            for field_name in ("required_capabilities", "allowed_capabilities", "required_capability_any"):
                capabilities.update(str(value) for value in item.get(field_name, []) or [] if isinstance(value, str))
    effects.update(str(value) for value in safety.effect_aliases.values() if isinstance(value, str))
    effects.update(str(value) for value in safety.allowed_external_effects)
    effects.update(str(value) for value in safety.capability_contracts)
    return frozenset(effects), frozenset(capabilities), safety


def _read_yaml_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProfileManifestError(f"cannot read {label} {path}: {exc}") from exc
    if len(raw) > MAX_YAML_BYTES:
        raise ProfileManifestError(f"{label} exceeds {MAX_YAML_BYTES} byte limit: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileManifestError(f"{label} is not valid UTF-8: {path}") from exc
    try:
        data = load_yaml_no_duplicate_keys(text)
    except Exception as exc:
        raise ProfileManifestError(f"cannot parse {label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileManifestError(f"{label} root must be an object: {path}")
    return dict(data), raw


def load_profile_manifest(path: str | Path, *, builtin: bool = False) -> LoadedProfileManifest:
    source = Path(path).resolve()
    data, raw = _read_yaml_object(source, label="profile manifest")
    return LoadedProfileManifest(
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
def materialized_profile_source(source: str | Path) -> Iterator[LoadedProfileManifest]:
    """Yield a filesystem-backed manifest for a path or bundled profile id."""

    if str(source) != BUILTIN_PROFILE_ID:
        yield load_profile_manifest(source)
        return
    with tempfile.TemporaryDirectory(prefix="ainir-profile-public-demo-") as tmp:
        root = Path(tmp) / "public_demo_v1"
        _copy_traversable(importlib_resources.files(BUILTIN_PROFILE_PACKAGE), root)
        yield load_profile_manifest(root / PROFILE_MANIFEST_FILENAME, builtin=True)


def _issue(issues: list[ProfileValidationIssue], code: str, path: str, message: str) -> None:
    issues.append(ProfileValidationIssue(code, path, message))


def _unknown_keys(value: Mapping[str, Any], allowed: set[str], path: str, issues: list[ProfileValidationIssue]) -> None:
    for key in sorted(set(value) - allowed):
        _issue(issues, "P001.unknown_field", f"{path}.{key}" if path else key, "unknown profile manifest field")


def _require_mapping(value: Any, path: str, issues: list[ProfileValidationIssue]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _issue(issues, "P002.object_required", path, "field must be an object")
        return {}
    return value


def _require_string(value: Any, path: str, issues: list[ProfileValidationIssue], *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        _issue(issues, "P003.string_required", path, "field must be a non-empty string")
        return ""
    if value != value.strip():
        _issue(issues, "P004.untrimmed_string", path, "string must not contain leading or trailing whitespace")
    if pattern is not None and not pattern.fullmatch(value):
        _issue(issues, "P005.invalid_identifier", path, f"value {value!r} does not match the required identifier syntax")
    return value


def _string_list(value: Any, path: str, issues: list[ProfileValidationIssue], *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        _issue(issues, "P006.array_required", path, "field must be an array")
        return []
    if not value and not allow_empty:
        _issue(issues, "P007.nonempty_array_required", path, "array must not be empty")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        token = _require_string(item, item_path, issues, pattern=_SAFE_TOKEN)
        if token in seen:
            _issue(issues, "P008.duplicate_value", item_path, f"duplicate value {token!r}")
        seen.add(token)
        result.append(token)
    return result


def _safe_relative_path(root: Path, value: Any, path: str, issues: list[ProfileValidationIssue]) -> Path | None:
    text = _require_string(value, path, issues)
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        _issue(issues, "P009.absolute_path_forbidden", path, "profile paths must be relative to the manifest directory")
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        _issue(issues, "P010.path_escape", path, "profile path escapes the manifest directory")
        return None
    return resolved


def _pack_categories(
    pack_path: Path,
    issues: list[ProfileValidationIssue],
    *,
    root: Path,
    expected_profile_id: str,
    allow_sources: bool,
) -> set[str]:
    try:
        pack, _ = _read_yaml_object(pack_path, label="conformance pack")
    except ProfileManifestError as exc:
        _issue(issues, "P011.conformance_pack_unreadable", "conformance.pack", str(exc))
        return set()
    if pack.get("kind") != CONFORMANCE_PACK_KIND:
        _issue(issues, "P012.conformance_pack_kind", "conformance.pack", f"kind must be {CONFORMANCE_PACK_KIND}")
    if pack.get("version") != CONFORMANCE_PACK_CONTRACT:
        _issue(issues, "P013.conformance_pack_version", "conformance.pack", f"version must be {CONFORMANCE_PACK_CONTRACT}")
    _unknown_keys(pack, _PACK_KEYS, "conformance.pack", issues)
    if pack.get("profile_id") != expected_profile_id:
        _issue(
            issues,
            "P016.conformance_profile_mismatch",
            "conformance.pack.profile_id",
            f"conformance profile_id must equal {expected_profile_id!r}",
        )
    categories: set[str] = set()
    seen_ids: set[str] = set()
    cases = pack.get("cases", [])
    if cases is not None:
        if not isinstance(cases, list):
            _issue(issues, "P014.conformance_cases_array", "conformance.pack.cases", "cases must be an array")
        else:
            for index, case in enumerate(cases):
                path = f"conformance.pack.cases[{index}]"
                if not isinstance(case, Mapping):
                    _issue(issues, "P017.conformance_case_object", path, "conformance case must be an object")
                    continue
                _unknown_keys(case, _PACK_CASE_KEYS, path, issues)
                case_id = _require_string(case.get("id"), f"{path}.id", issues, pattern=_SAFE_TOKEN)
                if case_id in seen_ids:
                    _issue(issues, "P018.duplicate_conformance_id", f"{path}.id", f"duplicate conformance id {case_id!r}")
                seen_ids.add(case_id)
                category = _require_string(case.get("category"), f"{path}.category", issues)
                if category not in _ALLOWED_CONFORMANCE_CATEGORIES:
                    _issue(issues, "P019.conformance_category", f"{path}.category", "invalid conformance category")
                else:
                    categories.add(category)
                present = [key for key in ("draft", "raw_yaml", "draft_ref") if key in case]
                if len(present) != 1:
                    _issue(issues, "P063.conformance_case_input", path, "case must define exactly one of draft, raw_yaml, or draft_ref")
                elif present[0] == "draft" and not isinstance(case.get("draft"), Mapping):
                    _issue(issues, "P064.conformance_case_draft", f"{path}.draft", "draft must be an object")
                elif present[0] == "raw_yaml" and not isinstance(case.get("raw_yaml"), str):
                    _issue(issues, "P065.conformance_case_raw_yaml", f"{path}.raw_yaml", "raw_yaml must be a string")
                elif present[0] == "draft_ref":
                    draft_path = _safe_relative_path(root, case.get("draft_ref"), f"{path}.draft_ref", issues)
                    if draft_path is not None and not draft_path.is_file():
                        _issue(issues, "P066.conformance_case_draft_missing", f"{path}.draft_ref", f"draft does not exist: {draft_path}")
                expected = _require_mapping(case.get("expected"), f"{path}.expected", issues)
                _unknown_keys(expected, _PACK_EXPECTED_KEYS, f"{path}.expected", issues)
                if expected.get("trust_status") not in {None, "passed", "refused", "invalid"}:
                    _issue(issues, "P067.conformance_expected_status", f"{path}.expected.trust_status", "trust_status must be passed, refused, or invalid")
                for field_name in ("lowering_allowed", "receipt_replay"):
                    if field_name in expected and not isinstance(expected.get(field_name), bool):
                        _issue(issues, "P068.conformance_expected_boolean", f"{path}.expected.{field_name}", "field must be boolean")
                for field_name in ("required_findings", "forbidden_findings"):
                    if field_name in expected:
                        _string_list(expected.get(field_name), f"{path}.expected.{field_name}", issues, allow_empty=True)
                expected_status = expected.get("trust_status")
                expected_lowering = expected.get("lowering_allowed")
                if category == "positive":
                    if expected_status != "passed" or expected_lowering is not True:
                        _issue(issues, "P082.vacuous_positive_case", path, "positive case must expect passed and lowering_allowed=true")
                elif category in {"negative", "mutation"}:
                    if expected_status not in {"refused", "invalid"} or expected_lowering is not False:
                        _issue(issues, "P083.vacuous_refusal_case", path, f"{category} case must expect refused/invalid and lowering_allowed=false")
                    required = expected.get("required_findings")
                    if not isinstance(required, list) or not required:
                        _issue(issues, "P084.refusal_finding_required", f"{path}.expected.required_findings", f"{category} case must name at least one required finding")
                elif category == "replay":
                    if expected_status != "passed" or expected_lowering is not True or expected.get("receipt_replay") is not True:
                        _issue(issues, "P085.vacuous_replay_case", path, "replay case must expect passed, lowering_allowed=true, and receipt_replay=true")
    sources = pack.get("sources", [])
    if sources is not None:
        if not isinstance(sources, list):
            _issue(issues, "P015.conformance_sources_array", "conformance.pack.sources", "sources must be an array")
        else:
            if sources and not allow_sources:
                _issue(issues, "P086.additive_sources_forbidden", "conformance.pack.sources", "legacy corpus source adapters are reserved for bundled packaged profiles")
            for index, source in enumerate(sources):
                path = f"conformance.pack.sources[{index}]"
                if not isinstance(source, Mapping):
                    _issue(issues, "P069.conformance_source_object", path, "conformance source must be an object")
                    continue
                _unknown_keys(source, _PACK_SOURCE_KEYS, path, issues)
                source_id = _require_string(source.get("id"), f"{path}.id", issues, pattern=_SAFE_TOKEN)
                if source_id in seen_ids:
                    _issue(issues, "P018.duplicate_conformance_id", f"{path}.id", f"duplicate conformance id {source_id!r}")
                seen_ids.add(source_id)
                source_type = source.get("type")
                if source_type == "golden_traces":
                    categories.update({"positive", "negative", "replay"})
                elif source_type == "negative_corpus":
                    categories.update({"negative", "mutation"})
                else:
                    _issue(issues, "P070.conformance_source_type", f"{path}.type", "source type must be golden_traces or negative_corpus")
                source_path = _safe_relative_path(root, source.get("path"), f"{path}.path", issues)
                if source_path is not None and not source_path.is_file():
                    _issue(issues, "P071.conformance_source_missing", f"{path}.path", f"source does not exist: {source_path}")
    return categories


def validate_profile_manifest(manifest: LoadedProfileManifest) -> ProfileValidationReport:
    data = manifest.data
    issues: list[ProfileValidationIssue] = []
    _unknown_keys(data, _TOP_LEVEL_KEYS, "", issues)

    if data.get("kind") != PROFILE_MANIFEST_KIND:
        _issue(issues, "P020.kind", "kind", f"kind must be {PROFILE_MANIFEST_KIND}")
    if data.get("version") != PROFILE_MANIFEST_CONTRACT:
        _issue(issues, "P021.version", "version", f"version must be {PROFILE_MANIFEST_CONTRACT}")
    profile_id = _require_string(data.get("profile_id"), "profile_id", issues, pattern=_SAFE_PROFILE_ID)
    _require_string(data.get("profile_version"), "profile_version", issues, pattern=_SAFE_VERSION)
    _require_string(data.get("display_name"), "display_name", issues)
    _require_string(data.get("description"), "description", issues)
    status = _require_string(data.get("status"), "status", issues)
    if status and status not in _ALLOWED_STATUSES:
        _issue(issues, "P022.status", "status", f"status must be one of {sorted(_ALLOWED_STATUSES)}")
    registry_mode = _require_string(data.get("registry_mode"), "registry_mode", issues)
    if registry_mode not in {"packaged", "additive"}:
        _issue(issues, "P023.registry_mode", "registry_mode", "registry_mode must be packaged or additive")
    base_profile = data.get("base_profile")
    if base_profile is not None:
        _require_string(base_profile, "base_profile", issues, pattern=_SAFE_PROFILE_ID)
    if registry_mode == "packaged" and base_profile is not None:
        _issue(issues, "P024.packaged_base_profile", "base_profile", "packaged profiles must not declare a base profile")
    if registry_mode == "packaged" and (profile_id != BUILTIN_PROFILE_ID or not manifest.builtin):
        _issue(
            issues,
            "P088.packaged_profile_reserved",
            "registry_mode",
            f"packaged mode is reserved for the bundled {BUILTIN_PROFILE_ID} profile loaded by stable ID",
        )
    if registry_mode == "additive" and base_profile != BUILTIN_PROFILE_ID:
        _issue(issues, "P025.additive_base_profile", "base_profile", f"additive profiles must extend {BUILTIN_PROFILE_ID}")
    if registry_mode == "additive" and profile_id == BUILTIN_PROFILE_ID:
        _issue(issues, "P089.builtin_profile_id_reserved", "profile_id", f"{BUILTIN_PROFILE_ID} is reserved for the bundled profile")

    policies = _require_mapping(data.get("policies"), "policies", issues)
    _unknown_keys(policies, _POLICY_KEYS, "policies", issues)
    for key in ("unknown_workflow", "unknown_operation", "unknown_effect"):
        if policies.get(key) != "refuse":
            _issue(issues, "P030.fail_closed_policy", f"policies.{key}", "core unknown semantics policy must remain refuse")
    for key in ("model_output_is_evidence", "consumer_can_override_trust_gate", "core_executes_actions"):
        if policies.get(key) is not False:
            _issue(issues, "P031.core_invariant_override", f"policies.{key}", "core invariant must remain false")

    coverage = _require_mapping(data.get("coverage"), "coverage", issues)
    _unknown_keys(coverage, _COVERAGE_KEYS, "coverage", issues)
    coverage_values: dict[str, list[str]] = {}
    for key in sorted(_COVERAGE_KEYS):
        coverage_values[key] = _string_list(
            coverage.get(key),
            f"coverage.{key}",
            issues,
            allow_empty=(key == "transaction_workflows"),
        )

    extensions = _require_mapping(data.get("extensions"), "extensions", issues)
    _unknown_keys(extensions, _EXTENSION_KEYS, "extensions", issues)
    list_extension_keys = {"workflows", "operations", "capabilities", "evidence_records", "allowed_external_effects"}
    map_extension_keys = {"effect_capability_contracts", "effect_aliases", "role_markers"}
    for key in list_extension_keys:
        if not isinstance(extensions.get(key), list):
            _issue(issues, "P032.extension_array", f"extensions.{key}", "extension field must be an array")
    for key in map_extension_keys:
        if not isinstance(extensions.get(key), Mapping):
            _issue(issues, "P033.extension_object", f"extensions.{key}", "extension field must be an object")

    if registry_mode == "packaged":
        for key, value in extensions.items():
            if value not in ({}, []):
                _issue(issues, "P034.packaged_extension_forbidden", f"extensions.{key}", "packaged profile binds existing registries and cannot add extensions")
    elif registry_mode == "additive":
        known_effects, known_capabilities, base_safety = _base_profile_vocabulary()
        for key in _P3_RESERVED_EXTENSION_FIELDS:
            value = extensions.get(key)
            if value not in ({}, []):
                _issue(
                    issues,
                    "P078.extension_requires_registry_governance",
                    f"extensions.{key}",
                    "P3 profiles may compose reviewed effects/capabilities but cannot add taxonomy aliases, role markers, contracts, or external allowlists",
                )
        workflows = extensions.get("workflows") if isinstance(extensions.get("workflows"), list) else []
        operations = extensions.get("operations") if isinstance(extensions.get("operations"), list) else []
        if not workflows:
            _issue(issues, "P035.workflow_extension_required", "extensions.workflows", "additive profile must define at least one workflow")
        if not operations:
            _issue(issues, "P036.operation_extension_required", "extensions.operations", "additive profile must define at least one operation")
        workflow_ids: set[str] = set()
        workflow_effects: set[str] = set()
        for index, workflow in enumerate(workflows):
            path = f"extensions.workflows[{index}]"
            if not isinstance(workflow, Mapping):
                _issue(issues, "P037.workflow_object", path, "workflow extension must be an object")
                continue
            allowed = {"id", "aliases", "semantic_profile"}
            _unknown_keys(workflow, allowed, path, issues)
            workflow_id = _require_string(workflow.get("id"), f"{path}.id", issues, pattern=_SAFE_WORKFLOW_ID)
            if workflow_id in workflow_ids:
                _issue(issues, "P038.duplicate_workflow", f"{path}.id", f"duplicate workflow id {workflow_id!r}")
            workflow_ids.add(workflow_id)
            _string_list(workflow.get("aliases", []), f"{path}.aliases", issues, allow_empty=True)
            semantic = _require_mapping(workflow.get("semantic_profile"), f"{path}.semantic_profile", issues)
            _unknown_keys(semantic, _SEMANTIC_PROFILE_KEYS, f"{path}.semantic_profile", issues)
            required_roles = _string_list(semantic.get("required_roles"), f"{path}.semantic_profile.required_roles", issues)
            if not required_roles:
                _issue(issues, "P039.required_roles", f"{path}.semantic_profile.required_roles", "workflow must require at least one semantic role")
            for field_name in (
                "required_policies",
                "required_effects",
                "forbidden_families",
                "forbidden_roles",
                "required_transaction_roles",
                "required_transaction_policies",
            ):
                if field_name in semantic:
                    values = _string_list(semantic.get(field_name), f"{path}.semantic_profile.{field_name}", issues, allow_empty=True)
                    if field_name == "required_effects":
                        workflow_effects.update(values)
            if "transaction_order_roles" in semantic:
                pairs = semantic.get("transaction_order_roles")
                if not isinstance(pairs, list):
                    _issue(issues, "P040.transaction_order_array", f"{path}.semantic_profile.transaction_order_roles", "transaction order must be an array")
                else:
                    for pair_index, pair in enumerate(pairs):
                        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(item, str) for item in pair):
                            _issue(issues, "P041.transaction_order_pair", f"{path}.semantic_profile.transaction_order_roles[{pair_index}]", "transaction order entry must contain two role strings")

        operation_ids: set[str] = set()
        operation_aliases: set[str] = set()
        operation_effects: set[str] = set()
        operation_capabilities: set[str] = set()
        for index, operation in enumerate(operations):
            path = f"extensions.operations[{index}]"
            if not isinstance(operation, Mapping):
                _issue(issues, "P042.operation_object", path, "operation extension must be an object")
                continue
            _unknown_keys(operation, _OPERATION_KEYS, path, issues)
            op_id = _require_string(operation.get("id"), f"{path}.id", issues, pattern=_SAFE_TOKEN)
            if op_id and base_safety.classify_operation(op_id):
                _issue(
                    issues,
                    "P079.safety_critical_operation_requires_core_review",
                    f"{path}.id",
                    f"profile operation id matches protected safety families: {sorted(base_safety.classify_operation(op_id))}",
                )
            if op_id in operation_ids:
                _issue(issues, "P043.duplicate_operation", f"{path}.id", f"duplicate operation id {op_id!r}")
            operation_ids.add(op_id)
            roles = _string_list(operation.get("semantic_roles"), f"{path}.semantic_roles", issues)
            allowed_workflows = _string_list(operation.get("allowed_workflows"), f"{path}.allowed_workflows", issues)
            for workflow_id in allowed_workflows:
                if workflow_id not in workflow_ids and workflow_id not in set(coverage_values.get("workflows", [])):
                    _issue(issues, "P044.operation_unknown_workflow", f"{path}.allowed_workflows", f"operation references undeclared workflow {workflow_id!r}")
            aliases = _string_list(operation.get("aliases", []), f"{path}.aliases", issues, allow_empty=True)
            for alias in aliases:
                if base_safety.classify_operation(alias):
                    _issue(
                        issues,
                        "P079.safety_critical_operation_requires_core_review",
                        f"{path}.aliases",
                        f"profile operation alias {alias!r} matches protected safety families",
                    )
                if alias in operation_aliases:
                    _issue(issues, "P045.duplicate_operation_alias", f"{path}.aliases", f"duplicate operation alias {alias!r}")
                operation_aliases.add(alias)
            if operation.get("allow_extra_effects", False) is not False:
                _issue(issues, "P046.extra_effects_forbidden", f"{path}.allow_extra_effects", "profile operations cannot permit undeclared extra effects")
            if operation.get("allow_extra_capabilities", False) is not False:
                _issue(issues, "P047.extra_capabilities_forbidden", f"{path}.allow_extra_capabilities", "profile operations cannot permit undeclared extra capabilities")
            if operation.get("trust_level") not in {None, "profile_fixture"}:
                _issue(issues, "P048.operation_trust_level", f"{path}.trust_level", "authored profile operations use isolated profile_fixture trust only")
            if not roles:
                _issue(issues, "P049.operation_roles", f"{path}.semantic_roles", "operation must declare at least one semantic role")
            for field_name in (
                "required_effects",
                "allowed_effects",
                "required_effect_families",
                "allowed_effect_families",
                "required_capabilities",
                "allowed_capabilities",
                "required_capability_any",
                "required_capability_prefixes",
                "allowed_capability_prefixes",
                "requires_policy_any",
                "forbidden_families",
                "forbidden_roles",
            ):
                if field_name in operation:
                    values = _string_list(operation.get(field_name), f"{path}.{field_name}", issues, allow_empty=True)
                    if field_name in {"required_effects", "allowed_effects"}:
                        operation_effects.update(values)
                    if field_name in {"required_capabilities", "allowed_capabilities", "required_capability_any"}:
                        operation_capabilities.update(values)
                    if field_name in _P3_FORBIDDEN_OPERATION_FAMILY_FIELDS and values:
                        _issue(
                            issues,
                            "P080.broad_operation_contract_forbidden",
                            f"{path}.{field_name}",
                            "P3 profile operations require exact reviewed effects and capabilities; family/prefix widening requires core review",
                        )
            for field_name in ("pure", "forbidden_in_public_demo"):
                if field_name in operation and not isinstance(operation.get(field_name), bool):
                    _issue(issues, "P072.operation_boolean", f"{path}.{field_name}", "operation field must be boolean")
            if "notes" in operation and not isinstance(operation.get("notes"), str):
                _issue(issues, "P073.operation_notes", f"{path}.notes", "notes must be a string")

        extension_capabilities = {
            str(item) for item in (extensions.get("capabilities") or []) if isinstance(item, str)
        }
        declared_caps = set(coverage_values.get("capabilities", [])) | extension_capabilities
        effect_contracts = extensions.get("effect_capability_contracts") if isinstance(extensions.get("effect_capability_contracts"), Mapping) else {}
        for effect, spec in effect_contracts.items():
            effect_path = f"extensions.effect_capability_contracts.{effect}"
            _require_string(effect, effect_path, issues, pattern=_SAFE_TOKEN)
            if not isinstance(spec, Mapping):
                _issue(issues, "P050.effect_contract_object", effect_path, "effect capability contract must be an object")
                continue
            prefixes = _string_list(spec.get("prefixes"), f"{effect_path}.prefixes", issues)
            if not prefixes:
                _issue(issues, "P051.effect_capability_prefix", f"{effect_path}.prefixes", "effect contract must require at least one capability prefix")
        for index, capability in enumerate(extensions.get("capabilities") or []):
            _require_string(capability, f"extensions.capabilities[{index}]", issues, pattern=_SAFE_TOKEN)
        if not declared_caps:
            _issue(issues, "P052.capability_coverage", "coverage.capabilities", "profile must declare capability coverage")
        for effect in sorted(workflow_effects | operation_effects):
            if effect not in known_effects:
                _issue(
                    issues,
                    "P081.unknown_profile_effect",
                    "extensions.operations",
                    f"effect {effect!r} is not in the packaged reviewed effect vocabulary",
                )
        for capability in sorted(extension_capabilities | operation_capabilities):
            if capability not in known_capabilities:
                _issue(
                    issues,
                    "P087.unknown_profile_capability",
                    "extensions.operations",
                    f"capability {capability!r} is not in the packaged reviewed capability vocabulary",
                )

        evidence_records = extensions.get("evidence_records") if isinstance(extensions.get("evidence_records"), list) else []
        evidence_ids: set[str] = set()
        for index, record in enumerate(evidence_records):
            path = f"extensions.evidence_records[{index}]"
            if not isinstance(record, Mapping):
                _issue(issues, "P053.evidence_object", path, "evidence record must be an object")
                continue
            _unknown_keys(record, _EVIDENCE_KEYS, path, issues)
            evidence_id = _require_string(record.get("id"), f"{path}.id", issues, pattern=_SAFE_TOKEN)
            if evidence_id in evidence_ids:
                _issue(issues, "P054.duplicate_evidence", f"{path}.id", f"duplicate evidence id {evidence_id!r}")
            evidence_ids.add(evidence_id)
            if record.get("kind") != "verifier_report":
                _issue(issues, "P055.evidence_kind", f"{path}.kind", "P3 authored evidence fixtures must use verifier_report")
            if record.get("status") != "checked":
                _issue(issues, "P056.evidence_status", f"{path}.status", "evidence fixture must be checked")
            if record.get("producer_kind") not in {None, "profile_fixture"}:
                _issue(issues, "P057.evidence_producer", f"{path}.producer_kind", "authored profile evidence uses isolated profile_fixture producer")
            if "supports_claims" in record:
                _string_list(record.get("supports_claims"), f"{path}.supports_claims", issues)
            for field_name in ("produced_by", "checked_by", "supports_module", "supports_workflow", "claim_statement_sha256", "artifact_ref", "artifact_sha256"):
                if field_name in record and not isinstance(record.get(field_name), str):
                    _issue(issues, "P074.evidence_string", f"{path}.{field_name}", "evidence field must be a string")
            for field_name in ("reliability", "min_reliability"):
                if field_name in record and (not isinstance(record.get(field_name), (int, float)) or isinstance(record.get(field_name), bool)):
                    _issue(issues, "P075.evidence_number", f"{path}.{field_name}", "evidence reliability must be numeric")

        coverage_workflows = set(coverage_values.get("workflows", []))
        coverage_operations = set(coverage_values.get("operations", []))
        coverage_effects = set(coverage_values.get("effects", []))
        coverage_capabilities = set(coverage_values.get("capabilities", []))
        coverage_evidence = set(coverage_values.get("evidence_records", []))
        extension_effects = set(workflow_effects) | set(operation_effects)
        extension_effects.update(str(item) for item in effect_contracts)
        extension_effects.update(str(item) for item in extensions.get("allowed_external_effects", []) or [] if isinstance(item, str))
        extension_effects.update(str(item) for item in (extensions.get("effect_aliases", {}) or {}).values() if isinstance(item, str))
        coherence_checks = (
            ("workflows", coverage_workflows, workflow_ids),
            ("operations", coverage_operations, operation_ids),
            ("effects", coverage_effects, extension_effects),
            ("capabilities", coverage_capabilities, extension_capabilities | operation_capabilities),
            ("evidence_records", coverage_evidence, evidence_ids),
        )
        for label, declared, actual in coherence_checks:
            if declared != actual:
                _issue(
                    issues,
                    "P076.coverage_mismatch",
                    f"coverage.{label}",
                    f"coverage must exactly match authored extension usage; declared={sorted(declared)!r} actual={sorted(actual)!r}",
                )

        transaction_workflows = {
            str(workflow.get("id"))
            for workflow in workflows
            if isinstance(workflow, Mapping)
            and isinstance(workflow.get("semantic_profile"), Mapping)
            and any(
                workflow["semantic_profile"].get(field)
                for field in (
                    "required_transaction_roles",
                    "required_transaction_policies",
                    "transaction_order_roles",
                    "transaction_contract",
                )
            )
        }
        if set(coverage_values.get("transaction_workflows", [])) != transaction_workflows:
            _issue(
                issues,
                "P077.transaction_coverage_mismatch",
                "coverage.transaction_workflows",
                f"transaction workflow coverage must equal {sorted(transaction_workflows)!r}",
            )

    conformance = _require_mapping(data.get("conformance"), "conformance", issues)
    _unknown_keys(conformance, _CONFORMANCE_KEYS, "conformance", issues)
    required_categories = set(_string_list(conformance.get("required_categories"), "conformance.required_categories", issues))
    if required_categories != REQUIRED_CONFORMANCE_CATEGORIES:
        _issue(
            issues,
            "P060.required_conformance_categories",
            "conformance.required_categories",
            f"required categories must be exactly {sorted(REQUIRED_CONFORMANCE_CATEGORIES)}",
        )
    pack_path = _safe_relative_path(manifest.root, conformance.get("pack"), "conformance.pack", issues)
    categories: set[str] = set()
    if pack_path is not None:
        if not pack_path.exists():
            _issue(issues, "P061.conformance_pack_missing", "conformance.pack", f"conformance pack does not exist: {pack_path}")
        else:
            categories = _pack_categories(
                pack_path,
                issues,
                root=manifest.root,
                expected_profile_id=profile_id,
                allow_sources=(registry_mode == "packaged" and manifest.builtin),
            )
            missing = REQUIRED_CONFORMANCE_CATEGORIES - categories
            if missing:
                _issue(issues, "P062.conformance_category_missing", "conformance.pack", f"conformance pack does not cover categories: {sorted(missing)}")

    return ProfileValidationReport(
        profile_id=profile_id or None,
        valid=not issues,
        manifest_path=str(manifest.path),
        manifest_raw_sha256=manifest.raw_sha256,
        manifest_canonical_sha256=manifest.canonical_sha256,
        issues=tuple(issues),
        conformance_categories=tuple(sorted(categories)),
    )


def inspect_profile_manifest(manifest: LoadedProfileManifest) -> dict[str, Any]:
    report = validate_profile_manifest(manifest)
    data = manifest.data
    extensions = data.get("extensions") if isinstance(data.get("extensions"), Mapping) else {}
    return {
        "kind": "AiNIRProfileInspection",
        "version": "ainir.profile-inspection.v1",
        "profile_id": data.get("profile_id"),
        "profile_version": data.get("profile_version"),
        "display_name": data.get("display_name"),
        "status": data.get("status"),
        "registry_mode": data.get("registry_mode"),
        "base_profile": data.get("base_profile"),
        "manifest_path": str(manifest.path),
        "manifest_raw_sha256": manifest.raw_sha256,
        "manifest_canonical_sha256": manifest.canonical_sha256,
        "coverage": data.get("coverage"),
        "extension_counts": {
            "workflows": len(extensions.get("workflows") or []),
            "operations": len(extensions.get("operations") or []),
            "effect_capability_contracts": len(extensions.get("effect_capability_contracts") or {}),
            "capabilities": len(extensions.get("capabilities") or []),
            "evidence_records": len(extensions.get("evidence_records") or []),
        },
        "conformance_categories": list(report.conformance_categories),
        "valid": report.valid,
        "issues": [issue.as_dict() for issue in report.issues],
        "production_runtime_ready": False,
    }


def list_workflow_profile_manifests(root: str | Path | None = None) -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    with materialized_profile_source(BUILTIN_PROFILE_ID) as builtin:
        items.append(inspect_profile_manifest(builtin))
    if root is not None:
        base = Path(root)
        if base.exists():
            candidates = sorted({*base.glob("**/profile.yaml"), *base.glob("**/profile.yml")})
            for candidate in candidates:
                try:
                    loaded = load_profile_manifest(candidate)
                    if loaded.profile_id == BUILTIN_PROFILE_ID:
                        continue
                    items.append(inspect_profile_manifest(loaded))
                except ProfileManifestError as exc:
                    items.append({
                        "kind": "AiNIRProfileInspection",
                        "version": "ainir.profile-inspection.v1",
                        "profile_id": None,
                        "manifest_path": str(candidate),
                        "valid": False,
                        "issues": [{"code": "P099.load_error", "path": "manifest", "message": str(exc), "severity": "error"}],
                        "production_runtime_ready": False,
                    })
    return tuple(sorted(items, key=lambda item: str(item.get("profile_id") or item.get("manifest_path"))))


def _statement_sha256(statement: str) -> str:
    return sha256(statement.encode("utf-8")).hexdigest()


def initialize_profile(
    target: str | Path,
    *,
    profile_id: str,
    workflow_id: str,
    force: bool = False,
) -> tuple[Path, ...]:
    """Create a safe, runnable additive profile template."""

    if not _SAFE_PROFILE_ID.fullmatch(profile_id):
        raise ProfileManifestError(f"invalid profile id: {profile_id!r}")
    if not _SAFE_WORKFLOW_ID.fullmatch(workflow_id):
        raise ProfileManifestError(f"invalid workflow id: {workflow_id!r}")
    root = Path(target).resolve()
    if root.exists() and any(root.iterdir()) and not force:
        raise ProfileManifestError(f"target directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    statement = "Example profile request is validated and persisted atomically."
    evidence_id = f"evidence.profile.{profile_id.replace('.', '_')}.reviewed"
    module_id = f"profile.{profile_id.replace('-', '_')}.example"
    manifest = {
        "kind": PROFILE_MANIFEST_KIND,
        "version": PROFILE_MANIFEST_CONTRACT,
        "profile_id": profile_id,
        "profile_version": "0.1.0",
        "display_name": profile_id,
        "description": "Additive AiNIR workflow profile generated by `ainir profile init`.",
        "status": "draft",
        "registry_mode": "additive",
        "base_profile": BUILTIN_PROFILE_ID,
        "policies": {
            "unknown_workflow": "refuse",
            "unknown_operation": "refuse",
            "unknown_effect": "refuse",
            "model_output_is_evidence": False,
            "consumer_can_override_trust_gate": False,
            "core_executes_actions": False,
        },
        "coverage": {
            "workflows": [workflow_id],
            "operations": ["profile.validate_request", "profile.persist_record"],
            "effects": ["effect.storage.db.write"],
            "capabilities": ["cap.db.write"],
            "evidence_records": [evidence_id],
            "transaction_workflows": [workflow_id],
        },
        "extensions": {
            "workflows": [{
                "id": workflow_id,
                "aliases": [],
                "semantic_profile": {
                    "required_roles": ["validate_request", "persist_record"],
                    "required_policies": ["policy.profile_reviewed"],
                    "required_transaction_roles": ["validate_request", "persist_record"],
                    "required_transaction_policies": ["policy.profile_reviewed"],
                    "transaction_order_roles": [["validate_request", "persist_record"]],
                    "forbidden_families": ["external_unallowlisted", "destructive_delete", "payment_real"],
                },
            }],
            "operations": [
                {
                    "id": "profile.validate_request",
                    "aliases": [],
                    "trust_level": "profile_fixture",
                    "pure": True,
                    "semantic_roles": ["validate_request"],
                    "allowed_workflows": [workflow_id],
                    "required_effects": [],
                    "allowed_effects": [],
                    "allow_extra_effects": False,
                    "required_capabilities": [],
                    "allowed_capabilities": [],
                    "allow_extra_capabilities": False,
                },
                {
                    "id": "profile.persist_record",
                    "aliases": [],
                    "trust_level": "profile_fixture",
                    "pure": False,
                    "semantic_roles": ["persist_record"],
                    "allowed_workflows": [workflow_id],
                    "required_effects": ["effect.storage.db.write"],
                    "allowed_effects": ["effect.storage.db.write"],
                    "allow_extra_effects": False,
                    "required_capabilities": ["cap.db.write"],
                    "allowed_capabilities": ["cap.db.write"],
                    "allow_extra_capabilities": False,
                    "requires_policy_any": ["policy.profile_reviewed"],
                },
            ],
            "effect_capability_contracts": {},
            "effect_aliases": {},
            "capabilities": ["cap.db.write"],
            "evidence_records": [{
                "id": evidence_id,
                "kind": "verifier_report",
                "status": "checked",
                "producer_kind": "profile_fixture",
                "produced_by": profile_id,
                "checked_by": "profile_author",
                "reliability": 0.95,
                "min_reliability": 0.8,
                "supports_module": module_id,
                "supports_workflow": workflow_id,
                "supports_claims": ["claim.profile.reviewed"],
                "claim_statement_sha256": _statement_sha256(statement),
            }],
            "role_markers": {},
            "allowed_external_effects": [],
        },
        "conformance": {
            "pack": "conformance.yaml",
            "required_categories": sorted(REQUIRED_CONFORMANCE_CATEGORIES),
        },
    }
    base_draft = {
        "module": module_id,
        "workflow": workflow_id,
        "task": f"{workflow_id}Task",
        "input_type": "unknown",
        "output_type": "unknown",
        "return": "state",
        "policies": [{"id": "policy.profile_reviewed"}],
        "transaction": {
            "id": "tx.profile",
            "mode": "atomic",
            "includes": ["op.validate", "op.persist"],
        },
        "operations": [
            {"id": "op.validate", "op": "profile.validate_request", "effects": [], "capabilities": []},
            {
                "id": "op.persist",
                "op": "profile.persist_record",
                "effects": ["effect.storage.db.write"],
                "capabilities": ["cap.db.write"],
                "policies": ["policy.profile_reviewed"],
            },
        ],
        "claims": [{
            "id": "claim.profile.reviewed",
            "status": "verified",
            "statement": statement,
            "evidence": [{"id": evidence_id, "kind": "verifier_report"}],
        }],
    }
    negative = json.loads(json.dumps(base_draft))
    negative["operations"] = [negative["operations"][1]]
    negative["transaction"]["includes"] = ["op.persist"]
    mutation = json.loads(json.dumps(base_draft))
    mutation["operations"][1]["op"] = "profile.unknown_operation"
    replay = json.loads(json.dumps(base_draft))
    pack = {
        "kind": CONFORMANCE_PACK_KIND,
        "version": CONFORMANCE_PACK_CONTRACT,
        "profile_id": profile_id,
        "cases": [
            {
                "id": "positive.profile_passes",
                "category": "positive",
                "description": "A complete profile draft passes the isolated Trust Gate.",
                "draft": base_draft,
                "expected": {"trust_status": "passed", "lowering_allowed": True, "receipt_replay": True},
            },
            {
                "id": "negative.required_role_missing",
                "category": "negative",
                "description": "Removing the validation role must be refused.",
                "draft": negative,
                "expected": {"trust_status": "refused", "lowering_allowed": False, "required_findings": ["W010.workflow_semantic_profile_missing"]},
            },
            {
                "id": "mutation.unknown_operation",
                "category": "mutation",
                "description": "An unknown operation cannot inherit trust from the profile.",
                "draft": mutation,
                "expected": {"trust_status": "refused", "lowering_allowed": False, "required_findings": ["O001.operation_spec_required"]},
            },
            {
                "id": "replay.profile_receipt",
                "category": "replay",
                "description": "A passing profile receipt exact-replays inside the same bound registry bundle.",
                "draft": replay,
                "expected": {"trust_status": "passed", "lowering_allowed": True, "receipt_replay": True},
            },
        ],
        "sources": [],
    }
    manifest_path = root / PROFILE_MANIFEST_FILENAME
    pack_path = root / "conformance.yaml"
    readme_path = root / "README.md"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    pack_path.write_text(yaml.safe_dump(pack, sort_keys=False, allow_unicode=True), encoding="utf-8")
    readme_path.write_text(
        "# AiNIR workflow profile\n\n"
        "This scaffold is an isolated conformance profile, not a production runtime.\n"
        "Run `ainir profile validate profile.yaml` and `ainir conformance run profile.yaml`.\n",
        encoding="utf-8",
    )
    return manifest_path, pack_path, readme_path


__all__ = [
    "BUILTIN_PROFILE_ID",
    "CONFORMANCE_PACK_CONTRACT",
    "CONFORMANCE_PACK_KIND",
    "LoadedProfileManifest",
    "ProfileManifestError",
    "ProfileValidationIssue",
    "ProfileValidationReport",
    "REQUIRED_CONFORMANCE_CATEGORIES",
    "initialize_profile",
    "inspect_profile_manifest",
    "list_workflow_profile_manifests",
    "load_profile_manifest",
    "materialized_profile_source",
    "validate_profile_manifest",
]
