from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from ._version import __version__
from .canonical import sha256_bytes, sha256_json
from .contract_validation import validate_replay_report, validate_trust_gate_decision
from .contracts import (
    LEGACY_TRUST_RECEIPT_VERSION,
    TRUST_RECEIPT_CONTRACT,
    artifact_contract_manifest,
)
from .core import dump_yaml, iter_example_drafts, load_draft, load_yaml_no_duplicate_keys
from .execution_context import TrustedExecutionContext, allowed_environments
from .evidence_provider import (
    EvidenceProviderError,
    FileEvidenceProvider,
    FixtureEvidenceProvider,
    SignedBundleEvidenceProvider,
    build_evidence_request_from_draft,
    load_evidence_bundle,
    load_evidence_provider_policy,
    validate_evidence_bundle,
    validate_evidence_provider_policy,
    validate_evidence_resolution,
    validate_evidence_validation_report,
    write_evidence_artifact,
)
from .golden_trace_harness import run_golden_traces
from .lowering import lower_to_typescript
from .negative_conformance_harness import run_negative_conformance_corpus
from .mcp_conformance import (
    MCPConformanceError,
    load_bundled_mcp_conformance_pack,
    load_mcp_conformance_pack,
    run_mcp_conformance,
    run_bundled_mcp_conformance,
    validate_mcp_conformance_pack,
)
from .mcp_authoring import MCPProfileAuthoringError, initialize_mcp_profile
from .mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    MCPToolCallError,
    assess_mcp_tool_call,
    build_mcp_host_context,
    build_mcp_tool_call_envelope,
    load_json_mapping as load_mcp_json_mapping,
    materialized_mcp_profile_source,
    validate_mcp_host_context,
    validate_mcp_tool_call_assessment,
    validate_mcp_tool_call_envelope,
    validate_mcp_tool_call_profile,
    write_mcp_artifact,
)
from .openai_function_tool_adapter import (
    OpenAIFunctionToolError,
    build_openai_function_call_binding,
    build_openai_function_tool_preflight,
    validate_openai_function_call_binding,
    validate_openai_function_tool_preflight,
    write_openai_function_artifact,
)
from .conformance_runner import (
    ConformancePackError,
    render_conformance_report,
    run_profile_conformance,
)
from .profile_manifest import (
    BUILTIN_PROFILE_ID,
    ProfileManifestError,
    initialize_profile,
    inspect_profile_manifest,
    list_workflow_profile_manifests,
    materialized_profile_source,
    validate_profile_manifest,
)
from .profiles import UnknownConsumerProfileError, consumer_profile_registry, get_consumer_profile, list_consumer_profiles
from .profile_runtime import compile_profile, profile_registry_context
from .registry_provenance import registry_snapshot, registry_snapshot_failures
from .registry_evolution import (
    RegistryEvolutionError,
    capture_registry_snapshot,
    create_registry_migration_record,
    diff_registry_snapshots,
    load_registry_migration_record,
    validate_registry_migration_record,
    write_registry_diff,
    write_registry_migration_record,
    write_registry_snapshot,
)
from .registry_replay import (
    EXACT_SNAPSHOT_REPLAY,
    REPLAY_MODES,
    replay_trust_receipt_mode,
)
from .resources import (
    PUBLIC_REGISTRY_NAMES,
    UnknownPublicResourceError,
    read_registry_text,
    registry_info,
)
from .temp_paths import ainir_temp_str
from .trust_gate import evaluate_trust_gate
from .trust_receipt_store import (
    issue_trust_receipt,
    replay_trust_receipt,
    verify_trust_receipt_artifact,
)
from .verifier import verify_draft


_LEGACY_COMMAND_REPLACEMENTS: dict[str, tuple[str, ...]] = {
    "trust-gate": ("trust", "evaluate"),
    "trust-receipt-issue": ("receipt", "issue"),
    "trust-receipt-replay": ("receipt", "replay"),
    "negative-conformance-eval": ("conformance", "negative"),
    "golden-trace-eval": ("conformance", "golden"),
    "verified-intent-export": ("profile", "export-intent"),
    "phase18-trust-gate-eval": ("conformance", "trust-gate"),
    "phase19-trust-receipt-eval": ("conformance", "receipt"),
    "phase20-receipt-conformance-eval": ("conformance", "receipt-integration"),
    "phase21-launch-readiness-eval": ("conformance", "release-readiness"),
    "phase22-verified-intent-eval": ("conformance", "intent-export"),
    "phase23-verified-intent-hardening-eval": ("conformance", "intent-hardening"),
    "phase24-verified-intent-semantic-eval": ("conformance", "intent-semantics"),
    "phase25-verified-intent-contract-eval": ("conformance", "intent-contract"),
    "phase26-private-trial-eval": ("conformance", "private-trial"),
    "phase30-v1-rc-candidate-check": ("conformance", "release-candidate"),
}


def _rewrite_legacy_argv(argv: list[str]) -> tuple[list[str], str | None]:
    if not argv or argv[0] not in _LEGACY_COMMAND_REPLACEMENTS:
        return argv, None
    legacy_name = argv[0]
    replacement = _LEGACY_COMMAND_REPLACEMENTS[legacy_name]
    replacement_text = "ainir " + " ".join(replacement)
    print(
        f"warning: 'ainir {legacy_name}' is deprecated; use '{replacement_text}'.",
        file=sys.stderr,
    )
    return [*replacement, *argv[1:]], legacy_name


