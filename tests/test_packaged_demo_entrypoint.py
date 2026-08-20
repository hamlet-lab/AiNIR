from __future__ import annotations

import json
from pathlib import Path

from ainir.entrypoint import main


def test_demo_falls_back_to_packaged_fixtures_outside_checkout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "demo-results"

    assert main(["demo", "--out-dir", str(out_dir)]) == 0

    summary_path = out_dir / "summary.yaml"
    assert summary_path.exists()
    text = summary_path.read_text(encoding="utf-8")
    assert "overall_status: passed" in text
    assert "account_deletion_hard_delete_blocked" in text
    assert "create_user_outbox_safe" in text


def test_explicit_missing_examples_dir_does_not_silently_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-examples"
    out_dir = tmp_path / "missing-results"

    assert main([
        "demo",
        "--examples-dir",
        str(missing),
        "--out-dir",
        str(out_dir),
    ]) == 2

    summary = (out_dir / "summary.yaml").read_text(encoding="utf-8")
    assert "No example draft files were found" in summary
