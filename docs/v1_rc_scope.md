# v1.0 RC Scope Freeze

This document defines what the AiNIR v1.0 RC candidate includes and excludes.

## Included in the public RC candidate

- Strict Draft AST parsing
- Safety Registry resolution
- Evidence Ledger binding
- Operation Spec Registry binding
- Effect and capability contract checks
- Trusted Execution Context separation
- Transaction binding
- Trust Gate decision surface
- TrustReceipt issue/replay
- Lowering eligibility gate
- Host enforcement TypeScript skeleton for the safe outbox example
- Negative conformance corpus
- Golden trace replay
- VerifiedIntentPacket optional export surface
- bounded external consumer profile slot
- bounded workflow registry and extension roadmap
- fixture-backed Evidence Ledger plus deterministic offline fixture/file/signed-bundle provider contracts
- exact/current/migrated TrustReceipt replay semantics and explicit registry-evolution artifacts
- bounded MCP `tools/call` profile, deterministic preflight artifacts, host-owned adapter, 26-case bundled conformance pack, and fixed-semantics external profile scaffold;
- completed OpenAI Responses function-call binding to P6 preflight, without API calls, tool-output submission, or execution
- public/private boundary documentation
- launch-readiness and private-trial simulation checks

## Excluded from the public RC candidate

- production runtime execution
- production policy/registry governance
- real email/payment/deletion actions, network evidence providers, public-key issuer identity, and automatic provider-to-ledger promotion
- enterprise approval workflows
- full private research archive
- detailed private external context profiles
- hard integration with downstream compilers/runtimes
- MCP transports, OAuth, Tasks, elicitation, sampling, multi-round execution, or tool execution
- v1.0 final stability claim

## RC acceptance rule

A public candidate may be called an RC candidate if it passes:

- unit tests;
- public demo;
- negative conformance;
- golden traces;
- TrustReceipt replay checks;
- VerifiedIntentPacket strict contract checks;
- offline EvidenceProvider readiness and no-auto-promotion checks;
- MCP tool-call profile readiness, no-execution checks, and deterministic conformance;
- private-trial simulation;
- release-candidate review;
- package cleanliness checks.


## Scope warning

The RC candidate does not claim to verify arbitrary workflows. It demonstrates a conservative trust boundary over a bounded workflow registry. Future workflows require explicit registry authoring and conformance fixtures.
