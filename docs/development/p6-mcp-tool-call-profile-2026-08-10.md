# P6 — MCP tool-call profile and host-owned adapter

P6 introduces six public MCP preflight artifacts, a bundled three-tool workspace profile, a non-executing host adapter, 26-case conformance pack, packaged schemas, CLI commands, and release/distribution checks.

Security decisions:

- descriptor text and annotations are not evidence;
- exact descriptor/schema/effect/capability bindings are required;
- unknown tools fail closed;
- credentials in arguments or metadata are refused;
- authorization audience, consent, resource identity, transaction, and rollback are host-owned bindings;
- destructive calls stop at `review_required`;
- Tasks and multi-round inputs are not claimed;
- AiNIR never contacts or executes an MCP tool;
- P5 registry and Trust Gate semantics remain unchanged.

Validation targets:

```bash
python -m pytest -q -p no:cacheprovider tests/test_p6_mcp_tool_call_profile.py
python scripts/check_mcp_tool_call_profile.py
python -m ainir mcp conformance
python scripts/run_phase30_v1_rc_candidate_check.py --mode quick-integrity
python scripts/check_distribution_contracts.py
```
