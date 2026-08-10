"""Verified intent export surface for optional external consumer profiles.

Pre-v1 Phase 25 tightens the VerifiedIntentPacket contract so the export
surface cannot become looser than the AiNIR Trust Gate. The packet is still an
AiNIR-owned optional future-consumer artifact; it does not call, import, or
integrate any downstream compiler/runtime.

Boundary:
- AiNIR may export a verified semantic-intent packet.
- AiNIR does not perform downstream schema grounding in this public demo.
- Concrete source/filter/projection grounding remains a future consumer
  obligation unless a verified AiNIR grounding subsystem exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .core import DraftModule, load_draft
from .execution_context import TrustedExecutionContext
from .trust_gate import evaluate_trust_gate
from .operation_registry import get_operation_registry
from .evidence_ledger import get_evidence_ledger

_PACKET_VERSION = "pre_v1_phase25_defensive_integrity_packet_integrity"
_PROFILE_AIVL = "AIVLConsumerProfile"
_SUPPORTED_PROFILE_WORKFLOWS = {
    _PROFILE_AIVL: {"PIIExportRequest"},
}

_AIVL_REQUIRED_SLOTS = {
    "trust",
    "profile_scope",
    "evidence_bindings",
    "effects",
    "capabilities",
    "intent",
    "grounding_status",
    "groundings",
    "ambiguity",
    "operation_constraints",
    "required_contracts",
    "security_classifications",
    "receipt_links",
}
_TOP_LEVEL_ALLOWED = {"kind", "version", "packet_id", "producer", "consumer_profile", "profile_status", "slots"}
_TRUST_ALLOWED = {"status", "decision", "blocked_reasons", "trust_gate_status", "lowering_allowed", "handoff_allowed"}
_PROFILE_SCOPE_ALLOWED = {"profile", "supported_workflow", "workflow", "task", "task_family"}
_EVIDENCE_BINDING_ALLOWED = {"claim", "evidence_id", "issuer", "status", "ledger_bound"}
_EFFECTS_ALLOWED_KEYS = {"consumer_allowed", "consumer_required", "consumer_denied", "ainir_declared", "ainir_implied"}
_CAPABILITIES_ALLOWED_KEYS = {"consumer_allowed", "consumer_denied", "ainir_declared", "ainir_implied"}
_INTENT_ALLOWED_KEYS = {"task_intent", "domain", "operation_kind", "natural_language_summary"}
_GROUNDING_STATUS_ALLOWED_KEYS = {"status", "reason", "required_consumer_checks"}
_AMBIGUITY_ALLOWED_KEYS = {"status", "unresolved_ambiguities"}
_OPERATION_CONSTRAINTS_ALLOWED_KEYS = {"allowed_operations", "denied_operations", "requires_human_review", "semantic_roles", "canonical_operations"}
_SECURITY_CLASSIFICATION_ALLOWED_KEYS = {"classification_scope", "classification", "source", "status", "field_path"}
_RECEIPT_LINKS_ALLOWED_KEYS = {
    "ainir_receipt_id",
    "draft_hash",
    "raw_source_sha256",
    "canonical_draft_sha256",
    "registry_hash",
    "registry_snapshot_hash",
    "verifier_report_hash",
    "policy_hash",
    "stable_receipt_projection_hash",
    "gate_results_hash",
    "evidence_summary_hash",
    "trusted_context",
}
_RECEIPT_LINKS_REQUIRED_KEYS = set(_RECEIPT_LINKS_ALLOWED_KEYS)
_CANONICAL_OPERATION_ALLOWED_KEYS = {"operation_id", "canonical_op", "semantic_roles", "effects", "capabilities"}

_PII_EXPORT_REQUIRED_CONTRACTS = {
    "schema_grounding_required",
    "filter_matches",
    "projection_matches",
    "pii_export_authorized",
    "field_allowlist",
    "encrypted_export_package",
    "pii_export_boundary_declared",
}
_PII_EXPORT_ALLOWED_CONTRACTS = set(_PII_EXPORT_REQUIRED_CONTRACTS)
_PII_EXPORT_REQUIRED_CONSUMER_EFFECTS = {"PIIExport", "PIIRead"}
_PII_EXPORT_ALLOWED_CONSUMER_EFFECTS = {"AuthorizationCheck", "Encrypt", "PIIExport", "PIIRead", "WriteExportPackage"}
_PII_EXPORT_DENIED_CONSUMER_EFFECTS = {"NetworkAccess", "WriteDatabase", "SecretAccess", "PaymentCharge", "AccountDelete"}
_PII_EXPORT_REQUIRED_CONSUMER_CAPABILITIES = {"PIIExport", "PIIRead"}
_PII_EXPORT_ALLOWED_CONSUMER_CAPABILITIES = {"AuthorizationCheck", "Encrypt", "PIIExport", "PIIRead", "WriteExportPackage"}
_PII_EXPORT_DENIED_CONSUMER_CAPABILITIES = set(_PII_EXPORT_DENIED_CONSUMER_EFFECTS)
_PII_EXPORT_ALLOWED_TASK_INTENTS = {"prepare_authorized_pii_export_package"}
_PII_EXPORT_ALLOWED_DOMAINS = {"privacy_export"}
_PII_EXPORT_ALLOWED_OPERATION_KINDS = {"data_pipeline"}
_PII_EXPORT_ALLOWED_CONSUMER_OPERATIONS = {
    "authorization_check",
    "field_allowlist_check",
    "read_pii_fields",
    "encrypt_export_package",
    "store_export_package",
}
_PII_EXPORT_REQUIRED_CONSUMER_OPERATIONS = set(_PII_EXPORT_ALLOWED_CONSUMER_OPERATIONS)
_PII_EXPORT_DENIED_CONSUMER_OPERATIONS = {"delete", "update", "external_network_send", "production_financial_effect"}
_PII_EXPORT_ALLOWED_SEMANTIC_ROLES = {
    "authorization",
    "pii_read",
    "export_allowlist",
    "export_encryption",
    "export_package_storage",
    "encrypted_or_safe_export",
}
_PII_EXPORT_REQUIRED_SEMANTIC_ROLES = set(_PII_EXPORT_ALLOWED_SEMANTIC_ROLES)

_DENIED_CONSUMER_EFFECTS_DEFAULT = sorted(_PII_EXPORT_DENIED_CONSUMER_EFFECTS)
_DENIED_CONSUMER_CAPABILITIES_DEFAULT = sorted(_PII_EXPORT_DENIED_CONSUMER_CAPABILITIES)

_EFFECT_TO_CONSUMER = {
    "effect.storage.db.read": "ReadDatabase",
    "effect.storage.db.write": "WriteDatabase",
    "effect.privacy.pii.read": "PIIRead",
    "effect.privacy.pii.export": "PIIExport",
    "effect.crypto.encrypt": "Encrypt",
    "effect.storage.export_package.write": "WriteExportPackage",
    "effect.external.network.call": "NetworkAccess",
    "effect.external.payment.charge.real": "PaymentCharge",
    "effect.destructive.account.hard_delete": "AccountDelete",
    "effect.auth.authorization.check": "AuthorizationCheck",
}

_CAPABILITY_TO_CONSUMER = {
    "cap.db.read": "ReadDatabase",
    "cap.db.user.read": "ReadDatabase",
    "cap.pii.read": "PIIRead",
    "cap.pii.export": "PIIExport",
    "cap.auth.check": "AuthorizationCheck",
    "cap.crypto.encrypt": "Encrypt",
    "cap.export.storage.write": "WriteExportPackage",
    "cap.outbox.write": "WriteOutbox",
    "cap.db.write": "WriteDatabase",
    "cap.db.user.write": "WriteDatabase",
}

_ROLE_TO_OPERATION = {
    "authorization": "authorization_check",
    "pii_read": "read_pii_fields",
    "export_allowlist": "field_allowlist_check",
    "export_encryption": "encrypt_export_package",
    "export_package_storage": "store_export_package",
}

_RAW_SLOT_FIELDS = {
    "intent",
    "groundings",
    "field_classifications",
}

_CLASSIFICATION_ENUM = {"PII", "Identifier", "Secret", "PublicText", "Internal"}
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PACKET_ID_RE = re.compile(r"^ainir\.verified_intent\.[a-f0-9]{20}$|^ainir\.verified_intent\.fixture\.[A-Za-z0-9_.-]+$")
_RECEIPT_ID_RE = re.compile(r"^ainir\.trust\.receipt\.(?:[a-f0-9]{20}|fixture(?:\.[A-Za-z0-9_.:-]+)?|example\.[A-Za-z0-9_.:-]+)$")


@dataclass(frozen=True)
class VerifiedIntentExportResult:
    status: str
    packet: dict[str, Any] | None
    reasons: tuple[str, ...]
    decision: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "packet": self.packet,
            "reasons": list(self.reasons),
            "decision": self.decision,
            "receipt": self.receipt,
        }


def export_verified_intent_packet(
    draft: DraftModule,
    context: TrustedExecutionContext | None = None,
    consumer_profile: str = _PROFILE_AIVL,
) -> VerifiedIntentExportResult:
    """Export a VerifiedIntentPacket for a future external consumer profile.

    This is an AiNIR-owned export surface. It does not invoke or depend on any
    downstream compiler/runtime. A failed/held/invalid Trust Gate decision never
    exports a verified packet.
    """
    if context is None:
        context = TrustedExecutionContext.from_environment("public_demo", source="default", purpose="verified_intent_export")
    elif context.purpose != "verified_intent_export":
        context = TrustedExecutionContext.from_environment(context.environment, source=context.source, purpose="verified_intent_export")
    profile = _normalize_profile(consumer_profile)
    if profile != _PROFILE_AIVL:
        return VerifiedIntentExportResult("refused", None, ("unsupported_consumer_profile",))

    pre_errors = _pre_export_profile_errors(draft, profile)
    if pre_errors:
        return VerifiedIntentExportResult("refused", None, tuple(pre_errors))

    decision = evaluate_trust_gate(draft, context).as_dict()
    if decision.get("status") != "passed":
        return VerifiedIntentExportResult("refused", None, ("trust_gate_not_passed",))
    if not decision.get("handoff_allowed"):
        return VerifiedIntentExportResult("refused", None, ("handoff_not_allowed",))

    if draft.workflow == "PIIExportRequest" and not _has_verified_authorization_evidence(draft):
        return VerifiedIntentExportResult("refused", None, ("profile_requires_verified_authorization_evidence",))

    packet = _build_packet(draft, context, decision, profile)
    packet_hash = _canonical_verified_intent_packet_hash(packet)
    # Bind the handoff payload to the exact TrustReceipt sidecar.  The packet
    # cannot safely carry a self-hash as part of its own canonical payload, so
    # the matching receipt/decision bundle carries the packet hash.
    decision = dict(decision)
    receipt = dict(decision.get("receipt", {})) if isinstance(decision.get("receipt"), Mapping) else {}
    if receipt:
        receipt["verified_intent_packet_canonical_sha256"] = packet_hash
        receipt["verified_intent_packet_hash_algorithm"] = "canonical_json_sha256"
        # The packet hash is part of the receipt stable projection for VerifiedIntent
        # bundles. Recompute after attaching it so replay cannot accept a
        # packet/receipt/manifest set that merely updates all mutable sidecars.
        from .trust_receipt_store import stable_receipt_projection_hash
        receipt["stable_receipt_projection_hash"] = stable_receipt_projection_hash(receipt)
        packet_links = packet.get("slots", {}).get("receipt_links", {}) if isinstance(packet.get("slots"), Mapping) else {}
        if isinstance(packet_links, dict):
            packet_links["stable_receipt_projection_hash"] = receipt["stable_receipt_projection_hash"]
        decision["receipt"] = receipt
    validation_errors = validate_verified_intent_packet(packet)
    if validation_errors:
        return VerifiedIntentExportResult("refused", None, tuple("packet_validation:" + e for e in validation_errors))
    return VerifiedIntentExportResult("exported", packet, (), dict(decision), receipt)


def export_verified_intent_packet_from_path(path: str | Path, env: str = "public_demo", consumer_profile: str = _PROFILE_AIVL) -> VerifiedIntentExportResult:
    context = TrustedExecutionContext.from_environment(env, source="cli", purpose="verified_intent_export")
    return export_verified_intent_packet(load_draft(path), context, consumer_profile)


def _canonical_json_hash(value: Any) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _canonical_verified_intent_packet_payload(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return the packet payload used for tamper-evident hashing.

    VerifiedIntentPacket includes receipt_links.stable_receipt_projection_hash,
    while the receipt stable projection includes the packet hash. To avoid an
    impossible hash cycle, the packet hash normalizes that one back-reference.
    The field itself is still validated separately during handoff/replay.
    """
    payload = json.loads(json.dumps(packet, sort_keys=True, ensure_ascii=False))
    try:
        links = payload["slots"]["receipt_links"]
        if isinstance(links, dict) and "stable_receipt_projection_hash" in links:
            links["stable_receipt_projection_hash"] = "sha256:" + ("0" * 64)
    except Exception:
        pass
    return payload


