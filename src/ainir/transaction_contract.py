"""Transaction binding and semantic integrity checks for AiNIR public demo.

Pre-v1 Phase 12 makes transaction metadata machine-checkable. A workflow that
requires an atomic boundary may not merely attach a note or comment; the
transaction must reference real operation ids, contain operation-spec roles
required by the workflow profile, preserve task order, and expose enough
metadata for the lowerer to hand the boundary to the host runtime.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .core import DraftModule, Finding
from .operation_registry import get_operation_registry
from .registry_context import DynamicRegistryProxy
from .safety_registry import get_registry, strict_safe_id


_ALLOWED_TX_MODES = {"atomic", "host_atomic", "host_enforced_atomic", "transactional"}


@dataclass(frozen=True)
class TransactionBinding:
    id: str
    includes: tuple[str, ...]
    mode: str
    raw: Mapping[str, Any]


REGISTRY = DynamicRegistryProxy(get_registry)
OP_REGISTRY = DynamicRegistryProxy(get_operation_registry)


def extract_transactions(draft: DraftModule) -> list[TransactionBinding]:
    """Return well-shaped transaction bindings only.

    Shape errors are reported by ``transaction_findings``. This helper is for
    lowerers that run after verification has passed.
    """
    out: list[TransactionBinding] = []
    for tx in _transaction_candidates(draft):
        if not isinstance(tx, Mapping):
            continue
        tx_id = tx.get("id")
        includes = tx.get("includes")
        mode = tx.get("mode", tx.get("kind", "atomic"))
        if isinstance(tx_id, str) and isinstance(includes, list) and isinstance(mode, str):
            if all(isinstance(x, str) for x in includes):
                out.append(TransactionBinding(tx_id, tuple(includes), mode, tx))
    return out


def transaction_findings(draft: DraftModule) -> list[Finding]:
    findings: list[Finding] = []
    profile = REGISTRY.workflow_profile(draft.workflow)
    required_roles = {str(r) for r in (profile.get("required_transaction_roles", []) or [])}
    order_roles = [tuple(str(x) for x in pair) for pair in (profile.get("transaction_order_roles", []) or []) if isinstance(pair, list) and len(pair) == 2]
    required_policies = {str(p) for p in (profile.get("required_transaction_policies", []) or [])}
    policy_ids = draft.policy_ids() | {p for op in draft.operations for p in (op.get("policies") or []) if isinstance(p, str)}

    candidates = _transaction_candidates(draft)
    if required_roles and not candidates:
        findings.append(Finding(
            "TX001.transaction_required",
            "critical",
            f"Workflow {draft.workflow} requires a transaction binding for roles: {', '.join(sorted(required_roles))}.",
            "transaction",
            suggestion="Declare transaction: {id, mode: atomic, includes:[...]} and include all required semantic-role operations.",
        ))
        return findings

    operation_ids = [str(op.get("id")) for op in draft.operations if isinstance(op.get("id"), str)]
    operation_id_set = set(operation_ids)
    op_position = {op_id: i for i, op_id in enumerate(operation_ids)}
    required_roles_to_ops = OP_REGISTRY.operation_ids_for_roles(draft.operations, required_roles) if required_roles else {}

    valid_transaction_count = 0
    required_roles_satisfied_in_a_single_tx = False

    for tx_index, tx in enumerate(candidates):
        target = "transaction" if tx_index == 0 else f"transactions[{tx_index}]"
        if not isinstance(tx, Mapping):
            findings.append(Finding("TX002.transaction_must_be_object", "critical", "Transaction binding must be an object.", target))
            continue

        tx_id = tx.get("id")
        if not isinstance(tx_id, str) or not tx_id.strip():
            findings.append(Finding("TX003.transaction_id_required", "critical", "Transaction binding requires a non-empty string id.", target))
        elif not strict_safe_id(tx_id):
            findings.append(Finding("TX004.transaction_id_must_be_safe", "critical", "Transaction id must be a safe identifier without whitespace or code-like characters.", str(tx_id)))

        mode = tx.get("mode", tx.get("kind"))
        if required_roles:
            if not isinstance(mode, str) or not mode.strip():
                findings.append(Finding("TX005.transaction_mode_required", "critical", "Workflows with required transaction roles must declare transaction.mode.", target))
            elif mode not in _ALLOWED_TX_MODES:
                findings.append(Finding("TX006.transaction_mode_not_allowed", "critical", f"Transaction mode {mode!r} is not allowed in the public demo.", target))
        elif mode is not None and (not isinstance(mode, str) or mode not in _ALLOWED_TX_MODES):
            findings.append(Finding("TX006.transaction_mode_not_allowed", "critical", "Transaction mode must be one of the allowed host-enforced atomic modes.", target))

        includes = tx.get("includes")
        if not isinstance(includes, list) or not includes:
            findings.append(Finding("TX007.transaction_includes_required", "critical", "transaction.includes must be a non-empty list of operation ids.", target))
            includes = []

        included_ids: list[str] = []
        seen: set[str] = set()
        for idx, item in enumerate(includes):
            item_target = f"{target}.includes[{idx}]"
            if not isinstance(item, str) or not item.strip():
                findings.append(Finding("TX008.transaction_include_must_be_string", "critical", "transaction.includes entries must be operation id strings.", item_target))
                continue
            if not strict_safe_id(item):
                findings.append(Finding("TX009.transaction_include_must_be_safe", "critical", "transaction.includes entry is not a safe operation id.", item_target))
            if item in seen:
                findings.append(Finding("TX010.transaction_include_duplicate", "critical", "transaction.includes must not contain duplicate operation ids.", item_target))
            seen.add(item)
            if item not in operation_id_set:
                findings.append(Finding("TX003.transaction_include_must_resolve", "critical", "transaction.includes must reference an existing operation id.", item_target))
            else:
                included_ids.append(item)

        if included_ids:
            valid_transaction_count += 1
            positions = [op_position[x] for x in included_ids]
            if positions != sorted(positions):
                findings.append(Finding("TX012.transaction_includes_task_order", "critical", "transaction.includes must follow task operation order.", target))
            if max(positions) - min(positions) + 1 != len(set(positions)):
                findings.append(Finding("TX013.transaction_includes_must_be_contiguous", "critical", "transaction.includes must be a contiguous operation segment so a host runtime can enforce the boundary.", target))

            if required_roles:
                missing_roles: list[str] = []
                for role, op_ids in required_roles_to_ops.items():
                    if not op_ids or not any(op_id in included_ids for op_id in op_ids):
                        missing_roles.append(role)
                if missing_roles:
                    findings.append(Finding("TX014.required_transaction_role_not_included", "critical", f"Transaction is missing operations for required roles: {', '.join(sorted(missing_roles))}.", target))
                else:
                    required_roles_satisfied_in_a_single_tx = True

            for before_role, after_role in order_roles:
                before_ops = [op_id for op_id in required_roles_to_ops.get(before_role, []) if op_id in included_ids]
                after_ops = [op_id for op_id in required_roles_to_ops.get(after_role, []) if op_id in included_ids]
                if before_ops and after_ops:
                    if min(op_position[a] for a in after_ops) <= max(op_position[b] for b in before_ops):
                        findings.append(Finding("TX015.transaction_role_order_violation", "critical", f"Transaction role {before_role} must occur before role {after_role}.", target))

        rollback_on = tx.get("rollback_on", [])
        if rollback_on is not None:
            if not isinstance(rollback_on, list):
                findings.append(Finding("TX016.rollback_on_must_be_list", "critical", "transaction.rollback_on must be a list when present.", target))
            elif any(not isinstance(x, str) or not x.strip() for x in rollback_on):
                findings.append(Finding("TX017.rollback_on_entries_must_be_strings", "critical", "transaction.rollback_on entries must be non-empty strings.", target))

    if required_roles and valid_transaction_count and not required_roles_satisfied_in_a_single_tx:
        findings.append(Finding("TX018.required_roles_must_share_one_transaction", "critical", "Required transactional roles must be included in the same transaction binding.", "transaction"))

    if required_roles and required_policies:
        missing_policies = sorted(required_policies - policy_ids)
        if missing_policies:
            findings.append(Finding("TX019.transaction_policy_required", "critical", f"Workflow {draft.workflow} requires transaction policies: {', '.join(missing_policies)}.", "transaction"))

    return findings


def transaction_for_operation(draft: DraftModule, operation_id: str) -> str | None:
    for tx in extract_transactions(draft):
        if operation_id in tx.includes:
            return tx.id
    return None


def _transaction_candidates(draft: DraftModule) -> list[Any]:
    raw = draft.raw
    candidates: list[Any] = []
    if "transaction" in raw:
        candidates.append(raw.get("transaction"))
    txs = raw.get("transactions")
    if isinstance(txs, list):
        candidates.extend(txs)
    elif txs is not None:
        candidates.append(txs)
    return candidates
