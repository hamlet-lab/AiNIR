from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import ainir
from ainir import __release_tag__, __version__
from ainir.resources import (
    PUBLIC_REGISTRY_NAMES,
    PUBLIC_SCHEMA_NAMES,
    UnknownPublicResourceError,
    public_resource_manifest,
    read_registry_bytes,
    read_schema_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def test_python_release_identity_has_one_source_and_matches_manifest():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject
    assert 'version = {attr = "ainir._version.__version__"}' in pyproject
    assert 'version = "0.1.0"' not in pyproject
    assert 'license = "Apache-2.0"' in pyproject
    assert 'license-files = ["LICENSE", "NOTICE", "AUTHORS.md"]' in pyproject
    assert 'requires = ["setuptools>=77"]' in pyproject

    manifest = yaml.safe_load(
        (ROOT / "release" / "v1_0_rc_candidate_manifest.yaml").read_text(encoding="utf-8")
    )
    assert __version__ == "1.0.0rc2"
    assert ainir.__version__ == __version__
    assert manifest["python_distribution_name"] == "ainir-public-demo"
    assert manifest["python_distribution_version"] == __version__
    assert manifest["release_tag"] == __release_tag__ == "v1.0.0-rc.2"
    assert manifest["status"] == "rc_candidate_2"
    assert manifest["not_v1_final"] is True
    assert manifest["production_runtime_ready"] is False
    assert "Public Resource API" in manifest["frozen_public_surfaces"]
    assert "Packaged Public Schemas" in manifest["frozen_public_surfaces"]


def test_node_metadata_is_explicitly_private_compile_fixture():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["name"] == "ainir-typescript-compile-fixture"
    assert package["version"] == "0.0.0-private"
    assert "does not define the AiNIR Python release" in package["description"]
    assert lock["name"] == package["name"]
    assert lock["version"] == package["version"]
    assert lock["packages"][""]["name"] == package["name"]
    assert lock["packages"][""]["version"] == package["version"]


def test_public_schema_and_registry_copies_match_repository_contract_sources():
    assert tuple(sorted(PUBLIC_SCHEMA_NAMES)) == PUBLIC_SCHEMA_NAMES
    assert tuple(sorted(PUBLIC_REGISTRY_NAMES)) == PUBLIC_REGISTRY_NAMES
    assert {path.name for path in (ROOT / "schemas").iterdir() if path.is_file()} == set(PUBLIC_SCHEMA_NAMES)
    assert {path.name for path in (ROOT / "registries").iterdir() if path.is_file()} == set(PUBLIC_REGISTRY_NAMES)

    for name in PUBLIC_SCHEMA_NAMES:
        root_bytes = (ROOT / "schemas" / name).read_bytes()
        packaged_bytes = (ROOT / "src" / "ainir" / "schemas" / name).read_bytes()
        assert packaged_bytes == root_bytes
        assert read_schema_bytes(name) == root_bytes

    for name in PUBLIC_REGISTRY_NAMES:
        root_bytes = (ROOT / "registries" / name).read_bytes()
        packaged_bytes = (ROOT / "src" / "ainir" / "registries" / name).read_bytes()
        assert packaged_bytes == root_bytes
        assert read_registry_bytes(name) == root_bytes


def test_public_resource_api_is_allowlisted_and_deterministic():
    first = public_resource_manifest()
    second = public_resource_manifest()
    assert first == second
    assert first["kind"] == "AiNIRPublicResourceManifest"
    assert first["version"] == "1"
    assert str(first["combined_sha256"]).startswith("sha256:")
    assert set(first["schemas"]) == set(PUBLIC_SCHEMA_NAMES)
    assert set(first["registries"]) == set(PUBLIC_REGISTRY_NAMES)

    with pytest.raises(UnknownPublicResourceError):
        read_schema_bytes("../registries/safety_registry.yaml")
    with pytest.raises(UnknownPublicResourceError):
        read_registry_bytes("unpublished_registry.yaml")


@pytest.mark.distribution
def test_built_wheel_and_sdist_preserve_public_distribution_contracts(tmp_path: Path):
    report_path = tmp_path / "distribution-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_distribution_contracts.py"),
            "--work-dir",
            str(tmp_path / "work"),
            "--output",
            str(report_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    failed = [check for check in report.get("checks", []) if check.get("status") != "passed"]
    assert result.returncode == 0, result.stdout + result.stderr
    assert report.get("overall_status") == "passed", failed
    assert report.get("wheel") == "ainir_public_demo-1.0.0rc2-py3-none-any.whl"
    assert report.get("sdist") == "ainir_public_demo-1.0.0rc2.tar.gz"


def test_distribution_checker_refuses_to_delete_unmarked_existing_directory(tmp_path: Path):
    protected = tmp_path / "protected"
    protected.mkdir()
    sentinel = protected / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_distribution_contracts.py"),
            "--work-dir",
            str(protected),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert "refusing to remove unmarked work directory" in result.stderr
