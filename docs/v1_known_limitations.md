# v1.0 RC Known Limitations

AiNIR v1.0 RC candidate is intentionally bounded.

## Not production runtime

AiNIR does not execute real external effects. It emits host-enforcement skeletons for review and demonstration.

## No enterprise registry governance yet

The public demo includes bounded registries. It does not include the governance process for adding, signing, retiring, or delegating registry entries across an organization.

## No production evidence backend

The public Evidence Ledger remains bundled and deterministic. P5 implements offline fixture, root-confined file, and local HMAC-signed bundle adapters, but it does not provide a live network backend, enterprise issuer directory, public-key attestation, key revocation service, or automatic ledger promotion.

A successfully validated provider record is only a `validated_candidate`; `trust_gate_promotion_allowed` remains false.

## No downstream integration

`VerifiedIntentPacket` is an optional export artifact. The public demo does not integrate with downstream compilers, runtimes, renderers, or workflow engines.

## Conservative workflow coverage

The public examples focus on a small set of safety-critical workflows. New workflows require explicit operation specs, safety profiles, and conformance fixtures.

## Host enforcement is required

Lowered TypeScript skeletons rely on a host runtime to implement enforcement hooks such as `enforceOperation`, `enforceTransaction`, and `runTransaction`.

## Bounded workflow registry

The public RC candidate is closed-world. Unknown workflows are refused with `W001.unknown_workflow` until a workflow profile, operation specs, effect/capability contracts, evidence requirements, transaction rules, negative conformance fixtures, and golden traces are registered.

See `docs/workflow_registry_extension.md`.

## Fixture-backed evidence ledger

The public evidence ledger is deterministic and bundled. It demonstrates evidence binding and self-attestation refusal, but it is not an enterprise evidence provider backend.

See `docs/evidence_provider_interface.md` and `docs/offline_evidence_providers.md`.

## Conformance-only additive profiles

Profile Manifest v1 and the authoring SDK create context-local conformance bundles. P3 profiles cannot add new global effect/capability taxonomy entries, aliases, role markers, external-effect allowlists, broad effect families, or capability prefixes. `profile_fixture` evidence is deterministic test material, not production evidence.

See `docs/profile_authoring.md` and `docs/profile_conformance.md`.

## Bounded effect taxonomy

The public safety registry is conservative and intentionally small. It is not a complete enterprise effect taxonomy. Future deployments should use canonical effect contracts and registry-governed aliases rather than relying on open-ended string matching.

See `docs/effect_taxonomy_and_canonical_effects.md`.

## Bounded local registry evolution, not production governance

AiNIR implements exact, current-registry, and migrated replay with content-bound RegistrySnapshot, RegistryDiff, and RegistryMigrationRecord artifacts. It does not yet implement cryptographic migration signatures, organizational authorization, distributed registry storage, server-side locking, revocation, or delegated governance.

Approved local migrations are refused by default unless the caller explicitly accepts the unsigned local-review limitation. This is suitable for bounded review and reproducibility testing, not production authorization.

See `docs/trust_receipt_registry_evolution.md`.

## Executable field is not the source of truth

Draft-level `executable` metadata is a claim. Trust Gate and Lowering Eligibility decide whether a draft can move toward lowering.

See `docs/executable_claim_semantics.md`.

## VerifiedIntentPacket is intentionally conservative

The public `VerifiedIntentPacket` surface does not emit concrete downstream schema groundings. Future consumers must perform their own schema, symbol, renderer, runtime, and execution-level verification.

See `docs/verified_intent_packet_scope.md`.


## Bounded MCP preflight, not an MCP runtime

P6 validates a reviewed subset of proposed `tools/call` requests for the `2025-11-25` and `2026-07-28` protocol shapes. It does not implement transport, discovery, OAuth, Tasks, elicitation, sampling, multi-round execution, tool result verification, or tool execution. Descriptions and annotations are untrusted. A `passed` result is only a host-handoff eligibility signal under exact bindings, not proof that a server or implementation is benign.

See `docs/mcp_tool_call_profile.md` and `docs/mcp_host_owned_adapter.md`.

## No arbitrary-code semantic guarantee

AiNIR v1.0 RC candidate demonstrates a registry-backed trust gate for bounded workflow profiles. It does not claim to infer all hidden semantics of arbitrary AI-generated code. Expanding coverage requires registered workflow profiles, canonical effects, evidence providers, and conformance packs.

## OpenAI function-call adapter is not an API client

P7 accepts a completed, host-observed Responses function-call item and exact reviewed function schema. It does not assemble streams, call OpenAI, submit function output, support hosted/built-in tools, own retries or response state, handle credentials, or execute a function. A passed result remains host preflight only.
