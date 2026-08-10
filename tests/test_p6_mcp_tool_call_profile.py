from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import ainir
from ainir.canonical import sha256_json
from ainir.contracts import artifact_contract_manifest
from ainir.mcp_conformance import (
    load_bundled_mcp_conformance_pack,
    mcp_conformance_pack_projection,
    mcp_conformance_report_projection,
    run_bundled_mcp_conformance,
    validate_mcp_conformance_pack,
)
from ainir.mcp_host_adapter import bundled_mcp_reference_adapter
from ainir.mcp_tool_call import (
    BUILTIN_MCP_PROFILE_ID,
    MCP_PASSED_HOST_ACTIONS,
    MCP_REFUSED_HOST_ACTIONS,
    MCP_REVIEW_HOST_ACTIONS,
    MCPToolCallError,
    assess_mcp_tool_call,
    build_mcp_host_context,
    build_mcp_tool_call_envelope,
    load_json_mapping,
    load_mcp_tool_call_profile,
    materialized_mcp_profile_source,
    mcp_host_context_projection,
    mcp_tool_call_assessment_projection,
    mcp_tool_call_envelope_projection,
    mcp_tool_call_profile_projection,
    validate_mcp_host_context,
    validate_mcp_tool_call_assessment,
    validate_mcp_tool_call_envelope,
    validate_mcp_tool_call_profile,
    validate_mcp_tool_descriptor,
)
from ainir.registry_provenance import registry_snapshot
from ainir.resources import PUBLIC_SCHEMA_NAMES, read_schema_text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/mcp_tool_call"
EXPECTED_REGISTRY_HASH = "sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "ainir", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )


def _safe_artifacts(tool_name: str = "workspace.read_text"):
    with materialized_mcp_profile_source() as profile:
        descriptor = load_json_mapping(profile.root / "descriptors" / f"{tool_name}.json", label="descriptor")
        args = {"path": "docs/README.md"}
        capabilities = ["cap.resource.read"]
        transaction = {}
        if tool_name == "workspace.write_text":
            args = {"path": "notes/out.txt", "content": "safe"}
            capabilities = ["cap.resource.write"]
            transaction = {
                "transaction_status": "prepared",
                "rollback_available": True,
                "rollback_plan_sha256": "sha256:" + "1" * 64,
            }
        elif tool_name == "workspace.delete_file":
            args = {"path": "tmp/remove.txt"}
            capabilities = ["cap.resource.delete"]
            transaction = {
                "transaction_status": "prepared",
                "rollback_available": True,
                "rollback_plan_sha256": "sha256:" + "2" * 64,
            }
        call = {
            "jsonrpc": "2.0",
            "id": "test-call-1",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args, "_meta": {"client": "pytest"}},
        }
        transport = {"protocol_version": "2026-07-28", "method_header": "tools/call", "name_header": tool_name}
        envelope = build_mcp_tool_call_envelope(profile, descriptor, call, transport)
        context = build_mcp_host_context(
            envelope=envelope,
            host_id="host.pytest",
            actor_id="human.pytest",
            evaluation_time="2026-08-10T00:00:00Z",
            server_id="mcp.server.workspace.reference",
            server_origin="mcp+stdio://workspace.reference",
            authorization_audience="mcp.server.workspace.reference",
            authenticated=True,
            schema_validator_id="host.schema.pytest.v1",
            schema_validation_status="passed",
            capability_grants=capabilities,
            resource_scope_ids=["scope.workspace.pytest"],
            resource_resolution_status="passed",
            symlinks_resolved=True,
            consent_decision="approved",
            consent_issued_at="2026-08-09T23:59:00Z",
            consent_valid_until="2026-08-10T00:05:00Z",
            **transaction,
        )
        assessment = assess_mcp_tool_call(profile, envelope, context)
        return dict(profile.data), descriptor, call, transport, envelope, context, assessment


