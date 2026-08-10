from __future__ import annotations

import argparse
import json
from pathlib import Path

from ainir.openai_function_tool_eval import run_openai_function_tool_adapter_check
from ainir.temp_paths import ainir_temp_str


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate P7 external MCP authoring and OpenAI function-tool preflight")
    parser.add_argument("--out-dir", default=ainir_temp_str("ainir_openai_function_tool_adapter"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_openai_function_tool_adapter_check(Path(args.out_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"AiNIR OpenAI function-tool adapter: {report['overall_status']}")
        print(f"checks: {report['checks_passed']}/{report['checks_total']}")
        print(f"external profile cases: {report['external_profile_case_count']}")
        print("openai_api_called: false")
        print("tool_output_submitted: false")
        print("execution_performed: false")
        print(f"reports: {report['output_dir']}")
    return 0 if report["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
