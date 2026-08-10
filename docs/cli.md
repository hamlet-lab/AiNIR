# AiNIR command-line interface

The stable RC2 CLI is organized by purpose. Users do not need to know AiNIR's historical phase numbers.

## Core commands

```bash
ainir verify <draft>
ainir trust evaluate <draft>
ainir receipt issue <draft> --out-dir <directory>
ainir receipt verify <receipt.json>
ainir receipt replay <receipt.json> [--draft <draft>]
ainir evidence bundle <bundle.json>
ainir evidence policy <policy.json>
ainir evidence resolve <bundle.json> <policy.json> <draft> --claim-id <id> --evidence-id <id> --evaluation-time <timestamp>
ainir mcp profile
ainir mcp init <directory> --profile-id <id> --tool-name <name>
ainir mcp normalize <descriptor.json> <call.json> <transport.json>
ainir mcp assess <descriptor.json> <call.json> <transport.json> <host-input.json>
ainir mcp conformance [--profile <profile.yaml>] [--cases <cases.yaml>]
ainir openai function-tool normalize <tool.json> <function-call.json> <host-binding.json>
ainir openai function-tool assess <tool.json> <function-call.json> <host-binding.json> <host-input.json>
ainir lower <draft> --out-dir <directory>
ainir demo
```

`trust evaluate` inspects a draft and produces a stable `ainir.trust-gate-decision.v1` decision. It does not execute the draft. `receipt issue` produces a stable `ainir.trust-receipt.v1` receipt and a content-bound `ainir.registry-snapshot.v1` sidecar. `receipt verify` checks JSON, contract fields, and the receipt's self-hash without re-running the Trust Gate. The `evidence` commands validate bounded offline provider artifacts; even an accepted result remains only a `validated_candidate` and cannot authorize execution.

## TrustReceipt replay modes

```bash
ainir receipt replay <receipt.json> --mode exact_snapshot_replay
ainir receipt replay <receipt.json> --mode current_registry_replay --source-snapshot <snapshot.json>
ainir receipt replay <receipt.json> --mode migrated_registry_replay \
  --source-snapshot <source.json> \
  --target-snapshot <target.json> \
  --migration-record <migration.json>
```

- `exact_snapshot_replay` preserves the historical exact-replay behavior.
- `current_registry_replay` re-evaluates under the active registry while leaving the historical receipt untouched.
- `migrated_registry_replay` requires an explicit source/target migration binding and fully re-runs the Trust Gate under the target registry.

Cryptographic migration signatures are not implemented. Even an approved local migration is refused unless the caller explicitly adds `--accept-unsigned-local-approval`. This is a bounded local-review escape hatch, not a production authorization mechanism.

## Conformance commands

```bash
ainir conformance negative
ainir conformance golden
ainir conformance run <profile.yaml-or-ainir.public-demo.v1> --out-dir <directory>
ainir conformance trust-gate
ainir conformance receipt
ainir conformance receipt-integration
ainir conformance release-readiness
ainir conformance intent-export
ainir conformance intent-hardening
ainir conformance intent-semantics
ainir conformance intent-contract
ainir conformance private-trial
ainir conformance release-candidate --mode quick-integrity
```

The phase-tagged commands used by older scripts remain accepted for one RC transition. They print a deprecation message to standard error and route to the corresponding command above. Legacy receipt replay remains exact-only.

## Offline evidence providers

```bash
ainir evidence bundle <bundle.json> [--verification-key-file <key>]
ainir evidence policy <policy.json>
ainir evidence resolve <bundle.json> <policy.json> <draft> \
  --claim-id <claim-id> \
  --evidence-id <evidence-id> \
  --expected-kind <kind> \
  --evaluation-time <host-timestamp>
```

The host supplies `evaluation-time`; provider timestamps are not accepted as the clock authority. A successful resolution produces only a `validated_candidate`. P5 never inserts it into the Trust Gate Evidence Ledger and never authorizes execution. `signed_bundle` uses local HMAC integrity for deterministic review, not public-key issuer attestation. See [`offline_evidence_providers.md`](offline_evidence_providers.md).

## MCP tool-call preflight

```bash
ainir mcp profile [profile.yaml] [--json]
ainir mcp normalize <descriptor.json> <call.json> <transport.json> [--out envelope.json]
ainir mcp assess <descriptor.json> <call.json> <transport.json> <host-input.json> [--out-dir reports]
ainir mcp conformance [--out-dir reports]
```

These commands do not open a transport or execute a tool. `assess` returns exit code `0` only for `passed`; destructive `review_required`, refusal, and invalid results use a nonzero exit code. The host remains responsible for final authorization and execution. See [`mcp_tool_call_profile.md`](mcp_tool_call_profile.md).

## Profile authoring and inspection

```bash
ainir profile list
ainir profile show AIVLConsumerProfile
ainir profile list --kind workflow [--root profiles]
ainir profile init <directory> --profile-id <id> --workflow-id <workflow>
ainir profile validate <profile.yaml-or-ainir.public-demo.v1>
ainir profile inspect <profile.yaml-or-ainir.public-demo.v1>
ainir profile export-intent <draft> --profile AIVL
```

`profile list` defaults to the RC2 read-only consumer-profile view for compatibility. `--kind workflow` exposes Profile Manifest v1 packages. Additive workflow profiles are compiled only inside an isolated conformance context and cannot overwrite protected registries, override a failed Trust Gate, or cause AiNIR to execute a downstream action.

`conformance run` always writes JSON, JSONL, JUnit XML, and YAML reports; `--format` selects the standard-output representation.

## Registry inspection and evolution

```bash
ainir registry list
ainir registry show safety_registry.yaml
ainir registry snapshot
ainir registry snapshot --evolution --out registry.json
ainir registry diff source.json target.json --out diff.json
ainir registry migration create source.json target.json \
  --authorized-by <reviewer-id> --reason <reason> --approve --out migration.json
ainir registry migration validate migration.json source.json target.json --require-approved
ainir contracts
```

Without `--evolution`, `registry snapshot` retains the legacy provenance output. With `--evolution`, it emits the portable `ainir.registry-snapshot.v1` artifact. See [`trust_receipt_registry_evolution.md`](trust_receipt_registry_evolution.md).

## JSON output

Commands that support `--json` write machine-readable JSON to standard output. Deprecation warnings are written to standard error so legacy JSON output remains parseable.

## Exit codes

- `0`: the requested check or replay procedure completed successfully, or an artifact was produced;
- `2`: a draft, receipt, replay binding, migration, evidence candidate, conformance check, or lookup was refused/failed;
- `3`: AiNIR generated an artifact that failed its own public contract validation;
- argparse usage errors use its standard nonzero exit code.

For current or migrated replay, exit code `0` means the replay procedure was valid. Inspect `evaluated_status` separately; it may be `refused` or `invalid`.

## External MCP authoring and OpenAI host preflight

`mcp init` emits a fixed-semantics read-only profile and four file-bound conformance cases. External profiles cannot use the bundled internal scenario shorthand.

`openai function-tool normalize` accepts a completed host-observed function call and creates a content-bound OpenAI binding plus MCP envelope. `assess` adds the P6 host context and assessment. Both are local-only; `openai_api_called`, `tool_output_submitted`, and `execution_performed` remain false.

See `mcp_profile_authoring.md` and `openai_function_tool_host_adapter.md`.