def _canonical_verified_intent_packet_hash(packet: Mapping[str, Any]) -> str:
    return _canonical_json_hash(_canonical_verified_intent_packet_payload(packet))


def canonical_verified_intent_packet_hash(packet: Mapping[str, Any]) -> str:
    """Return the supported canonical hash for a VerifiedIntentPacket."""

    return _canonical_verified_intent_packet_hash(packet)


def validate_verified_intent_packet(packet: Mapping[str, Any]) -> list[str]:
    """Validate the public-demo VerifiedIntentPacket contract.

    The custom validator intentionally mirrors and extends the JSON schema so a
    runtime consumer does not need to trust the schema file alone.
    """
    errors: list[str] = []
    if not isinstance(packet, Mapping):
        return ["packet must be an object"]
    _check_unknown_keys(errors, packet, _TOP_LEVEL_ALLOWED, "packet")

    required_top = {"kind", "version", "packet_id", "producer", "consumer_profile", "profile_status", "slots"}
    _check_required(errors, packet, required_top, "packet")
    if packet.get("kind") != "VerifiedIntentPacket":
        errors.append("kind must be VerifiedIntentPacket")
    if packet.get("version") != _PACKET_VERSION:
        errors.append(f"version must be {_PACKET_VERSION}")
    if not _PACKET_ID_RE.match(str(packet.get("packet_id", ""))):
        errors.append("packet_id must be an AiNIR VerifiedIntentPacket id")
    if packet.get("producer") != "AiNIR":
        errors.append("producer must be AiNIR")
    if packet.get("profile_status") != "consumer_profile_contract_only_no_downstream_integration":
        errors.append("profile_status must be consumer_profile_contract_only_no_downstream_integration")
    profile = str(packet.get("consumer_profile", ""))
    if profile != _PROFILE_AIVL:
        errors.append("consumer_profile must be AIVLConsumerProfile for this public demo profile")

    slots = packet.get("slots")
    if not isinstance(slots, Mapping):
        errors.append("slots must be an object")
        return errors
    _check_unknown_keys(errors, slots, _AIVL_REQUIRED_SLOTS, "slots")
    _check_required(errors, slots, _AIVL_REQUIRED_SLOTS, "slots")

    _validate_trust_slot(errors, slots.get("trust"))
    workflow, task_family = _validate_profile_scope_slot(errors, slots.get("profile_scope"), profile)
    _validate_evidence_bindings_slot(errors, slots.get("evidence_bindings"), workflow)
    _validate_effects_slot(errors, slots.get("effects"), workflow)
    _validate_capabilities_slot(errors, slots.get("capabilities"), workflow)
    _validate_intent_slot(errors, slots.get("intent"), workflow)
    _validate_grounding_status_slot(errors, slots.get("grounding_status"))
    _validate_groundings_slot(errors, slots.get("groundings"))
    _validate_ambiguity_slot(errors, slots.get("ambiguity"))
    _validate_operation_constraints_slot(errors, slots.get("operation_constraints"), workflow)
    _validate_required_contracts_slot(errors, slots.get("required_contracts"), workflow)
    _validate_security_classifications_slot(errors, slots.get("security_classifications"), workflow)
    _validate_receipt_links_slot(errors, slots.get("receipt_links"))
    return errors


