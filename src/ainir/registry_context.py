"""Isolated registry bundles for profile conformance evaluation.

The default AiNIR runtime continues to use the packaged public registries.
Profile authoring may activate an in-memory, additive bundle inside a context
manager.  The override is context-local, never process-global, and does not
permit a profile to mutate the packaged registries.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping


@dataclass(frozen=True)
class ActiveRegistryBundle:
    """Registry objects and snapshot used by one isolated profile run."""

    profile_id: str
    safety_registry: Any
    operation_registry: Any
    evidence_ledger: Any
    snapshot: Mapping[str, Any]
    manifest_sha256: str
    production_runtime_ready: bool = False


_ACTIVE_REGISTRY_BUNDLE: ContextVar[ActiveRegistryBundle | None] = ContextVar(
    "ainir_active_registry_bundle",
    default=None,
)


def active_registry_bundle() -> ActiveRegistryBundle | None:
    """Return the context-local profile registry bundle, when one is active."""

    return _ACTIVE_REGISTRY_BUNDLE.get()


@contextmanager
def use_registry_bundle(bundle: ActiveRegistryBundle) -> Iterator[ActiveRegistryBundle]:
    """Activate one registry bundle for the current context only."""

    token: Token[ActiveRegistryBundle | None] = _ACTIVE_REGISTRY_BUNDLE.set(bundle)
    try:
        yield bundle
    finally:
        _ACTIVE_REGISTRY_BUNDLE.reset(token)


class DynamicRegistryProxy:
    """Delegate attribute access to the registry selected for this context.

    Several pre-v1 modules historically captured a registry object at import
    time.  Replacing those captures with this proxy preserves their public
    behavior while allowing the standalone profile runner to use an isolated
    additive registry bundle.
    """

    __slots__ = ("_getter",)

    def __init__(self, getter: Callable[[], Any]):
        object.__setattr__(self, "_getter", getter)

    def _target(self) -> Any:
        return object.__getattribute__(self, "_getter")()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target(), name)

    def __repr__(self) -> str:
        return f"DynamicRegistryProxy({self._target()!r})"


__all__ = [
    "ActiveRegistryBundle",
    "DynamicRegistryProxy",
    "active_registry_bundle",
    "use_registry_bundle",
]
