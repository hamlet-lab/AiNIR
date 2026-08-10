from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_supply_chain_pins_are_enforced():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'check_ci_supply_chain_pins.py')],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_lockfiles_present_and_type_script_pinned():
    assert (ROOT / 'requirements.lock.txt').exists()
    assert 'PyYAML==6.0.3' in (ROOT / 'requirements.lock.txt').read_text(encoding='utf-8')
    assert 'pytest==9.0.2' in (ROOT / 'requirements.lock.txt').read_text(encoding='utf-8')
    assert 'setuptools==82.0.1' in (ROOT / 'requirements.lock.txt').read_text(encoding='utf-8')
    assert 'wheel==0.46.3' in (ROOT / 'requirements.lock.txt').read_text(encoding='utf-8')
    package_lock = (ROOT / 'package-lock.json').read_text(encoding='utf-8')
    assert 'typescript-5.8.3.tgz' in package_lock
    assert 'sha512-p1diW6TqL9L07nNxvRMM7hMMw4c5XOo/1ibL4aAIGmSAt9slTE1Xgw5KWuof2uTOvCg9BY7ZRi+GaF+7sfgPeQ==' in package_lock


def test_ci_runs_full_pytest_before_quick_integrity_gate():
    workflow = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    full_pytest = 'python -m pytest -q -p no:cacheprovider'
    quick_gate = 'python scripts/run_phase30_v1_rc_candidate_check.py --mode quick-integrity'
    assert full_pytest in workflow
    assert quick_gate in workflow
    assert workflow.index(full_pytest) < workflow.index(quick_gate)


def test_ci_declares_python_compatibility_and_cross_platform_distribution_smoke():
    workflow = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    for version in ('3.10', '3.11', '3.12', '3.13'):
        assert version in workflow
    assert 'windows-latest' in workflow
    assert 'macos-latest' in workflow
    assert 'python scripts/check_distribution_contracts.py' in workflow
    assert '-m "not distribution"' in workflow
