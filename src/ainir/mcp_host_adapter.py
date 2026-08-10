"""Host-owned reference adapter for bounded MCP ``tools/call`` preflight.

The adapter normalizes host-observed artifacts and delegates to AiNIR's
consumer-neutral MCP assessment.  It deliberately exposes no transport,
credential, retry, server-discovery, or execution method.  A passing assessment
only permits a host handoff under the reviewed profile; the host remains the
sole executor and must revalidate authorization and resource identity at
execution time.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    HostOwnedMCPToolCallAdapter,
    materialized_mcp_profile_source,
)

# A descriptive public alias keeps the implementation in one place while
# making the host-owned boundary obvious to integrators.
HostOwnedMCPReferenceAdapter = HostOwnedMCPToolCallAdapter


@contextmanager
def bundled_mcp_reference_adapter() -> Iterator[HostOwnedMCPReferenceAdapter]:
    """Yield the bundled, non-executing MCP reference adapter.

    Bundled package resources may live inside a wheel/zip, so their temporary
    materialization must remain alive for the whole adapter use.  This context
    manager owns that lifetime and removes the temporary copy on exit.
    """

    with materialized_mcp_profile_source(BUILTIN_MCP_PROFILE_ID) as profile:
        yield HostOwnedMCPReferenceAdapter(profile)


__all__ = [
    "HostOwnedMCPReferenceAdapter",
    "bundled_mcp_reference_adapter",
]
