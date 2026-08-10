from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from .core import DraftModule, Finding, VerificationReport
from .draft_ast import parse_draft_ast
from .execution_context import TrustedExecutionContext
from .normalizer import normalize_draft
from .policy_core import evaluate_policy_core
from .registry_context import DynamicRegistryProxy
from .safety_registry import get_registry, strict_safe_id
from .operation_registry import get_operation_registry
from .evidence_ledger import get_evidence_ledger
from .transaction_contract import transaction_findings


REGISTRY = DynamicRegistryProxy(get_registry)
OP_REGISTRY = DynamicRegistryProxy(get_operation_registry)
_SAFE_STATUS_VALUES = {"hypothesized", "verified", "unverified"}


def verify_draft(draft: DraftModule, context: TrustedExecutionContext | None = None) -> VerificationReport:
    """Verify an untrusted AiNIR public-demo draft using registry-backed gates.

    Pre-v1 Phase 2: untrusted YAML must first parse into Strict Draft AST.
    Semantic verification never runs over arbitrary dictionaries.
    """
    context = context or TrustedExecutionContext.public_demo()
    parsed = parse_draft_ast(draft)
    if parsed.has_critical or parsed.ast is None:
        return VerificationReport(
            module_id=_safe_report_field(draft.raw.get("module"), "invalid"),
            workflow=_safe_report_field(draft.raw.get("workflow"), "invalid"),
            status="invalid",
            findings=list(parsed.findings),
        )

    ast_draft = parsed.ast.to_draft_module()
    for internal_field in ("__source_path__", "__raw_source_sha256__"):
        if isinstance(draft.raw.get(internal_field), str):
            ast_draft.raw[internal_field] = draft.raw[internal_field]
    normalized, findings = normalize_draft(ast_draft)
    findings.extend(parsed.findings)
    schema_findings = _schema_findings(normalized)
    findings.extend(schema_findings)
    findings.extend(_workflow_findings(normalized))
    findings.extend(_execution_context_findings(normalized, context))
    findings.extend(_trust_findings(normalized))
    findings.extend(_operation_spec_findings(normalized))
    findings.extend(_capability_findings(normalized))
    findings.extend(_semantic_profile_findings(normalized))
    findings.extend(_transaction_findings(normalized))
    findings.extend(_hole_findings(normalized))
    findings.extend(evaluate_policy_core(normalized, context))

    status = "blocked" if any(f.severity == "critical" for f in findings) else "passed"
    return VerificationReport(
        module_id=normalized.module_id,
        workflow=normalized.workflow,
        status=status,
        findings=findings,
    )



def _execution_context_findings(draft: DraftModule, context: TrustedExecutionContext) -> list[Finding]:
    findings: list[Finding] = []
    if "environment" in draft.raw:
        draft_env = draft.raw.get("environment")
        if isinstance(draft_env, str):
            findings.append(
                Finding(
                    rule="X001.draft_environment_is_untrusted_metadata",
                    severity="warning",
                    target="environment",
                    message=f"Draft-declared environment {draft_env!r} is untrusted metadata and does not control policy evaluation.",
                    suggestion=f"Policy evaluation used trusted context environment {context.environment!r} supplied by the runtime/CLI.",
                )
            )
        else:
            findings.append(
                Finding(
                    rule="X002.draft_environment_malformed",
                    severity="critical",
                    target="environment",
                    message="Draft environment metadata must be a string if present.",
                )
            )
    return findings

