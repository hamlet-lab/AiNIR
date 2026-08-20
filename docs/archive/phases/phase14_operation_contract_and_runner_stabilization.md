# Pre-v1 Phase 14 — Operation Contract Fix and Launch Runner Stabilization

Phase 14 narrows the public demo changes to operation/effect contract correctness and launch-runner stability.

Implemented corrections:

1. `allowed_workflows: []` now means an operation spec is not allowed in any public demo workflow.
2. Operation specs can be explicitly forbidden in the public demo path.
3. Semantic roles marked as forbidden by a workflow profile cannot be disguised with safe-looking effects.
4. Registered safe operations are judged by operation specs, not broad keyword classifiers.
5. Registered operations cannot declare effects outside their spec unless `allow_extra_effects` is explicitly true.
6. The lowerer emits normalized canonical operation ids and normalized effects.
7. Pre-launch and release-candidate review runners write relative outputs outside the repository, use timeouts, and avoid generated-output self-conflicts.

Status: pre-v1 architecture hardening. This is not v1.0 final and not a production runtime.
