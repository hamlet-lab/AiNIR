"""Read-only access to bundled external consumer profile contracts.

This module preserves the RC2 consumer-profile compatibility surface. Workflow
Profile Manifest authoring is implemented separately in ``profile_manifest``
and ``profile_runtime`` so consumer handoff contracts cannot modify or bypass
AiNIR's Trust Gate.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .core import load_yaml_no_duplicate_keys
from .resources import read_registry_text


class ConsumerProfileRegistryError(ValueError):
    """Raised when the packaged profile registry is malformed."""


class UnknownConsumerProfileError(KeyError):
    """Raised when a requested profile is not registered."""


def consumer_profile_registry() -> dict[str, Any]:
    data = load_yaml_no_duplicate_keys(
        read_registry_text("external_consumer_profiles.yaml")
    ) or {}
    if not isinstance(data, Mapping):
        raise ConsumerProfileRegistryError("external consumer profile registry must be an object")
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        raise ConsumerProfileRegistryError("external consumer profile registry profiles must be an array")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(profiles):
        if not isinstance(item, Mapping):
            raise ConsumerProfileRegistryError(f"profile at index {index} must be an object")
        profile_id = item.get("id")
        if not isinstance(profile_id, str) or not profile_id:
            raise ConsumerProfileRegistryError(f"profile at index {index} has no valid id")
        if profile_id in seen:
            raise ConsumerProfileRegistryError(f"duplicate consumer profile id {profile_id!r}")
        seen.add(profile_id)
        normalized.append(deepcopy(dict(item)))
    result = deepcopy(dict(data))
    result["profiles"] = normalized
    return result


def list_consumer_profiles() -> tuple[dict[str, Any], ...]:
    registry = consumer_profile_registry()
    profiles = registry["profiles"]
    return tuple(sorted((deepcopy(item) for item in profiles), key=lambda item: str(item["id"])))


def get_consumer_profile(profile_id: str) -> dict[str, Any]:
    for profile in list_consumer_profiles():
        if profile.get("id") == profile_id:
            return deepcopy(profile)
    raise UnknownConsumerProfileError(f"unknown AiNIR consumer profile: {profile_id!r}")


__all__ = [
    "ConsumerProfileRegistryError",
    "UnknownConsumerProfileError",
    "consumer_profile_registry",
    "get_consumer_profile",
    "list_consumer_profiles",
]
