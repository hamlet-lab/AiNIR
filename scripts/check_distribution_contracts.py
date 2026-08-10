from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SCRATCH_MARKER = ".ainir-distribution-contract-scratch"

sys.path.insert(0, str(ROOT / "src"))
from ainir._version import __version__ as EXPECTED_VERSION  # noqa: E402
from ainir.contracts import (  # noqa: E402
    EVIDENCE_BUNDLE_CONTRACT,
    EVIDENCE_PROVIDER_POLICY_CONTRACT,
    EVIDENCE_VALIDATION_REPORT_CONTRACT,
    MCP_HOST_CONTEXT_CONTRACT,
    MCP_TOOL_CALL_ASSESSMENT_CONTRACT,
    MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT,
    MCP_TOOL_CALL_ENVELOPE_CONTRACT,
    MCP_TOOL_CALL_PROFILE_CONTRACT,
    REGISTRY_DIFF_CONTRACT,
    REGISTRY_MIGRATION_RECORD_CONTRACT,
    REGISTRY_SNAPSHOT_CONTRACT,
    TRUST_GATE_DECISION_CONTRACT,
    TRUST_RECEIPT_CONTRACT,
    TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "passed" if passed else "failed", **details}


def _copy_source(destination: Path) -> Path:
    source = destination / "source"
    ignore = shutil.ignore_patterns(
        ".git",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.egg-info",
        "build",
        "dist",
        "node_modules",
    )
    shutil.copytree(ROOT, source, ignore=ignore)
    return source


def _build_artifacts(source: Path, dist: Path) -> subprocess.CompletedProcess[str]:
    dist.mkdir(parents=True, exist_ok=True)
    code = (
        "from setuptools import build_meta; "
        f"out={str(dist)!r}; "
        "print(build_meta.build_sdist(out)); "
        "print(build_meta.build_wheel(out))"
    )
    return _run([sys.executable, "-c", code], cwd=source, timeout=240)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _expected_root_resource_hashes(source: Path) -> dict[str, dict[str, str]]:
    groups: dict[str, dict[str, str]] = {"schemas": {}, "registries": {}}
    for plural, directory in (("schemas", source / "schemas"), ("registries", source / "registries")):
        for path in sorted(p for p in directory.iterdir() if p.is_file()):
            groups[plural][path.name] = _sha256_bytes(path.read_bytes())
    return groups


def _wheel_resource_entries(wheel: Path) -> set[str]:
    with ZipFile(wheel) as archive:
        return set(archive.namelist())


def _sdist_resource_entries(sdist: Path) -> set[str]:
    with tarfile.open(sdist, "r:gz") as archive:
        return set(archive.getnames())


def _installed_runtime_probe(site: Path, runtime: Path) -> subprocess.CompletedProcess[str]:
    code = """
import json
from importlib.metadata import version
from pathlib import Path
import ainir
from ainir.resources import public_resource_manifest
print(json.dumps({
    "runtime_version": ainir.__version__,
    "metadata_version": version("ainir-public-demo"),
    "module_path": str(Path(ainir.__file__).resolve()),
    "resource_manifest": public_resource_manifest(),
}, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["PYTHONNOUSERSITE"] = "1"
    return _run([sys.executable, "-c", code], cwd=runtime, env=env)


def _installed_cli(
    site: Path,
    runtime: Path,
    args: list[str],
    *,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["PYTHONNOUSERSITE"] = "1"
    return _run([sys.executable, "-m", "ainir", *args], cwd=runtime, env=env, timeout=timeout)




def _installed_offline_evidence_probe(
    site: Path,
    runtime: Path,
    *,
    draft: Path,
    out_dir: Path,
) -> subprocess.CompletedProcess[str]:
    code = f"""
