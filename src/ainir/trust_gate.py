
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from .core import DraftModule, Finding, VerificationReport
from .execution_context import TrustedExecutionContext
from .lowering_gate import assess_lowering_eligibility
from .verifier import verify_draft
from .safety_registry import get_registry
from .evidence_ledger import non_vacuous_evidence_findings
from .registry_provenance import registry_snapshot, registry_snapshot_failures
from .contracts import (
    LEGACY_TRUST_GATE_DECISION_VERSION,
    LEGACY_TRUST_RECEIPT_VERSION,
    TRUST_GATE_DECISION_CONTRACT,
    TRUST_GATE_DECISION_KIND,
    TRUST_RECEIPT_CONTRACT,
    TRUST_RECEIPT_KIND,
)


_GATE_PREFIXES: dict[str, str] = {
    "S": "strict_draft_ast",
    "N": "safety_registry_resolution",
    "W": "workflow_registry",
    "X": "trusted_execution_context",
    "TR": "evidence_ledger_binding",
    "T": "trust_gate",
    "O": "operation_spec_binding",
    "P": "policy_core",
    "C": "capability_contract",
    "WF": "workflow_semantic_profile",
    "M": "workflow_semantic_profile",
    "TX": "transaction_binding",
    "H": "hole_resolution",
    "L": "lowering_eligibility",
    "RS": "registry_snapshot_valid",
}

_REQUIRED_GATES = [
    "strict_draft_ast",
    "safety_registry_resolution",
    "workflow_registry",
    "trusted_execution_context",
    "registry_snapshot_valid",
    "evidence_ledger_binding",
    "operation_spec_binding",
    "capability_contract",
    "workflow_semantic_profile",
    "transaction_binding",
    "policy_core",
    "lowering_eligibility",
]


@dataclass(frozen=True)
class TrustGateDecision:
    """Unified AiNIR trust-gate surface.

    This object is an AiNIR-internal decision surface. It is not an adapter for
    any downstream compiler/runtime. Optional export surfaces may consume this
    decision later, but they do not define AiNIR's core trust gate.
    """

    status: str
    module_id: str
    workflow: str
    executable: bool
    lowering_allowed: bool
    handoff_allowed: bool
    trusted_environment: str
    satisfied_gates: tuple[str, ...] = field(default_factory=tuple)
    failed_gates: tuple[str, ...] = field(default_factory=tuple)
    warning_gates: tuple[str, ...] = field(default_factory=tuple)
    gate_results: Mapping[str, Any] = field(default_factory=dict)
    required_next_actions: tuple[str, ...] = field(default_factory=tuple)
    verifier_report: Mapping[str, Any] = field(default_factory=dict)
    lowering_eligibility: Mapping[str, Any] = field(default_factory=dict)
    findings: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    receipt: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self, *, contract_version: str = LEGACY_TRUST_GATE_DECISION_VERSION) -> dict[str, Any]:
        """Serialize the decision using a stable or legacy public contract.

        The default remains the legacy pre-v1 representation for one RC cycle so
        existing phase harnesses and stored artifacts stay byte-for-byte
        reproducible. New user-facing CLI commands call :meth:`as_public_dict`.
        """

        payload = {
            "kind": TRUST_GATE_DECISION_KIND,
            "version": LEGACY_TRUST_GATE_DECISION_VERSION,
            "status": self.status,
            "module_id": self.module_id,
            "workflow": self.workflow,
            "executable": self.executable,
            "lowering_allowed": self.lowering_allowed,
            "handoff_allowed": self.handoff_allowed,
            "trusted_environment": self.trusted_environment,
            "satisfied_gates": list(self.satisfied_gates),
            "failed_gates": list(self.failed_gates),
            "warning_gates": list(self.warning_gates),
            "gate_results": dict(self.gate_results),
            "required_next_actions": list(self.required_next_actions),
            "verifier_report": dict(self.verifier_report),
            "lowering_eligibility": dict(self.lowering_eligibility),
            "findings": [dict(f) for f in self.findings],
            "receipt": dict(self.receipt),
        }
        if contract_version == LEGACY_TRUST_GATE_DECISION_VERSION:
            return payload
        if contract_version != TRUST_GATE_DECISION_CONTRACT:
            raise ValueError(f"unsupported TrustGateDecision contract: {contract_version!r}")
        from .trust_receipt_store import convert_trust_receipt_contract

        payload["legacy_version"] = LEGACY_TRUST_GATE_DECISION_VERSION
        payload["version"] = TRUST_GATE_DECISION_CONTRACT
        payload["receipt"] = convert_trust_receipt_contract(
            payload["receipt"], target_version=TRUST_RECEIPT_CONTRACT
        )
        return payload

    def as_public_dict(self) -> dict[str, Any]:
        """Serialize with stable phase-independent contract identifiers."""

        return self.as_dict(contract_version=TRUST_GATE_DECISION_CONTRACT)


