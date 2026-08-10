from __future__ import annotations

from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import ainir
from ainir.canonical import MAX_JSON_BYTES, sha256_json
from ainir.contracts import artifact_contract_manifest
from ainir.mcp_authoring import MCPProfileAuthoringError, initialize_mcp_profile
from ainir.mcp_conformance import (
    load_mcp_conformance_pack,
    mcp_conformance_pack_projection,
    run_mcp_conformance,
    validate_mcp_conformance_pack,
)
from ainir.mcp_tool_call import BUILTIN_MCP_PROFILE_ID, materialized_mcp_profile_source
from ainir.openai_function_tool_adapter import (
    HostOwnedOpenAIFunctionToolAdapter,
    OpenAIFunctionToolError,
    build_openai_function_call_binding,
    build_openai_function_tool_preflight,
    bundled_openai_function_tool_adapter,
    openai_function_call_binding_projection,
    openai_function_tool_preflight_projection,
    validate_openai_function_call_binding,
    validate_openai_function_tool_preflight,
)
from ainir.registry_provenance import registry_snapshot
from ainir.resources import PUBLIC_SCHEMA_NAMES, read_schema_text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/openai_function_tool"
EXPECTED_REGISTRY_HASH = "sha256:35379edcb7d6a19ffd82f648fbf0f69c8729fd6d7d60b5333f939c957a786f0a"


def _load(name: str) -> dict:
    return json.loads((EXAMPLE / name).read_text(encoding="utf-8"))


def _artifacts():
    with materialized_mcp_profile_source() as profile:
        binding, envelope = build_openai_function_call_binding(
            profile,
            _load("tool_definition.json"),
            _load("function_call.json"),
            _load("host_binding.json"),
        )
        preflight = build_openai_function_tool_preflight(
            profile,
            _load("tool_definition.json"),
            _load("function_call.json"),
            _load("host_binding.json"),
            _load("host_input.json"),
        )
        return binding, envelope, preflight


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


def test_p7_contracts_and_schemas_are_public_unique_and_packaged() -> None:
    assert ainir.OPENAI_FUNCTION_CALL_BINDING_CONTRACT == "ainir.openai-function-call-binding.v1"
    assert ainir.OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT == "ainir.openai-function-tool-preflight.v1"
    names = {
        "openai_function_call_binding.schema.json",
        "openai_function_tool_preflight.schema.json",
    }
    assert names <= set(PUBLIC_SCHEMA_NAMES)
    for name in names:
        root = ROOT / "schemas" / name
        packaged = ROOT / "src/ainir/schemas" / name
        assert root.read_bytes() == packaged.read_bytes()
        assert read_schema_text(name) == root.read_text(encoding="utf-8")
    manifest = artifact_contract_manifest()["contracts"]
    assert manifest["openai_function_call_binding"]["identifier"] == ainir.OPENAI_FUNCTION_CALL_BINDING_CONTRACT
    assert manifest["openai_function_tool_preflight"]["identifier"] == ainir.OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT
    identifiers = [item["identifier"] for item in manifest.values()]
    assert len(identifiers) == len(set(identifiers))


def test_external_mcp_scaffold_is_valid_and_conformance_is_deterministic(tmp_path: Path) -> None:
    target = tmp_path / "profile"
    profile_path, pack_path = initialize_mcp_profile(
        target,
        profile_id="example.readonly.workspace.v1",
        tool_name="workspace.example_read",
    )
    assert profile_path == target / "profile.yaml"
    assert pack_path == target / "cases.yaml"
    pack = load_mcp_conformance_pack(pack_path)
    assert all(item["status"] == "passed" for item in validate_mcp_conformance_pack(
        pack,
        expected_profile_id="example.readonly.workspace.v1",
        profile_root=target,
        allow_scenarios=False,
    ))
    assert pack["pack_sha256"] == sha256_json(mcp_conformance_pack_projection(pack))
    first = run_mcp_conformance(profile_path, pack_source=pack_path, out_dir=tmp_path / "first")
    second = run_mcp_conformance(profile_path, pack_source=pack_path, out_dir=tmp_path / "second")
    assert first["overall_status"] == "passed"
    assert first["case_count"] == first["passed"] == 4
    assert first["failed"] == 0
    assert first["report_sha256"] == second["report_sha256"]
    assert first["execution_performed"] is False
    assert first["trust_gate_override_allowed"] is False