def _add_env_argument(parser: argparse.ArgumentParser, *, default: str | None = "public_demo") -> None:
    parser.add_argument(
        "--env",
        choices=list(allowed_environments()),
        default=default,
        help="trusted runtime environment; draft.environment is ignored",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ainir",
        description="AiNIR semantic trust and conformance CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="verify one draft without lowering or execution")
    verify.add_argument("draft")
    verify.add_argument("--json", action="store_true")
    _add_env_argument(verify)

    trust = sub.add_parser("trust", help="evaluate the AiNIR Trust Gate")
    trust_sub = trust.add_subparsers(dest="trust_command", required=True)
    trust_evaluate = trust_sub.add_parser("evaluate", help="evaluate a draft and optionally persist decision artifacts")
    trust_evaluate.add_argument("draft")
    trust_evaluate.add_argument("--json", action="store_true")
    trust_evaluate.add_argument("--out-dir", default=None)
    _add_env_argument(trust_evaluate)

    receipt = sub.add_parser("receipt", help="issue, validate, or replay TrustReceipts")
    receipt_sub = receipt.add_subparsers(dest="receipt_command", required=True)
    receipt_issue = receipt_sub.add_parser("issue", help="issue a TrustReceipt using the stable public contract")
    receipt_issue.add_argument("draft")
    receipt_issue.add_argument("--out-dir", default="trust_receipts")
    receipt_issue.add_argument("--json", action="store_true")
    receipt_issue.add_argument(
        "--registry-snapshot-out",
        default=None,
        help="optional RegistrySnapshot output path; defaults to a content-addressed sidecar in --out-dir",
    )
    _add_env_argument(receipt_issue)
    receipt_verify = receipt_sub.add_parser("verify", help="validate receipt JSON, contract fields, and self-hash")
    receipt_verify.add_argument("receipt")
    receipt_verify.add_argument("--json", action="store_true")
    receipt_replay = receipt_sub.add_parser("replay", help="re-evaluate a receipt against its draft and registry")
    receipt_replay.add_argument("receipt")
    receipt_replay.add_argument("--draft", default=None)
    receipt_replay.add_argument("--out-dir", default=None)
    receipt_replay.add_argument("--json", action="store_true")
    receipt_replay.add_argument(
        "--mode",
        choices=REPLAY_MODES,
        default=EXACT_SNAPSHOT_REPLAY,
        help="exact historical replay, current-registry evaluation, or explicit migrated replay",
    )
    receipt_replay.add_argument("--source-snapshot", default=None, help="historical P4 RegistrySnapshot artifact")
    receipt_replay.add_argument("--target-snapshot", default=None, help="target P4 RegistrySnapshot for migrated replay")
    receipt_replay.add_argument("--migration-record", default=None, help="approved RegistryMigrationRecord for migrated replay")
    receipt_replay.add_argument(
        "--accept-unsigned-local-approval",
        action="store_true",
        help="explicitly accept an approved local migration record even though cryptographic signatures are not implemented",
    )
    _add_env_argument(receipt_replay, default=None)

    profile = sub.add_parser("profile", help="inspect consumer profiles and author workflow semantic profiles")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_list = profile_sub.add_parser("list", help="list bundled consumer profiles or workflow profile manifests")
    profile_list.add_argument("--json", action="store_true")
    profile_list.add_argument(
        "--kind",
        choices=("consumer", "workflow", "all"),
        default="consumer",
        help="profile surface to list; consumer preserves the RC2 compatibility view",
    )
    profile_list.add_argument("--root", default=None, help="optional directory to scan for workflow profile.yaml files")
    profile_show = profile_sub.add_parser("show", help="show one bundled consumer profile")
    profile_show.add_argument("profile_id")
    profile_show.add_argument("--json", action="store_true")
    profile_init = profile_sub.add_parser("init", help="create a safe additive workflow profile scaffold")
    profile_init.add_argument("target")
    profile_init.add_argument("--profile-id", required=True)
    profile_init.add_argument("--workflow-id", required=True)
    profile_init.add_argument("--force", action="store_true")
    profile_validate = profile_sub.add_parser("validate", help="validate a Profile Manifest and its conformance pack")
    profile_validate.add_argument("source", help=f"manifest path or bundled id {BUILTIN_PROFILE_ID}")
    profile_validate.add_argument("--json", action="store_true")
    profile_inspect = profile_sub.add_parser("inspect", help="inspect one workflow profile manifest")
    profile_inspect.add_argument("source", help=f"manifest path or bundled id {BUILTIN_PROFILE_ID}")
    profile_inspect.add_argument("--json", action="store_true")
    profile_export = profile_sub.add_parser("export-intent", help="export the bounded VerifiedIntentPacket compatibility surface")
    profile_export.add_argument("draft")
    profile_export.add_argument("--profile", default="AIVL")
    profile_export.add_argument("--out-dir", default=ainir_temp_str("ainir_verified_intent_results"))
    profile_export.add_argument("--json", action="store_true")
    _add_env_argument(profile_export)

    conformance = sub.add_parser("conformance", help="run public conformance and release-review checks")
    conf_sub = conformance.add_subparsers(dest="conformance_command", required=True)
    conf_negative = conf_sub.add_parser("negative", help="run defensive negative conformance cases")
    conf_negative.add_argument("--corpus", default="negative_conformance_corpus.yaml")
    conf_negative.add_argument("--out-dir", default=ainir_temp_str("ainir_negative_conformance"))
    _add_env_argument(conf_negative)
    conf_golden = conf_sub.add_parser("golden", help="run fixed golden traces")
    conf_golden.add_argument("--traces", default="golden_traces.yaml")
    conf_golden.add_argument("--out-dir", default=ainir_temp_str("ainir_golden_traces"))
    _add_env_argument(conf_golden)
    conf_run = conf_sub.add_parser("run", help="run a workflow profile conformance pack")
    conf_run.add_argument("source", help=f"manifest path or bundled id {BUILTIN_PROFILE_ID}")
    conf_run.add_argument("--out-dir", default=ainir_temp_str("ainir_profile_conformance"))
    conf_run.add_argument("--format", choices=("console", "json", "jsonl", "junit"), default="console")
    _add_env_argument(conf_run)

    conformance_specs = {
        "trust-gate": ("run Trust Gate conformance checks", "ainir_phase18_trust_gate"),
        "receipt": ("run TrustReceipt issue/replay checks", "ainir_phase19_trust_receipt"),
        "receipt-integration": ("run TrustReceipt integration checks", "ainir_phase20_receipt_conformance"),
        "release-readiness": ("run launch-readiness checks", "ainir_phase21_launch_readiness"),
        "intent-export": ("run verified-intent export checks", "ainir_phase22_verified_intent"),
        "intent-hardening": ("run verified-intent hardening checks", "ainir_phase23_verified_intent_hardening"),
        "intent-semantics": ("run verified-intent semantic checks", "ainir_phase24_verified_intent_semantic"),
        "intent-contract": ("run strict verified-intent contract checks", "ainir_phase25_verified_intent_contract"),
        "private-trial": ("run local private-repository simulation", "ainir_phase26_private_trial"),
    }
    for name, (help_text, default_dir) in conformance_specs.items():
        item = conf_sub.add_parser(name, help=help_text)
        item.add_argument("--out-dir", default=ainir_temp_str(default_dir))
    conf_release = conf_sub.add_parser("release-candidate", help="run the RC scope and package check")
    conf_release.add_argument("--out-dir", default=ainir_temp_str("ainir_phase30_v1_rc_candidate"))
    conf_release.add_argument("--mode", choices=["quick-integrity", "full"], default="full")


    mcp = sub.add_parser("mcp", help="inspect and assess bounded MCP tool calls without executing them")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_profile = mcp_sub.add_parser("profile", help="validate or show the bundled MCP tool-call profile")
    mcp_profile.add_argument("source", nargs="?", default=BUILTIN_MCP_PROFILE_ID)
    mcp_profile.add_argument("--json", action="store_true")
    mcp_init = mcp_sub.add_parser("init", help="create a fixed-semantics read-only MCP profile scaffold")
    mcp_init.add_argument("directory")
    mcp_init.add_argument("--profile-id", required=True)
    mcp_init.add_argument("--tool-name", required=True)
    mcp_init.add_argument("--server-id", default=None)
    mcp_init.add_argument("--server-origin", default=None)
    mcp_init.add_argument("--authorization-audience", default=None)
    mcp_normalize = mcp_sub.add_parser("normalize", help="bind a descriptor and proposed tools/call into a deterministic envelope")
    mcp_normalize.add_argument("descriptor")
    mcp_normalize.add_argument("call")
    mcp_normalize.add_argument("transport")
    mcp_normalize.add_argument("--profile", default=BUILTIN_MCP_PROFILE_ID)
    mcp_normalize.add_argument("--out", default=None)
    mcp_normalize.add_argument("--json", action="store_true")
    mcp_assess = mcp_sub.add_parser("assess", help="run host-owned preflight without contacting or executing an MCP server")
    mcp_assess.add_argument("descriptor")
    mcp_assess.add_argument("call")
    mcp_assess.add_argument("transport")
    mcp_assess.add_argument("host_input", help="host-owned JSON arguments for build_mcp_host_context")
    mcp_assess.add_argument("--profile", default=BUILTIN_MCP_PROFILE_ID)
    mcp_assess.add_argument("--out-dir", default=None)
    mcp_assess.add_argument("--json", action="store_true")
    mcp_conf = mcp_sub.add_parser("conformance", help="run a bundled or file-bound MCP preflight conformance pack")
    mcp_conf.add_argument("--profile", default=BUILTIN_MCP_PROFILE_ID)
    mcp_conf.add_argument("--cases", default=None)
    mcp_conf.add_argument("--out-dir", default=ainir_temp_str("ainir_mcp_tool_call_conformance"))
    mcp_conf.add_argument("--json", action="store_true")

    openai_cmd = sub.add_parser("openai", help="normalize finalized OpenAI function calls without calling the API or executing tools")
    openai_sub = openai_cmd.add_subparsers(dest="openai_command", required=True)
    openai_function = openai_sub.add_parser("function-tool", help="host-owned adapter for Responses function_call items")
    openai_function_sub = openai_function.add_subparsers(dest="openai_function_command", required=True)
    openai_normalize = openai_function_sub.add_parser("normalize", help="bind a completed function_call item to a reviewed AiNIR profile")
    openai_normalize.add_argument("tool_definition")
    openai_normalize.add_argument("function_call")
    openai_normalize.add_argument("host_binding")
    openai_normalize.add_argument("--profile", default=BUILTIN_MCP_PROFILE_ID)
    openai_normalize.add_argument("--out-dir", default=None)
    openai_normalize.add_argument("--json", action="store_true")
    openai_assess = openai_function_sub.add_parser("assess", help="run non-executing host preflight for a completed function_call item")
    openai_assess.add_argument("tool_definition")
    openai_assess.add_argument("function_call")
    openai_assess.add_argument("host_binding")
    openai_assess.add_argument("host_input")
    openai_assess.add_argument("--profile", default=BUILTIN_MCP_PROFILE_ID)
    openai_assess.add_argument("--out-dir", default=None)
    openai_assess.add_argument("--json", action="store_true")

    evidence = sub.add_parser("evidence", help="validate deterministic offline evidence-provider artifacts")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)

    evidence_bundle = evidence_sub.add_parser("bundle", help="validate an offline EvidenceBundle")
    evidence_bundle.add_argument("bundle")
    evidence_bundle.add_argument("--verification-key-file", default=None, help="local HMAC verification key file for signed_bundle artifacts")
    evidence_bundle.add_argument("--require-signature", action="store_true", help="require a verified HMAC signature")
    evidence_bundle.add_argument("--json", action="store_true")

    evidence_policy = evidence_sub.add_parser("policy", help="validate an EvidenceProviderPolicy")
    evidence_policy.add_argument("policy")
    evidence_policy.add_argument("--json", action="store_true")

    evidence_resolve = evidence_sub.add_parser("resolve", help="resolve one candidate record and independently validate it")
    evidence_resolve.add_argument("bundle")
    evidence_resolve.add_argument("policy")
    evidence_resolve.add_argument("draft")
    evidence_resolve.add_argument("--claim-id", required=True)
    evidence_resolve.add_argument("--evidence-id", required=True)
    evidence_resolve.add_argument("--expected-kind", default=None)
    evidence_resolve.add_argument("--evaluation-time", required=True, help="host-supplied ISO-8601 timestamp with timezone")
    evidence_resolve.add_argument("--verification-key-file", default=None, help="local HMAC verification key file for signed_bundle artifacts")
    evidence_resolve.add_argument("--out-dir", default=None, help="optional directory for request, resolution, and validation report JSON")
    evidence_resolve.add_argument("--json", action="store_true")

    registry = sub.add_parser("registry", help="inspect packaged public registries")
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    registry_list = registry_sub.add_parser("list", help="list allowlisted registry resources and hashes")
    registry_list.add_argument("--json", action="store_true")
    registry_show = registry_sub.add_parser("show", help="show one packaged registry")
    registry_show.add_argument("name", choices=list(PUBLIC_REGISTRY_NAMES))
    registry_show.add_argument("--json", action="store_true", help="parse YAML and emit JSON")
    registry_snapshot_parser = registry_sub.add_parser("snapshot", help="show the current content-bound registry snapshot")
    registry_snapshot_parser.add_argument("--json", action="store_true")
    registry_snapshot_parser.add_argument(
        "--evolution",
        action="store_true",
        help="emit the portable ainir.registry-snapshot.v1 artifact instead of the legacy provenance view",
    )
    registry_snapshot_parser.add_argument(
        "--profile",
        default=None,
        help=f"optional workflow Profile Manifest path or bundled id {BUILTIN_PROFILE_ID}; requires --evolution",
    )
    registry_snapshot_parser.add_argument("--out", default=None, help="optional output JSON path")
    registry_snapshot_parser.add_argument("--parent-snapshot-hash", default=None, help="optional parent artifact sha256 binding; requires --evolution")

    registry_diff_parser = registry_sub.add_parser("diff", help="classify semantic changes between two RegistrySnapshot artifacts")
    registry_diff_parser.add_argument("source")
    registry_diff_parser.add_argument("target")
    registry_diff_parser.add_argument("--json", action="store_true")
    registry_diff_parser.add_argument("--out", default=None, help="optional output JSON path")

    registry_migration = registry_sub.add_parser("migration", help="create or validate explicit registry migration records")
    registry_migration_sub = registry_migration.add_subparsers(dest="registry_migration_command", required=True)
    registry_migration_create = registry_migration_sub.add_parser("create", help="bind a source/target diff to explicit review metadata")
    registry_migration_create.add_argument("source")
    registry_migration_create.add_argument("target")
    registry_migration_create.add_argument("--authorized-by", required=True)
    registry_migration_create.add_argument("--reason", required=True)
    registry_migration_create.add_argument("--evidence-ref", default=None)
    registry_migration_create.add_argument("--approve", action="store_true", help="mark explicit local review as approved; this is not a cryptographic signature")
    registry_migration_create.add_argument("--out", required=True)
    registry_migration_create.add_argument("--json", action="store_true")
    registry_migration_validate = registry_migration_sub.add_parser("validate", help="validate migration bindings against source and target snapshots")
    registry_migration_validate.add_argument("record")
    registry_migration_validate.add_argument("source")
    registry_migration_validate.add_argument("target")
    registry_migration_validate.add_argument("--require-approved", action="store_true")
    registry_migration_validate.add_argument("--json", action="store_true")

    contracts = sub.add_parser("contracts", help="show stable artifact contract identifiers")
    contracts.add_argument("--json", action="store_true")

    lower = sub.add_parser("lower", help="verify then lower a safe draft into a TypeScript skeleton")
    lower.add_argument("draft")
    lower.add_argument("--out-dir", default="out")
    _add_env_argument(lower)

    demo = sub.add_parser("demo", help="run all public demo examples")
    demo.add_argument("--examples-dir", default="examples")
    demo.add_argument("--out-dir", default=ainir_temp_str("ainir_demo_results"))
    _add_env_argument(demo)
    return parser


