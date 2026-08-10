from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .core import load_yaml_no_duplicate_keys
from .registry_context import active_registry_bundle


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_json(data: Any) -> str:
    return "sha256:" + sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _duplicate_record_ids(data: Any) -> list[str]:
    """Return duplicate record ids in registry-like documents.

    This intentionally checks only explicit list-of-records sections so it does
    not impose schema on every YAML registry, while still catching evidence
    ledger/corpus id shadowing that would make warrant bindings ambiguous.
    """
    duplicates: list[str] = []
    if isinstance(data, Mapping):
        for key in ("records", "cases", "fixtures", "workflows", "operations"):
            value = data.get(key)
            if isinstance(value, list):
                seen: set[str] = set()
                for item in value:
                    if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                        rid = str(item.get("id"))
                        if rid in seen and rid not in duplicates:
                            duplicates.append(rid)
                        seen.add(rid)
    return sorted(duplicates)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _package_registry_dir() -> Path:
    return Path(__file__).resolve().parent / "registries"


def _read_yaml_path(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        return {"source_path": str(path), "label": label, "missing": True, "raw_sha256": None, "canonical_sha256": _sha256_json({})}
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        data = load_yaml_no_duplicate_keys(text) or {}
        result = {"source_path": str(path), "label": label, "raw_sha256": _sha256_bytes(raw), "canonical_sha256": _sha256_json(data)}
        duplicate_ids = _duplicate_record_ids(data)
        if duplicate_ids:
            result["duplicate_record_ids"] = duplicate_ids
        return result
    except Exception as exc:
        return {"source_path": str(path), "label": label, "raw_sha256": _sha256_bytes(raw), "canonical_sha256": _sha256_json({}), "load_error": type(exc).__name__, "load_error_detail": str(exc)}


def _read_effective_yaml(label: str, primary: Path, secondary: Path | None = None) -> dict[str, Any]:
    """Read the effective registry and record duplicate-copy consistency.

    Trust decisions must not silently fall back from a corrupt authoritative
    packaged registry to a clean root copy, and release readiness must notice
    when the root registry visible to humans drifts from the packaged registry
    used by installed code. source_path remains diagnostic only.
    """
    effective = _read_yaml_path(primary, label) if primary.exists() else (_read_yaml_path(secondary, label) if secondary is not None else _read_yaml_path(primary, label))
    if secondary is not None and primary.exists() and secondary.exists():
        first = _read_yaml_path(primary, label + ":primary")
        second = _read_yaml_path(secondary, label + ":secondary")
        effective["copy_consistency"] = {
            "primary_path": str(primary),
            "secondary_path": str(secondary),
            "primary_raw_sha256": first.get("raw_sha256"),
            "secondary_raw_sha256": second.get("raw_sha256"),
            "primary_canonical_sha256": first.get("canonical_sha256"),
            "secondary_canonical_sha256": second.get("canonical_sha256"),
            "primary_load_error": first.get("load_error"),
            "secondary_load_error": second.get("load_error"),
            "consistent": first.get("raw_sha256") == second.get("raw_sha256") and first.get("canonical_sha256") == second.get("canonical_sha256") and not first.get("load_error") and not second.get("load_error"),
        }
        if not effective["copy_consistency"]["consistent"]:
            effective["copy_drift"] = True
    return effective


def stable_registry_snapshot_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    items = snapshot.get("items") if isinstance(snapshot, Mapping) else {}
    stable_items: dict[str, Any] = {}
    if isinstance(items, Mapping):
        for name, item in sorted(items.items(), key=lambda pair: str(pair[0])):
            if isinstance(item, Mapping):
                stable_items[str(name)] = {
                    key: item.get(key)
                    for key in ("label", "raw_sha256", "canonical_sha256", "missing", "load_error", "copy_drift", "duplicate_record_ids")
                    if key in item
                }
            else:
                stable_items[str(name)] = item
    return {
        "kind": snapshot.get("kind") if isinstance(snapshot, Mapping) else None,
        "version": snapshot.get("version") if isinstance(snapshot, Mapping) else None,
        "items": stable_items,
    }


def registry_snapshot() -> dict[str, Any]:
    bundle = active_registry_bundle()
    if bundle is not None:
        return json.loads(json.dumps(bundle.snapshot, sort_keys=True, ensure_ascii=False))

    root = _repo_root()
    pkg = _package_registry_dir()
    items = {
        "safety_registry": _read_effective_yaml("safety_registry", pkg / "safety_registry.yaml", root / "registries" / "safety_registry.yaml"),
        "operation_spec_registry": _read_effective_yaml("operation_spec_registry", pkg / "operation_spec_registry.yaml", root / "registries" / "operation_spec_registry.yaml"),
        "evidence_ledger": _read_effective_yaml("evidence_ledger", root / "registries" / "evidence_ledger.yaml", pkg / "evidence_ledger.yaml"),
        "external_consumer_profiles": _read_effective_yaml("external_consumer_profiles", pkg / "external_consumer_profiles.yaml", root / "registries" / "external_consumer_profiles.yaml"),
    }
    snapshot = {
        "kind": "AiNIRRegistrySnapshot",
        "version": "public_defensive_integrity_registry_snapshot_v3_validity_gated",
        "items": items,
    }
    snapshot["combined_sha256"] = _sha256_json(stable_registry_snapshot_projection(snapshot))
    snapshot["valid"] = not registry_snapshot_failures(snapshot)
    return snapshot


def registry_snapshot_failures(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    required = {"safety_registry", "operation_spec_registry", "evidence_ledger", "external_consumer_profiles"}
    items = snapshot.get("items") if isinstance(snapshot, Mapping) else {}
    if not isinstance(items, Mapping):
        return [{"name": "<snapshot>", "reason": "snapshot_items_not_object"}]
    for name in sorted(required):
        item = items.get(name)
        if not isinstance(item, Mapping):
            failures.append({"name": name, "reason": "missing_snapshot_item"})
            continue
        if item.get("missing"):
            failures.append({"name": name, "reason": "registry_missing", "source_path": item.get("source_path")})
        if item.get("load_error"):
            failures.append({"name": name, "reason": "registry_load_error", "load_error": item.get("load_error"), "detail": item.get("load_error_detail"), "source_path": item.get("source_path")})
        if item.get("copy_drift"):
            failures.append({"name": name, "reason": "registry_copy_drift", "copy_consistency": item.get("copy_consistency")})
        if item.get("duplicate_record_ids"):
            failures.append({"name": name, "reason": "registry_duplicate_record_id", "duplicate_record_ids": item.get("duplicate_record_ids"), "source_path": item.get("source_path")})
    return failures
