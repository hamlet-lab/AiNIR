# P2 — Stable public CLI and artifact contracts

Status: implemented and fully validated locally on branch `codex/003-stable-cli-contracts`.

Parent: `codex/002-release-contracts` at `cd847b8c9dc9df647a6d7e94a14dc823e8b75545`.

## Goal

Remove historical phase knowledge from the normal user experience without invalidating existing commands, TrustReceipts, decision artifacts, or exact replay.

P2 changes serialization and command surfaces. It does **not** change Trust Gate semantics, add downstream execution, widen the workflow registry, or implement the P3 profile-authoring SDK.

## Delivered

### Stable CLI

The normal help surface now exposes purpose-oriented commands:

- `ainir trust evaluate`;
- `ainir receipt issue|verify|replay`;
- `ainir profile list|show|export-intent`;
- `ainir conformance ...`;
- `ainir registry list|show|snapshot`;
- `ainir contracts`;
- existing `verify`, `lower`, and `demo` commands.

Historical flat and phase-tagged commands are hidden from help but remain accepted for one RC transition. Deprecation messages go to stderr, preserving machine-readable JSON on stdout. Artifact-producing aliases retain legacy serialization.

### Stable artifact contracts

- Trust Gate decision: `ainir.trust-gate-decision.v1`;
- TrustReceipt: `ainir.trust-receipt.v1`;
- replay report: `ainir.trust-receipt-replay-report.v1`;
- Profile Manifest identifier reserved for P3: `ainir.profile-manifest.v1`.

Legacy `pre_v1_phase18` decisions and receipts remain accepted and exact-replayable. Stable receipts carry `legacy_version: pre_v1_phase18`; conversion changes contract metadata and the derived stable projection hash, not the receipt identity or semantic decision.

### Supported Python APIs

- `ainir.contracts` for public identifiers and the contract manifest;
- `ainir.canonical` for canonical JSON, SHA-256 helpers, and bounded defensive JSON-object loading;
- `ainir.contract_validation` for cross-field runtime checks;
- `convert_trust_receipt_contract()`;
- `verify_trust_receipt_artifact()`;
- `TrustGateDecision.as_public_dict()`;
- `ReceiptReplayReport.as_public_dict()`;
- read-only bundled profile access through `ainir.profiles`.

### Schema and release integration

Root and wheel-packaged schemas accept the stable contracts and their documented legacy transition forms. The RC manifest and Phase 30 check now bind the P2 delivery claims. Current entry documentation and the Phase 26 private-trial runner use phase-independent commands.

### Distribution verification

The installed-wheel checker now exercises the stable CLI and verifies:

- stable CLI help outside the checkout;
- stable Trust Gate decision version;
- stable TrustReceipt issue version;
- stable replay-report version;
- source/wheel schema and registry hash parity;
- exact receipt replay from the installed wheel.

During final validation this checker exposed one real P2 drift: it still expected the old help description and old flat commands. The checker was corrected and a regression test now prevents recurrence.

## Compatibility boundary

The following remain unchanged:

- default internal `TrustGateDecision.as_dict()` is legacy for existing phase harnesses;
- default Python `issue_trust_receipt()` is legacy unless a stable contract is explicitly requested;
- legacy command text output remains unchanged apart from the stderr deprecation warning;
- receipt IDs, statuses, gate results, evidence summaries, and registry bindings remain equivalent;
- historical receipt stable projections remain byte-shape compatible.

## Validation evidence

- 208 pytest tests collected and all uniquely covered;
- 202 non-release-file tests passed in bounded groups;
- 6 release identity and distribution tests passed;
- P2-focused tests: 18 passed;
- public demo: passed with one safe example and four expected refusals;
- negative conformance: 71/71 passed;
- golden traces: 10/10 passed;
- Phase 30 quick-integrity: passed;
- Phase 30 full mode, including Phase 26 private-trial: passed;
- full decision: `v1_0_rc_candidate_ready_for_private_github_trial`;
- distribution contract checks: 9/9 passed;
- Python compileall: passed;
- JSON parsed: 12 files;
- YAML parsed: 25 files;
- relative Markdown links checked: 123, missing: 0;
- `git diff --check`: passed.

The environment exposed third-party pytest plugins that could remain alive after completed test output. Final grouped validation therefore also ran with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`; all groups exited cleanly.

## Known limitations

- Hosted Python 3.10–3.13 and Windows/macOS evidence remains pending until the branch is pushed and GitHub Actions runs.
- Setuptools reports that the current TOML-table license form will be deprecated in 2027. Changing it safely requires reconciling the build-system minimum and belongs in release hardening rather than this compatibility PR.
- Profile authoring, standalone profile conformance reports, registry semantic migration, and live evidence providers remain later priorities.
- No GitHub push, pull request, tag, or release was performed in this local development step.

## Next priority

P3 — Profile Authoring SDK and standalone conformance runner, while keeping all protected core invariants non-overridable.