def _validate_trust_slot(errors: list[str], value: Any) -> None:
    if not isinstance(value, Mapping):
        errors.append("trust slot must be an object")
        return
    _check_unknown_keys(errors, value, _TRUST_ALLOWED, "trust")
    _check_required(errors, value, {"status", "decision", "blocked_reasons", "trust_gate_status", "lowering_allowed", "handoff_allowed"}, "trust")
    if value.get("status") != "verified" or value.get("decision") != "allow":
        errors.append("trust slot must be verified/allow for exported packets")
    if value.get("trust_gate_status") != "passed":
        errors.append("trust.trust_gate_status must be passed")
    if value.get("lowering_allowed") is not True or value.get("handoff_allowed") is not True:
        errors.append("trust.lowering_allowed and trust.handoff_allowed must both be true")
    if not isinstance(value.get("blocked_reasons"), list) or value.get("blocked_reasons"):
        errors.append("trust.blocked_reasons must be an empty list for exported packets")


def _validate_profile_scope_slot(errors: list[str], value: Any, profile: str) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        errors.append("profile_scope slot must be an object")
        return "", ""
    _check_unknown_keys(errors, value, _PROFILE_SCOPE_ALLOWED, "profile_scope")
    _check_required(errors, value, {"profile", "supported_workflow", "workflow", "task", "task_family"}, "profile_scope")
    workflow = str(value.get("workflow", ""))
    task_family = str(value.get("task_family", ""))
    if value.get("profile") != _PROFILE_AIVL:
        errors.append("profile_scope.profile must be AIVLConsumerProfile")
    if value.get("supported_workflow") is not True:
        errors.append("profile_scope.supported_workflow must be true")
    if workflow not in _SUPPORTED_PROFILE_WORKFLOWS.get(profile, set()):
        errors.append(f"consumer profile {profile} does not support workflow {workflow!r}")
    if workflow == "PIIExportRequest" and task_family != "pii_export_pipeline":
        errors.append("PIIExportRequest requires profile_scope.task_family=pii_export_pipeline")
    if not isinstance(value.get("task"), str) or not value.get("task"):
        errors.append("profile_scope.task must be a non-empty string")
    return workflow, task_family


def _validate_evidence_bindings_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, list):
        errors.append("evidence_bindings must be a list")
        return
    if workflow == "PIIExportRequest" and not value:
        errors.append("PIIExportRequest requires at least one evidence binding")
    for idx, ev in enumerate(value):
        if not isinstance(ev, Mapping):
            errors.append(f"evidence_bindings[{idx}] must be an object")
            continue
        _check_unknown_keys(errors, ev, _EVIDENCE_BINDING_ALLOWED, f"evidence_bindings[{idx}]")
        _check_required(errors, ev, _EVIDENCE_BINDING_ALLOWED, f"evidence_bindings[{idx}]")
        if ev.get("claim") not in {"claim.pii_export_authorized", "claim.export_authorized"}:
            errors.append(f"evidence_bindings[{idx}].claim is not a supported verified export claim")
        if not isinstance(ev.get("evidence_id"), str) or not ev.get("evidence_id"):
            errors.append(f"evidence_bindings[{idx}].evidence_id must be a non-empty string")
        else:
            try:
                eid = str(ev.get("evidence_id"))
                if eid not in get_evidence_ledger().records and not eid.startswith("evidence.fixture."):
                    errors.append(f"evidence_bindings[{idx}].evidence_id is not present in the evidence ledger")
            except Exception as exc:
                errors.append(f"evidence_bindings[{idx}].evidence ledger could not be checked: {type(exc).__name__}")
        if ev.get("issuer") != "ainir_evidence_ledger":
            errors.append(f"evidence_bindings[{idx}].issuer must be ainir_evidence_ledger")
        if ev.get("status") != "verified" or ev.get("ledger_bound") is not True:
            errors.append(f"evidence_bindings[{idx}] must be verified and ledger_bound")
    if workflow == "PIIExportRequest" and value:
        if not any(isinstance(ev, Mapping) and ev.get("claim") == "claim.pii_export_authorized" and ev.get("status") == "verified" and ev.get("ledger_bound") is True for ev in value):
            errors.append("PIIExportRequest requires ledger-bound verified pii_export_authorized evidence")


