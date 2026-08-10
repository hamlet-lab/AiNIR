# Host-owned MCP reference adapter

`ainir.mcp_host_adapter.HostOwnedMCPReferenceAdapter` is a deliberately narrow adapter around the P6 MCP tool-call assessment APIs.

It exposes only:

- normalization of a descriptor, `tools/call` request, and transport observations into a deterministic envelope;
- assessment of that envelope against a host-owned context.

It intentionally exposes no `execute`, `send`, `connect`, authorization, discovery, retry, or transport method. This separation prevents AiNIR from becoming the system that both judges and performs an action.

Use the bundled profile with a context manager so package resources remain materialized for the lifetime of the adapter:

```python
from ainir.mcp_host_adapter import bundled_mcp_reference_adapter

with bundled_mcp_reference_adapter() as adapter:
    envelope = adapter.normalize(descriptor, request, transport_binding)
    assessment = adapter.assess(envelope, host_context)
```

A `passed` assessment means only that the exact reviewed profile and host bindings did not produce a refusal. The host remains responsible for final authorization, user control, time-of-use resource identity, transaction execution, rollback, logging, and all actual side effects.

The adapter never presents `execute_outside_ainir_core` for `review_required`, `refused`, or `invalid` outcomes. Those outcomes remain non-handoff decisions; final destructive confirmation must be followed by reassessment.
