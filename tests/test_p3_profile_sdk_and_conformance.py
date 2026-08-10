from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from ainir.conformance_runner import render_conformance_report, run_profile_conformance
from ainir.core import load_draft
from ainir.execution_context import TrustedExecutionContext
from ainir.profile_manifest import (
    BUILTIN_PROFILE_ID,
    initialize_profile,
    inspect_profile_manifest,
    load_profile_manifest,
    materialized_profile_source,
    validate_profile_manifest,
)
from ainir.profile_runtime import ProfileCompilationError, compile_profile, profile_registry_context
from ainir.registry_provenance import registry_snapshot
from ainir.trust_gate import evaluate_trust_gate

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str, cwd: Path = ROOT, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "ainir", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _new_profile(tmp_path: Path, *, profile_id: str = "example.profile.v1", workflow_id: str = "ProfileRequest") -> Path:
    created = initialize_profile(tmp_path / "profile", profile_id=profile_id, workflow_id=workflow_id)
    return created[0]


def _positive_draft(profile_root: Path, output: Path) -> Path:
    pack = yaml.safe_load((profile_root / "conformance.yaml").read_text(encoding="utf-8"))
    positive = next(case for case in pack["cases"] if case["category"] == "positive")
    output.write_text(yaml.safe_dump(positive["draft"], sort_keys=False), encoding="utf-8")
    return output


def test_builtin_profile_is_valid_and_covers_all_required_categories() -> None:
    with materialized_profile_source(BUILTIN_PROFILE_ID) as manifest:
        report = validate_profile_manifest(manifest)
        inspection = inspect_profile_manifest(manifest)
    assert report.valid is True
    assert set(report.conformance_categories) == {"positive", "negative", "mutation", "replay"}
    assert inspection["profile_id"] == BUILTIN_PROFILE_ID
    assert inspection["registry_mode"] == "packaged"
    assert inspection["production_runtime_ready"] is False


def test_builtin_profile_unifies_existing_corpora_without_changing_default_registry(tmp_path: Path) -> None:
    before = registry_snapshot()["combined_sha256"]
    with materialized_profile_source(BUILTIN_PROFILE_ID) as manifest:
        report = run_profile_conformance(manifest, out_dir=tmp_path / "out")
    payload = report.as_dict()
    assert payload["overall_status"] == "passed"
    assert payload["case_count"] == payload["passed"] == 81
    assert payload["failed"] == 0
    assert payload["category_counts"]["positive"]["total"] == 1
    assert payload["category_counts"]["negative"]["total"] == 46
    assert payload["category_counts"]["mutation"]["total"] == 34
    assert payload["category_counts"]["replay"]["total"] == 10
    assert payload["registry_snapshot_hash"] == before
    assert registry_snapshot()["combined_sha256"] == before