def _validate_effects_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, Mapping):
        errors.append("effects slot must be an object")
        return
    _check_unknown_keys(errors, value, _EFFECTS_ALLOWED_KEYS, "effects")
    _check_required(errors, value, _EFFECTS_ALLOWED_KEYS, "effects")
    for field in _EFFECTS_ALLOWED_KEYS:
        _check_list_of_strings(errors, value.get(field), f"effects.{field}", allow_empty=field in {"ainir_implied"})
    allowed = set(value.get("consumer_allowed", []) if isinstance(value.get("consumer_allowed"), list) else [])
    required = set(value.get("consumer_required", []) if isinstance(value.get("consumer_required"), list) else [])
    denied = set(value.get("consumer_denied", []) if isinstance(value.get("consumer_denied"), list) else [])
    _check_disjoint(errors, list(allowed), list(denied), "effects consumer_allowed/consumer_denied")
    if workflow == "PIIExportRequest":
        if not required <= allowed:
            errors.append("effects.consumer_required must be a subset of effects.consumer_allowed")
        _check_subset(errors, allowed, _PII_EXPORT_ALLOWED_CONSUMER_EFFECTS, "effects.consumer_allowed")
        _check_subset(errors, required, _PII_EXPORT_ALLOWED_CONSUMER_EFFECTS, "effects.consumer_required")
        _check_subset(errors, denied, _PII_EXPORT_DENIED_CONSUMER_EFFECTS, "effects.consumer_denied")
        missing_allowed = sorted(_PII_EXPORT_REQUIRED_CONSUMER_EFFECTS - allowed)
        if missing_allowed:
            errors.append("PIIExportRequest missing required consumer_allowed effects: " + ", ".join(missing_allowed))
        if "PIIExport" not in required:
            errors.append("PIIExportRequest requires effects.consumer_required to include PIIExport")
        if denied != _PII_EXPORT_DENIED_CONSUMER_EFFECTS:
            errors.append("effects.consumer_denied must match the PIIExportRequest denied-effect set")


def _validate_capabilities_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, Mapping):
        errors.append("capabilities slot must be an object")
        return
    _check_unknown_keys(errors, value, _CAPABILITIES_ALLOWED_KEYS, "capabilities")
    _check_required(errors, value, _CAPABILITIES_ALLOWED_KEYS, "capabilities")
    for field in _CAPABILITIES_ALLOWED_KEYS:
        _check_list_of_strings(errors, value.get(field), f"capabilities.{field}", allow_empty=field == "ainir_implied")
    allowed = set(value.get("consumer_allowed", []) if isinstance(value.get("consumer_allowed"), list) else [])
    denied = set(value.get("consumer_denied", []) if isinstance(value.get("consumer_denied"), list) else [])
    _check_disjoint(errors, list(allowed), list(denied), "capabilities consumer_allowed/consumer_denied")
    if workflow == "PIIExportRequest":
        _check_subset(errors, allowed, _PII_EXPORT_ALLOWED_CONSUMER_CAPABILITIES, "capabilities.consumer_allowed")
        _check_subset(errors, denied, _PII_EXPORT_DENIED_CONSUMER_CAPABILITIES, "capabilities.consumer_denied")
        missing_allowed = sorted(_PII_EXPORT_REQUIRED_CONSUMER_CAPABILITIES - allowed)
        if missing_allowed:
            errors.append("PIIExportRequest missing required consumer_allowed capabilities: " + ", ".join(missing_allowed))
        if denied != _PII_EXPORT_DENIED_CONSUMER_CAPABILITIES:
            errors.append("capabilities.consumer_denied must match the PIIExportRequest denied-capability set")


def _validate_intent_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, Mapping):
        errors.append("intent slot must be an object")
        return
    _check_unknown_keys(errors, value, _INTENT_ALLOWED_KEYS, "intent")
    _check_required(errors, value, _INTENT_ALLOWED_KEYS, "intent")
    if workflow == "PIIExportRequest":
        if value.get("task_intent") not in _PII_EXPORT_ALLOWED_TASK_INTENTS:
            errors.append("PIIExportRequest intent.task_intent is outside the profile allowlist")
        if value.get("domain") not in _PII_EXPORT_ALLOWED_DOMAINS:
            errors.append("PIIExportRequest intent.domain is outside the profile allowlist")
        if value.get("operation_kind") not in _PII_EXPORT_ALLOWED_OPERATION_KINDS:
            errors.append("PIIExportRequest intent.operation_kind is outside the profile allowlist")
    if not isinstance(value.get("natural_language_summary"), str) or not value.get("natural_language_summary"):
        errors.append("intent.natural_language_summary must be a non-empty string")


def _validate_grounding_status_slot(errors: list[str], value: Any) -> None:
    if not isinstance(value, Mapping):
        errors.append("grounding_status slot must be an object")
        return
    _check_unknown_keys(errors, value, _GROUNDING_STATUS_ALLOWED_KEYS, "grounding_status")
    _check_required(errors, value, {"status", "reason", "required_consumer_checks"}, "grounding_status")
    if value.get("status") != "consumer_must_ground":
        errors.append("grounding_status.status must be consumer_must_ground in this public demo")
    req = value.get("required_consumer_checks", [])
    if not isinstance(req, list) or not all(isinstance(x, str) and x for x in req):
        errors.append("grounding_status.required_consumer_checks must be a non-empty-string list")
        return
    required = {"schema_grounding_required", "filter_matches", "projection_matches", "field_allowlist"}
    missing = sorted(required - set(req))
    if missing:
        errors.append("grounding_status.required_consumer_checks missing: " + ", ".join(missing))


def _validate_groundings_slot(errors: list[str], value: Any) -> None:
    if not isinstance(value, list):
        errors.append("groundings slot must be a list")
    elif value:
        errors.append("groundings must be empty unless AiNIR has a verified grounding subsystem")


def _validate_ambiguity_slot(errors: list[str], value: Any) -> None:
    if not isinstance(value, Mapping):
        errors.append("ambiguity slot must be an object")
        return
    _check_unknown_keys(errors, value, _AMBIGUITY_ALLOWED_KEYS, "ambiguity")
    _check_required(errors, value, _AMBIGUITY_ALLOWED_KEYS, "ambiguity")
    unresolved = value.get("unresolved_ambiguities", [])
    if value.get("status") != "resolved":
        errors.append("exported packet requires resolved ambiguity")
    if not isinstance(unresolved, list):
        errors.append("ambiguity.unresolved_ambiguities must be a list")
    elif unresolved:
        errors.append("ambiguity.status resolved requires empty unresolved_ambiguities")


