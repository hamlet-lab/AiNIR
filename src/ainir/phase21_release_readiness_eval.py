from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .core import load_draft
from .execution_context import TrustedExecutionContext
from .golden_trace_harness import run_golden_traces
from .lowering import lower_to_typescript
from .negative_conformance_harness import run_negative_conformance_corpus
from .phase18_trust_gate_eval import run_phase18_trust_gate_eval
from .phase19_trust_receipt_eval import run_phase19_trust_receipt_eval
from .phase20_receipt_conformance_eval import run_phase20_receipt_conformance_eval
from .phase24_verified_intent_semantic_eval import run_phase24_verified_intent_semantic_eval
from .phase25_verified_intent_contract_eval import run_phase25_verified_intent_contract_eval
from .trust_gate import evaluate_trust_gate
from .verifier import verify_draft

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReadinessStep:
    name: str
    status: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "details": dict(self.details)}


def _pass(name: str, **details: Any) -> ReadinessStep:
    return ReadinessStep(name, "passed", dict(details))


def _fail(name: str, **details: Any) -> ReadinessStep:
    return ReadinessStep(name, "failed", dict(details))


def _doc_scope_check() -> ReadinessStep:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    lower = readme.lower()
    findings: list[str] = []
    if "model output is a claim, not a fact" not in lower:
        findings.append("README missing core AiNIR claim/fact message")
    if "pre-v1" not in lower:
        findings.append("README missing pre-v1 status")
    for phrase in ["not a v1.0 final", "not a production runtime"]:
        if phrase not in lower:
            findings.append(f"README missing boundary phrase: {phrase}")
    if "production-ready" in lower or "production ready" in lower:
        findings.append("README appears to claim production readiness")
    return _fail("documentation_scope", findings=findings) if findings else _pass("documentation_scope")


def _public_boundary_check() -> ReadinessStep:
    findings: list[str] = []
    forbidden_suffixes = {".zip", ".pyc"}
    forbidden_dirs = {
        "__pycache__",
        ".pytest_cache",
        "demo_results",
        "prelaunch_results",
        "review_results",
        "negative_conformance_results",
        "golden_trace_results",
        "trust_receipts",
        "phase18_trust_gate_results",
        "phase19_trust_receipt_results",
        "phase20_receipt_conformance_results",
        "phase21_launch_readiness_results",
        "phase24_verified_intent_semantic_results",
        "out",
    }
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        # Ignore untracked/generated local output directories if a user ran a demo
        # before this check. Packaging still removes them before ZIP creation.
        if any(part in forbidden_dirs for part in rel.parts):
            continue
        if path.is_file() and path.suffix in forbidden_suffixes:
            findings.append(f"forbidden_file_suffix:{rel}")
        if path.is_file() and "private" in str(rel).lower() and path.suffix.lower() in {".zip", ".tar", ".gz"}:
            findings.append(f"private_archive_like_file:{rel}")
    required_files = [
        "README.md",
        "START_HERE.md",
        "docs/public_private_boundary.md",
        "docs/pre_v1_status.md",
        "docs/trust_gate.md",
        "docs/trust_receipt_persistence.md",
        "docs/archive/phases/phase20_trust_receipt_conformance.md",
    ]
    for item in required_files:
        if not (ROOT / item).exists():
            findings.append(f"missing_required_public_file:{item}")
    return _fail("public_private_boundary", findings=findings[:50]) if findings else _pass("public_private_boundary")


def _trust_gate_smoke(out_dir: Path) -> ReadinessStep:
    context = TrustedExecutionContext.public_demo()
    draft = load_draft(ROOT / "examples" / "create_user_outbox_safe" / "draft.yaml")
    decision = evaluate_trust_gate(draft, context).as_dict()
    (out_dir / "trust_gate_safe_create_user.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    checks = {
        "status": decision.get("status"),
        "lowering_allowed": decision.get("lowering_allowed"),
        "receipt_present": bool(decision.get("receipt", {}).get("receipt_id")),
    }
    if checks["status"] == "passed" and checks["lowering_allowed"] is True and checks["receipt_present"]:
        return _pass("trust_gate_smoke", **checks)
    return _fail("trust_gate_smoke", **checks)


def _blocked_lowering_smoke(out_dir: Path) -> ReadinessStep:
    context = TrustedExecutionContext.public_demo()
    draft = load_draft(ROOT / "examples" / "order_payment_real_payment_blocked" / "draft.yaml")
    report = verify_draft(draft, context)
    details: dict[str, Any] = {"verify_status": report.status}
    try:
        lower_to_typescript(draft, report, out_dir / "blocked_lowering", context)
        details["lowering_refused"] = False
        return _fail("blocked_lowering_refusal", **details)
    except RuntimeError as exc:
        details["lowering_refused"] = True
        details["reason"] = str(exc)[:300]
        return _pass("blocked_lowering_refusal", **details)


