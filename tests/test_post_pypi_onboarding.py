from __future__ import annotations

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]


def test_first_run_onboarding_uses_pypi_and_links_integration_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    start = (ROOT / "START_HERE.md").read_text(encoding="utf-8")

    readme_quickstart = readme.split("## Quick start", 1)[1].split("## Integrate in 5 minutes", 1)[0]
    start_install = start.split("## 1. Install from PyPI", 1)[1].split("## 2.", 1)[0]

    assert "python -m pip install ainir" in readme_quickstart
    assert "python -m pip install ainir" in start_install
    assert "git+https://github.com/hamlet-lab/ainir.git" not in readme_quickstart
    assert "git+https://github.com/hamlet-lab/ainir.git" not in start_install
    assert "docs/integration_quickstart.md" in readme
    assert "docs/integration_quickstart.md" in start


def test_current_status_docs_do_not_revert_to_prepublication_state() -> None:
    rc_candidate = (ROOT / "docs" / "v1_rc_candidate.md").read_text(encoding="utf-8")
    pre_v1 = (ROOT / "docs" / "pre_v1_status.md").read_text(encoding="utf-8")
    maintenance = (ROOT / "docs" / "github_launch_checklist.md").read_text(encoding="utf-8")

    assert "public_repository: live" in rc_candidate
    assert "public_release_state: published_rc" in rc_candidate
    assert "pending_private_github_trial" not in rc_candidate

    assert "public_release_type: published bounded demo" in pre_v1
    assert "suitable for private GitHub trial" not in pre_v1

    assert "Current-state note" in maintenance
    assert "Only upload to a private GitHub repository" not in maintenance


def test_docs_indexes_are_identical_and_surface_current_paths() -> None:
    docs_readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert docs_readme == docs_index
    assert "integration_quickstart.md" in docs_readme
    assert "PYPI_PUBLISHING.md" in docs_readme
    assert "archive/README.md" in docs_readme
    assert "public_launch_candidate.md" not in docs_readme


def test_historical_prose_is_grouped_under_docs_archive() -> None:
    docs = ROOT / "docs"
    archive = docs / "archive"

    assert (archive / "README.md").is_file()
    assert (archive / "development" / "README.md").is_file()
    assert (archive / "phases" / "phase13_release_candidate_reassessment.md").is_file()
    assert (archive / "phases" / "phase26_private_github_trial.md").is_file()
    assert (archive / "release-history" / "public_launch_candidate.md").is_file()
    assert (archive / "release-history" / "v1_rc_candidate_patch7.md").is_file()

    assert not (docs / "development").exists()
    assert not list(docs.glob("phase*.md"))
    assert not list(docs.glob("v1_rc_candidate_patch*.md"))
    assert not (docs / "public_launch_candidate.md").exists()


def test_integration_quickstart_runs_without_execution() -> None:
    namespace = runpy.run_path(str(ROOT / "examples" / "integration_quickstart.py"))

    assert namespace["main"]() == 0
