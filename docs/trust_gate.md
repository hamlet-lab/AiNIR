# AiNIR Trust Gate

AiNIR Trust Gate is the unified decision surface for the pre-v1 public demo.

It does not integrate AiNIR with any external compiler or runtime. It consolidates the existing AiNIR gates into one decision artifact so a reviewer can answer a simple question:

> Can this AI-generated semantic draft move toward lowering, receipt replay, or future handoff?

## Gates included

The Trust Gate summarizes these checks:

- Strict Draft AST
- Safety Registry Resolution
- Evidence Ledger Binding
- Operation Spec Binding
- Capability Contract
- Workflow Semantic Profile
- Trusted Execution Context
- Transaction Binding
- Policy Core
- Lowering Eligibility

## Decision states

| Status | Meaning |
|---|---|
| `passed` | The draft passed the bounded public-demo gates. Lowering may be allowed if all lowering checks also pass. |
| `refused` | The draft is structurally valid, but one or more safety-critical gates refused it. |
| `hold` | The draft needs clarification, evidence, or review before it can move forward. |
| `invalid` | The draft did not satisfy the strict intake format. |

## Example: refused decision

```json
{
  "status": "refused",
  "executable": false,
  "lowering_allowed": false,
  "handoff_allowed": false,
  "failed_gates": [
    "evidence_ledger",
    "capability_contract"
  ],
  "reasons": [
    {
      "rule_id": "EVIDENCE_SELF_ATTESTED",
      "severity": "critical",
      "message": "Verified claims require ledger-bound evidence."
    }
  ]
}
```

## CLI

```bash
python -m ainir trust evaluate examples/create_user_outbox_safe/draft.yaml --json --out-dir /tmp/ainir_trust_gate
```

Unsafe or malformed drafts produce `status: refused`, `status: hold`, or `status: invalid` and must not be lowered.

## Future handoff signal

`handoff_allowed` is a generic future extension signal. It is not tied to any specific downstream consumer in the current pre-v1 public demo.
