"""Single source of truth safety registry for AiNIR public demo.

This module is the first pre-v1 hardening step. Normalizer, verifier,
policy core, and lowerer must rely on this registry instead of keeping local
alias/allowlist copies. Provider/model output remains untrusted until it is
validated against this registry and checked by the verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

from .core import load_yaml_no_duplicate_keys
from .registry_context import active_registry_bundle

SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


def compact(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", ".", str(value).strip().lower()).strip(".")


def strict_safe_id(value: object) -> bool:
    return isinstance(value, str) and value == value.strip() and bool(SAFE_ID_RE.fullmatch(value))


@dataclass(frozen=True)
class EvidenceDecision:
    checked: bool
    reason: str


class SafetyRegistry:
    def __init__(self, data: Mapping[str, Any]):
        self.data = dict(data)
        self.canonical_workflows = set(data.get("canonical_workflows", []))
        self.workflow_aliases = dict(data.get("workflow_aliases", {}))
        self.effect_aliases = dict(data.get("effect_aliases", {}))
        self.allowed_external_effects = set(data.get("allowed_external_effects", []))
        self.effect_families = dict(data.get("effect_families", {}))
        self.safety_critical_effect_families = dict(data.get("safety_critical_effect_families", {}))
        self.safety_critical_operation_patterns = dict(data.get("safety_critical_operation_patterns", {}))
        self.capability_contracts = dict(data.get("capability_contracts", {}))
        self.lowering_type_allowlist = set(data.get("lowering_type_allowlist", []))
        self.lowering_return_allowlist = set(data.get("lowering_return_allowlist", []))
        self.trusted_evidence = dict(data.get("trusted_evidence", {}))
        self.workflow_profiles = dict(data.get("workflow_profiles", {}))
        self.role_markers = dict(data.get("role_markers", {}))
        self.ts_reserved_words = set(data.get("typescript_reserved_words", []))

    @classmethod
    def load(cls, path: str | Path | None = None) -> "SafetyRegistry":
        if path is not None:
            with Path(path).open("r", encoding="utf-8") as f:
                return cls(load_yaml_no_duplicate_keys(f.read()) or {})

        # Prefer packaged data so editable/install mode does not depend on CWD.
        try:
            content = resources.files("ainir.registries").joinpath("safety_registry.yaml").read_text(encoding="utf-8")
            return cls(load_yaml_no_duplicate_keys(content) or {})
        except Exception:
            pass

        # Fallback for direct source checkout.
        here = Path(__file__).resolve()
        for candidate in (
            here.parents[2] / "registries" / "safety_registry.yaml",
            Path.cwd() / "registries" / "safety_registry.yaml",
        ):
            if candidate.exists():
                with candidate.open("r", encoding="utf-8") as f:
                    return cls(load_yaml_no_duplicate_keys(f.read()) or {})
        raise RuntimeError("safety_registry.yaml not found")

    def normalize_workflow(self, workflow: object) -> tuple[str, bool]:
        if not isinstance(workflow, str):
            return "", False
        if workflow in self.canonical_workflows:
            return workflow, False
        key = re.sub(r"[^a-z0-9]+", "_", workflow.strip().lower()).strip("_")
        if key in self.workflow_aliases:
            return self.workflow_aliases[key], True
        compact_key = key.replace("_", "")
        if compact_key in self.workflow_aliases:
            return self.workflow_aliases[compact_key], True
        return workflow, False

    def is_known_workflow(self, workflow: object) -> bool:
        return isinstance(workflow, str) and workflow in self.canonical_workflows

    def normalize_effect(self, effect: object) -> tuple[str, bool]:
        if not isinstance(effect, str):
            return "", False
        if effect != effect.strip():
            return effect, False
        alias = self.effect_aliases.get(effect)
        if alias:
            return alias, True
        c = compact(effect)
        alias = self.effect_aliases.get(c)
        if alias:
            return alias, True
        return effect, False

    def classify_effect(self, effect: object) -> set[str]:
        """Return registry-defined effect families for an effect id.

        This intentionally avoids ad-hoc substring fallbacks. Families are
        derived from registry patterns and matched on compact token boundaries
        so terms such as ``db`` do not match unrelated tokens such as
        ``debug``. Updating family behavior must happen in the registry, not in
        inline classifier code.
        """
        if not isinstance(effect, str):
            return set()
        c = compact(effect)
        families: set[str] = set()
        for name, spec in self.effect_families.items():
            if self._matches_family(c, spec):
                families.add(name)
        for name, spec in self.safety_critical_effect_families.items():
            if self._matches_family(c, spec):
                families.add(name)
        if c.startswith("effect.external") and effect not in self.allowed_external_effects:
            families.add("external_unallowlisted")
        if c.startswith("effect.external"):
            families.add("external")
        return families

    @staticmethod
    def _tokens(compact_value: str) -> list[str]:
        return [t for t in compact_value.split(".") if t]

    @classmethod
    def _contains_term(cls, compact_value: str, term: object) -> bool:
        needle = compact(term)
        if not needle:
            return False
        hay = cls._tokens(compact_value)
        parts = cls._tokens(needle)
        if not parts:
            return False
        if len(parts) == 1:
            return parts[0] in hay
        n = len(parts)
        return any(hay[i:i+n] == parts for i in range(0, max(0, len(hay) - n + 1)))

    def _matches_family(self, compact_value: str, spec: Mapping[str, Any]) -> bool:
        def present(items: Any) -> bool:
            return any(self._contains_term(compact_value, item) for item in (items or []))

        includes_all = spec.get("includes_all", []) or []
        if any(not self._contains_term(compact_value, item) for item in includes_all):
            return False
        includes_any = spec.get("includes_any", []) or []
        if includes_any and not present(includes_any):
            return False
        action_any = spec.get("action_any", []) or []
        if action_any and not present(action_any):
            return False
        excludes_any = spec.get("excludes_any", []) or []
        if present(excludes_any):
            return False
        return True

    def classify_operation(self, op_name: object) -> set[str]:
        """Return registry-defined operation families for an operation id."""
        if not isinstance(op_name, str):
            return set()
        c = compact(op_name)
        families: set[str] = set()
        for name, spec in self.safety_critical_operation_patterns.items():
            if self._matches_operation(c, spec):
                implied = spec.get("implied_family", name)
                families.add(str(implied))
        return families

    def _matches_operation(self, compact_value: str, spec: Mapping[str, Any]) -> bool:
        def present(items: Any) -> bool:
            return any(self._contains_term(compact_value, item) for item in (items or []))

        includes_all = spec.get("includes_all", []) or []
        if any(not self._contains_term(compact_value, item) for item in includes_all):
            return False
        includes_any = spec.get("includes_any", []) or []
        action_any = spec.get("action_any", []) or []
        suffix_any = spec.get("op_suffix_any", []) or []
        # A risk pattern may define multiple conditions. They are conjunctive,
        # except suffix_any is only an additional guard when present.
        if includes_any and not present(includes_any):
            return False
        if action_any and not present(action_any):
            return False
        if suffix_any and not any(compact_value.endswith("." + compact(str(s))) or compact_value.endswith(compact(str(s))) for s in suffix_any):
            return False
        return True

    def lowering_allowed_types(self) -> set[str]:
        return set(self.lowering_type_allowlist)

    def lowering_allowed_returns(self) -> set[str]:
        return set(self.lowering_return_allowlist)

    def required_effect_family_for_operation_family(self, family: str) -> str | None:
        for _name, spec in self.safety_critical_operation_patterns.items():
            if str(spec.get("implied_family", _name)) == family:
                return spec.get("requires_explicit_effect_family")
        # Broad fallback.
        if family in {"payment", "external_network", "destructive_delete", "raw_token", "raw_pii", "notification_real"}:
            return {
                "payment": "payment",
                "external_network": "external",
                "destructive_delete": "destructive",
                "raw_token": "secret",
                "raw_pii": "privacy",
                "notification_real": "notification",
            }[family]
        return None

    def evidence_decision(self, ev: Mapping[str, Any], module_id: str, workflow: str) -> EvidenceDecision:
        eid = ev.get("id")
        if not isinstance(eid, str) or not eid.strip():
            return EvidenceDecision(False, "evidence id is missing")

        kind = ev.get("kind")
        if kind not in set(self.trusted_evidence.get("allowed_kinds", [])):
            return EvidenceDecision(False, "evidence kind is not allowed")

        untrusted = {str(s).lower() for s in self.trusted_evidence.get("untrusted_sources", [])}
        source_fields = ("source", "source_ref", "producer", "producer_kind", "generated_by", "checked_by")
        for field in source_fields:
            value = ev.get(field)
            if isinstance(value, str) and compact(value).replace(".", "") in {u.replace("-", "").replace("_", "") for u in untrusted}:
                return EvidenceDecision(False, f"evidence {field} is self-attested or model/provider generated")
            if isinstance(value, str) and value.strip().lower() in untrusted:
                return EvidenceDecision(False, f"evidence {field} is self-attested or model/provider generated")

        bundled = self.trusted_evidence.get("bundled_ids", {}) or {}
        if eid in bundled:
            spec = bundled[eid]
            if spec.get("supports_module") and spec.get("supports_module") != module_id:
                return EvidenceDecision(False, "bundled evidence id does not support this module")
            if spec.get("supports_workflow") and spec.get("supports_workflow") != workflow:
                return EvidenceDecision(False, "bundled evidence id does not support this workflow")
            try:
                reliability = float(ev.get("reliability", 0))
            except Exception:
                reliability = 0.0
            if reliability < float(spec.get("min_reliability", 0.8)):
                return EvidenceDecision(False, "evidence reliability is below registry threshold")
            if ev.get("checked") is not True and ev.get("status") != "checked":
                return EvidenceDecision(False, "evidence is not marked checked")
            return EvidenceDecision(True, "bundled evidence is registry-bound")

        # Public demo deliberately rejects free-floating checked evidence.
        return EvidenceDecision(False, "evidence id is not bound to the trusted registry")

    def effect_capability_prefixes(self, effect: str) -> tuple[str, ...]:
        spec = self.capability_contracts.get(effect)
        if not isinstance(spec, Mapping):
            return ()
        return tuple(spec.get("prefixes", []) or [])

    def workflow_profile(self, workflow: str) -> Mapping[str, Any]:
        return self.workflow_profiles.get(workflow, {}) or {}

    def role_satisfied(self, role: str, operations: list[Mapping[str, Any]], policy_ids: set[str]) -> bool:
        marker = self.role_markers.get(role, {}) or {}
        op_needles = [compact(x) for x in marker.get("op_any", []) or []]
        effect_needles = [compact(x) for x in marker.get("effect_any", []) or []]
        policy_needles = set(marker.get("policy_any", []) or [])
        if policy_needles & policy_ids:
            return True
        for op in operations:
            op_name = compact(op.get("op", ""))
            op_id = compact(op.get("id", ""))
            if any(n in op_name or n in op_id for n in op_needles):
                # Reject obvious placeholders/noops.
                if any(x in op_name or x in op_id for x in ("noop", "placeholder", "stub")):
                    continue
                return True
            for eff in op.get("effects", []) or []:
                e = compact(eff)
                if any(n in e for n in effect_needles):
                    return True
            for pol in op.get("policies", []) or []:
                if isinstance(pol, str) and pol in policy_needles:
                    return True
        return False


@lru_cache(maxsize=1)
def _default_registry() -> SafetyRegistry:
    return SafetyRegistry.load()


def get_registry() -> SafetyRegistry:
    bundle = active_registry_bundle()
    if bundle is not None:
        return bundle.safety_registry
    return _default_registry()
