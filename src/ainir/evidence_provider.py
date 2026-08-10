"""Deterministic offline EvidenceProvider contracts and adapters.

P5 deliberately separates provider transport from semantic trust.  Providers
return untrusted candidate evidence.  AiNIR then re-validates issuer identity,
claim scope, draft binding, reliability, validity, revocation, bundle integrity,
and (when required) an offline HMAC signature before emitting a validation
report.

A P5 validation report is not a Trust Gate promotion.  The public v1 contract
hard-codes ``trust_gate_promotion_allowed`` to ``False``; wiring accepted
provider records into receipt-bound Trust Gate evaluation requires a later,
explicit governance decision.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import yaml

from .canonical import MAX_JSON_BYTES, json_depth, read_json_object_artifact, sha256_json
from .contracts import (
    EVIDENCE_BUNDLE_CONTRACT,
    EVIDENCE_BUNDLE_KIND,
    EVIDENCE_PROVIDER_POLICY_CONTRACT,
    EVIDENCE_PROVIDER_POLICY_KIND,
    EVIDENCE_RECORD_CONTRACT,
    EVIDENCE_RECORD_KIND,
    EVIDENCE_REQUEST_CONTRACT,
    EVIDENCE_REQUEST_KIND,
    EVIDENCE_RESOLUTION_CONTRACT,
    EVIDENCE_RESOLUTION_KIND,
    EVIDENCE_VALIDATION_REPORT_CONTRACT,
    EVIDENCE_VALIDATION_REPORT_KIND,
)
from .core import DraftModule, load_yaml_no_duplicate_keys
from .safety_registry import get_registry


MAX_EVIDENCE_BUNDLE_BYTES = MAX_JSON_BYTES
MAX_EVIDENCE_RECORDS = 512
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_HMAC_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")
_PROVIDER_SOURCE_KINDS = frozenset({"fixture", "file", "signed_bundle"})
_RESOLUTION_STATUSES = frozenset({"resolved", "not_found", "provider_error"})
_SIGNATURE_STATUSES = frozenset({"not_applicable", "not_present", "unverified", "verified", "failed", "unknown_key"})
_REVOCATION_STATUSES = frozenset({"active", "revoked", "suspended", "unknown"})
_BINDING_MODES = frozenset({"raw", "canonical", "raw_or_canonical", "none"})

_REQUEST_FIELDS = frozenset({
    "kind", "version", "request_id", "provider_id", "evidence_id", "expected_kind",
    "claim_scope", "subject_binding", "evaluation_time", "production_runtime_ready",
})
_RECORD_FIELDS = frozenset({
    "kind", "version", "evidence_id", "evidence_kind", "issuer", "producer_kind",
    "policy_version", "claim_scope", "subject_binding", "validity", "revocation",
    "reliability", "provenance", "integrity", "production_runtime_ready",
})
_POLICY_FIELDS = frozenset({
    "kind", "version", "policy_id", "policy_sha256", "provider_id",
    "allowed_provider_versions", "allowed_source_kinds", "allowed_issuer_ids",
    "allowed_issuer_kinds", "allowed_evidence_kinds", "allowed_producer_kinds",
    "allowed_signature_key_ids",
    "minimum_reliability", "require_subject_binding", "require_validity_window",
    "require_active_revocation", "max_revocation_age_seconds",
    "require_verified_signature",
    "allow_trust_gate_promotion", "production_runtime_ready",
})
_BUNDLE_FIELDS = frozenset({
    "kind", "version", "bundle_id", "bundle_sha256", "provider_id",
    "provider_version", "source_kind", "records", "signature",
    "production_runtime_ready",
})
_RESOLUTION_FIELDS = frozenset({
    "kind", "version", "resolution_id", "resolution_sha256", "request_id",
    "status", "provider_id", "provider_version", "source_kind", "bundle_id",
    "bundle_sha256", "signature_status", "signature_key_id", "record", "message",
    "production_runtime_ready",
})
_REPORT_FIELDS = frozenset({
    "kind", "version", "validation_report_id", "validation_report_sha256",
    "overall_status", "accepted", "candidate_evidence_status", "request_id",
    "resolution_id", "evidence_id", "provider_id", "provider_policy_sha256",
    "record_sha256", "bundle_sha256", "signature_status", "checks",
    "trust_gate_promotion_allowed", "production_runtime_ready",
})


class EvidenceProviderError(ValueError):
    """Raised for malformed provider artifacts or unsafe adapter configuration."""


@dataclass(frozen=True)
class EvidenceArtifactValidationReport:
    artifact: str
    overall_status: str
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return self.overall_status == "passed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "overall_status": self.overall_status,
            "checks": [dict(check) for check in self.checks],
        }


@dataclass(frozen=True)
class EvidenceValidationReport:
    value: Mapping[str, Any]

    @property
    def accepted(self) -> bool:
        return bool(self.value.get("accepted"))

    @property
    def valid(self) -> bool:
        return self.accepted

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self.value))


@runtime_checkable
class EvidenceProvider(Protocol):
    """Minimal deterministic provider interface.

    Implementations do not return trusted facts.  They only return a candidate
    :class:`AiNIREvidenceResolution` for independent validation.
    """

    provider_id: str
    provider_version: str
    source_kind: str
    bundle: Mapping[str, Any]
    bundle_validation: EvidenceArtifactValidationReport
    signature_status: str
    signature_key_id: str | None

    def resolve(self, request: Mapping[str, Any]) -> dict[str, Any]:
        ...


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))


def _check(name: str, passed: bool, expected: Any, actual: Any, **extra: Any) -> dict[str, Any]:
    return {
        "check": name,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        **extra,
    }


def _safe_token(value: Any) -> bool:
    return isinstance(value, str) and bool(_SAFE_TOKEN_RE.fullmatch(value))


def _sha256_value(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _all_unique_strings(value: Any, *, non_empty: bool = True) -> bool:
    if not isinstance(value, list) or (non_empty and not value):
        return False
    if any(not _safe_token(item) for item in value):
        return False
    return len(value) == len(set(value))


def _ensure_finite_json(value: Any, *, path: str = "$", depth: int = 0) -> None:
    if depth > 160:
        raise EvidenceProviderError("evidence artifact nesting exceeds 160")
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceProviderError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceProviderError(f"non-string mapping key at {path}")
            _ensure_finite_json(item, path=f"{path}.{key}", depth=depth + 1)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_finite_json(item, path=f"{path}[{index}]", depth=depth + 1)


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def normalize_instant(value: str | datetime) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = _parse_instant(value)
        if parsed is None:
            raise EvidenceProviderError("time must be an ISO-8601 timestamp with a UTC offset")
    else:
        raise EvidenceProviderError("time must be a string or datetime")
    if parsed.tzinfo is None:
        raise EvidenceProviderError("time must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _projection_without(value: Mapping[str, Any], *fields: str) -> dict[str, Any]:
    return {key: _json_copy(item) for key, item in value.items() if key not in set(fields)}


def evidence_record_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    value = _json_copy(dict(record))
    integrity = value.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("record_sha256", None)
    return value


def evidence_policy_projection(policy: Mapping[str, Any]) -> dict[str, Any]:
    return _projection_without(policy, "policy_sha256")


def evidence_bundle_projection(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return _projection_without(bundle, "bundle_id", "bundle_sha256", "signature")


def evidence_resolution_projection(resolution: Mapping[str, Any]) -> dict[str, Any]:
    return _projection_without(resolution, "resolution_id", "resolution_sha256")


def evidence_validation_report_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    return _projection_without(report, "validation_report_id", "validation_report_sha256")


def build_evidence_record(
    *,
    evidence_id: str,
    evidence_kind: str,
    issuer_id: str,
    issuer_kind: str,
    producer_kind: str,
    policy_version: str,
    module_id: str,
    workflow: str,
    claim_ids: Sequence[str],
    claim_statement_sha256: str,
    provider_id: str,
    provider_version: str,
    source_kind: str,
    reliability: float,
    minimum_reliability: float = 0.8,
    subject_binding_mode: str = "none",
    raw_source_sha256: str | None = None,
    canonical_draft_sha256: str | None = None,
    valid_from: str | datetime | None = None,
    valid_until: str | datetime | None = None,
    revocation_status: str = "active",
    revocation_checked_at: str | datetime | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Build a self-hashed candidate evidence record."""

    record: dict[str, Any] = {
        "kind": EVIDENCE_RECORD_KIND,
        "version": EVIDENCE_RECORD_CONTRACT,
        "evidence_id": evidence_id,
        "evidence_kind": evidence_kind,
        "issuer": {"id": issuer_id, "kind": issuer_kind},
        "producer_kind": producer_kind,
        "policy_version": policy_version,
        "claim_scope": {
            "module_id": module_id,
            "workflow": workflow,
            "claim_ids": sorted(set(str(item) for item in claim_ids)),
            "claim_statement_sha256": claim_statement_sha256,
        },
        "subject_binding": {
            "mode": subject_binding_mode,
            "raw_source_sha256": raw_source_sha256,
            "canonical_draft_sha256": canonical_draft_sha256,
        },
        "validity": {
            "valid_from": normalize_instant(valid_from) if valid_from is not None else None,
            "valid_until": normalize_instant(valid_until) if valid_until is not None else None,
        },
        "revocation": {
            "status": revocation_status,
            "checked_at": normalize_instant(revocation_checked_at) if revocation_checked_at is not None else None,
        },
        "reliability": {
            "score": float(reliability),
            "minimum_required": float(minimum_reliability),
        },
        "provenance": {
            "provider_id": provider_id,
            "provider_version": provider_version,
            "source_kind": source_kind,
            "source_ref": source_ref,
        },
        "integrity": {"algorithm": "canonical_json_sha256"},
        "production_runtime_ready": False,
    }
    record["integrity"]["record_sha256"] = sha256_json(evidence_record_projection(record))
    return record


