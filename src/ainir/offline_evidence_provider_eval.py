from __future__ import annotations

"""Deterministic P5 readiness check for offline EvidenceProvider contracts.

This module deliberately exercises only bounded, local adapters.  It does not
perform network I/O, does not mutate the bundled Evidence Ledger, and does not
promote provider output into a Trust Gate decision.
"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .core import DraftModule, load_draft
from .evidence_provider import (
    FileEvidenceProvider,
    FixtureEvidenceProvider,
    SignedBundleEvidenceProvider,
    build_evidence_bundle,
    build_evidence_provider_policy,
    build_evidence_record,
    build_evidence_request_from_draft,
    evidence_bundle_projection,
    evidence_record_projection,
    evidence_resolution_projection,
    resolve_and_validate_evidence,
    sign_evidence_bundle,
    validate_evidence_bundle,
    validate_evidence_provider_policy,
    validate_evidence_resolution,
    validate_evidence_validation_report,
    write_evidence_artifact,
)
from .canonical import sha256_json
from .verifier import verify_draft

ROOT = Path(__file__).resolve().parents[2]
_SAFE_DRAFT = ROOT / "examples" / "create_user_outbox_safe" / "draft.yaml"
_EVALUATION_TIME = "2026-08-10T00:00:00Z"
_VALID_FROM = "2026-08-01T00:00:00Z"
_VALID_UNTIL = "2026-09-01T00:00:00Z"
_REVOCATION_CHECKED_AT = "2026-08-09T00:00:00Z"
_PROVIDER_VERSION = "1.0"
_ISSUER_ID = "issuer.ainir.offline-verifier"
_SIGNING_KEY_ID = "key.ainir.offline-demo"
# Public, deterministic fixture material.  This is not a credential and the
# HMAC adapter is explicitly not a production identity system.
_SIGNING_KEY = sha256(b"AiNIR P5 offline integrity demo key - public fixture").digest()


def _record_for(
    *,
    provider_id: str,
    policy_id: str,
    source_kind: str,
    evidence_id: str,
    request: Mapping[str, Any],
    draft: DraftModule,
    claim: Mapping[str, Any],
    valid_until: str = _VALID_UNTIL,
    revocation_checked_at: str = _REVOCATION_CHECKED_AT,
) -> dict[str, Any]:
    return build_evidence_record(
        evidence_id=evidence_id,
        evidence_kind="verifier_report",
        issuer_id=_ISSUER_ID,
        issuer_kind="verifier",
        producer_kind="verifier",
        policy_version=policy_id,
        module_id=draft.module_id,
        workflow=draft.workflow,
        claim_ids=[str(claim.get("id"))],
        claim_statement_sha256=str(request["claim_scope"]["claim_statement_sha256"]),
        provider_id=provider_id,
        provider_version=_PROVIDER_VERSION,
        source_kind=source_kind,
        reliability=0.95,
        minimum_reliability=0.8,
        subject_binding_mode="canonical",
        canonical_draft_sha256=str(request["subject_binding"]["canonical_draft_sha256"]),
        valid_from=_VALID_FROM,
        valid_until=valid_until,
        revocation_status="active",
        revocation_checked_at=revocation_checked_at,
        source_ref=f"{source_kind}://ainir/p5/{evidence_id}",
    )


def _policy_for(
    *,
    provider_id: str,
    policy_id: str,
    source_kind: str,
    signed: bool = False,
) -> dict[str, Any]:
    return build_evidence_provider_policy(
        policy_id=policy_id,
        provider_id=provider_id,
        allowed_provider_versions=[_PROVIDER_VERSION],
        allowed_source_kinds=[source_kind],
        allowed_issuer_ids=[_ISSUER_ID],
        allowed_issuer_kinds=["verifier"],
        allowed_evidence_kinds=["verifier_report"],
        allowed_producer_kinds=["verifier"],
        allowed_signature_key_ids=[_SIGNING_KEY_ID] if signed else [],
        minimum_reliability=0.8,
        require_subject_binding=True,
        require_validity_window=True,
        require_active_revocation=True,
        require_verified_signature=signed,
    )


def _request_for(
    *,
    provider_id: str,
    evidence_id: str,
    draft: DraftModule,
    claim: Mapping[str, Any],
) -> dict[str, Any]:
    return build_evidence_request_from_draft(
        draft,
        claim,
        {"id": evidence_id, "kind": "verifier_report"},
        provider_id=provider_id,
        evaluation_time=_EVALUATION_TIME,
    )


def _report_ok(value: Mapping[str, Any]) -> bool:
    return (
        value.get("overall_status") == "passed"
        and value.get("accepted") is True
        and value.get("candidate_evidence_status") == "validated_candidate"
        and value.get("trust_gate_promotion_allowed") is False
        and value.get("production_runtime_ready") is False
        and validate_evidence_validation_report(value).valid
    )


def run_offline_evidence_provider_check(
    out_dir: str | Path,
    *,
    draft_path: str | Path | None = None,
) -> dict[str, Any]:
    """Exercise fixture, file, and signed-bundle adapters fail-closed.

    The returned status is a release-readiness signal for the bounded public RC,
    not a production-readiness assertion.
    """

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_draft = Path(draft_path) if draft_path is not None else _SAFE_DRAFT
    draft = load_draft(source_draft)
    claim = draft.claims[0]
    checks: list[dict[str, Any]] = []

    def record_check(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "status": "passed" if passed else "failed", **details})

    # Fixture provider: deterministic, in-memory, unsigned.
    fixture_provider_id = "provider.ainir.fixture"
    fixture_policy_id = "policy.ainir.fixture.v1"
    fixture_evidence_id = "evidence.ainir.fixture.safe-outbox"
    fixture_request = _request_for(
        provider_id=fixture_provider_id,
        evidence_id=fixture_evidence_id,
        draft=draft,
        claim=claim,
    )
    fixture_record = _record_for(
        provider_id=fixture_provider_id,
        policy_id=fixture_policy_id,
        source_kind="fixture",
        evidence_id=fixture_evidence_id,
        request=fixture_request,
        draft=draft,
        claim=claim,
    )
    fixture_policy = _policy_for(
        provider_id=fixture_provider_id,
        policy_id=fixture_policy_id,
        source_kind="fixture",
    )
    fixture_provider = FixtureEvidenceProvider.from_records(
        provider_id=fixture_provider_id,
        provider_version=_PROVIDER_VERSION,
        records=[fixture_record],
    )
    fixture_report = resolve_and_validate_evidence(
        fixture_provider,
        fixture_request,
        fixture_policy,
    ).as_dict()
    record_check(
        "fixture_provider_validated_candidate",
        fixture_provider.bundle_validation.valid
        and validate_evidence_provider_policy(fixture_policy).valid
        and _report_ok(fixture_report),
        candidate_status=fixture_report.get("candidate_evidence_status"),
        promotion_allowed=fixture_report.get("trust_gate_promotion_allowed"),
    )

    # File provider: same semantics, but loaded from a root-confined JSON file.
    file_provider_id = "provider.ainir.file"
    file_policy_id = "policy.ainir.file.v1"
    file_evidence_id = "evidence.ainir.file.safe-outbox"
    file_request = _request_for(
        provider_id=file_provider_id,
        evidence_id=file_evidence_id,
        draft=draft,
        claim=claim,
    )
    file_record = _record_for(
        provider_id=file_provider_id,
        policy_id=file_policy_id,
        source_kind="file",
        evidence_id=file_evidence_id,
        request=file_request,
        draft=draft,
        claim=claim,
    )
    file_policy = _policy_for(
        provider_id=file_provider_id,
        policy_id=file_policy_id,
        source_kind="file",
    )
    file_bundle = build_evidence_bundle(
        provider_id=file_provider_id,
        provider_version=_PROVIDER_VERSION,
        source_kind="file",
        records=[file_record],
    )
    file_bundle_path = write_evidence_artifact(output / "file_provider" / "bundle.json", file_bundle)
    file_provider = FileEvidenceProvider(file_bundle_path, allowed_root=output / "file_provider")
    file_report = resolve_and_validate_evidence(file_provider, file_request, file_policy).as_dict()
    record_check(
        "file_provider_root_confined_and_revalidated",
        file_provider.bundle_validation.valid and _report_ok(file_report),
        bundle_path=str(file_bundle_path),
        candidate_status=file_report.get("candidate_evidence_status"),
    )

    # Signed bundle provider: local HMAC integrity only, with exact key-id policy.
    signed_provider_id = "provider.ainir.signed-bundle"
    signed_policy_id = "policy.ainir.signed-bundle.v1"
    signed_evidence_id = "evidence.ainir.signed.safe-outbox"
    signed_request = _request_for(
        provider_id=signed_provider_id,
        evidence_id=signed_evidence_id,
        draft=draft,
        claim=claim,
    )
    signed_record = _record_for(
        provider_id=signed_provider_id,
        policy_id=signed_policy_id,
        source_kind="signed_bundle",
        evidence_id=signed_evidence_id,
        request=signed_request,
        draft=draft,
        claim=claim,
    )
    signed_policy = _policy_for(
        provider_id=signed_provider_id,
        policy_id=signed_policy_id,
        source_kind="signed_bundle",
        signed=True,
    )
    unsigned_bundle = build_evidence_bundle(
        provider_id=signed_provider_id,
        provider_version=_PROVIDER_VERSION,
        source_kind="signed_bundle",
        records=[signed_record],
    )
    signed_bundle = sign_evidence_bundle(
        unsigned_bundle,
        key_id=_SIGNING_KEY_ID,
        key=_SIGNING_KEY,
    )
    signed_bundle_path = write_evidence_artifact(
        output / "signed_provider" / "bundle.json",
        signed_bundle,
    )
    signed_provider = SignedBundleEvidenceProvider(
        signed_bundle_path,
        verification_keys={_SIGNING_KEY_ID: _SIGNING_KEY},
        allowed_root=output / "signed_provider",
    )
    signed_report = resolve_and_validate_evidence(
        signed_provider,
        signed_request,
        signed_policy,
        verification_keys={_SIGNING_KEY_ID: _SIGNING_KEY},
    ).as_dict()
    record_check(
        "signed_bundle_exact_key_policy_and_revalidation",
        signed_provider.signature_status == "verified" and _report_ok(signed_report),
        signature_status=signed_provider.signature_status,
        signature_key_id=signed_provider.signature_key_id,
        candidate_status=signed_report.get("candidate_evidence_status"),
    )

    # Negative: the provider's own verified-signature claim is not enough.
    # The host must supply trusted verification key material independently.
    signed_claim_only_report = resolve_and_validate_evidence(
        signed_provider,
        signed_request,
        signed_policy,
    ).as_dict()
    signed_claim_only_failures = {
        str(item.get("check"))
        for item in signed_claim_only_report.get("checks", [])
        if item.get("status") == "failed"
    }
    record_check(
        "provider_signature_claim_without_host_key_refused",
        signed_claim_only_report.get("accepted") is False
        and "provider_bundle_independent.bundle.signature" in signed_claim_only_failures,
        failed_checks=sorted(signed_claim_only_failures),
    )

    # Negative: a coherently re-hashed outer bundle still cannot hide a modified
    # inner evidence record because each record has its own canonical self-hash.
    tampered_bundle = deepcopy(signed_bundle)
    tampered_bundle["records"][0]["issuer"]["id"] = "issuer.attacker"
    tampered_bundle["bundle_sha256"] = sha256_json(evidence_bundle_projection(tampered_bundle))
    tampered_bundle["bundle_id"] = (
        "ainir.evidence.bundle."
        + str(tampered_bundle["bundle_sha256"]).removeprefix("sha256:")[:20]
    )
    tamper_validation = validate_evidence_bundle(
        tampered_bundle,
        verification_keys={_SIGNING_KEY_ID: _SIGNING_KEY},
        require_signature=True,
    )
    record_check(
        "tampered_inner_record_refused",
        not tamper_validation.valid,
        failed_checks=[
            item.get("check")
            for item in tamper_validation.checks
            if item.get("status") == "failed"
        ],
    )

    # Negative: a provider cannot resolve to a semantically valid record that
    # is absent from the bundle bound by bundle_id/bundle_sha256.
    substituted_record = deepcopy(fixture_record)
    substituted_record["provenance"]["source_ref"] = "fixture://ainir/p5/substituted-record"
    substituted_record["integrity"]["record_sha256"] = sha256_json(
        evidence_record_projection(substituted_record)
    )
    substituted_resolution = fixture_provider.resolve(fixture_request)
    substituted_resolution["record"] = substituted_record
    substituted_resolution["resolution_sha256"] = sha256_json(
        evidence_resolution_projection(substituted_resolution)
    )
    substituted_resolution["resolution_id"] = (
        "ainir.evidence.resolution."
        + str(substituted_resolution["resolution_sha256"]).removeprefix("sha256:")[:20]
    )
    substituted_report = validate_evidence_resolution(
        fixture_request,
        substituted_resolution,
        fixture_policy,
        provider=fixture_provider,
    ).as_dict()
    substituted_failures = {
        str(item.get("check"))
        for item in substituted_report.get("checks", [])
        if item.get("status") == "failed"
    }
    record_check(
        "resolution_record_not_in_bound_bundle_refused",
        substituted_report.get("accepted") is False
        and "provider_bundle.resolution_record_matches_bundle" in substituted_failures,
        failed_checks=sorted(substituted_failures),
    )

    # Negative: expired candidate remains refused even when provider, bundle,
    # and record integrity are internally coherent.
    expired_record = _record_for(
        provider_id=fixture_provider_id,
        policy_id=fixture_policy_id,
        source_kind="fixture",
        evidence_id=fixture_evidence_id,
        request=fixture_request,
        draft=draft,
        claim=claim,
        valid_until=_EVALUATION_TIME,
    )
    expired_provider = FixtureEvidenceProvider.from_records(
        provider_id=fixture_provider_id,
        provider_version=_PROVIDER_VERSION,
        records=[expired_record],
    )
    expired_report = resolve_and_validate_evidence(
        expired_provider,
        fixture_request,
        fixture_policy,
    ).as_dict()
    expired_failures = {
        str(item.get("check"))
        for item in expired_report.get("checks", [])
        if item.get("status") == "failed"
    }
    record_check(
        "expired_candidate_refused",
        expired_report.get("accepted") is False
        and "candidate.validity.not_expired" in expired_failures,
        failed_checks=sorted(expired_failures),
    )

    # Negative: an active revocation state is not sufficient when its host
    # check is older than the policy's maximum freshness window.
    stale_record = _record_for(
        provider_id=fixture_provider_id,
        policy_id=fixture_policy_id,
        source_kind="fixture",
        evidence_id=fixture_evidence_id,
        request=fixture_request,
        draft=draft,
        claim=claim,
        revocation_checked_at="2026-08-08T23:59:59Z",
    )
    stale_provider = FixtureEvidenceProvider.from_records(
        provider_id=fixture_provider_id,
        provider_version=_PROVIDER_VERSION,
        records=[stale_record],
    )
    stale_report = resolve_and_validate_evidence(
        stale_provider,
        fixture_request,
        fixture_policy,
    ).as_dict()
    stale_failures = {
        str(item.get("check"))
        for item in stale_report.get("checks", [])
        if item.get("status") == "failed"
    }
    record_check(
        "stale_revocation_check_refused",
        stale_report.get("accepted") is False
        and "candidate.revocation.check_fresh" in stale_failures,
        failed_checks=sorted(stale_failures),
    )

    # Boundary: a successfully validated P5 candidate is not inserted into the
    # legacy Trust Gate ledger and cannot silently promote the draft.
    raw = deepcopy(draft.raw)
    raw["claims"][0]["evidence"] = [
        {"id": fixture_evidence_id, "kind": "verifier_report"}
    ]
    ordinary_verification = verify_draft(DraftModule(raw=raw))
    ordinary_rules = {finding.rule for finding in ordinary_verification.findings}
    record_check(
        "validated_candidate_not_silently_promoted_to_trust_gate",
        ordinary_verification.status == "blocked"
        and "TR001.verified_claim_requires_ledger_bound_evidence" in ordinary_rules,
        verifier_status=ordinary_verification.status,
        finding_rules=sorted(ordinary_rules),
    )

    artifacts = {
        "fixture_request": fixture_request,
        "fixture_policy": fixture_policy,
        "fixture_bundle": fixture_provider.bundle,
        "fixture_validation_report": fixture_report,
        "file_request": file_request,
        "file_policy": file_policy,
        "file_bundle": file_bundle,
        "file_validation_report": file_report,
        "signed_request": signed_request,
        "signed_policy": signed_policy,
        "signed_bundle": signed_bundle,
        "signed_validation_report": signed_report,
        "signed_claim_only_validation_report": signed_claim_only_report,
        "substituted_record_validation_report": substituted_report,
        "expired_validation_report": expired_report,
        "stale_revocation_validation_report": stale_report,
    }
    for name, value in artifacts.items():
        write_evidence_artifact(output / f"{name}.json", value)

    failed = [item for item in checks if item["status"] != "passed"]
    report = {
        "kind": "AiNIROfflineEvidenceProviderReadinessReport",
        "version": "ainir.offline-evidence-provider-readiness.v1",
        "overall_status": "passed" if not failed else "failed",
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "network_access_used": False,
        "trust_gate_promotion_enabled": False,
        "production_runtime_ready": False,
        "checks": checks,
        "draft_path": str(source_draft),
        "output_dir": str(output),
    }
    write_evidence_artifact(output / "offline_evidence_provider_readiness_report.json", report)
    return report


__all__ = ["run_offline_evidence_provider_check"]
