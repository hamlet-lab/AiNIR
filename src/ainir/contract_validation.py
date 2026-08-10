"""Supported runtime validation for AiNIR public artifact contracts.

These validators complement the published JSON Schemas with cross-field checks.
They intentionally remain dependency-free and conservative.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from .contracts import (
    LEGACY_TRUST_GATE_DECISION_VERSION,
    LEGACY_TRUST_RECEIPT_VERSION,
    PROFILE_MANIFEST_CONTRACT,
    PROFILE_MANIFEST_KIND,
    SUPPORTED_TRUST_GATE_DECISION_VERSIONS,
    SUPPORTED_TRUST_RECEIPT_VERSIONS,
    TRUST_GATE_DECISION_KIND,
    TRUST_RECEIPT_KIND,
    TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_KIND,
)
from .execution_context import allowed_environments

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_PUBLIC_REPLAY_REPORT_FIELDS = frozenset({
    "kind", "version", "overall_status", "replay_mode", "receipt_id",
    "historical_status", "evaluated_status", "historical_registry_snapshot_hash",
    "evaluated_registry_snapshot_hash", "decision_changed",
    "historical_receipt_unchanged", "registry_diff_status", "checks",
    "fresh_decision", "receipt", "registry_diff", "migration",
    "production_runtime_ready",
})


def _failure(name: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"check": name, "status": "failed", "expected": expected, "actual": actual}


def validate_trust_receipt(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return failed semantic checks for stable or legacy TrustReceipts."""

    checks: list[dict[str, Any]] = []
    receipt_id = receipt.get("receipt_id")
    normalized_id = str(receipt_id or "").replace("ainir.trust.receipt.", "receipt.")
    if not isinstance(receipt_id, str) or not _SAFE_TOKEN_RE.fullmatch(normalized_id):
        checks.append(_failure("receipt_schema_valid.receipt_id", "safe receipt id string", receipt_id))
    if receipt.get("receipt_kind") != TRUST_RECEIPT_KIND:
        checks.append(_failure("receipt_schema_valid.receipt_kind", TRUST_RECEIPT_KIND, receipt.get("receipt_kind")))
    version = receipt.get("version")
    if version not in SUPPORTED_TRUST_RECEIPT_VERSIONS:
        checks.append(_failure("receipt_schema_valid.version", sorted(SUPPORTED_TRUST_RECEIPT_VERSIONS), version))
    if version != LEGACY_TRUST_RECEIPT_VERSION:
        legacy = receipt.get("legacy_version")
        if legacy != LEGACY_TRUST_RECEIPT_VERSION:
            checks.append(_failure("receipt_schema_valid.legacy_version", LEGACY_TRUST_RECEIPT_VERSION, legacy))
    if receipt.get("status") not in {"passed", "refused", "invalid"}:
        checks.append(_failure("receipt_schema_valid.status", "passed|refused|invalid", receipt.get("status")))
    context = receipt.get("trusted_context")
    if not isinstance(context, Mapping):
        checks.append(_failure("receipt_schema_valid.trusted_context", "object", type(context).__name__))
    else:
        environment = context.get("environment")
        if not isinstance(environment, str) or environment not in set(allowed_environments()):
            checks.append(_failure("receipt_schema_valid.trusted_context.environment", sorted(allowed_environments()), environment))
        for field in ("source", "purpose"):
            value = context.get(field)
            if not isinstance(value, str) or not _SAFE_TOKEN_RE.fullmatch(value):
                checks.append(_failure(f"receipt_schema_valid.trusted_context.{field}", "safe token", value))
    for field in (
        "raw_source_sha256",
        "canonical_draft_sha256",
        "draft_hash",
        "verifier_report_hash",
        "stable_receipt_projection_hash",
    ):
        value = receipt.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            checks.append(_failure(f"receipt_schema_valid.{field}", "sha256:<64 lowercase hex>", value))
    registry_hash = receipt.get("registry_snapshot_hash")
    if registry_hash is not None and (not isinstance(registry_hash, str) or not _SHA256_RE.fullmatch(registry_hash)):
        checks.append(_failure("receipt_schema_valid.registry_snapshot_hash", "sha256:<64 lowercase hex>", registry_hash))
    packet_hash = receipt.get("verified_intent_packet_canonical_sha256")
    if packet_hash is not None:
        if not isinstance(packet_hash, str) or not _SHA256_RE.fullmatch(packet_hash):
            checks.append(_failure("receipt_schema_valid.verified_intent_packet_canonical_sha256", "sha256:<64 lowercase hex>", packet_hash))
        if receipt.get("verified_intent_packet_hash_algorithm") != "canonical_json_sha256":
            checks.append(_failure("receipt_schema_valid.verified_intent_packet_hash_algorithm", "canonical_json_sha256", receipt.get("verified_intent_packet_hash_algorithm")))
    if not isinstance(receipt.get("gate_results"), Mapping):
        checks.append(_failure("receipt_schema_valid.gate_results", "object", type(receipt.get("gate_results")).__name__))
    if not isinstance(receipt.get("evidence_summary"), Mapping):
        checks.append(_failure("receipt_schema_valid.evidence_summary", "object", type(receipt.get("evidence_summary")).__name__))
    return checks