def build_evidence_request(
    *,
    provider_id: str,
    evidence_id: str,
    expected_kind: str | None,
    module_id: str,
    workflow: str,
    claim_id: str,
    claim_statement_sha256: str,
    raw_source_sha256: str | None,
    canonical_draft_sha256: str | None,
    evaluation_time: str | datetime,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "kind": EVIDENCE_REQUEST_KIND,
        "version": EVIDENCE_REQUEST_CONTRACT,
        "provider_id": provider_id,
        "evidence_id": evidence_id,
        "expected_kind": expected_kind,
        "claim_scope": {
            "module_id": module_id,
            "workflow": workflow,
            "claim_id": claim_id,
            "claim_statement_sha256": claim_statement_sha256,
        },
        "subject_binding": {
            "raw_source_sha256": raw_source_sha256,
            "canonical_draft_sha256": canonical_draft_sha256,
        },
        "evaluation_time": normalize_instant(evaluation_time),
        "production_runtime_ready": False,
    }
    digest = sha256_json(request)
    request["request_id"] = "ainir.evidence.request." + digest.removeprefix("sha256:")[:20]
    return request


def build_evidence_request_from_draft(
    draft: DraftModule,
    claim: Mapping[str, Any],
    evidence_ref: Mapping[str, Any],
    *,
    provider_id: str,
    evaluation_time: str | datetime,
) -> dict[str, Any]:
    payload = {key: value for key, value in draft.raw.items() if not str(key).startswith("__")}
    canonical = "sha256:" + sha256(
        yaml.safe_dump(payload, sort_keys=True, allow_unicode=True).encode("utf-8")
    ).hexdigest()
    raw_source = draft.raw.get("__raw_source_sha256__")
    if not _sha256_value(raw_source):
        raw_source = canonical
    statement = str(claim.get("statement", ""))
    return build_evidence_request(
        provider_id=provider_id,
        evidence_id=str(evidence_ref.get("id", "")),
        expected_kind=str(evidence_ref.get("kind")) if evidence_ref.get("kind") is not None else None,
        module_id=draft.module_id,
        workflow=draft.workflow,
        claim_id=str(claim.get("id", "")),
        claim_statement_sha256="sha256:" + sha256(statement.encode("utf-8")).hexdigest(),
        raw_source_sha256=str(raw_source),
        canonical_draft_sha256=canonical,
        evaluation_time=evaluation_time,
    )


def build_evidence_provider_policy(
    *,
    policy_id: str,
    provider_id: str,
    allowed_provider_versions: Sequence[str],
    allowed_source_kinds: Sequence[str],
    allowed_issuer_ids: Sequence[str],
    allowed_issuer_kinds: Sequence[str],
    allowed_evidence_kinds: Sequence[str],
    allowed_producer_kinds: Sequence[str],
    allowed_signature_key_ids: Sequence[str] = (),
    minimum_reliability: float = 0.8,
    require_subject_binding: bool = True,
    require_validity_window: bool = True,
    require_active_revocation: bool = True,
    max_revocation_age_seconds: int = 86_400,
    require_verified_signature: bool = False,
) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "kind": EVIDENCE_PROVIDER_POLICY_KIND,
        "version": EVIDENCE_PROVIDER_POLICY_CONTRACT,
        "policy_id": policy_id,
        "provider_id": provider_id,
        "allowed_provider_versions": sorted(set(allowed_provider_versions)),
        "allowed_source_kinds": sorted(set(allowed_source_kinds)),
        "allowed_issuer_ids": sorted(set(allowed_issuer_ids)),
        "allowed_issuer_kinds": sorted(set(allowed_issuer_kinds)),
        "allowed_evidence_kinds": sorted(set(allowed_evidence_kinds)),
        "allowed_producer_kinds": sorted(set(allowed_producer_kinds)),
        "allowed_signature_key_ids": sorted(set(allowed_signature_key_ids)),
        "minimum_reliability": float(minimum_reliability),
        "require_subject_binding": bool(require_subject_binding),
        "require_validity_window": bool(require_validity_window),
        "require_active_revocation": bool(require_active_revocation),
        "max_revocation_age_seconds": max_revocation_age_seconds,
        "require_verified_signature": bool(require_verified_signature),
        "allow_trust_gate_promotion": False,
        "production_runtime_ready": False,
    }
    policy["policy_sha256"] = sha256_json(evidence_policy_projection(policy))
    return policy


