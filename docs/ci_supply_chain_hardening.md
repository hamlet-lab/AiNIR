# CI and supply-chain hardening

The public repository keeps third-party GitHub Actions pinned to full commit
SHAs, installs Python development dependencies under `requirements.lock.txt`
constraints, and installs the TypeScript compiler with `npm ci` from the
committed lockfile.

The workflow has three complementary gates:

1. `full-tests-py3.11` runs the complete Python suite before the historical
   Phase 30 quick-integrity wrapper and compiles with the locked TypeScript
   fixture;
2. `python-compat` exercises release identity, packaged resources, registries,
   and the Trust Gate on Python 3.10, 3.11, 3.12, and 3.13;
3. `platform-smoke` builds wheel and source distributions on Windows and macOS,
   installs the wheel outside the checkout, compares resource hashes, and
   issues/replays a TrustReceipt.

TypeScript remains pinned to `5.8.3` in this release-contract change. A compiler
major-version upgrade is intentionally separate from packaging and trust
semantics work.

Run the static action-pin check locally:

```bash
python scripts/check_ci_supply_chain_pins.py
```