def test_p6_contracts_and_schemas_are_public_and_unique() -> None:
    assert ainir.MCP_TOOL_CALL_PROFILE_CONTRACT == "ainir.mcp-tool-call-profile.v1"
    assert ainir.MCP_TOOL_CALL_ENVELOPE_CONTRACT == "ainir.mcp-tool-call-envelope.v1"
    assert ainir.MCP_HOST_CONTEXT_CONTRACT == "ainir.mcp-host-context.v1"
    assert ainir.MCP_TOOL_CALL_ASSESSMENT_CONTRACT == "ainir.mcp-tool-call-assessment.v1"
    assert ainir.MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT == "ainir.mcp-tool-call-conformance-pack.v1"
    assert ainir.MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT == "ainir.mcp-tool-call-conformance-report.v1"
    names = {
        "mcp_tool_call_profile.schema.json",
        "mcp_tool_call_envelope.schema.json",
        "mcp_host_context.schema.json",
        "mcp_tool_call_assessment.schema.json",
        "mcp_tool_call_conformance_pack.schema.json",
        "mcp_tool_call_conformance_report.schema.json",
    }
    assert names <= set(PUBLIC_SCHEMA_NAMES)
    for name in names:
        assert (ROOT / "schemas" / name).read_bytes() == (ROOT / "src/ainir/schemas" / name).read_bytes()
        assert read_schema_text(name) == (ROOT / "schemas" / name).read_text(encoding="utf-8")
    manifest = artifact_contract_manifest()["contracts"]
    expected = {
        "mcp_tool_call_profile",
        "mcp_tool_call_envelope",
        "mcp_host_context",
        "mcp_tool_call_assessment",
        "mcp_tool_call_conformance_pack",
        "mcp_tool_call_conformance_report",
    }
    assert expected <= set(manifest)
    identifiers = [item["identifier"] for item in manifest.values()]
    assert len(identifiers) == len(set(identifiers))

    import yaml
    release_manifest = yaml.safe_load(
        (ROOT / "release/v1_0_rc_candidate_manifest.yaml").read_text(encoding="utf-8")
    )
    p6 = release_manifest["p6_mcp_tool_call_profile"]
    assert p6["credential_like_arguments_metadata_and_values_refused"] is True
    assert p6["resource_path_traversal_absolute_and_cross_platform_ambiguity_refused"] is True
    assert p6["twenty_six_case_conformance_pack"] is True
    assert p6["content_addressed_mcp_ids_and_nested_bindings"] is True
    assert p6["non_passed_assessments_do_not_instruct_execution"] is True


def test_bundled_profile_is_self_hashed_reviewed_and_non_executing() -> None:
    with materialized_mcp_profile_source() as profile:
        report = validate_mcp_tool_call_profile(profile)
        assert report.valid
        assert profile.profile_id == BUILTIN_MCP_PROFILE_ID
        assert profile.data["profile_sha256"] == sha256_json(mcp_tool_call_profile_projection(profile.data))
        assert profile.data["policies"]["tool_annotations_are_evidence"] is False
        assert profile.data["policies"]["model_output_is_evidence"] is False
        assert profile.data["policies"]["ainir_executes_actions"] is False
        assert profile.data["production_runtime_ready"] is False


def test_safe_read_and_write_are_passed_but_never_executed() -> None:
    for tool_name in ("workspace.read_text", "workspace.write_text"):
        *_, assessment = _safe_artifacts(tool_name)
        assert assessment["overall_status"] == "passed"
        assert assessment["host_handoff_allowed"] is True
        assert assessment["execution_performed"] is False
        assert assessment["production_runtime_ready"] is False
        assert tuple(assessment["required_host_actions"]) == MCP_PASSED_HOST_ACTIONS
        assert "execute_outside_ainir_core" in assessment["required_host_actions"]
        assert "do_not_execute" not in assessment["required_host_actions"]
        assert validate_mcp_tool_call_assessment(assessment).valid


def test_destructive_delete_requires_final_review_and_is_not_handed_off() -> None:
    *_, assessment = _safe_artifacts("workspace.delete_file")
    assert assessment["overall_status"] == "review_required"
    assert assessment["host_handoff_allowed"] is False
    assert assessment["execution_performed"] is False
    assert tuple(assessment["required_host_actions"]) == MCP_REVIEW_HOST_ACTIONS
    assert "obtain_final_destructive_action_confirmation" in assessment["required_host_actions"]
    assert "execute_outside_ainir_core" not in assessment["required_host_actions"]
    assert "do_not_execute" in assessment["required_host_actions"]
    assert not [item for item in assessment["checks"] if item["status"] == "failed"]
    assert validate_mcp_tool_call_assessment(assessment).valid