def build_evidence_bundle(
    *,
    provider_id: str,
    provider_version: str,
    source_kind: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted((_json_copy(dict(record)) for record in records), key=lambda item: str(item.get("evidence_id", "")))
    bundle: dict[str, Any] = {
        "kind": EVIDENCE_BUNDLE_KIND,
        "version": EVIDENCE_BUNDLE_CONTRACT,
        "provider_id": provider_id,
        "provider_version": provider_version,
        "source_kind": source_kind,
        "records": ordered,
        "signature": None,
        "production_runtime_ready": False,
    }
    digest = sha256_json(evidence_bundle_projection(bundle))
    bundle["bundle_sha256"] = digest
    bundle["bundle_id"] = "ainir.evidence.bundle." + digest.removeprefix("sha256:")[:20]
    return bundle


def sign_evidence_bundle(
    bundle: Mapping[str, Any],
    *,
    key_id: str,
    key: bytes,
) -> dict[str, Any]:
    if not _safe_token(key_id):
        raise EvidenceProviderError("HMAC fixture key_id must be a safe token")
    if not isinstance(key, (bytes, bytearray)) or len(key) < 16:
        raise EvidenceProviderError("HMAC fixture key must contain at least 16 bytes")
    value = _json_copy(dict(bundle))
    report = validate_evidence_bundle(value)
    if not report.valid:
        raise EvidenceProviderError("cannot sign an invalid evidence bundle")
    signature = hmac.new(bytes(key), str(value["bundle_sha256"]).encode("ascii"), sha256).hexdigest()
    value["signature"] = {
        "algorithm": "hmac-sha256",
        "key_id": key_id,
        "value": signature,
        "purpose": "offline_integrity_demo_not_public_key_attestation",
    }
    return value


def _verify_signature(bundle: Mapping[str, Any], verification_keys: Mapping[str, bytes] | None) -> tuple[str, str | None]:
    signature = bundle.get("signature")
    if signature is None:
        return "not_present", None
    if not isinstance(signature, Mapping):
        return "failed", None
    key_id = signature.get("key_id")
    if not _safe_token(key_id):
        return "failed", None
    if signature.get("algorithm") != "hmac-sha256" or signature.get("purpose") != "offline_integrity_demo_not_public_key_attestation":
        return "failed", str(key_id)
    observed = signature.get("value")
    if not isinstance(observed, str) or not _HEX_HMAC_RE.fullmatch(observed):
        return "failed", str(key_id)
    key = (verification_keys or {}).get(str(key_id))
    if key is None:
        return "unknown_key", str(key_id)
    if not isinstance(key, (bytes, bytearray)) or len(key) < 16:
        return "failed", str(key_id)
    expected = hmac.new(bytes(key), str(bundle.get("bundle_sha256", "")).encode("ascii"), sha256).hexdigest()
    return ("verified" if hmac.compare_digest(expected, observed) else "failed"), str(key_id)


def _request_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    return _projection_without(request, "request_id")


def _validate_request(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append(_check("request.unknown_fields", not (set(request) - _REQUEST_FIELDS), [], sorted(set(request) - _REQUEST_FIELDS)))
    checks.append(_check("request.kind", request.get("kind") == EVIDENCE_REQUEST_KIND, EVIDENCE_REQUEST_KIND, request.get("kind")))
    checks.append(_check("request.version", request.get("version") == EVIDENCE_REQUEST_CONTRACT, EVIDENCE_REQUEST_CONTRACT, request.get("version")))
    for field_name in ("provider_id", "evidence_id"):
        checks.append(_check(f"request.{field_name}", _safe_token(request.get(field_name)), "safe token", request.get(field_name)))
    expected_kind = request.get("expected_kind")
    checks.append(_check("request.expected_kind", expected_kind is None or _safe_token(expected_kind), "safe token|null", expected_kind))
    scope = request.get("claim_scope")
    scope_ok = isinstance(scope, Mapping) and set(scope) == {"module_id", "workflow", "claim_id", "claim_statement_sha256"}
    checks.append(_check("request.claim_scope.shape", scope_ok, ["claim_id", "claim_statement_sha256", "module_id", "workflow"], sorted(scope) if isinstance(scope, Mapping) else type(scope).__name__))
    if isinstance(scope, Mapping):
        for field_name in ("module_id", "workflow", "claim_id"):
            checks.append(_check(f"request.claim_scope.{field_name}", _safe_token(scope.get(field_name)), "safe token", scope.get(field_name)))
        checks.append(_check("request.claim_scope.claim_statement_sha256", _sha256_value(scope.get("claim_statement_sha256")), "sha256:<64 lowercase hex>", scope.get("claim_statement_sha256")))
    subject = request.get("subject_binding")
    subject_ok = isinstance(subject, Mapping) and set(subject) == {"raw_source_sha256", "canonical_draft_sha256"}
    checks.append(_check("request.subject_binding.shape", subject_ok, ["canonical_draft_sha256", "raw_source_sha256"], sorted(subject) if isinstance(subject, Mapping) else type(subject).__name__))
    if isinstance(subject, Mapping):
        for field_name in ("raw_source_sha256", "canonical_draft_sha256"):
            value = subject.get(field_name)
            checks.append(_check(f"request.subject_binding.{field_name}", value is None or _sha256_value(value), "sha256:<64 lowercase hex>|null", value))
    instant = _parse_instant(request.get("evaluation_time"))
    checks.append(_check("request.evaluation_time", instant is not None, "ISO-8601 timestamp with timezone", request.get("evaluation_time")))
    expected_id = "ainir.evidence.request." + sha256_json(_request_projection(request)).removeprefix("sha256:")[:20]
    checks.append(_check("request.request_id", request.get("request_id") == expected_id, expected_id, request.get("request_id")))
    checks.append(_check("request.production_runtime_ready", request.get("production_runtime_ready") is False, False, request.get("production_runtime_ready")))
    return checks


def validate_evidence_provider_policy(policy: Mapping[str, Any]) -> EvidenceArtifactValidationReport:
    checks: list[dict[str, Any]] = []
    unknown = sorted(set(policy) - _POLICY_FIELDS)
    checks.append(_check("policy.unknown_fields", not unknown, [], unknown))
    checks.append(_check("policy.kind", policy.get("kind") == EVIDENCE_PROVIDER_POLICY_KIND, EVIDENCE_PROVIDER_POLICY_KIND, policy.get("kind")))
    checks.append(_check("policy.version", policy.get("version") == EVIDENCE_PROVIDER_POLICY_CONTRACT, EVIDENCE_PROVIDER_POLICY_CONTRACT, policy.get("version")))
    for field_name in ("policy_id", "provider_id"):
        checks.append(_check(f"policy.{field_name}", _safe_token(policy.get(field_name)), "safe token", policy.get(field_name)))
    for field_name in (
        "allowed_provider_versions", "allowed_source_kinds", "allowed_issuer_ids",
        "allowed_issuer_kinds", "allowed_evidence_kinds", "allowed_producer_kinds",
    ):
        checks.append(_check(
            f"policy.{field_name}",
            _all_unique_strings(policy.get(field_name)),
            "non-empty unique safe-token array",
            policy.get(field_name),
        ))
    signature_keys = policy.get("allowed_signature_key_ids")
    checks.append(_check(
        "policy.allowed_signature_key_ids",
        _all_unique_strings(signature_keys, non_empty=False),
        "unique safe-token array (may be empty unless signatures are required)",
        signature_keys,
    ))
    source_kinds = policy.get("allowed_source_kinds")
    checks.append(_check("policy.allowed_source_kinds.reviewed", isinstance(source_kinds, list) and set(source_kinds) <= _PROVIDER_SOURCE_KINDS, sorted(_PROVIDER_SOURCE_KINDS), source_kinds))
    minimum_value = policy.get("minimum_reliability")
    reliability_ok = (
        isinstance(minimum_value, (int, float))
        and not isinstance(minimum_value, bool)
        and math.isfinite(float(minimum_value))
        and 0.0 <= float(minimum_value) <= 1.0
    )
    checks.append(_check("policy.minimum_reliability", reliability_ok, "finite number in [0,1]", policy.get("minimum_reliability")))
    for field_name in (
        "require_subject_binding", "require_validity_window", "require_active_revocation",
        "require_verified_signature",
    ):
        checks.append(_check(f"policy.{field_name}", isinstance(policy.get(field_name), bool), "boolean", policy.get(field_name)))
    revocation_age = policy.get("max_revocation_age_seconds")
    revocation_age_ok = (
        isinstance(revocation_age, int)
        and not isinstance(revocation_age, bool)
        and 1 <= revocation_age <= 31_536_000
    )
    checks.append(_check(
        "policy.max_revocation_age_seconds",
        revocation_age_ok,
        "integer in [1,31536000]",
        revocation_age,
    ))
    if policy.get("require_verified_signature"):
        checks.append(_check("policy.signature_key_ids_required", bool(signature_keys), "at least one allowed signature key id", signature_keys))
    checks.append(_check("policy.allow_trust_gate_promotion", policy.get("allow_trust_gate_promotion") is False, False, policy.get("allow_trust_gate_promotion")))
    checks.append(_check("policy.production_runtime_ready", policy.get("production_runtime_ready") is False, False, policy.get("production_runtime_ready")))
    expected_hash = sha256_json(evidence_policy_projection(policy))
    checks.append(_check("policy.policy_sha256", policy.get("policy_sha256") == expected_hash, expected_hash, policy.get("policy_sha256")))
    return EvidenceArtifactValidationReport("evidence_provider_policy", "passed" if all(item["status"] == "passed" for item in checks) else "failed", tuple(checks))


def _record_structure_checks(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    unknown = sorted(set(record) - _RECORD_FIELDS)
    checks.append(_check("record.unknown_fields", not unknown, [], unknown))
    checks.append(_check("record.kind", record.get("kind") == EVIDENCE_RECORD_KIND, EVIDENCE_RECORD_KIND, record.get("kind")))
    checks.append(_check("record.version", record.get("version") == EVIDENCE_RECORD_CONTRACT, EVIDENCE_RECORD_CONTRACT, record.get("version")))
    for field_name in ("evidence_id", "evidence_kind", "producer_kind", "policy_version"):
        checks.append(_check(f"record.{field_name}", _safe_token(record.get(field_name)), "safe token", record.get(field_name)))
    issuer = record.get("issuer")
    issuer_ok = isinstance(issuer, Mapping) and set(issuer) == {"id", "kind"}
    checks.append(_check("record.issuer.shape", issuer_ok, ["id", "kind"], sorted(issuer) if isinstance(issuer, Mapping) else type(issuer).__name__))
    if isinstance(issuer, Mapping):
        for field_name in ("id", "kind"):
            checks.append(_check(f"record.issuer.{field_name}", _safe_token(issuer.get(field_name)), "safe token", issuer.get(field_name)))
    scope = record.get("claim_scope")
    scope_ok = isinstance(scope, Mapping) and set(scope) == {"module_id", "workflow", "claim_ids", "claim_statement_sha256"}
    checks.append(_check("record.claim_scope.shape", scope_ok, ["claim_ids", "claim_statement_sha256", "module_id", "workflow"], sorted(scope) if isinstance(scope, Mapping) else type(scope).__name__))
    if isinstance(scope, Mapping):
        for field_name in ("module_id", "workflow"):
            checks.append(_check(f"record.claim_scope.{field_name}", _safe_token(scope.get(field_name)), "safe token", scope.get(field_name)))
        checks.append(_check("record.claim_scope.claim_ids", _all_unique_strings(scope.get("claim_ids")), "non-empty unique safe-token array", scope.get("claim_ids")))
        checks.append(_check("record.claim_scope.claim_statement_sha256", _sha256_value(scope.get("claim_statement_sha256")), "sha256:<64 lowercase hex>", scope.get("claim_statement_sha256")))
    subject = record.get("subject_binding")
    subject_ok = isinstance(subject, Mapping) and set(subject) == {"mode", "raw_source_sha256", "canonical_draft_sha256"}
    checks.append(_check("record.subject_binding.shape", subject_ok, ["canonical_draft_sha256", "mode", "raw_source_sha256"], sorted(subject) if isinstance(subject, Mapping) else type(subject).__name__))
    if isinstance(subject, Mapping):
        checks.append(_check("record.subject_binding.mode", subject.get("mode") in _BINDING_MODES, sorted(_BINDING_MODES), subject.get("mode")))
        for field_name in ("raw_source_sha256", "canonical_draft_sha256"):
            value = subject.get(field_name)
            checks.append(_check(f"record.subject_binding.{field_name}", value is None or _sha256_value(value), "sha256:<64 lowercase hex>|null", value))
    validity = record.get("validity")
    validity_ok = isinstance(validity, Mapping) and set(validity) == {"valid_from", "valid_until"}
    checks.append(_check("record.validity.shape", validity_ok, ["valid_from", "valid_until"], sorted(validity) if isinstance(validity, Mapping) else type(validity).__name__))
    if isinstance(validity, Mapping):
        for field_name in ("valid_from", "valid_until"):
            value = validity.get(field_name)
            checks.append(_check(f"record.validity.{field_name}", value is None or _parse_instant(value) is not None, "ISO-8601 timestamp with timezone|null", value))
    revocation = record.get("revocation")
    revocation_ok = isinstance(revocation, Mapping) and set(revocation) == {"status", "checked_at"}
    checks.append(_check("record.revocation.shape", revocation_ok, ["checked_at", "status"], sorted(revocation) if isinstance(revocation, Mapping) else type(revocation).__name__))
    if isinstance(revocation, Mapping):
        checks.append(_check("record.revocation.status", revocation.get("status") in _REVOCATION_STATUSES, sorted(_REVOCATION_STATUSES), revocation.get("status")))
        checked_at = revocation.get("checked_at")
        checks.append(_check("record.revocation.checked_at", checked_at is None or _parse_instant(checked_at) is not None, "ISO-8601 timestamp with timezone|null", checked_at))
    reliability = record.get("reliability")
    reliability_ok = isinstance(reliability, Mapping) and set(reliability) == {"score", "minimum_required"}
    checks.append(_check("record.reliability.shape", reliability_ok, ["minimum_required", "score"], sorted(reliability) if isinstance(reliability, Mapping) else type(reliability).__name__))
    if isinstance(reliability, Mapping):
        for field_name in ("score", "minimum_required"):
            value = reliability.get(field_name)
            okay = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and 0.0 <= float(value) <= 1.0
            )
            checks.append(_check(f"record.reliability.{field_name}", okay, "finite number in [0,1]", value))
    provenance = record.get("provenance")
    provenance_ok = isinstance(provenance, Mapping) and set(provenance) == {"provider_id", "provider_version", "source_kind", "source_ref"}
    checks.append(_check("record.provenance.shape", provenance_ok, ["provider_id", "provider_version", "source_kind", "source_ref"], sorted(provenance) if isinstance(provenance, Mapping) else type(provenance).__name__))
    if isinstance(provenance, Mapping):
        for field_name in ("provider_id", "provider_version"):
            checks.append(_check(f"record.provenance.{field_name}", _safe_token(provenance.get(field_name)), "safe token", provenance.get(field_name)))
        checks.append(_check("record.provenance.source_kind", provenance.get("source_kind") in _PROVIDER_SOURCE_KINDS, sorted(_PROVIDER_SOURCE_KINDS), provenance.get("source_kind")))
        source_ref = provenance.get("source_ref")
        checks.append(_check("record.provenance.source_ref", source_ref is None or (isinstance(source_ref, str) and 1 <= len(source_ref) <= 512), "non-empty string up to 512 chars|null", source_ref))
    integrity = record.get("integrity")
    integrity_ok = isinstance(integrity, Mapping) and set(integrity) == {"algorithm", "record_sha256"}
    checks.append(_check("record.integrity.shape", integrity_ok, ["algorithm", "record_sha256"], sorted(integrity) if isinstance(integrity, Mapping) else type(integrity).__name__))
    if isinstance(integrity, Mapping):
        checks.append(_check("record.integrity.algorithm", integrity.get("algorithm") == "canonical_json_sha256", "canonical_json_sha256", integrity.get("algorithm")))
        expected_hash = sha256_json(evidence_record_projection(record))
        checks.append(_check("record.integrity.record_sha256", integrity.get("record_sha256") == expected_hash, expected_hash, integrity.get("record_sha256")))
    checks.append(_check("record.production_runtime_ready", record.get("production_runtime_ready") is False, False, record.get("production_runtime_ready")))
    return checks


def validate_evidence_bundle(
    bundle: Mapping[str, Any],
    *,
    verification_keys: Mapping[str, bytes] | None = None,
    require_signature: bool = False,
) -> EvidenceArtifactValidationReport:
    checks: list[dict[str, Any]] = []
    unknown = sorted(set(bundle) - _BUNDLE_FIELDS)
    checks.append(_check("bundle.unknown_fields", not unknown, [], unknown))
    checks.append(_check("bundle.kind", bundle.get("kind") == EVIDENCE_BUNDLE_KIND, EVIDENCE_BUNDLE_KIND, bundle.get("kind")))
    checks.append(_check("bundle.version", bundle.get("version") == EVIDENCE_BUNDLE_CONTRACT, EVIDENCE_BUNDLE_CONTRACT, bundle.get("version")))
    for field_name in ("provider_id", "provider_version"):
        checks.append(_check(f"bundle.{field_name}", _safe_token(bundle.get(field_name)), "safe token", bundle.get(field_name)))
    checks.append(_check("bundle.source_kind", bundle.get("source_kind") in _PROVIDER_SOURCE_KINDS, sorted(_PROVIDER_SOURCE_KINDS), bundle.get("source_kind")))
    records = bundle.get("records")
    records_ok = isinstance(records, list) and 0 < len(records) <= MAX_EVIDENCE_RECORDS and all(isinstance(item, Mapping) for item in records)
    checks.append(_check("bundle.records", records_ok, f"1..{MAX_EVIDENCE_RECORDS} record objects", type(records).__name__ if not isinstance(records, list) else len(records)))
    evidence_ids: list[str] = []
    if isinstance(records, list):
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                continue
            evidence_ids.append(str(record.get("evidence_id", "")))
            for check in _record_structure_checks(record):
                checks.append({**check, "check": f"bundle.records[{index}].{check['check']}"})
            provenance = record.get("provenance")
            if isinstance(provenance, Mapping):
                checks.append(_check(f"bundle.records[{index}].provider_binding", provenance.get("provider_id") == bundle.get("provider_id") and provenance.get("provider_version") == bundle.get("provider_version") and provenance.get("source_kind") == bundle.get("source_kind"), {"provider_id": bundle.get("provider_id"), "provider_version": bundle.get("provider_version"), "source_kind": bundle.get("source_kind")}, {"provider_id": provenance.get("provider_id"), "provider_version": provenance.get("provider_version"), "source_kind": provenance.get("source_kind")}))
    checks.append(_check("bundle.unique_evidence_ids", len(evidence_ids) == len(set(evidence_ids)), "unique evidence ids", evidence_ids))
    expected_hash = sha256_json(evidence_bundle_projection(bundle))
    checks.append(_check("bundle.bundle_sha256", bundle.get("bundle_sha256") == expected_hash, expected_hash, bundle.get("bundle_sha256")))
    expected_id = "ainir.evidence.bundle." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("bundle.bundle_id", bundle.get("bundle_id") == expected_id, expected_id, bundle.get("bundle_id")))
    signature_status, key_id = _verify_signature(bundle, verification_keys)
    if bundle.get("signature") is None and not require_signature:
        signature_ok = True
    elif require_signature:
        signature_ok = signature_status == "verified"
    else:
        signature_ok = signature_status in {"verified", "unknown_key", "unverified"}
        if signature_status == "not_present":
            signature_ok = True
    checks.append(_check("bundle.signature", signature_ok, "verified" if require_signature else "absent or structurally valid", signature_status, key_id=key_id))
    checks.append(_check("bundle.production_runtime_ready", bundle.get("production_runtime_ready") is False, False, bundle.get("production_runtime_ready")))
    return EvidenceArtifactValidationReport("evidence_bundle", "passed" if all(item["status"] == "passed" for item in checks) else "failed", tuple(checks))


def _resolution_projection(resolution: Mapping[str, Any]) -> dict[str, Any]:
    return evidence_resolution_projection(resolution)


def _build_resolution(
    *,
    request: Mapping[str, Any],
    status: str,
    provider_id: str,
    provider_version: str,
    source_kind: str,
    bundle: Mapping[str, Any],
    signature_status: str,
    signature_key_id: str | None,
    record: Mapping[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    resolution: dict[str, Any] = {
        "kind": EVIDENCE_RESOLUTION_KIND,
        "version": EVIDENCE_RESOLUTION_CONTRACT,
        "request_id": request.get("request_id"),
        "status": status,
        "provider_id": provider_id,
        "provider_version": provider_version,
        "source_kind": source_kind,
        "bundle_id": bundle.get("bundle_id"),
        "bundle_sha256": bundle.get("bundle_sha256"),
        "signature_status": signature_status,
        "signature_key_id": signature_key_id,
        "record": _json_copy(dict(record)) if isinstance(record, Mapping) else None,
        "message": message,
        "production_runtime_ready": False,
    }
    digest = sha256_json(_resolution_projection(resolution))
    resolution["resolution_sha256"] = digest
    resolution["resolution_id"] = "ainir.evidence.resolution." + digest.removeprefix("sha256:")[:20]
    return resolution


class _BundleEvidenceProvider:
    def __init__(
        self,
        bundle: Mapping[str, Any],
        *,
        verification_keys: Mapping[str, bytes] | None = None,
        require_signature: bool = False,
    ) -> None:
        self.bundle = _json_copy(dict(bundle))
        self._verification_keys = {
            str(key_id): bytes(key)
            for key_id, key in (verification_keys or {}).items()
            if _safe_token(key_id) and isinstance(key, (bytes, bytearray))
        }
        self.provider_id = str(self.bundle.get("provider_id", ""))
        self.provider_version = str(self.bundle.get("provider_version", ""))
        self.source_kind = str(self.bundle.get("source_kind", ""))
        self.signature_status, self.signature_key_id = _verify_signature(self.bundle, self._verification_keys)
        if self.bundle.get("signature") is None and self.source_kind == "fixture":
            self.signature_status = "not_applicable"
        self.bundle_validation = validate_evidence_bundle(
            self.bundle,
            verification_keys=self._verification_keys,
            require_signature=require_signature,
        )
        records = self.bundle.get("records")
        self._records = {
            str(record.get("evidence_id")): _json_copy(dict(record))
            for record in records
            if isinstance(records, list) and isinstance(record, Mapping) and isinstance(record.get("evidence_id"), str)
        } if isinstance(records, list) else {}

    def resolve(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self.bundle_validation.valid:
            return _build_resolution(
                request=request,
                status="provider_error",
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                source_kind=self.source_kind,
                bundle=self.bundle,
                signature_status=self.signature_status,
                signature_key_id=self.signature_key_id,
                record=None,
                message="provider bundle failed structural or integrity validation",
            )
        evidence_id = request.get("evidence_id")
        record = self._records.get(str(evidence_id))
        if record is None:
            return _build_resolution(
                request=request,
                status="not_found",
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                source_kind=self.source_kind,
                bundle=self.bundle,
                signature_status=self.signature_status,
                signature_key_id=self.signature_key_id,
                record=None,
                message="evidence id was not found in the provider bundle",
            )
        return _build_resolution(
            request=request,
            status="resolved",
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            source_kind=self.source_kind,
            bundle=self.bundle,
            signature_status=self.signature_status,
            signature_key_id=self.signature_key_id,
            record=record,
            message="provider returned one candidate evidence record; AiNIR validation is still required",
        )


class FixtureEvidenceProvider(_BundleEvidenceProvider):
    """In-memory deterministic provider for tests and conformance fixtures."""

    def __init__(self, bundle: Mapping[str, Any]) -> None:
        if bundle.get("source_kind") != "fixture":
            raise EvidenceProviderError("FixtureEvidenceProvider requires source_kind=fixture")
        super().__init__(bundle)

    @classmethod
    def from_records(
        cls,
        *,
        provider_id: str,
        provider_version: str,
        records: Sequence[Mapping[str, Any]],
    ) -> "FixtureEvidenceProvider":
        return cls(build_evidence_bundle(
            provider_id=provider_id,
            provider_version=provider_version,
            source_kind="fixture",
            records=records,
        ))


def _load_mapping_file(path: str | Path, *, max_bytes: int = MAX_EVIDENCE_BUNDLE_BYTES) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise EvidenceProviderError(f"cannot read evidence artifact {source}: {exc}") from exc
    if len(raw) > max_bytes:
        raise EvidenceProviderError(f"evidence artifact exceeds {max_bytes} bytes")
    if source.suffix.lower() == ".json":
        result = read_json_object_artifact(source, artifact_name="evidence_artifact", max_bytes=max_bytes)
        if not result.ok or result.value is None:
            raise EvidenceProviderError(f"invalid JSON evidence artifact: {result.reason}: {result.detail}")
        value = result.value
    else:
        try:
            text = raw.decode("utf-8")
            value = load_yaml_no_duplicate_keys(text)
        except Exception as exc:
            raise EvidenceProviderError(f"invalid YAML evidence artifact: {exc}") from exc
        if not isinstance(value, Mapping):
            raise EvidenceProviderError("evidence artifact root must be an object")
        value = dict(value)
        try:
            json_depth(value)
        except Exception as exc:
            raise EvidenceProviderError(str(exc)) from exc
    _ensure_finite_json(value)
    return _json_copy(dict(value))


def load_evidence_bundle(path: str | Path) -> dict[str, Any]:
    return _load_mapping_file(path)


def load_evidence_provider_policy(path: str | Path) -> dict[str, Any]:
    return _load_mapping_file(path)


class FileEvidenceProvider(_BundleEvidenceProvider):
    """Read an unsigned deterministic evidence bundle from a bounded local file."""

    def __init__(self, path: str | Path, *, allowed_root: str | Path | None = None) -> None:
        source = Path(path).expanduser().resolve()
        if allowed_root is not None:
            root = Path(allowed_root).expanduser().resolve()
            try:
                source.relative_to(root)
            except ValueError as exc:
                raise EvidenceProviderError("evidence bundle path escapes the allowed root") from exc
        bundle = load_evidence_bundle(source)
        if bundle.get("source_kind") != "file":
            raise EvidenceProviderError("FileEvidenceProvider requires source_kind=file")
        self.path = source
        super().__init__(bundle)


class SignedBundleEvidenceProvider(_BundleEvidenceProvider):
    """Verify a local HMAC-signed bundle before returning candidate evidence.

    HMAC here is an offline integrity adapter for deterministic testing.  It is
    not a public-key identity system and does not make the RC production ready.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        verification_keys: Mapping[str, bytes],
        allowed_root: str | Path | None = None,
    ) -> None:
        source = Path(path).expanduser().resolve()
        if allowed_root is not None:
            root = Path(allowed_root).expanduser().resolve()
            try:
                source.relative_to(root)
            except ValueError as exc:
                raise EvidenceProviderError("signed evidence bundle path escapes the allowed root") from exc
        bundle = load_evidence_bundle(source)
        if bundle.get("source_kind") != "signed_bundle":
            raise EvidenceProviderError("SignedBundleEvidenceProvider requires source_kind=signed_bundle")
        self.path = source
        super().__init__(bundle, verification_keys=verification_keys, require_signature=True)


def _validate_record_against_request(
    record: Mapping[str, Any],
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
    resolution: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks = _record_structure_checks(record)
    checks = [{**item, "check": f"candidate.{item['check']}"} for item in checks]

    checks.append(_check("candidate.evidence_id", record.get("evidence_id") == request.get("evidence_id"), request.get("evidence_id"), record.get("evidence_id")))
    expected_kind = request.get("expected_kind")
    if expected_kind is not None:
        checks.append(_check("candidate.expected_kind", record.get("evidence_kind") == expected_kind, expected_kind, record.get("evidence_kind")))
    checks.append(_check("candidate.policy.allowed_evidence_kind", record.get("evidence_kind") in set(policy.get("allowed_evidence_kinds") or []), policy.get("allowed_evidence_kinds"), record.get("evidence_kind")))
    registry_allowed = set(get_registry().trusted_evidence.get("allowed_kinds", []) or [])
    checks.append(_check("candidate.registry.allowed_evidence_kind", record.get("evidence_kind") in registry_allowed, sorted(registry_allowed), record.get("evidence_kind")))

    issuer = record.get("issuer") if isinstance(record.get("issuer"), Mapping) else {}
    checks.append(_check("candidate.policy.issuer_id", issuer.get("id") in set(policy.get("allowed_issuer_ids") or []), policy.get("allowed_issuer_ids"), issuer.get("id")))
    checks.append(_check("candidate.policy.issuer_kind", issuer.get("kind") in set(policy.get("allowed_issuer_kinds") or []), policy.get("allowed_issuer_kinds"), issuer.get("kind")))
    checks.append(_check("candidate.policy.producer_kind", record.get("producer_kind") in set(policy.get("allowed_producer_kinds") or []), policy.get("allowed_producer_kinds"), record.get("producer_kind")))
    checks.append(_check("candidate.policy.policy_version", record.get("policy_version") == policy.get("policy_id"), policy.get("policy_id"), record.get("policy_version")))

    provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
    checks.append(_check("candidate.provider.id", provenance.get("provider_id") == resolution.get("provider_id") == policy.get("provider_id"), policy.get("provider_id"), {"record": provenance.get("provider_id"), "resolution": resolution.get("provider_id")}))
    checks.append(_check("candidate.provider.version", provenance.get("provider_version") == resolution.get("provider_version") and resolution.get("provider_version") in set(policy.get("allowed_provider_versions") or []), policy.get("allowed_provider_versions"), {"record": provenance.get("provider_version"), "resolution": resolution.get("provider_version")}))
    checks.append(_check("candidate.provider.source_kind", provenance.get("source_kind") == resolution.get("source_kind") and resolution.get("source_kind") in set(policy.get("allowed_source_kinds") or []), policy.get("allowed_source_kinds"), {"record": provenance.get("source_kind"), "resolution": resolution.get("source_kind")}))

    request_scope = request.get("claim_scope") if isinstance(request.get("claim_scope"), Mapping) else {}
    record_scope = record.get("claim_scope") if isinstance(record.get("claim_scope"), Mapping) else {}
    checks.append(_check("candidate.claim_scope.module_id", record_scope.get("module_id") == request_scope.get("module_id"), request_scope.get("module_id"), record_scope.get("module_id")))
    checks.append(_check("candidate.claim_scope.workflow", record_scope.get("workflow") == request_scope.get("workflow"), request_scope.get("workflow"), record_scope.get("workflow")))
    checks.append(_check("candidate.claim_scope.claim_id", request_scope.get("claim_id") in set(record_scope.get("claim_ids") or []), request_scope.get("claim_id"), record_scope.get("claim_ids")))
    checks.append(_check("candidate.claim_scope.statement", record_scope.get("claim_statement_sha256") == request_scope.get("claim_statement_sha256"), request_scope.get("claim_statement_sha256"), record_scope.get("claim_statement_sha256")))

    subject = record.get("subject_binding") if isinstance(record.get("subject_binding"), Mapping) else {}
    requested_subject = request.get("subject_binding") if isinstance(request.get("subject_binding"), Mapping) else {}
    mode = subject.get("mode")
    raw_match = subject.get("raw_source_sha256") is not None and subject.get("raw_source_sha256") == requested_subject.get("raw_source_sha256")
    canonical_match = subject.get("canonical_draft_sha256") is not None and subject.get("canonical_draft_sha256") == requested_subject.get("canonical_draft_sha256")
    if mode == "raw":
        subject_accepted = raw_match
    elif mode == "canonical":
        subject_accepted = canonical_match
    elif mode == "raw_or_canonical":
        subject_accepted = raw_match or canonical_match
    elif mode == "none":
        subject_accepted = not bool(policy.get("require_subject_binding"))
    else:
        subject_accepted = False
    checks.append(_check("candidate.subject_binding", subject_accepted, "request-bound subject according to policy", {"mode": mode, "raw_match": raw_match, "canonical_match": canonical_match}))

    evaluation = _parse_instant(request.get("evaluation_time"))
    validity = record.get("validity") if isinstance(record.get("validity"), Mapping) else {}
    valid_from = _parse_instant(validity.get("valid_from"))
    valid_until = _parse_instant(validity.get("valid_until"))
    if policy.get("require_validity_window"):
        checks.append(_check("candidate.validity.window_present", valid_from is not None and valid_until is not None, "valid_from and valid_until", validity))
    if valid_from is not None and valid_until is not None:
        checks.append(_check("candidate.validity.order", valid_from < valid_until, "valid_from < valid_until", validity))
    checks.append(_check("candidate.validity.evaluation_time", evaluation is not None, "valid host evaluation_time", request.get("evaluation_time")))
    if evaluation is not None:
        starts_ok = valid_from is None or evaluation >= valid_from
        expires_ok = valid_until is None or evaluation < valid_until
        checks.append(_check("candidate.validity.not_before", starts_ok, f">= {validity.get('valid_from')}", request.get("evaluation_time")))
        checks.append(_check("candidate.validity.not_expired", expires_ok, f"< {validity.get('valid_until')}", request.get("evaluation_time")))

    revocation = record.get("revocation") if isinstance(record.get("revocation"), Mapping) else {}
    checked_at = _parse_instant(revocation.get("checked_at"))
    if policy.get("require_active_revocation"):
        checks.append(_check("candidate.revocation.active", revocation.get("status") == "active", "active", revocation.get("status")))
        checks.append(_check("candidate.revocation.checked_at_present", checked_at is not None, "host-verifiable revocation checked_at", revocation.get("checked_at")))
    if checked_at is not None and evaluation is not None:
        checks.append(_check("candidate.revocation.checked_at_not_future", checked_at <= evaluation, f"<= {request.get('evaluation_time')}", revocation.get("checked_at")))
        if policy.get("require_active_revocation"):
            max_age = policy.get("max_revocation_age_seconds")
            age_seconds = (evaluation - checked_at).total_seconds()
            freshness_ok = (
                isinstance(max_age, int)
                and not isinstance(max_age, bool)
                and 0 <= age_seconds <= max_age
            )
            checks.append(_check(
                "candidate.revocation.check_fresh",
                freshness_ok,
                f"0 <= age_seconds <= {max_age}",
                age_seconds,
                checked_at=revocation.get("checked_at"),
                evaluation_time=request.get("evaluation_time"),
            ))

    reliability = record.get("reliability") if isinstance(record.get("reliability"), Mapping) else {}
    score_value = reliability.get("score")
    record_min_value = reliability.get("minimum_required")
    policy_min_value = policy.get("minimum_reliability")
    numeric_values = (score_value, record_min_value, policy_min_value)
    reliability_ok = (
        all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in numeric_values)
        and all(math.isfinite(float(value)) for value in numeric_values)
        and float(score_value) >= max(float(record_min_value), float(policy_min_value))
    )
    checks.append(_check("candidate.reliability", reliability_ok, f">= max(record minimum, policy minimum={policy.get('minimum_reliability')})", reliability.get("score")))
    return checks


def validate_evidence_resolution(
    request: Mapping[str, Any],
    resolution: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    provider: EvidenceProvider | None = None,
    verification_keys: Mapping[str, bytes] | None = None,
) -> EvidenceValidationReport:
    """Independently validate one untrusted provider resolution.

    The provider object supplies the original bundle, but its own validation
    report and claimed signature status are never authoritative.  Signature
    keys must come from the host through ``verification_keys``; accepting key
    material supplied by an arbitrary provider would let that provider attest
    to itself.
    """

    checks: list[dict[str, Any]] = []
    checks.extend(_validate_request(request))
    policy_report = validate_evidence_provider_policy(policy)
    checks.extend({**item, "check": f"provider_policy.{item['check']}"} for item in policy_report.checks)

    unknown = sorted(set(resolution) - _RESOLUTION_FIELDS)
    checks.append(_check("resolution.unknown_fields", not unknown, [], unknown))
    checks.append(_check("resolution.kind", resolution.get("kind") == EVIDENCE_RESOLUTION_KIND, EVIDENCE_RESOLUTION_KIND, resolution.get("kind")))
    checks.append(_check("resolution.version", resolution.get("version") == EVIDENCE_RESOLUTION_CONTRACT, EVIDENCE_RESOLUTION_CONTRACT, resolution.get("version")))
    checks.append(_check("resolution.status", resolution.get("status") in _RESOLUTION_STATUSES, sorted(_RESOLUTION_STATUSES), resolution.get("status")))
    checks.append(_check("resolution.request_id", resolution.get("request_id") == request.get("request_id"), request.get("request_id"), resolution.get("request_id")))
    checks.append(_check("resolution.provider_id", resolution.get("provider_id") == request.get("provider_id") == policy.get("provider_id"), policy.get("provider_id"), {"request": request.get("provider_id"), "resolution": resolution.get("provider_id")}))
    checks.append(_check("resolution.provider_version", resolution.get("provider_version") in set(policy.get("allowed_provider_versions") or []), policy.get("allowed_provider_versions"), resolution.get("provider_version")))
    checks.append(_check("resolution.source_kind", resolution.get("source_kind") in set(policy.get("allowed_source_kinds") or []), policy.get("allowed_source_kinds"), resolution.get("source_kind")))
    checks.append(_check("resolution.signature_status", resolution.get("signature_status") in _SIGNATURE_STATUSES, sorted(_SIGNATURE_STATUSES), resolution.get("signature_status")))
    if policy.get("require_verified_signature"):
        checks.append(_check("resolution.signature_required", resolution.get("signature_status") == "verified", "verified", resolution.get("signature_status")))
        checks.append(_check("resolution.signature_key_id", resolution.get("signature_key_id") in set(policy.get("allowed_signature_key_ids") or []), policy.get("allowed_signature_key_ids"), resolution.get("signature_key_id")))
    expected_hash = sha256_json(_resolution_projection(resolution))
    checks.append(_check("resolution.resolution_sha256", resolution.get("resolution_sha256") == expected_hash, expected_hash, resolution.get("resolution_sha256")))
    expected_id = "ainir.evidence.resolution." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("resolution.resolution_id", resolution.get("resolution_id") == expected_id, expected_id, resolution.get("resolution_id")))
    checks.append(_check("resolution.production_runtime_ready", resolution.get("production_runtime_ready") is False, False, resolution.get("production_runtime_ready")))

    record = resolution.get("record")
    provider_present = provider is not None
    checks.append(_check(
        "provider_context_present",
        provider_present,
        "provider object carrying the original bundle",
        type(provider).__name__ if provider is not None else None,
    ))
    independently_observed_signature_status = str(resolution.get("signature_status"))
    independently_observed_signature_key_id = resolution.get("signature_key_id")
    if provider is not None:
        provider_id = getattr(provider, "provider_id", None)
        provider_version = getattr(provider, "provider_version", None)
        provider_source_kind = getattr(provider, "source_kind", None)
        raw_provider_bundle = getattr(provider, "bundle", None)
        provider_bundle: dict[str, Any] = {}
        provider_bundle_copy_ok = False
        if isinstance(raw_provider_bundle, Mapping):
            try:
                provider_bundle = _json_copy(dict(raw_provider_bundle))
                provider_bundle_copy_ok = True
            except (TypeError, ValueError, EvidenceProviderError):
                provider_bundle = {}
        checks.append(_check(
            "provider_bundle.mapping_copy",
            provider_bundle_copy_ok,
            "finite JSON object copied once for independent validation",
            type(raw_provider_bundle).__name__,
        ))
        require_signature = bool(policy.get("require_verified_signature"))
        independent_bundle_validation = validate_evidence_bundle(
            provider_bundle,
            verification_keys=verification_keys,
            require_signature=require_signature,
        )
        checks.extend(
            {**item, "check": f"provider_bundle_independent.{item['check']}"}
            for item in independent_bundle_validation.checks
        )
        claimed_validation = getattr(provider, "bundle_validation", None)
        claimed_valid = bool(getattr(claimed_validation, "valid", False))
        checks.append(_check(
            "provider_bundle.claimed_validation_matches_independent",
            claimed_valid == independent_bundle_validation.valid,
            independent_bundle_validation.valid,
            claimed_valid,
        ))
        independently_observed_signature_status, independently_observed_signature_key_id = _verify_signature(
            provider_bundle, verification_keys
        )
        if provider_bundle.get("signature") is None and provider_source_kind == "fixture":
            independently_observed_signature_status = "not_applicable"
        checks.append(_check(
            "provider_bundle.signature_status_recomputed",
            resolution.get("signature_status") == independently_observed_signature_status,
            independently_observed_signature_status,
            resolution.get("signature_status"),
        ))
        checks.append(_check(
            "provider_bundle.signature_key_id_recomputed",
            resolution.get("signature_key_id") == independently_observed_signature_key_id,
            independently_observed_signature_key_id,
            resolution.get("signature_key_id"),
        ))
        checks.append(_check("provider_bundle.identity", provider_id == resolution.get("provider_id") and provider_version == resolution.get("provider_version") and provider_source_kind == resolution.get("source_kind"), {"provider_id": resolution.get("provider_id"), "provider_version": resolution.get("provider_version"), "source_kind": resolution.get("source_kind")}, {"provider_id": provider_id, "provider_version": provider_version, "source_kind": provider_source_kind}))
        checks.append(_check(
            "provider_bundle.bundle_identity",
            provider_bundle.get("provider_id") == provider_id == resolution.get("provider_id")
            and provider_bundle.get("provider_version") == provider_version == resolution.get("provider_version")
            and provider_bundle.get("source_kind") == provider_source_kind == resolution.get("source_kind"),
            {
                "provider_id": resolution.get("provider_id"),
                "provider_version": resolution.get("provider_version"),
                "source_kind": resolution.get("source_kind"),
            },
            {
                "provider_id": provider_bundle.get("provider_id"),
                "provider_version": provider_bundle.get("provider_version"),
                "source_kind": provider_bundle.get("source_kind"),
            },
        ))
        checks.append(_check("provider_bundle.bundle_id", provider_bundle.get("bundle_id") == resolution.get("bundle_id"), provider_bundle.get("bundle_id"), resolution.get("bundle_id")))
        checks.append(_check("provider_bundle.bundle_sha256", provider_bundle.get("bundle_sha256") == resolution.get("bundle_sha256"), provider_bundle.get("bundle_sha256"), resolution.get("bundle_sha256")))
        bundle_records = provider_bundle.get("records")
        matching_records = [
            candidate
            for candidate in bundle_records
            if isinstance(bundle_records, list)
            and isinstance(candidate, Mapping)
            and candidate.get("evidence_id") == request.get("evidence_id")
        ] if isinstance(bundle_records, list) else []
        checks.append(_check(
            "provider_bundle.record_membership_count",
            len(matching_records) == 1,
            1,
            len(matching_records),
        ))
        bundled_record = matching_records[0] if len(matching_records) == 1 else None
        record_matches_bundle = (
            isinstance(record, Mapping)
            and isinstance(bundled_record, Mapping)
            and _json_copy(dict(record)) == _json_copy(dict(bundled_record))
        )
        checks.append(_check(
            "provider_bundle.resolution_record_matches_bundle",
            record_matches_bundle,
            "resolution record byte-semantically equal to the unique bundled record",
            "matched" if record_matches_bundle else "mismatch",
        ))

    resolved = resolution.get("status") == "resolved" and isinstance(record, Mapping)
    checks.append(_check("resolution.resolved_record", resolved, "status=resolved with one record", {"status": resolution.get("status"), "record_type": type(record).__name__}))
    if isinstance(record, Mapping):
        checks.extend(_validate_record_against_request(record, request, policy, resolution))

    checks.append(_check("provider_output_is_not_self_trusting", True, "AiNIR independent validation required", "validated by this report"))
    checks.append(_check("trust_gate_promotion_forbidden_in_p5", policy.get("allow_trust_gate_promotion") is False, False, policy.get("allow_trust_gate_promotion")))

    accepted = all(item["status"] == "passed" for item in checks)
    record_sha = None
    if isinstance(record, Mapping):
        integrity = record.get("integrity")
        if isinstance(integrity, Mapping):
            record_sha = integrity.get("record_sha256")
    report: dict[str, Any] = {
        "kind": EVIDENCE_VALIDATION_REPORT_KIND,
        "version": EVIDENCE_VALIDATION_REPORT_CONTRACT,
        "overall_status": "passed" if accepted else "failed",
        "accepted": accepted,
        "candidate_evidence_status": "validated_candidate" if accepted else "refused_candidate",
        "request_id": request.get("request_id"),
        "resolution_id": resolution.get("resolution_id"),
        "evidence_id": request.get("evidence_id"),
        "provider_id": policy.get("provider_id"),
        "provider_policy_sha256": policy.get("policy_sha256"),
        "record_sha256": record_sha,
        "bundle_sha256": resolution.get("bundle_sha256"),
        "signature_status": independently_observed_signature_status,
        "checks": checks,
        "trust_gate_promotion_allowed": False,
        "production_runtime_ready": False,
    }
    digest = sha256_json(evidence_validation_report_projection(report))
    report["validation_report_sha256"] = digest
    report["validation_report_id"] = "ainir.evidence.validation." + digest.removeprefix("sha256:")[:20]
    return EvidenceValidationReport(report)


def resolve_and_validate_evidence(
    provider: EvidenceProvider,
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    verification_keys: Mapping[str, bytes] | None = None,
) -> EvidenceValidationReport:
    resolution = provider.resolve(request)
    return validate_evidence_resolution(
        request,
        resolution,
        policy,
        provider=provider,
        verification_keys=verification_keys,
    )


def validate_evidence_validation_report(report: Mapping[str, Any]) -> EvidenceArtifactValidationReport:
    checks: list[dict[str, Any]] = []
    unknown = sorted(set(report) - _REPORT_FIELDS)
    checks.append(_check("validation_report.unknown_fields", not unknown, [], unknown))
    checks.append(_check("validation_report.kind", report.get("kind") == EVIDENCE_VALIDATION_REPORT_KIND, EVIDENCE_VALIDATION_REPORT_KIND, report.get("kind")))
    checks.append(_check("validation_report.version", report.get("version") == EVIDENCE_VALIDATION_REPORT_CONTRACT, EVIDENCE_VALIDATION_REPORT_CONTRACT, report.get("version")))
    checks_list = report.get("checks")
    checks_shape = isinstance(checks_list, list) and all(isinstance(item, Mapping) and item.get("status") in {"passed", "failed"} and isinstance(item.get("check"), str) for item in checks_list)
    checks.append(_check("validation_report.checks", checks_shape, "array of passed/failed check objects", type(checks_list).__name__))
    failed = [item.get("check") for item in checks_list if isinstance(item, Mapping) and item.get("status") == "failed"] if isinstance(checks_list, list) else []
    expected_accepted = not failed
    checks.append(_check("validation_report.accepted_consistency", report.get("accepted") is expected_accepted, expected_accepted, report.get("accepted"), failed_checks=failed))
    checks.append(_check("validation_report.overall_status_consistency", report.get("overall_status") == ("passed" if expected_accepted else "failed"), "passed" if expected_accepted else "failed", report.get("overall_status")))
    checks.append(_check("validation_report.candidate_status", report.get("candidate_evidence_status") == ("validated_candidate" if expected_accepted else "refused_candidate"), "validated_candidate" if expected_accepted else "refused_candidate", report.get("candidate_evidence_status")))
    checks.append(_check("validation_report.trust_gate_promotion_allowed", report.get("trust_gate_promotion_allowed") is False, False, report.get("trust_gate_promotion_allowed")))
    checks.append(_check("validation_report.production_runtime_ready", report.get("production_runtime_ready") is False, False, report.get("production_runtime_ready")))
    for field_name in ("provider_policy_sha256", "bundle_sha256"):
        checks.append(_check(f"validation_report.{field_name}", _sha256_value(report.get(field_name)), "sha256:<64 lowercase hex>", report.get(field_name)))
    record_sha = report.get("record_sha256")
    checks.append(_check("validation_report.record_sha256", record_sha is None or _sha256_value(record_sha), "sha256:<64 lowercase hex>|null", record_sha))
    expected_hash = sha256_json(evidence_validation_report_projection(report))
    checks.append(_check("validation_report.validation_report_sha256", report.get("validation_report_sha256") == expected_hash, expected_hash, report.get("validation_report_sha256")))
    expected_id = "ainir.evidence.validation." + expected_hash.removeprefix("sha256:")[:20]
    checks.append(_check("validation_report.validation_report_id", report.get("validation_report_id") == expected_id, expected_id, report.get("validation_report_id")))
    return EvidenceArtifactValidationReport("evidence_validation_report", "passed" if all(item["status"] == "passed" for item in checks) else "failed", tuple(checks))


def write_evidence_artifact(path: str | Path, value: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


__all__ = [
    "EvidenceArtifactValidationReport",
    "EvidenceProvider",
    "EvidenceProviderError",
    "EvidenceValidationReport",
    "FileEvidenceProvider",
    "FixtureEvidenceProvider",
    "MAX_EVIDENCE_BUNDLE_BYTES",
    "MAX_EVIDENCE_RECORDS",
    "SignedBundleEvidenceProvider",
    "build_evidence_bundle",
    "build_evidence_provider_policy",
    "build_evidence_record",
    "build_evidence_request",
    "build_evidence_request_from_draft",
    "evidence_bundle_projection",
    "evidence_policy_projection",
    "evidence_record_projection",
    "evidence_resolution_projection",
    "evidence_validation_report_projection",
    "load_evidence_bundle",
    "load_evidence_provider_policy",
    "normalize_instant",
    "resolve_and_validate_evidence",
    "sign_evidence_bundle",
    "validate_evidence_bundle",
    "validate_evidence_provider_policy",
    "validate_evidence_resolution",
    "validate_evidence_validation_report",
    "write_evidence_artifact",
]