def evaluate_trust_gate(draft: DraftModule, context: TrustedExecutionContext | None = None) -> TrustGateDecision:
    context = context or TrustedExecutionContext.public_demo()
    verifier_report = verify_draft(draft, context)
    verifier_dict = verifier_report.as_dict()
    registry_snapshot_data = registry_snapshot()
    registry_findings: list[dict[str, Any]] = [_registry_snapshot_finding(f) for f in registry_snapshot_failures(registry_snapshot_data)]
    if verifier_report.status == "invalid":
        lowering_dict = {"status": "not_checked", "context_environment": context.environment, "findings": []}
        lowering_allowed_by_gate = False
        trust_evidence_findings: list[dict[str, Any]] = []
    else:
        lowering = assess_lowering_eligibility(draft, verifier_report, context)
        lowering_dict = lowering.as_dict()
        lowering_allowed_by_gate = lowering.allowed
        trust_evidence_findings = [f.as_dict() for f in non_vacuous_evidence_findings(draft)]
    context_findings: list[dict[str, Any]] = []
    if context.is_production:
        context_findings.append({
            "rule": "X010.production_context_not_supported",
            "severity": "critical",
            "target": "trusted_context.environment",
            "message": "The public demo is not a production runtime; production context cannot pass handoff/lowering.",
        })
        context_findings.append({
            "rule": "T010.production_context_not_supported",
            "severity": "critical",
            "target": "trust_gate",
            "message": "The Trust Gate refuses public-demo production context handoff/lowering.",
        })
    all_findings: list[dict[str, Any]] = list(verifier_dict.get("findings", [])) + registry_findings + trust_evidence_findings + context_findings + list(lowering_dict.get("findings", []))
    failed = sorted({_gate_for_rule(str(f.get("rule", ""))) for f in all_findings if f.get("severity") == "critical"})
    failed = [g for g in failed if g]
    warnings = sorted({_gate_for_rule(str(f.get("rule", ""))) for f in all_findings if f.get("severity") == "warning"})
    warnings = [g for g in warnings if g and g not in failed]

    if verifier_report.status == "invalid":
        status = "invalid"
    elif failed or verifier_report.status != "passed" or not lowering_allowed_by_gate:
        status = "refused"
    else:
        status = "passed"

    lowering_allowed = status == "passed" and lowering_allowed_by_gate
    executable = lowering_allowed
    handoff_allowed = status == "passed"
    gate_results = _build_gate_results(draft, failed, warnings, status)
    satisfied = tuple(g for g, result in gate_results.items() if result.get("status") == "passed")
    next_actions = tuple(_next_actions(all_findings, status))
    receipt = _build_receipt(draft, context, verifier_report, lowering_dict, status, failed, warnings, gate_results, registry_snapshot_data)

    return TrustGateDecision(
        status=status,
        module_id=verifier_report.module_id,
        workflow=verifier_report.workflow,
        executable=executable,
        lowering_allowed=lowering_allowed,
        handoff_allowed=handoff_allowed,
        trusted_environment=context.environment,
        satisfied_gates=tuple(satisfied),
        failed_gates=tuple(failed),
        warning_gates=tuple(warnings),
        gate_results=gate_results,
        required_next_actions=next_actions,
        verifier_report=verifier_dict,
        lowering_eligibility=lowering_dict,
        findings=tuple(all_findings),
        receipt=receipt,
    )


def _registry_snapshot_finding(failure: Mapping[str, Any]) -> dict[str, Any]:
    reason = str(failure.get("reason", "registry_snapshot_invalid"))
    name = str(failure.get("name", "registry"))
    return {
        "rule": "RS001.registry_snapshot_invalid",
        "severity": "critical",
        "target": f"registry_snapshot.items.{name}",
        "message": f"Required trust registry snapshot is invalid: {reason}",
        "details": dict(failure),
        "suggestion": "Repair duplicate/corrupt/missing registry files and keep root/package registry copies byte-identical before issuing a TrustReceipt or handoff artifact.",
    }


