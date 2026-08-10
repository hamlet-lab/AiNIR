from __future__ import annotations

import argparse
import json
from pathlib import Path

from ainir.mcp_tool_call_eval import run_mcp_tool_call_profile_check
from ainir.temp_paths import ainir_temp_str


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the bounded AiNIR MCP tool-call profile")
    parser.add_argument("--out-dir", default=ainir_temp_str("ainir_mcp_tool_call_profile"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_mcp_tool_call_profile_check(Path(args.out_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"AiNIR MCP tool-call profile: {report['overall_status']}")
        print(f"checks: {report['checks_passed']}/{report['checks_total']}")
        print(f"conformance cases: {report['case_count']}")
        print("execution_performed: false")
        print(f"reports: {report['output_dir']}")
    return 0 if report["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