import json
from ainir.offline_evidence_provider_eval import run_offline_evidence_provider_check
report = run_offline_evidence_provider_check({str(out_dir)!r}, draft_path={str(draft)!r})
print(json.dumps(report, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["PYTHONNOUSERSITE"] = "1"
    return _run([sys.executable, "-c", code], cwd=runtime, env=env, timeout=180)


def _installed_mcp_tool_call_probe(
    site: Path,
    runtime: Path,
    *,
    out_dir: Path,
) -> subprocess.CompletedProcess[str]:
    code = f"""
import json
from ainir.mcp_tool_call_eval import run_mcp_tool_call_profile_check
report = run_mcp_tool_call_profile_check({str(out_dir)!r})
print(json.dumps(report, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["PYTHONNOUSERSITE"] = "1"
    return _run([sys.executable, "-c", code], cwd=runtime, env=env, timeout=240)


def _installed_openai_function_tool_probe(
    site: Path,
    runtime: Path,
    *,
    out_dir: Path,
) -> subprocess.CompletedProcess[str]:
    code = f"""
import json
from ainir.openai_function_tool_eval import run_openai_function_tool_adapter_check
report = run_openai_function_tool_adapter_check({str(out_dir)!r})
print(json.dumps(report, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["PYTHONNOUSERSITE"] = "1"
    return _run([sys.executable, "-c", code], cwd=runtime, env=env, timeout=240)


def _installed_profile_sdk_probe(
    site: Path,
    runtime: Path,
    *,
    out_dir: Path,
) -> subprocess.CompletedProcess[str]:
    code = f"""
import json
from pathlib import Path
from ainir.profile_manifest import (
    BUILTIN_PROFILE_ID,
    initialize_profile,
    load_profile_manifest,
    materialized_profile_source,
    validate_profile_manifest,
)
from ainir.conformance_runner import run_profile_conformance

out = Path({str(out_dir)!r})
out.mkdir(parents=True, exist_ok=True)
with materialized_profile_source(BUILTIN_PROFILE_ID) as bundled:
    bundled_validation = validate_profile_manifest(bundled).as_dict()
generated_root = out / "generated-profile"
created = initialize_profile(
    generated_root,
    profile_id="ainir.distribution-smoke.v1",
    workflow_id="DistributionSmokeRequest",
)
generated = load_profile_manifest(created[0])
generated_validation = validate_profile_manifest(generated).as_dict()
conformance = run_profile_conformance(generated, out_dir=out / "conformance").as_dict()
print(json.dumps({{
    "bundled_validation": bundled_validation,
    "generated_validation": generated_validation,
    "conformance": conformance,
}}, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["PYTHONNOUSERSITE"] = "1"
    return _run([sys.executable, "-c", code], cwd=runtime, env=env, timeout=180)


def _prepare_scratch(work_dir: Path) -> Path:
    work_dir = work_dir.expanduser().resolve()
    if work_dir == ROOT or work_dir.is_relative_to(ROOT) or ROOT.is_relative_to(work_dir):
        raise ValueError(f"work directory must be outside the source checkout: {work_dir}")
    marker = work_dir / SCRATCH_MARKER
    if work_dir.exists():
        if not marker.is_file():
            raise ValueError(
                f"refusing to remove unmarked work directory: {work_dir}; "
                "choose a new path or a scratch directory previously created by this script"
            )
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    marker.write_text("AiNIR distribution contract scratch\n", encoding="utf-8")
    return work_dir


def run_distribution_contract_check(work_dir: Path) -> dict[str, Any]:
    work_dir = _prepare_scratch(work_dir)
    source = _copy_source(work_dir)
    dist = work_dir / "dist"
    site = work_dir / "site"
    runtime = work_dir / "runtime"
    runtime.mkdir()

    checks: list[dict[str, Any]] = []

    build = _build_artifacts(source, dist)
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    checks.append(
        _check(
            "build_wheel_and_sdist",
            build.returncode == 0 and len(wheels) == 1 and len(sdists) == 1,
            exit_code=build.returncode,
            wheels=[p.name for p in wheels],
            sdists=[p.name for p in sdists],
            stdout_tail=build.stdout[-2000:],
            stderr_tail=build.stderr[-2000:],
        )
    )
    if not wheels or not sdists:
        return {"overall_status": "failed", "checks": checks}

    wheel = wheels[0]
    sdist = sdists[0]
    wheel_entries = _wheel_resource_entries(wheel)
    expected_wheel = {
        *(f"ainir/schemas/{p.name}" for p in sorted((source / "schemas").iterdir()) if p.is_file()),
        *(f"ainir/registries/{p.name}" for p in sorted((source / "registries").iterdir()) if p.is_file()),
        *(
            "ainir/" + str(p.relative_to(source / "src" / "ainir")).replace(os.sep, "/")
            for p in sorted((source / "src" / "ainir" / "profile_packs").rglob("*.yaml"))
        ),
        *(
            "ainir/" + str(p.relative_to(source / "src" / "ainir")).replace(os.sep, "/")
            for p in sorted((source / "src" / "ainir" / "mcp_profiles").rglob("*"))
            if p.is_file() and p.suffix in {".yaml", ".json"}
        ),
        "ainir/_version.py",
        "ainir/resources.py",
    }
    missing_wheel = sorted(expected_wheel - wheel_entries)
    checks.append(_check("wheel_contains_public_resources", not missing_wheel, missing=missing_wheel))

    sdist_entries = _sdist_resource_entries(sdist)
    expected_sdist_suffixes = {
        *(f"schemas/{p.name}" for p in sorted((source / "schemas").iterdir()) if p.is_file()),
        *(f"registries/{p.name}" for p in sorted((source / "registries").iterdir()) if p.is_file()),
        *(f"src/ainir/schemas/{p.name}" for p in sorted((source / "schemas").iterdir()) if p.is_file()),
        *(f"src/ainir/registries/{p.name}" for p in sorted((source / "registries").iterdir()) if p.is_file()),
        *(
            "src/ainir/" + str(p.relative_to(source / "src" / "ainir")).replace(os.sep, "/")
            for p in sorted((source / "src" / "ainir" / "profile_packs").rglob("*.yaml"))
        ),
        *(
            "src/ainir/" + str(p.relative_to(source / "src" / "ainir")).replace(os.sep, "/")
            for p in sorted((source / "src" / "ainir" / "mcp_profiles").rglob("*"))
            if p.is_file() and p.suffix in {".yaml", ".json"}
        ),
        "release/v1_0_rc_candidate_manifest.yaml",
    }
    missing_sdist = sorted(
        suffix
        for suffix in expected_sdist_suffixes
        if not any(entry.endswith("/" + suffix) for entry in sdist_entries)
    )
    checks.append(_check("sdist_contains_public_contract_sources", not missing_sdist, missing=missing_sdist))

    install = _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--target",
            str(site),
            str(wheel),
        ],
        cwd=runtime,
        timeout=180,
    )
    checks.append(
        _check(
            "install_wheel_without_index",
            install.returncode == 0,
            exit_code=install.returncode,
            stdout_tail=install.stdout[-1200:],
            stderr_tail=install.stderr[-1200:],
        )
    )

    probe = _installed_runtime_probe(site, runtime)
    probe_data: dict[str, Any] = {}
    if probe.returncode == 0:
        try:
            probe_data = json.loads(probe.stdout.strip().splitlines()[-1])
        except Exception:
            probe_data = {}
    module_path = str(probe_data.get("module_path", ""))
    try:
        module_is_installed = Path(module_path).resolve().is_relative_to(site.resolve())
    except (OSError, ValueError):
        module_is_installed = False
    checks.append(
        _check(
            "installed_metadata_matches_runtime",
            probe.returncode == 0
            and probe_data.get("runtime_version") == EXPECTED_VERSION
            and probe_data.get("metadata_version") == EXPECTED_VERSION
            and module_is_installed,
            probe=probe_data,
            stderr_tail=probe.stderr[-1200:],
        )
    )

    expected_hashes = _expected_root_resource_hashes(source)
    installed_manifest = probe_data.get("resource_manifest") if isinstance(probe_data, dict) else None
    installed_hashes: dict[str, dict[str, str]] = {"schemas": {}, "registries": {}}
    if isinstance(installed_manifest, dict):
        for plural in ("schemas", "registries"):
            group = installed_manifest.get(plural)
            if isinstance(group, dict):
                installed_hashes[plural] = {
                    str(name): str(info.get("sha256"))
                    for name, info in group.items()
                    if isinstance(info, dict)
                }
    checks.append(
        _check(
            "source_and_wheel_resource_hashes_match",
            installed_hashes == expected_hashes,
            expected=expected_hashes,
            installed=installed_hashes,
        )
    )

    help_result = _installed_cli(site, runtime, ["--help"])
    checks.append(
        _check(
            "installed_module_cli_outside_checkout",
            help_result.returncode == 0
            and "AiNIR semantic trust and conformance CLI" in help_result.stdout
            and "{verify,trust,receipt,profile,conformance,mcp,openai,evidence,registry,contracts,lower,demo}" in help_result.stdout
            and "phase18-trust-gate-eval" not in help_result.stdout,
            exit_code=help_result.returncode,
            stdout_tail=help_result.stdout[-1000:],
            stderr_tail=help_result.stderr[-1000:],
        )
    )

    draft = source / "examples" / "create_user_outbox_safe" / "draft.yaml"
    gate = _installed_cli(site, runtime, ["trust", "evaluate", str(draft), "--json"])
    gate_data: dict[str, Any] = {}
    if gate.returncode == 0:
        try:
            gate_data = json.loads(gate.stdout)
        except Exception:
            gate_data = {}
    checks.append(
        _check(
            "installed_wheel_safe_trust_gate",
            gate.returncode == 0
            and gate_data.get("version") == TRUST_GATE_DECISION_CONTRACT
            and gate_data.get("status") == "passed"
            and gate_data.get("lowering_allowed") is True,
            exit_code=gate.returncode,
            status=gate_data.get("status"),
            stderr_tail=gate.stderr[-1000:],
        )
    )

    receipts = runtime / "receipts"
    issue = _installed_cli(
        site,
        runtime,
        ["receipt", "issue", str(draft), "--out-dir", str(receipts), "--json"],
    )
    issue_data: dict[str, Any] = {}
    if issue.returncode == 0:
        try:
            issue_data = json.loads(issue.stdout)
        except Exception:
            issue_data = {}
    receipt_files = sorted(receipts.glob("*.receipt.json")) if receipts.exists() else []
    replay = None
    if issue.returncode == 0 and len(receipt_files) == 1:
        replay = _installed_cli(
            site,
            runtime,
            ["receipt", "replay", str(receipt_files[0]), "--draft", str(draft), "--json"],
        )
    replay_data: dict[str, Any] = {}
    if replay is not None and replay.returncode == 0:
        try:
            replay_data = json.loads(replay.stdout)
        except Exception:
            replay_data = {}
    snapshot_sidecar_value = issue_data.get("registry_snapshot_path")
    snapshot_sidecar = Path(snapshot_sidecar_value) if isinstance(snapshot_sidecar_value, str) else None
    checks.append(
        _check(
            "installed_wheel_receipt_exact_replay",
            issue.returncode == 0
            and issue_data.get("receipt_version") == TRUST_RECEIPT_CONTRACT
            and isinstance(issue_data.get("registry_snapshot_id"), str)
            and isinstance(issue_data.get("registry_snapshot_artifact_sha256"), str)
            and snapshot_sidecar is not None
            and snapshot_sidecar.is_file()
            and len(receipt_files) == 1
            and replay is not None
            and replay.returncode == 0
            and replay_data.get("version") == TRUST_RECEIPT_REPLAY_REPORT_CONTRACT
            and replay_data.get("overall_status") == "passed"
            and replay_data.get("replay_mode") == "exact_snapshot_replay"
            and replay_data.get("historical_receipt_unchanged") is True,
            issue_exit_code=issue.returncode,
            issue_receipt_version=issue_data.get("receipt_version"),
            registry_snapshot_path=snapshot_sidecar_value,
            registry_snapshot_id=issue_data.get("registry_snapshot_id"),
            receipt_count=len(receipt_files),
            replay_exit_code=None if replay is None else replay.returncode,
            replay_status=replay_data.get("overall_status"),
            replay_mode=replay_data.get("replay_mode"),
            replay_version=replay_data.get("version"),
            historical_receipt_unchanged=replay_data.get("historical_receipt_unchanged"),
            issue_stderr_tail=issue.stderr[-1000:],
            replay_stderr_tail="" if replay is None else replay.stderr[-1000:],
        )
    )

    p4_current_snapshot = runtime / "registry-current.json"
    p4_diff = runtime / "registry-diff.json"
    p4_migration = runtime / "registry-migration.json"
    p4_snapshot_result = None
    p4_diff_result = None
    p4_current_replay = None
    p4_migration_create = None
    p4_migrated_blocked = None
    p4_migrated_accepted = None
    p4_snapshot_data: dict[str, Any] = {}
    p4_diff_data: dict[str, Any] = {}
    p4_current_data: dict[str, Any] = {}
    p4_migration_data: dict[str, Any] = {}
    p4_blocked_data: dict[str, Any] = {}
    p4_accepted_data: dict[str, Any] = {}
    receipt_before = receipt_files[0].read_bytes() if len(receipt_files) == 1 else None
    if snapshot_sidecar is not None and snapshot_sidecar.is_file() and len(receipt_files) == 1:
        p4_snapshot_result = _installed_cli(
            site,
            runtime,
            ["registry", "snapshot", "--evolution", "--out", str(p4_current_snapshot), "--json"],
        )
        if p4_snapshot_result.returncode == 0:
            try:
                p4_snapshot_data = json.loads(p4_snapshot_result.stdout)
            except Exception:
                p4_snapshot_data = {}
        p4_diff_result = _installed_cli(
            site,
            runtime,
            ["registry", "diff", str(snapshot_sidecar), str(p4_current_snapshot), "--out", str(p4_diff), "--json"],
        )
        if p4_diff_result.returncode == 0:
            try:
                p4_diff_data = json.loads(p4_diff_result.stdout)
            except Exception:
                p4_diff_data = {}
        p4_current_replay = _installed_cli(
            site,
            runtime,
            [
                "receipt", "replay", str(receipt_files[0]), "--draft", str(draft),
                "--mode", "current_registry_replay", "--source-snapshot", str(snapshot_sidecar), "--json",
            ],
        )
        if p4_current_replay.returncode == 0:
            try:
                p4_current_data = json.loads(p4_current_replay.stdout)
            except Exception:
                p4_current_data = {}
        p4_migration_create = _installed_cli(
            site,
            runtime,
            [
                "registry", "migration", "create", str(snapshot_sidecar), str(p4_current_snapshot),
                "--authorized-by", "distribution-contract-check", "--reason", "identity migration replay",
                "--approve", "--out", str(p4_migration), "--json",
            ],
        )
        if p4_migration_create.returncode == 0:
            try:
                p4_migration_data = json.loads(p4_migration_create.stdout)
            except Exception:
                p4_migration_data = {}
        common_migrated = [
            "receipt", "replay", str(receipt_files[0]), "--draft", str(draft),
            "--mode", "migrated_registry_replay", "--source-snapshot", str(snapshot_sidecar),
            "--target-snapshot", str(p4_current_snapshot), "--migration-record", str(p4_migration),
        ]
        p4_migrated_blocked = _installed_cli(site, runtime, [*common_migrated, "--json"])
        try:
            p4_blocked_data = json.loads(p4_migrated_blocked.stdout)
        except Exception:
            p4_blocked_data = {}
        p4_migrated_accepted = _installed_cli(
            site,
            runtime,
            [*common_migrated, "--accept-unsigned-local-approval", "--json"],
        )
        if p4_migrated_accepted.returncode == 0:
            try:
                p4_accepted_data = json.loads(p4_migrated_accepted.stdout)
            except Exception:
                p4_accepted_data = {}
    receipt_after = receipt_files[0].read_bytes() if len(receipt_files) == 1 else None
    checks.append(
        _check(
            "installed_wheel_registry_evolution_and_replay_modes",
            p4_snapshot_result is not None
            and p4_snapshot_result.returncode == 0
            and p4_snapshot_data.get("version") == REGISTRY_SNAPSHOT_CONTRACT
            and p4_diff_result is not None
            and p4_diff_result.returncode == 0
            and p4_diff_data.get("version") == REGISTRY_DIFF_CONTRACT
            and p4_diff_data.get("overall_classification") == "compatible"
            and p4_current_replay is not None
            and p4_current_replay.returncode == 0
            and p4_current_data.get("overall_status") == "passed"
            and p4_current_data.get("replay_mode") == "current_registry_replay"
            and p4_current_data.get("historical_receipt_unchanged") is True
            and p4_migration_create is not None
            and p4_migration_create.returncode == 0
            and p4_migration_data.get("version") == REGISTRY_MIGRATION_RECORD_CONTRACT
            and (p4_migration_data.get("authorization") or {}).get("status") == "approved"
            and p4_migration_data.get("cryptographic_signature_status") == "not_implemented"
            and p4_migrated_blocked is not None
            and p4_migrated_blocked.returncode == 2
            and p4_blocked_data.get("overall_status") == "failed"
            and p4_blocked_data.get("replay_mode") == "migrated_registry_replay"
            and (p4_blocked_data.get("migration") or {}).get("unsigned_local_approval_accepted") is False
            and p4_migrated_accepted is not None
            and p4_migrated_accepted.returncode == 0
            and p4_accepted_data.get("overall_status") == "passed"
            and p4_accepted_data.get("replay_mode") == "migrated_registry_replay"
            and p4_accepted_data.get("historical_receipt_unchanged") is True
            and (p4_accepted_data.get("migration") or {}).get("unsigned_local_approval_accepted") is True
            and receipt_before is not None
            and receipt_before == receipt_after,
            snapshot_exit_code=None if p4_snapshot_result is None else p4_snapshot_result.returncode,
            snapshot_version=p4_snapshot_data.get("version"),
            diff_exit_code=None if p4_diff_result is None else p4_diff_result.returncode,
            diff_classification=p4_diff_data.get("overall_classification"),
            current_replay_exit_code=None if p4_current_replay is None else p4_current_replay.returncode,
            current_replay_status=p4_current_data.get("overall_status"),
            migration_create_exit_code=None if p4_migration_create is None else p4_migration_create.returncode,
            migration_authorization=(p4_migration_data.get("authorization") or {}).get("status"),
            unsigned_blocked_exit_code=None if p4_migrated_blocked is None else p4_migrated_blocked.returncode,
            unsigned_blocked_status=p4_blocked_data.get("overall_status"),
            unsigned_accepted_exit_code=None if p4_migrated_accepted is None else p4_migrated_accepted.returncode,
            unsigned_accepted_status=p4_accepted_data.get("overall_status"),
            historical_receipt_unchanged=receipt_before is not None and receipt_before == receipt_after,
            snapshot_stderr_tail="" if p4_snapshot_result is None else p4_snapshot_result.stderr[-1000:],
            diff_stderr_tail="" if p4_diff_result is None else p4_diff_result.stderr[-1000:],
            current_stderr_tail="" if p4_current_replay is None else p4_current_replay.stderr[-1000:],
            migration_stderr_tail="" if p4_migration_create is None else p4_migration_create.stderr[-1000:],
            blocked_stderr_tail="" if p4_migrated_blocked is None else p4_migrated_blocked.stderr[-1000:],
            accepted_stderr_tail="" if p4_migrated_accepted is None else p4_migrated_accepted.stderr[-1000:],
        )
    )


    evidence_out = runtime / "offline-evidence-providers"
    evidence_probe = _installed_offline_evidence_probe(
        site,
        runtime,
        draft=draft,
        out_dir=evidence_out,
    )
    evidence_probe_data: dict[str, Any] = {}
    if evidence_probe.returncode == 0:
        try:
            evidence_probe_data = json.loads(evidence_probe.stdout.strip().splitlines()[-1])
        except Exception:
            evidence_probe_data = {}

    fixture_bundle_path = evidence_out / "fixture_bundle.json"
    fixture_policy_path = evidence_out / "fixture_policy.json"
    fixture_bundle_data: dict[str, Any] = {}
    fixture_policy_data: dict[str, Any] = {}
    try:
        fixture_bundle_data = json.loads(fixture_bundle_path.read_text(encoding="utf-8"))
        fixture_policy_data = json.loads(fixture_policy_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    evidence_bundle_cli = _installed_cli(
        site, runtime, ["evidence", "bundle", str(fixture_bundle_path), "--json"]
    )
    evidence_policy_cli = _installed_cli(
        site, runtime, ["evidence", "policy", str(fixture_policy_path), "--json"]
    )
    evidence_resolve_out = runtime / "evidence-resolve-cli"
    evidence_resolve_cli = _installed_cli(
        site,
        runtime,
        [
            "evidence", "resolve", str(fixture_bundle_path), str(fixture_policy_path), str(draft),
            "--claim-id", "claim.create_user_uses_outbox",
            "--evidence-id", "evidence.ainir.fixture.safe-outbox",
            "--expected-kind", "verifier_report",
            "--evaluation-time", "2026-08-10T00:00:00Z",
            "--out-dir", str(evidence_resolve_out),
            "--json",
        ],
    )
    evidence_bundle_cli_data: dict[str, Any] = {}
    evidence_policy_cli_data: dict[str, Any] = {}
    evidence_resolve_cli_data: dict[str, Any] = {}
    for proc, target in (
        (evidence_bundle_cli, evidence_bundle_cli_data),
        (evidence_policy_cli, evidence_policy_cli_data),
        (evidence_resolve_cli, evidence_resolve_cli_data),
    ):
        if proc.returncode == 0:
            try:
                target.update(json.loads(proc.stdout))
            except Exception:
                pass
    checks.append(
        _check(
            "installed_wheel_offline_evidence_providers",
            evidence_probe.returncode == 0
            and evidence_probe_data.get("overall_status") == "passed"
            and evidence_probe_data.get("checks_total") == 9
            and evidence_probe_data.get("checks_passed") == 9
            and evidence_probe_data.get("network_access_used") is False
            and evidence_probe_data.get("trust_gate_promotion_enabled") is False
            and fixture_bundle_data.get("version") == EVIDENCE_BUNDLE_CONTRACT
            and fixture_policy_data.get("version") == EVIDENCE_PROVIDER_POLICY_CONTRACT
            and evidence_bundle_cli.returncode == 0
            and evidence_bundle_cli_data.get("overall_status") == "passed"
            and evidence_policy_cli.returncode == 0
            and evidence_policy_cli_data.get("overall_status") == "passed"
            and evidence_resolve_cli.returncode == 0
            and evidence_resolve_cli_data.get("version") == EVIDENCE_VALIDATION_REPORT_CONTRACT
            and evidence_resolve_cli_data.get("accepted") is True
            and evidence_resolve_cli_data.get("candidate_evidence_status") == "validated_candidate"
            and evidence_resolve_cli_data.get("trust_gate_promotion_allowed") is False
            and evidence_resolve_cli_data.get("production_runtime_ready") is False,
            readiness_exit_code=evidence_probe.returncode,
            readiness_status=evidence_probe_data.get("overall_status"),
            readiness_checks=f"{evidence_probe_data.get('checks_passed')}/{evidence_probe_data.get('checks_total')}",
            bundle_cli_exit_code=evidence_bundle_cli.returncode,
            policy_cli_exit_code=evidence_policy_cli.returncode,
            resolve_cli_exit_code=evidence_resolve_cli.returncode,
            candidate_status=evidence_resolve_cli_data.get("candidate_evidence_status"),
            trust_gate_promotion_allowed=evidence_resolve_cli_data.get("trust_gate_promotion_allowed"),
            readiness_stderr_tail=evidence_probe.stderr[-1000:],
            bundle_stderr_tail=evidence_bundle_cli.stderr[-1000:],
            policy_stderr_tail=evidence_policy_cli.stderr[-1000:],
            resolve_stderr_tail=evidence_resolve_cli.stderr[-1000:],
        )
    )

    mcp_out = runtime / "mcp-tool-call-profile"
    mcp_probe = _installed_mcp_tool_call_probe(site, runtime, out_dir=mcp_out)
    mcp_probe_data: dict[str, Any] = {}
    if mcp_probe.returncode == 0:
        try:
            mcp_probe_data = json.loads(mcp_probe.stdout.strip().splitlines()[-1])
        except Exception:
            mcp_probe_data = {}
    checks.append(
        _check(
            "installed_wheel_mcp_tool_call_profile",
            mcp_probe.returncode == 0
            and mcp_probe_data.get("overall_status") == "passed"
            and mcp_probe_data.get("checks_total") == 10
            and mcp_probe_data.get("checks_passed") == 10
            and mcp_probe_data.get("case_count") == 26
            and mcp_probe_data.get("execution_performed") is False
            and mcp_probe_data.get("network_access_used") is False
            and mcp_probe_data.get("trust_gate_override_enabled") is False
            and mcp_probe_data.get("evidence_ledger_promotion_enabled") is False
            and mcp_probe_data.get("production_runtime_ready") is False,
            readiness_exit_code=mcp_probe.returncode,
            readiness_status=mcp_probe_data.get("overall_status"),
            readiness_checks=f"{mcp_probe_data.get('checks_passed')}/{mcp_probe_data.get('checks_total')}",
            conformance_cases=mcp_probe_data.get("case_count"),
            execution_performed=mcp_probe_data.get("execution_performed"),
            network_access_used=mcp_probe_data.get("network_access_used"),
            trust_gate_override_enabled=mcp_probe_data.get("trust_gate_override_enabled"),
            evidence_ledger_promotion_enabled=mcp_probe_data.get("evidence_ledger_promotion_enabled"),
            readiness_stderr_tail=mcp_probe.stderr[-1000:],
        )
    )

    openai_out = runtime / "openai-function-tool-adapter"
    openai_probe = _installed_openai_function_tool_probe(site, runtime, out_dir=openai_out)
    openai_probe_data: dict[str, Any] = {}
    if openai_probe.returncode == 0:
        try:
            openai_probe_data = json.loads(openai_probe.stdout.strip().splitlines()[-1])
        except Exception:
            openai_probe_data = {}
    checks.append(
        _check(
            "installed_wheel_openai_function_tool_adapter",
            openai_probe.returncode == 0
            and openai_probe_data.get("overall_status") == "passed"
            and openai_probe_data.get("checks_total") == 10
            and openai_probe_data.get("checks_passed") == 10
            and openai_probe_data.get("external_profile_case_count") == 4
            and openai_probe_data.get("openai_api_called") is False
            and openai_probe_data.get("tool_output_submitted") is False
            and openai_probe_data.get("execution_performed") is False
            and openai_probe_data.get("network_access_used") is False
            and openai_probe_data.get("mcp_transport_opened") is False
            and openai_probe_data.get("trust_gate_override_enabled") is False
            and openai_probe_data.get("evidence_ledger_promotion_enabled") is False
            and openai_probe_data.get("production_runtime_ready") is False,
            readiness_exit_code=openai_probe.returncode,
            readiness_status=openai_probe_data.get("overall_status"),
            readiness_checks=f"{openai_probe_data.get('checks_passed')}/{openai_probe_data.get('checks_total')}",
            external_profile_cases=openai_probe_data.get("external_profile_case_count"),
            openai_api_called=openai_probe_data.get("openai_api_called"),
            tool_output_submitted=openai_probe_data.get("tool_output_submitted"),
            execution_performed=openai_probe_data.get("execution_performed"),
            readiness_stderr_tail=openai_probe.stderr[-1000:],
        )
    )

    profile_probe_out = runtime / "profile-sdk-smoke"
    profile_probe = _installed_profile_sdk_probe(site, runtime, out_dir=profile_probe_out)
    profile_probe_data: dict[str, Any] = {}
    if profile_probe.returncode == 0:
        try:
            profile_probe_data = json.loads(profile_probe.stdout.strip().splitlines()[-1])
        except Exception:
            profile_probe_data = {}
    bundled_validation = profile_probe_data.get("bundled_validation") or {}
    generated_validation = profile_probe_data.get("generated_validation") or {}
    profile_run_data = profile_probe_data.get("conformance") or {}
    checks.append(
        _check(
            "installed_wheel_profile_sdk_and_conformance",
            profile_probe.returncode == 0
            and bundled_validation.get("valid") is True
            and generated_validation.get("valid") is True
            and profile_run_data.get("overall_status") == "passed"
            and profile_run_data.get("case_count") == 4
            and profile_run_data.get("passed") == 4,
            probe_exit_code=profile_probe.returncode,
            bundled_profile_valid=bundled_validation.get("valid"),
            generated_profile_valid=generated_validation.get("valid"),
            conformance_status=profile_run_data.get("overall_status"),
            case_count=profile_run_data.get("case_count"),
            conformance_passed_cases=profile_run_data.get("passed"),
            probe_stderr_tail=profile_probe.stderr[-1000:],
        )
    )

    failed = [check for check in checks if check["status"] != "passed"]
    return {
        "kind": "AiNIRDistributionContractReport",
        "version": "1",
        "overall_status": "passed" if not failed else "failed",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "wheel": wheel.name,
        "sdist": sdist.name,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify AiNIR wheel/sdist contracts")
    parser.add_argument("--work-dir", default=None, help="scratch directory; replaced if it already exists")
    parser.add_argument("--output", default=None, help="optional JSON report path")
    args = parser.parse_args(argv)

    try:
        if args.work_dir:
            work_dir = Path(args.work_dir).expanduser().resolve()
            report = run_distribution_contract_check(work_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="ainir_distribution_contract_") as tmp:
                report = run_distribution_contract_check(Path(tmp) / "work")
    except ValueError as exc:
        print(f"distribution contract check refused: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("overall_status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
