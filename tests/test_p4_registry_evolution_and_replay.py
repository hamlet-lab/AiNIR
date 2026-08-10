from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import ainir
from ainir.canonical import sha256_bytes, sha256_json
from ainir.contract_validation import validate_replay_report
from ainir.contracts import (
    REGISTRY_DIFF_CONTRACT,
    REGISTRY_MIGRATION_RECORD_CONTRACT,
    REGISTRY_SNAPSHOT_CONTRACT,
    TRUST_RECEIPT_CONTRACT,
)
from ainir.execution_context import TrustedExecutionContext
from ainir.profile_manifest import initialize_profile, load_profile_manifest
from ainir.profile_runtime import compile_profile, profile_registry_context
from ainir.registry_evolution import (
    RegistryEvolutionError,
    _snapshot_projection,
    build_registry_snapshot,
    capture_registry_snapshot,
    create_registry_migration_record,
    diff_registry_snapshots,
    load_registry_snapshot,
    validate_registry_diff,
    validate_registry_migration_record,
    validate_registry_snapshot,
    write_registry_migration_record,
    write_registry_snapshot,
)
from ainir.registry_replay import (
    CURRENT_REGISTRY_REPLAY,
    EXACT_SNAPSHOT_REPLAY,
    MIGRATED_REGISTRY_REPLAY,
    replay_trust_receipt_mode,
)
from ainir.resources import PUBLIC_SCHEMA_NAMES, read_schema_text
from ainir.trust_receipt_store import issue_trust_receipt


ROOT = Path(__file__).resolve().parents[1]
SAFE = ROOT / "examples/create_user_outbox_safe/draft.yaml"
P3_BASE_REGISTRY_HASH = "sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a"


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


def _components(snapshot: dict) -> dict:
    return {
        name: deepcopy(item["data"])
        for name, item in snapshot["components"].items()
    }


def _mutated_snapshot(source: dict, mutate) -> dict:
    components = _components(source)
    mutate(components)
    return build_registry_snapshot(
        components,
        parent_snapshot_hash=source["snapshot_sha256"],
    )


def _issue_stable(tmp_path: Path, draft: Path = SAFE):
    return issue_trust_receipt(
        draft,
        tmp_path,
        TrustedExecutionContext.public_demo(),
        contract_version=TRUST_RECEIPT_CONTRACT,
    )


def _generated_profile(tmp_path: Path):
    root = tmp_path / "profile"
    manifest_path, pack_path, _ = initialize_profile(
        root,
        profile_id="example.registry-evolution.v1",
        workflow_id="RegistryEvolutionExample",
    )
    manifest = load_profile_manifest(manifest_path)
    compiled = compile_profile(manifest)
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    draft_path = root / "positive.yaml"
    draft_path.write_text(yaml.safe_dump(pack["cases"][0]["draft"], sort_keys=False), encoding="utf-8")
    return compiled, draft_path


def test_p4_contracts_are_public_and_packaged() -> None:
    assert ainir.REGISTRY_SNAPSHOT_CONTRACT == REGISTRY_SNAPSHOT_CONTRACT
    assert ainir.REGISTRY_DIFF_CONTRACT == REGISTRY_DIFF_CONTRACT
    assert ainir.REGISTRY_MIGRATION_RECORD_CONTRACT == REGISTRY_MIGRATION_RECORD_CONTRACT
    expected = {
        "registry_snapshot.schema.json",
        "registry_diff.schema.json",
        "registry_migration_record.schema.json",
    }
    assert expected <= set(PUBLIC_SCHEMA_NAMES)
    for name in expected:
        assert json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert (ROOT / "schemas" / name).read_bytes() == (ROOT / "src/ainir/schemas" / name).read_bytes()
        assert read_schema_text(name) == (ROOT / "schemas" / name).read_text(encoding="utf-8")


def test_snapshot_is_deterministic_portable_and_self_validating() -> None:
    first = capture_registry_snapshot()
    second = capture_registry_snapshot()
    assert first == second
    assert first["version"] == REGISTRY_SNAPSHOT_CONTRACT
    assert first["runtime_registry_snapshot_hash"] == P3_BASE_REGISTRY_HASH
    assert first["snapshot_sha256"].startswith("sha256:")
    assert first["runtime_registry_snapshot_hash"] == first["runtime_snapshot"]["combined_sha256"]
    assert validate_registry_snapshot(first).valid
    for name, component in first["components"].items():
        assert component["canonical_sha256"] == first["runtime_snapshot"]["items"][name]["canonical_sha256"]


