from __future__ import annotations

from .core import DraftModule, Finding
from .execution_context import TrustedExecutionContext
from .registry_context import DynamicRegistryProxy
from .safety_registry import compact, get_registry
from .operation_registry import get_operation_registry


REGISTRY = DynamicRegistryProxy(get_registry)
OP_REGISTRY = DynamicRegistryProxy(get_operation_registry)


def evaluate_policy_core(draft: DraftModule, context: TrustedExecutionContext | None = None) -> list[Finding]:
    """Evaluate the demo policy core from registry-defined risk families.

    This module deliberately contains no local alias tables or allowlists. All
    effect/operation family decisions come from the safety registry.
    """
    context = context or TrustedExecutionContext.public_demo()
    findings: list[Finding] = []
    policy_ids = draft.policy_ids()

    for op in draft.operations:
        op_id = str(op.get("id", "unknown_op"))
        op_name = str(op.get("op", ""))
        effects = [e for e in (op.get("effects") or []) if isinstance(e, str)]
        op_policies = {p for p in (op.get("policies") or []) if isinstance(p, str)} | policy_ids
        effect_families = set().union(*(REGISTRY.classify_effect(e) for e in effects)) if effects else set()
        spec = OP_REGISTRY.spec_for(op_name)
        # Registered safe operations are judged by their operation specs. The broad
        # keyword classifier is a fallback for unknown operations and for specs
        # that are explicitly forbidden in the public demo path; this preserves
        # negative conformance visibility while avoiding false positives for safe
        # registered operations such as export encryption or authorization.
        if spec is None or getattr(spec, "forbidden_in_public_demo", False) or getattr(spec, "forbidden_families", set()):
            op_families = REGISTRY.classify_operation(op_name)
        else:
            op_families = set()
        findings.extend(_operation_implied_effect_findings(op_id, op_name, op_families, effect_families))
        findings.extend(_payment_idempotency_findings(op_id, op_name, effects, op_policies))

    for op_id, effect in draft.all_effects():
        families = REGISTRY.classify_effect(effect)
        if "raw_token" in families:
            findings.append(
                Finding(
                    rule="P001.no_raw_secret_persistence",
                    severity="critical",
                    target=op_id,
                    message="Raw secret token would be stored, logged, or persisted.",
                    suggestion="Hash or seal the token before persistence; never log raw tokens.",
                )
            )
        if "raw_pii" in families:
            findings.append(
                Finding(
                    rule="P002.no_raw_pii_logging_or_storage",
                    severity="critical",
                    target=op_id,
                    message="Raw PII would be logged/stored or exported.",
                    suggestion="Use metadata-only audit or encrypted/allowlisted export packaging.",
                )
            )
        if "payment_real" in families:
            findings.append(
                Finding(
                    rule="P003.no_real_payment_in_public_demo",
                    severity="critical",
                    target=op_id,
                    message="Real or production-like payment effect is forbidden in the public demo path.",
                    suggestion="Use mock/sandbox effect with idempotency, or keep blocked for review.",
                )
            )
        if "destructive_delete" in families:
            findings.append(
                Finding(
                    rule="P004.no_hard_delete_in_public_demo",
                    severity="critical",
                    target=op_id,
                    message="Hard/permanent/destructive deletion variant is forbidden in the public demo path.",
                    suggestion="Use scheduled soft delete plus approval, grace period, legal-hold, and anonymization gates.",
                )
            )
        if draft.workflow == "CreateUser" and "notification" in families and compact(effect).find("real") >= 0:
            findings.append(
                Finding(
                    rule="P005.no_direct_email_in_create_user",
                    severity="critical",
                    target=op_id,
                    message="CreateUser must not send real email directly; use outbox/worker separation.",
                    suggestion="Replace direct email send with a WelcomeEmailRequested outbox event.",
                )
            )
        if "external_unallowlisted" in families:
            findings.append(
                Finding(
                    rule="P008.no_unallowlisted_external_effect",
                    severity="critical",
                    target=op_id,
                    message=f"External effect {effect} is not allowlisted in the public demo path.",
                    suggestion="Use a mock/sandbox effect or keep the module blocked for review.",
                )
            )
        if context.is_test_like and "external" in families and _is_real_like_external_effect(effect):
            findings.append(
                Finding(
                    rule="P006.no_real_external_effect_in_test_context",
                    severity="critical",
                    target=op_id,
                    message=f"Trusted execution context {context.environment!r} forbids real/live external effects.",
                    suggestion="Use a mock/sandbox effect, or run only under a trusted non-test context after verifier approval.",
                )
            )

    if draft.workflow == "NewsletterSignup":
        has_marketing = any("marketing" in compact(effect) for _, effect in draft.all_effects()) or any(
            "marketing" in compact(str(op.get("op", ""))) for op in draft.operations
        )
        if has_marketing and "policy.no_marketing_without_consent" not in policy_ids:
            findings.append(
                Finding(
                    rule="P007.no_marketing_without_consent",
                    severity="critical",
                    target="module",
                    message="Marketing email operation/effect requires explicit consent policy.",
                    suggestion="Add policy.no_marketing_without_consent and enforce consent before subscriber/outbox write.",
                )
            )
    return findings


def _operation_implied_effect_findings(op_id: str, op_name: str, op_families: set[str], effect_families: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for family in sorted(op_families):
        required = REGISTRY.required_effect_family_for_operation_family(family)
        if not required:
            continue
        if required not in effect_families:
            rule = "P020.undeclared_implied_effect"
            if required == "notification":
                rule = "P021.undeclared_implied_email_effect"
            elif required == "destructive":
                rule = "P022.undeclared_implied_hard_delete_effect"
            elif required == "payment":
                rule = "P020.undeclared_implied_payment_effect"
            elif required == "external":
                rule = "P025.undeclared_implied_external_effect"
            findings.append(
                Finding(
                    rule=rule,
                    severity="critical",
                    target=op_id,
                    message=f"Operation {op_name!r} implies {required} side effects but does not declare that effect family.",
                    suggestion="Declare the implied effect explicitly or keep the draft blocked for review.",
                )
            )
    return findings


def _payment_idempotency_findings(op_id: str, op_name: str, effects: list[str], policies: set[str]) -> list[Finding]:
    families = set().union(*(REGISTRY.classify_effect(e) for e in effects)) if effects else set()
    op_families = REGISTRY.classify_operation(op_name)
    payment_like = "payment_charge" in families or "payment" in op_families
    idempotency_policies = set(REGISTRY.data.get("role_markers", {}).get("idempotency", {}).get("policy_any", []))
    if payment_like and not (policies & idempotency_policies):
        return [
            Finding(
                rule="P009.payment_charge_requires_idempotency",
                severity="critical",
                target=op_id,
                message="Payment-like operation/effect requires an idempotency policy or idempotency marker.",
                suggestion="Add policy.payment_idempotency_required or an explicit idempotency operation before charging.",
            )
        ]
    return []


def _is_real_like_external_effect(effect: str) -> bool:
    c = compact(effect)
    if not c.startswith("effect.external") and not c.startswith("external"):
        return False
    real_terms = {"real", "live", "prod", "production"}
    safe_terms = {"mock", "sandbox", "dryrun", "test_stub"}
    parts = set(c.split("."))
    return bool(parts & real_terms) and not bool(parts & safe_terms)
