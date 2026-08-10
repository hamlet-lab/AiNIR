from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import ainir
from ainir.canonical import sha256_json
from ainir.core import DraftModule, load_draft
from ainir.evidence_provider import (
    EvidenceProviderError,
    FileEvidenceProvider,
    FixtureEvidenceProvider,
    SignedBundleEvidenceProvider,
    build_evidence_bundle,
    build_evidence_provider_policy,
    build_evidence_record,
    build_evidence_request,
    build_evidence_request_from_draft,
    evidence_bundle_projection,
    evidence_record_projection,
    load_evidence_bundle,
    resolve_and_validate_evidence,
    sign_evidence_bundle,
    validate_evidence_bundle,
    validate_evidence_provider_policy,
    validate_evidence_resolution,
    validate_evidence_validation_report,
    write_evidence_artifact,
)
from ainir.resources import PUBLIC_SCHEMA_NAMES, read_schema_text
from ainir.offline_evidence_provider_eval import run_offline_evidence_provider_check
from ainir.verifier import verify_draft


ROOT = Path(__file__).resolve().parents[1]
SAFE = ROOT / "examples/create_user_outbox_safe/draft.yaml"
EVALUATION_TIME = "2026-08-10T00:00:00Z"
VALID_FROM = "2026-08-01T00:00:00Z"
VALID_UNTIL = "2026-09-01T00:00:00Z"
PROVIDER_ID = "provider.p5.fixture"
PROVIDER_VERSION = "1.0"
POLICY_ID = "policy.p5.fixture.v1"
ISSUER_ID = "issuer.p5.verifier"
EVIDENCE_ID = "evidence.p5.safe_outbox"
SIGNING_KEY_ID = "key.p5.test"
SIGNING_KEY = sha256(b"AiNIR P5 deterministic test key material").digest()


def _run_cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "ainir", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )


def _draft_and_claim():
    draft = load_draft(SAFE)
    claim = draft.claims[0]
    return draft, claim


def _request(*, provider_id: str = PROVIDER_ID, evidence_id: str = EVIDENCE_ID):
    draft, claim = _draft_and_claim()
    return build_evidence_request_from_draft(
        draft,
        claim,
        {"id": evidence_id, "kind": "verifier_report"},
        provider_id=provider_id,
        evaluation_time=EVALUATION_TIME,
    )


def _record(
    *,
    provider_id: str = PROVIDER_ID,
    provider_version: str = PROVIDER_VERSION,
    source_kind: str = "fixture",
    policy_id: str = POLICY_ID,
    issuer_id: str = ISSUER_ID,
    issuer_kind: str = "verifier",
    producer_kind: str = "verifier",
    evidence_id: str = EVIDENCE_ID,
    reliability: float = 0.95,
    valid_from: str | None = VALID_FROM,
    valid_until: str | None = VALID_UNTIL,
    revocation_status: str = "active",
    revocation_checked_at: str | None = "2026-08-09T00:00:00Z",
    subject_binding_mode: str = "canonical",
    module_id: str | None = None,
    workflow: str | None = None,
    claim_ids: list[str] | None = None,
    claim_statement_sha256: str | None = None,
):
    draft, claim = _draft_and_claim()
    request = _request(provider_id=provider_id, evidence_id=evidence_id)
    return build_evidence_record(
        evidence_id=evidence_id,
        evidence_kind="verifier_report",
        issuer_id=issuer_id,
        issuer_kind=issuer_kind,
        producer_kind=producer_kind,
        policy_version=policy_id,
        module_id=module_id or draft.module_id,
        workflow=workflow or draft.workflow,
        claim_ids=claim_ids or [claim["id"]],
        claim_statement_sha256=claim_statement_sha256 or request["claim_scope"]["claim_statement_sha256"],
        provider_id=provider_id,
        provider_version=provider_version,
        source_kind=source_kind,
        reliability=reliability,
        minimum_reliability=0.8,
        subject_binding_mode=subject_binding_mode,
        raw_source_sha256=request["subject_binding"]["raw_source_sha256"] if subject_binding_mode in {"raw", "raw_or_canonical"} else None,
        canonical_draft_sha256=request["subject_binding"]["canonical_draft_sha256"] if subject_binding_mode in {"canonical", "raw_or_canonical"} else None,
        valid_from=valid_from,
        valid_until=valid_until,
        revocation_status=revocation_status,
        revocation_checked_at=revocation_checked_at,
        source_ref="fixture://p5/safe-outbox",
    )