def test_snapshot_rejects_component_data_hidden_under_unrelated_runtime_hash() -> None:
    original = capture_registry_snapshot()
    tampered = deepcopy(original)
    data = tampered["components"]["safety_registry"]["data"]
    data["allowed_external_effects"].append("effect.external.notification.email.real")
    tampered["components"]["safety_registry"]["canonical_sha256"] = sha256_json(data)
    tampered["snapshot_sha256"] = sha256_json(_snapshot_projection(tampered))
    tampered["snapshot_id"] = "ainir.registry.snapshot." + tampered["snapshot_sha256"].removeprefix("sha256:")[:20]
    report = validate_registry_snapshot(tampered)
    assert not report.valid
    assert any(check["check"] == "snapshot.runtime_component_bindings" for check in report.checks if check["status"] == "failed")
    with pytest.raises(RegistryEvolutionError, match="does not bind"):
        build_registry_snapshot(_components(tampered), runtime_snapshot=original["runtime_snapshot"])


def test_snapshot_rejects_duplicate_registry_ids_and_outer_hash_tampering() -> None:
    original = capture_registry_snapshot()
    duplicate = _components(original)
    duplicate["operation_spec_registry"]["operations"].append(
        deepcopy(duplicate["operation_spec_registry"]["operations"][0])
    )
    snapshot = build_registry_snapshot(duplicate)
    report = validate_registry_snapshot(snapshot)
    assert not report.valid
    assert any("duplicate_ids" in check["check"] for check in report.checks if check["status"] == "failed")

    outer = deepcopy(original)
    outer["profile_id"] = "tampered.profile"
    outer["snapshot_sha256"] = sha256_json(_snapshot_projection(outer))
    outer["snapshot_id"] = "ainir.registry.snapshot." + outer["snapshot_sha256"].removeprefix("sha256:")[:20]
    report = validate_registry_snapshot(outer)
    assert not report.valid
    assert any(check["check"] == "snapshot.profile_binding" for check in report.checks if check["status"] == "failed")
    with pytest.raises(RegistryEvolutionError):
        load_registry_snapshot(outer)

    with pytest.raises(RegistryEvolutionError, match="profile_id must exactly match"):
        build_registry_snapshot(
            _components(original),
            runtime_snapshot=original["runtime_snapshot"],
            profile_id="spoofed.profile.v1",
        )

    unknown_top = deepcopy(original)
    unknown_top["unreviewed_extension"] = {"allow": True}
    unknown_top["snapshot_sha256"] = sha256_json(_snapshot_projection(unknown_top))
    unknown_top["snapshot_id"] = "ainir.registry.snapshot." + unknown_top["snapshot_sha256"].removeprefix("sha256:")[:20]
    assert any(
        check["check"] == "snapshot.unknown_fields" and check["status"] == "failed"
        for check in validate_registry_snapshot(unknown_top).checks
    )

    unknown_runtime = deepcopy(original)
    unknown_runtime["runtime_snapshot"]["unreviewed_policy"] = "allow"
    unknown_runtime["snapshot_sha256"] = sha256_json(_snapshot_projection(unknown_runtime))
    unknown_runtime["snapshot_id"] = "ainir.registry.snapshot." + unknown_runtime["snapshot_sha256"].removeprefix("sha256:")[:20]
    assert any(
        check["check"] == "snapshot.runtime_snapshot.unknown_fields" and check["status"] == "failed"
        for check in validate_registry_snapshot(unknown_runtime).checks
    )


