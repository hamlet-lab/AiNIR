from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_public_governance_and_security_files_exist():
    required = [
        "AGENTS.md",
        "PUBLIC_SCOPE.md",
        "PROTECTED_INVARIANTS.md",
        "SECURITY.md",
        "SUPPORT.md",
        "MAINTAINERS.md",
        "CHANGELOG.md",
        ".github/CODEOWNERS",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/conformance-case.yml",
        ".github/ISSUE_TEMPLATE/profile-proposal.yml",
        "docs/development/baseline-2026-08-09.md",
        "docs/development/p1-release-contracts-2026-08-10.md",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    assert missing == []


def test_protected_invariants_cover_core_fail_closed_boundaries():
    text = (ROOT / "PROTECTED_INVARIANTS.md").read_text(encoding="utf-8")
    required_phrases = [
        "Model output is a claim",
        "Self-attestation cannot promote",
        "Unknown workflows",
        "TrustReceipt replay is deterministic",
        "does not execute downstream actions",
        "never weakened solely to make a fixture",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert missing == []


def test_issue_form_yaml_is_parseable_and_has_required_identity_fields():
    for path in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), path
        assert isinstance(data.get("name"), str) and data["name"], path
        assert isinstance(data.get("description"), str) and data["description"], path
        assert isinstance(data.get("title"), str), path
        assert isinstance(data.get("body"), list) and data["body"], path