def _policy(
    *,
    provider_id: str = PROVIDER_ID,
    source_kind: str = "fixture",
    policy_id: str = POLICY_ID,
    require_signature: bool = False,
    allowed_key_ids: tuple[str, ...] = (),
    max_revocation_age_seconds: int = 86_400,
):
    return build_evidence_provider_policy(
        policy_id=policy_id,
        provider_id=provider_id,
        allowed_provider_versions=[PROVIDER_VERSION],
        allowed_source_kinds=[source_kind],
        allowed_issuer_ids=[ISSUER_ID],
        allowed_issuer_kinds=["verifier"],
        allowed_evidence_kinds=["verifier_report"],
        allowed_producer_kinds=["verifier"],
        allowed_signature_key_ids=allowed_key_ids,
        minimum_reliability=0.8,
        require_subject_binding=True,
        require_validity_window=True,
        require_active_revocation=True,
        max_revocation_age_seconds=max_revocation_age_seconds,
        require_verified_signature=require_signature,
    )


def _fixture_provider(record: dict | None = None):
    return FixtureEvidenceProvider.from_records(
        provider_id=PROVIDER_ID,
        provider_version=PROVIDER_VERSION,
        records=[record or _record()],
    )


def _failed_checks(report: dict) -> set[str]:
    return {str(item.get("check")) for item in report.get("checks", []) if item.get("status") == "failed"}


def test_p5_contracts_and_schemas_are_public_and_packaged() -> None:
    assert ainir.EVIDENCE_REQUEST_CONTRACT == "ainir.evidence-request.v1"
    assert ainir.EVIDENCE_RECORD_CONTRACT == "ainir.evidence-record.v1"
    assert ainir.EVIDENCE_PROVIDER_POLICY_CONTRACT == "ainir.evidence-provider-policy.v1"
    assert ainir.EVIDENCE_BUNDLE_CONTRACT == "ainir.evidence-bundle.v1"
    assert ainir.EVIDENCE_RESOLUTION_CONTRACT == "ainir.evidence-resolution.v1"
    assert ainir.EVIDENCE_VALIDATION_REPORT_CONTRACT == "ainir.evidence-validation-report.v1"
    names = {
        "evidence_request.schema.json",
        "evidence_record.schema.json",
        "evidence_provider_policy.schema.json",
        "evidence_bundle.schema.json",
        "evidence_resolution.schema.json",
        "evidence_validation_report.schema.json",
    }
    assert names <= set(PUBLIC_SCHEMA_NAMES)
    for name in names:
        assert json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert (ROOT / "schemas" / name).read_bytes() == (ROOT / "src/ainir/schemas" / name).read_bytes()
        assert read_schema_text(name) == (ROOT / "schemas" / name).read_text(encoding="utf-8")


def test_fixture_provider_resolution_is_revalidated_and_not_promoted() -> None:
    provider = _fixture_provider()
    policy = _policy()
    request = _request()
    resolution = provider.resolve(request)
    report = validate_evidence_resolution(request, resolution, policy, provider=provider).as_dict()
    assert provider.bundle_validation.valid
    assert validate_evidence_provider_policy(policy).valid
    assert report["accepted"] is True
    assert report["candidate_evidence_status"] == "validated_candidate"
    assert report["trust_gate_promotion_allowed"] is False
    assert report["production_runtime_ready"] is False
    assert validate_evidence_validation_report(report).valid

    # P5 provider validation does not silently insert the record into the Trust
    # Gate ledger. The same external id remains untrusted in an ordinary draft.
    draft, _ = _draft_and_claim()
    raw = deepcopy(draft.raw)
    raw["claims"][0]["evidence"] = [{"id": EVIDENCE_ID, "kind": "verifier_report"}]
    verification = verify_draft(DraftModule(raw=raw))
    assert verification.status == "blocked"
    assert "TR001.verified_claim_requires_ledger_bound_evidence" in {finding.rule for finding in verification.findings}


