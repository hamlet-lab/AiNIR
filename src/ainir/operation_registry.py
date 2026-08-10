"""Registry-bound operation semantics for AiNIR public demo.

Pre-v1 Phase 10 tightens the operation/effect contract: registered operations
may only declare effects allowed by their operation spec. Semantic workflow
roles are satisfied only by registered operation roles, never by policy names
alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

import yaml

from .core import load_yaml_no_duplicate_keys
from .registry_context import active_registry_bundle

from .safety_registry import compact, get_registry


@dataclass(frozen=True)
class OperationSpec:
    id: str
    raw: Mapping[str, Any]

    @property
    def semantic_roles(self) -> set[str]:
        return {str(x) for x in self.raw.get("semantic_roles", []) or []}

    @property
    def allowed_workflows_declared(self) -> bool:
        return "allowed_workflows" in self.raw

    @property
    def allowed_workflows(self) -> set[str]:
        return {str(x) for x in self.raw.get("allowed_workflows", []) or []}

    @property
    def forbidden_roles(self) -> set[str]:
        return {str(x) for x in self.raw.get("forbidden_roles", []) or []}

    @property
    def forbidden_in_public_demo(self) -> bool:
        return bool(self.raw.get("forbidden_in_public_demo", False))

    @property
    def required_effects(self) -> set[str]:
        return {str(x) for x in self.raw.get("required_effects", []) or []}

    @property
    def required_effect_families(self) -> set[str]:
        return {str(x) for x in self.raw.get("required_effect_families", []) or []}

    @property
    def allowed_effects(self) -> set[str]:
        return {str(x) for x in self.raw.get("allowed_effects", self.raw.get("required_effects", [])) or []}

    @property
    def allowed_effect_families(self) -> set[str]:
        return {str(x) for x in self.raw.get("allowed_effect_families", self.raw.get("required_effect_families", [])) or []}

    @property
    def allow_extra_effects(self) -> bool:
        return bool(self.raw.get("allow_extra_effects", False))

    @property
    def forbidden_families(self) -> set[str]:
        return {str(x) for x in self.raw.get("forbidden_families", []) or []}

    @property
    def required_capabilities(self) -> set[str]:
        return {str(x) for x in self.raw.get("required_capabilities", []) or []}

    @property
    def required_capability_any(self) -> set[str]:
        return {str(x) for x in self.raw.get("required_capability_any", []) or []}

    @property
    def required_capability_prefixes(self) -> tuple[str, ...]:
        return tuple(str(x) for x in self.raw.get("required_capability_prefixes", []) or [])


    @property
    def allowed_capability_prefixes(self) -> tuple[str, ...]:
        if "allowed_capability_prefixes" in self.raw:
            return tuple(str(x) for x in self.raw.get("allowed_capability_prefixes", []) or [])
        return self.required_capability_prefixes

    @property
    def allowed_capabilities(self) -> set[str]:
        if "allowed_capabilities" in self.raw:
            return {str(x) for x in self.raw.get("allowed_capabilities", []) or []}
        if "required_capabilities" in self.raw:
            return self.required_capabilities
        return set()

    @property
    def allow_extra_capabilities(self) -> bool:
        return bool(self.raw.get("allow_extra_capabilities", False))

    @property
    def requires_policy_any(self) -> set[str]:
        return {str(x) for x in self.raw.get("requires_policy_any", []) or []}

    @property
    def trust_level(self) -> str:
        return str(self.raw.get("trust_level", "untrusted"))


class OperationRegistry:
    def __init__(self, data: Mapping[str, Any]):
        self.data = dict(data or {})
        self.trusted_levels = {str(x) for x in self.data.get("trusted_spec_levels", []) or []}
        self.unknown_operation_policy = str(self.data.get("unknown_operation_policy", "block_for_known_workflows"))
        self.specs: dict[str, OperationSpec] = {}
        self.alias_to_id: dict[str, str] = {}
        for item in self.data.get("operations", []) or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            op_id = str(item["id"])
            if op_id in self.specs:
                continue
            spec = OperationSpec(op_id, dict(item))
            self.specs[op_id] = spec
            self.alias_to_id[compact(op_id)] = op_id
            for alias in item.get("aliases", []) or []:
                if isinstance(alias, str):
                    self.alias_to_id[compact(alias)] = op_id

    @classmethod
    def load(cls, path: str | Path | None = None) -> "OperationRegistry":
        if path is not None:
            with Path(path).open("r", encoding="utf-8") as f:
                return cls(load_yaml_no_duplicate_keys(f.read()) or {})
        try:
            content = resources.files("ainir.registries").joinpath("operation_spec_registry.yaml").read_text(encoding="utf-8")
            return cls(load_yaml_no_duplicate_keys(content) or {})
        except Exception:
            pass
        here = Path(__file__).resolve()
        for candidate in (
            here.parents[2] / "registries" / "operation_spec_registry.yaml",
            Path.cwd() / "registries" / "operation_spec_registry.yaml",
        ):
            if candidate.exists():
                with candidate.open("r", encoding="utf-8") as f:
                    return cls(load_yaml_no_duplicate_keys(f.read()) or {})
        raise RuntimeError("operation_spec_registry.yaml not found")

    def resolve_id(self, op_name: object) -> tuple[str | None, bool]:
        if not isinstance(op_name, str) or not op_name.strip():
            return None, False
        if op_name in self.specs:
            return op_name, False
        resolved = self.alias_to_id.get(compact(op_name))
        if resolved:
            return resolved, resolved != op_name
        return None, False

    def spec_for(self, op_name: object) -> OperationSpec | None:
        resolved, _ = self.resolve_id(op_name)
        if resolved is None:
            return None
        return self.specs.get(resolved)

    def canonical_id_for(self, op_name: object) -> str | None:
        resolved, _ = self.resolve_id(op_name)
        return resolved

    def semantic_roles_for_operations(self, operations: list[Mapping[str, Any]]) -> set[str]:
        roles: set[str] = set()
        for op in operations:
            spec = self.spec_for(op.get("op"))
            if spec:
                roles.update(spec.semantic_roles)
        return roles

    def role_satisfied(self, role: str, operations: list[Mapping[str, Any]], _policy_ids: set[str] | None = None) -> bool:
        return role in self.semantic_roles_for_operations(operations)

    def operation_ids_for_roles(self, operations: list[Mapping[str, Any]], roles: set[str]) -> dict[str, list[str]]:
        out = {r: [] for r in roles}
        for op in operations:
            spec = self.spec_for(op.get("op"))
            if not spec:
                continue
            op_id = str(op.get("id", "unknown_op"))
            for role in roles & spec.semantic_roles:
                out[role].append(op_id)
        return out

    def operation_binding_findings(self, module_workflow: str, op: Mapping[str, Any]) -> list[dict[str, Any]]:
        safety = get_registry()
        out: list[dict[str, Any]] = []
        op_id = str(op.get("id", "unknown_op"))
        op_name = op.get("op")
        spec = self.spec_for(op_name)
        effects = [e for e in (op.get("effects") or []) if isinstance(e, str)]
        capabilities = [c for c in (op.get("capabilities") or []) if isinstance(c, str)]
        policies = {p for p in (op.get("policies") or []) if isinstance(p, str)}
        effect_families = set().union(*(safety.classify_effect(e) for e in effects)) if effects else set()

        if spec is None:
            if safety.is_known_workflow(module_workflow) and self.unknown_operation_policy == "block_for_known_workflows":
                out.append({"rule": "O001.operation_spec_required", "severity": "critical", "target": op_id, "message": f"Operation {op_name!r} is not registered for a known workflow."})
            return out

        if self.trusted_levels and spec.trust_level not in self.trusted_levels:
            out.append({"rule": "O002.operation_spec_untrusted", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} has untrusted level {spec.trust_level!r}."})
        if spec.forbidden_in_public_demo:
            out.append({"rule": "O010.operation_forbidden_in_public_demo", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} is explicitly forbidden in the public demo path."})
        if spec.allowed_workflows_declared:
            if not spec.allowed_workflows:
                out.append({"rule": "O003.operation_not_allowed_in_any_workflow", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} is not allowed in any public demo workflow."})
            elif module_workflow not in spec.allowed_workflows:
                out.append({"rule": "O003.operation_not_allowed_in_workflow", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} is not allowed in workflow {module_workflow}."})
        for required in sorted(spec.required_effects):
            if required not in effects:
                out.append({"rule": "O004.operation_required_effect_missing", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} requires effect {required}."})
        for family in sorted(spec.required_effect_families):
            if family not in effect_families:
                out.append({"rule": "O005.operation_required_effect_family_missing", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} requires effect family {family}."})
        for role in sorted(spec.semantic_roles & _profile_forbidden_roles(module_workflow)):
            out.append({"rule": "O011.operation_forbidden_semantic_role", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} has forbidden semantic role {role} in workflow {module_workflow}."})
        for role in sorted(spec.forbidden_roles):
            if role in spec.semantic_roles:
                out.append({"rule": "O011.operation_forbidden_semantic_role", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} declares forbidden semantic role {role}."})
        for family in sorted(spec.forbidden_families):
            if family in effect_families or family in safety.classify_operation(op_name):
                out.append({"rule": "O006.operation_forbidden_effect_family", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} is bound to forbidden effect family {family} in this demo path."})
        for effect in effects:
            families = safety.classify_effect(effect)
            if not spec.allow_extra_effects and effect not in spec.allowed_effects and not (families & spec.allowed_effect_families):
                out.append({"rule": "O009.operation_declares_unallowed_effect", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} does not allow declared effect {effect}."})
        for required_capability in sorted(spec.required_capabilities):
            if required_capability not in capabilities:
                out.append({"rule": "O007.operation_required_capability_missing", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} requires capability {required_capability}."})
        if spec.required_capability_any and not any(cap in spec.required_capability_any for cap in capabilities):
            out.append({"rule": "O007.operation_required_capability_missing", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} requires at least one exact capability from: {', '.join(sorted(spec.required_capability_any))}."})
        for prefix in spec.required_capability_prefixes:
            if not any(cap.startswith(prefix) for cap in capabilities):
                out.append({"rule": "O007.operation_required_capability_missing", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} requires a capability with prefix {prefix}."})
        if not spec.allow_extra_capabilities:
            allowed_prefixes = spec.allowed_capability_prefixes
            allowed_exact = spec.allowed_capabilities
            for cap in capabilities:
                if cap in allowed_exact:
                    continue
                if any(cap.startswith(prefix) for prefix in allowed_prefixes):
                    continue
                out.append({"rule": "O012.operation_declares_unallowed_capability", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} does not allow declared capability {cap}."})
        if spec.requires_policy_any and not (spec.requires_policy_any & policies):
            out.append({"rule": "O008.operation_required_policy_missing", "severity": "critical", "target": op_id, "message": f"Operation spec {spec.id} requires one of policies: {', '.join(sorted(spec.requires_policy_any))}."})
        return out


@lru_cache(maxsize=1)
def _default_operation_registry() -> OperationRegistry:
    return OperationRegistry.load()


def get_operation_registry() -> OperationRegistry:
    bundle = active_registry_bundle()
    if bundle is not None:
        return bundle.operation_registry
    return _default_operation_registry()


def _profile_forbidden_roles(workflow: str) -> set[str]:
    profile = get_registry().workflow_profile(workflow)
    return {str(x) for x in (profile.get("forbidden_roles", []) or [])}
