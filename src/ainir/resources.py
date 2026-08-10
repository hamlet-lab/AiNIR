"""Supported access to AiNIR's packaged public schemas and registries.

Callers should use this module instead of deriving paths from ``__file__``.
The API works in editable installs, wheels, zip-compatible importers, and
ordinary source checkouts as long as the package data is present.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import resources as importlib_resources
import json
from typing import Literal

ResourceKind = Literal["schema", "registry"]

PUBLIC_SCHEMA_NAMES: tuple[str, ...] = (
    "conformance_pack.schema.json",
    "conformance_report.schema.json",
    "draft_packet.schema.yaml",
    "evidence_bundle.schema.json",
    "evidence_provider_policy.schema.json",
    "evidence_record.schema.json",
    "evidence_request.schema.json",
    "evidence_resolution.schema.json",
    "evidence_validation_report.schema.json",
    "mcp_host_context.schema.json",
    "mcp_tool_call_assessment.schema.json",
    "mcp_tool_call_conformance_pack.schema.json",
    "mcp_tool_call_conformance_report.schema.json",
    "mcp_tool_call_envelope.schema.json",
    "mcp_tool_call_profile.schema.json",
    "openai_function_call_binding.schema.json",
    "openai_function_tool_preflight.schema.json",
    "profile_manifest.schema.json",
    "registry_diff.schema.json",
    "registry_migration_record.schema.json",
    "registry_snapshot.schema.json",
    "trust_gate_decision.schema.json",
    "trust_receipt.schema.json",
    "trust_receipt_replay_report.schema.json",
    "verified_intent_packet.schema.json",
)

PUBLIC_REGISTRY_NAMES: tuple[str, ...] = (
    "evidence_ledger.yaml",
    "external_consumer_profiles.yaml",
    "operation_spec_registry.yaml",
    "safety_registry.yaml",
)

_RESOURCE_PACKAGES: dict[ResourceKind, str] = {
    "schema": "ainir.schemas",
    "registry": "ainir.registries",
}

_ALLOWED_NAMES: dict[ResourceKind, tuple[str, ...]] = {
    "schema": PUBLIC_SCHEMA_NAMES,
    "registry": PUBLIC_REGISTRY_NAMES,
}


class UnknownPublicResourceError(KeyError):
    """Raised when a caller asks for an undeclared public resource."""


@dataclass(frozen=True)
class PublicResourceInfo:
    kind: ResourceKind
    name: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _validate(kind: ResourceKind, name: str) -> None:
    if kind not in _RESOURCE_PACKAGES:
        raise ValueError(f"unsupported resource kind: {kind!r}")
    if not isinstance(name, str) or name not in _ALLOWED_NAMES[kind]:
        raise UnknownPublicResourceError(f"unknown AiNIR {kind}: {name!r}")


def public_resource_names(kind: ResourceKind) -> tuple[str, ...]:
    """Return the stable allowlisted filenames for one public resource kind."""

    if kind not in _ALLOWED_NAMES:
        raise ValueError(f"unsupported resource kind: {kind!r}")
    return _ALLOWED_NAMES[kind]


def read_public_resource_bytes(kind: ResourceKind, name: str) -> bytes:
    """Read one allowlisted packaged resource as bytes."""

    _validate(kind, name)
    resource = importlib_resources.files(_RESOURCE_PACKAGES[kind]).joinpath(name)
    return resource.read_bytes()


def read_public_resource_text(
    kind: ResourceKind,
    name: str,
    *,
    encoding: str = "utf-8",
) -> str:
    """Read one allowlisted packaged resource as text."""

    return read_public_resource_bytes(kind, name).decode(encoding)


def public_resource_info(kind: ResourceKind, name: str) -> PublicResourceInfo:
    """Return deterministic size and SHA-256 metadata for one resource."""

    data = read_public_resource_bytes(kind, name)
    return PublicResourceInfo(
        kind=kind,
        name=name,
        size=len(data),
        sha256="sha256:" + sha256(data).hexdigest(),
    )


def public_resource_manifest() -> dict[str, object]:
    """Return a deterministic manifest for all packaged public resources."""

    resource_groups: dict[str, dict[str, dict[str, str | int]]] = {}
    for plural, kind in (("schemas", "schema"), ("registries", "registry")):
        resource_groups[plural] = {
            name: public_resource_info(kind, name).as_dict()
            for name in public_resource_names(kind)
        }
    stable_payload = {
        "kind": "AiNIRPublicResourceManifest",
        "version": "1",
        **resource_groups,
    }
    canonical = json.dumps(
        stable_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **stable_payload,
        "combined_sha256": "sha256:" + sha256(canonical).hexdigest(),
    }


def read_schema_bytes(name: str) -> bytes:
    return read_public_resource_bytes("schema", name)


def read_schema_text(name: str, *, encoding: str = "utf-8") -> str:
    return read_public_resource_text("schema", name, encoding=encoding)


def schema_info(name: str) -> PublicResourceInfo:
    return public_resource_info("schema", name)


def read_registry_bytes(name: str) -> bytes:
    return read_public_resource_bytes("registry", name)


def read_registry_text(name: str, *, encoding: str = "utf-8") -> str:
    return read_public_resource_text("registry", name, encoding=encoding)


def registry_info(name: str) -> PublicResourceInfo:
    return public_resource_info("registry", name)


__all__ = [
    "PUBLIC_REGISTRY_NAMES",
    "PUBLIC_SCHEMA_NAMES",
    "PublicResourceInfo",
    "ResourceKind",
    "UnknownPublicResourceError",
    "public_resource_info",
    "public_resource_manifest",
    "public_resource_names",
    "read_public_resource_bytes",
    "read_public_resource_text",
    "read_registry_bytes",
    "read_registry_text",
    "read_schema_bytes",
    "read_schema_text",
    "registry_info",
    "schema_info",
]