def test_provider_output_cannot_self_assert_trust_or_add_unknown_fields() -> None:
    provider = _fixture_provider()
    policy = _policy()
    request = _request()
    resolution = provider.resolve(request)
    tampered = deepcopy(resolution)
    tampered["trusted"] = True
    tampered["record"]["checked"] = True
    # Keep the outer resolution hash coherent to prove semantic validation, not
    # only hash mismatch, rejects the unknown trust assertions.
    from ainir.evidence_provider import evidence_resolution_projection
    tampered["resolution_sha256"] = sha256_json(evidence_resolution_projection(tampered))
    tampered["resolution_id"] = "ainir.evidence.resolution." + tampered["resolution_sha256"].removeprefix("sha256:")[:20]
    report = validate_evidence_resolution(request, tampered, policy, provider=provider).as_dict()
    assert report["accepted"] is False
    failed = _failed_checks(report)
    assert "resolution.unknown_fields" in failed
    assert "candidate.record.unknown_fields" in failed


@pytest.mark.parametrize(
    ("record", "expected_check"),
    [
        (_record(issuer_id="issuer.untrusted"), "candidate.policy.issuer_id"),
        (_record(module_id="demo.other"), "candidate.claim_scope.module_id"),
        (_record(claim_ids=["claim.other"]), "candidate.claim_scope.claim_id"),
        (_record(claim_statement_sha256="sha256:" + "0" * 64), "candidate.claim_scope.statement"),
        (_record(reliability=0.5), "candidate.reliability"),
        (_record(valid_until="2026-08-10T00:00:00Z"), "candidate.validity.not_expired"),
        (_record(valid_from="2026-08-11T00:00:00Z"), "candidate.validity.not_before"),
        (_record(revocation_status="revoked"), "candidate.revocation.active"),
        (_record(revocation_checked_at=None), "candidate.revocation.checked_at_present"),
        (_record(revocation_checked_at="2026-08-11T00:00:00Z"), "candidate.revocation.checked_at_not_future"),
        (_record(revocation_checked_at="2026-08-08T23:59:59Z"), "candidate.revocation.check_fresh"),
        (_record(subject_binding_mode="none"), "candidate.subject_binding"),
    ],
)
def test_semantic_candidate_failures_are_fail_closed(record: dict, expected_check: str) -> None:
    provider = _fixture_provider(record)
    report = resolve_and_validate_evidence(provider, _request(), _policy()).as_dict()
    assert report["accepted"] is False
    assert expected_check in _failed_checks(report)
    assert validate_evidence_validation_report(report).valid


def test_record_policy_version_and_provider_identity_are_exactly_bound() -> None:
    record = _record(policy_id="policy.other.v1")
    provider = _fixture_provider(record)
    report = resolve_and_validate_evidence(provider, _request(), _policy()).as_dict()
    assert report["accepted"] is False
    assert "candidate.policy.policy_version" in _failed_checks(report)

    wrong_provider_record = _record(provider_id="provider.other")
    bundle = build_evidence_bundle(
        provider_id=PROVIDER_ID,
        provider_version=PROVIDER_VERSION,
        source_kind="fixture",
        records=[wrong_provider_record],
    )
    validation = validate_evidence_bundle(bundle)
    assert not validation.valid
    assert any("provider_binding" in item["check"] for item in validation.checks if item["status"] == "failed")


