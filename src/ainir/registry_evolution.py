"""Portable registry snapshots, semantic diffs, and explicit migrations.

P4 adds an evolution layer without changing the receipt-bound pre-v1 registry
snapshot used by existing TrustReceipts.  Evolution snapshots carry the public
registry data needed for deterministic review and replay, while preserving the
original runtime snapshot hash as an immutable binding.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .canonical import read_json_object_artifact, sha256_json
from .contracts import (
    REGISTRY_DIFF_CONTRACT,
    REGISTRY_DIFF_KIND,
    REGISTRY_MIGRATION_RECORD_CONTRACT,
    REGISTRY_MIGRATION_RECORD_KIND,
    REGISTRY_SNAPSHOT_CONTRACT,
    REGISTRY_SNAPSHOT_KIND,
)
from .core import load_yaml_no_duplicate_keys
from .evidence_ledger import EvidenceLedger, get_evidence_ledger
from .operation_registry import OperationRegistry, get_operation_registry
from .registry_context import ActiveRegistryBundle, active_registry_bundle
from .registry_provenance import (
    registry_snapshot,
    registry_snapshot_failures,
    stable_registry_snapshot_projection,
)
from .resources import read_registry_text
from .safety_registry import SafetyRegistry, get_registry


_COMPONENT_NAMES = (
    "safety_registry",
    "operation_spec_registry",
    "evidence_ledger",
    "external_consumer_profiles",
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")
_METADATA_FIELDS = {
    "description",
    "display_name",
    "note",
    "purpose",
    "title",
    "version",
}
_ORDERED_LIST_FIELDS = {
    "transaction_order_roles",
}
_REQUIRED_PREFIXES = (
    "required_",
    "requires_",
)
_FORBIDDEN_PREFIXES = (
    "forbidden_",
    "denied_",
)
_ALLOWED_PREFIXES = (
    "allowed_",
    "trusted_",
)
_SNAPSHOT_ALLOWED_FIELDS = frozenset({
    "kind", "version", "snapshot_id", "snapshot_sha256", "profile_id",
    "parent_snapshot_hash", "runtime_registry_snapshot_hash", "runtime_snapshot",
    "components", "valid", "production_runtime_ready",
})
_RUNTIME_SNAPSHOT_ALLOWED_FIELDS = frozenset({
    "kind", "version", "items", "combined_sha256", "valid", "profile_id",
    "profile_manifest_sha256", "base_registry_snapshot_hash",
})
_RUNTIME_ITEM_ALLOWED_FIELDS = frozenset({
    "label", "source_path", "raw_sha256", "canonical_sha256", "missing",
    "load_error", "copy_drift", "duplicate_record_ids",
})
_COMPONENT_ITEM_ALLOWED_FIELDS = frozenset({"canonical_sha256", "data"})
_DIFF_ALLOWED_FIELDS = frozenset({
    "kind", "version", "diff_id", "diff_sha256", "source_snapshot_id",
    "target_snapshot_id", "source_snapshot_sha256", "target_snapshot_sha256",
    "source_runtime_snapshot_hash", "target_runtime_snapshot_hash",
    "overall_classification", "changed", "change_count", "classification_counts",
    "requires_explicit_migration", "changes", "production_runtime_ready",
})
_DIFF_CHANGE_ALLOWED_FIELDS = frozenset({
    "path", "change_type", "old", "new", "classification", "rationale", "change_id",
})
_MIGRATION_ALLOWED_FIELDS = frozenset({
    "kind", "version", "migration_id", "record_sha256", "source_snapshot_sha256",
    "target_snapshot_sha256", "source_runtime_snapshot_hash",
    "target_runtime_snapshot_hash", "registry_diff_sha256", "overall_classification",
    "acknowledged_change_ids", "authorization", "cryptographic_signature_status",
    "production_runtime_ready",
})
_MIGRATION_AUTH_ALLOWED_FIELDS = frozenset({
    "status", "actor_id", "mechanism", "reason", "evidence_ref",
})


class RegistryEvolutionError(ValueError):
    """Raised when a registry evolution artifact is malformed or inconsistent."""


@dataclass(frozen=True)
class RegistryArtifactValidationReport:
    kind: str
    overall_status: str
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return self.overall_status == "passed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "overall_status": self.overall_status,
            "checks": [dict(check) for check in self.checks],
        }


_DIFF_CLASSIFICATIONS = frozenset(
    {"tightening", "compatible", "behavioral", "relaxation", "breaking", "unknown"}
)
_CHANGE_TYPES = frozenset({"added", "removed", "modified"})


@dataclass(frozen=True)
class RegistryDiffReport:
    source_snapshot_id: str
    target_snapshot_id: str
    source_snapshot_sha256: str
    target_snapshot_sha256: str
    source_runtime_snapshot_hash: str
    target_runtime_snapshot_hash: str
    overall_classification: str
    changes: tuple[dict[str, Any], ...]
    diff_sha256: str
    diff_id: str

    @property
    def changed(self) -> bool:
        return bool(self.changes)

    def as_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for change in self.changes:
            classification = str(change.get("classification"))
            counts[classification] = counts.get(classification, 0) + 1
        return {
            "kind": REGISTRY_DIFF_KIND,
            "version": REGISTRY_DIFF_CONTRACT,
            "diff_id": self.diff_id,
            "diff_sha256": self.diff_sha256,
            "source_snapshot_id": self.source_snapshot_id,
            "target_snapshot_id": self.target_snapshot_id,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "target_snapshot_sha256": self.target_snapshot_sha256,
            "source_runtime_snapshot_hash": self.source_runtime_snapshot_hash,
            "target_runtime_snapshot_hash": self.target_runtime_snapshot_hash,
            "overall_classification": self.overall_classification,
            "changed": self.changed,
            "change_count": len(self.changes),
            "classification_counts": dict(sorted(counts.items())),
            "requires_explicit_migration": any(
                change.get("classification") != "compatible" for change in self.changes
            ),
            "changes": [dict(change) for change in self.changes],
            "production_runtime_ready": False,
        }


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _check(name: str, passed: bool, expected: Any, actual: Any, **extra: Any) -> dict[str, Any]:
    return {
        "check": name,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        **extra,
    }


def _component_data() -> dict[str, dict[str, Any]]:
    bundle = active_registry_bundle()
    if bundle is not None:
        safety = bundle.safety_registry.data
        operations = bundle.operation_registry.data
        evidence = bundle.evidence_ledger.data
    else:
        safety = get_registry().data
        operations = get_operation_registry().data
        evidence = get_evidence_ledger().data
    external = load_yaml_no_duplicate_keys(read_registry_text("external_consumer_profiles.yaml")) or {}
    return {
        "safety_registry": _json_copy(dict(safety)),
        "operation_spec_registry": _json_copy(dict(operations)),
        "evidence_ledger": _json_copy(dict(evidence)),
        "external_consumer_profiles": _json_copy(dict(external)),
    }


def _portable_runtime_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    stable = stable_registry_snapshot_projection(value)
    portable: dict[str, Any] = {
        **stable,
        "combined_sha256": value.get("combined_sha256"),
        "valid": not registry_snapshot_failures(value),
    }
    for field_name in (
        "profile_id",
        "profile_manifest_sha256",
        "base_registry_snapshot_hash",
    ):
        if field_name in value:
            portable[field_name] = value.get(field_name)
    return _json_copy(portable)


def _component_item(label: str, data: Mapping[str, Any]) -> dict[str, Any]:
    digest = sha256_json(data)
    return {
        "label": label,
        "source_path": f"snapshot://{label}",
        "raw_sha256": digest,
        "canonical_sha256": digest,
    }


def _runtime_snapshot_from_components(
    components: Mapping[str, Mapping[str, Any]],
    *,
    profile_id: str | None = None,
) -> dict[str, Any]:
    items = {
        name: _component_item(name, components[name])
        for name in _COMPONENT_NAMES
    }
    runtime: dict[str, Any] = {
        "kind": "AiNIRRegistrySnapshot",
        "version": "ainir.evolution-runtime-registry-snapshot.v1",
        "items": items,
    }
    if profile_id:
        runtime["profile_id"] = profile_id
    runtime["combined_sha256"] = sha256_json(stable_registry_snapshot_projection(runtime))
    runtime["valid"] = not registry_snapshot_failures(runtime)
    return runtime


def _runtime_component_binding_failures(
    runtime: Mapping[str, Any],
    components: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Detect divergence between full component data and receipt-bound hashes."""

    items = runtime.get("items") if isinstance(runtime, Mapping) else None
    if not isinstance(items, Mapping):
        return [{"name": "<runtime>", "reason": "runtime_items_not_object"}]
    failures: list[dict[str, Any]] = []
    for name in _COMPONENT_NAMES:
        runtime_item = items.get(name)
        component = components.get(name)
        runtime_hash = runtime_item.get("canonical_sha256") if isinstance(runtime_item, Mapping) else None
        component_hash = component.get("canonical_sha256") if isinstance(component, Mapping) else None
        if runtime_hash != component_hash:
            failures.append({
                "name": name,
                "reason": "runtime_component_hash_mismatch",
                "runtime_canonical_sha256": runtime_hash,
                "component_canonical_sha256": component_hash,
            })
    return failures


