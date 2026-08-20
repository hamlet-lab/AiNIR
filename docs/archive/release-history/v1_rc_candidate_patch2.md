# AiNIR v1.0 RC Candidate Patch 2 — Trust Surface Consistency

Patch 2 keeps AiNIR within the v1.0 RC candidate boundary while aligning the Trust Gate, lowerer, and TrustReceipt replay surfaces.

## Changes

- Lowering eligibility now preflights public-demo `input_type`, `output_type`, and `return` allowlists.
- `executable: false` drafts cannot lower.
- Trust-looking claim statuses such as `evidence_checked` and `evidence_attached` are rejected in the public draft schema. Use `verified` only with ledger-bound evidence, or keep the claim `hypothesized`/`unverified`.
- TrustReceipt replay now checks stable explanatory fields: failed gates, warning gates, lowering eligibility, and trusted-context source/purpose.
- Phase 26 private-trial checks include a Git-tracked packaging scan when run inside a real Git checkout.

## Status

This is still an RC candidate, not v1.0 final and not a production runtime.