def test_bundle_hash_record_hash_and_duplicate_id_tampering_are_rejected() -> None:
    record = _record()
    bundle = build_evidence_bundle(
        provider_id=PROVIDER_ID,
        provider_version=PROVIDER_VERSION,
        source_kind="fixture",
        records=[record],
    )
    assert validate_evidence_bundle(bundle).valid

    record_tamper = deepcopy(bundle)
    record_tamper["records"][0]["issuer"]["id"] = "issuer.attacker"
    record_tamper["bundle_sha256"] = sha256_json(evidence_bundle_projection(record_tamper))
    record_tamper["bundle_id"] = "ainir.evidence.bundle." + record_tamper["bundle_sha256"].removeprefix("sha256:")[:20]
    report = validate_evidence_bundle(record_tamper)
    assert not report.valid
    assert any("record.integrity.record_sha256" in item["check"] for item in report.checks if item["status"] == "failed")

    boolean_reliability = deepcopy(bundle)
    boolean_reliability["records"][0]["reliability"]["score"] = True
    boolean_reliability["records"][0]["integrity"]["record_sha256"] = sha256_json(
        evidence_record_projection(boolean_reliability["records"][0])
    )
    boolean_reliability["bundle_sha256"] = sha256_json(
        evidence_bundle_projection(boolean_reliability)
    )
    boolean_reliability["bundle_id"] = (
        "ainir.evidence.bundle."
        + boolean_reliability["bundle_sha256"].removeprefix("sha256:")[:20]
    )
    report = validate_evidence_bundle(boolean_reliability)
    assert not report.valid
    assert any(
        "record.reliability.score" in item["check"]
        for item in report.checks
        if item["status"] == "failed"
    )

    duplicate = build_evidence_bundle(
        provider_id=PROVIDER_ID,
        provider_version=PROVIDER_VERSION,
        source_kind="fixture",
        records=[record, record],
    )
    report = validate_evidence_bundle(duplicate)
    assert not report.valid
    assert any(item["check"] == "bundle.unique_evidence_ids" for item in report.checks if item["status"] == "failed")

    outer_tamper = deepcopy(bundle)
    outer_tamper["provider_version"] = "2.0"
    assert not validate_evidence_bundle(outer_tamper).valid


def test_file_provider_is_bounded_duplicate_safe_and_root_confined(tmp_path: Path) -> None:
    provider_id = "provider.p5.file"
    policy_id = "policy.p5.file.v1"
    record = _record(provider_id=provider_id, source_kind="file", policy_id=policy_id)
    bundle = build_evidence_bundle(
        provider_id=provider_id,
        provider_version=PROVIDER_VERSION,
        source_kind="file",
        records=[record],
    )
    path = write_evidence_artifact(tmp_path / "allowed" / "bundle.json", bundle)
    provider = FileEvidenceProvider(path, allowed_root=tmp_path / "allowed")
    policy = _policy(provider_id=provider_id, source_kind="file", policy_id=policy_id)
    request = _request(provider_id=provider_id)
    assert resolve_and_validate_evidence(provider, request, policy).accepted

    with pytest.raises(EvidenceProviderError, match="escapes the allowed root"):
        FileEvidenceProvider(path, allowed_root=tmp_path / "other")

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"kind":"AiNIREvidenceBundle","kind":"duplicate"}', encoding="utf-8")
    with pytest.raises(EvidenceProviderError, match="duplicate"):
        load_evidence_bundle(duplicate)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * 1_000_001 + b"}")
    with pytest.raises(EvidenceProviderError, match="exceeds"):
        load_evidence_bundle(oversized)

    nonfinite = tmp_path / "nonfinite.yaml"
    nonfinite.write_text("value: .nan\n", encoding="utf-8")
    with pytest.raises(EvidenceProviderError, match="non-finite"):
        load_evidence_bundle(nonfinite)