def test_registry_diff_classifies_identity_and_semantic_directions() -> None:
    source = capture_registry_snapshot()
    identity = diff_registry_snapshots(source, source).as_dict()
    assert identity["version"] == REGISTRY_DIFF_CONTRACT
    assert identity["overall_classification"] == "compatible"
    assert identity["change_count"] == 0
    assert not identity["requires_explicit_migration"]
    assert validate_registry_diff(identity).valid

    tampered_identity = deepcopy(identity)
    tampered_identity["overall_classification"] = "relaxation"
    assert not validate_registry_diff(tampered_identity).valid

    unknown_diff = deepcopy(identity)
    unknown_diff["automatic_allow"] = True
    assert any(
        check["check"] == "diff.unknown_fields" and check["status"] == "failed"
        for check in validate_registry_diff(unknown_diff).checks
    )

    metadata = _mutated_snapshot(source, lambda c: c["safety_registry"].__setitem__("version", "reviewed-metadata-v2"))
    assert diff_registry_snapshots(source, metadata).overall_classification == "compatible"

    relaxation = _mutated_snapshot(
        source,
        lambda c: c["safety_registry"]["allowed_external_effects"].append("effect.external.notification.email.real"),
    )
    assert diff_registry_snapshots(source, relaxation).overall_classification == "relaxation"

    def tighten(components):
        operation = next(item for item in components["operation_spec_registry"]["operations"] if item["id"] == "data.normalize_email")
        operation["required_capabilities"].append("cap.db.read")
    tightening = _mutated_snapshot(source, tighten)
    assert diff_registry_snapshots(source, tightening).overall_classification == "tightening"

    def remove_operation(components):
        components["operation_spec_registry"]["operations"] = [
            item for item in components["operation_spec_registry"]["operations"]
            if item["id"] != "data.normalize_email"
        ]
    breaking = _mutated_snapshot(source, remove_operation)
    assert diff_registry_snapshots(source, breaking).overall_classification == "breaking"

    unknown = _mutated_snapshot(
        source,
        lambda c: c["operation_spec_registry"].__setitem__("unknown_operation_policy", "manual_review"),
    )
    assert diff_registry_snapshots(source, unknown).overall_classification == "unknown"

    def permit_forbidden_operation(components):
        operation = next(
            item for item in components["operation_spec_registry"]["operations"]
            if item["id"] == "email.send.real"
        )
        operation["forbidden_in_public_demo"] = False

    operation_relaxation = _mutated_snapshot(source, permit_forbidden_operation)
    assert diff_registry_snapshots(source, operation_relaxation).overall_classification == "relaxation"
    assert diff_registry_snapshots(operation_relaxation, source).overall_classification == "tightening"

    def remove_human_review_requirement(components):
        profile = components["external_consumer_profiles"]["profiles"][0]
        profile["strict_packet_validation"]["requires_human_review"] = False

    review_relaxation = _mutated_snapshot(source, remove_human_review_requirement)
    assert diff_registry_snapshots(source, review_relaxation).overall_classification == "relaxation"
    assert diff_registry_snapshots(review_relaxation, source).overall_classification == "tightening"


def test_replay_modes_reject_incompatible_arguments_and_migration_metadata(tmp_path: Path) -> None:
    issued = _issue_stable(tmp_path / "receipt")
    snapshot = capture_registry_snapshot()

    with pytest.raises(ValueError, match="exact_snapshot_replay does not accept"):
        replay_trust_receipt_mode(
            issued.receipt_path,
            SAFE,
            TrustedExecutionContext.public_demo(),
            mode=EXACT_SNAPSHOT_REPLAY,
            source_snapshot=snapshot,
        )
    with pytest.raises(ValueError, match="current_registry_replay accepts only"):
        replay_trust_receipt_mode(
            issued.receipt_path,
            SAFE,
            TrustedExecutionContext.public_demo(),
            mode=CURRENT_REGISTRY_REPLAY,
            target_snapshot=snapshot,
        )

    exact_cli = _run_cli(
        "receipt", "replay", issued.receipt_path, "--draft", str(SAFE),
        "--mode", EXACT_SNAPSHOT_REPLAY, "--source-snapshot", str(tmp_path / "unused.json"),
    )
    assert exact_cli.returncode == 2
    assert "arguments refused" in exact_cli.stderr
    assert "Traceback" not in exact_cli.stderr

    current_cli = _run_cli(
        "receipt", "replay", issued.receipt_path, "--draft", str(SAFE),
        "--mode", CURRENT_REGISTRY_REPLAY, "--target-snapshot", str(tmp_path / "unused.json"),
    )
    assert current_cli.returncode == 2
    assert "arguments refused" in current_cli.stderr
    assert "Traceback" not in current_cli.stderr

    for bad_ref in ("", "x" * 513):
        with pytest.raises(RegistryEvolutionError, match="evidence_ref"):
            create_registry_migration_record(
                snapshot,
                snapshot,
                authorized_by="maintainer",
                reason="Validate migration evidence metadata.",
                approve=True,
                evidence_ref=bad_ref,
            )