def test_host_context_and_assessment_self_hashes_reject_tampering() -> None:
    *_, context, assessment = _safe_artifacts()
    tampered_context = deepcopy(context)
    tampered_context["capability_grants"] = ["cap.resource.write"]
    assert tampered_context["context_sha256"] != sha256_json(mcp_host_context_projection(tampered_context))
    assert not validate_mcp_host_context(tampered_context).valid
    tampered_assessment = deepcopy(assessment)
    tampered_assessment["host_handoff_allowed"] = False
    assert tampered_assessment["assessment_sha256"] != sha256_json(mcp_tool_call_assessment_projection(tampered_assessment))
    assert not validate_mcp_tool_call_assessment(tampered_assessment).valid


def test_ambiguous_workspace_paths_are_refused() -> None:
    report = run_bundled_mcp_conformance()
    by_id = {item["case_id"]: item for item in report["results"]}
    for case_id in (
        "absolute_path_refused",
        "path_traversal_refused",
        "windows_ads_path_refused",
        "windows_reserved_device_path_refused",
        "control_character_path_refused",
    ):
        assert by_id[case_id]["passed"] is True
        assert by_id[case_id]["actual_status"] == "refused"
        assert "resources.normalized" in by_id[case_id]["failed_checks"]


def test_credentials_in_argument_names_metadata_or_values_are_refused() -> None:
    report = run_bundled_mcp_conformance()
    by_id = {item["case_id"]: item for item in report["results"]}
    for case_id in (
        "credential_argument_refused",
        "credential_meta_refused",
        "credential_value_in_content_refused",
    ):
        assert by_id[case_id]["actual_status"] == "refused"
        assert "arguments.sensitive_paths" in by_id[case_id]["failed_checks"]


def test_authorization_consent_capability_and_transaction_fail_closed() -> None:
    report = run_bundled_mcp_conformance()
    by_id = {item["case_id"]: item for item in report["results"]}
    expected = {
        "wrong_audience_refused": "host.authorization.audience",
        "missing_consent_refused": "host.consent.decision",
        "expired_consent_refused": "host.consent.validity",
        "capability_widening_refused": "host.capabilities.exact",
        "missing_transaction_refused": "host.transaction.present",
        "missing_rollback_refused": "host.transaction.rollback_available",
        "unauthenticated_server_refused": "host.server.authenticated",
        "symlink_unresolved_refused": "host.resource_resolution.symlinks",
    }
    for case_id, check in expected.items():
        assert by_id[case_id]["passed"] is True
        assert by_id[case_id]["actual_status"] == "refused"
        assert check in by_id[case_id]["failed_checks"]


def test_untrusted_annotations_cannot_downgrade_reviewed_effects() -> None:
    report = run_bundled_mcp_conformance()
    item = next(item for item in report["results"] if item["case_id"] == "annotation_understates_write_refused")
    assert item["actual_status"] == "refused"
    assert "annotations.read_only_not_understated" in item["failed_checks"]


def test_task_and_multi_round_input_surfaces_are_refused_in_bounded_p6() -> None:
    report = run_bundled_mcp_conformance()
    by_id = {item["case_id"]: item for item in report["results"]}
    assert "task.not_requested" in by_id["task_requested_refused"]["failed_checks"]
    assert "mrtr.not_present" in by_id["mrtr_present_refused"]["failed_checks"]


def test_conformance_pack_and_report_are_deterministic_and_non_executing(tmp_path: Path) -> None:
    pack = load_bundled_mcp_conformance_pack()
    assert all(item["status"] == "passed" for item in validate_mcp_conformance_pack(pack))
    assert pack["pack_sha256"] == sha256_json(mcp_conformance_pack_projection(pack))
    first = run_bundled_mcp_conformance(out_dir=tmp_path / "first")
    second = run_bundled_mcp_conformance(out_dir=tmp_path / "second")
    assert first["overall_status"] == "passed"
    assert first["case_count"] == 26
    assert first["passed"] == 26
    assert first["failed"] == 0
    assert first["report_sha256"] == second["report_sha256"]
    assert first["report_sha256"] == sha256_json(mcp_conformance_report_projection(first))
    assert first["execution_performed"] is False
    assert first["trust_gate_override_allowed"] is False
    assert (tmp_path / "first/mcp_tool_call_conformance_report.junit.xml").is_file()