def _validate_operation_constraints_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, Mapping):
        errors.append("operation_constraints slot must be an object")
        return
    _check_unknown_keys(errors, value, _OPERATION_CONSTRAINTS_ALLOWED_KEYS, "operation_constraints")
    _check_required(errors, value, _OPERATION_CONSTRAINTS_ALLOWED_KEYS, "operation_constraints")
    allowed_ops = value.get("allowed_operations", [])
    denied_ops = value.get("denied_operations", [])
    semantic_roles = value.get("semantic_roles", [])
    canonical_operations = value.get("canonical_operations", [])
    _check_list_of_strings(errors, allowed_ops, "operation_constraints.allowed_operations")
    _check_list_of_strings(errors, denied_ops, "operation_constraints.denied_operations")
    _check_list_of_strings(errors, semantic_roles, "operation_constraints.semantic_roles")
    if value.get("requires_human_review") is not True:
        errors.append("operation_constraints.requires_human_review must be true for this profile")
    if not isinstance(canonical_operations, list) or not canonical_operations:
        errors.append("operation_constraints.canonical_operations must be a non-empty list")
    else:
        for idx, op in enumerate(canonical_operations):
            if not isinstance(op, Mapping):
                errors.append(f"operation_constraints.canonical_operations[{idx}] must be an object")
                continue
            _check_unknown_keys(errors, op, _CANONICAL_OPERATION_ALLOWED_KEYS, f"operation_constraints.canonical_operations[{idx}]")
            _check_required(errors, op, {"operation_id", "canonical_op", "semantic_roles", "effects", "capabilities"}, f"operation_constraints.canonical_operations[{idx}]")
            _check_list_of_strings(errors, op.get("semantic_roles"), f"operation_constraints.canonical_operations[{idx}].semantic_roles", allow_empty=True)
            _check_list_of_strings(errors, op.get("effects"), f"operation_constraints.canonical_operations[{idx}].effects", allow_empty=True)
            _check_list_of_strings(errors, op.get("capabilities"), f"operation_constraints.canonical_operations[{idx}].capabilities", allow_empty=True)
    if workflow == "PIIExportRequest":
        if isinstance(allowed_ops, list):
            ops = set(x for x in allowed_ops if isinstance(x, str))
            unsupported_ops = sorted(ops - _PII_EXPORT_ALLOWED_CONSUMER_OPERATIONS)
            if unsupported_ops:
                errors.append("operation_constraints.allowed_operations contains unsupported operations: " + ", ".join(unsupported_ops))
            missing = sorted(_PII_EXPORT_REQUIRED_CONSUMER_OPERATIONS - ops)
            if missing:
                errors.append("operation_constraints.allowed_operations missing required operations: " + ", ".join(missing))
        if isinstance(denied_ops, list):
            denied = set(x for x in denied_ops if isinstance(x, str))
            if denied != _PII_EXPORT_DENIED_CONSUMER_OPERATIONS:
                errors.append("operation_constraints.denied_operations must match the PIIExportRequest denied operation set")
        if isinstance(semantic_roles, list):
            roles = set(x for x in semantic_roles if isinstance(x, str))
            _check_subset(errors, roles, _PII_EXPORT_ALLOWED_SEMANTIC_ROLES, "operation_constraints.semantic_roles")
            missing_roles = sorted(_PII_EXPORT_REQUIRED_SEMANTIC_ROLES - roles)
            if missing_roles:
                errors.append("operation_constraints.semantic_roles missing required roles: " + ", ".join(missing_roles))
        if isinstance(allowed_ops, list) and isinstance(semantic_roles, list):
            overlap = sorted(set(x for x in allowed_ops if isinstance(x, str)) & set(x for x in semantic_roles if isinstance(x, str)))
            if overlap:
                errors.append("operation_constraints.allowed_operations must not contain semantic roles: " + ", ".join(overlap))


def _validate_required_contracts_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        errors.append("required_contracts must be a non-empty-string list")
        return
    if workflow == "PIIExportRequest":
        contracts = set(value)
        missing = sorted(_PII_EXPORT_REQUIRED_CONTRACTS - contracts)
        if missing:
            errors.append("PIIExportRequest missing required contracts: " + ", ".join(missing))
        extra = sorted(contracts - _PII_EXPORT_ALLOWED_CONTRACTS)
        if extra:
            errors.append("required_contracts contains unsupported contracts: " + ", ".join(extra))


def _validate_security_classifications_slot(errors: list[str], value: Any, workflow: str) -> None:
    if not isinstance(value, list):
        errors.append("security_classifications must be a list")
        return
    if workflow == "PIIExportRequest" and not value:
        errors.append("PIIExportRequest requires a PII export payload security classification")
    has_export_payload_pii = False
    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            errors.append(f"security_classifications[{idx}] must be an object")
            continue
        _check_unknown_keys(errors, item, _SECURITY_CLASSIFICATION_ALLOWED_KEYS, f"security_classifications[{idx}]")
        _check_required(errors, item, {"classification_scope", "classification", "source", "status"}, f"security_classifications[{idx}]")
        if item.get("classification") not in _CLASSIFICATION_ENUM:
            errors.append(f"security_classifications[{idx}].classification is not allowed: {item.get('classification')}")
        if item.get("classification_scope") == "export_payload" and item.get("classification") == "PII":
            has_export_payload_pii = True
        if item.get("status") != "consumer_must_ground":
            errors.append(f"security_classifications[{idx}].status must be consumer_must_ground")
        if "field_path" in item and (not isinstance(item.get("field_path"), list) or not all(isinstance(x, str) for x in item.get("field_path", []))):
            errors.append(f"security_classifications[{idx}].field_path must be a string list when present")
    if workflow == "PIIExportRequest" and not has_export_payload_pii:
        errors.append("PIIExportRequest requires classification_scope=export_payload with classification=PII")


def _validate_receipt_links_slot(errors: list[str], value: Any) -> None:
    if not isinstance(value, Mapping):
        errors.append("receipt_links slot must be an object")
        return
    _check_unknown_keys(errors, value, _RECEIPT_LINKS_ALLOWED_KEYS, "receipt_links")
    _check_required(errors, value, _RECEIPT_LINKS_REQUIRED_KEYS, "receipt_links")
    rid = str(value.get("ainir_receipt_id", ""))
    if not _RECEIPT_ID_RE.match(rid):
        errors.append("receipt_links.ainir_receipt_id must reference an issued, fixture, or example AiNIR TrustReceipt")
    for field in ("draft_hash", "raw_source_sha256", "canonical_draft_sha256", "registry_hash", "registry_snapshot_hash", "verifier_report_hash", "policy_hash", "stable_receipt_projection_hash", "gate_results_hash", "evidence_summary_hash"):
        if not _SHA_RE.match(str(value.get(field, ""))):
            errors.append(f"receipt_links.{field} must be sha256:<64 lowercase hex>")
    trusted_context = value.get("trusted_context")
    if not isinstance(trusted_context, Mapping):
        errors.append("receipt_links.trusted_context must be an object")
    else:
        if trusted_context.get("environment") not in {"public_demo", "ci", "test"}:
            errors.append("receipt_links.trusted_context.environment must be public_demo/ci/test")
        if not isinstance(trusted_context.get("source"), str) or not trusted_context.get("source"):
            errors.append("receipt_links.trusted_context.source must be non-empty")
        if trusted_context.get("purpose") != "verified_intent_export":
            errors.append("receipt_links.trusted_context.purpose must be verified_intent_export")
    if value.get("policy_hash") == value.get("registry_hash"):
        errors.append("receipt_links.policy_hash must be distinct from receipt_links.registry_hash")
    if value.get("draft_hash") != value.get("canonical_draft_sha256"):
        errors.append("receipt_links.draft_hash must alias canonical_draft_sha256 in this public profile")