def validate_trust_gate_decision(decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if decision.get("kind") != TRUST_GATE_DECISION_KIND:
        checks.append(_failure("decision_schema_valid.kind", TRUST_GATE_DECISION_KIND, decision.get("kind")))
    version = decision.get("version")
    if version not in SUPPORTED_TRUST_GATE_DECISION_VERSIONS:
        checks.append(_failure("decision_schema_valid.version", sorted(SUPPORTED_TRUST_GATE_DECISION_VERSIONS), version))
    if version != LEGACY_TRUST_GATE_DECISION_VERSION and decision.get("legacy_version") != LEGACY_TRUST_GATE_DECISION_VERSION:
        checks.append(_failure("decision_schema_valid.legacy_version", LEGACY_TRUST_GATE_DECISION_VERSION, decision.get("legacy_version")))
    status = decision.get("status")
    if status not in {"passed", "refused", "invalid", "hold"}:
        checks.append(_failure("decision_schema_valid.status", "passed|refused|invalid|hold", status))
    if status != "passed" and decision.get("lowering_allowed") is True:
        checks.append(_failure("decision_semantics.lowering_allowed", False, True))
    receipt = decision.get("receipt")
    if not isinstance(receipt, Mapping):
        checks.append(_failure("decision_schema_valid.receipt", "object", type(receipt).__name__))
    else:
        checks.extend(validate_trust_receipt(receipt))
        if receipt.get("status") != status:
            checks.append(_failure("decision_semantics.receipt_status", status, receipt.get("status")))
    return checks


def validate_replay_report(report: Mapping[str, Any], *, require_public_contract: bool = False) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if require_public_contract:
        if report.get("kind") != TRUST_RECEIPT_REPLAY_REPORT_KIND:
            checks.append(_failure("replay_report_schema_valid.kind", TRUST_RECEIPT_REPLAY_REPORT_KIND, report.get("kind")))
        if report.get("version") != TRUST_RECEIPT_REPLAY_REPORT_CONTRACT:
            checks.append(_failure("replay_report_schema_valid.version", TRUST_RECEIPT_REPLAY_REPORT_CONTRACT, report.get("version")))
    if report.get("overall_status") not in {"passed", "failed"}:
        checks.append(_failure("replay_report_schema_valid.overall_status", "passed|failed", report.get("overall_status")))
    report_checks = report.get("checks")
    if not isinstance(report_checks, list):
        checks.append(_failure("replay_report_schema_valid.checks", "array", type(report_checks).__name__))
    else:
        for index, item in enumerate(report_checks):
            if not isinstance(item, Mapping):
                checks.append(_failure(f"replay_report_schema_valid.checks[{index}]", "object", type(item).__name__))
                continue
            if not isinstance(item.get("check"), str) or not item.get("check"):
                checks.append(_failure(f"replay_report_schema_valid.checks[{index}].check", "non-empty string", item.get("check")))
            if item.get("status") not in {"passed", "failed"}:
                checks.append(_failure(f"replay_report_schema_valid.checks[{index}].status", "passed|failed", item.get("status")))
    replay_mode = report.get("replay_mode")
    if require_public_contract or replay_mode is not None:
        unknown_fields = sorted(set(report) - _PUBLIC_REPLAY_REPORT_FIELDS)
        if unknown_fields:
            checks.append(_failure("replay_report_schema_valid.unknown_fields", [], unknown_fields))
        allowed_modes = {
            "exact_snapshot_replay",
            "current_registry_replay",
            "migrated_registry_replay",
        }
        if replay_mode not in allowed_modes:
            checks.append(_failure("replay_report_schema_valid.replay_mode", sorted(allowed_modes), replay_mode))
        if not isinstance(report.get("historical_receipt_unchanged"), bool):
            checks.append(_failure(
                "replay_report_schema_valid.historical_receipt_unchanged",
                "boolean",
                type(report.get("historical_receipt_unchanged")).__name__,
            ))
        decision_changed = report.get("decision_changed")
        if decision_changed is not None and not isinstance(decision_changed, bool):
            checks.append(_failure("replay_report_schema_valid.decision_changed", "boolean|null", decision_changed))
        for field in ("historical_status", "evaluated_status"):
            value = report.get(field)
            if value is not None and value not in {"passed", "refused", "invalid", "hold"}:
                checks.append(_failure(f"replay_report_schema_valid.{field}", "passed|refused|invalid|hold|null", value))
        if isinstance(report_checks, list):
            failed_report_checks = [
                item.get("check")
                for item in report_checks
                if isinstance(item, Mapping) and item.get("status") == "failed"
            ]
            if report.get("overall_status") == "passed" and failed_report_checks:
                checks.append(_failure("replay_report_semantics.passed_has_no_failed_checks", [], failed_report_checks))
            if report.get("overall_status") == "failed" and not failed_report_checks:
                checks.append(_failure("replay_report_semantics.failed_has_failed_check", "at least one failed check", failed_report_checks))
        if replay_mode == "migrated_registry_replay" and report.get("overall_status") == "passed":
            migration = report.get("migration")
            if not isinstance(migration, Mapping):
                checks.append(_failure("replay_report_semantics.migration", "object for passed migrated replay", type(migration).__name__))
            else:
                if migration.get("authorization_status") != "approved":
                    checks.append(_failure("replay_report_semantics.migration.authorization_status", "approved", migration.get("authorization_status")))
                if migration.get("cryptographic_signature_status") != "not_implemented":
                    checks.append(_failure(
                        "replay_report_semantics.migration.cryptographic_signature_status",
                        "not_implemented",
                        migration.get("cryptographic_signature_status"),
                    ))
                if migration.get("unsigned_local_approval_accepted") is not True:
                    checks.append(_failure(
                        "replay_report_semantics.migration.unsigned_local_approval_accepted",
                        True,
                        migration.get("unsigned_local_approval_accepted"),
                    ))
        for field in ("historical_registry_snapshot_hash", "evaluated_registry_snapshot_hash"):
            value = report.get(field)
            if value is not None and (not isinstance(value, str) or not _SHA256_RE.fullmatch(value)):
                checks.append(_failure(f"replay_report_schema_valid.{field}", "sha256:<64 lowercase hex>|null", value))
        diff_statuses = {"not_applicable", "unavailable", "identity_by_bound_hash", "available", "failed"}
        if report.get("registry_diff_status") not in diff_statuses:
            checks.append(_failure("replay_report_schema_valid.registry_diff_status", sorted(diff_statuses), report.get("registry_diff_status")))
        if report.get("registry_diff") is not None and not isinstance(report.get("registry_diff"), Mapping):
            checks.append(_failure("replay_report_schema_valid.registry_diff", "object|null", type(report.get("registry_diff")).__name__))
        if report.get("migration") is not None and not isinstance(report.get("migration"), Mapping):
            checks.append(_failure("replay_report_schema_valid.migration", "object|null", type(report.get("migration")).__name__))
        if report.get("registry_diff_status") in {"available", "identity_by_bound_hash"} and not isinstance(report.get("registry_diff"), Mapping):
            checks.append(_failure(
                "replay_report_semantics.registry_diff_available",
                "object",
                type(report.get("registry_diff")).__name__,
            ))
        if replay_mode == "exact_snapshot_replay":
            if report.get("registry_diff_status") != "not_applicable":
                checks.append(_failure("replay_report_semantics.exact.registry_diff_status", "not_applicable", report.get("registry_diff_status")))
            if report.get("registry_diff") is not None:
                checks.append(_failure("replay_report_semantics.exact.registry_diff", None, type(report.get("registry_diff")).__name__))
            if report.get("migration") is not None:
                checks.append(_failure("replay_report_semantics.exact.migration", None, type(report.get("migration")).__name__))
        if replay_mode == "current_registry_replay" and report.get("migration") is not None:
            checks.append(_failure("replay_report_semantics.current.migration", None, type(report.get("migration")).__name__))
        if report.get("production_runtime_ready") is not False:
            checks.append(_failure("replay_report_schema_valid.production_runtime_ready", False, report.get("production_runtime_ready")))
        if report.get("overall_status") == "passed" and report.get("historical_receipt_unchanged") is not True:
            checks.append(_failure("replay_report_semantics.historical_receipt_unchanged", True, report.get("historical_receipt_unchanged")))
    return checks


def validate_profile_manifest(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate profile-manifest identity and portable metadata fields.

    Path-aware authoring, conformance-pack, coverage, and collision validation
    is provided by :mod:`ainir.profile_manifest` and
    :mod:`ainir.profile_runtime`. This mapping-level compatibility function is
    retained for callers that only have an already-decoded artifact.
    """

    checks: list[dict[str, Any]] = []
    if manifest.get("kind") != PROFILE_MANIFEST_KIND:
        checks.append(_failure("profile_manifest_schema_valid.kind", PROFILE_MANIFEST_KIND, manifest.get("kind")))
    if manifest.get("version") != PROFILE_MANIFEST_CONTRACT:
        checks.append(_failure("profile_manifest_schema_valid.version", PROFILE_MANIFEST_CONTRACT, manifest.get("version")))
    for field in ("profile_id", "profile_version"):
        value = manifest.get(field)
        if not isinstance(value, str) or not _SAFE_TOKEN_RE.fullmatch(value):
            checks.append(_failure(f"profile_manifest_schema_valid.{field}", "safe token", value))
    return checks


__all__ = [
    "validate_profile_manifest",
    "validate_replay_report",
    "validate_trust_gate_decision",
    "validate_trust_receipt",
]