def test_signed_bundle_requires_allowed_verified_key_and_detects_tampering(tmp_path: Path) -> None:
    provider_id = "provider.p5.signed"
    policy_id = "policy.p5.signed.v1"
    record = _record(provider_id=provider_id, source_kind="signed_bundle", policy_id=policy_id)
    unsigned = build_evidence_bundle(
        provider_id=provider_id,
        provider_version=PROVIDER_VERSION,
        source_kind="signed_bundle",
        records=[record],
    )
    signed = sign_evidence_bundle(unsigned, key_id=SIGNING_KEY_ID, key=SIGNING_KEY)
    path = write_evidence_artifact(tmp_path / "signed.json", signed)
    provider = SignedBundleEvidenceProvider(path, verification_keys={SIGNING_KEY_ID: SIGNING_KEY})
    policy = _policy(
        provider_id=provider_id,
        source_kind="signed_bundle",
        policy_id=policy_id,
        require_signature=True,
        allowed_key_ids=(SIGNING_KEY_ID,),
    )
    request = _request(provider_id=provider_id)
    no_host_key_report = resolve_and_validate_evidence(provider, request, policy).as_dict()
    assert no_host_key_report["accepted"] is False
    assert "provider_bundle_independent.bundle.signature" in _failed_checks(no_host_key_report)

    malformed_host_key_report = resolve_and_validate_evidence(
        provider,
        request,
        policy,
        verification_keys={SIGNING_KEY_ID: "not-bytes"},  # type: ignore[dict-item]
    ).as_dict()
    assert malformed_host_key_report["accepted"] is False
    assert "provider_bundle_independent.bundle.signature" in _failed_checks(malformed_host_key_report)

    report = resolve_and_validate_evidence(
        provider,
        request,
        policy,
        verification_keys={SIGNING_KEY_ID: SIGNING_KEY},
    ).as_dict()
    assert report["accepted"] is True
    assert report["signature_status"] == "verified"

    wrong_policy = _policy(
        provider_id=provider_id,
        source_kind="signed_bundle",
        policy_id=policy_id,
        require_signature=True,
        allowed_key_ids=("key.other",),
    )
    refused = resolve_and_validate_evidence(
        provider,
        request,
        wrong_policy,
        verification_keys={SIGNING_KEY_ID: SIGNING_KEY},
    ).as_dict()
    assert refused["accepted"] is False
    assert "resolution.signature_key_id" in _failed_checks(refused)

    with pytest.raises(EvidenceProviderError, match="at least 16 bytes"):
        sign_evidence_bundle(unsigned, key_id=SIGNING_KEY_ID, key=b"short")

    wrong_key_provider = SignedBundleEvidenceProvider(
        path,
        verification_keys={SIGNING_KEY_ID: sha256(b"wrong key").digest()},
    )
    assert not wrong_key_provider.bundle_validation.valid
    wrong_key = sha256(b"wrong key").digest()
    refused = resolve_and_validate_evidence(
        wrong_key_provider,
        request,
        policy,
        verification_keys={SIGNING_KEY_ID: wrong_key},
    ).as_dict()
    assert refused["accepted"] is False

    tampered = deepcopy(signed)
    tampered["records"][0]["reliability"]["score"] = 1.0
    tampered_path = write_evidence_artifact(tmp_path / "tampered.json", tampered)
    tampered_provider = SignedBundleEvidenceProvider(
        tampered_path,
        verification_keys={SIGNING_KEY_ID: SIGNING_KEY},
    )
    assert not tampered_provider.bundle_validation.valid


def test_custom_provider_cannot_self_attest_signature_or_bundle_validation() -> None:
    provider_id = "provider.p5.malicious-signed"
    policy_id = "policy.p5.malicious-signed.v1"
    record = _record(provider_id=provider_id, source_kind="signed_bundle", policy_id=policy_id)
    unsigned = build_evidence_bundle(
        provider_id=provider_id,
        provider_version=PROVIDER_VERSION,
        source_kind="signed_bundle",
        records=[record],
    )
    # Simulate a custom provider lying about a signature and its own validation.
    from ainir.evidence_provider import _BundleEvidenceProvider

    malicious = _BundleEvidenceProvider(unsigned, require_signature=False)
    malicious.signature_status = "verified"
    malicious.signature_key_id = SIGNING_KEY_ID
    request = _request(provider_id=provider_id)
    resolution = malicious.resolve(request)
    policy = _policy(
        provider_id=provider_id,
        source_kind="signed_bundle",
        policy_id=policy_id,
        require_signature=True,
        allowed_key_ids=(SIGNING_KEY_ID,),
    )
    report = validate_evidence_resolution(
        request,
        resolution,
        policy,
        provider=malicious,
        verification_keys={},
    ).as_dict()
    assert report["accepted"] is False
    failed = _failed_checks(report)
    assert "provider_bundle_independent.bundle.signature" in failed
    assert "provider_bundle.signature_status_recomputed" in failed
    assert "provider_bundle.claimed_validation_matches_independent" in failed