def test_external_conformance_pack_rejects_fixture_escape_and_scenario_mode(tmp_path: Path) -> None:
    target = tmp_path / "profile"
    profile_path, pack_path = initialize_mcp_profile(
        target,
        profile_id="example.fixture.boundary.v1",
        tool_name="workspace.boundary_read",
    )
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    pack["cases"][0]["fixtures"]["call"] = "../outside.json"
    pack["pack_sha256"] = sha256_json(mcp_conformance_pack_projection(pack))
    bad_path = target / "bad.yaml"
    bad_path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")
    checks = validate_mcp_conformance_pack(pack, expected_profile_id=pack["profile_id"], profile_root=target, allow_scenarios=False)
    assert any(item["check"].endswith("fixtures.call") and item["status"] == "failed" for item in checks)
    with pytest.raises(ValueError):
        run_mcp_conformance(profile_path, pack_source=bad_path)

    scenario = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    scenario["cases"][0].pop("fixtures")
    scenario["cases"][0]["scenario"] = "safe_read"
    scenario["pack_sha256"] = sha256_json(mcp_conformance_pack_projection(scenario))
    scenario_path = target / "scenario.yaml"
    scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match=r"pack.cases\[0\].scenario"):
        run_mcp_conformance(profile_path, pack_source=scenario_path)


def test_scaffold_refuses_nonempty_target_and_invalid_identity(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("do not delete", encoding="utf-8")
    with pytest.raises(MCPProfileAuthoringError):
        initialize_mcp_profile(occupied, profile_id="valid.profile.v1", tool_name="workspace.read")
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "do not delete"
    with pytest.raises(MCPProfileAuthoringError):
        initialize_mcp_profile(tmp_path / "bad", profile_id="../bad", tool_name="workspace.read")


def test_openai_safe_binding_and_preflight_are_self_hashed_and_nonexecuting() -> None:
    binding, envelope, preflight = _artifacts()
    assert validate_openai_function_call_binding(binding).valid
    assert validate_openai_function_tool_preflight(preflight).valid
    assert binding["binding_sha256"] == sha256_json(openai_function_call_binding_projection(binding))
    assert preflight["preflight_sha256"] == sha256_json(openai_function_tool_preflight_projection(preflight))
    assert binding["mcp_envelope_sha256"] == envelope["envelope_sha256"]
    assert preflight["overall_status"] == "passed"
    assert preflight["host_handoff_allowed"] is True
    assert preflight["execution_performed"] is False
    assert preflight["openai_api_called"] is False
    assert preflight["tool_output_submitted"] is False
    assert preflight["credentials_processed"] is False
    assert preflight["production_runtime_ready"] is False


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("tool", "strict", False, "strict=true"),
        ("call", "status", "in_progress", "completed function_call"),
        ("call", "name", "workspace.write_text", "names differ"),
        ("host", "response_status", "in_progress", "completed Responses"),
        ("host", "output_index", True, "non-negative integer"),
    ],
)
def test_openai_adapter_rejects_unfinalized_or_ambiguous_bindings(target: str, field: str, value, message: str) -> None:
    tool = _load("tool_definition.json")
    call = _load("function_call.json")
    host = _load("host_binding.json")
    {"tool": tool, "call": call, "host": host}[target][field] = value
    with materialized_mcp_profile_source() as profile, pytest.raises(OpenAIFunctionToolError, match=message):
        build_openai_function_call_binding(profile, tool, call, host)


def test_openai_adapter_rejects_schema_drift_duplicate_keys_nonobject_and_nonfinite() -> None:
    tool = _load("tool_definition.json")
    call = _load("function_call.json")
    host = _load("host_binding.json")
    drift = deepcopy(tool)
    drift["parameters"]["properties"]["path"]["maxLength"] = 999
    with materialized_mcp_profile_source() as profile:
        with pytest.raises(OpenAIFunctionToolError, match="do not match"):
            build_openai_function_call_binding(profile, drift, call, host)
        duplicate = deepcopy(call)
        duplicate["arguments"] = '{"path":"a","path":"b"}'
        with pytest.raises(OpenAIFunctionToolError, match="duplicate-key-free"):
            build_openai_function_call_binding(profile, tool, duplicate, host)
        nonobject = deepcopy(call)
        nonobject["arguments"] = '["docs/README.md"]'
        with pytest.raises(OpenAIFunctionToolError, match="root must decode to an object"):
            build_openai_function_call_binding(profile, tool, nonobject, host)
        nonfinite = deepcopy(call)
        nonfinite["arguments"] = '{"path":NaN}'
        with pytest.raises(OpenAIFunctionToolError, match="non-finite"):
            build_openai_function_call_binding(profile, tool, nonfinite, host)


def test_openai_adapter_rejects_oversized_or_deep_source_artifacts() -> None:
    tool = _load("tool_definition.json")
    call = _load("function_call.json")
    host = _load("host_binding.json")
    oversized = deepcopy(tool)
    oversized["description"] = "x" * (MAX_JSON_BYTES + 1)
    with materialized_mcp_profile_source() as profile, pytest.raises(OpenAIFunctionToolError, match="exceeds"):
        build_openai_function_call_binding(profile, oversized, call, host)

    deeply_nested = deepcopy(host)
    value: dict = {}
    cursor = value
    for _ in range(170):
        child: dict = {}
        cursor["nested"] = child
        cursor = child
    deeply_nested["unexpected"] = value
    with materialized_mcp_profile_source() as profile, pytest.raises(OpenAIFunctionToolError, match="nesting depth"):
        build_openai_function_call_binding(profile, tool, call, deeply_nested)


