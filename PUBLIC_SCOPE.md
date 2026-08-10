# Public scope

AiNIR is a bounded, registry-backed semantic trust layer for inspecting AI-generated workflow claims before lowering or host handoff.

## In scope

- strict Draft AST parsing and normalization;
- a closed-world public workflow registry;
- safety, operation, effect, capability, evidence, context, and transaction checks;
- fail-closed Trust Gate decisions;
- TrustReceipt issuance, persistence, deterministic exact replay, current-registry evaluation, and explicitly reviewed migrated replay;
- negative conformance cases and golden traces;
- lowering eligibility and a non-production host-enforcement skeleton;
- optional, consumer-neutral verified-intent export contracts;
- packaged public schemas and registries exposed through a deterministic resource API;
- content-bound RegistrySnapshot, semantic RegistryDiff, and explicit local RegistryMigrationRecord artifacts;
- deterministic offline EvidenceRequest/Record/Policy/Bundle/Resolution/ValidationReport contracts;
- fixture, root-confined file, and local signed-bundle adapters whose candidates remain outside the Trust Gate Evidence Ledger;
- a bounded MCP `tools/call` profile, deterministic envelope/host-context/assessment artifacts, and a non-executing host-owned reference adapter;
- public profile, registry, receipt, and conformance hardening work.

## Out of scope

- executing tools, files, payments, account changes, or network actions;
- production host runtime, enterprise evidence backend, public-key evidence identity, or production registry governance/signing service;
- arbitrary AI-generated code verification;
- universal effect or capability inference;
- AIVL, LEP, or other downstream implementations;
- live credential handling and networked provider integrations in the core;
- MCP transport, server/client runtime, OAuth, Tasks, elicitation, sampling, multi-round execution, or tool execution in AiNIR core;
- private research archives, full mutation corpora, and enterprise policy packs.

Unknown workflows and unsupported semantics remain refused until an explicit, reviewed profile and conformance pack exist.

## Bounded MCP tool-call preflight

The public repository includes a consumer-neutral reference profile, deterministic envelope/context/assessment contracts, 26 offline conformance cases, and a host-owned non-executing adapter. AiNIR does not implement an MCP transport or tool executor, does not accept tool descriptions or annotations as evidence, and does not promote an MCP assessment into the Trust Gate or Evidence Ledger.

## P7 public additions

P7 publicly includes:

- a fixed-semantics read-only external MCP profile scaffold;
- file-bound external MCP conformance cases with profile-root confinement;
- a non-executing adapter from completed OpenAI Responses function-call JSON to the P6 MCP envelope and assessment;
- content-bound OpenAI function-call binding and preflight artifacts.

P7 does not include an OpenAI client, API call, streaming assembler, tool-output submission, hosted-tool support, credentials, transport ownership, or execution.
