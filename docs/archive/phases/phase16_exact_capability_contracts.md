# Pre-v1 Phase 16 — Exact Capability Contracts

Phase 16 tightens the public demo capability model.

The Phase 15 least-privilege check rejected obviously unrelated capabilities, but several operation specs still used broad capability prefixes such as `cap.db.`. A draft could therefore attach an unrelated capability that shared a broad prefix and still satisfy the operation contract.

Phase 16 changes the public demo to exact capability contracts:

- operation specs declare `required_capability_any` and `allowed_capabilities`;
- broad prefix matching is no longer the authority for public-demo operation conformance;
- `allow_extra_capabilities` remains `false` by default;
- an operation with no allowed capability cannot declare any capability;
- lowered TypeScript continues to dispatch through canonical operation envelopes.

This phase keeps AiNIR's rule narrow and explicit:

> Capabilities are not decorative metadata. They are part of the operation contract.
