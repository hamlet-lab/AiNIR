# P7 — OpenAI host adapter and external MCP authoring

P7 extends the P6 non-executing preflight surface in two directions:

1. a fixed-semantics read-only MCP profile scaffold with file-bound external conformance fixtures;
2. a host-owned adapter that binds a completed OpenAI Responses function call to the reviewed P6 MCP profile and assessment.

Protected boundaries:

- no OpenAI SDK or API call;
- no MCP transport;
- no tool-output submission;
- no execution;
- no credentials;
- no semantics inferred from descriptions;
- no external scenario shorthand;
- no Trust Gate override or Evidence Ledger promotion;
- P6 registry hash remains unchanged.

The implementation adds two public artifact contracts, two packaged schemas, a four-case generated profile pack, deterministic readiness checks, CLI commands, and installed-wheel verification.

## Final red-team hardening

- all host-supplied OpenAI artifacts are bounded by the public canonical JSON byte and depth limits before normalization;
- external conformance cases no longer convert arbitrary `TypeError` or `ValueError` programming defects into an expected `invalid` result;
- host-observed response identifiers remain audit bindings, not cryptographic source authentication; AiNIR performs no OpenAI API verification.
