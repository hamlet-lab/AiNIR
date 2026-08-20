# P1 release identity and distributable contracts — 2026-08-10

## Scope

This change implements P1 from the August 2026 priority plan without changing
Trust Gate semantics, registry contents, evidence rules, or lowering policy.

## Delivered

- Python release identity `1.0.0rc2` defined once in `src/ainir/_version.py`;
- dynamic setuptools metadata that reads the runtime version source;
- explicit release tag `v1.0.0-rc.2` and RC2 manifest identity;
- private npm compile-fixture identity separated from the Python release;
- five public schemas packaged under `ainir.schemas`;
- four public registries available under `ainir.registries`;
- allowlisted `ainir.resources` API with deterministic SHA-256 manifest;
- `MANIFEST.in` coverage for wheel/sdist contract sources;
- a scratch-copy distribution checker that builds wheel and sdist, installs the
  wheel without an index, runs outside the checkout, compares resource hashes,
  passes the safe Trust Gate, and issues/replays a TrustReceipt;
- Python 3.10–3.13 compatibility jobs and Windows/macOS distribution-smoke jobs
  in GitHub Actions;
- public API, contributor, scope, release, and distribution documentation.

## Local evidence

- 190 tests pass when executed in bounded groups;
- public demo: passed;
- negative conformance: 71/71 passed;
- golden traces: 10/10 passed;
- Phase 30 full check, including Phase 26 private-trial simulation: passed;
- wheel: `ainir_public_demo-1.0.0rc2-py3-none-any.whl`;
- sdist: `ainir_public_demo-1.0.0rc2.tar.gz`;
- source and installed-wheel public resource hashes: identical;
- installed-wheel safe Trust Gate and exact TrustReceipt replay: passed;
- generated TypeScript skeleton: strict compile passed with `tsc 5.8.3`;
- JSON/YAML parsing, Markdown relative links, action pinning, Python compile,
  and `git diff --check`: passed.

## Environment limitation

Local `npm ci` could not download the already locked TypeScript 5.8.3 tarball
because the execution environment's internal npm mirror returned HTTP 404. The
same compiler version was present globally and strict compilation passed. The
workflow retains `npm ci`; its public GitHub-hosted execution must be observed
after the branch is pushed.

Only Python 3.13 was available in the local execution environment. The 3.10,
3.11, 3.12, Windows, and macOS jobs are defined and statically checked but have
not yet produced hosted-run evidence in this local-only branch.

## Compatibility

- no registry bytes changed;
- no public schema bytes changed, only packaged copies were added;
- no Trust Gate decision logic changed;
- legacy TrustReceipt format and exact replay behavior are unchanged;
- existing historical phase commands remain unchanged;
- the npm metadata is private and not a public package version.
