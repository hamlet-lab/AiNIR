from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._version import __release_tag__, __version__
from .core import load_yaml_no_duplicate_keys
from .temp_paths import ainir_temp_str
from .phase26_private_trial import _is_local_temp_rel, _is_within, _safe_trial_temp_parent, run_phase26_private_trial
from .phase25_verified_intent_contract_eval import run_phase25_verified_intent_contract_eval
from .conformance_runner import run_profile_conformance
from .profile_manifest import BUILTIN_PROFILE_ID, materialized_profile_source, validate_profile_manifest
from .contracts import TRUST_RECEIPT_CONTRACT
from .execution_context import TrustedExecutionContext
from .registry_evolution import (
    capture_registry_snapshot,
    create_registry_migration_record,
    diff_registry_snapshots,
    validate_registry_diff,
    validate_registry_migration_record,
    validate_registry_snapshot,
    write_registry_diff,
    write_registry_migration_record,
    write_registry_snapshot,
)
from .registry_replay import (
    CURRENT_REGISTRY_REPLAY,
    EXACT_SNAPSHOT_REPLAY,
    MIGRATED_REGISTRY_REPLAY,
    replay_trust_receipt_mode,
)
from .trust_receipt_store import issue_trust_receipt
from .offline_evidence_provider_eval import run_offline_evidence_provider_check
from .mcp_tool_call_eval import run_mcp_tool_call_profile_check
from .openai_function_tool_eval import run_openai_function_tool_adapter_check

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DOCS = [
    "docs/v1_rc_candidate.md",
    "docs/v1_rc_scope.md",
    "docs/v1_api_surface.md",
    "docs/v1_acceptance_criteria.md",
    "docs/v1_known_limitations.md",
    "docs/cli.md",
    "docs/artifact_contracts.md",
    "docs/legacy_cli_compatibility.md",
    "docs/profile_authoring.md",
    "docs/profile_conformance.md",
    "docs/trust_receipt_registry_evolution.md",
    "docs/offline_evidence_providers.md",
    "docs/mcp_tool_call_profile.md",
    "docs/mcp_profile_authoring.md",
    "docs/openai_function_tool_host_adapter.md",
    "release/v1_0_rc_candidate_manifest.yaml",
]

REQUIRED_README_PHRASES = [
    "Model output is a claim, not a fact.",
    "v1.0 RC candidate",
    "not a v1.0 final",
    "not a production runtime",
]


def _step(name: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, **extra}


def _static_docs_check() -> dict[str, Any]:
    missing = [rel for rel in REQUIRED_DOCS if not (ROOT / rel).exists()]
    return _step("v1_rc_docs_present", "passed" if not missing else "failed", missing=missing)


def _status_language_check() -> dict[str, Any]:
    text = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
    missing = [phrase for phrase in REQUIRED_README_PHRASES if phrase not in text]
    forbidden = []
    lower = text.lower()
    for phrase in ["production-ready", "v1.0 final release", "v1 final release"]:
        idx = lower.find(phrase)
        if idx != -1:
            context = lower[max(0, idx - 80):idx]
            if "not" not in context:
                forbidden.append(phrase)
    return _step("v1_rc_status_language", "passed" if not missing and not forbidden else "failed", missing=missing, forbidden=forbidden)