def test_profile_scaffold_validates_and_runs_all_four_categories(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    manifest = load_profile_manifest(manifest_path)
    validation = validate_profile_manifest(manifest)
    assert validation.valid is True, [issue.as_dict() for issue in validation.issues]
    report = run_profile_conformance(manifest, out_dir=tmp_path / "out")
    payload = report.as_dict()
    assert payload["overall_status"] == "passed"
    assert payload["case_count"] == payload["passed"] == 4
    assert payload["failed"] == 0
    for category in ("positive", "negative", "mutation", "replay"):
        assert payload["category_counts"][category]["total"] >= 1
    for name in ("conformance_report.json", "conformance_report.jsonl", "conformance_report.junit.xml", "conformance_report.yaml"):
        assert (tmp_path / "out" / name).is_file()


def test_additive_profile_is_context_local_and_receipt_binds_profile_snapshot(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path, profile_id="example.bound.v1", workflow_id="BoundRequest")
    manifest = load_profile_manifest(manifest_path)
    compiled = compile_profile(manifest)
    draft_path = _positive_draft(manifest.root, tmp_path / "draft.yaml")
    context = TrustedExecutionContext.from_environment("public_demo", source="test", purpose="profile_scope")
    base_hash = registry_snapshot()["combined_sha256"]

    outside = evaluate_trust_gate(load_draft(draft_path), context)
    assert outside.status == "refused"

    with profile_registry_context(compiled):
        inside = evaluate_trust_gate(load_draft(draft_path), context)
        assert inside.status == "passed"
        assert inside.lowering_allowed is True
        assert inside.receipt["registry_snapshot_hash"] != base_hash
        assert inside.receipt["registry_snapshot"]["profile_id"] == "example.bound.v1"
        assert inside.receipt["registry_snapshot"]["profile_manifest_sha256"] == manifest.canonical_sha256

    assert registry_snapshot()["combined_sha256"] == base_hash
    restored = evaluate_trust_gate(load_draft(draft_path), context)
    assert restored.status == "refused"


def test_profile_cannot_override_protected_workflow(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path, workflow_id="CollisionRequest")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["coverage"]["workflows"] = ["CreateUser"]
    data["coverage"]["transaction_workflows"] = ["CreateUser"]
    data["extensions"]["workflows"][0]["id"] = "CreateUser"
    for operation in data["extensions"]["operations"]:
        operation["allowed_workflows"] = ["CreateUser"]
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    manifest = load_profile_manifest(manifest_path)
    assert validate_profile_manifest(manifest).valid is True
    with pytest.raises(ProfileCompilationError, match="collides with protected value"):
        compile_profile(manifest)


def test_profile_cannot_weaken_fail_closed_policy_or_escape_pack_root(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["policies"]["unknown_workflow"] = "pass"
    data["conformance"]["pack"] = "../outside.yaml"
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    codes = {issue.code for issue in report.issues}
    assert report.valid is False
    assert "P030.fail_closed_policy" in codes
    assert "P010.path_escape" in codes


def test_validator_rejects_hidden_nested_fields_and_pack_profile_mismatch(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["extensions"]["operations"][0]["silently_trusted"] = True
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    pack_path = manifest_path.parent / "conformance.yaml"
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    pack["profile_id"] = "example.other.v1"
    pack_path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")
    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    codes = {issue.code for issue in report.issues}
    assert report.valid is False
    assert "P001.unknown_field" in codes
    assert "P016.conformance_profile_mismatch" in codes


def test_nested_profile_contexts_and_compilation_are_refused(tmp_path: Path) -> None:
    first = load_profile_manifest(_new_profile(tmp_path / "a", profile_id="example.a.v1", workflow_id="ARequest"))
    second = load_profile_manifest(_new_profile(tmp_path / "b", profile_id="example.b.v1", workflow_id="BRequest"))
    compiled_first = compile_profile(first)
    compiled_second = compile_profile(second)
    with profile_registry_context(compiled_first):
        with pytest.raises(ProfileCompilationError, match="nested profile registry contexts"):
            with profile_registry_context(compiled_second):
                pass
        with pytest.raises(ProfileCompilationError, match="nested profile compilation"):
            compile_profile(second)


def test_cli_preserves_consumer_default_and_adds_workflow_profile_commands(tmp_path: Path) -> None:
    default_list = _run_cli("profile", "list", "--json")
    assert default_list.returncode == 0, default_list.stderr
    assert json.loads(default_list.stdout)["kind"] == "AiNIRConsumerProfileList"

    workflow_list = _run_cli("profile", "list", "--kind", "workflow", "--json")
    assert workflow_list.returncode == 0, workflow_list.stderr
    workflow_payload = json.loads(workflow_list.stdout)
    assert workflow_payload["kind"] == "AiNIRWorkflowProfileList"
    assert any(item["profile_id"] == BUILTIN_PROFILE_ID for item in workflow_payload["profiles"])

    target = tmp_path / "cli-profile"
    initialized = _run_cli(
        "profile", "init", str(target),
        "--profile-id", "example.cli.v1",
        "--workflow-id", "CliRequest",
    )
    assert initialized.returncode == 0, initialized.stderr
    manifest = target / "profile.yaml"
    validated = _run_cli("profile", "validate", str(manifest), "--json")
    inspected = _run_cli("profile", "inspect", str(manifest), "--json")
    assert validated.returncode == inspected.returncode == 0
    assert json.loads(validated.stdout)["valid"] is True
    assert json.loads(inspected.stdout)["extension_counts"]["workflows"] == 1

    output = tmp_path / "conformance"
    run = _run_cli("conformance", "run", str(manifest), "--out-dir", str(output), "--format", "json")
    assert run.returncode == 0, run.stderr
    payload = json.loads(run.stdout)
    assert payload["overall_status"] == "passed"
    assert payload["case_count"] == 4


def test_conformance_renderers_are_machine_readable(tmp_path: Path) -> None:
    manifest = load_profile_manifest(_new_profile(tmp_path))
    report = run_profile_conformance(manifest, out_dir=tmp_path / "out")
    json_payload = json.loads(render_conformance_report(report, "json"))
    jsonl = [json.loads(line) for line in render_conformance_report(report, "jsonl").splitlines()]
    junit = render_conformance_report(report, "junit")
    assert json_payload["report_sha256"].startswith("sha256:")
    assert jsonl[-1]["record_type"] == "summary"
    assert "<testsuite" in junit and 'tests="4"' in junit


def test_profile_schemas_are_packaged_and_contract_status_is_implemented() -> None:
    from ainir.contracts import artifact_contract_manifest
    from ainir.resources import PUBLIC_SCHEMA_NAMES, read_schema_bytes

    contracts = artifact_contract_manifest()["contracts"]
    assert contracts["profile_manifest"]["status"] == "implemented"
    assert contracts["conformance_pack"]["status"] == "implemented"
    assert contracts["conformance_report"]["status"] == "implemented"
    for name in ("profile_manifest.schema.json", "conformance_pack.schema.json", "conformance_report.schema.json"):
        assert name in PUBLIC_SCHEMA_NAMES
        assert read_schema_bytes(name) == (ROOT / "schemas" / name).read_bytes()

    release_manifest = yaml.safe_load((ROOT / "release" / "v1_0_rc_candidate_manifest.yaml").read_text(encoding="utf-8"))
    p3 = release_manifest["p3_profile_sdk_and_conformance"]
    for key in (
        "reviewed_exact_effect_capability_vocabulary_only",
        "taxonomy_alias_and_external_allowlist_refusal",
        "broad_family_and_capability_prefix_refusal",
        "safety_critical_operation_alias_refusal",
        "non_vacuous_conformance_expectations",
        "additive_legacy_source_adapter_refusal",
    ):
        assert p3[key] is True


def test_profile_rejects_taxonomy_aliases_external_effects_and_broad_contracts(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["extensions"]["effect_aliases"] = {"effect.custom.alias": "effect.storage.db.write"}
    data["extensions"]["effect_capability_contracts"] = {
        "effect.custom.alias": {"prefixes": ["cap.db."]}
    }
    data["extensions"]["role_markers"] = {"custom_role": {"keywords": ["custom"]}}
    data["extensions"]["allowed_external_effects"] = ["effect.custom.external"]
    data["extensions"]["operations"][0]["required_effect_families"] = ["storage"]
    data["extensions"]["operations"][0]["allowed_capability_prefixes"] = ["cap.db."]
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    codes = {issue.code for issue in report.issues}
    assert report.valid is False
    assert "P078.extension_requires_registry_governance" in codes
    assert "P080.broad_operation_contract_forbidden" in codes


def test_profile_rejects_unknown_effect_and_capability_vocabulary(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    persist = data["extensions"]["operations"][1]
    persist["required_effects"] = ["effect.custom.unreviewed"]
    persist["allowed_effects"] = ["effect.custom.unreviewed"]
    persist["required_capabilities"] = ["cap.custom.unreviewed"]
    persist["allowed_capabilities"] = ["cap.custom.unreviewed"]
    data["coverage"]["effects"] = ["effect.custom.unreviewed"]
    data["coverage"]["capabilities"] = ["cap.custom.unreviewed"]
    data["extensions"]["capabilities"] = ["cap.custom.unreviewed"]
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    codes = {issue.code for issue in report.issues}
    assert report.valid is False
    assert "P081.unknown_profile_effect" in codes
    assert "P087.unknown_profile_capability" in codes


def test_profile_rejects_safety_critical_operation_alias_laundering(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["extensions"]["operations"][0]["aliases"] = ["hard_delete_user"]
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    assert report.valid is False
    assert "P079.safety_critical_operation_requires_core_review" in {
        issue.code for issue in report.issues
    }


def test_conformance_pack_rejects_vacuous_cases_and_additive_legacy_sources(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    pack_path = manifest_path.parent / "conformance.yaml"
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    positive = next(case for case in pack["cases"] if case["category"] == "positive")
    negative = next(case for case in pack["cases"] if case["category"] == "negative")
    replay = next(case for case in pack["cases"] if case["category"] == "replay")
    positive["expected"]["trust_status"] = "refused"
    positive["expected"]["lowering_allowed"] = False
    negative["expected"]["required_findings"] = []
    replay["expected"]["receipt_replay"] = False
    pack["sources"] = [{
        "id": "legacy-source",
        "type": "golden_traces",
        "path": "conformance.yaml",
    }]
    pack_path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")

    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    codes = {issue.code for issue in report.issues}
    assert report.valid is False
    assert {
        "P082.vacuous_positive_case",
        "P084.refusal_finding_required",
        "P085.vacuous_replay_case",
        "P086.additive_sources_forbidden",
    }.issubset(codes)


def test_profile_manifest_schema_matches_runtime_taxonomy_restrictions() -> None:
    schema = json.loads((ROOT / "schemas" / "profile_manifest.schema.json").read_text(encoding="utf-8"))
    extensions = schema["properties"]["extensions"]["properties"]
    operation = extensions["operations"]["items"]["properties"]

    assert extensions["effect_capability_contracts"]["maxProperties"] == 0
    assert extensions["effect_aliases"]["maxProperties"] == 0
    assert extensions["role_markers"]["maxProperties"] == 0
    assert extensions["allowed_external_effects"]["maxItems"] == 0
    assert operation["required_effect_families"]["maxItems"] == 0
    assert operation["allowed_capability_prefixes"]["maxItems"] == 0
    assert "effect.storage.db.write" in operation["required_effects"]["items"]["enum"]
    assert "effect.custom.unreviewed" not in operation["required_effects"]["items"]["enum"]
    assert "cap.db.write" in operation["required_capabilities"]["items"]["enum"]
    assert "cap.custom.unreviewed" not in operation["required_capabilities"]["items"]["enum"]


def test_packaged_profile_mode_and_builtin_id_are_reserved(tmp_path: Path) -> None:
    manifest_path = _new_profile(tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["registry_mode"] = "packaged"
    data["base_profile"] = None
    for key in data["extensions"]:
        data["extensions"][key] = [] if isinstance(data["extensions"][key], list) else {}
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    report = validate_profile_manifest(load_profile_manifest(manifest_path))
    assert "P088.packaged_profile_reserved" in {issue.code for issue in report.issues}

    second = _new_profile(tmp_path / "second", profile_id="example.second.v1", workflow_id="SecondRequest")
    second_data = yaml.safe_load(second.read_text(encoding="utf-8"))
    second_data["profile_id"] = BUILTIN_PROFILE_ID
    pack_path = second.parent / "conformance.yaml"
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    pack["profile_id"] = BUILTIN_PROFILE_ID
    pack_path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")
    second.write_text(yaml.safe_dump(second_data, sort_keys=False), encoding="utf-8")
    second_report = validate_profile_manifest(load_profile_manifest(second))
    assert "P089.builtin_profile_id_reserved" in {issue.code for issue in second_report.issues}