def _write_trust_gate_bundle(out: Path, decision: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    decision_path = out / "trust_gate_decision.json"
    receipt_path = out / "trust_receipt.json"
    manifest_path = out / "trust_receipt_manifest.jsonl"
    decision_path.write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    receipt = dict(decision.get("receipt", {})) if isinstance(decision.get("receipt"), dict) else {}
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    record = {
        "receipt_id": receipt.get("receipt_id"),
        "manifest_record_status": "active",
        "artifact_family": "trust_gate_out_dir_bundle",
        "trust_status": decision.get("status"),
        "stable_receipt_projection_hash": receipt.get("stable_receipt_projection_hash"),
        "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
        "module_id": decision.get("module_id"),
        "workflow": decision.get("workflow"),
        "receipt_raw_file_sha256": sha256_bytes(receipt_path.read_bytes()),
        "receipt_canonical_sha256": sha256_json(receipt),
        "decision_raw_file_sha256": sha256_bytes(decision_path.read_bytes()),
        "decision_canonical_sha256": sha256_json(decision),
        "receipt_path": str(receipt_path),
        "decision_path": str(decision_path),
    }
    manifest_path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_verified_intent_bundle(out: Path, result: dict[str, Any]) -> None:
    from .verified_intent_export import canonical_verified_intent_packet_hash

    out.mkdir(parents=True, exist_ok=True)
    (out / "verified_intent_export_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    packet = result.get("packet")
    receipt = result.get("receipt")
    decision = result.get("decision")
    if isinstance(packet, dict):
        (out / "verified_intent_packet.json").write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    if isinstance(receipt, dict):
        (out / "verified_intent_trust_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    if isinstance(decision, dict):
        (out / "verified_intent_trust_gate_decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    if isinstance(receipt, dict) and isinstance(decision, dict):
        receipt_path = out / "verified_intent_trust_receipt.json"
        decision_path = out / "verified_intent_trust_gate_decision.json"
        packet_path = out / "verified_intent_packet.json"
        record = {
            "artifact_family": "verified_intent_export_bundle",
            "manifest_record_status": "active",
            "receipt_id": receipt.get("receipt_id"),
            "trust_status": decision.get("status"),
            "stable_receipt_projection_hash": receipt.get("stable_receipt_projection_hash"),
            "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
            "module_id": decision.get("module_id"),
            "workflow": decision.get("workflow"),
            "receipt_raw_file_sha256": sha256_bytes(receipt_path.read_bytes()),
            "receipt_canonical_sha256": sha256_json(receipt),
            "decision_raw_file_sha256": sha256_bytes(decision_path.read_bytes()),
            "decision_canonical_sha256": sha256_json(decision),
            "packet_raw_file_sha256": sha256_bytes(packet_path.read_bytes()) if packet_path.exists() else None,
            "packet_canonical_sha256": canonical_verified_intent_packet_hash(packet) if isinstance(packet, dict) else None,
            "receipt_path": str(receipt_path),
            "decision_path": str(decision_path),
            "packet_path": str(packet_path) if packet_path.exists() else None,
        }
        (out / "trust_receipt_manifest.jsonl").write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _print_trust_decision(decision: dict[str, Any]) -> None:
    print(f"trust_gate_status: {decision['status']}")
    print(f"module: {decision['module_id']}")
    print(f"workflow: {decision['workflow']}")
    print(f"lowering_allowed: {decision['lowering_allowed']}")
    print(f"receipt_id: {decision['receipt'].get('receipt_id')}")
    for finding in decision.get("findings", []):
        if finding.get("severity") == "critical":
            print(f"[critical] {finding.get('rule')} :: {finding.get('target')}")


def _run_conformance(args: argparse.Namespace, legacy_name: str | None) -> int:
    name = args.conformance_command
    if name == "run":
        try:
            with materialized_profile_source(args.source) as manifest:
                report = run_profile_conformance(
                    manifest,
                    out_dir=args.out_dir,
                    environment=args.env,
                )
        except (ProfileManifestError, ConformancePackError, OSError, ValueError) as exc:
            print(f"profile conformance failed: {exc}", file=sys.stderr)
            return 2
        print(render_conformance_report(report, args.format), end="")
        return 0 if report.overall_status == "passed" else 2
    if name == "negative":
        summary = run_negative_conformance_corpus(args.corpus, args.out_dir, args.env)
        print(f"AiNIR negative conformance: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "golden":
        summary = run_golden_traces(args.traces, args.out_dir, args.env)
        print(f"AiNIR golden traces: {summary['overall_status']}")
        print(f"traces: {summary['trace_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "trust-gate":
        from .phase18_trust_gate_eval import run_phase18_trust_gate_eval
        summary = run_phase18_trust_gate_eval(args.out_dir)
        label = "AiNIR Phase 18 trust gate eval" if legacy_name else "AiNIR trust-gate conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "receipt":
        from .phase19_trust_receipt_eval import run_phase19_trust_receipt_eval
        summary = run_phase19_trust_receipt_eval(args.out_dir)
        label = "AiNIR Phase 19 trust receipt eval" if legacy_name else "AiNIR receipt conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "receipt-integration":
        from .phase20_receipt_conformance_eval import run_phase20_receipt_conformance_eval
        summary = run_phase20_receipt_conformance_eval(args.out_dir)
        label = "AiNIR Phase 20 receipt conformance eval" if legacy_name else "AiNIR receipt integration conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "release-readiness":
        from .phase21_release_readiness_eval import run_phase21_launch_readiness_eval
        summary = run_phase21_launch_readiness_eval(args.out_dir)
        label = "AiNIR Phase 21 launch readiness" if legacy_name else "AiNIR release readiness"
        print(f"{label}: {summary['overall_status']}")
        print(f"decision: {summary['decision']}")
    elif name == "intent-export":
        from .phase22_verified_intent_eval import run_phase22_verified_intent_eval
        summary = run_phase22_verified_intent_eval(args.out_dir)
        label = "AiNIR Phase 22 verified intent export eval" if legacy_name else "AiNIR verified-intent export conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "intent-hardening":
        from .phase23_verified_intent_hardening_eval import run_phase23_verified_intent_hardening_eval
        summary = run_phase23_verified_intent_hardening_eval(args.out_dir)
        label = "AiNIR Phase 23 verified intent export hardening eval" if legacy_name else "AiNIR verified-intent hardening conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "intent-semantics":
        from .phase24_verified_intent_semantic_eval import run_phase24_verified_intent_semantic_eval
        summary = run_phase24_verified_intent_semantic_eval(args.out_dir)
        label = "AiNIR Phase 24 verified intent semantic eval" if legacy_name else "AiNIR verified-intent semantic conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "intent-contract":
        from .phase25_verified_intent_contract_eval import run_phase25_verified_intent_contract_eval
        summary = run_phase25_verified_intent_contract_eval(args.out_dir)
        label = "AiNIR Phase 25 verified intent contract eval" if legacy_name else "AiNIR verified-intent contract conformance"
        print(f"{label}: {summary['overall_status']}")
        print(f"cases: {summary['case_count']} passed={summary['passed']} failed={summary['failed']}")
    elif name == "private-trial":
        from .phase26_private_trial import run_phase26_private_trial
        summary = run_phase26_private_trial(args.out_dir)
        label = "AiNIR Phase 26 private-trial simulation" if legacy_name else "AiNIR private-repository simulation"
        print(f"{label}: {summary['overall_status']}")
        print(f"decision: {summary['decision']}")
    elif name == "release-candidate":
        from .phase30_v1_rc_candidate import run_phase30_v1_rc_candidate_check
        summary = run_phase30_v1_rc_candidate_check(args.out_dir, mode=args.mode)
        label = "AiNIR Phase 30 v1.0 RC candidate check" if legacy_name else "AiNIR release-candidate check"
        print(f"{label}: {summary['overall_status']}")
        print(f"decision: {summary['decision']}")
    else:  # pragma: no cover - argparse prevents this
        raise ValueError(f"unknown conformance command: {name}")
    print(f"reports: {args.out_dir}")
    return 0 if summary["overall_status"] == "passed" else 2



def _verification_keys_for_bundle(bundle: Mapping[str, Any], key_file: str | None) -> dict[str, bytes]:
    if key_file is None:
        return {}
    signature = bundle.get("signature")
    key_id = signature.get("key_id") if isinstance(signature, Mapping) else None
    if not isinstance(key_id, str) or not key_id:
        raise EvidenceProviderError("verification key was supplied but the bundle has no valid signature key_id")
    key = Path(key_file).read_bytes().strip()
    if len(key) < 16:
        raise EvidenceProviderError("verification key file must contain at least 16 bytes")
    return {key_id: key}


def _find_claim(draft: Any, claim_id: str) -> Mapping[str, Any]:
    for claim in draft.claims:
        if isinstance(claim, Mapping) and claim.get("id") == claim_id:
            return claim
    raise EvidenceProviderError(f"claim id {claim_id!r} was not found in the draft")


def _print_artifact_validation(payload: Mapping[str, Any], *, label: str) -> None:
    print(f"{label}: {payload.get('overall_status')}")
    for check in payload.get("checks", []):
        if isinstance(check, Mapping) and check.get("status") != "passed":
            print(f"[failed] {check.get('check')} expected={check.get('expected')} actual={check.get('actual')}")


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    rewritten, legacy_name = _rewrite_legacy_argv(raw_argv)
    args = _build_parser().parse_args(rewritten)
    legacy_contract = legacy_name is not None

    if args.command == "verify":
        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="verification")
        report = verify_draft(load_draft(args.draft), context)
        if args.json:
            print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        else:
            _print_report(report.as_dict())
        return 0 if report.status == "passed" else 2

    if args.command == "trust" and args.trust_command == "evaluate":
        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="trust_gate")
        decision_object = evaluate_trust_gate(load_draft(args.draft), context)
        decision = decision_object.as_dict() if legacy_contract else decision_object.as_public_dict()
        validation_failures = validate_trust_gate_decision(decision)
        if validation_failures:
            print(json.dumps({"error": "generated_decision_contract_invalid", "checks": validation_failures}, indent=2), file=sys.stderr)
            return 3
        if args.out_dir:
            _write_trust_gate_bundle(Path(args.out_dir), decision)
        if args.json:
            print(json.dumps(decision, indent=2, ensure_ascii=False))
        else:
            _print_trust_decision(decision)
        return 0 if decision["status"] == "passed" else 2

    if args.command == "receipt" and args.receipt_command == "issue":
        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="trust_receipt_issue")
        version = LEGACY_TRUST_RECEIPT_VERSION if legacy_contract else TRUST_RECEIPT_CONTRACT
        issued = issue_trust_receipt(args.draft, args.out_dir, context, contract_version=version)
        summary = issued.as_dict()
        if not legacy_contract:
            try:
                snapshot = capture_registry_snapshot()
                expected_runtime_hash = issued.receipt.get("registry_snapshot_hash")
                actual_runtime_hash = snapshot.get("runtime_registry_snapshot_hash")
                if actual_runtime_hash != expected_runtime_hash:
                    print(
                        json.dumps(
                            {
                                "error": "issued_receipt_registry_snapshot_mismatch",
                                "expected": expected_runtime_hash,
                                "actual": actual_runtime_hash,
                            },
                            indent=2,
                        ),
                        file=sys.stderr,
                    )
                    return 3
                snapshot_path = (
                    Path(args.registry_snapshot_out)
                    if args.registry_snapshot_out
                    else Path(args.out_dir) / f"{snapshot['snapshot_id']}.json"
                )
                write_registry_snapshot(snapshot_path, snapshot)
                summary["registry_snapshot_path"] = str(snapshot_path)
                summary["registry_snapshot_id"] = snapshot.get("snapshot_id")
                summary["registry_snapshot_artifact_sha256"] = snapshot.get("snapshot_sha256")
            except (RegistryEvolutionError, OSError, ValueError) as exc:
                print(f"registry snapshot sidecar creation failed: {exc}", file=sys.stderr)
                return 3
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"trust_receipt_issued: {summary['receipt_id']}")
            print(f"trust_status: {summary['trust_status']}")
            if not legacy_contract:
                print(f"receipt_version: {summary['receipt_version']}")
                print(f"registry_snapshot: {summary['registry_snapshot_path']}")
            print(f"receipt: {summary['receipt_path']}")
            print(f"decision: {summary['decision_path']}")
        return 0

    if args.command == "receipt" and args.receipt_command == "verify":
        report = verify_trust_receipt_artifact(args.receipt).as_dict()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"trust_receipt_verify: {report['overall_status']}")
            print(f"receipt_id: {report.get('receipt_id')}")
            print(f"receipt_version: {report.get('receipt_version')}")
            for check in report.get("checks", []):
                if check.get("status") != "passed":
                    print(f"[failed] {check.get('check')} expected={check.get('expected')} actual={check.get('actual')}")
        return 0 if report["overall_status"] == "passed" else 2

    if args.command == "receipt" and args.receipt_command == "replay":
        context = None
        if args.env:
            context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="trust_receipt_replay")
        if legacy_contract:
            if (
                args.mode != EXACT_SNAPSHOT_REPLAY
                or args.source_snapshot is not None
                or args.target_snapshot is not None
                or args.migration_record is not None
                or args.accept_unsigned_local_approval
            ):
                print(
                    "legacy 'trust-receipt-replay' supports exact replay only; "
                    "use 'ainir receipt replay' for explicit current or migrated replay",
                    file=sys.stderr,
                )
                return 2
            replay = replay_trust_receipt(args.receipt, args.draft, context)
            report = replay.as_dict()
            require_public_contract = False
        else:
            try:
                replay = replay_trust_receipt_mode(
                    args.receipt,
                    args.draft,
                    context,
                    mode=args.mode,
                    source_snapshot=args.source_snapshot,
                    target_snapshot=args.target_snapshot,
                    migration_record=args.migration_record,
                    allow_unsigned_local_approval=args.accept_unsigned_local_approval,
                )
            except (RegistryEvolutionError, ValueError) as exc:
                print(f"receipt replay arguments refused: {exc}", file=sys.stderr)
                return 2
            report = replay.as_dict()
            require_public_contract = True
        validation_failures = validate_replay_report(
            report,
            require_public_contract=require_public_contract,
        )
        if validation_failures:
            print(json.dumps({"error": "generated_replay_report_invalid", "checks": validation_failures}, indent=2), file=sys.stderr)
            return 3
        if args.out_dir:
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "trust_receipt_replay_report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"trust_receipt_replay: {report['overall_status']}")
            if not legacy_contract:
                print(f"replay_mode: {report.get('replay_mode')}")
                print(f"historical_status: {report.get('historical_status')}")
                print(f"evaluated_status: {report.get('evaluated_status')}")
                print(f"decision_changed: {report.get('decision_changed')}")
                print(f"historical_receipt_unchanged: {report.get('historical_receipt_unchanged')}")
                print(f"registry_diff_status: {report.get('registry_diff_status')}")
                diff = report.get("registry_diff")
                if isinstance(diff, dict):
                    print(f"registry_change_classification: {diff.get('overall_classification')}")
            print(f"receipt_id: {report.get('receipt_id')}")
            for check in report.get("checks", []):
                if check.get("status") != "passed":
                    print(f"[failed] {check.get('check')} expected={check.get('expected')} actual={check.get('actual')}")
        return 0 if report["overall_status"] == "passed" else 2


    if args.command == "mcp" and args.mcp_command == "init":
        try:
            profile_path, cases_path = initialize_mcp_profile(
                args.directory,
                profile_id=args.profile_id,
                tool_name=args.tool_name,
                server_id=args.server_id,
                server_origin=args.server_origin,
                authorization_audience=args.authorization_audience,
            )
        except (MCPProfileAuthoringError, OSError, ValueError) as exc:
            print(f"MCP profile initialization failed: {exc}", file=sys.stderr)
            return 2
        print(f"profile: {profile_path}")
        print(f"cases: {cases_path}")
        print("execution_performed: false")
        return 0

    if args.command == "mcp" and args.mcp_command == "profile":
        try:
            with materialized_mcp_profile_source(args.source) as profile:
                validation = validate_mcp_tool_call_profile(profile).as_dict()
                payload = {
                    "profile": dict(profile.data),
                    "validation": validation,
                    "execution_performed": False,
                    "production_runtime_ready": False,
                }
        except (MCPToolCallError, OSError, ValueError) as exc:
            print(f"MCP profile validation failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"mcp_profile_valid: {validation.get('overall_status') == 'passed'}")
            print(f"profile_id: {payload['profile'].get('profile_id')}")
            print(f"profile_sha256: {payload['profile'].get('profile_sha256')}")
            print("execution_performed: false")
            print("production_runtime_ready: false")
        return 0 if validation.get("overall_status") == "passed" else 2

    if args.command == "mcp" and args.mcp_command in {"normalize", "assess"}:
        try:
            descriptor = load_mcp_json_mapping(args.descriptor, label="MCP tool descriptor")
            call = load_mcp_json_mapping(args.call, label="MCP tools/call request")
            transport = load_mcp_json_mapping(args.transport, label="MCP transport binding")
            with materialized_mcp_profile_source(args.profile) as profile:
                envelope = build_mcp_tool_call_envelope(profile, descriptor, call, transport)
                envelope_validation = validate_mcp_tool_call_envelope(envelope)
                if not envelope_validation.valid:
                    raise MCPToolCallError("generated MCP envelope failed public contract validation")
                if args.mcp_command == "normalize":
                    payload = envelope
                else:
                    host_values = load_mcp_json_mapping(args.host_input, label="MCP host input")
                    context = build_mcp_host_context(envelope=envelope, **host_values)
                    if not validate_mcp_host_context(context).valid:
                        raise MCPToolCallError("generated MCP host context failed public contract validation")
                    assessment = assess_mcp_tool_call(profile, envelope, context)
                    if not validate_mcp_tool_call_assessment(assessment).valid:
                        raise MCPToolCallError("generated MCP assessment failed public contract validation")
                    payload = assessment
                    if args.out_dir:
                        output = Path(args.out_dir)
                        write_mcp_artifact(output / "mcp_tool_call_envelope.json", envelope)
                        write_mcp_artifact(output / "mcp_host_context.json", context)
                        write_mcp_artifact(output / "mcp_tool_call_assessment.json", assessment)
        except (MCPToolCallError, OSError, TypeError, ValueError) as exc:
            print(f"MCP {args.mcp_command} failed: {exc}", file=sys.stderr)
            return 2
        target = args.out if args.mcp_command == "normalize" else None
        if target:
            write_mcp_artifact(target, payload)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.mcp_command == "normalize":
            print(f"mcp_envelope: {payload.get('envelope_id')}")
            print(f"envelope_sha256: {payload.get('envelope_sha256')}")
            print("execution_performed: false")
            if target:
                print(f"envelope: {target}")
        else:
            print(f"mcp_assessment: {payload.get('overall_status')}")
            print(f"host_handoff_allowed: {str(payload.get('host_handoff_allowed')).lower()}")
            print(f"assessment_id: {payload.get('assessment_id')}")
            print("execution_performed: false")
            print("production_runtime_ready: false")
            if args.out_dir:
                print(f"reports: {args.out_dir}")
        return 0 if payload.get("overall_status", "passed") == "passed" else 2

    if args.command == "mcp" and args.mcp_command == "conformance":
        try:
            report = run_mcp_conformance(
                args.profile,
                pack_source=args.cases,
                out_dir=args.out_dir,
            )
        except (MCPConformanceError, MCPToolCallError, OSError, ValueError) as exc:
            print(f"MCP conformance failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"AiNIR MCP tool-call conformance: {report.get('overall_status')}")
            print(f"cases: {report.get('case_count')} passed={report.get('passed')} failed={report.get('failed')}")
            print("execution_performed: false")
            print(f"reports: {args.out_dir}")
        return 0 if report.get("overall_status") == "passed" else 2

    if args.command == "openai" and args.openai_command == "function-tool":
        try:
            tool_definition = load_mcp_json_mapping(args.tool_definition, label="OpenAI function tool definition")
            function_call = load_mcp_json_mapping(args.function_call, label="OpenAI function_call item")
            host_binding = load_mcp_json_mapping(args.host_binding, label="OpenAI host binding")
            with materialized_mcp_profile_source(args.profile) as profile:
                if args.openai_function_command == "normalize":
                    binding, envelope = build_openai_function_call_binding(
                        profile,
                        tool_definition,
                        function_call,
                        host_binding,
                    )
                    if not validate_openai_function_call_binding(binding).valid:
                        raise OpenAIFunctionToolError("generated OpenAI binding failed validation")
                    if not validate_mcp_tool_call_envelope(envelope).valid:
                        raise OpenAIFunctionToolError("generated MCP envelope failed validation")
                    payload: Mapping[str, Any] = binding
                    if args.out_dir:
                        output = Path(args.out_dir)
                        write_openai_function_artifact(output / "openai_function_call_binding.json", binding)
                        write_mcp_artifact(output / "mcp_tool_call_envelope.json", envelope)
                else:
                    host_input = load_mcp_json_mapping(args.host_input, label="OpenAI host-owned preflight input")
                    preflight = build_openai_function_tool_preflight(
                        profile,
                        tool_definition,
                        function_call,
                        host_binding,
                        host_input,
                    )
                    if not validate_openai_function_tool_preflight(preflight).valid:
                        raise OpenAIFunctionToolError("generated OpenAI preflight failed validation")
                    payload = preflight
                    if args.out_dir:
                        output = Path(args.out_dir)
                        write_openai_function_artifact(output / "openai_function_tool_preflight.json", preflight)
                        write_openai_function_artifact(output / "openai_function_call_binding.json", preflight["binding"])
                        write_mcp_artifact(output / "mcp_tool_call_envelope.json", preflight["mcp_envelope"])
                        write_mcp_artifact(output / "mcp_host_context.json", preflight["mcp_host_context"])
                        write_mcp_artifact(output / "mcp_tool_call_assessment.json", preflight["mcp_assessment"])
        except (OpenAIFunctionToolError, MCPToolCallError, OSError, TypeError, ValueError) as exc:
            print(f"OpenAI function-tool {args.openai_function_command} failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.openai_function_command == "normalize":
            print(f"openai_binding: {payload.get('binding_id')}")
            print("openai_api_called: false")
            print("execution_performed: false")
        else:
            print(f"openai_preflight: {payload.get('overall_status')}")
            print(f"host_handoff_allowed: {str(payload.get('host_handoff_allowed')).lower()}")
            print("openai_api_called: false")
            print("tool_output_submitted: false")
            print("execution_performed: false")
        return 0 if payload.get("overall_status", "passed") == "passed" else 2

    if args.command == "evidence" and args.evidence_command == "bundle":
        try:
            bundle = load_evidence_bundle(args.bundle)
            keys = _verification_keys_for_bundle(bundle, args.verification_key_file)
            require_signature = bool(args.require_signature or bundle.get("source_kind") == "signed_bundle")
            report = validate_evidence_bundle(
                bundle,
                verification_keys=keys,
                require_signature=require_signature,
            ).as_dict()
        except (EvidenceProviderError, OSError, ValueError) as exc:
            print(f"evidence bundle validation failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            _print_artifact_validation(report, label="evidence_bundle_validation")
        return 0 if report.get("overall_status") == "passed" else 2

    if args.command == "evidence" and args.evidence_command == "policy":
        try:
            policy = load_evidence_provider_policy(args.policy)
            report = validate_evidence_provider_policy(policy).as_dict()
        except (EvidenceProviderError, OSError, ValueError) as exc:
            print(f"evidence policy validation failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            _print_artifact_validation(report, label="evidence_provider_policy_validation")
        return 0 if report.get("overall_status") == "passed" else 2

    if args.command == "evidence" and args.evidence_command == "resolve":
        try:
            bundle = load_evidence_bundle(args.bundle)
            policy = load_evidence_provider_policy(args.policy)
            policy_validation = validate_evidence_provider_policy(policy)
            if not policy_validation.valid:
                raise EvidenceProviderError("provider policy failed validation")
            keys = _verification_keys_for_bundle(bundle, args.verification_key_file)
            source_kind = bundle.get("source_kind")
            if source_kind == "fixture":
                provider = FixtureEvidenceProvider(bundle)
            elif source_kind == "file":
                provider = FileEvidenceProvider(args.bundle)
            elif source_kind == "signed_bundle":
                if not keys:
                    raise EvidenceProviderError("signed_bundle resolution requires --verification-key-file")
                provider = SignedBundleEvidenceProvider(args.bundle, verification_keys=keys)
            else:
                raise EvidenceProviderError(f"unsupported provider source_kind: {source_kind!r}")
            draft = load_draft(args.draft)
            claim = _find_claim(draft, args.claim_id)
            evidence_ref = {"id": args.evidence_id, "kind": args.expected_kind}
            request = build_evidence_request_from_draft(
                draft,
                claim,
                evidence_ref,
                provider_id=provider.provider_id,
                evaluation_time=args.evaluation_time,
            )
            resolution = provider.resolve(request)
            report = validate_evidence_resolution(
                request,
                resolution,
                policy,
                provider=provider,
                verification_keys=keys,
            ).as_dict()
            generated_validation = validate_evidence_validation_report(report)
            if not generated_validation.valid:
                print(
                    json.dumps({"error": "generated_evidence_validation_report_invalid", "checks": generated_validation.as_dict()["checks"]}, indent=2),
                    file=sys.stderr,
                )
                return 3
            if args.out_dir:
                out = Path(args.out_dir)
                write_evidence_artifact(out / "evidence_request.json", request)
                write_evidence_artifact(out / "evidence_resolution.json", resolution)
                write_evidence_artifact(out / "evidence_validation_report.json", report)
        except (EvidenceProviderError, OSError, ValueError) as exc:
            print(f"evidence resolution failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"evidence_validation: {report.get('overall_status')}")
            print(f"candidate_evidence_status: {report.get('candidate_evidence_status')}")
            print(f"evidence_id: {report.get('evidence_id')}")
            print(f"signature_status: {report.get('signature_status')}")
            print("trust_gate_promotion_allowed: false")
            for check in report.get("checks", []):
                if isinstance(check, Mapping) and check.get("status") != "passed":
                    print(f"[failed] {check.get('check')} expected={check.get('expected')} actual={check.get('actual')}")
            if args.out_dir:
                print(f"reports: {args.out_dir}")
        return 0 if report.get("accepted") is True else 2

    if args.command == "profile" and args.profile_command == "list":
        consumer_result: dict[str, Any] | None = None
        workflow_result: dict[str, Any] | None = None
        if args.kind in {"consumer", "all"}:
            registry = consumer_profile_registry()
            profiles = list_consumer_profiles()
            consumer_result = {
                "kind": "AiNIRConsumerProfileList",
                "version": "ainir.consumer-profile-list.v1",
                "registry_version": registry.get("version"),
                "profiles": list(profiles),
                "profile_manifest_contract": artifact_contract_manifest()["contracts"]["profile_manifest"]["identifier"],
            }
        if args.kind in {"workflow", "all"}:
            workflow_result = {
                "kind": "AiNIRWorkflowProfileList",
                "version": "ainir.workflow-profile-list.v1",
                "profiles": list(list_workflow_profile_manifests(args.root)),
                "bundled_profile_id": BUILTIN_PROFILE_ID,
                "production_runtime_ready": False,
            }
        result: dict[str, Any]
        if args.kind == "consumer":
            result = consumer_result or {}
        elif args.kind == "workflow":
            result = workflow_result or {}
        else:
            result = {
                "kind": "AiNIRProfileSurfaceList",
                "version": "ainir.profile-surface-list.v1",
                "consumer": consumer_result,
                "workflow": workflow_result,
                "production_runtime_ready": False,
            }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.kind == "consumer":
            for item in (consumer_result or {}).get("profiles", []):
                workflows = ", ".join(item.get("supported_workflows") or [])
                print(f"{item.get('id')} status={item.get('status')} workflows={workflows}")
        elif args.kind == "workflow":
            for item in (workflow_result or {}).get("profiles", []):
                print(f"{item.get('profile_id')} valid={item.get('valid')} manifest={item.get('manifest_path')}")
        else:
            for item in (consumer_result or {}).get("profiles", []):
                print(f"consumer {item.get('id')} status={item.get('status')}")
            for item in (workflow_result or {}).get("profiles", []):
                print(f"workflow {item.get('profile_id')} valid={item.get('valid')}")
        return 0

    if args.command == "profile" and args.profile_command == "init":
        try:
            created = initialize_profile(
                args.target,
                profile_id=args.profile_id,
                workflow_id=args.workflow_id,
                force=args.force,
            )
        except (ProfileManifestError, OSError) as exc:
            print(f"profile initialization failed: {exc}", file=sys.stderr)
            return 2
        print(f"profile_initialized: {Path(args.target).resolve()}")
        for path in created:
            print(f"created: {path}")
        print(f"next: ainir profile validate {created[0]}")
        print(f"next: ainir conformance run {created[0]}")
        return 0

    if args.command == "profile" and args.profile_command in {"validate", "inspect"}:
        try:
            with materialized_profile_source(args.source) as manifest:
                payload = (
                    validate_profile_manifest(manifest).as_dict()
                    if args.profile_command == "validate"
                    else inspect_profile_manifest(manifest)
                )
        except (ProfileManifestError, OSError, ValueError) as exc:
            print(f"profile {args.profile_command} failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.profile_command == "validate":
            print(f"profile_valid: {payload.get('valid')}")
            print(f"profile_id: {payload.get('profile_id')}")
            print(f"manifest: {payload.get('manifest_path')}")
            print(f"conformance_categories: {', '.join(payload.get('conformance_categories') or [])}")
            for issue in payload.get("issues", []):
                print(f"[{issue.get('severity')}] {issue.get('code')} :: {issue.get('path')} :: {issue.get('message')}")
        else:
            print(f"profile_id: {payload.get('profile_id')}")
            print(f"profile_version: {payload.get('profile_version')}")
            print(f"valid: {payload.get('valid')}")
            print(f"registry_mode: {payload.get('registry_mode')}")
            print(f"manifest_sha256: {payload.get('manifest_canonical_sha256')}")
            print(f"production_runtime_ready: {payload.get('production_runtime_ready')}")
        return 0 if payload.get("valid") else 2

    if args.command == "profile" and args.profile_command == "show":
        try:
            item = get_consumer_profile(args.profile_id)
        except UnknownConsumerProfileError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            print(f"profile_id: {item.get('id')}")
            print(f"display_name: {item.get('display_name')}")
            print(f"status: {item.get('status')}")
            print(f"supported_workflows: {', '.join(item.get('supported_workflows') or [])}")
            print(f"description: {str(item.get('description') or '').strip()}")
        return 0

    if args.command == "profile" and args.profile_command == "export-intent":
        from .verified_intent_export import export_verified_intent_packet
        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="verified_intent_export")
        result = export_verified_intent_packet(load_draft(args.draft), context, args.profile).as_dict()
        _write_verified_intent_bundle(Path(args.out_dir), result)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"verified_intent_export: {result['status']}")
            print(f"reports: {args.out_dir}")
            for reason in result.get("reasons", []):
                print(f"reason: {reason}")
        return 0 if result["status"] == "exported" else 2

    if args.command == "conformance":
        return _run_conformance(args, legacy_name)

    if args.command == "registry" and args.registry_command == "list":
        items = [registry_info(name).as_dict() for name in PUBLIC_REGISTRY_NAMES]
        result = {"kind": "AiNIRRegistryResourceList", "version": "1", "registries": items}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for item in items:
                print(f"{item['name']} size={item['size']} sha256={item['sha256']}")
        return 0

    if args.command == "registry" and args.registry_command == "show":
        try:
            text = read_registry_text(args.name)
        except UnknownPublicResourceError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.json:
            data = load_yaml_no_duplicate_keys(text)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(text, end="" if text.endswith("\n") else "\n")
        return 0

    if args.command == "registry" and args.registry_command == "snapshot":
        if args.profile is not None and not args.evolution:
            print("--profile requires --evolution", file=sys.stderr)
            return 2
        if args.parent_snapshot_hash is not None and not args.evolution:
            print("--parent-snapshot-hash requires --evolution", file=sys.stderr)
            return 2
        try:
            if args.evolution and args.profile is not None:
                with materialized_profile_source(args.profile) as manifest:
                    compiled = compile_profile(manifest)
                    with profile_registry_context(compiled):
                        snapshot = capture_registry_snapshot(
                            parent_snapshot_hash=args.parent_snapshot_hash,
                            profile_id=compiled.profile_id,
                        )
                failures: list[dict[str, Any]] = []
            elif args.evolution:
                snapshot = capture_registry_snapshot(
                    parent_snapshot_hash=args.parent_snapshot_hash,
                )
                failures = []
            else:
                snapshot = registry_snapshot()
                failures = registry_snapshot_failures(snapshot)
        except (RegistryEvolutionError, ProfileManifestError, OSError, ValueError) as exc:
            print(f"registry snapshot failed: {exc}", file=sys.stderr)
            return 2
        if args.out:
            target = Path(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            if args.evolution:
                write_registry_snapshot(target, snapshot)
            else:
                target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        elif args.evolution:
            print("registry_snapshot_valid: true")
            print(f"registry_snapshot_id: {snapshot.get('snapshot_id')}")
            print(f"registry_snapshot_sha256: {snapshot.get('snapshot_sha256')}")
            print(f"runtime_registry_snapshot_hash: {snapshot.get('runtime_registry_snapshot_hash')}")
            print(f"profile_id: {snapshot.get('profile_id')}")
            print("production_runtime_ready: false")
            if args.out:
                print(f"snapshot: {args.out}")
        else:
            print(f"registry_snapshot_valid: {not failures}")
            print(f"registry_snapshot_hash: {snapshot.get('combined_sha256')}")
            for failure in failures:
                print(f"[failed] {failure.get('name')} reason={failure.get('reason')}")
        return 0 if not failures else 2

    if args.command == "registry" and args.registry_command == "diff":
        try:
            report = diff_registry_snapshots(args.source, args.target).as_dict()
        except (RegistryEvolutionError, OSError, ValueError) as exc:
            print(f"registry diff failed: {exc}", file=sys.stderr)
            return 2
        if args.out:
            write_registry_diff(args.out, report)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"registry_diff: {report['overall_classification']}")
            print(f"changed: {report['changed']}")
            print(f"change_count: {report['change_count']}")
            print(f"diff_id: {report['diff_id']}")
            print(f"requires_explicit_migration: {report['requires_explicit_migration']}")
            if args.out:
                print(f"diff: {args.out}")
        return 0

    if args.command == "registry" and args.registry_command == "migration":
        if args.registry_migration_command == "create":
            try:
                record = create_registry_migration_record(
                    args.source,
                    args.target,
                    authorized_by=args.authorized_by,
                    reason=args.reason,
                    approve=args.approve,
                    evidence_ref=args.evidence_ref,
                )
                write_registry_migration_record(args.out, record)
            except (RegistryEvolutionError, OSError, ValueError) as exc:
                print(f"registry migration creation failed: {exc}", file=sys.stderr)
                return 2
            if args.json:
                print(json.dumps(record, indent=2, ensure_ascii=False))
            else:
                print(f"registry_migration_created: {record['migration_id']}")
                print(f"authorization_status: {record['authorization']['status']}")
                print(f"overall_classification: {record['overall_classification']}")
                print(f"cryptographic_signature_status: {record['cryptographic_signature_status']}")
                print("production_runtime_ready: false")
                print(f"record: {args.out}")
            return 0
        if args.registry_migration_command == "validate":
            try:
                record = load_registry_migration_record(args.record)
                validation = validate_registry_migration_record(
                    record,
                    args.source,
                    args.target,
                    require_approved=args.require_approved,
                ).as_dict()
                validation["migration_id"] = record.get("migration_id")
                validation["authorization_status"] = (
                    record.get("authorization", {}).get("status")
                    if isinstance(record.get("authorization"), dict)
                    else None
                )
                validation["cryptographic_signature_status"] = record.get("cryptographic_signature_status")
            except (RegistryEvolutionError, OSError, ValueError) as exc:
                print(f"registry migration validation failed: {exc}", file=sys.stderr)
                return 2
            if args.json:
                print(json.dumps(validation, indent=2, ensure_ascii=False))
            else:
                print(f"registry_migration_valid: {validation['overall_status'] == 'passed'}")
                print(f"overall_status: {validation['overall_status']}")
                for check in validation.get("checks", []):
                    if check.get("status") != "passed":
                        print(f"[failed] {check.get('check')} expected={check.get('expected')} actual={check.get('actual')}")
            return 0 if validation["overall_status"] == "passed" else 2

    if args.command == "contracts":
        manifest = artifact_contract_manifest()
        if args.json:
            print(json.dumps(manifest, indent=2, ensure_ascii=False))
        else:
            for name, item in manifest["contracts"].items():
                legacy = ",".join(item.get("legacy_versions") or []) or "none"
                print(f"{name}: {item['identifier']} status={item['status']} legacy={legacy}")
        return 0

    if args.command == "lower":
        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="lowering")
        draft = load_draft(args.draft)
        decision = evaluate_trust_gate(draft, context)
        if not decision.lowering_allowed:
            print(f"lowering refused by trust gate: status={decision.status}")
            if decision.failed_gates:
                print("failed_gates: " + ", ".join(decision.failed_gates))
            for finding in decision.findings:
                if finding.get("severity") == "critical":
                    print(f"[critical] {finding.get('rule')} :: {finding.get('target')}")
            return 2
        try:
            target = lower_to_typescript(draft, verify_draft(draft, context), args.out_dir, context)
        except RuntimeError as exc:
            print(f"lowering refused: {exc}")
            return 2
        print(f"lowered: {target}")
        return 0

    if args.command == "demo":
        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="demo")
        return _run_demo(Path(args.examples_dir), Path(args.out_dir), context)

    return 1


def _run_demo(examples_dir: Path, out_dir: Path, context: TrustedExecutionContext) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    draft_paths = list(iter_example_drafts(examples_dir))
    if not draft_paths:
        summary = {
            "overall_status": "failed",
            "reason": "No example draft files were found.",
            "examples_dir": str(examples_dir),
            "examples": [],
        }
        dump_yaml(summary, out_dir / "summary.yaml")
        print("AiNIR public demo: failed")
        print(f"reason: no example draft files found in {examples_dir}")
        print(f"reports: {out_dir}")
        return 2
    manifest = _load_demo_manifest(examples_dir)
    for path in draft_paths:
        draft = load_draft(path)
        report = verify_draft(draft, context)
        decision = evaluate_trust_gate(draft, context)
        example_name = path.parent.name
        expected_status = (manifest.get(example_name) or {}).get("expected_status") if manifest else None
        result = {"example": example_name, "expected_status": expected_status, **report.as_dict()}
        result["trust_gate"] = {
            "status": decision.status,
            "lowering_allowed": decision.lowering_allowed,
            "handoff_allowed": decision.handoff_allowed,
            "failed_gates": list(decision.failed_gates),
        }
        results.append(result)
        dump_yaml(report.as_dict(), out_dir / f"{example_name}.report.yaml")
        if report.status == "passed":
            if not decision.lowering_allowed:
                results[-1]["lowering_error"] = "trust_gate_lowering_not_allowed"
                results[-1]["status"] = "failed"
                results[-1]["critical_count"] = int(results[-1].get("critical_count", 0)) + 1
                results[-1]["findings"].append({
                    "rule": "T011.trust_gate_lowering_not_allowed",
                    "severity": "critical",
                    "target": "trust_gate.lowering_allowed",
                    "message": "Demo lowering is refused unless TrustGateDecision.lowering_allowed is true.",
                })
            else:
                try:
                    lower_to_typescript(draft, report, out_dir / "lowered", context)
                except RuntimeError as exc:
                    results[-1]["lowering_error"] = str(exc)
                    results[-1]["status"] = "failed"
                    results[-1]["critical_count"] = int(results[-1].get("critical_count", 0)) + 1
                    results[-1]["findings"].append({
                        "rule": "L001.lowering_refused",
                        "severity": "critical",
                        "target": "lowerer",
                        "message": str(exc),
                    })

    summary = {
        "overall_status": "passed" if all(_expected_ok(r) for r in results) else "failed",
        "trusted_context": {"environment": context.environment, "source": context.source, "purpose": context.purpose},
        "expected_status_source": "examples/demo_manifest.json" if manifest else "legacy_name_fallback",
        "examples": results,
    }
    dump_yaml(summary, out_dir / "summary.yaml")
    print(f"AiNIR public demo: {summary['overall_status']}")
    for r in results:
        print(f"- {r['example']}: {r['status']} ({r['critical_count']} critical)")
    print(f"reports: {out_dir}")
    return 0 if summary["overall_status"] == "passed" else 2


def _load_demo_manifest(examples_dir: Path) -> dict[str, dict[str, Any]]:
    manifest_path = examples_dir / "demo_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    examples = data.get("examples", {}) if isinstance(data, dict) else {}
    return examples if isinstance(examples, dict) else {}


def _expected_ok(result: dict[str, Any]) -> bool:
    expected = result.get("expected_status")
    if expected == "passed":
        return result["status"] == "passed"
    if expected == "blocked":
        return result["status"] == "blocked" and result["critical_count"] > 0
    # Legacy fallback for older extracted demos without a manifest.
    example = result["example"]
    if example.endswith("_safe"):
        return result["status"] == "passed"
    return result["status"] == "blocked" and result["critical_count"] > 0


def _print_report(report: dict[str, Any]) -> None:
    print(f"status: {report['status']}")
    print(f"module: {report['module_id']}")
    print(f"workflow: {report['workflow']}")
    for finding in report["findings"]:
        print(f"[{finding['severity']}] {finding['rule']} :: {finding['target']}")
        print(f"  {finding['message']}")
        if finding.get("suggestion"):
            print(f"  suggestion: {finding['suggestion']}")


if __name__ == "__main__":
    raise SystemExit(main())
