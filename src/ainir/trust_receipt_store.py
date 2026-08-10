from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .core import load_draft
from .execution_context import TrustedExecutionContext
from .trust_gate import evaluate_trust_gate
from .canonical import (
    DuplicateKeyJSONError,
    MAX_JSON_BYTES,
    MAX_JSON_DEPTH,
    canonical_json,
    json_depth,
    read_json_object_artifact,
    reject_duplicate_json_keys,
    sha256_bytes,
    sha256_json,
    sha256_text,
)
from .contract_validation import validate_trust_receipt
from .contracts import (
    LEGACY_TRUST_RECEIPT_VERSION,
    TRUST_RECEIPT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_KIND,
)


# Backwards-compatible private aliases retained for one RC cycle. New callers
# should import the supported helpers from ``ainir.canonical``.
_canonical_json = canonical_json
_sha256_text = sha256_text
_sha256_json = sha256_json
_sha256_bytes = sha256_bytes
_reject_duplicate_json_keys = reject_duplicate_json_keys


def _json_depth(value: Any, limit: int = MAX_JSON_DEPTH, current: int = 0) -> int:
    return json_depth(value, limit=limit, current=current)


def _read_json_artifact(path: str | Path, artifact_name: str = "receipt") -> dict[str, Any]:
    return read_json_object_artifact(path, artifact_name=artifact_name).as_dict()


def _stable_lowering_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": None, "findings": []}
    findings = value.get("findings", [])
    stable_findings = []
    if isinstance(findings, list):
        for f in findings:
            if isinstance(f, Mapping):
                stable_findings.append({
                    "rule": f.get("rule"),
                    "severity": f.get("severity"),
                    "target": f.get("target"),
                    "message": f.get("message"),
                })
    return {
        "status": value.get("status"),
        "context_environment": value.get("context_environment"),
        "findings": stable_findings,
    }




def _stable_registry_snapshot(value: Any) -> dict[str, Any]:
    """Return a path-portable registry snapshot projection for receipts.

    Receipts should bind registry *content* snapshots, not absolute checkout
    paths. The full receipt may include source_path for diagnostics, but replay
    compares this stable projection so moving the repository does not invalidate
    a receipt when registry bytes are unchanged.
    """
    if not isinstance(value, Mapping):
        return {}
    items = value.get("items")
    stable_items: dict[str, Any] = {}
    if isinstance(items, Mapping):
        for name, item in sorted(items.items(), key=lambda pair: str(pair[0])):
            if isinstance(item, Mapping):
                stable_items[str(name)] = {
                    key: item.get(key)
                    for key in ("label", "raw_sha256", "canonical_sha256", "missing", "load_error", "copy_drift")
                    if key in item
                }
            else:
                stable_items[str(name)] = item
    return {
        "kind": value.get("kind"),
        "version": value.get("version"),
        "combined_sha256": value.get("combined_sha256"),
        "items": stable_items,
    }

def stable_receipt_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the tamper-evident stable receipt fields used by replay.

    Timestamps and local file paths are intentionally excluded. The projection is
    not a cryptographic signature, but it makes receipt-field edits visible to
    local replay unless the entire receipt is knowingly recomputed.
    """
    trusted_context = receipt.get("trusted_context") if isinstance(receipt.get("trusted_context"), Mapping) else {}
    projection = {
        "receipt_id": receipt.get("receipt_id"),
        "receipt_kind": receipt.get("receipt_kind"),
        "version": receipt.get("version"),
        "status": receipt.get("status"),
        "module_id": receipt.get("module_id"),
        "workflow": receipt.get("workflow"),
        "draft_hash": receipt.get("draft_hash"),
        "canonical_draft_sha256": receipt.get("canonical_draft_sha256"),
        "raw_source_sha256": receipt.get("raw_source_sha256"),
        "safety_registry_hash": receipt.get("safety_registry_hash"),
        "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
        "registry_snapshot": _stable_registry_snapshot(receipt.get("registry_snapshot")),
        "verifier_report_hash": receipt.get("verifier_report_hash"),
        "trusted_context": {
            "environment": trusted_context.get("environment"),
            "source": trusted_context.get("source"),
            "purpose": trusted_context.get("purpose"),
        },
        "failed_gates": list(receipt.get("failed_gates") or []),
        "warning_gates": list(receipt.get("warning_gates") or []),
        "gate_results": receipt.get("gate_results") if isinstance(receipt.get("gate_results"), Mapping) else {},
        "evidence_summary": receipt.get("evidence_summary") if isinstance(receipt.get("evidence_summary"), Mapping) else {},
        "verified_intent_packet_canonical_sha256": receipt.get("verified_intent_packet_canonical_sha256"),
        "verified_intent_packet_hash_algorithm": receipt.get("verified_intent_packet_hash_algorithm"),
        "lowering_eligibility": _stable_lowering_projection(receipt.get("lowering_eligibility")),
        "production_runtime_ready": receipt.get("production_runtime_ready"),
        "v1_final_ready": receipt.get("v1_final_ready"),
    }
    # Preserve the exact legacy projection shape. Stable v1 receipts bind the
    # legacy serializer marker explicitly so it cannot be silently rewritten.
    if receipt.get("version") == TRUST_RECEIPT_CONTRACT:
        projection["legacy_version"] = receipt.get("legacy_version")
    return projection


def stable_receipt_projection_hash(receipt: Mapping[str, Any]) -> str:
    return _sha256_json(stable_receipt_projection(receipt))


def convert_trust_receipt_contract(
    receipt: Mapping[str, Any],
    *,
    target_version: str = TRUST_RECEIPT_CONTRACT,
) -> dict[str, Any]:
    """Convert between the stable v1 and legacy pre-v1 receipt serializers.

    Conversion changes only contract metadata and the derived stable projection
    hash. Trust semantics, receipt id, evidence, registry, and decision fields
    are preserved.
    """

    converted = json.loads(json.dumps(dict(receipt), ensure_ascii=False))
    current = converted.get("version")
    if target_version == LEGACY_TRUST_RECEIPT_VERSION:
        if current == TRUST_RECEIPT_CONTRACT:
            converted["version"] = LEGACY_TRUST_RECEIPT_VERSION
            converted.pop("legacy_version", None)
        elif current != LEGACY_TRUST_RECEIPT_VERSION:
            raise ValueError(f"unsupported TrustReceipt source contract: {current!r}")
    elif target_version == TRUST_RECEIPT_CONTRACT:
        if current == LEGACY_TRUST_RECEIPT_VERSION:
            converted["legacy_version"] = LEGACY_TRUST_RECEIPT_VERSION
            converted["version"] = TRUST_RECEIPT_CONTRACT
        elif current == TRUST_RECEIPT_CONTRACT:
            converted.setdefault("legacy_version", LEGACY_TRUST_RECEIPT_VERSION)
        else:
            raise ValueError(f"unsupported TrustReceipt source contract: {current!r}")
    else:
        raise ValueError(f"unsupported TrustReceipt target contract: {target_version!r}")
    converted["stable_receipt_projection_hash"] = stable_receipt_projection_hash(converted)
    return converted


def _read_json(path: str | Path) -> dict[str, Any]:
    result = _read_json_artifact(path)
    if not result.get("ok"):
        reason = result.get("reason", "json_load_error")
        detail = result.get("detail", "")
        raise ValueError(f"{reason}: {detail}")
    return result["value"]




def _validate_receipt_semantics(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compatibility wrapper around the supported contract validator."""

    return validate_trust_receipt(receipt)


