from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core import DraftModule, Finding, VerificationReport
from .draft_ast import parse_draft_ast
from .execution_context import TrustedExecutionContext
from .registry_context import DynamicRegistryProxy
from .safety_registry import get_registry
from .evidence_ledger import non_vacuous_evidence_findings


_LOWERING_REGISTRY = DynamicRegistryProxy(get_registry)


@dataclass(frozen=True)
class LoweringEligibility:
    """Result of the pre-lowering safety gate.

    Lowering is not allowed merely because a caller supplies a report that says
    "passed". The gate re-verifies the same draft under the trusted execution
    context and checks that the supplied report is consistent with that result.
    """

    status: str
    context_environment: str
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return self.status == "allowed" and not any(f.severity == "critical" for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "context_environment": self.context_environment,
            "findings": [f.as_dict() for f in self.findings],
        }


def assess_lowering_eligibility(
    draft: DraftModule,
    supplied_report: VerificationReport,
    context: TrustedExecutionContext | None = None,
) -> LoweringEligibility:
    """Assess whether an untrusted draft can be lowered.

    Principles:
    - blocked/invalid drafts cannot be lowered;
    - malformed drafts cannot be lowered;
    - lowering uses a trusted runtime context, not draft.environment;
    - a stale or mismatched verification report cannot authorize lowering;
    - the report must match a fresh verification of the same draft and context.
    """
    from .verifier import verify_draft  # local import avoids a module cycle

    context = context or TrustedExecutionContext.public_demo()
    findings: list[Finding] = []

    if context.is_production:
        findings.append(
            Finding(
                rule="L013.public_demo_production_context_not_lowerable",
                severity="critical",
                target="trusted_context.environment",
                message="The public demo lowerer is not production-runtime ready; production context cannot authorize lowering.",
            )
        )

    parsed = parse_draft_ast(draft)
    if parsed.has_critical or parsed.ast is None:
        findings.extend(parsed.findings)
        findings.append(
            Finding(
                rule="L001.lowering_requires_strict_ast",
                severity="critical",
                target="draft",
                message="Lowering requires a valid Strict Draft AST.",
            )
        )
        return LoweringEligibility("blocked", context.environment, tuple(findings))

    if supplied_report.status != "passed":
        findings.append(
            Finding(
                rule="L002.lowering_requires_passed_report",
                severity="critical",
                target="verification_report",
                message="Lowering requires a verifier report with status='passed'.",
            )
        )

    if supplied_report.critical_count > 0:
        findings.append(
            Finding(
                rule="L003.lowering_report_has_critical_findings",
                severity="critical",
                target="verification_report",
                message="Lowering is forbidden when the supplied report contains critical findings.",
            )
        )

    for hole in draft.holes:
        if hole.get("resolved") is not True:
            findings.append(
                Finding(
                    rule="L007.lowering_forbids_unresolved_holes",
                    severity="critical",
                    target=str(hole.get("id", "unknown_hole")),
                    message="Lowering is refused when the draft contains unresolved holes, even if executable=false.",
                )
            )

    ambiguity = draft.raw.get("ambiguity")
    if isinstance(ambiguity, dict):
        if ambiguity.get("status") != "resolved" or ambiguity.get("unresolved_ambiguities"):
            findings.append(
                Finding(
                    rule="L008.lowering_forbids_unresolved_ambiguity",
                    severity="critical",
                    target="ambiguity",
                    message="Lowering is refused when ambiguity is unresolved, even if the verifier allows a non-executable draft to pass.",
                )
            )
    if draft.raw.get("unresolved_ambiguities"):
        findings.append(
            Finding(
                rule="L008.lowering_forbids_unresolved_ambiguity",
                severity="critical",
                target="unresolved_ambiguities",
                message="Lowering is refused when unresolved ambiguities remain.",
            )
        )

    # Keep the Trust Gate and the actual TypeScript lowerer in sync.
    # These are preflight checks for the public-demo lowerer, not semantic
    # verification of TypeScript. They prevent TrustGateDecision.lowering_allowed
    # from claiming true when the lowerer would later refuse the same draft.
    if draft.raw.get("executable") is False:
        findings.append(
            Finding(
                rule="L012.lowering_forbids_executable_false",
                severity="critical",
                target="executable",
                message="Lowering is refused when executable=false is declared.",
            )
        )
    _add_lowering_surface_findings(parsed.ast.passthrough, findings)
    findings.extend(non_vacuous_evidence_findings(draft, target="evidence.bindings"))
    fresh_report = verify_draft(draft, context)
    if fresh_report.status != "passed":
        findings.append(
            Finding(
                rule="L004.lowering_fresh_verification_failed",
                severity="critical",
                target="verification_report",
                message=f"Fresh verification under trusted context {context.environment!r} returned {fresh_report.status!r}.",
                suggestion="Run verification under the same trusted context and address all critical findings before lowering.",
            )
        )

    if supplied_report.module_id != fresh_report.module_id or supplied_report.workflow != fresh_report.workflow:
        findings.append(
            Finding(
                rule="L005.lowering_report_identity_mismatch",
                severity="critical",
                target="verification_report",
                message="Supplied verification report does not match the freshly verified draft identity.",
                suggestion="Do not reuse verifier reports across drafts or trusted execution contexts.",
            )
        )

    if supplied_report.status != fresh_report.status:
        findings.append(
            Finding(
                rule="L006.lowering_report_status_mismatch",
                severity="critical",
                target="verification_report",
                message="Supplied verification report status differs from fresh verification status.",
            )
        )

    if findings:
        return LoweringEligibility("blocked", context.environment, tuple(findings))
    return LoweringEligibility("allowed", context.environment, tuple())


def _add_lowering_surface_findings(passthrough: Any, findings: list[Finding]) -> None:
    if not isinstance(passthrough, dict):
        return
    input_type = passthrough.get("input_type", "Record<string, unknown>")
    output_type = passthrough.get("output_type", "Record<string, unknown>")
    return_expr = passthrough.get("return", "state")
    if not isinstance(input_type, str) or input_type.strip() not in _LOWERING_REGISTRY.lowering_allowed_types():
        findings.append(
            Finding(
                rule="L009.lowering_forbids_unallowed_input_type",
                severity="critical",
                target="input_type",
                message="Lowering is refused when input_type is outside the public demo TypeScript type allowlist.",
            )
        )
    if not isinstance(output_type, str) or output_type.strip() not in _LOWERING_REGISTRY.lowering_allowed_types():
        findings.append(
            Finding(
                rule="L010.lowering_forbids_unallowed_output_type",
                severity="critical",
                target="output_type",
                message="Lowering is refused when output_type is outside the public demo TypeScript type allowlist.",
            )
        )
    if not isinstance(return_expr, str) or return_expr.strip() not in _LOWERING_REGISTRY.lowering_allowed_returns():
        findings.append(
            Finding(
                rule="L011.lowering_forbids_unallowed_return_expr",
                severity="critical",
                target="return",
                message="Lowering is refused when return expression is outside the public demo return allowlist.",
            )
        )