def test_mcp_public_schemas_validate_real_artifacts() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    profile, _, _, _, envelope, context, assessment = _safe_artifacts()
    artifacts = {
        "mcp_tool_call_profile.schema.json": profile,
        "mcp_tool_call_envelope.schema.json": envelope,
        "mcp_host_context.schema.json": context,
        "mcp_tool_call_assessment.schema.json": assessment,
        "mcp_tool_call_conformance_pack.schema.json": load_bundled_mcp_conformance_pack(),
        "mcp_tool_call_conformance_report.schema.json": run_bundled_mcp_conformance(),
    }
    for name, artifact in artifacts.items():
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(artifact, schema)


def test_profile_tampering_and_unknown_fields_fail_validation() -> None:
    with materialized_mcp_profile_source() as profile:
        tampered = deepcopy(profile.data)
        tampered["policies"]["tool_annotations_are_evidence"] = True
        assert not validate_mcp_tool_call_profile(tampered).valid
        unknown = deepcopy(profile.data)
        unknown["trust_me"] = True
        unknown["profile_sha256"] = sha256_json(mcp_tool_call_profile_projection(unknown))
        assert not validate_mcp_tool_call_profile(unknown).valid


def test_host_owned_adapter_has_no_execution_or_transport_methods() -> None:
    with bundled_mcp_reference_adapter() as adapter:
        assert adapter.profile.profile_id == BUILTIN_MCP_PROFILE_ID
        for forbidden in ("execute", "send", "connect", "request", "open_transport", "authorize"):
            assert not hasattr(adapter, forbidden)


def test_cli_profile_assess_and_conformance(tmp_path: Path) -> None:
    profile = _run_cli("mcp", "profile", "--json")
    assert profile.returncode == 0, profile.stderr
    assert json.loads(profile.stdout)["validation"]["overall_status"] == "passed"
    out = tmp_path / "assessment"
    assess = _run_cli(
        "mcp", "assess",
        str(EXAMPLE / "tool_descriptor.json"),
        str(EXAMPLE / "tool_call.json"),
        str(EXAMPLE / "transport_binding.json"),
        str(EXAMPLE / "host_input.json"),
        "--out-dir", str(out), "--json",
    )
    assert assess.returncode == 0, assess.stderr
    payload = json.loads(assess.stdout)
    assert payload["overall_status"] == "passed"
    assert payload["execution_performed"] is False
    assert (out / "mcp_tool_call_envelope.json").is_file()
    assert (out / "mcp_host_context.json").is_file()
    assert (out / "mcp_tool_call_assessment.json").is_file()
    conf = _run_cli("mcp", "conformance", "--out-dir", str(tmp_path / "conformance"), "--json")
    assert conf.returncode == 0, conf.stderr
    report = json.loads(conf.stdout)
    assert report["case_count"] == report["passed"] == 26
    assert report["execution_performed"] is False


def test_existing_registry_hash_and_core_trust_gate_are_unchanged() -> None:
    assert registry_snapshot()["combined_sha256"] == EXPECTED_REGISTRY_HASH
    result = _run_cli("trust", "evaluate", str(ROOT / "examples/create_user_outbox_safe/draft.yaml"), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["receipt"]["registry_snapshot_hash"] == EXPECTED_REGISTRY_HASH


def test_mcp_reference_code_contains_no_network_or_execution_primitive() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/ainir/mcp_tool_call.py", ROOT / "src/ainir/mcp_host_adapter.py")
    )
    forbidden = ("requests.", "httpx.", "urllib.request", "socket.", "subprocess.", "os.system(", "shell=True")
    assert not any(token in text for token in forbidden)


