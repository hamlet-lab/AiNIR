from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import ainir
from ainir.canonical import read_json_object_artifact, sha256_json
from ainir.contract_validation import validate_trust_gate_decision, validate_trust_receipt
from ainir.contracts import (
    LEGACY_TRUST_GATE_DECISION_VERSION,
    LEGACY_TRUST_RECEIPT_VERSION,
    PROFILE_MANIFEST_CONTRACT,
    TRUST_GATE_DECISION_CONTRACT,
    TRUST_RECEIPT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
    artifact_contract_manifest,
)
from ainir.core import load_draft
from ainir.execution_context import TrustedExecutionContext
from ainir.profiles import get_consumer_profile, list_consumer_profiles
from ainir.trust_gate import evaluate_trust_gate
from ainir.trust_receipt_store import (
    convert_trust_receipt_contract,
    issue_trust_receipt,
    replay_trust_receipt,
    verify_trust_receipt_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
SAFE = ROOT / "examples/create_user_outbox_safe/draft.yaml"


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


def test_stable_contract_identifiers_are_exported_and_manifested() -> None:
    assert ainir.TRUST_GATE_DECISION_CONTRACT == TRUST_GATE_DECISION_CONTRACT
    assert ainir.TRUST_RECEIPT_CONTRACT == TRUST_RECEIPT_CONTRACT
    assert ainir.TRUST_RECEIPT_REPLAY_REPORT_CONTRACT == TRUST_RECEIPT_REPLAY_REPORT_CONTRACT
    assert ainir.PROFILE_MANIFEST_CONTRACT == PROFILE_MANIFEST_CONTRACT
    manifest = artifact_contract_manifest()
    assert manifest["contracts"]["trust_gate_decision"]["identifier"] == TRUST_GATE_DECISION_CONTRACT
    assert manifest["contracts"]["trust_receipt"]["legacy_versions"] == [LEGACY_TRUST_RECEIPT_VERSION]
    assert manifest["contracts"]["profile_manifest"]["status"] == "implemented"


def test_supported_canonical_json_is_deterministic_and_defensive(tmp_path: Path) -> None:
    assert sha256_json({"b": 1, "a": 2}) == sha256_json({"a": 2, "b": 1})
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    duplicate_result = read_json_object_artifact(duplicate)
    assert duplicate_result.ok is False
    assert duplicate_result.reason == "json_duplicate_key"
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":NaN}', encoding="utf-8")
    nonfinite_result = read_json_object_artifact(nonfinite)
    assert nonfinite_result.ok is False
    assert nonfinite_result.reason == "json_non_finite_number"


def test_stable_decision_preserves_legacy_semantics_and_receipt_identity() -> None:
    decision = evaluate_trust_gate(load_draft(SAFE), TrustedExecutionContext.public_demo())
    legacy = decision.as_dict()
    stable = decision.as_public_dict()
    assert legacy["version"] == LEGACY_TRUST_GATE_DECISION_VERSION
    assert stable["version"] == TRUST_GATE_DECISION_CONTRACT
    assert stable["legacy_version"] == LEGACY_TRUST_GATE_DECISION_VERSION
    for field in ("status", "module_id", "workflow", "lowering_allowed", "failed_gates", "gate_results"):
        assert stable[field] == legacy[field]
    assert stable["receipt"]["receipt_id"] == legacy["receipt"]["receipt_id"]
    assert stable["receipt"]["version"] == TRUST_RECEIPT_CONTRACT
    assert not validate_trust_gate_decision(stable)


def test_receipt_contract_conversion_round_trip_preserves_legacy_artifact() -> None:
    legacy = evaluate_trust_gate(load_draft(SAFE), TrustedExecutionContext.public_demo()).as_dict()["receipt"]
    stable = convert_trust_receipt_contract(legacy, target_version=TRUST_RECEIPT_CONTRACT)
    restored = convert_trust_receipt_contract(stable, target_version=LEGACY_TRUST_RECEIPT_VERSION)
    assert stable["version"] == TRUST_RECEIPT_CONTRACT
    assert stable["legacy_version"] == LEGACY_TRUST_RECEIPT_VERSION
    assert restored == legacy
    assert not validate_trust_receipt(stable)


def test_stable_and_legacy_receipts_issue_validate_and_exact_replay(tmp_path: Path) -> None:
    context = TrustedExecutionContext.public_demo()
    stable = issue_trust_receipt(SAFE, tmp_path / "stable", context, contract_version=TRUST_RECEIPT_CONTRACT)
    legacy = issue_trust_receipt(SAFE, tmp_path / "legacy", context)
    assert stable.receipt["version"] == TRUST_RECEIPT_CONTRACT
    assert legacy.receipt["version"] == LEGACY_TRUST_RECEIPT_VERSION
    assert stable.receipt["receipt_id"] == legacy.receipt["receipt_id"]
    assert verify_trust_receipt_artifact(stable.receipt_path).overall_status == "passed"
    assert replay_trust_receipt(stable.receipt_path, SAFE, context).overall_status == "passed"
    assert replay_trust_receipt(legacy.receipt_path, SAFE, context).overall_status == "passed"


def test_unsupported_receipt_contract_fails_before_replay(tmp_path: Path) -> None:
    issued = issue_trust_receipt(SAFE, tmp_path, TrustedExecutionContext.public_demo())
    receipt = dict(issued.receipt)
    receipt["version"] = "ainir.trust-receipt.v999"
    path = tmp_path / "unsupported.receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    report = replay_trust_receipt(path, SAFE, TrustedExecutionContext.public_demo())
    assert report.overall_status == "failed"
    assert any(check["check"] == "receipt_schema_valid.version" for check in report.checks)


def test_public_help_hides_phase_history_and_shows_command_groups() -> None:
    result = _run_cli("--help")
    assert result.returncode == 0, result.stderr
    for command in ("trust", "receipt", "profile", "conformance", "registry", "contracts"):
        assert command in result.stdout
    assert "phase18-trust-gate-eval" not in result.stdout
    assert "trust-receipt-issue" not in result.stdout


def test_new_and_legacy_trust_commands_are_equivalent_with_deprecation_warning() -> None:
    stable_result = _run_cli("trust", "evaluate", str(SAFE), "--json")
    legacy_result = _run_cli("trust-gate", str(SAFE), "--json")
    assert stable_result.returncode == legacy_result.returncode == 0
    stable = json.loads(stable_result.stdout)
    legacy = json.loads(legacy_result.stdout)
    assert stable["version"] == TRUST_GATE_DECISION_CONTRACT
    assert legacy["version"] == LEGACY_TRUST_GATE_DECISION_VERSION
    assert stable["receipt"]["receipt_id"] == legacy["receipt"]["receipt_id"]
    assert "use 'ainir trust evaluate'" in legacy_result.stderr


def test_new_receipt_cli_issues_stable_artifact_and_replays_it(tmp_path: Path) -> None:
    issue = _run_cli("receipt", "issue", str(SAFE), "--out-dir", str(tmp_path), "--json")
    assert issue.returncode == 0, issue.stderr
    summary = json.loads(issue.stdout)
    assert summary["receipt_version"] == TRUST_RECEIPT_CONTRACT
    receipt_path = Path(summary["receipt_path"])
    verify = _run_cli("receipt", "verify", str(receipt_path), "--json")
    replay = _run_cli("receipt", "replay", str(receipt_path), "--draft", str(SAFE), "--json")
    assert verify.returncode == replay.returncode == 0
    replay_report = json.loads(replay.stdout)
    assert replay_report["version"] == TRUST_RECEIPT_REPLAY_REPORT_CONTRACT
    assert replay_report["overall_status"] == "passed"


def test_read_only_profile_surface_lists_and_resolves_bundled_profile() -> None:
    profiles = list_consumer_profiles()
    assert [profile["id"] for profile in profiles] == ["AIVLConsumerProfile"]
    assert get_consumer_profile("AIVLConsumerProfile")["status"] == "contract_slot_only"
    result = _run_cli("profile", "list", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["profile_manifest_contract"] == PROFILE_MANIFEST_CONTRACT


def test_registry_and_contract_cli_are_machine_readable() -> None:
    registry = _run_cli("registry", "list", "--json")
    snapshot = _run_cli("registry", "snapshot", "--json")
    contracts = _run_cli("contracts", "--json")
    assert registry.returncode == snapshot.returncode == contracts.returncode == 0
    assert len(json.loads(registry.stdout)["registries"]) == 4
    assert json.loads(snapshot.stdout)["valid"] is True
    assert json.loads(contracts.stdout)["contracts"]["trust_receipt"]["identifier"] == TRUST_RECEIPT_CONTRACT


def test_cli_uses_supported_canonical_helpers_not_private_receipt_hashes() -> None:
    source = (ROOT / "src/ainir/cli.py").read_text(encoding="utf-8")
    assert "from .canonical import sha256_bytes, sha256_json" in source
    assert "from .trust_receipt_store import _sha256_json" not in source
    assert "_canonical_verified_intent_packet_hash" not in source


def test_release_manifest_and_phase30_check_bind_p2_contracts() -> None:
    import yaml

    from ainir.phase30_v1_rc_candidate import _manifest_check

    manifest = yaml.safe_load((ROOT / "release/v1_0_rc_candidate_manifest.yaml").read_text(encoding="utf-8"))
    p2 = manifest["p2_stable_cli_and_artifact_contracts"]
    assert p2 and all(value is True for value in p2.values())
    assert "Stable Public CLI" in manifest["frozen_public_surfaces"]
    assert "Stable Artifact Contract Identifiers" in manifest["frozen_public_surfaces"]
    assert _manifest_check()["status"] == "passed"


def test_current_private_trial_and_entry_docs_use_phase_independent_commands() -> None:
    private_trial = (ROOT / "src/ainir/phase26_private_trial.py").read_text(encoding="utf-8")
    for legacy in (
        "'negative-conformance-eval'",
        "'golden-trace-eval'",
        "'phase18-trust-gate-eval'",
        "'phase25-verified-intent-contract-eval'",
    ):
        assert legacy not in private_trial
    for stable in (
        "'conformance', 'negative'",
        "'conformance', 'golden'",
        "'conformance', 'trust-gate'",
        "'conformance', 'intent-contract'",
    ):
        assert stable in private_trial

    current_docs = (
        ROOT / "README.md",
        ROOT / "START_HERE.md",
        ROOT / "docs/cli.md",
        ROOT / "docs/trust_gate.md",
        ROOT / "docs/trust_receipt_persistence.md",
        ROOT / "docs/negative_conformance_corpus.md",
        ROOT / "docs/golden_traces.md",
        ROOT / "docs/v1_acceptance_criteria.md",
        ROOT / "docs/github_launch_checklist.md",
    )
    legacy_invocations = (
        "python -m ainir trust-gate ",
        "python -m ainir trust-receipt-issue ",
        "python -m ainir trust-receipt-replay ",
        "python -m ainir negative-conformance-eval",
        "python -m ainir golden-trace-eval",
        "python -m ainir phase",
    )
    for path in current_docs:
        text = path.read_text(encoding="utf-8")
        assert not any(invocation in text for invocation in legacy_invocations), path


def test_packaged_contract_schemas_match_source_and_accept_transition_versions() -> None:
    cases = {
        "trust_gate_decision.schema.json": [TRUST_GATE_DECISION_CONTRACT, LEGACY_TRUST_GATE_DECISION_VERSION],
        "trust_receipt.schema.json": [TRUST_RECEIPT_CONTRACT, LEGACY_TRUST_RECEIPT_VERSION],
    }
    for name, expected_versions in cases.items():
        source = ROOT / "schemas" / name
        packaged = ROOT / "src/ainir/schemas" / name
        assert source.read_bytes() == packaged.read_bytes()
        schema = json.loads(source.read_text(encoding="utf-8"))
        assert schema["properties"]["version"]["enum"] == expected_versions

    replay_source = ROOT / "schemas/trust_receipt_replay_report.schema.json"
    replay_packaged = ROOT / "src/ainir/schemas/trust_receipt_replay_report.schema.json"
    assert replay_source.read_bytes() == replay_packaged.read_bytes()
    replay_schema = json.loads(replay_source.read_text(encoding="utf-8"))
    assert replay_schema["properties"]["version"]["const"] == TRUST_RECEIPT_REPLAY_REPORT_CONTRACT


def test_legacy_receipt_text_output_remains_unchanged_while_new_output_names_version(tmp_path: Path) -> None:
    stable_dir = tmp_path / "stable"
    legacy_dir = tmp_path / "legacy"
    stable = _run_cli("receipt", "issue", str(SAFE), "--out-dir", str(stable_dir))
    legacy = _run_cli("trust-receipt-issue", str(SAFE), "--out-dir", str(legacy_dir))
    assert stable.returncode == legacy.returncode == 0
    assert f"receipt_version: {TRUST_RECEIPT_CONTRACT}" in stable.stdout
    assert "receipt_version:" not in legacy.stdout
    assert "use 'ainir receipt issue'" in legacy.stderr


def test_distribution_checker_exercises_stable_cli_and_contract_versions() -> None:
    source = (ROOT / "scripts/check_distribution_contracts.py").read_text(encoding="utf-8")
    assert '["trust", "evaluate"' in source
    assert '["receipt", "issue"' in source
    assert '["receipt", "replay"' in source
    assert 'gate_data.get("version") == TRUST_GATE_DECISION_CONTRACT' in source
    assert 'issue_data.get("receipt_version") == TRUST_RECEIPT_CONTRACT' in source
    assert 'replay_data.get("version") == TRUST_RECEIPT_REPLAY_REPORT_CONTRACT' in source
    for legacy in ('["trust-gate"', '["trust-receipt-issue"', '["trust-receipt-replay"'):
        assert legacy not in source


def test_registry_show_rejects_unknown_or_traversal_resource_without_traceback() -> None:
    for name in ("unknown.yaml", "../schemas/trust_receipt.schema.json"):
        result = _run_cli("registry", "show", name, "--json")
        assert result.returncode == 2
        assert "invalid choice" in result.stderr or "unknown AiNIR public registry" in result.stderr
        assert "Traceback" not in result.stderr