def test_resolution_record_must_be_the_unique_record_from_the_provider_bundle() -> None:
    provider = _fixture_provider()
    policy = _policy()
    request = _request()
    resolution = provider.resolve(request)
    replacement = _record(reliability=0.99)
    assert replacement != provider.bundle["records"][0]
    tampered = deepcopy(resolution)
    tampered["record"] = replacement
    from ainir.evidence_provider import evidence_resolution_projection

    tampered["resolution_sha256"] = sha256_json(evidence_resolution_projection(tampered))
    tampered["resolution_id"] = "ainir.evidence.resolution." + tampered["resolution_sha256"].removeprefix("sha256:")[:20]
    report = validate_evidence_resolution(request, tampered, policy, provider=provider).as_dict()
    assert report["accepted"] is False
    assert "provider_bundle.resolution_record_matches_bundle" in _failed_checks(report)


def test_resolution_validation_requires_original_provider_bundle_context() -> None:
    provider = _fixture_provider()
    request = _request()
    report = validate_evidence_resolution(request, provider.resolve(request), _policy()).as_dict()
    assert report["accepted"] is False
    assert "provider_context_present" in _failed_checks(report)


def test_policy_cannot_enable_trust_gate_promotion_or_unbounded_source() -> None:
    policy = _policy()
    policy["allow_trust_gate_promotion"] = True
    policy["policy_sha256"] = sha256_json({k: v for k, v in policy.items() if k != "policy_sha256"})
    report = validate_evidence_provider_policy(policy)
    assert not report.valid
    assert any(item["check"] == "policy.allow_trust_gate_promotion" for item in report.checks if item["status"] == "failed")

    unbounded = _policy()
    unbounded["allowed_source_kinds"].append("network")
    unbounded["policy_sha256"] = sha256_json({k: v for k, v in unbounded.items() if k != "policy_sha256"})
    assert not validate_evidence_provider_policy(unbounded).valid

    for invalid_age in (0, 31_536_001, True, 1.5):
        invalid_freshness = _policy(max_revocation_age_seconds=invalid_age)
        validation = validate_evidence_provider_policy(invalid_freshness)
        assert not validation.valid
        assert any(
            item["check"] == "policy.max_revocation_age_seconds"
            for item in validation.checks
            if item["status"] == "failed"
        )

    boolean_reliability = _policy()
    boolean_reliability["minimum_reliability"] = True
    boolean_reliability["policy_sha256"] = sha256_json(
        {k: v for k, v in boolean_reliability.items() if k != "policy_sha256"}
    )
    validation = validate_evidence_provider_policy(boolean_reliability)
    assert not validation.valid
    assert any(
        item["check"] == "policy.minimum_reliability"
        for item in validation.checks
        if item["status"] == "failed"
    )


def test_request_and_resolution_identity_tampering_is_rejected() -> None:
    provider = _fixture_provider()
    policy = _policy()
    request = _request()
    resolution = provider.resolve(request)

    tampered_request = deepcopy(request)
    tampered_request["claim_scope"]["workflow"] = "OtherWorkflow"
    report = validate_evidence_resolution(tampered_request, resolution, policy, provider=provider).as_dict()
    assert report["accepted"] is False
    assert "request.request_id" in _failed_checks(report)

    tampered_resolution = deepcopy(resolution)
    tampered_resolution["bundle_sha256"] = "sha256:" + "0" * 64
    report = validate_evidence_resolution(request, tampered_resolution, policy, provider=provider).as_dict()
    assert report["accepted"] is False
    assert {"resolution.resolution_sha256", "provider_bundle.bundle_sha256"} <= _failed_checks(report)


