from __future__ import annotations

import argparse
import json
from pathlib import Path

from ainir.offline_evidence_provider_eval import run_offline_evidence_provider_check
from ainir.temp_paths import ainir_temp_str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic offline EvidenceProvider readiness checks"
    )
    parser.add_argument(
        "--out-dir",
        default=ainir_temp_str("ainir_offline_evidence_provider_check"),
    )
    parser.add_argument("--draft", default=None, help="optional safe draft path for installed-wheel checks")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_offline_evidence_provider_check(Path(args.out_dir), draft_path=args.draft)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"AiNIR offline EvidenceProvider check: {report['overall_status']}")
        print(f"checks: {report['checks_passed']}/{report['checks_total']}")
        print(f"reports: {report['output_dir']}")
    return 0 if report["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