def test_migration_record_binds_exact_diff_and_requires_explicit_approval() -> None:
    source = capture_registry_snapshot()
    target = _mutated_snapshot(
        source,
        lambda c: c["safety_registry"]["allowed_external_effects"].append("effect.external.notification.email.real"),
    )
    review = create_registry_migration_record(
        source,
        target,
        authorized_by="maintainer",
        reason="Review registry relaxation before local replay.",
    )
    assert validate_registry_migration_record(review, source, target).valid
    assert not validate_registry_migration_record(review, source, target, require_approved=True).valid

    approved = create_registry_migration_record(
        source,
        target,
        authorized_by="maintainer",
        reason="Approve registry relaxation for explicit local replay.",
        approve=True,
    )
    assert validate_registry_migration_record(approved, source, target, require_approved=True).valid
    assert approved["cryptographic_signature_status"] == "not_implemented"

    tampered = deepcopy(approved)
    tampered["acknowledged_change_ids"] = []
    assert not validate_registry_migration_record(tampered, source, target, require_approved=True).valid

    unknown = deepcopy(approved)
    unknown["authorization"]["implicit_admin_override"] = True
    assert any(
        check["check"] == "migration.authorization.unknown_fields" and check["status"] == "failed"
        for check in validate_registry_migration_record(unknown, source, target, require_approved=True).checks
    )


def test_exact_and_current_replay_preserve_historical_receipt(tmp_path: Path) -> None:
    issued = _issue_stable(tmp_path / "receipt")
    snapshot = capture_registry_snapshot()
    before = sha256_bytes(Path(issued.receipt_path).read_bytes())

    exact = replay_trust_receipt_mode(
        issued.receipt_path,
        SAFE,
        TrustedExecutionContext.public_demo(),
        mode=EXACT_SNAPSHOT_REPLAY,
    )
    assert exact.overall_status == "passed"
    assert exact.historical_receipt_unchanged
    assert exact.registry_diff_status == "not_applicable"

    current = replay_trust_receipt_mode(
        issued.receipt_path,
        SAFE,
        TrustedExecutionContext.public_demo(),
        mode=CURRENT_REGISTRY_REPLAY,
        source_snapshot=snapshot,
    )
    assert current.overall_status == "passed"
    assert current.registry_diff_status == "available"
    assert current.registry_diff["overall_classification"] == "compatible"
    assert current.decision_changed is False
    assert sha256_bytes(Path(issued.receipt_path).read_bytes()) == before
    assert not validate_replay_report(current.as_dict(), require_public_contract=True)

    mismatched_source = _mutated_snapshot(
        snapshot,
        lambda c: c["safety_registry"].__setitem__("version", "mismatched-source"),
    )
    mismatch = replay_trust_receipt_mode(
        issued.receipt_path,
        SAFE,
        TrustedExecutionContext.public_demo(),
        mode=CURRENT_REGISTRY_REPLAY,
        source_snapshot=mismatched_source,
    )
    assert mismatch.overall_status == "failed"
    assert mismatch.historical_receipt_unchanged
    assert any(
        check["check"] == "source_snapshot_matches_historical_receipt"
        and check["status"] == "failed"
        for check in mismatch.checks
    )


