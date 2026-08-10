# Protected invariants

These invariants are release blockers. A passing test suite is not sufficient if a change violates one of them.

| ID | Invariant |
|---|---|
| `AINIR-I001` | Model output is a claim, not evidence or fact. |
| `AINIR-I002` | Verified claims require non-vacuous, ledger-bound evidence from an allowed issuer. |
| `AINIR-I003` | Self-attestation cannot promote a claim to verified status. |
| `AINIR-I004` | Unknown workflows and unknown safety-critical semantics fail closed. |
| `AINIR-I005` | Declared effects and capabilities cannot exceed registered operation contracts. |
| `AINIR-I006` | Trusted execution context comes from the host boundary, not `draft.environment`. |
| `AINIR-I007` | Transaction-required workflows must preserve explicit, ordered transaction boundaries. |
| `AINIR-I008` | Refused, invalid, stale, ambiguous, or hole-containing drafts cannot lower or hand off. |
| `AINIR-I009` | Consumer profiles may narrow or annotate a decision but cannot override the core Trust Gate. |
| `AINIR-I010` | TrustReceipt replay is deterministic for the bound draft, context, verifier report, and registry snapshot. |
| `AINIR-I011` | Registry evolution is explicit; historical decision meaning is never silently rewritten. |
| `AINIR-I012` | AiNIR core does not execute downstream actions or manufacture evidence for its own decision. |
| `AINIR-I013` | A gate is never weakened solely to make a fixture, demo, or release check pass. |
| `AINIR-I014` | Public changes do not leak private archive or enterprise-only material. |
| `AINIR-I015` | EvidenceProvider output remains untrusted until AiNIR independently recomputes bundle/signature integrity, binds the unique bundled record, checks policy-bounded revocation freshness, and completes semantic validation; a validated P5 candidate is never automatically promoted into the Trust Gate Evidence Ledger. |
| `AINIR-I016` | MCP tool descriptions, annotations, model/client metadata, and provider claims are not evidence; exact host-owned authorization audience, schema, capability, resource, consent, transaction, and rollback bindings are required, and AiNIR never executes the tool. |

Every semantic pull request must state which invariants it touches and provide negative or tamper-oriented coverage for them.

## I016 — MCP preflight never becomes execution authority

AiNIR may normalize and assess a reviewed MCP `tools/call` proposal, but it must not open a transport, hold or forward credentials, invoke the tool, trust model-generated host context, treat descriptions/annotations as evidence, override the core Trust Gate, or promote the result into the Evidence Ledger. Unknown tools and unsupported MCP task/multi-round surfaces fail closed.

## I017 — Host-framework adapters are translation and preflight only

| ID | Invariant |
|---|---|
| `AINIR-I017` | A host-framework adapter may bind finalized host-observed artifacts to reviewed AiNIR contracts, but it cannot call the provider API, import execution authority, submit tool output, handle credentials, infer semantics from descriptions, replace host authorization, or execute the tool. Nested binding, envelope, context, and assessment identities must remain cross-consistent. |