def _normalize_profile(profile: str) -> str:
    p = str(profile or "").strip().lower().replace("-", "_")
    if p in {"aivl", "aivl_consumer_profile", "aivlconsumerprofile"}:
        return _PROFILE_AIVL
    return str(profile)


def _pre_export_profile_errors(draft: DraftModule, profile: str) -> list[str]:
    errors: list[str] = []
    supported = _SUPPORTED_PROFILE_WORKFLOWS.get(profile, set())
    if draft.workflow not in supported:
        errors.append("consumer_profile_does_not_support_workflow")
    for field in sorted(_RAW_SLOT_FIELDS):
        if field in draft.raw:
            errors.append(f"raw_{field}_slot_not_exportable")
    ambiguity = _ambiguity_slot(draft)
    if ambiguity["status"] != "resolved" or ambiguity.get("unresolved_ambiguities"):
        errors.append("unresolved_ambiguity")
    # PII authorization evidence is enforced after the Trust Gate so missing
    # ledger-bound evidence is reported as a Trust Gate failure rather than a
    # consumer-profile preflight shortcut.
    return errors


def _has_verified_authorization_evidence(draft: DraftModule) -> bool:
    for claim in draft.claims:
        if claim.get("id") in {"claim.pii_export_authorized", "claim.export_authorized"} and claim.get("status") == "verified":
            for ev in claim.get("evidence", []) or []:
                if isinstance(ev, Mapping) and isinstance(ev.get("id"), str):
                    return True
    return False


def _build_packet(draft: DraftModule, context: TrustedExecutionContext, decision: Mapping[str, Any], profile: str) -> dict[str, Any]:
    op_registry = get_operation_registry()
    operations = draft.operations
    canonical_ops: list[dict[str, Any]] = []
    roles: set[str] = set()
    declared_effects: list[str] = []
    declared_capabilities: list[str] = []
    for op in operations:
        spec = op_registry.spec_for(op.get("op"))
        canonical = spec.id if spec else str(op.get("op", "unknown"))
        op_roles = sorted(spec.semantic_roles) if spec else []
        roles.update(op_roles)
        op_effects = [e for e in op.get("effects", []) or [] if isinstance(e, str)]
        op_caps = [c for c in op.get("capabilities", []) or [] if isinstance(c, str)]
        declared_effects.extend(op_effects)
        declared_capabilities.extend(op_caps)
        canonical_ops.append({
            "operation_id": str(op.get("id", canonical)),
            "canonical_op": canonical,
            "semantic_roles": op_roles,
            "effects": op_effects,
            "capabilities": op_caps,
        })

    implied_effects = _implied_effects_for_profile(draft.workflow, profile)
    implied_capabilities = _implied_capabilities_for_profile(draft.workflow, profile)
    all_ainir_effects = sorted(set(declared_effects) | set(implied_effects))
    all_ainir_capabilities = sorted(set(declared_capabilities) | set(implied_capabilities))
    consumer_allowed_effects = sorted({_effect_to_consumer(e) for e in all_ainir_effects})
    consumer_required_effects = sorted(_PII_EXPORT_REQUIRED_CONSUMER_EFFECTS if draft.workflow == "PIIExportRequest" else {_effect_to_consumer(e) for e in implied_effects})
    consumer_allowed_capabilities = sorted({_capability_to_consumer(c) for c in all_ainir_capabilities})
    consumer_denied_effects = sorted(x for x in _DENIED_CONSUMER_EFFECTS_DEFAULT if x not in set(consumer_allowed_effects))
    consumer_denied_capabilities = sorted(x for x in _DENIED_CONSUMER_CAPABILITIES_DEFAULT if x not in set(consumer_allowed_capabilities))

    receipt = decision.get("receipt", {}) if isinstance(decision.get("receipt"), Mapping) else {}
    packet_seed = json.dumps({
        "module": draft.module_id,
        "workflow": draft.workflow,
        "task": draft.task,
        "receipt_id": receipt.get("receipt_id"),
        "profile": profile,
        "version": _PACKET_VERSION,
    }, sort_keys=True, ensure_ascii=False)
    packet_id = "ainir.verified_intent." + sha256(packet_seed.encode("utf-8")).hexdigest()[:20]
    return {
        "kind": "VerifiedIntentPacket",
        "version": _PACKET_VERSION,
        "packet_id": packet_id,
        "producer": "AiNIR",
        "consumer_profile": profile,
        "profile_status": "consumer_profile_contract_only_no_downstream_integration",
        "slots": {
            "trust": {
                "status": "verified",
                "decision": "allow",
                "blocked_reasons": [],
                "trust_gate_status": decision.get("status"),
                "lowering_allowed": bool(decision.get("lowering_allowed")),
                "handoff_allowed": bool(decision.get("handoff_allowed")),
            },
            "profile_scope": {
                "profile": profile,
                "supported_workflow": True,
                "workflow": draft.workflow,
                "task": draft.task,
                "task_family": "pii_export_pipeline" if draft.workflow == "PIIExportRequest" else "unsupported",
            },
            "evidence_bindings": _evidence_bindings(draft),
            "effects": {
                "consumer_allowed": consumer_allowed_effects,
                "consumer_required": consumer_required_effects,
                "consumer_denied": consumer_denied_effects,
                "ainir_declared": sorted(set(declared_effects)),
                "ainir_implied": sorted(set(implied_effects)),
            },
            "capabilities": {
                "consumer_allowed": consumer_allowed_capabilities,
                "consumer_denied": consumer_denied_capabilities,
                "ainir_declared": sorted(set(declared_capabilities)),
                "ainir_implied": sorted(set(implied_capabilities)),
            },
            "intent": _derived_intent_slot(draft),
            "grounding_status": _grounding_status_slot(draft),
            "groundings": [],
            "ambiguity": _ambiguity_slot(draft),
            "operation_constraints": _operation_constraints_slot(roles, canonical_ops),
            "required_contracts": _required_contracts_for_workflow(draft.workflow),
            "security_classifications": _derived_field_classifications(draft),
            "receipt_links": {
                "ainir_receipt_id": receipt.get("receipt_id"),
                # Compatibility alias retained for earlier packet consumers.
                "draft_hash": receipt.get("canonical_draft_sha256") or receipt.get("draft_hash"),
                "raw_source_sha256": receipt.get("raw_source_sha256"),
                "canonical_draft_sha256": receipt.get("canonical_draft_sha256") or receipt.get("draft_hash"),
                # registry_hash is the old safety-registry alias; registry_snapshot_hash is the authoritative v2 link.
                "registry_hash": receipt.get("safety_registry_hash") or receipt.get("registry_hash"),
                "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
                "verifier_report_hash": receipt.get("verifier_report_hash"),
                "policy_hash": _consumer_profile_policy_hash(draft.workflow),
                "stable_receipt_projection_hash": receipt.get("stable_receipt_projection_hash"),
                "gate_results_hash": _canonical_json_hash(receipt.get("gate_results") if isinstance(receipt.get("gate_results"), Mapping) else {}),
                "evidence_summary_hash": _canonical_json_hash(receipt.get("evidence_summary") if isinstance(receipt.get("evidence_summary"), Mapping) else {}),
                "trusted_context": receipt.get("trusted_context") if isinstance(receipt.get("trusted_context"), Mapping) else {},
            },
        },
    }