@dataclass(frozen=True)
class IssuedTrustReceipt:
    decision: Mapping[str, Any]
    receipt: Mapping[str, Any]
    receipt_path: str
    decision_path: str
    manifest_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_status": "issued",
            "receipt_id": self.receipt.get("receipt_id"),
            "trust_status": self.decision.get("status"),
            "module_id": self.decision.get("module_id"),
            "workflow": self.decision.get("workflow"),
            "receipt_version": self.receipt.get("version"),
            "receipt_path": self.receipt_path,
            "decision_path": self.decision_path,
            "manifest_path": self.manifest_path,
        }


@dataclass(frozen=True)
class ReceiptReplayReport:
    overall_status: str
    receipt_id: str | None
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fresh_decision: Mapping[str, Any] = field(default_factory=dict)
    receipt: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "receipt_id": self.receipt_id,
            "checks": [dict(c) for c in self.checks],
            "fresh_decision": dict(self.fresh_decision),
            "receipt": dict(self.receipt),
        }

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "kind": TRUST_RECEIPT_REPLAY_REPORT_KIND,
            "version": TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
            **self.as_dict(),
        }


@dataclass(frozen=True)
class ReceiptArtifactValidationReport:
    overall_status: str
    receipt_id: str | None
    receipt_version: str | None
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    receipt: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "receipt_id": self.receipt_id,
            "receipt_version": self.receipt_version,
            "checks": [dict(check) for check in self.checks],
            "receipt": dict(self.receipt),
        }


def verify_trust_receipt_artifact(path: str | Path) -> ReceiptArtifactValidationReport:
    """Validate receipt JSON, contract fields, and its stable self-hash.

    This does not re-evaluate the draft or current registry. Use
    :func:`replay_trust_receipt` when fresh semantic replay is required.
    """

    artifact = _read_json_artifact(path, artifact_name="receipt")
    if not artifact.get("ok"):
        check = {
            "check": "receipt_json_valid",
            "status": "failed",
            "expected": "bounded duplicate-key-free UTF-8 JSON object",
            "actual": artifact.get("reason"),
            "detail": artifact.get("detail"),
            "path": artifact.get("path"),
        }
        return ReceiptArtifactValidationReport("failed", None, None, (check,))
    receipt = artifact["value"]
    checks: list[dict[str, Any]] = [{
        "check": "receipt_json_valid",
        "status": "passed",
        "expected": "bounded duplicate-key-free UTF-8 JSON object",
        "actual": "valid",
        "receipt_raw_file_sha256": artifact.get("raw_file_sha256"),
        "receipt_canonical_sha256": artifact.get("canonical_sha256"),
    }]
    semantic = _validate_receipt_semantics(receipt)
    checks.extend(semantic)
    if not semantic:
        checks.append({
            "check": "receipt_contract_valid",
            "status": "passed",
            "expected": "supported stable or legacy TrustReceipt contract",
            "actual": receipt.get("version"),
        })
    stored = receipt.get("stable_receipt_projection_hash")
    computed = stable_receipt_projection_hash(receipt)
    checks.append({
        "check": "stable_receipt_projection_hash_self_check",
        "status": "passed" if stored == computed else "failed",
        "expected": stored,
        "actual": computed,
    })
    overall = "passed" if all(check.get("status") == "passed" for check in checks) else "failed"
    return ReceiptArtifactValidationReport(
        overall,
        receipt.get("receipt_id") if isinstance(receipt.get("receipt_id"), str) else None,
        receipt.get("version") if isinstance(receipt.get("version"), str) else None,
        tuple(checks),
        receipt,
    )