def _snapshot_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    components = snapshot.get("components") if isinstance(snapshot, Mapping) else {}
    projected_components: dict[str, Any] = {}
    if isinstance(components, Mapping):
        for name in sorted(components):
            item = components.get(name)
            if isinstance(item, Mapping):
                projected_components[str(name)] = {
                    "canonical_sha256": item.get("canonical_sha256"),
                    "data": item.get("data"),
                }
            else:
                projected_components[str(name)] = item
    return {
        "kind": snapshot.get("kind"),
        "version": snapshot.get("version"),
        "profile_id": snapshot.get("profile_id"),
        "parent_snapshot_hash": snapshot.get("parent_snapshot_hash"),
        "runtime_registry_snapshot_hash": snapshot.get("runtime_registry_snapshot_hash"),
        "runtime_snapshot": snapshot.get("runtime_snapshot"),
        "components": projected_components,
        "production_runtime_ready": snapshot.get("production_runtime_ready"),
    }


def build_registry_snapshot(
    components: Mapping[str, Mapping[str, Any]],
    *,
    runtime_snapshot: Mapping[str, Any] | None = None,
    profile_id: str | None = None,
    parent_snapshot_hash: str | None = None,
) -> dict[str, Any]:
    """Build one deterministic, portable public registry snapshot artifact."""

    supplied_names = set(str(name) for name in components)
    if supplied_names != set(_COMPONENT_NAMES):
        raise RegistryEvolutionError(
            f"registry snapshot components must be exactly {_COMPONENT_NAMES}; got {sorted(supplied_names)}"
        )
    clean_components: dict[str, dict[str, Any]] = {}
    for name in _COMPONENT_NAMES:
        data = components.get(name)
        if not isinstance(data, Mapping):
            raise RegistryEvolutionError(f"registry component {name!r} must be an object")
        copied = _json_copy(dict(data))
        clean_components[name] = {
            "canonical_sha256": sha256_json(copied),
            "data": copied,
        }
    if profile_id is not None and (
        not isinstance(profile_id, str) or not _SAFE_TOKEN_RE.fullmatch(profile_id)
    ):
        raise RegistryEvolutionError("profile_id must be null or a portable profile id")
    if parent_snapshot_hash is not None and not _SHA256_RE.fullmatch(parent_snapshot_hash):
        raise RegistryEvolutionError("parent_snapshot_hash must be sha256:<64 lowercase hex>")
    if runtime_snapshot is None:
        runtime = _runtime_snapshot_from_components(
            {name: item["data"] for name, item in clean_components.items()},
            profile_id=profile_id,
        )
    else:
        runtime = _portable_runtime_snapshot(runtime_snapshot)
    runtime_hash = runtime.get("combined_sha256")
    if not isinstance(runtime_hash, str) or not _SHA256_RE.fullmatch(runtime_hash):
        raise RegistryEvolutionError("runtime snapshot is missing a valid combined_sha256")
    expected_runtime_hash = sha256_json(stable_registry_snapshot_projection(runtime))
    if runtime_hash != expected_runtime_hash:
        raise RegistryEvolutionError("runtime snapshot combined_sha256 does not match its stable projection")
    if registry_snapshot_failures(runtime):
        raise RegistryEvolutionError(
            f"runtime registry snapshot is invalid: {registry_snapshot_failures(runtime)}"
        )
    binding_failures = _runtime_component_binding_failures(runtime, clean_components)
    if binding_failures:
        raise RegistryEvolutionError(
            f"runtime registry snapshot does not bind the supplied component data: {binding_failures}"
        )
    runtime_profile_id = runtime.get("profile_id")
    if runtime_profile_id != profile_id:
        raise RegistryEvolutionError(
            "profile_id must exactly match runtime_snapshot.profile_id; "
            f"outer={profile_id!r} runtime={runtime_profile_id!r}"
        )
    artifact: dict[str, Any] = {
        "kind": REGISTRY_SNAPSHOT_KIND,
        "version": REGISTRY_SNAPSHOT_CONTRACT,
        "profile_id": profile_id,
        "parent_snapshot_hash": parent_snapshot_hash,
        "runtime_registry_snapshot_hash": runtime_hash,
        "runtime_snapshot": runtime,
        "components": clean_components,
        "production_runtime_ready": False,
    }
    artifact_hash = sha256_json(_snapshot_projection(artifact))
    artifact["snapshot_sha256"] = artifact_hash
    artifact["snapshot_id"] = "ainir.registry.snapshot." + artifact_hash.removeprefix("sha256:")[:20]
    artifact["valid"] = True
    return artifact