def _schema_findings(draft: DraftModule) -> list[Finding]:
    findings: list[Finding] = []
    raw = draft.raw

    if "__parse_error__" in raw:
        findings.append(Finding("S000.yaml_parse_error", "critical", "Draft YAML could not be parsed.", "draft"))
    if "__decode_error__" in raw:
        findings.append(Finding("S000.yaml_decode_error", "critical", "Draft file is not valid UTF-8 YAML text.", "draft"))
        findings.append(Finding("S072.yaml_utf8_decode_error", "critical", "Draft file is not valid UTF-8 YAML text.", "draft"))
    if "__complex_key_error__" in raw:
        findings.append(Finding("S071.yaml_complex_mapping_key_forbidden", "critical", "Draft YAML uses a complex/non-scalar mapping key.", "draft"))
    if "__load_error__" in raw:
        findings.append(Finding("S000.draft_load_error", "critical", "Draft file could not be loaded.", "draft"))
    if "__invalid_root__" in raw:
        findings.append(Finding("S000.draft_root_must_be_object", "critical", "Draft YAML root must be an object, not a list/string/scalar.", "draft"))

    for field in ("module", "workflow", "task"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip() or value.strip() == "unknown":
            findings.append(Finding("S001.required_identity_field", "critical", f"Draft requires non-empty string field '{field}'.", field))
        else:
            findings.extend(_validate_safe_id_value(value, field, f"Draft field '{field}'"))

    operations = raw.get("operations")
    if not isinstance(operations, list) or len(operations) == 0:
        findings.append(Finding("S003.operations_required", "critical", "Draft must contain at least one operation.", "operations"))
    else:
        seen: set[str] = set()
        for index, op in enumerate(operations):
            target = f"operations[{index}]"
            if not isinstance(op, Mapping):
                findings.append(Finding("S004.operation_must_be_object", "critical", "Operation item must be an object.", target))
                continue
            op_id = op.get("id")
            op_name = op.get("op")
            if not isinstance(op_id, str) or not op_id.strip():
                findings.append(Finding("S005.operation_id_required", "critical", "Operation requires non-empty string id.", target))
            else:
                findings.extend(_validate_safe_id_value(op_id, op_id, "Operation id"))
                if op_id in seen:
                    findings.append(Finding("S007.operation_id_unique", "critical", "Duplicate operation id.", op_id))
                seen.add(op_id)
            if not isinstance(op_name, str) or not op_name.strip():
                findings.append(Finding("S008.operation_op_required", "critical", "Operation requires non-empty string op.", str(op_id or target)))
            else:
                findings.extend(_validate_safe_id_value(op_name, str(op_id or target), "Canonical operation name"))

            effects = op.get("effects")
            if effects is None:
                findings.append(Finding("S010.effects_required", "critical", "Operation must explicitly declare effects; use [] for pure.", str(op_id or target)))
            elif not isinstance(effects, list):
                findings.append(Finding("S011.effects_must_be_list", "critical", "Operation effects must be a list.", str(op_id or target)))
            else:
                findings.extend(_validate_string_list(effects, str(op_id or target), "effect", "S012"))

            capabilities = op.get("capabilities", [])
            if capabilities is not None and not isinstance(capabilities, list):
                findings.append(Finding("S013.capabilities_must_be_list", "critical", "Operation capabilities must be a list if present.", str(op_id or target)))
            else:
                findings.extend(_validate_string_list(capabilities or [], str(op_id or target), "capability", "S016"))

            policies = op.get("policies", [])
            if policies is not None and not isinstance(policies, list):
                findings.append(Finding("S020.operation_policies_must_be_list", "critical", "Operation policies must be a list if present.", str(op_id or target)))
            else:
                findings.extend(_validate_string_list(policies or [], str(op_id or target), "policy", "S021"))

    for section in ("claims", "holes", "policies", "evidence"):
        findings.extend(_validate_section_list(raw, section))

    executable = raw.get("executable", False)
    if not isinstance(executable, bool):
        findings.append(Finding("S015.executable_must_be_boolean", "critical", "Draft field 'executable' must be true or false.", "executable"))
    return findings


def _validate_safe_id_value(value: str, target: str, label: str) -> list[Finding]:
    findings: list[Finding] = []
    if value != value.strip():
        findings.append(Finding("S002.identity_whitespace_forbidden", "critical", f"{label} has leading or trailing whitespace.", target))
    if not strict_safe_id(value):
        findings.append(Finding("S002.unsafe_identity_field", "critical", f"{label} contains unsafe characters.", target))
    return findings


def _validate_string_list(values: Iterable[object], target: str, label: str, prefix: str) -> list[Finding]:
    findings: list[Finding] = []
    for index, value in enumerate(values):
        item_target = f"{target}.{label}s[{index}]"
        if not isinstance(value, str) or not value.strip():
            findings.append(Finding(f"{prefix}.{label}_id_required", "critical", f"{label.capitalize()} id must be a non-empty string.", item_target))
            continue
        if value != value.strip():
            findings.append(Finding(f"{prefix}.{label}_id_whitespace_forbidden", "critical", f"{label.capitalize()} id has leading or trailing whitespace.", item_target))
        if not strict_safe_id(value):
            findings.append(Finding(f"{prefix}.{label}_id_unsafe", "critical", f"{label.capitalize()} id contains unsafe characters.", item_target))
    return findings


def _validate_section_list(raw: Mapping[str, Any], section: str) -> list[Finding]:
    findings: list[Finding] = []
    value = raw.get(section, [])
    if value is None:
        return findings
    if not isinstance(value, list):
        findings.append(Finding(f"S030.{section}_must_be_list", "critical", f"Section '{section}' must be a list if present.", section))
        return findings
    for index, item in enumerate(value):
        target = f"{section}[{index}]"
        if not isinstance(item, Mapping):
            findings.append(Finding(f"S017.section_item_must_be_object", "critical", f"Items in '{section}' must be objects, not prose/scalars.", target))
            continue
        item_id = item.get("id")
        if item_id is not None:
            if not isinstance(item_id, str) or not item_id.strip():
                findings.append(Finding(f"S032.{section}_id_must_be_string", "critical", f"{section} id must be a non-empty string if present.", target))
            else:
                findings.extend(_validate_safe_id_value(item_id, target, f"{section} id"))
        if section == "claims":
            status = item.get("status", "hypothesized")
            if not isinstance(status, str) or status not in _SAFE_STATUS_VALUES:
                findings.append(Finding("S040.claim_status_invalid", "critical", "Claim status is not allowed in the public demo.", target))
            evidence = item.get("evidence", [])
            if evidence is not None:
                if not isinstance(evidence, list):
                    findings.append(Finding("S041.claim_evidence_must_be_list", "critical", "Claim evidence must be a list if present.", target))
                else:
                    for ev_index, ev in enumerate(evidence):
                        if not isinstance(ev, Mapping):
                            findings.append(Finding("S042.claim_evidence_item_must_be_object", "critical", "Claim evidence items must be objects.", f"{target}.evidence[{ev_index}]"))
        if section == "holes":
            # Hole text is untrusted prose; structure only here, executable gate later.
            resolved = item.get("resolved", False)
            if resolved is not None and not isinstance(resolved, bool):
                findings.append(Finding("S050.hole_resolved_must_be_boolean", "critical", "Hole resolved field must be boolean if present.", target))
    return findings


def _workflow_findings(draft: DraftModule) -> list[Finding]:
    if not REGISTRY.is_known_workflow(draft.workflow):
        return [
            Finding(
                "W001.unknown_workflow",
                "critical",
                f"Workflow {draft.workflow!r} is outside the bounded public demo workflow registry.",
                "workflow",
                suggestion="Register a workflow profile, operation specs, required semantic roles, effect/capability contracts, and negative conformance fixtures before verification or lowering.",
            )
        ]
    return []


def _trust_findings(draft: DraftModule) -> list[Finding]:
    """Validate evidence attached to claims that explicitly say verified.

    Basic verification may inspect draft structure, policies, and operation
    contracts without requiring an export/handoff-ready evidence packet. The
    non-vacuous "at least one ledger-bound verified claim" rule is enforced by
    the Trust Gate and lowering gate, where handoff/execution eligibility is
    decided.
    """
    findings: list[Finding] = []
    for claim in draft.claims:
        status = str(claim.get("status", "hypothesized"))
        if status != "verified":
            continue
        evidence = claim.get("evidence", []) or []
        checked = False
        reasons: list[str] = []
        if not evidence:
            reasons.append("no evidence attached")
        for ev in evidence:
            if isinstance(ev, Mapping):
                decision = get_evidence_ledger().decide(ev, claim, draft.module_id, draft.workflow, draft)
                checked = checked or decision.checked
                if not decision.checked:
                    reasons.append(f"{decision.evidence_id or 'evidence'}: {decision.reason}")
        if not checked:
            findings.append(
                Finding(
                    rule="T001.verified_claim_requires_ledger_bound_evidence",
                    severity="critical",
                    target=str(claim.get("id", "unknown_claim")),
                    message="Claim marked verified without ledger-bound checked evidence.",
                    suggestion="Reference an evidence id present in registries/evidence_ledger.yaml, or keep the claim hypothesized. Reasons: " + "; ".join(reasons[:4]),
                )
            )
            findings.append(
                Finding(
                    rule="TR001.verified_claim_requires_ledger_bound_evidence",
                    severity="critical",
                    target=str(claim.get("id", "unknown_claim")),
                    message="Evidence ledger binding failed for a verified claim.",
                    suggestion="Bind the claim to a checked evidence ledger record before handoff or lowering.",
                )
            )
    return findings

def _operation_spec_findings(draft: DraftModule) -> list[Finding]:
    findings: list[Finding] = []
    for op in draft.operations:
        for raw in OP_REGISTRY.operation_binding_findings(draft.workflow, op):
            findings.append(
                Finding(
                    rule=str(raw.get("rule", "O000.operation_spec")),
                    severity=str(raw.get("severity", "critical")),
                    target=str(raw.get("target", op.get("id", "unknown_op"))),
                    message=str(raw.get("message", "Operation spec binding failed.")),
                    suggestion=raw.get("suggestion"),
                )
            )
    return findings

def _capability_findings(draft: DraftModule) -> list[Finding]:
    findings: list[Finding] = []
    for op in draft.operations:
        op_id = str(op.get("id", "unknown_op"))
        caps = [c for c in (op.get("capabilities") or []) if isinstance(c, str)]
        for eff in [e for e in (op.get("effects") or []) if isinstance(e, str)]:
            prefixes = REGISTRY.effect_capability_prefixes(eff)
            if not prefixes:
                continue
            if not any(any(cap.startswith(prefix) for prefix in prefixes) for cap in caps):
                findings.append(
                    Finding(
                        rule="C001.effect_requires_matching_capability_family",
                        severity="critical",
                        target=op_id,
                        message=f"Effect {eff} requires a matching capability family.",
                        suggestion=f"Declare one of capability prefixes: {', '.join(prefixes)}",
                    )
                )
    return findings


def _semantic_profile_findings(draft: DraftModule) -> list[Finding]:
    profile = REGISTRY.workflow_profile(draft.workflow)
    findings: list[Finding] = []
    if not profile:
        return findings
    effects = {eff for _, eff in draft.all_effects()}
    effect_families = set().union(*(REGISTRY.classify_effect(e) for e in effects)) if effects else set()
    policy_ids = draft.policy_ids() | {p for op in draft.operations for p in (op.get("policies") or []) if isinstance(p, str)}

    for eff in profile.get("required_effects", []) or []:
        if eff not in effects:
            findings.append(Finding("M001.workflow_required_effect_missing", "critical", f"Workflow {draft.workflow} is missing required effect {eff}.", draft.workflow))
    for policy in profile.get("required_policies", []) or []:
        if policy not in policy_ids:
            findings.append(Finding("M002.workflow_required_policy_missing", "critical", f"Workflow {draft.workflow} is missing required policy {policy}.", draft.workflow))
    for role in profile.get("required_roles", []) or []:
        if not OP_REGISTRY.role_satisfied(role, draft.operations, policy_ids):
            findings.append(Finding("W010.workflow_semantic_profile_missing", "critical", f"Workflow {draft.workflow} is missing required semantic role {role} according to operation specs.", draft.workflow))
    for family in profile.get("forbidden_families", []) or []:
        if family in effect_families:
            findings.append(Finding("M004.workflow_forbidden_effect_family_present", "critical", f"Workflow {draft.workflow} contains forbidden effect family {family}.", draft.workflow))
    if not OP_REGISTRY.semantic_roles_for_operations(draft.operations):
        findings.append(Finding("W011.workflow_semantic_empty", "critical", "Known workflow has no registered semantic roles.", draft.workflow))
    return findings


def _transaction_findings(draft: DraftModule) -> list[Finding]:
    return transaction_findings(draft)

def _hole_findings(draft: DraftModule) -> list[Finding]:
    findings: list[Finding] = []
    if draft.raw.get("executable") is True:
        for hole in draft.holes:
            if hole.get("resolved") is not True:
                findings.append(Finding("H001.unresolved_hole_blocks_execution", "critical", "Executable draft contains unresolved hole.", str(hole.get("id", "unknown_hole"))))
    return findings


def _safe_report_field(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:120]
    return fallback