def test_evidence_cli_validates_bundle_policy_and_resolution(tmp_path: Path) -> None:
    provider_id = "provider.p5.file"
    policy_id = "policy.p5.file.v1"
    record = _record(provider_id=provider_id, source_kind="file", policy_id=policy_id)
    bundle = build_evidence_bundle(
        provider_id=provider_id,
        provider_version=PROVIDER_VERSION,
        source_kind="file",
        records=[record],
    )
    policy = _policy(provider_id=provider_id, source_kind="file", policy_id=policy_id)
    bundle_path = write_evidence_artifact(tmp_path / "bundle.json", bundle)
    policy_path = write_evidence_artifact(tmp_path / "policy.json", policy)

    bundle_cli = _run_cli("evidence", "bundle", str(bundle_path), "--json")
    assert bundle_cli.returncode == 0, bundle_cli.stderr
    assert json.loads(bundle_cli.stdout)["overall_status"] == "passed"

    policy_cli = _run_cli("evidence", "policy", str(policy_path), "--json")
    assert policy_cli.returncode == 0, policy_cli.stderr
    assert json.loads(policy_cli.stdout)["overall_status"] == "passed"

    out = tmp_path / "reports"
    resolve_cli = _run_cli(
        "evidence", "resolve", str(bundle_path), str(policy_path), str(SAFE),
        "--claim-id", "claim.create_user_uses_outbox",
        "--evidence-id", EVIDENCE_ID,
        "--expected-kind", "verifier_report",
        "--evaluation-time", EVALUATION_TIME,
        "--out-dir", str(out),
        "--json",
    )
    assert resolve_cli.returncode == 0, resolve_cli.stderr
    report = json.loads(resolve_cli.stdout)
    assert report["accepted"] is True
    assert report["trust_gate_promotion_allowed"] is False
    assert (out / "evidence_request.json").is_file()
    assert (out / "evidence_resolution.json").is_file()
    assert (out / "evidence_validation_report.json").is_file()
    assert validate_evidence_validation_report(json.loads((out / "evidence_validation_report.json").read_text())).valid


def test_p5_json_schemas_validate_reference_artifacts() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    provider = _fixture_provider()
    policy = _policy()
    request = _request()
    resolution = provider.resolve(request)
    report = validate_evidence_resolution(request, resolution, policy, provider=provider).as_dict()
    artifacts = {
        "evidence_request.schema.json": request,
        "evidence_record.schema.json": provider.bundle["records"][0],
        "evidence_provider_policy.schema.json": policy,
        "evidence_bundle.schema.json": provider.bundle,
        "evidence_resolution.schema.json": resolution,
        "evidence_validation_report.schema.json": report,
    }
    for name, artifact in artifacts.items():
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(artifact, schema)


def test_signed_policy_requires_an_explicit_allowed_key_id() -> None:
    policy = _policy(
        source_kind="signed_bundle",
        require_signature=True,
        allowed_key_ids=(),
    )
    validation = validate_evidence_provider_policy(policy)
    assert not validation.valid
    assert any(
        item["check"] == "policy.signature_key_ids_required"
        for item in validation.checks
        if item["status"] == "failed"
    )


def test_offline_readiness_check_covers_all_adapters_and_no_promotion(tmp_path: Path) -> None:
    report = run_offline_evidence_provider_check(tmp_path / "readiness", draft_path=SAFE)
    assert report["overall_status"] == "passed"
    assert report["checks_total"] == 9
    assert report["checks_passed"] == 9
    assert report["network_access_used"] is False
    assert report["trust_gate_promotion_enabled"] is False
    assert report["production_runtime_ready"] is False
    assert (tmp_path / "readiness" / "offline_evidence_provider_readiness_report.json").is_file()


def test_p5_release_ci_distribution_and_public_example_are_wired() -> None:
    manifest = yaml.safe_load((ROOT / "release/v1_0_rc_candidate_manifest.yaml").read_text(encoding="utf-8"))
    p5 = manifest["p5_offline_evidence_providers"]
    assert len(p5) == 18
    assert all(value is True for value in p5.values())

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution_contracts.py").read_text(encoding="utf-8")
    phase30 = (ROOT / "src/ainir/phase30_v1_rc_candidate.py").read_text(encoding="utf-8")
    assert "Validate offline EvidenceProvider contracts and no-auto-promotion boundary" in workflow
    assert "tests/test_p5_offline_evidence_providers.py" in workflow
    assert "installed_wheel_offline_evidence_providers" in distribution
    assert "offline_evidence_providers" in phase30

    bundle = ROOT / "examples/offline_evidence_provider/bundle.json"
    policy = ROOT / "examples/offline_evidence_provider/policy.json"
    assert validate_evidence_bundle(json.loads(bundle.read_text(encoding="utf-8"))).valid
    assert validate_evidence_provider_policy(json.loads(policy.read_text(encoding="utf-8"))).valid