def test_migrated_replay_is_fail_closed_without_explicit_unsigned_opt_in(tmp_path: Path) -> None:
    compiled, draft_path = _generated_profile(tmp_path)
    source = capture_registry_snapshot()
    issued = _issue_stable(tmp_path / "receipt", draft_path)
    assert issued.receipt["status"] == "refused"
    with profile_registry_context(compiled):
        target = capture_registry_snapshot(parent_snapshot_hash=source["snapshot_sha256"])
    migration = create_registry_migration_record(
        source,
        target,
        authorized_by="maintainer",
        reason="Approve generated profile for explicit local replay.",
        approve=True,
    )
    before = sha256_bytes(Path(issued.receipt_path).read_bytes())
    blocked = replay_trust_receipt_mode(
        issued.receipt_path,
        draft_path,
        TrustedExecutionContext.public_demo(),
        mode=MIGRATED_REGISTRY_REPLAY,
        source_snapshot=source,
        target_snapshot=target,
        migration_record=migration,
    )
    assert blocked.overall_status == "failed"
    assert any(
        check["check"] == "migration_unsigned_local_approval_explicitly_accepted"
        and check["status"] == "failed"
        for check in blocked.checks
    )

    allowed = replay_trust_receipt_mode(
        issued.receipt_path,
        draft_path,
        TrustedExecutionContext.public_demo(),
        mode=MIGRATED_REGISTRY_REPLAY,
        source_snapshot=source,
        target_snapshot=target,
        migration_record=migration,
        allow_unsigned_local_approval=True,
    )
    assert allowed.overall_status == "passed"
    assert allowed.historical_status == "refused"
    assert allowed.evaluated_status == "passed"
    assert allowed.decision_changed is True
    assert allowed.registry_diff["overall_classification"] in {"relaxation", "behavioral", "unknown"}
    assert allowed.migration["authorization_status"] == "approved"
    assert allowed.migration["unsigned_local_approval_accepted"] is True
    assert sha256_bytes(Path(issued.receipt_path).read_bytes()) == before
    allowed_payload = allowed.as_dict()
    assert not validate_replay_report(allowed_payload, require_public_contract=True)

    unknown_field = deepcopy(allowed_payload)
    unknown_field["implicit_authorization"] = True
    assert any(
        check["check"] == "replay_report_schema_valid.unknown_fields"
        for check in validate_replay_report(unknown_field, require_public_contract=True)
    )

    unsigned_claim = deepcopy(allowed_payload)
    unsigned_claim["migration"]["unsigned_local_approval_accepted"] = False
    assert any(
        check["check"] == "replay_report_semantics.migration.unsigned_local_approval_accepted"
        for check in validate_replay_report(unsigned_claim, require_public_contract=True)
    )

    contradictory = deepcopy(allowed_payload)
    contradictory["checks"].append({"check": "tampered", "status": "failed", "expected": True, "actual": False})
    assert any(
        check["check"] == "replay_report_semantics.passed_has_no_failed_checks"
        for check in validate_replay_report(contradictory, require_public_contract=True)
    )


def test_migrated_replay_rejects_wrong_target_and_unapproved_record(tmp_path: Path) -> None:
    issued = _issue_stable(tmp_path / "receipt")
    source = capture_registry_snapshot()
    target = _mutated_snapshot(source, lambda c: c["safety_registry"].__setitem__("version", "metadata-v2"))
    wrong = _mutated_snapshot(source, lambda c: c["safety_registry"].__setitem__("version", "metadata-v3"))
    review = create_registry_migration_record(
        source,
        target,
        authorized_by="maintainer",
        reason="Migration still requires explicit approval.",
        approve=False,
    )
    report = replay_trust_receipt_mode(
        issued.receipt_path,
        SAFE,
        TrustedExecutionContext.public_demo(),
        mode=MIGRATED_REGISTRY_REPLAY,
        source_snapshot=source,
        target_snapshot=wrong,
        migration_record=review,
        allow_unsigned_local_approval=True,
    )
    assert report.overall_status == "failed"
    assert report.historical_receipt_unchanged
    assert report.migration is not None
    assert report.migration["unsigned_local_approval_accepted"] is False


