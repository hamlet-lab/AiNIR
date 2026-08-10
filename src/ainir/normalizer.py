from __future__ import annotations

from typing import List

from .core import DraftModule, Finding
from .registry_context import DynamicRegistryProxy
from .safety_registry import get_registry
from .operation_registry import get_operation_registry


REGISTRY = DynamicRegistryProxy(get_registry)
OP_REGISTRY = DynamicRegistryProxy(get_operation_registry)


def normalize_draft(draft: DraftModule) -> tuple[DraftModule, List[Finding]]:
    """Conservatively normalize aliases using the single safety registry.

    Normalization never turns an unsafe draft into a safe one. Any alias that
    resolves to a sensitive effect remains visible as a finding for the verifier.
    """
    raw = dict(draft.raw)
    findings: List[Finding] = []

    workflow = raw.get("workflow")
    if isinstance(workflow, str):
        normalized_workflow, was_alias = REGISTRY.normalize_workflow(workflow)
        if was_alias:
            findings.append(
                Finding(
                    rule="N000.workflow_alias_normalized",
                    severity="warning",
                    target="workflow",
                    message=f"Workflow alias {workflow!r} was normalized to {normalized_workflow!r}.",
                )
            )
            raw["workflow"] = normalized_workflow

    normalized_ops = []
    for op in draft.operations:
        new_op = dict(op)
        raw_effects = op.get("effects", []) or []
        effects: list[str] = []
        alias_seen = False
        safety_critical_alias_seen = False
        for effect in raw_effects:
            if not isinstance(effect, str):
                continue
            normalized_effect, was_alias = REGISTRY.normalize_effect(effect)
            effects.append(normalized_effect)
            if was_alias:
                alias_seen = True
                if REGISTRY.classify_effect(normalized_effect) & {
                    "payment_real", "raw_token", "raw_pii", "destructive_delete", "external_unallowlisted"
                }:
                    safety_critical_alias_seen = True
        if alias_seen:
            findings.append(
                Finding(
                    rule="N001.effect_alias_normalized",
                    severity="warning",
                    target=str(op.get("id", "unknown_op")),
                    message="Effect alias was normalized using the safety registry.",
                )
            )
        if safety_critical_alias_seen:
            findings.append(
                Finding(
                    rule="N003.safety_critical_effect_alias_visible",
                    severity="critical",
                    target=str(op.get("id", "unknown_op")),
                    message="An effect alias resolved to a safety-critical effect family; verifier must block or require review.",
                )
            )
        op_name = op.get("op")
        normalized_op, op_was_alias = OP_REGISTRY.resolve_id(op_name)
        if normalized_op and op_was_alias:
            findings.append(
                Finding(
                    rule="N010.operation_alias_normalized",
                    severity="warning",
                    target=str(op.get("id", "unknown_op")),
                    message=f"Operation alias {op_name!r} was normalized to registered spec {normalized_op!r}.",
                )
            )
            new_op["op"] = normalized_op
        new_op["effects"] = effects
        normalized_ops.append(new_op)
    raw["operations"] = normalized_ops

    # Do not trust claim status emitted by a model. The verifier will decide
    # whether verified status is supported by registry-bound evidence.
    return DraftModule(raw=raw), findings
