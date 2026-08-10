"""Compile additive workflow profiles into isolated registry bundles."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from .canonical import sha256_json
from .core import load_yaml_no_duplicate_keys
from .evidence_ledger import EvidenceLedger, get_evidence_ledger
from .operation_registry import OperationRegistry, get_operation_registry
from .profile_manifest import LoadedProfileManifest, validate_profile_manifest
from .registry_context import ActiveRegistryBundle, active_registry_bundle, use_registry_bundle
from .registry_provenance import registry_snapshot, registry_snapshot_failures, stable_registry_snapshot_projection
from .resources import read_registry_text
from .safety_registry import SafetyRegistry, compact, get_registry


class ProfileCompilationError(ValueError):
    """Raised when an additive profile collides with protected registry data."""


@dataclass(frozen=True)
class CompiledProfile:
    profile_id: str
    manifest_sha256: str
    bundle: ActiveRegistryBundle | None
    registry_mode: str
    base_snapshot_hash: str

    @property
    def uses_registry_override(self) -> bool:
        return self.bundle is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "AiNIRCompiledProfile",
            "version": "ainir.compiled-profile.v1",
            "profile_id": self.profile_id,
            "manifest_sha256": self.manifest_sha256,
            "registry_mode": self.registry_mode,
            "uses_registry_override": self.uses_registry_override,
            "base_snapshot_hash": self.base_snapshot_hash,
            "registry_snapshot_hash": self.bundle.snapshot.get("combined_sha256") if self.bundle else self.base_snapshot_hash,
            "production_runtime_ready": False,
        }


def _canonical_item(label: str, data: Any) -> dict[str, Any]:
    digest = sha256_json(data)
    return {
        "label": label,
        "source_path": f"profile://{label}",
        "raw_sha256": digest,
        "canonical_sha256": digest,
    }


def _assert_unique(value: str, existing: set[str], *, label: str) -> None:
    if value in existing:
        raise ProfileCompilationError(f"profile {label} collides with protected value {value!r}")
    existing.add(value)


def _load_external_consumer_profiles() -> dict[str, Any]:
    data = load_yaml_no_duplicate_keys(read_registry_text("external_consumer_profiles.yaml")) or {}
    return dict(data) if isinstance(data, Mapping) else {}


def _compile_additive(manifest: LoadedProfileManifest) -> ActiveRegistryBundle:
    active = active_registry_bundle()
    if active is not None:
        raise ProfileCompilationError(
            f"nested profile compilation is forbidden; active profile is {active.profile_id!r}"
        )
    data = manifest.data
    extensions = data.get("extensions") if isinstance(data.get("extensions"), Mapping) else {}

    # Defense in depth: Profile Manifest validation already refuses these P3
    # surfaces. The compiler independently rejects them so a future caller
    # cannot bypass validation and silently widen the trusted taxonomy.
    forbidden_extension_fields = (
        "effect_capability_contracts",
        "effect_aliases",
        "role_markers",
        "allowed_external_effects",
    )
    for field_name in forbidden_extension_fields:
        if extensions.get(field_name):
            raise ProfileCompilationError(
                f"P3 additive profiles cannot define {field_name}; core registry governance is required"
            )
    forbidden_operation_fields = (
        "required_effect_families",
        "allowed_effect_families",
        "required_capability_prefixes",
        "allowed_capability_prefixes",
    )
    for operation in extensions.get("operations", []) or []:
        if isinstance(operation, Mapping):
            for field_name in forbidden_operation_fields:
                if operation.get(field_name):
                    raise ProfileCompilationError(
                        f"P3 additive profile operation cannot define {field_name}; exact contracts are required"
                    )

    base_safety = deepcopy(get_registry().data)
    base_operations = deepcopy(get_operation_registry().data)
    base_evidence = deepcopy(get_evidence_ledger().data)
    external_profiles = _load_external_consumer_profiles()
    base_snapshot = registry_snapshot()

    canonical_workflows = list(base_safety.get("canonical_workflows", []) or [])
    workflow_ids = {str(item) for item in canonical_workflows}
    workflow_aliases = dict(base_safety.get("workflow_aliases", {}) or {})
    workflow_profiles = dict(base_safety.get("workflow_profiles", {}) or {})

    for workflow in extensions.get("workflows", []) or []:
        if not isinstance(workflow, Mapping):
            raise ProfileCompilationError("workflow extension must be an object")
        workflow_id = str(workflow.get("id", ""))
        _assert_unique(workflow_id, workflow_ids, label="workflow id")
        canonical_workflows.append(workflow_id)
        semantic_profile = workflow.get("semantic_profile")
        if not isinstance(semantic_profile, Mapping):
            raise ProfileCompilationError(f"workflow {workflow_id!r} has no semantic_profile")
        workflow_profiles[workflow_id] = deepcopy(dict(semantic_profile))
        for alias in workflow.get("aliases", []) or []:
            alias_key = str(alias)
            normalized = "_".join(part for part in compact(alias_key).split(".") if part)
            compact_key = normalized.replace("_", "")
            for key in {alias_key, normalized, compact_key}:
                if not key:
                    continue
                if key in workflow_aliases and workflow_aliases[key] != workflow_id:
                    raise ProfileCompilationError(f"workflow alias {key!r} collides with protected workflow {workflow_aliases[key]!r}")
                workflow_aliases[key] = workflow_id

    base_safety["canonical_workflows"] = canonical_workflows
    base_safety["workflow_aliases"] = workflow_aliases
    base_safety["workflow_profiles"] = workflow_profiles

    effect_aliases = dict(base_safety.get("effect_aliases", {}) or {})
    for alias, target in (extensions.get("effect_aliases", {}) or {}).items():
        alias_s = str(alias)
        target_s = str(target)
        if alias_s in effect_aliases and effect_aliases[alias_s] != target_s:
            raise ProfileCompilationError(f"effect alias {alias_s!r} collides with protected effect alias")
        effect_aliases[alias_s] = target_s
    base_safety["effect_aliases"] = effect_aliases

    capability_contracts = dict(base_safety.get("capability_contracts", {}) or {})
    for effect, spec in (extensions.get("effect_capability_contracts", {}) or {}).items():
        effect_s = str(effect)
        if effect_s in capability_contracts:
            raise ProfileCompilationError(f"effect capability contract {effect_s!r} cannot override the base registry")
        capability_contracts[effect_s] = deepcopy(dict(spec)) if isinstance(spec, Mapping) else spec
    base_safety["capability_contracts"] = capability_contracts

    role_markers = dict(base_safety.get("role_markers", {}) or {})
    for role, marker in (extensions.get("role_markers", {}) or {}).items():
        role_s = str(role)
        if role_s in role_markers:
            raise ProfileCompilationError(f"role marker {role_s!r} cannot override the base registry")
        role_markers[role_s] = deepcopy(dict(marker)) if isinstance(marker, Mapping) else marker
    base_safety["role_markers"] = role_markers

    allowed_external = list(base_safety.get("allowed_external_effects", []) or [])
    allowed_external_set = {str(item) for item in allowed_external}
    for effect in extensions.get("allowed_external_effects", []) or []:
        effect_s = str(effect)
        if effect_s not in allowed_external_set:
            allowed_external.append(effect_s)
            allowed_external_set.add(effect_s)
    base_safety["allowed_external_effects"] = allowed_external

    trusted_evidence = dict(base_safety.get("trusted_evidence", {}) or {})
    trusted_producers = list(trusted_evidence.get("trusted_producers", []) or [])
    if "profile_fixture" not in trusted_producers:
        trusted_producers.append("profile_fixture")
    trusted_evidence["trusted_producers"] = trusted_producers
    base_safety["trusted_evidence"] = trusted_evidence

    operation_specs = list(base_operations.get("operations", []) or [])
    operation_ids = {str(item.get("id")) for item in operation_specs if isinstance(item, Mapping) and isinstance(item.get("id"), str)}
    operation_aliases: set[str] = set()
    for item in operation_specs:
        if not isinstance(item, Mapping):
            continue
        operation_aliases.add(compact(item.get("id", "")))
        operation_aliases.update(compact(alias) for alias in (item.get("aliases", []) or []) if isinstance(alias, str))
    for operation in extensions.get("operations", []) or []:
        if not isinstance(operation, Mapping):
            raise ProfileCompilationError("operation extension must be an object")
        item = deepcopy(dict(operation))
        op_id = str(item.get("id", ""))
        _assert_unique(op_id, operation_ids, label="operation id")
        compact_id = compact(op_id)
        if compact_id in operation_aliases:
            raise ProfileCompilationError(f"operation id {op_id!r} collides with a protected operation alias")
        for alias in item.get("aliases", []) or []:
            alias_key = compact(alias)
            if alias_key in operation_aliases:
                raise ProfileCompilationError(f"operation alias {alias!r} collides with a protected operation")
            operation_aliases.add(alias_key)
        item["trust_level"] = "profile_fixture"
        item["allow_extra_effects"] = False
        item["allow_extra_capabilities"] = False
        operation_specs.append(item)
    trusted_levels = list(base_operations.get("trusted_spec_levels", []) or [])
    if "profile_fixture" not in trusted_levels:
        trusted_levels.append("profile_fixture")
    base_operations["trusted_spec_levels"] = trusted_levels
    base_operations["operations"] = operation_specs

    evidence_records = list(base_evidence.get("records", []) or [])
    evidence_ids = {str(item.get("id")) for item in evidence_records if isinstance(item, Mapping) and isinstance(item.get("id"), str)}
    for record in extensions.get("evidence_records", []) or []:
        if not isinstance(record, Mapping):
            raise ProfileCompilationError("evidence extension must be an object")
        item = deepcopy(dict(record))
        evidence_id = str(item.get("id", ""))
        _assert_unique(evidence_id, evidence_ids, label="evidence id")
        item["producer_kind"] = "profile_fixture"
        evidence_records.append(item)
    base_evidence["records"] = evidence_records

    safety = SafetyRegistry(base_safety)
    operations = OperationRegistry(base_operations)
    evidence = EvidenceLedger(base_evidence, manifest.root)

    pack_path = (manifest.root / str(data.get("conformance", {}).get("pack", "conformance.yaml"))).resolve()
    try:
        pack_data = load_yaml_no_duplicate_keys(pack_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ProfileCompilationError(f"cannot read conformance pack for snapshot: {exc}") from exc

    items = {
        "safety_registry": _canonical_item("safety_registry", base_safety),
        "operation_spec_registry": _canonical_item("operation_spec_registry", base_operations),
        "evidence_ledger": _canonical_item("evidence_ledger", base_evidence),
        "external_consumer_profiles": _canonical_item("external_consumer_profiles", external_profiles),
        "profile_manifest": _canonical_item("profile_manifest", data),
        "profile_conformance_pack": _canonical_item("profile_conformance_pack", pack_data),
    }
    snapshot: dict[str, Any] = {
        "kind": "AiNIRRegistrySnapshot",
        "version": "ainir.profile-registry-snapshot.v1",
        "profile_id": data.get("profile_id"),
        "profile_manifest_sha256": manifest.canonical_sha256,
        "base_registry_snapshot_hash": base_snapshot.get("combined_sha256"),
        "items": items,
    }
    snapshot["combined_sha256"] = sha256_json(stable_registry_snapshot_projection(snapshot))
    snapshot["valid"] = not registry_snapshot_failures(snapshot)
    if not snapshot["valid"]:
        raise ProfileCompilationError(f"compiled profile registry snapshot is invalid: {registry_snapshot_failures(snapshot)}")

    return ActiveRegistryBundle(
        profile_id=str(data.get("profile_id")),
        safety_registry=safety,
        operation_registry=operations,
        evidence_ledger=evidence,
        snapshot=snapshot,
        manifest_sha256=manifest.canonical_sha256,
        production_runtime_ready=False,
    )


def compile_profile(manifest: LoadedProfileManifest) -> CompiledProfile:
    report = validate_profile_manifest(manifest)
    if not report.valid:
        raise ProfileCompilationError(
            "profile manifest is invalid: " + "; ".join(f"{issue.code}@{issue.path}" for issue in report.issues[:8])
        )
    base_snapshot_hash = str(registry_snapshot().get("combined_sha256"))
    mode = str(manifest.data.get("registry_mode"))
    if mode == "packaged":
        return CompiledProfile(
            profile_id=manifest.profile_id,
            manifest_sha256=manifest.canonical_sha256,
            bundle=None,
            registry_mode=mode,
            base_snapshot_hash=base_snapshot_hash,
        )
    bundle = _compile_additive(manifest)
    return CompiledProfile(
        profile_id=manifest.profile_id,
        manifest_sha256=manifest.canonical_sha256,
        bundle=bundle,
        registry_mode=mode,
        base_snapshot_hash=base_snapshot_hash,
    )


@contextmanager
def profile_registry_context(compiled: CompiledProfile) -> Iterator[ActiveRegistryBundle | None]:
    if compiled.bundle is None:
        yield None
        return
    active = active_registry_bundle()
    if active is not None:
        raise ProfileCompilationError(
            f"nested profile registry contexts are forbidden; active profile is {active.profile_id!r}"
        )
    with use_registry_bundle(compiled.bundle) as bundle:
        yield bundle


__all__ = [
    "CompiledProfile",
    "ProfileCompilationError",
    "compile_profile",
    "profile_registry_context",
]
