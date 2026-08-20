
# Pre-v1 Phase 26 — GitHub Private Trial Simulation

Phase 26 is not a new verifier feature. It is a launch-readiness simulation that runs the public candidate in a fresh temporary copy, writes all command outputs outside the repository, and confirms that the repo remains clean after the trial commands.

The goal is to approximate what should happen after uploading the public candidate to a private GitHub repository:

1. README commands work.
2. GitHub Actions commands are sensible.
3. Public/private boundaries remain clean.
4. No generated outputs, caches, private archives, or nested ZIPs are included in the public repo.
5. Trust Gate, TrustReceipt replay, negative conformance, golden traces, and VerifiedIntentPacket strict contract checks remain green.
6. The project remains explicitly pre-v1, not a v1.0 final release and not a production runtime.

Run:

```bash
python scripts/run_phase26_private_trial.py --out-dir /tmp/ainir_phase26_private_trial
```

A passing Phase 26 result means the public candidate is ready to be uploaded to a private GitHub repository for real UI/CI inspection. It does not mean public release, v1.0 final, or production runtime readiness.