def issue_trust_receipt(
    draft_path: str | Path,
    out_dir: str | Path,
    context: TrustedExecutionContext | None = None,
    *,
    contract_version: str = LEGACY_TRUST_RECEIPT_VERSION,
) -> IssuedTrustReceipt:
    """Run the Trust Gate and persist its decision plus receipt.

    A receipt is not a substitute for replay. It is a signed-by-structure local
    artifact: future replay must recompute hashes and the Trust Gate decision.
    """
    context = context or TrustedExecutionContext.public_demo()
    draft = load_draft(draft_path)
    decision_object = evaluate_trust_gate(draft, context)
    if contract_version == LEGACY_TRUST_RECEIPT_VERSION:
        decision = decision_object.as_dict()
    elif contract_version == TRUST_RECEIPT_CONTRACT:
        decision = decision_object.as_public_dict()
    else:
        raise ValueError(f"unsupported TrustReceipt contract: {contract_version!r}")
    receipt = dict(decision["receipt"])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    receipt_id = str(receipt.get("receipt_id") or "receipt.unknown")
    safe_name = receipt_id.replace(":", "_").replace("/", "_")
    decision_path = out / f"{safe_name}.decision.json"
    receipt_path = out / f"{safe_name}.receipt.json"
    manifest_path = out / "trust_receipt_manifest.jsonl"
    decision_text = json.dumps(decision, indent=2, ensure_ascii=False)
    receipt_text = json.dumps(receipt, indent=2, ensure_ascii=False)
    decision_path.write_text(decision_text, encoding="utf-8")
    receipt_path.write_text(receipt_text, encoding="utf-8")
    receipt_canonical_sha256 = _sha256_json(receipt)
    decision_canonical_sha256 = _sha256_json(decision)
    receipt_record = {
        "receipt_id": receipt_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "trust_status": decision.get("status"),
        "module_id": decision.get("module_id"),
        "workflow": decision.get("workflow"),
        "draft_hash": receipt.get("draft_hash"),
        "canonical_draft_sha256": receipt.get("canonical_draft_sha256"),
        "raw_source_sha256": receipt.get("raw_source_sha256"),
        "safety_registry_hash": receipt.get("safety_registry_hash"),
        "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
        "stable_receipt_projection_hash": receipt.get("stable_receipt_projection_hash"),
        "registry_snapshot": _stable_registry_snapshot(receipt.get("registry_snapshot")),
        "verifier_report_hash": receipt.get("verifier_report_hash"),
        "receipt_raw_file_sha256": _sha256_bytes(receipt_path.read_bytes()),
        "receipt_canonical_sha256": receipt_canonical_sha256,
        "decision_raw_file_sha256": _sha256_bytes(decision_path.read_bytes()),
        "decision_canonical_sha256": decision_canonical_sha256,
        "receipt_file_hash": receipt_canonical_sha256,
        "decision_file_hash": decision_canonical_sha256,
        "receipt_path": str(receipt_path),
        "decision_path": str(decision_path),
    }
    _write_manifest_with_active_record(manifest_path, receipt_record)
    return IssuedTrustReceipt(
        decision=decision,
        receipt=receipt,
        receipt_path=str(receipt_path),
        decision_path=str(decision_path),
        manifest_path=str(manifest_path),
    )


def _public_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_replay_source(source: Any, receipt_path: str | Path) -> tuple[Path | None, list[str], Path | None]:
    if not isinstance(source, (str, Path)) or not str(source):
        return None, [], None
    raw = Path(source)
    tried: list[str] = []
    if raw.is_absolute():
        tried.append(str(raw))
        return (raw, tried, None) if raw.exists() else (None, tried, None)
    # Preserve repo-relative input strings for deterministic receipt replay.
    # If replay is invoked from outside the repo, evaluate inside repo_root so
    # Verifier report input_file remains the same relative path used at issue time.
    tried.append(str(raw))
    if raw.exists():
        return raw, tried, None
    repo_candidate = _public_repo_root() / raw
    tried.append(str(repo_candidate))
    if repo_candidate.exists():
        return raw, tried, _public_repo_root()
    receipt_candidate = Path(receipt_path).resolve().parent / raw
    tried.append(str(receipt_candidate))
    if receipt_candidate.exists():
        return receipt_candidate, tried, None
    return None, tried, None