def test_cli_issues_snapshot_sidecar_and_runs_registry_evolution_commands(tmp_path: Path) -> None:
    issue = _run_cli("receipt", "issue", str(SAFE), "--out-dir", str(tmp_path / "receipt"), "--json")
    assert issue.returncode == 0, issue.stderr
    issued = json.loads(issue.stdout)
    receipt_path = Path(issued["receipt_path"])
    source_path = Path(issued["registry_snapshot_path"])
    assert receipt_path.exists() and source_path.exists()
    assert load_registry_snapshot(source_path)["snapshot_id"] == issued["registry_snapshot_id"]

    exact = _run_cli("receipt", "replay", str(receipt_path), "--draft", str(SAFE), "--json")
    assert exact.returncode == 0, exact.stderr
    exact_data = json.loads(exact.stdout)
    assert exact_data["replay_mode"] == EXACT_SNAPSHOT_REPLAY
    assert exact_data["historical_receipt_unchanged"] is True

    current = _run_cli(
        "receipt", "replay", str(receipt_path), "--draft", str(SAFE),
        "--mode", CURRENT_REGISTRY_REPLAY, "--source-snapshot", str(source_path), "--json",
    )
    assert current.returncode == 0, current.stderr
    current_data = json.loads(current.stdout)
    assert current_data["registry_diff"]["overall_classification"] == "compatible"
    assert current_data["historical_receipt_unchanged"] is True

    target_path = tmp_path / "target.json"
    snapshot = _run_cli("registry", "snapshot", "--evolution", "--out", str(target_path), "--json")
    assert snapshot.returncode == 0, snapshot.stderr
    diff = _run_cli("registry", "diff", str(source_path), str(target_path), "--json")
    assert diff.returncode == 0, diff.stderr
    assert json.loads(diff.stdout)["overall_classification"] == "compatible"

    record_path = tmp_path / "migration.json"
    create = _run_cli(
        "registry", "migration", "create", str(source_path), str(target_path),
        "--authorized-by", "maintainer", "--reason", "Identity migration review.",
        "--approve", "--out", str(record_path), "--json",
    )
    assert create.returncode == 0, create.stderr
    validate = _run_cli(
        "registry", "migration", "validate", str(record_path), str(source_path), str(target_path),
        "--require-approved", "--json",
    )
    assert validate.returncode == 0, validate.stderr
    assert json.loads(validate.stdout)["overall_status"] == "passed"

    blocked = _run_cli(
        "receipt", "replay", str(receipt_path), "--draft", str(SAFE),
        "--mode", MIGRATED_REGISTRY_REPLAY,
        "--source-snapshot", str(source_path),
        "--target-snapshot", str(target_path),
        "--migration-record", str(record_path),
        "--json",
    )
    assert blocked.returncode == 2
    blocked_data = json.loads(blocked.stdout)
    assert blocked_data["overall_status"] == "failed"

    accepted = _run_cli(
        "receipt", "replay", str(receipt_path), "--draft", str(SAFE),
        "--mode", MIGRATED_REGISTRY_REPLAY,
        "--source-snapshot", str(source_path),
        "--target-snapshot", str(target_path),
        "--migration-record", str(record_path),
        "--accept-unsigned-local-approval",
        "--json",
    )
    assert accepted.returncode == 0, accepted.stderr
    accepted_data = json.loads(accepted.stdout)
    assert accepted_data["migration"]["unsigned_local_approval_accepted"] is True
    assert accepted_data["historical_receipt_unchanged"] is True

    legacy_nonexact = _run_cli(
        "trust-receipt-replay", str(receipt_path), "--draft", str(SAFE),
        "--mode", CURRENT_REGISTRY_REPLAY,
    )
    assert legacy_nonexact.returncode == 2
    assert "supports exact replay only" in legacy_nonexact.stderr



def test_ci_and_distribution_checks_exercise_p4_contracts() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution_contracts.py").read_text(encoding="utf-8")
    assert "Validate registry evolution artifacts and replay-mode contracts" in workflow
    assert "registry snapshot --evolution" in workflow
    assert "tests/test_p4_registry_evolution_and_replay.py" in workflow
    assert "installed_wheel_registry_evolution_and_replay_modes" in distribution
    assert '"--mode", "current_registry_replay"' in distribution
    assert '"--mode", "migrated_registry_replay"' in distribution
    assert '"--accept-unsigned-local-approval"' in distribution
    assert "historical_receipt_unchanged" in distribution

def test_schema_documents_accept_generated_p4_artifacts(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    source = capture_registry_snapshot()
    target = _mutated_snapshot(source, lambda c: c["safety_registry"].__setitem__("version", "metadata-v2"))
    diff = diff_registry_snapshots(source, target).as_dict()
    migration = create_registry_migration_record(
        source,
        target,
        authorized_by="maintainer",
        reason="Validate generated artifact schemas.",
        approve=True,
    )
    issued = _issue_stable(tmp_path / "receipt")
    replay = replay_trust_receipt_mode(
        issued.receipt_path,
        SAFE,
        TrustedExecutionContext.public_demo(),
        mode=CURRENT_REGISTRY_REPLAY,
        source_snapshot=source,
    ).as_dict()
    for name, artifact in (
        ("registry_snapshot.schema.json", source),
        ("registry_diff.schema.json", diff),
        ("registry_migration_record.schema.json", migration),
        ("trust_receipt_replay_report.schema.json", replay),
    ):
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(artifact, schema)
