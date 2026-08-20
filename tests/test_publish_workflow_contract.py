from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def test_publish_workflow_is_manual_and_guarded() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "- build-only" in text
    assert "- testpypi" in text
    assert "- pypi" in text

    # Publishing must not happen merely because code, tags, or releases changed.
    assert "\n  push:" not in text
    assert "\n  release:" not in text
    assert "\n  schedule:" not in text

    # Long-lived PyPI credentials must not be stored or consumed by the workflow.
    assert "secrets." not in text
    assert "password:" not in text
    assert "api-token" not in text.lower()

    # Production publication is additionally gated by the GitHub environment.
    assert "name: pypi" in text
    assert "id-token: write" in text
    assert "inputs.target == 'pypi'" in text


def test_publish_workflow_pins_external_actions() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    expected = (
        "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
        "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
    )
    for action in expected:
        assert action in text

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            ref = stripped.split("@", 1)[1]
            assert len(ref) == 40
            int(ref, 16)


def test_publish_workflow_verifies_installed_demo_before_publish() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/check_distribution_contracts.py" in text
    assert "python -m build --sdist --wheel --outdir dist" in text
    assert "metadata['Name'] == 'ainir-public-demo'" in text
    assert "-m ainir demo" in text
    assert "/bin/ainir\" demo" in text
    assert "needs: build" in text
