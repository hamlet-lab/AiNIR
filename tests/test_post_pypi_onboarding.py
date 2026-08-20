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


def test_integration_quickstart_runs_without_execution() -> None:
    namespace = runpy.run_path(str(ROOT / "examples" / "integration_quickstart.py"))

    assert namespace["main"]() == 0