def replay_trust_receipt(
    receipt_path: str | Path,
    draft_path: str | Path | None = None,
    context: TrustedExecutionContext | None = None,
) -> ReceiptReplayReport:
    """Replay a stored receipt against the current draft and registry.

    Replay passes only when the current Trust Gate decision reproduces the
    receipt's stable hashes and decision fields. The receipt's `generated_at`
    timestamp is intentionally ignored.
    """
    receipt_artifact = _read_json_artifact(receipt_path, artifact_name="receipt")
    if not receipt_artifact.get("ok"):
        return ReceiptReplayReport(
            overall_status="failed",
            receipt_id=None,
            checks=({
                "check": "receipt_json_valid",
                "status": "failed",
                "expected": "valid JSON object without duplicate keys",
                "actual": receipt_artifact.get("reason"),
                "detail": receipt_artifact.get("detail"),
                "path": receipt_artifact.get("path"),
                "raw_file_sha256": receipt_artifact.get("raw_file_sha256"),
            },),
        )
    receipt = receipt_artifact["value"]
    source = draft_path if draft_path is not None else receipt.get("draft_source_path")
    semantic_failures = _validate_receipt_semantics(receipt)
    checks: list[dict[str, Any]] = [{
        "check": "receipt_json_valid",
        "status": "passed",
        "expected": "valid JSON object without duplicate keys",
        "actual": "valid",
        "receipt_raw_file_sha256": receipt_artifact.get("raw_file_sha256"),
        "receipt_canonical_sha256": receipt_artifact.get("canonical_sha256"),
    }]
    checks.extend(semantic_failures)
    if semantic_failures:
        return ReceiptReplayReport(
            overall_status="failed",
            receipt_id=receipt.get("receipt_id") if isinstance(receipt.get("receipt_id"), str) else None,
            receipt=receipt,
            checks=tuple(checks),
        )
    source_path, tried_sources, replay_cwd = _resolve_replay_source(source, receipt_path)
    if source_path is None:
        return ReceiptReplayReport(
            overall_status="failed",
            receipt_id=receipt.get("receipt_id") if isinstance(receipt.get("receipt_id"), str) else None,
            receipt=receipt,
            checks=({
                "check": "draft_source_exists",
                "status": "failed",
                "expected": "existing explicit draft path or repo-relative receipt.draft_source_path",
                "actual": source,
                "tried": tried_sources,
            },),
        )
    if context is None:
        env = None
        source_value = "receipt_replay"
        purpose_value = "trust_receipt_replay"
        tc = receipt.get("trusted_context")
        if isinstance(tc, dict):
            if isinstance(tc.get("environment"), str):
                env = tc.get("environment")
            if isinstance(tc.get("source"), str) and tc.get("source"):
                source_value = tc.get("source")
            if isinstance(tc.get("purpose"), str) and tc.get("purpose"):
                purpose_value = tc.get("purpose")
        context = TrustedExecutionContext.from_environment(env or "public_demo", source=source_value, purpose=purpose_value)
    try:
        old_cwd = Path.cwd()
        if replay_cwd is not None:
            os.chdir(replay_cwd)
        try:
            draft = load_draft(source_path)
            fresh_decision_object = evaluate_trust_gate(draft, context)
            if receipt.get("version") == TRUST_RECEIPT_CONTRACT:
                fresh = fresh_decision_object.as_public_dict()
            else:
                fresh = fresh_decision_object.as_dict()
        finally:
            if replay_cwd is not None:
                os.chdir(old_cwd)
    except Exception as exc:
        checks.append({
            "check": "replay_evaluation_completed",
            "status": "failed",
            "expected": "Trust Gate replay without registry/parser/runtime exception",
            "actual": type(exc).__name__,
            "detail": str(exc),
        })
        return ReceiptReplayReport(
            overall_status="failed",
            receipt_id=receipt.get("receipt_id") if isinstance(receipt.get("receipt_id"), str) else None,
            checks=tuple(checks),
            receipt=receipt,
        )
    fresh_receipt = dict(fresh.get("receipt", {}))

    expected_verified_intent_packet_hash = None
    if receipt.get("verified_intent_packet_canonical_sha256") is not None:
        try:
            from .verified_intent_export import _PROFILE_AIVL, _build_packet, _canonical_verified_intent_packet_hash
            expected_packet = _build_packet(draft, context, fresh, _PROFILE_AIVL)
            expected_verified_intent_packet_hash = _canonical_verified_intent_packet_hash(expected_packet)
            fresh_receipt["verified_intent_packet_canonical_sha256"] = expected_verified_intent_packet_hash
            fresh_receipt["verified_intent_packet_hash_algorithm"] = "canonical_json_sha256"
            fresh_receipt["stable_receipt_projection_hash"] = stable_receipt_projection_hash(fresh_receipt)
        except Exception as exc:
            checks.append({
                "check": "verified_intent_expected_packet_regenerated",
                "status": "failed",
                "expected": "regenerate expected VerifiedIntentPacket from draft and fresh Trust Gate decision",
                "actual": type(exc).__name__,
                "detail": str(exc),
            })

    stored_projection_hash = receipt.get("stable_receipt_projection_hash")
    supplied_projection_hash = stable_receipt_projection_hash(receipt)
    fresh_projection_hash = stable_receipt_projection_hash(fresh_receipt)

    comparisons = [
        ("receipt_version", receipt.get("version"), fresh_receipt.get("version")),
        ("receipt_legacy_version", receipt.get("legacy_version"), fresh_receipt.get("legacy_version")),
        ("receipt_id", receipt.get("receipt_id"), fresh_receipt.get("receipt_id")),
        ("status", receipt.get("status"), fresh_receipt.get("status")),
        ("module_id", receipt.get("module_id"), fresh_receipt.get("module_id")),
        ("workflow", receipt.get("workflow"), fresh_receipt.get("workflow")),
        ("draft_hash", receipt.get("draft_hash"), fresh_receipt.get("draft_hash")),
        ("canonical_draft_sha256", receipt.get("canonical_draft_sha256"), fresh_receipt.get("canonical_draft_sha256")),
        ("raw_source_sha256", receipt.get("raw_source_sha256"), fresh_receipt.get("raw_source_sha256")),
        ("safety_registry_hash", receipt.get("safety_registry_hash"), fresh_receipt.get("safety_registry_hash")),
        ("registry_snapshot_hash", receipt.get("registry_snapshot_hash"), fresh_receipt.get("registry_snapshot_hash")),
        ("registry_snapshot", _stable_registry_snapshot(receipt.get("registry_snapshot")), _stable_registry_snapshot(fresh_receipt.get("registry_snapshot"))),
        ("verifier_report_hash", receipt.get("verifier_report_hash"), fresh_receipt.get("verifier_report_hash")),
        ("trusted_environment", _nested(receipt, ["trusted_context", "environment"]), _nested(fresh_receipt, ["trusted_context", "environment"])),
        ("trusted_context_source", _nested(receipt, ["trusted_context", "source"]), _nested(fresh_receipt, ["trusted_context", "source"])),
        ("trusted_context_purpose", _nested(receipt, ["trusted_context", "purpose"]), _nested(fresh_receipt, ["trusted_context", "purpose"])),
        ("failed_gates", receipt.get("failed_gates"), fresh_receipt.get("failed_gates")),
        ("warning_gates", receipt.get("warning_gates"), fresh_receipt.get("warning_gates")),
        ("gate_results", receipt.get("gate_results"), fresh_receipt.get("gate_results")),
        ("evidence_summary", receipt.get("evidence_summary"), fresh_receipt.get("evidence_summary")),
        ("verified_intent_packet_canonical_sha256", receipt.get("verified_intent_packet_canonical_sha256"), fresh_receipt.get("verified_intent_packet_canonical_sha256")),
        ("verified_intent_packet_hash_algorithm", receipt.get("verified_intent_packet_hash_algorithm"), fresh_receipt.get("verified_intent_packet_hash_algorithm")),
        ("lowering_eligibility", _stable_lowering_projection(receipt.get("lowering_eligibility")), _stable_lowering_projection(fresh_receipt.get("lowering_eligibility"))),
        ("production_runtime_ready", receipt.get("production_runtime_ready"), fresh_receipt.get("production_runtime_ready")),
        ("v1_final_ready", receipt.get("v1_final_ready"), fresh_receipt.get("v1_final_ready")),
        ("stable_receipt_projection_hash_self_check", stored_projection_hash, supplied_projection_hash),
        ("stable_receipt_projection_hash_replay", stored_projection_hash, fresh_projection_hash),
    ]
    for name, expected, actual in comparisons:
        checks.append({
            "check": name,
            "status": "passed" if expected == actual else "failed",
            "expected": expected,
            "actual": actual,
        })
    checks.extend(_bundle_integrity_checks(Path(receipt_path), receipt, expected_verified_intent_packet_hash=expected_verified_intent_packet_hash))
    overall = "passed" if all(c["status"] == "passed" for c in checks) else "failed"
    return ReceiptReplayReport(
        overall_status=overall,
        receipt_id=receipt.get("receipt_id") if isinstance(receipt.get("receipt_id"), str) else None,
        checks=tuple(checks),
        fresh_decision=fresh,
        receipt=receipt,
    )