def test_content_addressed_ids_reject_substitution_even_with_valid_hashes() -> None:
    *_, envelope, context, assessment = _safe_artifacts("workspace.write_text")

    substituted_envelope = deepcopy(envelope)
    substituted_envelope["envelope_id"] = "ainir.mcp.envelope." + "f" * 20
    substituted_envelope["envelope_sha256"] = sha256_json(mcp_tool_call_envelope_projection(substituted_envelope))
    envelope_report = validate_mcp_tool_call_envelope(substituted_envelope)
    assert not envelope_report.valid
    assert any(item["check"] == "envelope.id_binding" and item["status"] == "failed" for item in envelope_report.checks)

    substituted_context = deepcopy(context)
    substituted_context["context_id"] = "ainir.mcp.context." + "e" * 20
    substituted_context["context_sha256"] = sha256_json(mcp_host_context_projection(substituted_context))
    context_report = validate_mcp_host_context(substituted_context)
    assert not context_report.valid
    assert any(item["check"] == "context.id_binding" and item["status"] == "failed" for item in context_report.checks)

    substituted_assessment = deepcopy(assessment)
    substituted_assessment["assessment_id"] = "ainir.mcp.assessment." + "d" * 20
    substituted_assessment["assessment_sha256"] = sha256_json(mcp_tool_call_assessment_projection(substituted_assessment))
    assessment_report = validate_mcp_tool_call_assessment(substituted_assessment)
    assert not assessment_report.valid
    assert any(item["check"] == "assessment.id_binding" and item["status"] == "failed" for item in assessment_report.checks)


def test_nested_context_and_consent_tampering_fails_after_outer_rehash() -> None:
    *_, context, _ = _safe_artifacts()

    nested_unknown = deepcopy(context)
    nested_unknown["server_binding"]["trust_me"] = True
    nested_unknown["context_sha256"] = sha256_json(mcp_host_context_projection(nested_unknown))
    nested_unknown["context_id"] = "ainir.mcp.context." + nested_unknown["context_sha256"].removeprefix("sha256:")[:20]
    report = validate_mcp_host_context(nested_unknown)
    assert not report.valid
    assert any(item["check"] == "context.server_binding.unknown_fields" and item["status"] == "failed" for item in report.checks)

    consent_swap = deepcopy(context)
    consent_swap["consent"]["consent_id"] = "ainir.mcp.consent." + "a" * 20
    consent_swap["context_sha256"] = sha256_json(mcp_host_context_projection(consent_swap))
    consent_swap["context_id"] = "ainir.mcp.context." + consent_swap["context_sha256"].removeprefix("sha256:")[:20]
    report = validate_mcp_host_context(consent_swap)
    assert not report.valid
    assert any(item["check"] == "context.consent.id_binding" and item["status"] == "failed" for item in report.checks)


def test_transaction_id_is_bound_to_the_envelope_hash() -> None:
    *_, context, _ = _safe_artifacts("workspace.write_text")
    tampered = deepcopy(context)
    tampered["transaction"]["transaction_id"] = "ainir.mcp.transaction." + "b" * 20
    tampered["context_sha256"] = sha256_json(mcp_host_context_projection(tampered))
    tampered["context_id"] = "ainir.mcp.context." + tampered["context_sha256"].removeprefix("sha256:")[:20]
    report = validate_mcp_host_context(tampered)
    assert not report.valid
    assert any(item["check"] == "context.transaction.id_binding" and item["status"] == "failed" for item in report.checks)


def test_bool_jsonrpc_id_and_external_schema_ref_fail_closed() -> None:
    with materialized_mcp_profile_source() as profile:
        descriptor = load_json_mapping(profile.root / "descriptors/workspace.read_text.json", label="descriptor")
        call = {
            "jsonrpc": "2.0",
            "id": True,
            "method": "tools/call",
            "params": {"name": "workspace.read_text", "arguments": {"path": "docs/README.md"}},
        }
        transport = {"protocol_version": "2026-07-28", "method_header": "tools/call", "name_header": "workspace.read_text"}
        with pytest.raises(MCPToolCallError):
            build_mcp_tool_call_envelope(profile, descriptor, call, transport)

        external = deepcopy(descriptor)
        external["inputSchema"]["properties"]["path"] = {"$ref": "https://attacker.invalid/path.schema.json"}
        report = validate_mcp_tool_descriptor(external)
        assert not report.valid
        assert any(item["check"] == "descriptor.input_schema.external_refs" and item["status"] == "failed" for item in report.checks)


