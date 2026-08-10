"""Release-readiness check for the bounded MCP tool-call profile."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import artifact_contract_manifest
from .mcp_conformance import run_bundled_mcp_conformance
from .mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    materialized_mcp_profile_source,
    validate_mcp_tool_call_profile,
)
from .registry_provenance import registry_snapshot

EXPECTED_P5_REGISTRY_HASH = "sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a"
_REQUIRED_CONTRACTS = {
    "mcp_tool_call_profile",
    "mcp_tool_call_envelope",
    "mcp_host_context",
    "mcp_tool_call_assessment",
    "mcp_tool_call_conformance_pack",
    "mcp_tool_call_conformance_report",
}


def _check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "passed" if passed else "failed", **details}


def run_mcp_tool_call_profile_check(out_dir: str | Path) -> dict[str, Any]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    with materialized_mcp_profile_source(BUILTIN_MCP_PROFILE_ID) as profile:
        validation = validate_mcp_tool_call_profile(profile).as_dict()
        checks.append(_check(
            "bundled_profile_valid",
            validation.get("overall_status") == "passed",
            profile_id=profile.profile_id,
            profile_sha256=profile.data.get("profile_sha256"),
        ))
        policies = profile.data.get("policies") if isinstance(profile.data.get("policies"), dict) else {}
        checks.append(_check(
            "profile_fail_closed_and_non_executing",
            policies.get("unknown_tool") == "refuse"
            and policies.get("tool_annotations_are_evidence") is False
            and policies.get("model_output_is_evidence") is False
            and policies.get("ainir_executes_actions") is False
            and profile.data.get("production_runtime_ready") is False,
            policies=policies,
        ))
        destructive = next((tool for tool in profile.data.get("tools", []) if tool.get("risk_class") == "destructive"), {})
        checks.append(_check(
            "destructive_tool_capped_at_review_required",
            destructive.get("decision_mode") == "review_required",
            tool=destructive.get("name"),
            decision_mode=destructive.get("decision_mode"),
        ))

    report = run_bundled_mcp_conformance(out_dir=output / "conformance")
    checks.append(_check(
        "bounded_conformance_26_cases",
        report.get("overall_status") == "passed"
        and report.get("case_count") == 26
        and report.get("passed") == 26
        and report.get("failed") == 0,
        case_count=report.get("case_count"),
        passed_cases=report.get("passed"),
        failed_cases=report.get("failed"),
    ))
    checks.append(_check(
        "conformance_never_executes_or_overrides_trust_gate",
        report.get("execution_performed") is False
        and report.get("trust_gate_override_allowed") is False
        and report.get("production_runtime_ready") is False,
        execution_performed=report.get("execution_performed"),
        trust_gate_override_allowed=report.get("trust_gate_override_allowed"),
    ))
    results = {item.get("case_id"): item for item in report.get("results", []) if isinstance(item, dict)}
    checks.append(_check(
        "authorization_consent_scope_and_transaction_refusals_present",
        all(results.get(case_id, {}).get("passed") is True for case_id in (
            "wrong_audience_refused",
            "missing_consent_refused",
            "expired_consent_refused",
            "capability_widening_refused",
            "path_traversal_refused",
            "absolute_path_refused",
            "windows_ads_path_refused",
            "windows_reserved_device_path_refused",
            "control_character_path_refused",
            "missing_transaction_refused",
            "missing_rollback_refused",
        )),
    ))
    checks.append(_check(
        "credentials_and_untrusted_annotations_refused",
        all(results.get(case_id, {}).get("passed") is True for case_id in (
            "credential_argument_refused",
            "credential_meta_refused",
            "credential_value_in_content_refused",
            "annotation_understates_write_refused",
        )),
    ))
    checks.append(_check(
        "task_and_multi_round_input_not_claimed",
        results.get("task_requested_refused", {}).get("passed") is True
        and results.get("mrtr_present_refused", {}).get("passed") is True,
    ))
    contracts = artifact_contract_manifest().get("contracts", {})
    checks.append(_check(
        "six_public_mcp_artifact_contracts_present",
        _REQUIRED_CONTRACTS.issubset(set(contracts)),
        missing=sorted(_REQUIRED_CONTRACTS - set(contracts)),
    ))
    current_hash = registry_snapshot().get("combined_sha256")
    checks.append(_check(
        "p5_registry_hash_preserved",
        current_hash == EXPECTED_P5_REGISTRY_HASH,
        expected=EXPECTED_P5_REGISTRY_HASH,
        actual=current_hash,
    ))
    failed = [item for item in checks if item["status"] != "passed"]
    payload = {
        "kind": "AiNIRMCPToolCallProfileReadinessReport",
        "version": "ainir.mcp-tool-call-profile-readiness-report.v1",
        "overall_status": "passed" if not failed else "failed",
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "case_count": report.get("case_count"),
        "conformance_report_sha256": report.get("report_sha256"),
        "execution_performed": False,
        "network_access_used": False,
        "trust_gate_override_enabled": False,
        "evidence_ledger_promotion_enabled": False,
        "production_runtime_ready": False,
        "checks": checks,
        "output_dir": str(output.resolve()),
    }
    (output / "mcp_tool_call_profile_readiness_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


__all__ = ["EXPECTED_P5_REGISTRY_HASH", "run_mcp_tool_call_profile_check"]