def verify_verified_intent_packet_handoff(
    packet: Mapping[str, Any],
    receipt: Mapping[str, Any] | None = None,
    replay_report: Mapping[str, Any] | None = None,
    *,
    require_receipt_replay: bool = True,
) -> list[str]:
    """Verify a VerifiedIntentPacket against replayed AiNIR warrant.

    validate_verified_intent_packet() is a strict shape/profile validator. This
    function is stronger: it binds the packet payload to the matching receipt,
    requires a passed TrustReceipt replay report by default, and checks consumer
    policy/registry aliases so self-consistent fake receipt-like objects are not
    accepted as handoff warrant.
    """
    errors = list(validate_verified_intent_packet(packet))
    if errors:
        return errors
    if receipt is None or not isinstance(receipt, Mapping):
        errors.append("handoff verification requires the matching TrustReceipt artifact")
        return errors
    if require_receipt_replay:
        # This API accepts only an actual ReceiptReplayReport instance.  Passing
        # a caller-authored dict is treated as link-comparison data, not replay
        # authority; use verify_verified_intent_packet_handoff_from_files() for
        # normal bundle verification.
        from .trust_receipt_store import ReceiptReplayReport
        if not isinstance(replay_report, ReceiptReplayReport):
            errors.append("handoff verification requires a ReceiptReplayReport produced by replay_trust_receipt")
            return errors
        replay_payload = replay_report.as_dict()
        if replay_payload.get("overall_status") != "passed":
            errors.append("TrustReceipt replay report must have overall_status=passed")
        if replay_payload.get("receipt_id") != receipt.get("receipt_id"):
            errors.append("TrustReceipt replay report receipt_id does not match the supplied receipt")
        replay_receipt = replay_payload.get("receipt")
        if isinstance(replay_receipt, Mapping) and replay_receipt.get("stable_receipt_projection_hash") != receipt.get("stable_receipt_projection_hash"):
            errors.append("TrustReceipt replay report receipt projection does not match the supplied receipt")
    slots = packet.get("slots") if isinstance(packet, Mapping) else {}
    links = slots.get("receipt_links") if isinstance(slots, Mapping) else {}
    if not isinstance(links, Mapping):
        return errors + ["receipt_links slot must be an object"]
    comparisons = {
        "ainir_receipt_id": receipt.get("receipt_id"),
        "raw_source_sha256": receipt.get("raw_source_sha256"),
        "canonical_draft_sha256": receipt.get("canonical_draft_sha256") or receipt.get("draft_hash"),
        "registry_snapshot_hash": receipt.get("registry_snapshot_hash"),
        "verifier_report_hash": receipt.get("verifier_report_hash"),
        "stable_receipt_projection_hash": receipt.get("stable_receipt_projection_hash"),
        "gate_results_hash": _canonical_json_hash(receipt.get("gate_results") if isinstance(receipt.get("gate_results"), Mapping) else {}),
        "evidence_summary_hash": _canonical_json_hash(receipt.get("evidence_summary") if isinstance(receipt.get("evidence_summary"), Mapping) else {}),
    }
    for field, expected in comparisons.items():
        if links.get(field) != expected:
            errors.append(f"receipt_links.{field} does not match TrustReceipt")
    if links.get("trusted_context") != receipt.get("trusted_context"):
        errors.append("receipt_links.trusted_context does not match TrustReceipt")
    profile_scope = slots.get("profile_scope") if isinstance(slots, Mapping) else {}
    workflow = str(profile_scope.get("workflow", "")) if isinstance(profile_scope, Mapping) else ""
    expected_policy_hash = _consumer_profile_policy_hash(workflow)
    if links.get("policy_hash") != expected_policy_hash:
        errors.append("receipt_links.policy_hash does not match the consumer-profile policy hash")
    if links.get("registry_hash") != receipt.get("safety_registry_hash"):
        errors.append("receipt_links.registry_hash compatibility alias does not match TrustReceipt.safety_registry_hash")
    packet_hash = _canonical_verified_intent_packet_hash(packet)
    expected_packet_hash = receipt.get("verified_intent_packet_canonical_sha256")
    if expected_packet_hash != packet_hash:
        errors.append("VerifiedIntentPacket canonical payload hash does not match the TrustReceipt sidecar")
    evidence_ids = {b.get("evidence_id") for b in slots.get("evidence_bindings", []) if isinstance(b, Mapping)} if isinstance(slots.get("evidence_bindings"), list) else set()
    summary_ids = set((receipt.get("evidence_summary") or {}).get("referenced_evidence_ids", []) if isinstance(receipt.get("evidence_summary"), Mapping) else [])
    if evidence_ids and summary_ids and not evidence_ids <= summary_ids:
        errors.append("packet evidence_bindings are not a subset of receipt evidence_summary.referenced_evidence_ids")
    return errors



def verify_verified_intent_packet_handoff_from_files(
    packet_path: str | Path,
    receipt_path: str | Path,
    draft_path: str | Path | None = None,
) -> list[str]:
    """Verify a VerifiedIntent handoff bundle from files.

    This is the replay-authoritative helper. It loads packet/receipt with the
    hardened JSON artifact reader, runs TrustReceipt replay internally, and then
    compares the packet, receipt links, and replayed warrant. It avoids trusting
    a caller-supplied replay_report dictionary.
    """
    from .trust_receipt_store import _read_json_artifact, replay_trust_receipt
    packet_artifact = _read_json_artifact(packet_path, artifact_name="verified_intent_packet")
    if not packet_artifact.get("ok"):
        return [f"packet JSON artifact invalid: {packet_artifact.get('reason')}"]
    receipt_artifact = _read_json_artifact(receipt_path, artifact_name="receipt")
    if not receipt_artifact.get("ok"):
        return [f"receipt JSON artifact invalid: {receipt_artifact.get('reason')}"]
    replay = replay_trust_receipt(receipt_path, draft_path=draft_path)
    return verify_verified_intent_packet_handoff(packet_artifact["value"], receipt_artifact["value"], replay)