def test_profile_descriptor_path_escape_and_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    import shutil
    import yaml

    with materialized_mcp_profile_source() as profile:
        copied = tmp_path / "profile"
        shutil.copytree(profile.root, copied)
    profile_path = copied / "profile.yaml"
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    data["tools"][0]["descriptor"] = "../outside.json"
    data["profile_sha256"] = sha256_json(mcp_tool_call_profile_projection(data))
    profile_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    loaded = load_mcp_tool_call_profile(profile_path)
    report = validate_mcp_tool_call_profile(loaded)
    assert not report.valid
    assert any(item["check"].endswith(".descriptor_load") and item["status"] == "failed" for item in report.checks)

    pack = deepcopy(load_bundled_mcp_conformance_pack())
    pack["cases"][1]["case_id"] = pack["cases"][0]["case_id"]
    pack["pack_sha256"] = sha256_json(mcp_conformance_pack_projection(pack))
    checks = validate_mcp_conformance_pack(pack)
    assert any(item["check"].endswith(".case_id") and item["status"] == "failed" for item in checks)


def test_host_owned_adapter_normalizes_and_assesses_without_execution() -> None:
    with bundled_mcp_reference_adapter() as adapter:
        descriptor = load_json_mapping(adapter.profile.root / "descriptors/workspace.read_text.json", label="descriptor")
        call = {
            "jsonrpc": "2.0",
            "id": "adapter-call-1",
            "method": "tools/call",
            "params": {"name": "workspace.read_text", "arguments": {"path": "docs/README.md"}},
        }
        transport = {"protocol_version": "2026-07-28", "method_header": "tools/call", "name_header": "workspace.read_text"}
        envelope = adapter.normalize(descriptor, call, transport)
        context = build_mcp_host_context(
            envelope=envelope,
            host_id="host.adapter.pytest",
            actor_id="human.adapter.pytest",
            evaluation_time="2026-08-10T00:00:00Z",
            server_id="mcp.server.workspace.reference",
            server_origin="mcp+stdio://workspace.reference",
            authorization_audience="mcp.server.workspace.reference",
            authenticated=True,
            schema_validator_id="host.schema.adapter.pytest.v1",
            schema_validation_status="passed",
            capability_grants=["cap.resource.read"],
            resource_scope_ids=["scope.workspace.adapter.pytest"],
            resource_resolution_status="passed",
            symlinks_resolved=True,
            consent_decision="approved",
            consent_issued_at="2026-08-09T23:59:00Z",
            consent_valid_until="2026-08-10T00:05:00Z",
        )
        assessment = adapter.assess(envelope, context)
        assert assessment["overall_status"] == "passed"
        assert assessment["execution_performed"] is False
        assert tuple(assessment["required_host_actions"]) == MCP_PASSED_HOST_ACTIONS


def test_assessment_risk_and_host_actions_cannot_be_rewritten_after_rehash() -> None:
    *_, passed = _safe_artifacts()
    action_swap = deepcopy(passed)
    action_swap["required_host_actions"] = list(MCP_REFUSED_HOST_ACTIONS)
    action_swap["assessment_sha256"] = sha256_json(mcp_tool_call_assessment_projection(action_swap))
    action_swap["assessment_id"] = "ainir.mcp.assessment." + action_swap["assessment_sha256"].removeprefix("sha256:")[:20]
    report = validate_mcp_tool_call_assessment(action_swap)
    assert not report.valid
    assert any(item["check"] == "assessment.required_host_actions" and item["status"] == "failed" for item in report.checks)

    risk_swap = deepcopy(passed)
    risk_swap["risk_class"] = None
    risk_swap["assessment_sha256"] = sha256_json(mcp_tool_call_assessment_projection(risk_swap))
    risk_swap["assessment_id"] = "ainir.mcp.assessment." + risk_swap["assessment_sha256"].removeprefix("sha256:")[:20]
    report = validate_mcp_tool_call_assessment(risk_swap)
    assert not report.valid
    assert any(item["check"] == "assessment.risk_class" and item["status"] == "failed" for item in report.checks)

    conformance = run_bundled_mcp_conformance()
    refused = next(item for item in conformance["results"] if item["case_id"] == "unknown_tool_refused")
    assert tuple(refused["required_host_actions"]) == MCP_REFUSED_HOST_ACTIONS
    assert "execute_outside_ainir_core" not in refused["required_host_actions"]