def _manifest_check() -> dict[str, Any]:
    path = ROOT / "release/v1_0_rc_candidate_manifest.yaml"
    if not path.exists():
        return _step("v1_rc_manifest", "failed", missing=[str(path.relative_to(ROOT))])
    try:
        data = load_yaml_no_duplicate_keys(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return _step("v1_rc_manifest", "failed", errors=[f"manifest_parse_error:{type(exc).__name__}:{exc}"])
    errors: list[str] = []
    expected = {
        "status": "rc_candidate_2",
        "python_distribution_name": "ainir-public-demo",
        "python_distribution_version": __version__,
        "release_tag": __release_tag__,
        "npm_metadata_role": "private_typescript_compile_fixture",
        "not_v1_final": True,
        "production_runtime_ready": False,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            errors.append(f"{key}:expected={value!r}:actual={data.get(key)!r}")
    surfaces = data.get("frozen_public_surfaces")
    for required in ("TrustGateDecision", "TrustReceipt", "VerifiedIntentPacket"):
        if not isinstance(surfaces, list) or required not in surfaces:
            errors.append(f"missing_frozen_public_surface:{required}")
    p1 = data.get("p1_release_identity_and_distributable_contracts")
    if not isinstance(p1, dict) or not all(value is True for value in p1.values()):
        errors.append("p1_release_identity_and_distributable_contracts:not_all_true")
    p2 = data.get("p2_stable_cli_and_artifact_contracts")
    if not isinstance(p2, dict) or not all(value is True for value in p2.values()):
        errors.append("p2_stable_cli_and_artifact_contracts:not_all_true")
    p3 = data.get("p3_profile_sdk_and_conformance")
    required_p3 = {
        "profile_manifest_v1_implemented",
        "conformance_pack_v1_implemented",
        "conformance_report_v1_implemented",
        "bundled_public_demo_profile",
        "additive_profile_scaffold",
        "context_local_registry_bundle",
        "protected_registry_collision_refusal",
        "fail_closed_profile_policies",
        "standalone_conformance_runner",
        "console_json_jsonl_junit_yaml_reports",
        "existing_public_registry_hash_preserved",
        "existing_receipt_projection_preserved",
        "reviewed_exact_effect_capability_vocabulary_only",
        "taxonomy_alias_and_external_allowlist_refusal",
        "broad_family_and_capability_prefix_refusal",
        "safety_critical_operation_alias_refusal",
        "non_vacuous_conformance_expectations",
        "additive_legacy_source_adapter_refusal",
    }
    if not isinstance(p3, dict) or not required_p3.issubset(p3) or not all(value is True for value in p3.values()):
        errors.append("p3_profile_sdk_and_conformance:missing_or_not_all_true")
    p4 = data.get("p4_registry_evolution_and_replay")
    required_p4 = {
        "registry_snapshot_v1_implemented",
        "registry_diff_v1_implemented",
        "registry_migration_record_v1_implemented",
        "legacy_registry_snapshot_cli_preserved",
        "portable_snapshot_component_hash_binding",
        "semantic_change_classification",
        "unknown_change_fail_conservative",
        "exact_snapshot_replay_preserved",
        "current_registry_replay_implemented",
        "migrated_registry_replay_implemented",
        "historical_receipt_never_rewritten",
        "migration_requires_approved_record",
        "unsigned_local_approval_requires_explicit_opt_in",
        "target_registry_full_trust_gate_reevaluation",
        "source_snapshot_receipt_binding",
        "registry_snapshot_sidecar_on_stable_receipt_issue",
        "p3_registry_hash_preserved",
        "production_runtime_ready_false",
    }
    if not isinstance(p4, dict) or not required_p4.issubset(p4) or not all(value is True for value in p4.values()):
        errors.append("p4_registry_evolution_and_replay:missing_or_not_all_true")
    p5 = data.get("p5_offline_evidence_providers")
    required_p5 = {
        "evidence_request_v1_implemented",
        "evidence_record_v1_implemented",
        "evidence_provider_policy_v1_implemented",
        "evidence_bundle_v1_implemented",
        "evidence_resolution_v1_implemented",
        "evidence_validation_report_v1_implemented",
        "fixture_provider_implemented",
        "root_confined_file_provider_implemented",
        "signed_bundle_provider_implemented",
        "exact_signature_key_policy_binding",
        "provider_signature_and_bundle_claims_independently_recomputed",
        "resolution_record_bound_to_unique_bundle_member",
        "revocation_freshness_window_enforced",
        "issuer_claim_subject_validity_revocation_revalidated",
        "provider_output_not_self_trusting",
        "validated_candidate_not_auto_promoted",
        "network_access_not_used",
        "production_runtime_ready_false",
    }
    if not isinstance(p5, dict) or not required_p5.issubset(p5) or not all(value is True for value in p5.values()):
        errors.append("p5_offline_evidence_providers:missing_or_not_all_true")
    p6 = data.get("p6_mcp_tool_call_profile")
    required_p6 = {
        "mcp_tool_call_profile_v1_implemented",
        "mcp_tool_call_envelope_v1_implemented",
        "mcp_host_context_v1_implemented",
        "mcp_tool_call_assessment_v1_implemented",
        "mcp_conformance_pack_and_report_v1_implemented",
        "host_owned_reference_adapter_non_executing",
        "tool_descriptions_and_annotations_not_evidence",
        "exact_descriptor_schema_effect_capability_binding",
        "audience_bound_authorization_metadata",
        "credential_like_arguments_metadata_and_values_refused",
        "resource_path_traversal_absolute_and_cross_platform_ambiguity_refused",
        "explicit_per_call_consent_bound_to_arguments_and_resources",
        "transaction_and_rollback_requirements_enforced",
        "destructive_calls_capped_at_review_required",
        "task_and_multi_round_input_not_claimed",
        "twenty_six_case_conformance_pack",
        "content_addressed_mcp_ids_and_nested_bindings",
        "non_passed_assessments_do_not_instruct_execution",
        "p5_registry_hash_preserved",
        "network_access_not_used",
        "trust_gate_override_not_allowed",
        "evidence_ledger_promotion_not_allowed",
        "production_runtime_ready_false",
    }
    if not isinstance(p6, dict) or not required_p6.issubset(p6) or not all(value is True for value in p6.values()):
        errors.append("p6_mcp_tool_call_profile:missing_or_not_all_true")
    p7 = data.get("p7_openai_function_tool_adapter")
    required_p7 = {
        "external_mcp_profile_scaffold",
        "external_conformance_file_bound_fixtures",
        "external_scenario_shortcuts_refused",
        "openai_function_call_binding_v1_implemented",
        "openai_function_tool_preflight_v1_implemented",
        "strict_exact_reviewed_schema_binding",
        "completed_source_artifacts_required",
        "duplicate_nonfinite_oversized_arguments_refused",
        "credential_like_values_refused",
        "cross_artifact_substitution_refused",
        "no_openai_sdk_or_api_calls",
        "no_tool_output_submission",
        "no_mcp_transport_or_execution",
        "p6_registry_hash_preserved",
        "trust_gate_override_not_allowed",
        "evidence_ledger_promotion_not_allowed",
        "production_runtime_ready_false",
    }
    if not isinstance(p7, dict) or not required_p7.issubset(p7) or not all(value is True for value in p7.values()):
        errors.append("p7_openai_function_tool_adapter:missing_or_not_all_true")
    return _step(
        "v1_rc_manifest",
        "passed" if not errors else "failed",
        errors=errors,
        python_distribution_version=data.get("python_distribution_version"),
        release_tag=data.get("release_tag"),
    )



def _registry_snapshot_validity_check() -> dict[str, Any]:
    from .registry_provenance import registry_snapshot, registry_snapshot_failures
    snap = registry_snapshot()
    failures = registry_snapshot_failures(snap)
    return _step(
        "registry_snapshot_valid_and_copy_consistent",
        "passed" if not failures else "failed",
        failures=failures,
        registry_snapshot_hash=snap.get("combined_sha256"),
    )


def _profile_sdk_check(out_dir: str | Path) -> dict[str, Any]:
    print("[phase30] starting profile_sdk_and_conformance", flush=True)
    try:
        with materialized_profile_source(BUILTIN_PROFILE_ID) as manifest:
            validation = validate_profile_manifest(manifest)
            if not validation.valid:
                return _step(
                    "profile_sdk_and_conformance",
                    "failed",
                    validation=validation.as_dict(),
                )
            report = run_profile_conformance(manifest, out_dir=out_dir)
            payload = report.as_dict()
    except Exception as exc:  # pragma: no cover - defensive readiness wrapper
        return _step("profile_sdk_and_conformance", "failed", error=repr(exc))
    return _step(
        "profile_sdk_and_conformance",
        "passed" if payload.get("overall_status") == "passed" and payload.get("case_count") == 81 else "failed",
        profile_id=payload.get("profile_id"),
        case_count=payload.get("case_count"),
        passed_cases=payload.get("passed"),
        failed_cases=payload.get("failed"),
        registry_snapshot_hash=payload.get("registry_snapshot_hash"),
        output_dir=str(out_dir),
    )


def _registry_evolution_check(out_dir: str | Path) -> dict[str, Any]:
    print("[phase30] starting registry_evolution_and_replay", flush=True)
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    receipt_dir = output / "receipt"
    safe_draft = ROOT / "examples" / "create_user_outbox_safe" / "draft.yaml"
    try:
        legacy_hash = _legacy_registry_hash()
        source = capture_registry_snapshot()
        source_validation = validate_registry_snapshot(source)
        identity = diff_registry_snapshots(source, source).as_dict()
        diff_validation = validate_registry_diff(identity)
        migration = create_registry_migration_record(
            source,
            source,
            authorized_by="phase30.local-review",
            reason="Phase 30 identity migration replay validation.",
            approve=True,
        )
        migration_validation = validate_registry_migration_record(
            migration,
            source,
            source,
            require_approved=True,
        )
        issued = issue_trust_receipt(
            safe_draft,
            receipt_dir,
            TrustedExecutionContext.public_demo(),
            contract_version=TRUST_RECEIPT_CONTRACT,
        )
        receipt_path = Path(issued.receipt_path)
        before = receipt_path.read_bytes()
        exact = replay_trust_receipt_mode(
            receipt_path,
            safe_draft,
            TrustedExecutionContext.public_demo(),
            mode=EXACT_SNAPSHOT_REPLAY,
        )
        current = replay_trust_receipt_mode(
            receipt_path,
            safe_draft,
            TrustedExecutionContext.public_demo(),
            mode=CURRENT_REGISTRY_REPLAY,
            source_snapshot=source,
        )
        blocked = replay_trust_receipt_mode(
            receipt_path,
            safe_draft,
            TrustedExecutionContext.public_demo(),
            mode=MIGRATED_REGISTRY_REPLAY,
            source_snapshot=source,
            target_snapshot=source,
            migration_record=migration,
        )
        migrated = replay_trust_receipt_mode(
            receipt_path,
            safe_draft,
            TrustedExecutionContext.public_demo(),
            mode=MIGRATED_REGISTRY_REPLAY,
            source_snapshot=source,
            target_snapshot=source,
            migration_record=migration,
            allow_unsigned_local_approval=True,
        )
        unchanged = receipt_path.read_bytes() == before
        write_registry_snapshot(output / "registry_snapshot.json", source)
        write_registry_diff(output / "registry_diff.json", identity)
        write_registry_migration_record(output / "registry_migration_record.json", migration)
        for name, report in (
            ("exact_replay.json", exact),
            ("current_replay.json", current),
            ("blocked_unsigned_migrated_replay.json", blocked),
            ("accepted_unsigned_migrated_replay.json", migrated),
        ):
            (output / name).write_text(
                json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        passed = all((
            source_validation.valid,
            source.get("runtime_registry_snapshot_hash") == legacy_hash,
            identity.get("overall_classification") == "compatible",
            identity.get("change_count") == 0,
            diff_validation.valid,
            migration_validation.valid,
            exact.overall_status == "passed",
            current.overall_status == "passed",
            blocked.overall_status == "failed",
            migrated.overall_status == "passed",
            migrated.historical_receipt_unchanged,
            unchanged,
        ))
        return _step(
            "registry_evolution_and_replay",
            "passed" if passed else "failed",
            legacy_registry_snapshot_hash=legacy_hash,
            evolution_runtime_snapshot_hash=source.get("runtime_registry_snapshot_hash"),
            snapshot_id=source.get("snapshot_id"),
            diff_classification=identity.get("overall_classification"),
            exact_replay=exact.overall_status,
            current_replay=current.overall_status,
            unsigned_migrated_replay_without_opt_in=blocked.overall_status,
            unsigned_migrated_replay_with_opt_in=migrated.overall_status,
            historical_receipt_unchanged=unchanged,
            production_runtime_ready=False,
            output_dir=str(output),
        )
    except Exception as exc:  # pragma: no cover - defensive readiness wrapper
        return _step("registry_evolution_and_replay", "failed", error=repr(exc), output_dir=str(output))


def _legacy_registry_hash() -> str | None:
    from .registry_provenance import registry_snapshot

    return registry_snapshot().get("combined_sha256")


def _run_eval_function(name: str, fn, out_path: str) -> dict[str, Any]:
    print(f"[phase30] starting {name}", flush=True)
    try:
        result = fn(out_path)
    except Exception as exc:  # pragma: no cover - defensive readiness wrapper
        return _step(name, "failed", error=repr(exc))
    status = result.get("overall_status") or result.get("status") or "unknown"
    return _step(name, "passed" if status == "passed" else "failed", output_dir=out_path, summary_status=status)

def _run_command(name: str, cmd: list[str], timeout: int = 240) -> dict[str, Any]:
    print(f"[phase30] starting {name}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    return _step(
        name,
        "passed" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode,
        command=cmd,
        stdout_tail=(proc.stdout or "").strip()[-1200:],
        stderr_tail=(proc.stderr or "").strip()[-1200:],
    )



def _sanitize_phase30_out_dir(out_dir: Path) -> Path:
    try:
        resolved = out_dir.expanduser().resolve()
    except OSError:
        return out_dir
    if _is_within(resolved, ROOT) and _is_local_temp_rel(resolved.relative_to(ROOT)):
        target = (_safe_trial_temp_parent() / resolved.name).resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target
    return out_dir

def run_phase30_v1_rc_candidate_check(out_dir: str | Path, mode: str = "full") -> dict[str, Any]:
    out_dir = _sanitize_phase30_out_dir(Path(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    if mode not in {"quick-integrity", "full"}:
        raise ValueError("mode must be 'quick-integrity' or 'full'")

    steps: list[dict[str, Any]] = [
        _static_docs_check(),
        _status_language_check(),
        _manifest_check(),
        _registry_snapshot_validity_check(),
        _registry_evolution_check(out_dir / "registry_evolution_and_replay"),
        _run_eval_function(
            "offline_evidence_providers",
            run_offline_evidence_provider_check,
            str(out_dir / "offline_evidence_providers"),
        ),
        _run_eval_function(
            "mcp_tool_call_profile",
            run_mcp_tool_call_profile_check,
            str(out_dir / "mcp_tool_call_profile"),
        ),
        _run_eval_function(
            "openai_function_tool_adapter",
            run_openai_function_tool_adapter_check,
            str(out_dir / "openai_function_tool_adapter"),
        ),
        _profile_sdk_check(ainir_temp_str("ainir_phase30_profile_conformance")),
        _run_eval_function("phase25_verified_intent_contract", run_phase25_verified_intent_contract_eval, ainir_temp_str("ainir_phase30_phase25_verified_intent_contract")),
    ]
    if mode == "full":
        steps.append(_run_eval_function("phase26_private_trial", run_phase26_private_trial, ainir_temp_str("ainir_phase30_phase26_private_trial")))
    else:
        steps.append(_step("phase26_private_trial", "not_run", reason="quick-integrity mode skips the heavier private-trial simulation"))
    passed = sum(1 for s in steps if s["status"] == "passed")
    failed = [s for s in steps if s["status"] not in {"passed", "not_run"}]
    report = {
        "phase": "pre_v1_phase30_v1_0_rc_candidate",
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(out_dir),
        "overall_status": "passed" if not failed else "failed",
        "decision": ("v1_0_rc_candidate_ready_for_private_github_trial" if mode == "full" and not failed else "quick_integrity_passed_full_release_check_not_run" if mode == "quick-integrity" and not failed else "needs_fix_before_rc_candidate"),
        "steps_total": len(steps),
        "steps_passed": passed,
        "steps_failed": len(failed),
        "production_runtime_ready": False,
        "v1_final_ready": False,
        "human_external_review": "pending",
        "steps": steps,
    }
    (out_dir / "phase30_v1_rc_candidate_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# AiNIR Phase 30 v1.0 RC Candidate Check",
        "",
        f"overall_status: {report['overall_status']}",
        f"mode: {report['mode']}",
        f"decision: {report['decision']}",
        "",
        "This check confirms RC candidate scope, status language, manifest presence, registry-evolution/replay invariants, offline EvidenceProvider fail-closed behavior, bounded non-executing MCP tool-call preflight, external MCP profile authoring and completed OpenAI function-call host preflight, Phase 26 private-trial simulation, and Phase 25 VerifiedIntentPacket contract strictness.",
        "",
        "AiNIR remains not v1.0 final and not a production runtime.",
    ]
    for s in steps:
        lines.append(f"- {s['name']}: {s['status']}")
    (out_dir / "phase30_v1_rc_candidate_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return report