def _gate_results(failed: list[str], warnings: list[str]) -> dict[str, dict[str, str]]:
    failed_set = set(failed)
    warning_set = set(warnings)
    results: dict[str, dict[str, str]] = {}
    for gate in _REQUIRED_GATES:
        if gate in failed_set:
            status = "failed"
        elif gate in warning_set:
            status = "passed_with_warnings"
        else:
            status = "passed"
        results[gate] = {"status": status}
    return results


def _gate_for_rule(rule: str) -> str:
    # Rule identifiers start with an uppercase prefix such as S060, TR001,
    # TX001, or L008. Extract the alphabetic prefix explicitly instead of
    # relying on prefix-length sorting, so adding future prefixes cannot
    # silently change gate classification.
    match = re.match(r"^[A-Z]+", rule or "")
    if not match:
        return "unknown_gate"
    return _GATE_PREFIXES.get(match.group(0), "unknown_gate")


def _build_gate_results(draft: DraftModule, failed_gates: list[str], warning_gates: list[str], decision_status: str = "passed") -> dict[str, dict[str, Any]]:
    failed = set(failed_gates)
    warnings = set(warning_gates)
    claim_count = len(draft.claims)
    verified_claim_count = sum(1 for c in draft.claims if isinstance(c, Mapping) and c.get("status") == "verified")
    evidence_ref_count = sum(
        1
        for c in draft.claims
        if isinstance(c, Mapping)
        for e in (c.get("evidence") or [])
        if isinstance(e, Mapping)
    )
    results: dict[str, dict[str, Any]] = {}
    strict_failed = "strict_draft_ast" in failed
    for gate in _REQUIRED_GATES:
        if gate in failed:
            status = "failed"
        elif gate in warnings:
            status = "warning"
        elif decision_status == "invalid" and gate != "strict_draft_ast":
            status = "not_checked"
        elif strict_failed and gate != "strict_draft_ast":
            status = "not_checked"
        else:
            status = "passed"
        results[gate] = {"status": status}
    evidence = results.get("evidence_ledger_binding", {"status": "passed"})
    evidence.update({
        "claim_count": claim_count,
        "verified_claim_count": verified_claim_count,
        "evidence_reference_count": evidence_ref_count,
    })
    if decision_status == "invalid" and evidence["status"] != "failed":
        evidence["status"] = "not_checked"
    elif evidence["status"] == "passed" and verified_claim_count == 0:
        evidence["status"] = "insufficient_input"
    results["evidence_ledger_binding"] = evidence
    return results


def _next_actions(findings: list[Mapping[str, Any]], status: str) -> list[str]:
    if status == "passed":
        return []
    actions: list[str] = []
    rules = {str(f.get("rule", "")) for f in findings}
    if any("registry" in r.lower() or r.startswith("RS") for r in rules):
        actions.append("repair_required_registry_snapshot")
    if any("evidence" in r.lower() or r.startswith("TR") for r in rules):
        actions.append("provide_ledger_bound_evidence")
    if any(r.startswith("S") for r in rules):
        actions.append("repair_draft_structure")
    if any(r.startswith("O") for r in rules):
        actions.append("bind_operations_to_registered_specs")
    if any(r.startswith("C") for r in rules):
        actions.append("reduce_capabilities_to_exact_operation_contract")
    if any(r.startswith("TX") for r in rules):
        actions.append("repair_transaction_contract")
    if any(r.startswith("L") for r in rules):
        actions.append("rerun_verification_before_lowering")
    if not actions:
        actions.append("review_trust_gate_findings")
    return sorted(set(actions))




