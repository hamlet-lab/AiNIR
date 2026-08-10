"""Strict Draft AST for AiNIR public demo.

Pre-v1 Phase 2 moves shape/type validation ahead of semantic verification.
The verifier should not reason over arbitrary YAML dictionaries. It should first
parse untrusted YAML into a typed DraftAST, collect parse/shape findings, and
only hand a normalized AST-shaped dictionary to the normalizer/verifier.

This is intentionally small and public-demo scoped, but the boundary is strict:
malformed sections, scalar prose, unsafe identifiers, non-list fields, or
missing required identity fields are rejected before semantic rules run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any

from .core import DraftModule, Finding
from .registry_context import DynamicRegistryProxy
from .safety_registry import get_registry, strict_safe_id

REGISTRY = DynamicRegistryProxy(get_registry)

_SAFE_STATUS_VALUES = {"hypothesized", "verified", "unverified"}
_OPTIONAL_PASSTHROUGH_FIELDS = {
    "input_type",
    "output_type",
    "return",
    "transaction",
    "transactions",
    "environment",
    "executable",
    "ambiguity",
    "unresolved_ambiguities",
}

_REQUIRED_TOP_LEVEL_FIELDS = {"module", "workflow", "task", "operations"}
_OPTIONAL_SECTION_FIELDS = {"claims", "evidence", "policies", "holes"}
_INTERNAL_LOADER_FIELDS = {"__source_path__", "__raw_source_sha256__", "__parse_error__", "__duplicate_key_error__", "__complex_key_error__", "__decode_error__", "__load_error__", "__invalid_root__", "__size_error__", "__alias_error__", "__depth_error__", "__resource_error__"}
_ALLOWED_TOP_LEVEL_FIELDS = _REQUIRED_TOP_LEVEL_FIELDS | _OPTIONAL_SECTION_FIELDS | _OPTIONAL_PASSTHROUGH_FIELDS | _INTERNAL_LOADER_FIELDS
_ALLOWED_OPERATION_FIELDS = {"id", "op", "effects", "capabilities", "policies"}
_ALLOWED_CLAIM_FIELDS = {"id", "status", "statement", "evidence"}
_SELF_ATTEST_EVIDENCE_FIELDS = {
    "checked",
    "status",
    "reliability",
    "source",
    "source_ref",
    "producer",
    "producer_kind",
    "generated_by",
    "checked_by",
    "report_ref",
    "artifact_ref",
    "supports",
    "supports_claims",
    "claim_statement_sha256",
}
# These fields are known evidence-assertion fields. They are allowed through the
# strict AST so the Evidence Ledger gate can reject self-attested evidence with
# a semantic Trust finding instead of a shape error. Unknown evidence prose or
# hidden metadata is still refused by S063/S064.
_ALLOWED_EVIDENCE_REF_FIELDS = {"id", "kind"} | _SELF_ATTEST_EVIDENCE_FIELDS
_ALLOWED_EVIDENCE_FIELDS = {"id", "kind"} | _SELF_ATTEST_EVIDENCE_FIELDS
_ALLOWED_POLICY_FIELDS = {"id"}
_ALLOWED_HOLE_FIELDS = {"id", "resolved"}
_ALLOWED_TRANSACTION_FIELDS = {"id", "mode", "kind", "includes", "rollback_on"}
_ALLOWED_UNRESOLVED_AMBIGUITY_FIELDS = {"slot", "question", "candidates", "resolution_required"}


@dataclass(frozen=True)
class OperationAST:
    id: str
    op: str
    effects: tuple[str, ...]
    capabilities: tuple[str, ...] = ()
    policies: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        data = dict(self.raw)
        data["id"] = self.id
        data["op"] = self.op
        data["effects"] = list(self.effects)
        if self.capabilities:
            data["capabilities"] = list(self.capabilities)
        elif "capabilities" in data:
            data["capabilities"] = []
        if self.policies:
            data["policies"] = list(self.policies)
        elif "policies" in data:
            data["policies"] = []
        return data


@dataclass(frozen=True)
class ClaimAST:
    id: str | None
    status: str
    evidence: tuple[Mapping[str, Any], ...]
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        data = dict(self.raw)
        if self.id is not None:
            data["id"] = self.id
        data["status"] = self.status
        if self.evidence:
            data["evidence"] = [dict(e) for e in self.evidence]
        elif "evidence" in data:
            data["evidence"] = []
        return data


@dataclass(frozen=True)
class EvidenceAST:
    id: str | None
    kind: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class PolicyAST:
    id: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class HoleAST:
    id: str | None
    resolved: bool
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        data = dict(self.raw)
        if self.id is not None:
            data["id"] = self.id
        data["resolved"] = self.resolved
        return data


@dataclass(frozen=True)
class DraftAST:
    module: str
    workflow: str
    task: str
    operations: tuple[OperationAST, ...]
    claims: tuple[ClaimAST, ...] = ()
    evidence: tuple[EvidenceAST, ...] = ()
    policies: tuple[PolicyAST, ...] = ()
    holes: tuple[HoleAST, ...] = ()
    passthrough: Mapping[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "module": self.module,
            "workflow": self.workflow,
            "task": self.task,
            "operations": [op.to_raw() for op in self.operations],
        }
        raw.update(dict(self.passthrough))
        if self.claims:
            raw["claims"] = [c.to_raw() for c in self.claims]
        elif "claims" in self.passthrough:
            raw["claims"] = []
        if self.evidence:
            raw["evidence"] = [e.to_raw() for e in self.evidence]
        elif "evidence" in self.passthrough:
            raw["evidence"] = []
        if self.policies:
            raw["policies"] = [p.to_raw() for p in self.policies]
        elif "policies" in self.passthrough:
            raw["policies"] = []
        if self.holes:
            raw["holes"] = [h.to_raw() for h in self.holes]
        elif "holes" in self.passthrough:
            raw["holes"] = []
        return raw

    def to_draft_module(self) -> DraftModule:
        return DraftModule(raw=self.to_raw())


@dataclass(frozen=True)
class DraftParseResult:
    ast: DraftAST | None
    findings: tuple[Finding, ...]

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)


def parse_draft_ast(draft: DraftModule) -> DraftParseResult:
    raw = draft.raw
    findings: list[Finding] = []

    if "__duplicate_key_error__" in raw:
        return DraftParseResult(None, (Finding("S070.yaml_duplicate_key", "critical", "Draft YAML contains duplicate mapping keys; duplicate-key shadowing is forbidden.", "draft"),))
    if "__complex_key_error__" in raw:
        return DraftParseResult(None, (Finding("S071.yaml_complex_mapping_key_forbidden", "critical", "Draft YAML uses a complex/non-scalar mapping key; AiNIR drafts require scalar keys.", "draft"),))
    if "__decode_error__" in raw:
        return DraftParseResult(None, (
            Finding("S000.yaml_decode_error", "critical", "Draft file is not valid UTF-8 YAML text.", "draft"),
            Finding("S072.yaml_utf8_decode_error", "critical", "Draft file is not valid UTF-8 YAML text.", "draft"),
        ))
    if "__alias_error__" in raw:
        return DraftParseResult(None, (Finding("S075.yaml_alias_forbidden", "critical", "Draft YAML aliases/anchors exceed the public-demo safety budget.", "draft"),))
    if "__depth_error__" in raw:
        return DraftParseResult(None, (Finding("S073.yaml_depth_limit_exceeded", "critical", "Draft YAML exceeds the public-demo nesting depth limit.", "draft"),))
    if "__size_error__" in raw:
        return DraftParseResult(None, (Finding("S074.yaml_file_too_large", "critical", "Draft YAML exceeds the public-demo file size limit.", "draft"),))
    if "__resource_error__" in raw:
        return DraftParseResult(None, (Finding("S000.yaml_resource_error", "critical", "Draft YAML could not be safely parsed within resource limits.", "draft"),))
    if "__parse_error__" in raw:
        return DraftParseResult(None, (Finding("S000.yaml_parse_error", "critical", "Draft YAML could not be parsed.", "draft"),))
    if "__load_error__" in raw:
        return DraftParseResult(None, (Finding("S000.draft_load_error", "critical", "Draft file could not be loaded.", "draft"),))
    if "__invalid_root__" in raw:
        return DraftParseResult(None, (Finding("S000.draft_root_must_be_object", "critical", "Draft YAML root must be an object, not a list/string/scalar.", "draft"),))
    if not isinstance(raw, Mapping):
        return DraftParseResult(None, (Finding("S000.draft_root_must_be_object", "critical", "Draft YAML root must be an object.", "draft"),))

    _unknown_field_findings(raw, _ALLOWED_TOP_LEVEL_FIELDS, "draft", "S060.unknown_top_level_field", findings)

    module = _required_id(raw, "module", findings)
    workflow_raw = _required_id(raw, "workflow", findings)
    task = _required_id(raw, "task", findings)

    workflow = workflow_raw
    if workflow_raw:
        workflow, alias = REGISTRY.normalize_workflow(workflow_raw)
        if alias:
            findings.append(Finding("A010.workflow_alias_normalized", "warning", f"Workflow alias {workflow_raw!r} normalized to {workflow!r}.", "workflow"))

    operations = _parse_operations(raw.get("operations"), findings)
    claims = _parse_claims(raw.get("claims", []), findings)
    evidence = _parse_evidence(raw.get("evidence", []), findings)
    policies = _parse_policies(raw.get("policies", []), findings)
    holes = _parse_holes(raw.get("holes", []), findings)

    passthrough = {k: v for k, v in raw.items() if k in _OPTIONAL_PASSTHROUGH_FIELDS}
    _validate_passthrough(passthrough, findings)

    if any(f.severity == "critical" for f in findings):
        return DraftParseResult(None, tuple(findings))
    assert module and workflow and task  # for type narrowing after critical check
    ast = DraftAST(
        module=module,
        workflow=workflow,
        task=task,
        operations=tuple(operations),
        claims=tuple(claims),
        evidence=tuple(evidence),
        policies=tuple(policies),
        holes=tuple(holes),
        passthrough=passthrough,
    )
    return DraftParseResult(ast, tuple(findings))


def _required_id(raw: Mapping[str, Any], field: str, findings: list[Finding]) -> str | None:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip() or value.strip() == "unknown":
        findings.append(Finding("S001.required_identity_field", "critical", f"Draft requires non-empty string field '{field}'.", field))
        return None
    findings.extend(_safe_id_findings(value, field, f"Draft field '{field}'"))
    return value


def _safe_id_findings(value: str, target: str, label: str) -> list[Finding]:
    out: list[Finding] = []
    if value != value.strip():
        out.append(Finding("S002.identity_whitespace_forbidden", "critical", f"{label} has leading or trailing whitespace.", target))
    if not strict_safe_id(value):
        out.append(Finding("S002.unsafe_identity_field", "critical", f"{label} contains unsafe characters.", target))
    return out


def _parse_operations(value: Any, findings: list[Finding]) -> list[OperationAST]:
    operations: list[OperationAST] = []
    if not isinstance(value, list) or not value:
        findings.append(Finding("S003.operations_required", "critical", "Draft must contain at least one operation.", "operations"))
        return operations
    seen: set[str] = set()
    for index, item in enumerate(value):
        target = f"operations[{index}]"
        if not isinstance(item, Mapping):
            findings.append(Finding("S004.operation_must_be_object", "critical", "Operation item must be an object.", target))
            continue
        _unknown_field_findings(item, _ALLOWED_OPERATION_FIELDS, target, "S061.unknown_operation_field", findings)
        op_id = item.get("id")
        op_name = item.get("op")
        if not isinstance(op_id, str) or not op_id.strip():
            findings.append(Finding("S005.operation_id_required", "critical", "Operation requires non-empty string id.", target))
            op_id = None
        else:
            findings.extend(_safe_id_findings(op_id, str(op_id), "Operation id"))
            if op_id in seen:
                findings.append(Finding("S007.operation_id_unique", "critical", "Duplicate operation id.", op_id))
            seen.add(op_id)
        if not isinstance(op_name, str) or not op_name.strip():
            findings.append(Finding("S008.operation_op_required", "critical", "Operation requires non-empty string op.", str(op_id or target)))
            op_name = None
        else:
            findings.extend(_safe_id_findings(op_name, str(op_id or target), "Canonical operation name"))
        effects = _parse_id_list(item.get("effects", None), str(op_id or target), "effect", "S012", findings, required=True)
        capabilities = _parse_id_list(item.get("capabilities", []), str(op_id or target), "capability", "S016", findings, required=False)
        policies = _parse_id_list(item.get("policies", []), str(op_id or target), "policy", "S021", findings, required=False)
        if isinstance(op_id, str) and isinstance(op_name, str):
            operations.append(OperationAST(op_id, op_name, tuple(effects), tuple(capabilities), tuple(policies), raw=item))
    return operations


def _parse_id_list(value: Any, target: str, label: str, prefix: str, findings: list[Finding], *, required: bool) -> list[str]:
    if value is None:
        if required:
            findings.append(Finding("S010.effects_required", "critical", "Operation must explicitly declare effects; use [] for pure.", target))
        return []
    if not isinstance(value, list):
        rule = "S011.effects_must_be_list" if label == "effect" else f"{prefix}.{label}s_must_be_list"
        findings.append(Finding(rule, "critical", f"Operation {label}s must be a list.", target))
        return []
    out: list[str] = []
    for index, item in enumerate(value):
        item_target = f"{target}.{label}s[{index}]"
        if not isinstance(item, str) or not item.strip():
            findings.append(Finding(f"{prefix}.{label}_id_required", "critical", f"{label.capitalize()} id must be a non-empty string.", item_target))
            continue
        if item != item.strip():
            findings.append(Finding(f"{prefix}.{label}_id_whitespace_forbidden", "critical", f"{label.capitalize()} id has leading or trailing whitespace.", item_target))
        if not strict_safe_id(item):
            findings.append(Finding(f"{prefix}.{label}_id_unsafe", "critical", f"{label.capitalize()} id contains unsafe characters.", item_target))
        out.append(item)
    return out


def _parse_claims(value: Any, findings: list[Finding]) -> list[ClaimAST]:
    items = _object_list(value, "claims", findings)
    out: list[ClaimAST] = []
    for index, item in enumerate(items):
        target = f"claims[{index}]"
        _unknown_field_findings(item, _ALLOWED_CLAIM_FIELDS, target, "S062.unknown_claim_field", findings)
        cid = _optional_id(item, target, findings)
        status = item.get("status", "hypothesized")
        if not isinstance(status, str) or status not in _SAFE_STATUS_VALUES:
            findings.append(Finding("S040.claim_status_invalid", "critical", "Claim status is not allowed in the public demo.", target))
            status = "hypothesized"
        evidence_value = item.get("evidence", [])
        evidence: list[Mapping[str, Any]] = []
        if evidence_value is None:
            evidence_value = []
        if not isinstance(evidence_value, list):
            findings.append(Finding("S041.claim_evidence_must_be_list", "critical", "Claim evidence must be a list if present.", target))
        else:
            for ev_index, ev in enumerate(evidence_value):
                if not isinstance(ev, Mapping):
                    findings.append(Finding("S042.claim_evidence_item_must_be_object", "critical", "Claim evidence items must be objects.", f"{target}.evidence[{ev_index}]"))
                    continue
                ev_target = f"{target}.evidence[{ev_index}]"
                _unknown_field_findings(ev, _ALLOWED_EVIDENCE_REF_FIELDS, ev_target, "S063.unknown_claim_evidence_field", findings)
                ev_id = ev.get("id")
                if ev_id is not None:
                    findings.extend(_safe_id_findings(str(ev_id) if isinstance(ev_id, str) else "", f"{target}.evidence[{ev_index}]", "evidence id")) if isinstance(ev_id, str) else findings.append(Finding("S032.evidence_id_must_be_string", "critical", "evidence id must be a non-empty string if present.", f"{target}.evidence[{ev_index}]"))
                evidence.append(ev)
        out.append(ClaimAST(cid, status, tuple(evidence), raw=item))
    return out


def _parse_evidence(value: Any, findings: list[Finding]) -> list[EvidenceAST]:
    items = _object_list(value, "evidence", findings)
    out: list[EvidenceAST] = []
    for index, item in enumerate(items):
        target = f"evidence[{index}]"
        _unknown_field_findings(item, _ALLOWED_EVIDENCE_FIELDS, target, "S064.unknown_evidence_field", findings)
        eid = _optional_id(item, target, findings)
        kind = item.get("kind")
        if kind is not None and (not isinstance(kind, str) or not kind.strip()):
            findings.append(Finding("S060.evidence_kind_must_be_string", "critical", "Evidence kind must be a non-empty string if present.", target))
            kind = None
        out.append(EvidenceAST(eid, kind, raw=item))
    return out


def _parse_policies(value: Any, findings: list[Finding]) -> list[PolicyAST]:
    out: list[PolicyAST] = []
    for i, item in enumerate(_object_list(value, "policies", findings)):
        target = f"policies[{i}]"
        _unknown_field_findings(item, _ALLOWED_POLICY_FIELDS, target, "S065.unknown_policy_field", findings)
        out.append(PolicyAST(_optional_id(item, target, findings), raw=item))
    return out


def _parse_holes(value: Any, findings: list[Finding]) -> list[HoleAST]:
    out: list[HoleAST] = []
    for i, item in enumerate(_object_list(value, "holes", findings)):
        target = f"holes[{i}]"
        _unknown_field_findings(item, _ALLOWED_HOLE_FIELDS, target, "S066.unknown_hole_field", findings)
        hid = _optional_id(item, target, findings)
        resolved = item.get("resolved", False)
        if not isinstance(resolved, bool):
            findings.append(Finding("S050.hole_resolved_must_be_boolean", "critical", "Hole resolved field must be boolean if present.", target))
            resolved = False
        out.append(HoleAST(hid, resolved, raw=item))
    return out


def _object_list(value: Any, section: str, findings: list[Finding]) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        findings.append(Finding(f"S030.{section}_must_be_list", "critical", f"Section '{section}' must be a list if present.", section))
        return []
    out: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            findings.append(Finding("S017.section_item_must_be_object", "critical", f"Items in '{section}' must be objects, not prose/scalars.", f"{section}[{index}]"))
            continue
        out.append(item)
    return out


def _unknown_field_findings(item: Mapping[str, Any], allowed: set[str], target: str, rule: str, findings: list[Finding]) -> None:
    unknown = sorted(k for k in item.keys() if k not in allowed)
    for field in unknown:
        findings.append(
            Finding(
                rule,
                "critical",
                f"Unknown field {field!r} is not part of the strict public-demo draft contract.",
                f"{target}.{field}" if target else str(field),
                suggestion="Represent extra semantics through a registered operation, claim, policy, evidence reference, or consumer profile contract instead of hidden free-form fields.",
            )
        )


def _optional_id(item: Mapping[str, Any], target: str, findings: list[Finding]) -> str | None:
    item_id = item.get("id")
    if item_id is None:
        return None
    if not isinstance(item_id, str) or not item_id.strip():
        findings.append(Finding("S032.section_id_must_be_string", "critical", "Section id must be a non-empty string if present.", target))
        return None
    findings.extend(_safe_id_findings(item_id, target, "section id"))
    return item_id


def _validate_passthrough(passthrough: Mapping[str, Any], findings: list[Finding]) -> None:
    if "executable" in passthrough and not isinstance(passthrough["executable"], bool):
        findings.append(Finding("S015.executable_must_be_boolean", "critical", "Draft field 'executable' must be true or false.", "executable"))
    for field in ("input_type", "output_type", "return", "environment"):
        value = passthrough.get(field)
        if value is not None and not isinstance(value, str):
            findings.append(Finding(f"S070.{field}_must_be_string", "critical", f"Optional field '{field}' must be a string if present.", field))

    transaction = passthrough.get("transaction")
    if transaction is not None:
        if not isinstance(transaction, Mapping):
            findings.append(Finding("S067.transaction_must_be_object", "critical", "Optional field 'transaction' must be an object if present.", "transaction"))
        else:
            _unknown_field_findings(transaction, _ALLOWED_TRANSACTION_FIELDS, "transaction", "S067.unknown_transaction_field", findings)

    transactions = passthrough.get("transactions")
    if transactions is not None:
        if not isinstance(transactions, list):
            findings.append(Finding("S068.transactions_must_be_list", "critical", "Optional field 'transactions' must be a list if present.", "transactions"))
        else:
            for index, tx in enumerate(transactions):
                target = f"transactions[{index}]"
                if not isinstance(tx, Mapping):
                    findings.append(Finding("S068.transaction_item_must_be_object", "critical", "Each transactions[] item must be an object.", target))
                else:
                    _unknown_field_findings(tx, _ALLOWED_TRANSACTION_FIELDS, target, "S068.unknown_transactions_field", findings)

    ambiguity = passthrough.get("ambiguity")
    if ambiguity is not None:
        if not isinstance(ambiguity, Mapping):
            findings.append(Finding("S071.ambiguity_must_be_object", "critical", "Optional field 'ambiguity' must be an object if present.", "ambiguity"))
        else:
            allowed = {"status", "unresolved_ambiguities"}
            _unknown_field_findings(ambiguity, allowed, "ambiguity", "S072.unknown_ambiguity_field", findings)
            status = ambiguity.get("status")
            unresolved = ambiguity.get("unresolved_ambiguities", [])
            if status is not None and status not in {"resolved", "requires_clarification", "blocked"}:
                findings.append(Finding("S073.ambiguity_status_invalid", "critical", "Ambiguity status must be resolved, requires_clarification, or blocked.", "ambiguity.status"))
            if not isinstance(unresolved, list):
                findings.append(Finding("S074.unresolved_ambiguities_must_be_list", "critical", "unresolved_ambiguities must be a list if present.", "ambiguity.unresolved_ambiguities"))
            else:
                _validate_unresolved_ambiguity_items(unresolved, "ambiguity.unresolved_ambiguities", findings)
    unresolved = passthrough.get("unresolved_ambiguities")
    if unresolved is not None:
        if not isinstance(unresolved, list):
            findings.append(Finding("S074.unresolved_ambiguities_must_be_list", "critical", "unresolved_ambiguities must be a list if present.", "unresolved_ambiguities"))
        else:
            _validate_unresolved_ambiguity_items(unresolved, "unresolved_ambiguities", findings)


def _validate_unresolved_ambiguity_items(value: list[Any], target: str, findings: list[Finding]) -> None:
    for index, item in enumerate(value):
        item_target = f"{target}[{index}]"
        if not isinstance(item, Mapping):
            findings.append(Finding("S075.unresolved_ambiguity_item_must_be_object", "critical", "Each unresolved ambiguity must be an object.", item_target))
            continue
        _unknown_field_findings(item, _ALLOWED_UNRESOLVED_AMBIGUITY_FIELDS, item_target, "S076.unknown_unresolved_ambiguity_field", findings)
        slot = item.get("slot")
        if slot is not None and (not isinstance(slot, str) or not slot.strip()):
            findings.append(Finding("S077.unresolved_ambiguity_slot_must_be_string", "critical", "unresolved ambiguity slot must be a non-empty string if present.", f"{item_target}.slot"))
        question = item.get("question")
        if question is not None and not isinstance(question, str):
            findings.append(Finding("S078.unresolved_ambiguity_question_must_be_string", "critical", "unresolved ambiguity question must be a string if present.", f"{item_target}.question"))
        candidates = item.get("candidates")
        if candidates is not None and (not isinstance(candidates, list) or any(not isinstance(x, str) for x in candidates)):
            findings.append(Finding("S079.unresolved_ambiguity_candidates_must_be_strings", "critical", "unresolved ambiguity candidates must be a list of strings if present.", f"{item_target}.candidates"))
        resolution_required = item.get("resolution_required")
        if resolution_required is not None and not isinstance(resolution_required, bool):
            findings.append(Finding("S080.unresolved_ambiguity_resolution_required_must_be_boolean", "critical", "unresolved ambiguity resolution_required must be boolean if present.", f"{item_target}.resolution_required"))