def test_external_conformance_does_not_mask_unexpected_programming_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "profile"
    profile_path, pack_path = initialize_mcp_profile(
        target,
        profile_id="example.error.visibility.v1",
        tool_name="workspace.error_visibility_read",
    )
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    pack["cases"] = [deepcopy(pack["cases"][0])]
    pack["cases"][0]["expected_status"] = "invalid"
    pack["cases"][0]["required_failed_checks"] = []
    pack["cases"][0]["required_host_actions"] = []
    pack["pack_sha256"] = sha256_json(mcp_conformance_pack_projection(pack))
    invalid_path = target / "unexpected-error.yaml"
    invalid_path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")

    def explode(*_args, **_kwargs):
        raise TypeError("programming defect must escape the conformance harness")

    monkeypatch.setattr("ainir.mcp_conformance.build_mcp_tool_call_envelope", explode)
    with pytest.raises(TypeError, match="programming defect"):
        run_mcp_conformance(profile_path, pack_source=invalid_path)


def test_openai_credential_values_are_refused_by_p6_preflight() -> None:
    call = _load("function_call.json")
    call["arguments"] = json.dumps({"path": "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefgh.ijklmnop"})
    with materialized_mcp_profile_source() as profile:
        preflight = build_openai_function_tool_preflight(
            profile,
            _load("tool_definition.json"),
            call,
            _load("host_binding.json"),
            _load("host_input.json"),
        )
    assert preflight["overall_status"] == "refused"
    failed = {item["check"] for item in preflight["mcp_assessment"]["checks"] if item["status"] == "failed"}
    assert "arguments.sensitive_paths" in failed
    assert validate_openai_function_tool_preflight(preflight).valid


def test_openai_binding_and_preflight_tampering_fail_even_after_nested_changes() -> None:
    binding, _, preflight = _artifacts()
    tampered_binding = deepcopy(binding)
    tampered_binding["function_name"] = "workspace.write_text"
    assert not validate_openai_function_call_binding(tampered_binding).valid
    tampered_preflight = deepcopy(preflight)
    tampered_preflight["tool_output_submitted"] = True
    assert not validate_openai_function_tool_preflight(tampered_preflight).valid


def test_openai_public_schemas_validate_real_artifacts() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    binding, _, preflight = _artifacts()
    for name, artifact in {
        "openai_function_call_binding.schema.json": binding,
        "openai_function_tool_preflight.schema.json": preflight,
    }.items():
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(artifact, schema)


def test_openai_adapter_exposes_no_api_transport_execution_or_output_submission() -> None:
    with bundled_openai_function_tool_adapter() as adapter:
        assert isinstance(adapter, HostOwnedOpenAIFunctionToolAdapter)
        for forbidden in (
            "execute", "send", "connect", "request", "open_transport", "authorize",
            "create_response", "submit_tool_output", "responses", "client",
        ):
            assert not hasattr(adapter, forbidden)
    source = inspect.getsource(sys.modules["ainir.openai_function_tool_adapter"])
    forbidden_tokens = (
        "import openai", "from openai", "requests.", "httpx.", "urllib.request",
        "socket.", "subprocess.", "os.system(", "shell=True",
    )
    assert not any(token in source for token in forbidden_tokens)


def test_cli_scaffold_external_conformance_and_openai_preflight(tmp_path: Path) -> None:
    target = tmp_path / "profile"
    init = _run_cli(
        "mcp", "init", str(target),
        "--profile-id", "example.cli.readonly.v1",
        "--tool-name", "workspace.cli_read",
    )
    assert init.returncode == 0, init.stderr
    assert "execution_performed: false" in init.stdout
    conf = _run_cli(
        "mcp", "conformance",
        "--profile", str(target / "profile.yaml"),
        "--cases", str(target / "cases.yaml"),
        "--out-dir", str(tmp_path / "conf"),
        "--json",
    )
    assert conf.returncode == 0, conf.stderr
    report = json.loads(conf.stdout)
    assert report["case_count"] == report["passed"] == 4

    normalize = _run_cli(
        "openai", "function-tool", "normalize",
        str(EXAMPLE / "tool_definition.json"),
        str(EXAMPLE / "function_call.json"),
        str(EXAMPLE / "host_binding.json"),
        "--out-dir", str(tmp_path / "normalize"), "--json",
    )
    assert normalize.returncode == 0, normalize.stderr
    binding = json.loads(normalize.stdout)
    assert binding["openai_api_called"] is False
    assess = _run_cli(
        "openai", "function-tool", "assess",
        str(EXAMPLE / "tool_definition.json"),
        str(EXAMPLE / "function_call.json"),
        str(EXAMPLE / "host_binding.json"),
        str(EXAMPLE / "host_input.json"),
        "--out-dir", str(tmp_path / "assess"), "--json",
    )
    assert assess.returncode == 0, assess.stderr
    preflight = json.loads(assess.stdout)
    assert preflight["overall_status"] == "passed"
    assert preflight["openai_api_called"] is False
    assert preflight["tool_output_submitted"] is False
    assert preflight["execution_performed"] is False
    assert (tmp_path / "assess/openai_function_tool_preflight.json").is_file()


