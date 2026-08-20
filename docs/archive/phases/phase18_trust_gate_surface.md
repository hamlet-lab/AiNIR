
# Pre-v1 Phase 18 — Trust Gate Surface Consolidation

Phase 18 adds an AiNIR-owned Trust Gate surface. This phase is not an external integration phase and does not add a downstream adapter. It consolidates the
pre-v1 safety gates into a stable decision/receipt interface.

## New artifacts

- `src/ainir/trust_gate.py`
- `schemas/trust_gate_decision.schema.json`
- `schemas/trust_receipt.schema.json`
- `docs/trust_gate.md`
- `docs/trust_receipt.md`
- `tests/test_phase18_trust_gate.py`

## Rule

The Trust Gate is part of AiNIR core. Optional future export slots may be built
on top of it, but they are not the purpose of this phase.