@dataclass(frozen=True)
class ManifestRecordsResult:
    ok: bool
    records: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()


def _manifest_records(manifest_path: Path) -> ManifestRecordsResult:
    """Load a trust receipt JSONL manifest without silently skipping bad lines.

    Bundle manifests are trust artifacts. Empty lines are tolerated for append-only
    convenience, but every non-empty line must be a duplicate-key-free JSON
    object within the configured artifact size/depth limits. A single malformed
    line makes the whole manifest defective, even if another line contains a
    matching receipt record.
    """
    if not manifest_path.exists():
        return ManifestRecordsResult(ok=True)
    try:
        raw_bytes = manifest_path.read_bytes()
    except OSError as exc:
        return ManifestRecordsResult(ok=False, errors=({"line": None, "reason": "jsonl_file_read_error", "detail": str(exc)},))
    if len(raw_bytes) > MAX_JSON_BYTES:
        return ManifestRecordsResult(ok=False, errors=({"line": None, "reason": "jsonl_file_too_large", "detail": f"manifest exceeds {MAX_JSON_BYTES} byte limit"},))
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ManifestRecordsResult(ok=False, errors=({"line": None, "reason": "jsonl_utf8_decode_error", "detail": str(exc)},))

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except DuplicateKeyJSONError as exc:
            errors.append({"line": lineno, "reason": "json_duplicate_key", "detail": str(exc)})
            continue
        except json.JSONDecodeError as exc:
            errors.append({"line": lineno, "reason": "json_decode_error", "detail": str(exc)})
            continue
        except (RecursionError, MemoryError, ValueError) as exc:
            errors.append({"line": lineno, "reason": "json_resource_error", "detail": str(exc)})
            continue
        if not isinstance(value, dict):
            errors.append({"line": lineno, "reason": "json_root_not_object", "detail": type(value).__name__})
            continue
        try:
            _json_depth(value)
        except (ValueError, RecursionError, MemoryError) as exc:
            errors.append({"line": lineno, "reason": "json_depth_limit_exceeded", "detail": str(exc)})
            continue
        records.append(value)
    return ManifestRecordsResult(ok=not errors, records=tuple(records), errors=tuple(errors))


def _write_manifest_with_active_record(manifest_path: Path, record: Mapping[str, Any]) -> None:
    """Persist an active manifest record and mark older same-receipt records superseded.

    The replay path treats every non-superseded record with the same receipt_id as
    authoritative. Rewriting older records as explicitly superseded preserves the
    useful append/history semantics for repeated local issuance while making
    injected conflicting records fail replay/release validation.
    """
    active = dict(record)
    active.setdefault("manifest_record_status", "active")
    receipt_id = active.get("receipt_id")
    current_raw = active.get("receipt_raw_file_sha256")
    issued_at = active.get("issued_at")
    existing: list[dict[str, Any]] = []
    if manifest_path.exists():
        loaded = _manifest_records(manifest_path)
        if not loaded.ok:
            raise ValueError(
                f"Refusing to append to defective trust receipt manifest {manifest_path}: "
                f"{list(loaded.errors)}"
            )
        existing = [dict(r) for r in loaded.records]
    rewritten: list[dict[str, Any]] = []
    for old in existing:
        if old.get("receipt_id") == receipt_id and old.get("manifest_record_status") != "superseded":
            old = dict(old)
            old["manifest_record_status"] = "superseded"
            if current_raw is not None:
                old["superseded_by_receipt_raw_file_sha256"] = current_raw
            if issued_at is not None:
                old.setdefault("superseded_at", issued_at)
        rewritten.append(old)
    rewritten.append(active)
    manifest_path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rewritten), encoding="utf-8")


