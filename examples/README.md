# AiNIR public examples

These examples are the fastest way to understand what AiNIR is trying to do.

The public demo is intentionally small and closed-world: known workflow profiles are checked against registered semantic contracts, and unknown workflows are refused rather than guessed.

## At a glance

| Scenario | Proposal | Expected decision |
|---|---|---|
| `account_deletion_hard_delete_blocked` | permanently delete an account | refused |
| `order_payment_real_payment_blocked` | perform a real payment effect | refused |
| `password_reset_raw_token_blocked` | persist a raw reset token | refused |
| `pii_export_raw_pii_blocked` | export unprotected PII | refused |
| `create_user_outbox_safe` | create a user using the reviewed transaction-bound outbox pattern | passed + lowerable |

Run all five with:

```bash
python -m ainir demo
```

## 1. Account deletion: destructive hard delete

File: [`account_deletion_hard_delete_blocked/draft.yaml`](account_deletion_hard_delete_blocked/draft.yaml)

The draft contains a destructive hard-delete operation and capability:

```yaml
workflow: AccountDeletion
operations:
  - op: auth.check_account_deletion_authorization
  - op: db.hard_delete_user
    effects: [effect.destructive.account.hard_delete]
    capabilities: [cap.account.delete.hard]
```

Evaluate it:

```bash
python -m ainir trust evaluate examples/account_deletion_hard_delete_blocked/draft.yaml --json
```

Expected public-demo result: **refused**.

## 2. Real payment: irreversible financial effect

File: [`order_payment_real_payment_blocked/draft.yaml`](order_payment_real_payment_blocked/draft.yaml)

Evaluate it:

```bash
python -m ainir trust evaluate examples/order_payment_real_payment_blocked/draft.yaml --json
```

Expected public-demo result: **refused**.

## 3. Password reset: raw secret persistence

File: [`password_reset_raw_token_blocked/draft.yaml`](password_reset_raw_token_blocked/draft.yaml)

Evaluate it:

```bash
python -m ainir trust evaluate examples/password_reset_raw_token_blocked/draft.yaml --json
```

Expected public-demo result: **refused**.

## 4. PII export: unprotected sensitive data

File: [`pii_export_raw_pii_blocked/draft.yaml`](pii_export_raw_pii_blocked/draft.yaml)

Evaluate it:

```bash
python -m ainir trust evaluate examples/pii_export_raw_pii_blocked/draft.yaml --json
```

Expected public-demo result: **refused**.

## 5. Create user + outbox: bounded safe path

File: [`create_user_outbox_safe/draft.yaml`](create_user_outbox_safe/draft.yaml)

Evaluate it:

```bash
python -m ainir trust evaluate examples/create_user_outbox_safe/draft.yaml --json
```

Expected public-demo result: **passed** and eligible for the bounded lowering path.

Issue a receipt:

```bash
python -m ainir receipt issue examples/create_user_outbox_safe/draft.yaml --json
```

Lower the safe example toward the host-enforcement skeleton:

```bash
python -m ainir lower examples/create_user_outbox_safe/draft.yaml
```

Passing the Trust Gate is not execution. The host runtime still owns authentication, authorization, sandboxing, resource access, transaction enforcement, and any real external side effect.

## Tool-call examples

AiNIR also contains bounded preflight examples for:

- [`mcp_tool_call/`](mcp_tool_call/) — MCP `tools/call` assessment without contacting or executing the server;
- [`openai_function_tool/`](openai_function_tool/) — assessment of already-observed completed OpenAI function-call artifacts;
- [`offline_evidence_provider/`](offline_evidence_provider/) — deterministic evidence-candidate validation without automatic Trust Gate promotion.

Return to the main [`README.md`](../README.md) for the architecture and scope, or follow [`START_HERE.md`](../START_HERE.md) for the shortest guided path.
