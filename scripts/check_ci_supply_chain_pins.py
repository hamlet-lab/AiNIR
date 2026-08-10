#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'
EXPECTED_ACTIONS = {
    'actions/checkout': '93cb6efe18208431cddfb8368fd83d5badbf9bfd',
    'actions/setup-python': 'a309ff8b426b58ec0e2a45f0f869d46889d02405',
    'actions/setup-node': 'a0853c24544627f65ddf259abe73b1d18a591444',
}


def main() -> int:
    text = WORKFLOW.read_text(encoding='utf-8')
    failures: list[str] = []
    for action, sha in EXPECTED_ACTIONS.items():
        pattern = rf"uses:\s*{re.escape(action)}@([0-9a-f]{{40}})"
        match = re.search(pattern, text)
        if not match:
            failures.append(f'{action} is not pinned to a full 40-character commit SHA')
        elif match.group(1) != sha:
            failures.append(f'{action} pinned SHA mismatch: {match.group(1)} != {sha}')
    if re.search(r"uses:\s*[^\s#]+@v\d+", text):
        failures.append('workflow still contains a mutable version-tag action reference')
    if 'requirements.lock.txt' not in text:
        failures.append('workflow does not use requirements.lock.txt')
    if 'npm ci' not in text:
        failures.append('workflow does not install Node dependencies from package-lock with npm ci')
    if 'npm install -g' in text:
        failures.append('workflow still performs global npm install')
    full_pytest = 'python -m pytest -q -p no:cacheprovider'
    quick_gate = 'python scripts/run_phase30_v1_rc_candidate_check.py --mode quick-integrity'
    if full_pytest not in text:
        failures.append('workflow does not run the full Python test suite')
    if quick_gate in text and full_pytest in text and text.index(full_pytest) > text.index(quick_gate):
        failures.append('workflow runs quick-integrity before the full Python test suite')
    if failures:
        for failure in failures:
            print(f'FAILED: {failure}')
        return 2
    print('CI supply-chain pins: passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