def _manifest_all_record_schema_checks(records: list[dict[str, Any]], manifest_path: Path) -> list[dict[str, Any]]:
    """Validate every JSONL manifest record, not only the current receipt id.

    Trust receipt manifests act as bundle append logs.  A current replay is
    receipt-scoped, but the manifest itself should not contain malformed active
    records for unrelated receipt ids because downstream tools may index the
    log globally.  Superseded records are allowed as historical records; active
    records must carry the core receipt binding fields, and optional decision /
    VerifiedIntent packet field groups must be complete when present.
    """
    allowed_statuses = {"active", "superseded"}
    status_errors: list[dict[str, Any]] = []
    missing_required: list[dict[str, Any]] = []
    core_required = (
        "receipt_id",
        "receipt_raw_file_sha256",
        "receipt_canonical_sha256",
        "stable_receipt_projection_hash",
        "registry_snapshot_hash",
    )
    grouped_required = (
        ("decision_raw_file_sha256", "decision_canonical_sha256"),
        ("packet_raw_file_sha256", "packet_canonical_sha256"),
    )

    for index, record in enumerate(records, start=1):
        status = record.get("manifest_record_status", "active")
        if status not in allowed_statuses:
            status_errors.append({
                "record_index": index,
                "receipt_id": record.get("receipt_id"),
                "actual": status,
                "allowed": sorted(allowed_statuses),
            })
            continue
        if status == "superseded":
            continue

        missing = [field for field in core_required if record.get(field) in (None, "")]
        for group in grouped_required:
            if any(field in record for field in group):
                missing.extend(field for field in group if record.get(field) in (None, ""))
        if missing:
            missing_required.append({
                "record_index": index,
                "receipt_id": record.get("receipt_id"),
                "missing_fields": sorted(set(missing)),
            })

    return [
        {
            "check": "bundle_manifest_all_record_statuses_valid",
            "status": "passed" if not status_errors else "failed",
            "expected": "every manifest_record_status is active or superseded; absent is treated as active for legacy records",
            "actual": status_errors or "valid",
            "path": str(manifest_path),
        },
        {
            "check": "bundle_manifest_all_active_records_required_fields_present",
            "status": "passed" if not missing_required else "failed",
            "expected": {
                "core_required": list(core_required),
                "complete_optional_groups": [list(group) for group in grouped_required],
            },
            "actual": missing_required or "all active records complete",
            "path": str(manifest_path),
        },
    ]


def _active_manifest_conflict_checks(records: list[dict[str, Any]], receipt_id: str, expected: Mapping[str, Any], manifest_path: Path) -> list[dict[str, Any]]:
    """Validate same-receipt manifest records as a strict active bundle set.

    Non-empty manifest lines are parsed elsewhere.  Here we enforce bundle
    semantics: every record for the current receipt_id must have a known status,
    every active record must carry all applicable hash fields, and every active
    record must agree with the current receipt bundle.  Superseded records are
    historical only and cannot satisfy current replay.
    """
    same = [r for r in records if r.get("receipt_id") == receipt_id]
    allowed_statuses = {"active", "superseded"}
    status_errors: list[dict[str, Any]] = []
    missing_required: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    active_count = 0
    required_expected = {field: value for field, value in expected.items() if value is not None}

    for index, record in enumerate(same, start=1):
        status = record.get("manifest_record_status", "active")
        if status not in allowed_statuses:
            status_errors.append({
                "receipt_id": receipt_id,
                "matching_record_index": index,
                "actual": status,
                "allowed": sorted(allowed_statuses),
            })
            continue
        if status == "superseded":
            continue

        active_count += 1
        missing = [field for field in required_expected if field not in record or record.get(field) in (None, "")]
        if missing:
            missing_required.append({
                "receipt_id": receipt_id,
                "matching_record_index": index,
                "missing_fields": sorted(missing),
            })

        mismatches: dict[str, dict[str, Any]] = {}
        for field, expected_value in required_expected.items():
            if field not in record or record.get(field) in (None, ""):
                continue
            actual_value = record.get(field)
            if actual_value != expected_value:
                mismatches[field] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            conflicts.append({"receipt_id": receipt_id, "matching_record_index": index, "mismatches": mismatches})

    checks = [
        {
            "check": "bundle_manifest_record_status_valid",
            "status": "passed" if not status_errors else "failed",
            "expected": "manifest_record_status is active or superseded; absent is treated as active for legacy records",
            "actual": status_errors or "valid",
            "path": str(manifest_path),
        },
        {
            "check": "bundle_manifest_active_record_required_fields_present",
            "status": "passed" if not missing_required else "failed",
            "expected": sorted(required_expected),
            "actual": {"active_record_count": active_count, "missing": missing_required},
            "path": str(manifest_path),
        },
        {
            "check": "bundle_manifest_receipt_id_unique_or_consistent",
            "status": "passed" if not conflicts else "failed",
            "expected": "all active records for this receipt_id match the current receipt bundle hashes",
            "actual": {"active_record_count": active_count, "conflicts": conflicts},
            "path": str(manifest_path),
        },
        {
            "check": "bundle_manifest_active_matching_record_present",
            "status": "passed" if active_count > 0 else "failed",
            "expected": "at least one active manifest record for the current receipt_id",
            "actual": {"active_record_count": active_count, "same_receipt_record_count": len(same)},
            "path": str(manifest_path),
        },
    ]
    return checks

