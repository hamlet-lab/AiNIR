# AiNIR v1.0 RC Candidate

AiNIR is a **v1.0 RC candidate public demo**. The public repository and Python distribution are now part of the active RC surface; the earlier private-GitHub trial was a pre-publication gate, not the current release state.

This does **not** mean AiNIR is a v1.0 final release or a production runtime.

## RC candidate decision

```text
decision: v1_0_rc_candidate
public_repository: live
python_distribution: ainir
public_release_state: published_rc
production_runtime_ready: false
v1_final_ready: false
human_external_review: pending
```

## What is frozen for RC review

- Trust Gate decision surface
- TrustReceipt issue/replay shape
- offline EvidenceProvider artifact contracts and no-auto-promotion boundary
- public negative conformance corpus
- public golden traces
- public safety registry and operation registry shape
- public VerifiedIntentPacket export contract slot
- public/private boundary language
- launch-readiness and private-trial checks

## What is not frozen

- production host runtime integrations
- enterprise evidence ledger backend and provider-to-ledger promotion governance
- networked provider and external consumer adapters
- organization-level policy registry governance
- future workflow domains beyond the public demo set
- v1.0 final release wording

## Current public path

The first-run path is the published Python distribution and bundled demo:

```bash
python -m pip install ainir
ainir demo
```

The repository also includes a bounded, non-executing [5-minute integration quick start](integration_quickstart.md). A passing AiNIR preflight remains a host-handoff eligibility signal, not permission to skip time-of-use authorization, resource checks, sandboxing, or execution controls.

## Recommended next step

Use the public RC to collect external integration and review evidence while preserving the bounded claim surface. Any later RC or final publication must use a new version; do not reuse the published `1.0.0rc2` identity.

Historical private-trial and prelaunch documents remain in the repository for traceability. They should not be read as instructions to make the currently public repository private again.