def _safe_lowering_smoke(out_dir: Path) -> ReadinessStep:
    context = TrustedExecutionContext.public_demo()
    draft = load_draft(ROOT / "examples" / "create_user_outbox_safe" / "draft.yaml")
    report = verify_draft(draft, context)
    details: dict[str, Any] = {"verify_status": report.status}
    if report.status != "passed":
        return _fail("safe_lowering", **details)
    target = lower_to_typescript(draft, report, out_dir / "safe_lowering", context)
    details["target"] = str(target)
    details["target_exists"] = Path(target).exists()
    return _pass("safe_lowering", **details) if details["target_exists"] else _fail("safe_lowering", **details)


def _run_eval_step(name: str, summary: dict[str, Any], status_key: str = "overall_status") -> ReadinessStep:
    status = summary.get(status_key)
    details = {k: summary.get(k) for k in ["overall_status", "case_count", "trace_count", "passed", "failed", "steps_passed", "steps_failed"] if k in summary}
    if status in {"passed", "passed_with_known_pending"}:
        return _pass(name, **details)
    return _fail(name, **details)


def run_phase21_launch_readiness_eval(out_dir: str | Path = "phase21_launch_readiness_results") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    steps: list[ReadinessStep] = []

    # Static gates first.
    steps.append(_doc_scope_check())
    steps.append(_public_boundary_check())

    # Focused AiNIR core gates.
    steps.append(_trust_gate_smoke(out))
    steps.append(_safe_lowering_smoke(out))
    steps.append(_blocked_lowering_smoke(out))

    # Conformance suites with TrustReceipt replay included.
    steps.append(_run_eval_step("phase18_trust_gate_eval", run_phase18_trust_gate_eval(out / "phase18_trust_gate")))
    steps.append(_run_eval_step("phase19_trust_receipt_replay_eval", run_phase19_trust_receipt_eval(out / "phase19_trust_receipt")))
    steps.append(_run_eval_step("phase20_receipt_conformance_eval", run_phase20_receipt_conformance_eval(out / "phase20_receipt_conformance")))
    steps.append(_run_eval_step("phase24_verified_intent_semantic_eval", run_phase24_verified_intent_semantic_eval(out / "phase24_verified_intent_semantic")))
    steps.append(_run_eval_step("phase25_verified_intent_contract_eval", run_phase25_verified_intent_contract_eval(out / "phase25_verified_intent_contract")))
    steps.append(_run_eval_step("negative_conformance_eval", run_negative_conformance_corpus(ROOT / "negative_conformance_corpus.yaml", out / "negative_conformance", "public_demo")))
    steps.append(_run_eval_step("golden_trace_replay", run_golden_traces(ROOT / "golden_traces.yaml", out / "golden_traces", "public_demo")))

    overall = "passed" if all(step.status == "passed" for step in steps) else "failed"
    decision = "ready_for_private_github_trial" if overall == "passed" else "hold_for_fix"
    report = {
        "report": "ainir.pre_v1.phase21.launch_readiness_with_trust_receipts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "decision": decision,
        "steps_total": len(steps),
        "steps_passed": sum(1 for s in steps if s.status == "passed"),
        "steps_failed": sum(1 for s in steps if s.status != "passed"),
        "human_external_evaluator_status": "pending",
        "production_runtime_ready": False,
        "v1_final_ready": False,
        "public_release_ready": False,
        "private_github_trial_ready": overall == "passed",
        "steps": [s.as_dict() for s in steps],
        "notes": [
            "This is a pre-v1 launch-readiness decision, not a final release proof.",
            "TrustReceipt replay conformance is now a release-readiness gate.",
            "VerifiedIntentPacket semantic grounding and strict contract validation are included in readiness.",
            "Public release still requires private GitHub CI/README inspection before visibility changes.",
        ],
    }
    (out / "phase21_launch_readiness_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# AiNIR Pre-v1 Phase 21 Launch Readiness",
        "",
        f"overall_status: {overall}",
        f"decision: {decision}",
        f"steps: {report['steps_passed']}/{report['steps_total']} passed",
        "human_external_evaluator_status: pending",
        "production_runtime_ready: false",
        "v1_final_ready: false",
        "public_release_ready: false",
        "",
        "| Step | Status |",
        "|---|---|",
    ]
    for step in steps:
        lines.append(f"| {step.name} | {step.status} |")
    lines.extend([
        "",
        "This readiness decision includes TrustReceipt replay conformance as a hard gate.",
    ])
    (out / "phase21_launch_readiness_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return report
