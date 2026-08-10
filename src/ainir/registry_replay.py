"""Explicit exact, current-registry, and migrated TrustReceipt replay modes."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .canonical import sha256_bytes
from .contracts import (
    LEGACY_TRUST_RECEIPT_VERSION,
    TRUST_RECEIPT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_KIND,
)
from .core import load_draft
from .execution_context import TrustedExecutionContext
from .registry_context import active_registry_bundle, use_registry_bundle
from .registry_evolution import (
    RegistryEvolutionError,
    capture_registry_snapshot,
    diff_registry_snapshots,
    load_registry_migration_record,
    load_registry_snapshot,
    registry_bundle_from_snapshot,
    validate_registry_migration_record,
)
from .trust_gate import evaluate_trust_gate
from .trust_receipt_store import (
    _bundle_integrity_checks,
    _resolve_replay_source,
    replay_trust_receipt,
    verify_trust_receipt_artifact,
)

EXACT_SNAPSHOT_REPLAY = "exact_snapshot_replay"
CURRENT_REGISTRY_REPLAY = "current_registry_replay"
MIGRATED_REGISTRY_REPLAY = "migrated_registry_replay"
REPLAY_MODES = (
    EXACT_SNAPSHOT_REPLAY,
    CURRENT_REGISTRY_REPLAY,
    MIGRATED_REGISTRY_REPLAY,
)


@dataclass(frozen=True)
class RegistryReplayReport:
    overall_status: str
    replay_mode: str
    receipt_id: str | None
    historical_status: str | None
    evaluated_status: str | None
    historical_registry_snapshot_hash: str | None
    evaluated_registry_snapshot_hash: str | None
    decision_changed: bool | None
    historical_receipt_unchanged: bool
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fresh_decision: Mapping[str, Any] = field(default_factory=dict)
    receipt: Mapping[str, Any] = field(default_factory=dict)
    registry_diff: Mapping[str, Any] | None = None
    migration: Mapping[str, Any] | None = None
    registry_diff_status: str = "not_applicable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": TRUST_RECEIPT_REPLAY_REPORT_KIND,
            "version": TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
            "overall_status": self.overall_status,
            "replay_mode": self.replay_mode,
            "receipt_id": self.receipt_id,
            "historical_status": self.historical_status,
            "evaluated_status": self.evaluated_status,
            "historical_registry_snapshot_hash": self.historical_registry_snapshot_hash,
            "evaluated_registry_snapshot_hash": self.evaluated_registry_snapshot_hash,
            "decision_changed": self.decision_changed,
            "historical_receipt_unchanged": self.historical_receipt_unchanged,
            "registry_diff_status": self.registry_diff_status,
            "checks": [dict(check) for check in self.checks],
            "fresh_decision": dict(self.fresh_decision),
            "receipt": dict(self.receipt),
            "registry_diff": dict(self.registry_diff) if isinstance(self.registry_diff, Mapping) else None,
            "migration": dict(self.migration) if isinstance(self.migration, Mapping) else None,
            "production_runtime_ready": False,
        }


@dataclass(frozen=True)
class _PreparedReplay:
    receipt_path: Path
    receipt: Mapping[str, Any]
    source_path: Path
    replay_cwd: Path | None
    context: TrustedExecutionContext
    checks: tuple[dict[str, Any], ...]
    raw_before_sha256: str


def _check(name: str, passed: bool, expected: Any, actual: Any, **extra: Any) -> dict[str, Any]:
    return {
        "check": name,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        **extra,
    }


def _context_from_receipt(receipt: Mapping[str, Any]) -> TrustedExecutionContext:
    trusted = receipt.get("trusted_context")
    environment = "public_demo"
    source = "receipt_replay"
    purpose = "trust_receipt_replay"
    if isinstance(trusted, Mapping):
        if isinstance(trusted.get("environment"), str):
            environment = str(trusted["environment"])
        if isinstance(trusted.get("source"), str) and trusted.get("source"):
            source = str(trusted["source"])
        if isinstance(trusted.get("purpose"), str) and trusted.get("purpose"):
            purpose = str(trusted["purpose"])
    return TrustedExecutionContext.from_environment(environment, source=source, purpose=purpose)


def _prepare_replay(
    receipt_path: str | Path,
    draft_path: str | Path | None,
    context: TrustedExecutionContext | None,
) -> tuple[_PreparedReplay | None, RegistryReplayReport | None]:
    path = Path(receipt_path)
    try:
        raw_before = path.read_bytes()
    except OSError as exc:
        report = RegistryReplayReport(
            overall_status="failed",
            replay_mode=CURRENT_REGISTRY_REPLAY,
            receipt_id=None,
            historical_status=None,
            evaluated_status=None,
            historical_registry_snapshot_hash=None,
            evaluated_registry_snapshot_hash=None,
            decision_changed=None,
            historical_receipt_unchanged=False,
            checks=(_check("receipt_file_readable", False, "readable receipt file", type(exc).__name__, detail=str(exc)),),
        )
        return None, report
    validation = verify_trust_receipt_artifact(path)
    checks = [dict(check) for check in validation.checks]
    receipt = dict(validation.receipt)
    if validation.overall_status != "passed":
        return None, RegistryReplayReport(
            overall_status="failed",
            replay_mode=CURRENT_REGISTRY_REPLAY,
            receipt_id=validation.receipt_id,
            historical_status=receipt.get("status"),
            evaluated_status=None,
            historical_registry_snapshot_hash=receipt.get("registry_snapshot_hash"),
            evaluated_registry_snapshot_hash=None,
            decision_changed=None,
            historical_receipt_unchanged=True,
            checks=tuple(checks),
            receipt=receipt,
        )
    checks.extend(_bundle_integrity_checks(path, receipt))
    source = draft_path if draft_path is not None else receipt.get("draft_source_path")
    resolved, tried, replay_cwd = _resolve_replay_source(source, path)
    if resolved is None:
        checks.append(_check(
            "draft_source_exists",
            False,
            "existing explicit draft path or repo-relative receipt.draft_source_path",
            source,
            tried=tried,
        ))
        return None, RegistryReplayReport(
            overall_status="failed",
            replay_mode=CURRENT_REGISTRY_REPLAY,
            receipt_id=validation.receipt_id,
            historical_status=receipt.get("status"),
            evaluated_status=None,
            historical_registry_snapshot_hash=receipt.get("registry_snapshot_hash"),
            evaluated_registry_snapshot_hash=None,
            decision_changed=None,
            historical_receipt_unchanged=True,
            checks=tuple(checks),
            receipt=receipt,
        )
    return _PreparedReplay(
        receipt_path=path,
        receipt=receipt,
        source_path=resolved,
        replay_cwd=replay_cwd,
        context=context or _context_from_receipt(receipt),
        checks=tuple(checks),
        raw_before_sha256=sha256_bytes(raw_before),
    ), None


def _evaluate(prepared: _PreparedReplay) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    checks = [dict(check) for check in prepared.checks]
    old_cwd = Path.cwd()
    try:
        if prepared.replay_cwd is not None:
            os.chdir(prepared.replay_cwd)
        draft = load_draft(prepared.source_path)
        decision_object = evaluate_trust_gate(draft, prepared.context)
        if prepared.receipt.get("version") == TRUST_RECEIPT_CONTRACT:
            decision = decision_object.as_public_dict()
        elif prepared.receipt.get("version") == LEGACY_TRUST_RECEIPT_VERSION:
            decision = decision_object.as_dict()
        else:  # contract validation should have rejected this already
            raise ValueError(f"unsupported receipt version: {prepared.receipt.get('version')!r}")
    finally:
        if prepared.replay_cwd is not None:
            os.chdir(old_cwd)
    fresh_receipt = dict(decision.get("receipt", {}))
    historical = prepared.receipt
    immutable = (
        ("receipt_version", historical.get("version"), fresh_receipt.get("version")),
        ("receipt_legacy_version", historical.get("legacy_version"), fresh_receipt.get("legacy_version")),
        ("module_id", historical.get("module_id"), fresh_receipt.get("module_id")),
        ("workflow", historical.get("workflow"), fresh_receipt.get("workflow")),
        ("draft_hash", historical.get("draft_hash"), fresh_receipt.get("draft_hash")),
        ("canonical_draft_sha256", historical.get("canonical_draft_sha256"), fresh_receipt.get("canonical_draft_sha256")),
        ("raw_source_sha256", historical.get("raw_source_sha256"), fresh_receipt.get("raw_source_sha256")),
        ("trusted_environment", _nested(historical, "trusted_context", "environment"), _nested(fresh_receipt, "trusted_context", "environment")),
        ("trusted_context_source", _nested(historical, "trusted_context", "source"), _nested(fresh_receipt, "trusted_context", "source")),
        ("trusted_context_purpose", _nested(historical, "trusted_context", "purpose"), _nested(fresh_receipt, "trusted_context", "purpose")),
    )
    for name, expected, actual in immutable:
        checks.append(_check(name, expected == actual, expected, actual))
    return decision, fresh_receipt, checks


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _file_unchanged(prepared: _PreparedReplay) -> tuple[bool, str | None]:
    try:
        after = sha256_bytes(prepared.receipt_path.read_bytes())
    except OSError:
        return False, None
    return after == prepared.raw_before_sha256, after


def _decision_changed(historical: Mapping[str, Any], fresh: Mapping[str, Any]) -> bool:
    fields = (
        "status",
        "failed_gates",
        "warning_gates",
        "gate_results",
        "evidence_summary",
        "lowering_eligibility",
    )
    return any(historical.get(field) != fresh.get(field) for field in fields)


def _migration_summary(
    record: Mapping[str, Any],
    *,
    unsigned_local_approval_accepted: bool = False,
) -> dict[str, Any]:
    authorization = record.get("authorization") if isinstance(record.get("authorization"), Mapping) else {}
    return {
        "migration_id": record.get("migration_id"),
        "record_sha256": record.get("record_sha256"),
        "overall_classification": record.get("overall_classification"),
        "authorization_status": authorization.get("status"),
        "authorized_by": authorization.get("actor_id"),
        "cryptographic_signature_status": record.get("cryptographic_signature_status"),
        "unsigned_local_approval_accepted": unsigned_local_approval_accepted,
    }


def replay_trust_receipt_mode(
    receipt_path: str | Path,
    draft_path: str | Path | None = None,
    context: TrustedExecutionContext | None = None,
    *,
    mode: str = EXACT_SNAPSHOT_REPLAY,
    source_snapshot: str | Path | Mapping[str, Any] | None = None,
    target_snapshot: str | Path | Mapping[str, Any] | None = None,
    migration_record: str | Path | Mapping[str, Any] | None = None,
    allow_unsigned_local_approval: bool = False,
) -> RegistryReplayReport:
    """Replay without ever rewriting the historical receipt artifact."""

    if mode not in REPLAY_MODES:
        raise ValueError(f"unsupported replay mode: {mode!r}")
    if mode == EXACT_SNAPSHOT_REPLAY and (
        source_snapshot is not None
        or target_snapshot is not None
        or migration_record is not None
        or allow_unsigned_local_approval
    ):
        raise ValueError(
            "exact_snapshot_replay does not accept registry-evolution artifacts or unsigned-migration approval"
        )
    if mode == CURRENT_REGISTRY_REPLAY and (
        target_snapshot is not None
        or migration_record is not None
        or allow_unsigned_local_approval
    ):
        raise ValueError(
            "current_registry_replay accepts only an optional source_snapshot; target/migration arguments require migrated_registry_replay"
        )
    if mode == EXACT_SNAPSHOT_REPLAY:
        path = Path(receipt_path)
        try:
            before = sha256_bytes(path.read_bytes())
        except OSError:
            before = None
        exact = replay_trust_receipt(receipt_path, draft_path, context)
        try:
            after = sha256_bytes(path.read_bytes())
        except OSError:
            after = None
        unchanged = before is not None and before == after
        checks = [dict(check) for check in exact.checks]
        checks.append(_check("historical_receipt_unchanged", unchanged, before, after))
        fresh_receipt = exact.fresh_decision.get("receipt") if isinstance(exact.fresh_decision, Mapping) else {}
        if not isinstance(fresh_receipt, Mapping):
            fresh_receipt = {}
        overall = "passed" if exact.overall_status == "passed" and unchanged else "failed"
        return RegistryReplayReport(
            overall_status=overall,
            replay_mode=mode,
            receipt_id=exact.receipt_id,
            historical_status=exact.receipt.get("status"),
            evaluated_status=exact.fresh_decision.get("status") if isinstance(exact.fresh_decision, Mapping) else None,
            historical_registry_snapshot_hash=exact.receipt.get("registry_snapshot_hash"),
            evaluated_registry_snapshot_hash=fresh_receipt.get("registry_snapshot_hash"),
            decision_changed=_decision_changed(exact.receipt, fresh_receipt) if fresh_receipt else None,
            historical_receipt_unchanged=unchanged,
            checks=tuple(checks),
            fresh_decision=exact.fresh_decision,
            receipt=exact.receipt,
            registry_diff_status="not_applicable",
        )

    prepared, early = _prepare_replay(receipt_path, draft_path, context)
    if prepared is None:
        assert early is not None
        return RegistryReplayReport(**{**early.__dict__, "replay_mode": mode})

    source_artifact: dict[str, Any] | None = None
    target_artifact: dict[str, Any] | None = None
    migration: dict[str, Any] | None = None
    unsigned_local_approval_accepted = False
    pre_checks = [dict(check) for check in prepared.checks]

    try:
        if source_snapshot is not None:
            source_artifact = load_registry_snapshot(source_snapshot)
            matches = source_artifact["runtime_registry_snapshot_hash"] == prepared.receipt.get("registry_snapshot_hash")
            pre_checks.append(_check(
                "source_snapshot_matches_historical_receipt",
                matches,
                prepared.receipt.get("registry_snapshot_hash"),
                source_artifact["runtime_registry_snapshot_hash"],
            ))
        if mode == MIGRATED_REGISTRY_REPLAY:
            if source_artifact is None or target_snapshot is None or migration_record is None:
                missing = [
                    name
                    for name, value in (
                        ("source_snapshot", source_artifact),
                        ("target_snapshot", target_snapshot),
                        ("migration_record", migration_record),
                    )
                    if value is None
                ]
                pre_checks.append(_check("migrated_replay_required_artifacts", False, [], missing))
                raise RegistryEvolutionError("migrated replay requires source snapshot, target snapshot, and migration record")
            target_artifact = load_registry_snapshot(target_snapshot)
            migration = load_registry_migration_record(migration_record)
            migration_validation = validate_registry_migration_record(
                migration,
                source_artifact,
                target_artifact,
                require_approved=True,
            )
            pre_checks.extend(dict(check) for check in migration_validation.checks)
            if not migration_validation.valid:
                raise RegistryEvolutionError("registry migration record is not approved and valid")
            signature_status = migration.get("cryptographic_signature_status")
            local_approval_allowed = (
                signature_status == "not_implemented" and allow_unsigned_local_approval
            )
            unsigned_local_approval_accepted = local_approval_allowed
            pre_checks.append(_check(
                "migration_unsigned_local_approval_explicitly_accepted",
                local_approval_allowed,
                True,
                local_approval_allowed,
                cryptographic_signature_status=signature_status,
            ))
            if not local_approval_allowed:
                raise RegistryEvolutionError(
                    "migrated replay is fail-closed because cryptographic signatures are not implemented; "
                    "the caller must explicitly accept unsigned local approval"
                )
    except RegistryEvolutionError as exc:
        unchanged, after = _file_unchanged(prepared)
        pre_checks.append(_check("registry_evolution_artifacts_valid", False, "valid replay artifacts", type(exc).__name__, detail=str(exc)))
        pre_checks.append(_check("historical_receipt_unchanged", unchanged, prepared.raw_before_sha256, after))
        return RegistryReplayReport(
            overall_status="failed",
            replay_mode=mode,
            receipt_id=prepared.receipt.get("receipt_id"),
            historical_status=prepared.receipt.get("status"),
            evaluated_status=None,
            historical_registry_snapshot_hash=prepared.receipt.get("registry_snapshot_hash"),
            evaluated_registry_snapshot_hash=None,
            decision_changed=None,
            historical_receipt_unchanged=unchanged,
            checks=tuple(pre_checks),
            receipt=prepared.receipt,
            migration=_migration_summary(migration, unsigned_local_approval_accepted=unsigned_local_approval_accepted) if migration else None,
            registry_diff_status="failed",
        )

    try:
        if mode == MIGRATED_REGISTRY_REPLAY:
            assert target_artifact is not None
            if active_registry_bundle() is not None:
                raise RegistryEvolutionError("migrated replay cannot replace an already active registry context")
            # Evolution snapshots are portable and do not carry repository
            # files. Evidence records remain bound to the replayed draft hash;
            # do not invent a checkout root that may not exist in a wheel.
            bundle = registry_bundle_from_snapshot(target_artifact, evidence_root=None)
            with use_registry_bundle(bundle):
                decision, fresh_receipt, checks = _evaluate(
                    _PreparedReplay(
                        **{**prepared.__dict__, "checks": tuple(pre_checks)}
                    )
                )
                evaluated_snapshot = capture_registry_snapshot(
                    parent_snapshot_hash=source_artifact["snapshot_sha256"] if source_artifact else None
                )
        else:
            decision, fresh_receipt, checks = _evaluate(
                _PreparedReplay(**{**prepared.__dict__, "checks": tuple(pre_checks)})
            )
            evaluated_snapshot = capture_registry_snapshot(
                parent_snapshot_hash=source_artifact["snapshot_sha256"] if source_artifact else None
            )
    except Exception as exc:
        unchanged, after = _file_unchanged(prepared)
        checks = [*pre_checks, _check("replay_evaluation_completed", False, "Trust Gate evaluation", type(exc).__name__, detail=str(exc))]
        checks.append(_check("historical_receipt_unchanged", unchanged, prepared.raw_before_sha256, after))
        return RegistryReplayReport(
            overall_status="failed",
            replay_mode=mode,
            receipt_id=prepared.receipt.get("receipt_id"),
            historical_status=prepared.receipt.get("status"),
            evaluated_status=None,
            historical_registry_snapshot_hash=prepared.receipt.get("registry_snapshot_hash"),
            evaluated_registry_snapshot_hash=None,
            decision_changed=None,
            historical_receipt_unchanged=unchanged,
            checks=tuple(checks),
            receipt=prepared.receipt,
            migration=_migration_summary(migration, unsigned_local_approval_accepted=unsigned_local_approval_accepted) if migration else None,
            registry_diff_status="failed",
        )

    expected_target_hash = (
        target_artifact["runtime_registry_snapshot_hash"]
        if target_artifact is not None
        else evaluated_snapshot["runtime_registry_snapshot_hash"]
    )
    checks.append(_check(
        "evaluated_registry_snapshot_matches_target",
        fresh_receipt.get("registry_snapshot_hash") == expected_target_hash,
        expected_target_hash,
        fresh_receipt.get("registry_snapshot_hash"),
    ))
    registry_diff: dict[str, Any] | None = None
    diff_status = "unavailable"
    if source_artifact is not None:
        diff_target = target_artifact or evaluated_snapshot
        registry_diff = diff_registry_snapshots(source_artifact, diff_target).as_dict()
        diff_status = "available"
    elif evaluated_snapshot["runtime_registry_snapshot_hash"] == prepared.receipt.get("registry_snapshot_hash"):
        registry_diff = diff_registry_snapshots(evaluated_snapshot, evaluated_snapshot).as_dict()
        diff_status = "identity_by_bound_hash"

    unchanged, after = _file_unchanged(prepared)
    checks.append(_check("historical_receipt_unchanged", unchanged, prepared.raw_before_sha256, after))
    overall = "passed" if all(check.get("status") == "passed" for check in checks) else "failed"
    return RegistryReplayReport(
        overall_status=overall,
        replay_mode=mode,
        receipt_id=prepared.receipt.get("receipt_id"),
        historical_status=prepared.receipt.get("status"),
        evaluated_status=decision.get("status"),
        historical_registry_snapshot_hash=prepared.receipt.get("registry_snapshot_hash"),
        evaluated_registry_snapshot_hash=fresh_receipt.get("registry_snapshot_hash"),
        decision_changed=_decision_changed(prepared.receipt, fresh_receipt),
        historical_receipt_unchanged=unchanged,
        checks=tuple(checks),
        fresh_decision=decision,
        receipt=prepared.receipt,
        registry_diff=registry_diff,
        migration=_migration_summary(migration, unsigned_local_approval_accepted=unsigned_local_approval_accepted) if migration else None,
        registry_diff_status=diff_status,
    )


__all__ = [
    "CURRENT_REGISTRY_REPLAY",
    "EXACT_SNAPSHOT_REPLAY",
    "MIGRATED_REGISTRY_REPLAY",
    "REPLAY_MODES",
    "RegistryReplayReport",
    "replay_trust_receipt_mode",
]
