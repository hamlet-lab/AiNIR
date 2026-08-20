# Pre-v1 Status

AiNIR is currently a **public v1.0 RC candidate**, not a v1.0 final release and not a production runtime.

The public repository and the `ainir` Python distribution expose a bounded semantic trust layer around AI-generated workflow and tool-call proposals. The public RC is suitable for evaluation, integration experiments, conformance review, and external feedback. It is not a claim of production deployment readiness.

## Current status

```text
status: v1.0.0rc2 public RC
public_release_type: published bounded demo
python_distribution: ainir
production_runtime_ready: false
human_external_review: pending
v1_final_ready: false
```

## What can be claimed

It is accurate to describe this repository as:

> a public v1.0 RC demo showing how AI-generated workflow and tool-call proposals can be parsed, normalized, checked against reviewed semantic contracts and trusted host context, refused when unsupported, and represented by auditable decision artifacts before any host-owned execution step.

The public surface also includes a bounded non-executing host-integration path for reviewed MCP/OpenAI-style tool calls. A `passed` result is not execution authorization; the host still owns time-of-use validation and the real side effect.

## What should not be claimed

Do not claim that this repository is:

- a v1.0 final release;
- a production compiler or execution runtime;
- a production payment/deletion/email runtime;
- a universal verifier for arbitrary AI-generated code;
- a complete formal proof system;
- the full private AiNIR archive;
- externally human-reviewed final software.

## Completed public hardening arc

The public candidate includes the following core surfaces:

1. Safety Registry as single source of truth
2. Strict Draft AST
3. Evidence Ledger binding
4. Operation Spec and workflow semantic profile binding
5. Trusted Execution Context separation
6. Lowering Eligibility Gate and host enforcement contract
7. Negative conformance corpus and deterministic robustness harness
8. Golden traces and replay harness
9. Public/private split and documentation hardening
10. Effect contracts and semantic role tightening
11. Terminology conformance
12. Transaction binding and semantic integrity
13. Release candidate reassessment and review package
14. Operation contract and launch runner stabilization
15. Capability least-privilege and host enforcement contract
16. Exact capability contracts
17. Final defensive conformance review
18. Trust Gate surface consolidation
19. TrustReceipt persistence and replay
20. TrustReceipt conformance integration
21. Launch readiness with TrustReceipt replay
22. Verified Intent export surface and external consumer profile slot
23. VerifiedIntentPacket export contract hardening
24. VerifiedIntentPacket semantic grounding and validator hardening
25. VerifiedIntentPacket contract strictness and registry consistency
26. Local private GitHub trial simulation
27. README and boundary polish
28. First-impression polish
29. Private archive and external context profile split
30. v1.0 RC scope freeze and candidate packaging
31. Public PyPI onboarding and a bounded five-minute host integration path

## RC candidate boundary

The v1.0 RC candidate freezes the reviewed public contract surface for RC evaluation. Public availability does not freeze production deployment behavior, enterprise registry governance, downstream execution integrations, or future release wording.

Historical documents that describe private-GitHub trial or pre-publication upload steps are retained only as development and release-history records.