def _bundle_integrity_checks(receipt_path: Path, receipt: Mapping[str, Any], expected_verified_intent_packet_hash: str | None = None) -> list[dict[str, Any]]:
    """Validate sibling decision/manifest/VerifiedIntent packet artifacts.

    Standalone receipts remain replay-authoritative only when they have no sibling
    handoff artifacts.  Once a sibling decision exists, or once a receipt binds a
    VerifiedIntent packet hash, bundle replay must inspect the matching sidecars
    directly.  Packet checks intentionally do not depend on a decision sidecar
    being present; otherwise deleting decision/manifest files could make a
    tampered packet invisible to receipt replay.
    """
    checks: list[dict[str, Any]] = []
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str):
        return checks

    safe_name = receipt_id.replace(":", "_").replace("/", "_")
    candidate_decisions = [
        receipt_path.with_name(f"{safe_name}.decision.json"),
        receipt_path.with_name("trust_gate_decision.json"),
        receipt_path.with_name("verified_intent_trust_gate_decision.json"),
    ]
    decision_path = next((p for p in candidate_decisions if p.exists()), None)
    packet_path = receipt_path.with_name("verified_intent_packet.json")
    packet_bound = receipt.get("verified_intent_packet_canonical_sha256") is not None
    packet_sidecar_present = packet_path.exists()
    bundle_expected = decision_path is not None or packet_bound or packet_sidecar_present
    if not bundle_expected:
        return checks

    packet_artifact: dict[str, Any] | None = None
    actual_packet_hash: str | None = None
    if packet_bound or packet_sidecar_present:
        packet_artifact = _read_json_artifact(packet_path, artifact_name="verified_intent_packet") if packet_path.exists() else {"ok": False, "reason": "packet_file_missing", "path": str(packet_path)}
        if packet_artifact.get("ok"):
            try:
                from .verified_intent_export import _canonical_verified_intent_packet_hash
                actual_packet_hash = _canonical_verified_intent_packet_hash(packet_artifact.get("value", {}))
            except Exception:
                actual_packet_hash = packet_artifact.get("canonical_sha256")

    decision_artifact: dict[str, Any] = {"ok": False, "reason": "decision_file_not_present"}
    if decision_path is not None:
        decision_artifact = _read_json_artifact(decision_path, artifact_name="decision")
        checks.append({
            "check": "sibling_decision_json_valid",
            "status": "passed" if decision_artifact.get("ok") else "failed",
            "expected": "valid JSON object without duplicate keys",
            "actual": "valid" if decision_artifact.get("ok") else decision_artifact.get("reason"),
            "path": str(decision_path),
        })
        if decision_artifact.get("ok"):
            decision = decision_artifact["value"]
            embedded = decision.get("receipt") if isinstance(decision, Mapping) else None
            checks.append({
                "check": "sibling_decision_embedded_receipt_matches",
                "status": "passed" if isinstance(embedded, Mapping) and stable_receipt_projection_hash(embedded) == stable_receipt_projection_hash(receipt) else "failed",
                "expected": stable_receipt_projection_hash(receipt),
                "actual": stable_receipt_projection_hash(embedded) if isinstance(embedded, Mapping) else None,
                "path": str(decision_path),
            })
            checks.extend(_decision_top_level_consistency_checks(decision, receipt, decision_path))
    elif packet_bound or packet_sidecar_present:
        checks.append({
            "check": "sibling_decision_present_for_bound_packet",
            "status": "failed",
            "expected": "decision sidecar present when receipt binds or is colocated with a VerifiedIntentPacket",
            "actual": "missing",
            "path": str(receipt_path.parent),
        })

    manifest_path = receipt_path.with_name("trust_receipt_manifest.jsonl")
    checks.append({
        "check": "bundle_manifest_present",
        "status": "passed" if manifest_path.exists() else "failed",
        "expected": "trust_receipt_manifest.jsonl present when sibling decision or VerifiedIntentPacket exists",
        "actual": "present" if manifest_path.exists() else "missing",
        "path": str(manifest_path),
    })
    records: list[dict[str, Any]] = []
    matching_records: list[dict[str, Any]] = []
    matching = None
    if not manifest_path.exists():
        # Packet JSON validity/hash is still checked below when a sidecar exists;
        # manifest-backed raw/canonical hash checks necessarily cannot run.
        matching = None
    else:
        manifest_result = _manifest_records(manifest_path)
        checks.append({
            "check": "bundle_manifest_jsonl_valid",
            "status": "passed" if manifest_result.ok else "failed",
            "expected": "all non-empty JSONL lines are duplicate-key-free JSON objects",
            "actual": "valid" if manifest_result.ok else list(manifest_result.errors),
            "path": str(manifest_path),
        })
        records = list(manifest_result.records)
        checks.extend(_manifest_all_record_schema_checks(records, manifest_path))
        receipt_raw = _sha256_bytes(receipt_path.read_bytes())
        matching_records = [record for record in records if record.get("receipt_id") == receipt_id]
        active_expected = {
            "receipt_raw_file_sha256": receipt_raw,
            "receipt_canonical_sha256": _sha256_json(receipt),
            "stable_receipt_projection_hash": receipt.get("stable_receipt_projection_hash"),
            "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
        }
        if decision_artifact.get("ok"):
            active_expected.update({
                "decision_raw_file_sha256": decision_artifact.get("raw_file_sha256"),
                "decision_canonical_sha256": decision_artifact.get("canonical_sha256"),
            })
        if packet_artifact is not None and packet_artifact.get("ok"):
            active_expected.update({
                "packet_raw_file_sha256": packet_artifact.get("raw_file_sha256"),
                "packet_canonical_sha256": actual_packet_hash,
            })
        checks.extend(_active_manifest_conflict_checks(matching_records, str(receipt_id), active_expected, manifest_path))
        matching = next((record for record in reversed(matching_records) if record.get("receipt_raw_file_sha256") == receipt_raw and record.get("manifest_record_status", "active") == "active"), None)
        checks.append({
            "check": "bundle_manifest_matching_record_present",
            "status": "passed" if matching is not None else "failed",
            "expected": receipt_id,
            "actual": [r.get("receipt_id") for r in records],
            "path": str(manifest_path),
        })
        if matching is not None:
            checks.append({
                "check": "manifest_receipt_raw_file_sha256",
                "status": "passed" if matching.get("receipt_raw_file_sha256") == receipt_raw else "failed",
                "expected": matching.get("receipt_raw_file_sha256"),
                "actual": receipt_raw,
                "path": str(manifest_path),
            })
            if decision_artifact.get("ok"):
                checks.extend([
                    {
                        "check": "manifest_decision_raw_file_sha256",
                        "status": "passed" if matching.get("decision_raw_file_sha256") == decision_artifact.get("raw_file_sha256") else "failed",
                        "expected": matching.get("decision_raw_file_sha256"),
                        "actual": decision_artifact.get("raw_file_sha256"),
                        "path": str(manifest_path),
                    },
                    {
                        "check": "manifest_decision_canonical_sha256",
                        "status": "passed" if matching.get("decision_canonical_sha256") == decision_artifact.get("canonical_sha256") else "failed",
                        "expected": matching.get("decision_canonical_sha256"),
                        "actual": decision_artifact.get("canonical_sha256"),
                        "path": str(manifest_path),
                    },
                ])

    if packet_bound or packet_sidecar_present:
        packet_artifact = packet_artifact or {"ok": False, "reason": "packet_file_missing", "path": str(packet_path)}
        checks.append({
            "check": "sibling_verified_intent_packet_json_valid",
            "status": "passed" if packet_artifact.get("ok") else "failed",
            "expected": "valid VerifiedIntentPacket JSON object when receipt binds or is colocated with a packet hash",
            "actual": "valid" if packet_artifact.get("ok") else packet_artifact.get("reason"),
            "path": str(packet_path),
        })
        if packet_artifact.get("ok"):
            checks.append({
                "check": "sibling_verified_intent_packet_hash_matches_receipt",
                "status": "passed" if actual_packet_hash == receipt.get("verified_intent_packet_canonical_sha256") else "failed",
                "expected": receipt.get("verified_intent_packet_canonical_sha256"),
                "actual": actual_packet_hash,
                "path": str(packet_path),
            })
            if expected_verified_intent_packet_hash is not None:
                checks.append({
                    "check": "sibling_verified_intent_packet_hash_matches_fresh_replay",
                    "status": "passed" if actual_packet_hash == expected_verified_intent_packet_hash else "failed",
                    "expected": expected_verified_intent_packet_hash,
                    "actual": actual_packet_hash,
                    "path": str(packet_path),
                })
            if matching is not None:
                checks.extend([
                    {
                        "check": "manifest_packet_raw_file_sha256",
                        "status": "passed" if matching.get("packet_raw_file_sha256") == packet_artifact.get("raw_file_sha256") else "failed",
                        "expected": matching.get("packet_raw_file_sha256"),
                        "actual": packet_artifact.get("raw_file_sha256"),
                        "path": str(manifest_path),
                    },
                    {
                        "check": "manifest_packet_canonical_sha256",
                        "status": "passed" if matching.get("packet_canonical_sha256") == actual_packet_hash else "failed",
                        "expected": matching.get("packet_canonical_sha256"),
                        "actual": actual_packet_hash,
                        "path": str(manifest_path),
                    },
                ])
    return checks