def _consumer_profile_policy_hash(workflow: str) -> str:
    payload = {
        "packet_version": _PACKET_VERSION,
        "profile": _PROFILE_AIVL,
        "workflow": workflow,
        "supported_workflows": sorted(_SUPPORTED_PROFILE_WORKFLOWS[_PROFILE_AIVL]),
        "required_contracts": sorted(_PII_EXPORT_REQUIRED_CONTRACTS),
        "allowed_consumer_effects": sorted(_PII_EXPORT_ALLOWED_CONSUMER_EFFECTS),
        "required_consumer_effects": sorted(_PII_EXPORT_REQUIRED_CONSUMER_EFFECTS),
        "denied_consumer_effects": sorted(_PII_EXPORT_DENIED_CONSUMER_EFFECTS),
        "allowed_consumer_capabilities": sorted(_PII_EXPORT_ALLOWED_CONSUMER_CAPABILITIES),
        "required_consumer_capabilities": sorted(_PII_EXPORT_REQUIRED_CONSUMER_CAPABILITIES),
        "denied_consumer_capabilities": sorted(_PII_EXPORT_DENIED_CONSUMER_CAPABILITIES),
        "allowed_operations": sorted(_PII_EXPORT_ALLOWED_CONSUMER_OPERATIONS),
        "denied_operations": sorted(_PII_EXPORT_DENIED_CONSUMER_OPERATIONS),
        "semantic_roles": sorted(_PII_EXPORT_ALLOWED_SEMANTIC_ROLES),
    }
    return "sha256:" + sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

def _operation_constraints_slot(roles: set[str], canonical_ops: list[dict[str, Any]]) -> dict[str, Any]:
    consumer_ops = sorted({op for role in roles for op in [_ROLE_TO_OPERATION.get(role)] if op})
    return {
        "allowed_operations": consumer_ops,
        "denied_operations": sorted(_PII_EXPORT_DENIED_CONSUMER_OPERATIONS),
        "requires_human_review": True,
        "semantic_roles": sorted(roles),
        "canonical_operations": canonical_ops,
    }


def _implied_effects_for_profile(workflow: str, profile: str) -> list[str]:
    if profile == _PROFILE_AIVL and workflow == "PIIExportRequest":
        return ["effect.privacy.pii.export"]
    return []


def _implied_capabilities_for_profile(workflow: str, profile: str) -> list[str]:
    if profile == _PROFILE_AIVL and workflow == "PIIExportRequest":
        return ["cap.pii.export"]
    return []


def _effect_to_consumer(effect: str) -> str:
    return _EFFECT_TO_CONSUMER.get(effect, effect)


def _capability_to_consumer(cap: str) -> str:
    return _CAPABILITY_TO_CONSUMER.get(cap, cap)


def _derived_intent_slot(draft: DraftModule) -> dict[str, Any]:
    if draft.workflow == "PIIExportRequest":
        return {
            "task_intent": "prepare_authorized_pii_export_package",
            "domain": "privacy_export",
            "operation_kind": "data_pipeline",
            "natural_language_summary": "Prepare an authorized encrypted PII export package. Concrete data-source grounding must be performed by the future consumer.",
        }
    return {
        "task_intent": "unsupported_for_profile",
        "domain": draft.workflow,
        "operation_kind": "unsupported",
        "natural_language_summary": "This workflow is not supported by the selected external consumer profile.",
    }


def _grounding_status_slot(draft: DraftModule) -> dict[str, Any]:
    return {
        "status": "consumer_must_ground",
        "reason": "AiNIR validates trust, evidence, operation, effect, capability, context, and transaction boundaries; this public demo does not verify concrete source/filter/projection schema grounding.",
        "required_consumer_checks": sorted({
            "schema_grounding_required",
            "filter_matches",
            "projection_matches",
            "field_allowlist",
        }),
    }


def _ambiguity_slot(draft: DraftModule) -> dict[str, Any]:
    raw = draft.raw.get("ambiguity")
    if isinstance(raw, Mapping):
        status = str(raw.get("status", "resolved"))
        unresolved = raw.get("unresolved_ambiguities", [])
        if not isinstance(unresolved, list):
            unresolved = []
        return {"status": status, "unresolved_ambiguities": unresolved}
    unresolved = draft.raw.get("unresolved_ambiguities")
    if isinstance(unresolved, list) and unresolved:
        return {"status": "requires_clarification", "unresolved_ambiguities": unresolved}
    return {"status": "resolved", "unresolved_ambiguities": []}


def _evidence_bindings(draft: DraftModule) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for claim in draft.claims:
        for ev in claim.get("evidence", []) or []:
            if not isinstance(ev, Mapping) or not isinstance(ev.get("id"), str):
                continue
            out.append({
                "claim": claim.get("id"),
                "evidence_id": ev.get("id"),
                "issuer": "ainir_evidence_ledger",
                "status": "verified" if claim.get("status") == "verified" else "referenced",
                "ledger_bound": claim.get("status") == "verified",
            })
    return out


def _required_contracts_for_workflow(workflow: str) -> list[str]:
    if workflow == "PIIExportRequest":
        return sorted(_PII_EXPORT_REQUIRED_CONTRACTS)
    return ["trust_gate_passed", "operation_contracts_satisfied"]


def _derived_field_classifications(draft: DraftModule) -> list[dict[str, Any]]:
    if draft.workflow == "PIIExportRequest":
        return [{
            "classification_scope": "export_payload",
            "classification": "PII",
            "source": "consumer_grounded_export_fields",
            "status": "consumer_must_ground",
        }]
    return []


def _check_unknown_keys(errors: list[str], obj: Mapping[str, Any], allowed: set[str], path: str) -> None:
    extra = sorted(set(obj.keys()) - allowed)
    if extra:
        errors.append(f"{path} contains unsupported fields: " + ", ".join(extra))


def _check_required(errors: list[str], obj: Mapping[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - set(obj.keys()))
    if missing:
        errors.append(f"{path} missing required fields: " + ", ".join(missing))


def _check_subset(errors: list[str], values: set[str], allowed: set[str], path: str) -> None:
    extra = sorted(values - allowed)
    if extra:
        errors.append(f"{path} contains unsupported values: " + ", ".join(extra))


def _check_disjoint(errors: list[str], a: Any, b: Any, name: str) -> None:
    if not isinstance(a, list) or not isinstance(b, list):
        errors.append(f"{name} must compare two lists")
        return
    overlap = sorted(set(x for x in a if isinstance(x, str)) & set(x for x in b if isinstance(x, str)))
    if overlap:
        errors.append(f"{name} must not overlap: {', '.join(overlap)}")


def _check_list_of_strings(errors: list[str], value: Any, name: str, allow_empty: bool = False) -> None:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        errors.append(f"{name} must be a string list")
        return
    if not value and not allow_empty:
        errors.append(f"{name} must be non-empty")