def capture_registry_snapshot(
    *,
    parent_snapshot_hash: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Capture the currently active packaged or profile registry as a P4 artifact."""

    runtime = registry_snapshot()
    failures = registry_snapshot_failures(runtime)
    if failures:
        raise RegistryEvolutionError(f"cannot capture an invalid registry snapshot: {failures}")
    runtime_profile_id = runtime.get("profile_id") if isinstance(runtime.get("profile_id"), str) else None
    effective_profile_id = profile_id if profile_id is not None else runtime_profile_id
    return build_registry_snapshot(
        _component_data(),
        runtime_snapshot=runtime,
        profile_id=effective_profile_id,
        parent_snapshot_hash=parent_snapshot_hash,
    )


def validate_registry_snapshot(snapshot: Mapping[str, Any]) -> RegistryArtifactValidationReport:
    checks: list[dict[str, Any]] = []
    unknown_top = sorted(set(snapshot) - _SNAPSHOT_ALLOWED_FIELDS)
    checks.append(_check("snapshot.unknown_fields", not unknown_top, [], unknown_top))
    checks.append(_check("snapshot.kind", snapshot.get("kind") == REGISTRY_SNAPSHOT_KIND, REGISTRY_SNAPSHOT_KIND, snapshot.get("kind")))
    checks.append(_check("snapshot.version", snapshot.get("version") == REGISTRY_SNAPSHOT_CONTRACT, REGISTRY_SNAPSHOT_CONTRACT, snapshot.get("version")))
    profile_id = snapshot.get("profile_id")
    checks.append(_check(
        "snapshot.profile_id",
        profile_id is None or (isinstance(profile_id, str) and bool(_SAFE_TOKEN_RE.fullmatch(profile_id))),
        "null or portable profile id",
        profile_id,
    ))
    parent_hash = snapshot.get("parent_snapshot_hash")
    checks.append(_check("snapshot.parent_snapshot_hash", parent_hash is None or (isinstance(parent_hash, str) and bool(_SHA256_RE.fullmatch(parent_hash))), "null or sha256:<64 lowercase hex>", parent_hash))
    components = snapshot.get("components")
    component_names = set(components) if isinstance(components, Mapping) else set()
    checks.append(_check("snapshot.components", component_names == set(_COMPONENT_NAMES), sorted(_COMPONENT_NAMES), sorted(component_names)))
    if isinstance(components, Mapping):
        for name in _COMPONENT_NAMES:
            item = components.get(name)
            data = item.get("data") if isinstance(item, Mapping) else None
            actual_hash = item.get("canonical_sha256") if isinstance(item, Mapping) else None
            expected_hash = sha256_json(data) if isinstance(data, Mapping) else None
            unknown_component_fields = sorted(set(item) - _COMPONENT_ITEM_ALLOWED_FIELDS) if isinstance(item, Mapping) else []
            checks.append(_check(f"snapshot.components.{name}.unknown_fields", not unknown_component_fields, [], unknown_component_fields))
            checks.append(_check(f"snapshot.components.{name}.data", isinstance(data, Mapping), "object", type(data).__name__))
            checks.append(_check(f"snapshot.components.{name}.canonical_sha256", actual_hash == expected_hash, expected_hash, actual_hash))
            duplicates = _duplicate_ids(data) if isinstance(data, Mapping) else []
            checks.append(_check(f"snapshot.components.{name}.duplicate_ids", not duplicates, [], duplicates))
    runtime = snapshot.get("runtime_snapshot")
    runtime_hash = snapshot.get("runtime_registry_snapshot_hash")
    runtime_unknown = sorted(set(runtime) - _RUNTIME_SNAPSHOT_ALLOWED_FIELDS) if isinstance(runtime, Mapping) else []
    checks.append(_check("snapshot.runtime_snapshot.unknown_fields", not runtime_unknown, [], runtime_unknown))
    runtime_items = runtime.get("items") if isinstance(runtime, Mapping) else None
    if isinstance(runtime_items, Mapping):
        for item_name, runtime_item in sorted(runtime_items.items(), key=lambda pair: str(pair[0])):
            unknown_item_fields = (
                sorted(set(runtime_item) - _RUNTIME_ITEM_ALLOWED_FIELDS)
                if isinstance(runtime_item, Mapping)
                else []
            )
            checks.append(_check(
                f"snapshot.runtime_snapshot.items.{item_name}.unknown_fields",
                isinstance(runtime_item, Mapping) and not unknown_item_fields,
                [],
                unknown_item_fields if isinstance(runtime_item, Mapping) else type(runtime_item).__name__,
            ))
    runtime_valid = isinstance(runtime, Mapping) and not registry_snapshot_failures(runtime)
    expected_runtime_hash = sha256_json(stable_registry_snapshot_projection(runtime)) if isinstance(runtime, Mapping) else None
    checks.append(_check("snapshot.runtime_snapshot", runtime_valid, "valid portable runtime snapshot", registry_snapshot_failures(runtime) if isinstance(runtime, Mapping) else type(runtime).__name__))
    checks.append(_check("snapshot.runtime_registry_snapshot_hash", runtime_hash == expected_runtime_hash, expected_runtime_hash, runtime_hash))
    binding_failures = (
        _runtime_component_binding_failures(runtime, components)
        if isinstance(runtime, Mapping) and isinstance(components, Mapping)
        else [{"reason": "runtime_or_components_not_object"}]
    )
    checks.append(_check(
        "snapshot.runtime_component_bindings",
        not binding_failures,
        [],
        binding_failures,
    ))
    runtime_profile_id = runtime.get("profile_id") if isinstance(runtime, Mapping) else None
    checks.append(_check(
        "snapshot.profile_binding",
        runtime_profile_id == profile_id,
        profile_id,
        runtime_profile_id,
    ))
    expected_snapshot_hash = sha256_json(_snapshot_projection(snapshot))
    checks.append(_check("snapshot.snapshot_sha256", snapshot.get("snapshot_sha256") == expected_snapshot_hash, expected_snapshot_hash, snapshot.get("snapshot_sha256")))
    expected_id = "ainir.registry.snapshot." + expected_snapshot_hash.removeprefix("sha256:")[:20]
    checks.append(_check("snapshot.snapshot_id", snapshot.get("snapshot_id") == expected_id, expected_id, snapshot.get("snapshot_id")))
    checks.append(_check("snapshot.valid", snapshot.get("valid") is True, True, snapshot.get("valid")))
    checks.append(_check("snapshot.production_runtime_ready", snapshot.get("production_runtime_ready") is False, False, snapshot.get("production_runtime_ready")))
    overall = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    return RegistryArtifactValidationReport(REGISTRY_SNAPSHOT_KIND, overall, tuple(checks))


def _duplicate_ids(data: Mapping[str, Any]) -> list[str]:
    duplicates: list[str] = []
    for key in ("records", "operations", "profiles", "workflows"):
        values = data.get(key)
        if not isinstance(values, list):
            continue
        seen: set[str] = set()
        for item in values:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                value = str(item["id"])
                if value in seen and value not in duplicates:
                    duplicates.append(value)
                seen.add(value)
    return sorted(duplicates)


def load_registry_snapshot(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        snapshot = _json_copy(dict(source))
    else:
        artifact = read_json_object_artifact(source, artifact_name="registry_snapshot")
        if not artifact.ok:
            raise RegistryEvolutionError(
                f"cannot read registry snapshot: {artifact.reason}: {artifact.detail}"
            )
        snapshot = artifact.value
    report = validate_registry_snapshot(snapshot)
    if not report.valid:
        failures = [check for check in report.checks if check.get("status") != "passed"]
        raise RegistryEvolutionError(f"registry snapshot validation failed: {failures[:8]}")
    return snapshot


def write_registry_snapshot(path: str | Path, snapshot: Mapping[str, Any]) -> Path:
    checked = load_registry_snapshot(snapshot)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(checked, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def registry_bundle_from_snapshot(
    snapshot: str | Path | Mapping[str, Any],
    *,
    evidence_root: str | Path | None = None,
) -> ActiveRegistryBundle:
    """Rehydrate a validated snapshot into an isolated, context-local bundle."""

    checked = load_registry_snapshot(snapshot)
    components = checked["components"]
    safety_data = components["safety_registry"]["data"]
    operation_data = components["operation_spec_registry"]["data"]
    evidence_data = components["evidence_ledger"]["data"]
    root = Path(evidence_root).resolve() if evidence_root is not None else None
    return ActiveRegistryBundle(
        profile_id=str(checked.get("profile_id") or checked.get("snapshot_id")),
        safety_registry=SafetyRegistry(safety_data),
        operation_registry=OperationRegistry(operation_data),
        evidence_ledger=EvidenceLedger(evidence_data, root),
        snapshot=_json_copy(checked["runtime_snapshot"]),
        manifest_sha256=str(checked["snapshot_sha256"]),
        production_runtime_ready=False,
    )


def _normalize(value: Any, *, field_name: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item, field_name=str(key))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        if value and all(isinstance(item, Mapping) and isinstance(item.get("id"), str) for item in value):
            return {
                str(item["id"]): _normalize(item, field_name=str(item["id"]))
                for item in sorted(value, key=lambda item: str(item["id"]))
            }
        normalized = [_normalize(item) for item in value]
        if field_name not in _ORDERED_LIST_FIELDS and all(
            isinstance(item, (str, int, float, bool)) or item is None for item in normalized
        ):
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
        return normalized
    return value


def _deep_changes(old: Any, new: Any, path: tuple[str, ...]) -> list[dict[str, Any]]:
    if old == new:
        return []
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        changes: list[dict[str, Any]] = []
        keys = sorted(set(old) | set(new), key=str)
        for key in keys:
            child = (*path, str(key))
            if key not in old:
                changes.append({"path": ".".join(child), "change_type": "added", "old": None, "new": new[key]})
            elif key not in new:
                changes.append({"path": ".".join(child), "change_type": "removed", "old": old[key], "new": None})
            else:
                changes.extend(_deep_changes(old[key], new[key], child))
        return changes
    return [{"path": ".".join(path), "change_type": "modified", "old": old, "new": new}]


def _set_delta(old: Any, new: Any) -> tuple[set[Any], set[Any]]:
    if not isinstance(old, Sequence) or isinstance(old, (str, bytes)):
        return set(), set()
    if not isinstance(new, Sequence) or isinstance(new, (str, bytes)):
        return set(), set()
    try:
        old_set = set(old)
        new_set = set(new)
    except TypeError:
        return set(), set()
    return new_set - old_set, old_set - new_set


def _classify_change(change: Mapping[str, Any]) -> tuple[str, str]:
    path = str(change.get("path") or "")
    parts = path.split(".") if path else []
    field_name = parts[-1] if parts else ""
    parent = parts[-2] if len(parts) > 1 else ""
    change_type = str(change.get("change_type"))
    old = change.get("old")
    new = change.get("new")

    if field_name in _METADATA_FIELDS:
        return "compatible", "documentation or declared version metadata changed"

    # Registry ids commonly contain dots. A human-readable dotted path cannot
    # safely recover its immediate parent by splitting on '.', so collection
    # item additions/removals are recognized from both the collection marker and
    # the record-shaped value. Nested field changes do not satisfy this test.
    record_value = new if change_type == "added" else old if change_type == "removed" else None
    if isinstance(record_value, Mapping) and isinstance(record_value.get("id"), str):
        for collection in ("operations", "records", "workflow_profiles"):
            if f".{collection}." in f".{path}.":
                label = collection[:-1] if collection.endswith("s") else collection
                if change_type == "added":
                    return "relaxation", f"new {label} can authorize previously unknown semantics"
                return "breaking", f"existing {label} was removed"
        if ".profiles." in f".{path}.":
            if change_type == "added":
                return "behavioral", "consumer profile surface was added"
            return "breaking", "consumer profile surface was removed"

    if parent in {"operations", "records", "workflow_profiles"}:
        if change_type == "added":
            return "relaxation", f"new {parent[:-1] if parent.endswith('s') else parent} can authorize previously unknown semantics"
        if change_type == "removed":
            return "breaking", f"existing {parent[:-1] if parent.endswith('s') else parent} was removed"
    if parent == "profiles":
        if change_type == "added":
            return "behavioral", "consumer profile surface was added"
        if change_type == "removed":
            return "breaking", "consumer profile surface was removed"

    if parent == "workflow_aliases":
        if change_type == "added":
            return "relaxation", "new workflow alias can recognize previously refused input"
        if change_type == "removed":
            return "breaking", "workflow alias removal can break existing drafts"
        return "unknown", "workflow alias retargeting requires human semantic review"
    if parent == "effect_aliases":
        return "unknown", "effect alias changes can tighten or relax effect classification"

    if field_name == "canonical_workflows":
        added, removed = _set_delta(old, new)
        if added and not removed:
            return "relaxation", "new workflow ids can recognize previously refused workflows"
        if removed and not added:
            return "breaking", "workflow ids were removed"
        return "unknown", "workflow set changed in both directions"

    if field_name in {"aliases", "semantic_roles"}:
        added, removed = _set_delta(old, new)
        if added and not removed:
            return "relaxation", f"additional {field_name} can satisfy more inputs"
        if removed and not added:
            return "breaking", f"removing {field_name} can invalidate existing inputs"
        return "unknown", f"{field_name} changed in both directions"

    if isinstance(old, bool) and isinstance(new, bool):
        if field_name.startswith(_REQUIRED_PREFIXES) or field_name.startswith(_FORBIDDEN_PREFIXES):
            return (
                ("tightening", f"{field_name} changed from false to true")
                if new
                else ("relaxation", f"{field_name} changed from true to false")
            )
        if field_name.startswith(_ALLOWED_PREFIXES):
            return (
                ("relaxation", f"{field_name} changed from false to true")
                if new
                else ("tightening", f"{field_name} changed from true to false")
            )

    if field_name.startswith(_REQUIRED_PREFIXES) or field_name.startswith(_FORBIDDEN_PREFIXES):
        added, removed = _set_delta(old, new)
        if added and not removed:
            return "tightening", f"{field_name} gained requirements or prohibitions"
        if removed and not added:
            return "relaxation", f"{field_name} lost requirements or prohibitions"
        if change_type == "added":
            return "tightening", f"{field_name} was added"
        if change_type == "removed":
            return "relaxation", f"{field_name} was removed"
        return "behavioral", f"{field_name} changed in both directions"

    if field_name.startswith(_ALLOWED_PREFIXES) or field_name in {"trusted_spec_levels"}:
        added, removed = _set_delta(old, new)
        if added and not removed:
            return "relaxation", f"{field_name} authorizes additional values"
        if removed and not added:
            return "tightening", f"{field_name} authorizes fewer values"
        if change_type == "added":
            return "relaxation", f"{field_name} was added"
        if change_type == "removed":
            return "tightening", f"{field_name} was removed"
        return "behavioral", f"{field_name} changed in both directions"

    if field_name in {"allow_extra_effects", "allow_extra_capabilities"} and isinstance(old, bool) and isinstance(new, bool):
        return ("relaxation", f"{field_name} changed from false to true") if new else ("tightening", f"{field_name} changed from true to false")
    if field_name == "min_reliability" and isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return ("tightening", "minimum evidence reliability increased") if new > old else ("relaxation", "minimum evidence reliability decreased")
    if field_name == "reliability" and isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return ("relaxation", "evidence reliability increased") if new > old else ("tightening", "evidence reliability decreased")
    if field_name == "status" and "evidence_ledger" in parts:
        if old != "checked" and new == "checked":
            return "relaxation", "evidence became checked and may now satisfy claims"
        if old == "checked" and new != "checked":
            return "tightening", "evidence is no longer checked"
        return "behavioral", "evidence status changed"
    if field_name in {"unknown_operation_policy", "transaction_contract", "trust_level", "producer_kind"}:
        return "unknown", f"{field_name} changes require domain review"

    return "unknown", "no conservative semantic classifier covers this path"


def _overall_classification(changes: Sequence[Mapping[str, Any]]) -> str:
    classes = {str(change.get("classification")) for change in changes}
    if not classes or classes == {"compatible"}:
        return "compatible"
    if "unknown" in classes:
        return "unknown"
    if "breaking" in classes:
        return "breaking"
    if "relaxation" in classes and "tightening" in classes:
        return "behavioral"
    if "relaxation" in classes:
        return "relaxation"
    if "tightening" in classes:
        return "tightening"
    if "behavioral" in classes:
        return "behavioral"
    return "compatible"


def diff_registry_snapshots(
    source: str | Path | Mapping[str, Any],
    target: str | Path | Mapping[str, Any],
) -> RegistryDiffReport:
    old = load_registry_snapshot(source)
    new = load_registry_snapshot(target)
    old_components = {
        name: _normalize(old["components"][name]["data"], field_name=name)
        for name in _COMPONENT_NAMES
    }
    new_components = {
        name: _normalize(new["components"][name]["data"], field_name=name)
        for name in _COMPONENT_NAMES
    }
    raw_changes = _deep_changes(old_components, new_components, ("components",))
    changes: list[dict[str, Any]] = []
    for raw in raw_changes:
        classification, rationale = _classify_change(raw)
        item = {
            **raw,
            "classification": classification,
            "rationale": rationale,
        }
        item["change_id"] = "ainir.registry.change." + sha256_json(item).removeprefix("sha256:")[:20]
        changes.append(item)
    changes.sort(key=lambda item: (str(item["path"]), str(item["change_type"])))
    overall = _overall_classification(changes)
    payload = {
        "source_snapshot_sha256": old["snapshot_sha256"],
        "target_snapshot_sha256": new["snapshot_sha256"],
        "source_runtime_snapshot_hash": old["runtime_registry_snapshot_hash"],
        "target_runtime_snapshot_hash": new["runtime_registry_snapshot_hash"],
        "overall_classification": overall,
        "changes": changes,
    }
    digest = sha256_json(payload)
    return RegistryDiffReport(
        source_snapshot_id=str(old["snapshot_id"]),
        target_snapshot_id=str(new["snapshot_id"]),
        source_snapshot_sha256=str(old["snapshot_sha256"]),
        target_snapshot_sha256=str(new["snapshot_sha256"]),
        source_runtime_snapshot_hash=str(old["runtime_registry_snapshot_hash"]),
        target_runtime_snapshot_hash=str(new["runtime_registry_snapshot_hash"]),
        overall_classification=overall,
        changes=tuple(changes),
        diff_sha256=digest,
        diff_id="ainir.registry.diff." + digest.removeprefix("sha256:")[:20],
    )


def _diff_projection(diff: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_snapshot_sha256": diff.get("source_snapshot_sha256"),
        "target_snapshot_sha256": diff.get("target_snapshot_sha256"),
        "source_runtime_snapshot_hash": diff.get("source_runtime_snapshot_hash"),
        "target_runtime_snapshot_hash": diff.get("target_runtime_snapshot_hash"),
        "overall_classification": diff.get("overall_classification"),
        "changes": diff.get("changes"),
    }


def validate_registry_diff(
    diff: Mapping[str, Any],
    *,
    source_snapshot: str | Path | Mapping[str, Any] | None = None,
    target_snapshot: str | Path | Mapping[str, Any] | None = None,
) -> RegistryArtifactValidationReport:
    unknown_top = sorted(set(diff) - _DIFF_ALLOWED_FIELDS)
    checks: list[dict[str, Any]] = [
        _check("diff.unknown_fields", not unknown_top, [], unknown_top),
        _check("diff.kind", diff.get("kind") == REGISTRY_DIFF_KIND, REGISTRY_DIFF_KIND, diff.get("kind")),
        _check("diff.version", diff.get("version") == REGISTRY_DIFF_CONTRACT, REGISTRY_DIFF_CONTRACT, diff.get("version")),
    ]
    for field_name in (
        "source_snapshot_sha256",
        "target_snapshot_sha256",
        "source_runtime_snapshot_hash",
        "target_runtime_snapshot_hash",
    ):
        value = diff.get(field_name)
        checks.append(_check(
            f"diff.{field_name}",
            isinstance(value, str) and bool(_SHA256_RE.fullmatch(value)),
            "sha256:<64 lowercase hex>",
            value,
        ))
    changes = diff.get("changes")
    checks.append(_check("diff.changes", isinstance(changes, list), "array", type(changes).__name__))
    normalized_changes = changes if isinstance(changes, list) else []
    for index, change in enumerate(normalized_changes):
        prefix = f"diff.changes[{index}]"
        if not isinstance(change, Mapping):
            checks.append(_check(prefix, False, "object", type(change).__name__))
            continue
        classification = change.get("classification")
        change_type = change.get("change_type")
        unknown_change_fields = sorted(set(change) - _DIFF_CHANGE_ALLOWED_FIELDS)
        checks.append(_check(f"{prefix}.unknown_fields", not unknown_change_fields, [], unknown_change_fields))
        checks.append(_check(f"{prefix}.path", isinstance(change.get("path"), str) and bool(change.get("path")), "non-empty string", change.get("path")))
        checks.append(_check(f"{prefix}.change_type", change_type in _CHANGE_TYPES, sorted(_CHANGE_TYPES), change_type))
        checks.append(_check(f"{prefix}.classification", classification in _DIFF_CLASSIFICATIONS, sorted(_DIFF_CLASSIFICATIONS), classification))
        checks.append(_check(f"{prefix}.rationale", isinstance(change.get("rationale"), str) and bool(change.get("rationale")), "non-empty string", change.get("rationale")))
        payload = {key: value for key, value in change.items() if key != "change_id"}
        expected_change_id = "ainir.registry.change." + sha256_json(payload).removeprefix("sha256:")[:20]
        checks.append(_check(f"{prefix}.change_id", change.get("change_id") == expected_change_id, expected_change_id, change.get("change_id")))
    expected_overall = _overall_classification(
        [change for change in normalized_changes if isinstance(change, Mapping)]
    )
    checks.append(_check("diff.overall_classification", diff.get("overall_classification") == expected_overall, expected_overall, diff.get("overall_classification")))
    checks.append(_check("diff.changed", diff.get("changed") is bool(normalized_changes), bool(normalized_changes), diff.get("changed")))
    checks.append(_check("diff.change_count", diff.get("change_count") == len(normalized_changes), len(normalized_changes), diff.get("change_count")))
    counts: dict[str, int] = {}
    for change in normalized_changes:
        if isinstance(change, Mapping):
            key = str(change.get("classification"))
            counts[key] = counts.get(key, 0) + 1
    checks.append(_check("diff.classification_counts", diff.get("classification_counts") == dict(sorted(counts.items())), dict(sorted(counts.items())), diff.get("classification_counts")))
    requires = any(
        isinstance(change, Mapping) and change.get("classification") != "compatible"
        for change in normalized_changes
    )
    checks.append(_check("diff.requires_explicit_migration", diff.get("requires_explicit_migration") is requires, requires, diff.get("requires_explicit_migration")))
    expected_hash = sha256_json(_diff_projection(diff))
    checks.append(_check("diff.diff_sha256", diff.get("diff_sha256") == expected_hash, expected_hash, diff.get("diff_sha256")))
    expected_id = "ainir.registry.diff." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("diff.diff_id", diff.get("diff_id") == expected_id, expected_id, diff.get("diff_id")))
    checks.append(_check("diff.production_runtime_ready", diff.get("production_runtime_ready") is False, False, diff.get("production_runtime_ready")))
    if (source_snapshot is None) != (target_snapshot is None):
        checks.append(_check(
            "diff.snapshot_pair",
            False,
            "both source_snapshot and target_snapshot or neither",
            "one snapshot supplied",
        ))
    elif source_snapshot is not None and target_snapshot is not None:
        expected = diff_registry_snapshots(source_snapshot, target_snapshot).as_dict()
        for field_name in (
            "source_snapshot_id",
            "target_snapshot_id",
            "source_snapshot_sha256",
            "target_snapshot_sha256",
            "source_runtime_snapshot_hash",
            "target_runtime_snapshot_hash",
            "overall_classification",
            "changes",
            "diff_sha256",
            "diff_id",
        ):
            checks.append(_check(
                f"diff.snapshot_binding.{field_name}",
                diff.get(field_name) == expected.get(field_name),
                expected.get(field_name),
                diff.get(field_name),
            ))
    overall = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    return RegistryArtifactValidationReport(REGISTRY_DIFF_KIND, overall, tuple(checks))


def load_registry_diff(
    source: str | Path | Mapping[str, Any],
    *,
    source_snapshot: str | Path | Mapping[str, Any] | None = None,
    target_snapshot: str | Path | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(source, Mapping):
        diff = _json_copy(dict(source))
    else:
        artifact = read_json_object_artifact(source, artifact_name="registry_diff")
        if not artifact.ok:
            raise RegistryEvolutionError(
                f"cannot read registry diff: {artifact.reason}: {artifact.detail}"
            )
        diff = artifact.value
    validation = validate_registry_diff(
        diff,
        source_snapshot=source_snapshot,
        target_snapshot=target_snapshot,
    )
    if not validation.valid:
        failures = [check for check in validation.checks if check.get("status") != "passed"]
        raise RegistryEvolutionError(f"registry diff validation failed: {failures[:8]}")
    return diff


def write_registry_diff(path: str | Path, diff: Mapping[str, Any]) -> Path:
    validation = validate_registry_diff(diff)
    if not validation.valid:
        failures = [check for check in validation.checks if check.get("status") != "passed"]
        raise RegistryEvolutionError(f"registry diff validation failed: {failures[:8]}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(diff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def _migration_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": record.get("kind"),
        "version": record.get("version"),
        "source_snapshot_sha256": record.get("source_snapshot_sha256"),
        "target_snapshot_sha256": record.get("target_snapshot_sha256"),
        "source_runtime_snapshot_hash": record.get("source_runtime_snapshot_hash"),
        "target_runtime_snapshot_hash": record.get("target_runtime_snapshot_hash"),
        "registry_diff_sha256": record.get("registry_diff_sha256"),
        "overall_classification": record.get("overall_classification"),
        "acknowledged_change_ids": record.get("acknowledged_change_ids"),
        "authorization": record.get("authorization"),
        "cryptographic_signature_status": record.get("cryptographic_signature_status"),
        "production_runtime_ready": record.get("production_runtime_ready"),
    }


def create_registry_migration_record(
    source: str | Path | Mapping[str, Any],
    target: str | Path | Mapping[str, Any],
    *,
    authorized_by: str,
    reason: str,
    approve: bool = False,
    evidence_ref: str | None = None,
) -> dict[str, Any]:
    old = load_registry_snapshot(source)
    new = load_registry_snapshot(target)
    diff = diff_registry_snapshots(old, new)
    if not isinstance(authorized_by, str) or not _SAFE_TOKEN_RE.fullmatch(authorized_by):
        raise RegistryEvolutionError("authorized_by must be a non-empty portable actor id")
    if not isinstance(reason, str) or len(reason.strip()) < 8:
        raise RegistryEvolutionError("migration reason must contain at least 8 characters")
    if evidence_ref is not None and (
        not isinstance(evidence_ref, str) or not (1 <= len(evidence_ref) <= 512)
    ):
        raise RegistryEvolutionError(
            "evidence_ref must be null or a non-empty string up to 512 characters"
        )
    authorization = {
        "status": "approved" if approve else "review_required",
        "actor_id": authorized_by,
        "mechanism": "explicit_local_review",
        "reason": reason.strip(),
        "evidence_ref": evidence_ref,
    }
    record: dict[str, Any] = {
        "kind": REGISTRY_MIGRATION_RECORD_KIND,
        "version": REGISTRY_MIGRATION_RECORD_CONTRACT,
        "source_snapshot_sha256": old["snapshot_sha256"],
        "target_snapshot_sha256": new["snapshot_sha256"],
        "source_runtime_snapshot_hash": old["runtime_registry_snapshot_hash"],
        "target_runtime_snapshot_hash": new["runtime_registry_snapshot_hash"],
        "registry_diff_sha256": diff.diff_sha256,
        "overall_classification": diff.overall_classification,
        "acknowledged_change_ids": sorted(
            str(change["change_id"])
            for change in diff.changes
            if change.get("classification") != "compatible"
        ),
        "authorization": authorization,
        "cryptographic_signature_status": "not_implemented",
        "production_runtime_ready": False,
    }
    record_hash = sha256_json(_migration_projection(record))
    record["record_sha256"] = record_hash
    record["migration_id"] = "ainir.registry.migration." + record_hash.removeprefix("sha256:")[:20]
    return record


def validate_registry_migration_record(
    record: Mapping[str, Any],
    source: str | Path | Mapping[str, Any],
    target: str | Path | Mapping[str, Any],
    *,
    require_approved: bool = False,
) -> RegistryArtifactValidationReport:
    old = load_registry_snapshot(source)
    new = load_registry_snapshot(target)
    diff = diff_registry_snapshots(old, new)
    unknown_top = sorted(set(record) - _MIGRATION_ALLOWED_FIELDS)
    checks = [
        _check("migration.unknown_fields", not unknown_top, [], unknown_top),
        _check("migration.kind", record.get("kind") == REGISTRY_MIGRATION_RECORD_KIND, REGISTRY_MIGRATION_RECORD_KIND, record.get("kind")),
        _check("migration.version", record.get("version") == REGISTRY_MIGRATION_RECORD_CONTRACT, REGISTRY_MIGRATION_RECORD_CONTRACT, record.get("version")),
        _check("migration.source_snapshot_sha256", record.get("source_snapshot_sha256") == old["snapshot_sha256"], old["snapshot_sha256"], record.get("source_snapshot_sha256")),
        _check("migration.target_snapshot_sha256", record.get("target_snapshot_sha256") == new["snapshot_sha256"], new["snapshot_sha256"], record.get("target_snapshot_sha256")),
        _check("migration.source_runtime_snapshot_hash", record.get("source_runtime_snapshot_hash") == old["runtime_registry_snapshot_hash"], old["runtime_registry_snapshot_hash"], record.get("source_runtime_snapshot_hash")),
        _check("migration.target_runtime_snapshot_hash", record.get("target_runtime_snapshot_hash") == new["runtime_registry_snapshot_hash"], new["runtime_registry_snapshot_hash"], record.get("target_runtime_snapshot_hash")),
        _check("migration.registry_diff_sha256", record.get("registry_diff_sha256") == diff.diff_sha256, diff.diff_sha256, record.get("registry_diff_sha256")),
        _check("migration.overall_classification", record.get("overall_classification") == diff.overall_classification, diff.overall_classification, record.get("overall_classification")),
    ]
    expected_changes = sorted(
        str(change["change_id"])
        for change in diff.changes
        if change.get("classification") != "compatible"
    )
    actual_changes = record.get("acknowledged_change_ids")
    checks.append(_check("migration.acknowledged_change_ids", actual_changes == expected_changes, expected_changes, actual_changes))
    authorization = record.get("authorization")
    unknown_authorization = sorted(set(authorization) - _MIGRATION_AUTH_ALLOWED_FIELDS) if isinstance(authorization, Mapping) else []
    checks.append(_check("migration.authorization.unknown_fields", not unknown_authorization, [], unknown_authorization))
    auth_status = authorization.get("status") if isinstance(authorization, Mapping) else None
    actor = authorization.get("actor_id") if isinstance(authorization, Mapping) else None
    reason = authorization.get("reason") if isinstance(authorization, Mapping) else None
    mechanism = authorization.get("mechanism") if isinstance(authorization, Mapping) else None
    evidence_ref = authorization.get("evidence_ref") if isinstance(authorization, Mapping) else None
    checks.append(_check("migration.authorization.actor_id", isinstance(actor, str) and bool(_SAFE_TOKEN_RE.fullmatch(actor)), "portable actor id", actor))
    checks.append(_check("migration.authorization.reason", isinstance(reason, str) and len(reason.strip()) >= 8, "at least 8 characters", reason))
    checks.append(_check("migration.authorization.mechanism", mechanism == "explicit_local_review", "explicit_local_review", mechanism))
    checks.append(_check(
        "migration.authorization.evidence_ref",
        evidence_ref is None or (isinstance(evidence_ref, str) and 1 <= len(evidence_ref) <= 512),
        "null or non-empty string up to 512 characters",
        evidence_ref,
    ))
    allowed_statuses = {"approved"} if require_approved else {"approved", "review_required"}
    checks.append(_check("migration.authorization.status", auth_status in allowed_statuses, sorted(allowed_statuses), auth_status))
    checks.append(_check("migration.cryptographic_signature_status", record.get("cryptographic_signature_status") == "not_implemented", "not_implemented", record.get("cryptographic_signature_status")))
    checks.append(_check("migration.production_runtime_ready", record.get("production_runtime_ready") is False, False, record.get("production_runtime_ready")))
    expected_hash = sha256_json(_migration_projection(record))
    checks.append(_check("migration.record_sha256", record.get("record_sha256") == expected_hash, expected_hash, record.get("record_sha256")))
    expected_id = "ainir.registry.migration." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("migration.migration_id", record.get("migration_id") == expected_id, expected_id, record.get("migration_id")))
    overall = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    return RegistryArtifactValidationReport(REGISTRY_MIGRATION_RECORD_KIND, overall, tuple(checks))


def load_registry_migration_record(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return _json_copy(dict(source))
    artifact = read_json_object_artifact(source, artifact_name="registry_migration")
    if not artifact.ok:
        raise RegistryEvolutionError(
            f"cannot read registry migration record: {artifact.reason}: {artifact.detail}"
        )
    return artifact.value


def write_registry_migration_record(path: str | Path, record: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


__all__ = [
    "RegistryArtifactValidationReport",
    "RegistryDiffReport",
    "RegistryEvolutionError",
    "build_registry_snapshot",
    "capture_registry_snapshot",
    "create_registry_migration_record",
    "diff_registry_snapshots",
    "load_registry_diff",
    "load_registry_migration_record",
    "load_registry_snapshot",
    "registry_bundle_from_snapshot",
    "validate_registry_diff",
    "validate_registry_migration_record",
    "validate_registry_snapshot",
    "write_registry_diff",
    "write_registry_migration_record",
    "write_registry_snapshot",
]