def _evidence_summary(draft: DraftModule, report: VerificationReport, gate_results: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Summarize whether the evidence gate was a real check or a refusal.

    This prevents a vacuous "no findings" interpretation from looking like an
    evidence pass in receipts or downstream audit logs. Trust Gate / lowering
    findings are reflected through gate_results, not just the verifier report.
    """
    claims = draft.claims
    findings = list(report.findings)
    evidence_rules = {f.rule for f in findings if f.rule.startswith("TR")}
    verified_claims = [c for c in claims if str(c.get("status", "hypothesized")) == "verified"]
    referenced_evidence = []
    for claim in verified_claims:
        for ev in claim.get("evidence", []) or []:
            if isinstance(ev, Mapping) and isinstance(ev.get("id"), str):
                referenced_evidence.append(str(ev["id"]))
    evidence_gate = {}
    if isinstance(gate_results, Mapping):
        candidate = gate_results.get("evidence_ledger_binding")
        if isinstance(candidate, Mapping):
            evidence_gate = dict(candidate)
    gate_status = str(evidence_gate.get("status") or ("failed" if evidence_rules else "passed"))
    return {
        "claim_count": len(claims),
        "verified_claim_count": len(verified_claims),
        "referenced_evidence_count": len(referenced_evidence),
        "referenced_evidence_ids": sorted(set(referenced_evidence)),
        "ledger_bound": gate_status in {"passed", "warning"} and bool(verified_claims) and bool(referenced_evidence),
        "gate_status": gate_status,
        "finding_rules": sorted(evidence_rules),
    }

def _build_receipt(
    draft: DraftModule,
    context: TrustedExecutionContext,
    report: VerificationReport,
    lowering: Mapping[str, Any],
    status: str,
    failed_gates: list[str],
    warning_gates: list[str],
    gate_results: Mapping[str, Any] | None = None,
    registry_snapshot_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_path = draft.raw.get("__source_path__")
    draft_payload = {k: v for k, v in draft.raw.items() if not str(k).startswith("__")}
    draft_text = yaml.safe_dump(draft_payload, sort_keys=True, allow_unicode=True)
    canonical_draft_hash = "sha256:" + sha256(draft_text.encode("utf-8")).hexdigest()
    raw_source_sha256 = draft.raw.get("__raw_source_sha256__")
    if not isinstance(raw_source_sha256, str) or not raw_source_sha256.startswith("sha256:"):
        raw_source_sha256 = canonical_draft_hash
    draft_hash = canonical_draft_hash
    registry = get_registry()
    registry_text = json.dumps(registry.data, sort_keys=True, ensure_ascii=False)
    registry_hash = "sha256:" + sha256(registry_text.encode("utf-8")).hexdigest()
    if registry_snapshot_data is None:
        registry_snapshot_data = registry_snapshot()
    registry_snapshot_hash = str(registry_snapshot_data.get("combined_sha256") or registry_hash)
    report_text = json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False)
    report_hash = "sha256:" + sha256(report_text.encode("utf-8")).hexdigest()
    evidence_summary = _evidence_summary(draft, report, gate_results)
    receipt_seed = "|".join([raw_source_sha256, canonical_draft_hash, registry_snapshot_hash, report_hash, context.environment, context.source, context.purpose, status])
    receipt_id = "ainir.trust.receipt." + sha256(receipt_seed.encode("utf-8")).hexdigest()[:20]
    receipt = {
        "receipt_id": receipt_id,
        "receipt_kind": TRUST_RECEIPT_KIND,
        "version": LEGACY_TRUST_RECEIPT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "module_id": report.module_id,
        "workflow": report.workflow,
        "draft_hash": draft_hash,
        "canonical_draft_sha256": canonical_draft_hash,
        "raw_source_sha256": raw_source_sha256,
        "draft_source_path": str(source_path) if isinstance(source_path, str) else None,
        "safety_registry_hash": registry_hash,
        "registry_snapshot_hash": registry_snapshot_hash,
        "registry_snapshot": registry_snapshot_data,
        "verifier_report_hash": report_hash,
        "trusted_context": {
            "environment": context.environment,
            "source": context.source,
            "purpose": context.purpose,
        },
        "failed_gates": failed_gates,
        "warning_gates": warning_gates,
        "gate_results": dict(gate_results or {}),
        "lowering_eligibility": dict(lowering),
        "evidence_summary": evidence_summary,
        "production_runtime_ready": False,
        "v1_final_ready": False,
        "external_consumer_handoff": {
            "status": "future_extension_point",
            "note": "AiNIR may expose verified intent artifacts later; no external consumer is part of the current pre-v1 public demo.",
        },
    }
    # Imported lazily to avoid a module import cycle at import time.
    from .trust_receipt_store import stable_receipt_projection_hash

    receipt["stable_receipt_projection_hash"] = stable_receipt_projection_hash(receipt)
    return receipt