def test_existing_registry_hash_and_trust_gate_remain_unchanged() -> None:
    assert registry_snapshot()["combined_sha256"] == EXPECTED_REGISTRY_HASH
    result = _run_cli("trust", "evaluate", str(ROOT / "examples/create_user_outbox_safe/draft.yaml"), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["receipt"]["registry_snapshot_hash"] == EXPECTED_REGISTRY_HASH


def test_preflight_rejects_cross_artifact_substitution_after_outer_rehash() -> None:
    _, _, read_preflight = _artifacts()
    with materialized_mcp_profile_source() as profile:
        descriptor = json.loads((profile.root / "descriptors/workspace.write_text.json").read_text(encoding="utf-8"))
        tool = {
            "type": "function",
            "name": "workspace.write_text",
            "description": descriptor["description"],
            "parameters": descriptor["inputSchema"],
            "strict": True,
        }
        call = {
            "type": "function_call",
            "id": "fc_write_substitution",
            "call_id": "call_write_substitution",
            "name": "workspace.write_text",
            "arguments": '{"path":"notes/out.txt","content":"safe"}',
            "status": "completed",
        }
        binding = {"response_id": "resp_write_substitution", "response_status": "completed", "output_index": 0}
        host = _load("host_input.json")
        host["capability_grants"] = ["cap.resource.write"]
        host["resource_scope_ids"] = ["scope.workspace.notes"]
        host["transaction_status"] = "prepared"
        host["rollback_available"] = True
        host["rollback_plan_sha256"] = "sha256:" + "1" * 64
        write_preflight = build_openai_function_tool_preflight(profile, tool, call, binding, host)
    assert validate_openai_function_tool_preflight(write_preflight).valid
    mixed = deepcopy(read_preflight)
    mixed["mcp_assessment"] = deepcopy(write_preflight["mcp_assessment"])
    mixed["overall_status"] = mixed["mcp_assessment"]["overall_status"]
    mixed["host_handoff_allowed"] = mixed["mcp_assessment"]["host_handoff_allowed"]
    mixed["required_host_actions"] = deepcopy(mixed["mcp_assessment"]["required_host_actions"])
    mixed["preflight_sha256"] = sha256_json(openai_function_tool_preflight_projection(mixed))
    mixed["preflight_id"] = "ainir.openai.preflight." + mixed["preflight_sha256"].removeprefix("sha256:")[:20]
    report = validate_openai_function_tool_preflight(mixed)
    assert not report.valid
    failed = {item["check"] for item in report.checks if item["status"] == "failed"}
    assert "preflight.assessment.tool_name" in failed
    assert "preflight.assessment.envelope_hash" in failed


def test_p7_readiness_release_ci_and_distribution_are_wired(tmp_path: Path) -> None:
    from ainir.openai_function_tool_eval import run_openai_function_tool_adapter_check
    report = run_openai_function_tool_adapter_check(tmp_path / "readiness")
    assert report["overall_status"] == "passed"
    assert report["checks_total"] == report["checks_passed"] == 10
    assert report["external_profile_case_count"] == 4
    assert report["openai_api_called"] is False
    assert report["tool_output_submitted"] is False
    assert report["execution_performed"] is False

    manifest = yaml.safe_load((ROOT / "release/v1_0_rc_candidate_manifest.yaml").read_text(encoding="utf-8"))
    p7 = manifest["p7_openai_function_tool_adapter"]
    assert p7 and all(value is True for value in p7.values())
    assert "openai_function_tool_adapter_p7" in manifest["required_checks"]

    phase30 = (ROOT / "src/ainir/phase30_v1_rc_candidate.py").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution_contracts.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run_openai_function_tool_adapter_check" in phase30
    assert "p7_openai_function_tool_adapter" in phase30
    assert "installed_wheel_openai_function_tool_adapter" in distribution
    assert "{verify,trust,receipt,profile,conformance,mcp,openai,evidence,registry,contracts,lower,demo}" in distribution
    assert "check_openai_function_tool_adapter.py" in workflow
    assert "tests/test_p7_openai_host_adapter_and_mcp_authoring.py" in workflow