def _decision_top_level_consistency_checks(decision: Mapping[str, Any], receipt: Mapping[str, Any], decision_path: Path) -> list[dict[str, Any]]:
    """Bind sibling decision top-level fields to the replay-authoritative receipt.

    The manifest is unsigned and cannot be the trust root.  These checks prevent
    joint decision+manifest edits from making forged decision fields look valid
    while leaving the embedded receipt untouched.
    """
    checks: list[dict[str, Any]] = []

    def add(name: str, expected: Any, actual: Any) -> None:
        checks.append({
            "check": f"sibling_decision_{name}_matches_receipt",
            "status": "passed" if expected == actual else "failed",
            "expected": expected,
            "actual": actual,
            "path": str(decision_path),
        })

    add("status", receipt.get("status"), decision.get("status"))
    add("module_id", receipt.get("module_id"), decision.get("module_id"))
    add("workflow", receipt.get("workflow"), decision.get("workflow"))
    add("failed_gates", receipt.get("failed_gates") or [], decision.get("failed_gates") or [])
    add("warning_gates", receipt.get("warning_gates") or [], decision.get("warning_gates") or [])
    add("gate_results", receipt.get("gate_results") if isinstance(receipt.get("gate_results"), Mapping) else {}, decision.get("gate_results") if isinstance(decision.get("gate_results"), Mapping) else {})
    expected_handoff = receipt.get("status") == "passed" and not (receipt.get("failed_gates") or [])
    if "handoff_allowed" in decision:
        add("handoff_allowed", expected_handoff, decision.get("handoff_allowed"))
    lowering = receipt.get("lowering_eligibility") if isinstance(receipt.get("lowering_eligibility"), Mapping) else {}
    expected_lowering = expected_handoff and lowering.get("status") == "allowed"
    if "lowering_allowed" in decision:
        add("lowering_allowed", expected_lowering, decision.get("lowering_allowed"))
    return checks


def _nested(data: Mapping[str, Any], path: list[str]) -> Any:
    value: Any = data
    for part in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value
