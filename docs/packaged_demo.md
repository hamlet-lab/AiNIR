# Packaged public demo

AiNIR's five bounded public demo workflows are bundled with the installed package.

## Why

The normal public demo should not require a source checkout merely to find `examples/`.
After a normal installation from the project source distribution or wheel, users can change to another directory and run:

```bash
python -m ainir demo
```

or:

```bash
ainir demo
```

The entrypoint preserves source-checkout behavior:

1. If `--examples-dir` is explicitly supplied, AiNIR uses that path and never hides a missing/invalid directory by falling back.
2. If the current checkout contains `examples/demo_manifest.json`, AiNIR uses the repository examples.
3. Otherwise, AiNIR materializes the bundled public demo fixtures into a temporary directory and feeds that directory to the existing demo runner.

The verifier, Trust Gate, lowering logic, registries, and expected pass/refusal semantics are unchanged. Only demo-fixture discovery changes.

## Packaged scenarios

- `account_deletion_hard_delete_blocked` — expected `blocked`
- `create_user_outbox_safe` — expected `passed`
- `order_payment_real_payment_blocked` — expected `blocked`
- `password_reset_raw_token_blocked` — expected `blocked`
- `pii_export_raw_pii_blocked` — expected `blocked`

The packaged manifest is kept aligned with the public repository demo manifest.

## Verification

`.github/workflows/packaged-demo-smoke.yml` performs a normal `pip install .`, changes into the runner temporary directory, and verifies both module and console-script entrypoints outside the repository checkout.
