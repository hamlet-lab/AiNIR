"""Stable public artifact contract identifiers for AiNIR.

The identifiers in this module are compatibility names, not claims of
production readiness.  Legacy pre-v1 phase-tagged artifacts remain accepted
for exact replay during the RC transition.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

TRUST_GATE_DECISION_KIND: Final = "AiNIRTrustGateDecision"
TRUST_GATE_DECISION_CONTRACT: Final = "ainir.trust-gate-decision.v1"
LEGACY_TRUST_GATE_DECISION_VERSION: Final = "pre_v1_phase18"

TRUST_RECEIPT_KIND: Final = "AiNIRTrustReceipt"
TRUST_RECEIPT_CONTRACT: Final = "ainir.trust-receipt.v1"
LEGACY_TRUST_RECEIPT_VERSION: Final = "pre_v1_phase18"

TRUST_RECEIPT_REPLAY_REPORT_KIND: Final = "AiNIRTrustReceiptReplayReport"
TRUST_RECEIPT_REPLAY_REPORT_CONTRACT: Final = "ainir.trust-receipt-replay-report.v1"

PROFILE_MANIFEST_KIND: Final = "AiNIRProfileManifest"
PROFILE_MANIFEST_CONTRACT: Final = "ainir.profile-manifest.v1"

CONFORMANCE_PACK_KIND: Final = "AiNIRConformancePack"
CONFORMANCE_PACK_CONTRACT: Final = "ainir.conformance-pack.v1"

CONFORMANCE_REPORT_KIND: Final = "AiNIRConformanceReport"
CONFORMANCE_REPORT_CONTRACT: Final = "ainir.conformance-report.v1"

REGISTRY_SNAPSHOT_KIND: Final = "AiNIRRegistrySnapshotArtifact"
REGISTRY_SNAPSHOT_CONTRACT: Final = "ainir.registry-snapshot.v1"

REGISTRY_DIFF_KIND: Final = "AiNIRRegistryDiff"
REGISTRY_DIFF_CONTRACT: Final = "ainir.registry-diff.v1"

REGISTRY_MIGRATION_RECORD_KIND: Final = "AiNIRRegistryMigrationRecord"
REGISTRY_MIGRATION_RECORD_CONTRACT: Final = "ainir.registry-migration-record.v1"

EVIDENCE_REQUEST_KIND: Final = "AiNIREvidenceRequest"
EVIDENCE_REQUEST_CONTRACT: Final = "ainir.evidence-request.v1"

EVIDENCE_RECORD_KIND: Final = "AiNIREvidenceRecord"
EVIDENCE_RECORD_CONTRACT: Final = "ainir.evidence-record.v1"

EVIDENCE_PROVIDER_POLICY_KIND: Final = "AiNIREvidenceProviderPolicy"
EVIDENCE_PROVIDER_POLICY_CONTRACT: Final = "ainir.evidence-provider-policy.v1"

EVIDENCE_BUNDLE_KIND: Final = "AiNIREvidenceBundle"
EVIDENCE_BUNDLE_CONTRACT: Final = "ainir.evidence-bundle.v1"

EVIDENCE_RESOLUTION_KIND: Final = "AiNIREvidenceResolution"
EVIDENCE_RESOLUTION_CONTRACT: Final = "ainir.evidence-resolution.v1"

EVIDENCE_VALIDATION_REPORT_KIND: Final = "AiNIREvidenceValidationReport"
EVIDENCE_VALIDATION_REPORT_CONTRACT: Final = "ainir.evidence-validation-report.v1"

MCP_TOOL_CALL_PROFILE_KIND: Final = "AiNIRMCPToolCallProfile"
MCP_TOOL_CALL_PROFILE_CONTRACT: Final = "ainir.mcp-tool-call-profile.v1"

MCP_TOOL_CALL_ENVELOPE_KIND: Final = "AiNIRMCPToolCallEnvelope"
MCP_TOOL_CALL_ENVELOPE_CONTRACT: Final = "ainir.mcp-tool-call-envelope.v1"

MCP_HOST_CONTEXT_KIND: Final = "AiNIRMCPHostContext"
MCP_HOST_CONTEXT_CONTRACT: Final = "ainir.mcp-host-context.v1"

MCP_TOOL_CALL_ASSESSMENT_KIND: Final = "AiNIRMCPToolCallAssessment"
MCP_TOOL_CALL_ASSESSMENT_CONTRACT: Final = "ainir.mcp-tool-call-assessment.v1"

MCP_TOOL_CALL_CONFORMANCE_PACK_KIND: Final = "AiNIRMCPToolCallConformancePack"
MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT: Final = "ainir.mcp-tool-call-conformance-pack.v1"

MCP_TOOL_CALL_CONFORMANCE_REPORT_KIND: Final = "AiNIRMCPToolCallConformanceReport"
MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT: Final = "ainir.mcp-tool-call-conformance-report.v1"

OPENAI_FUNCTION_CALL_BINDING_KIND: Final = "AiNIROpenAIFunctionCallBinding"
OPENAI_FUNCTION_CALL_BINDING_CONTRACT: Final = "ainir.openai-function-call-binding.v1"

OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND: Final = "AiNIROpenAIFunctionToolPreflight"
OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT: Final = "ainir.openai-function-tool-preflight.v1"

CONTRACT_MANIFEST_KIND: Final = "AiNIRArtifactContractManifest"
CONTRACT_MANIFEST_VERSION: Final = "ainir.artifact-contract-manifest.v1"

SUPPORTED_TRUST_GATE_DECISION_VERSIONS: Final = frozenset(
    {TRUST_GATE_DECISION_CONTRACT, LEGACY_TRUST_GATE_DECISION_VERSION}
)
SUPPORTED_TRUST_RECEIPT_VERSIONS: Final = frozenset(
    {TRUST_RECEIPT_CONTRACT, LEGACY_TRUST_RECEIPT_VERSION}
)


@dataclass(frozen=True)
class ArtifactContractInfo:
    name: str
    kind: str
    identifier: str
    schema: str | None
    status: str
    legacy_versions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["legacy_versions"] = list(self.legacy_versions)
        return result


_ARTIFACT_CONTRACTS: Final = (

    ArtifactContractInfo(
        name="openai_function_call_binding",
        kind=OPENAI_FUNCTION_CALL_BINDING_KIND,
        identifier=OPENAI_FUNCTION_CALL_BINDING_CONTRACT,
        schema="openai_function_call_binding.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="openai_function_tool_preflight",
        kind=OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND,
        identifier=OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT,
        schema="openai_function_tool_preflight.schema.json",
        status="implemented",
    ),

    ArtifactContractInfo(
        name="mcp_tool_call_profile",
        kind=MCP_TOOL_CALL_PROFILE_KIND,
        identifier=MCP_TOOL_CALL_PROFILE_CONTRACT,
        schema="mcp_tool_call_profile.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="mcp_tool_call_envelope",
        kind=MCP_TOOL_CALL_ENVELOPE_KIND,
        identifier=MCP_TOOL_CALL_ENVELOPE_CONTRACT,
        schema="mcp_tool_call_envelope.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="mcp_host_context",
        kind=MCP_HOST_CONTEXT_KIND,
        identifier=MCP_HOST_CONTEXT_CONTRACT,
        schema="mcp_host_context.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="mcp_tool_call_assessment",
        kind=MCP_TOOL_CALL_ASSESSMENT_KIND,
        identifier=MCP_TOOL_CALL_ASSESSMENT_CONTRACT,
        schema="mcp_tool_call_assessment.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="mcp_tool_call_conformance_pack",
        kind=MCP_TOOL_CALL_CONFORMANCE_PACK_KIND,
        identifier=MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT,
        schema="mcp_tool_call_conformance_pack.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="mcp_tool_call_conformance_report",
        kind=MCP_TOOL_CALL_CONFORMANCE_REPORT_KIND,
        identifier=MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT,
        schema="mcp_tool_call_conformance_report.schema.json",
        status="implemented",
    ),

    ArtifactContractInfo(
        name="evidence_request",
        kind=EVIDENCE_REQUEST_KIND,
        identifier=EVIDENCE_REQUEST_CONTRACT,
        schema="evidence_request.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="evidence_record",
        kind=EVIDENCE_RECORD_KIND,
        identifier=EVIDENCE_RECORD_CONTRACT,
        schema="evidence_record.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="evidence_provider_policy",
        kind=EVIDENCE_PROVIDER_POLICY_KIND,
        identifier=EVIDENCE_PROVIDER_POLICY_CONTRACT,
        schema="evidence_provider_policy.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="evidence_bundle",
        kind=EVIDENCE_BUNDLE_KIND,
        identifier=EVIDENCE_BUNDLE_CONTRACT,
        schema="evidence_bundle.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="evidence_resolution",
        kind=EVIDENCE_RESOLUTION_KIND,
        identifier=EVIDENCE_RESOLUTION_CONTRACT,
        schema="evidence_resolution.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="evidence_validation_report",
        kind=EVIDENCE_VALIDATION_REPORT_KIND,
        identifier=EVIDENCE_VALIDATION_REPORT_CONTRACT,
        schema="evidence_validation_report.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="trust_gate_decision",
        kind=TRUST_GATE_DECISION_KIND,
        identifier=TRUST_GATE_DECISION_CONTRACT,
        schema="trust_gate_decision.schema.json",
        status="implemented",
        legacy_versions=(LEGACY_TRUST_GATE_DECISION_VERSION,),
    ),
    ArtifactContractInfo(
        name="trust_receipt",
        kind=TRUST_RECEIPT_KIND,
        identifier=TRUST_RECEIPT_CONTRACT,
        schema="trust_receipt.schema.json",
        status="implemented",
        legacy_versions=(LEGACY_TRUST_RECEIPT_VERSION,),
    ),
    ArtifactContractInfo(
        name="trust_receipt_replay_report",
        kind=TRUST_RECEIPT_REPLAY_REPORT_KIND,
        identifier=TRUST_RECEIPT_REPLAY_REPORT_CONTRACT,
        schema="trust_receipt_replay_report.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="profile_manifest",
        kind=PROFILE_MANIFEST_KIND,
        identifier=PROFILE_MANIFEST_CONTRACT,
        schema="profile_manifest.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="conformance_pack",
        kind=CONFORMANCE_PACK_KIND,
        identifier=CONFORMANCE_PACK_CONTRACT,
        schema="conformance_pack.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="conformance_report",
        kind=CONFORMANCE_REPORT_KIND,
        identifier=CONFORMANCE_REPORT_CONTRACT,
        schema="conformance_report.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="registry_snapshot",
        kind=REGISTRY_SNAPSHOT_KIND,
        identifier=REGISTRY_SNAPSHOT_CONTRACT,
        schema="registry_snapshot.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="registry_diff",
        kind=REGISTRY_DIFF_KIND,
        identifier=REGISTRY_DIFF_CONTRACT,
        schema="registry_diff.schema.json",
        status="implemented",
    ),
    ArtifactContractInfo(
        name="registry_migration_record",
        kind=REGISTRY_MIGRATION_RECORD_KIND,
        identifier=REGISTRY_MIGRATION_RECORD_CONTRACT,
        schema="registry_migration_record.schema.json",
        status="implemented",
    ),
)


def artifact_contracts() -> tuple[ArtifactContractInfo, ...]:
    """Return the immutable public artifact-contract registry."""

    return _ARTIFACT_CONTRACTS


def artifact_contract_manifest() -> dict[str, object]:
    """Return a deterministic description of stable and legacy contracts."""

    return {
        "kind": CONTRACT_MANIFEST_KIND,
        "version": CONTRACT_MANIFEST_VERSION,
        "contracts": {
            item.name: item.as_dict()
            for item in sorted(_ARTIFACT_CONTRACTS, key=lambda value: value.name)
        },
        "production_runtime_ready": False,
        "v1_final_ready": False,
    }


def schema_name_for_contract(identifier: str) -> str | None:
    for item in _ARTIFACT_CONTRACTS:
        if identifier == item.identifier or identifier in item.legacy_versions:
            return item.schema
    raise KeyError(f"unknown AiNIR artifact contract: {identifier!r}")


__all__ = [
    "ArtifactContractInfo",
    "EVIDENCE_BUNDLE_CONTRACT",
    "EVIDENCE_BUNDLE_KIND",
    "EVIDENCE_PROVIDER_POLICY_CONTRACT",
    "EVIDENCE_PROVIDER_POLICY_KIND",
    "EVIDENCE_RECORD_CONTRACT",
    "EVIDENCE_RECORD_KIND",
    "EVIDENCE_REQUEST_CONTRACT",
    "EVIDENCE_REQUEST_KIND",
    "EVIDENCE_RESOLUTION_CONTRACT",
    "EVIDENCE_RESOLUTION_KIND",
    "EVIDENCE_VALIDATION_REPORT_CONTRACT",
    "EVIDENCE_VALIDATION_REPORT_KIND",
    "MCP_HOST_CONTEXT_CONTRACT",
    "MCP_HOST_CONTEXT_KIND",
    "MCP_TOOL_CALL_ASSESSMENT_CONTRACT",
    "MCP_TOOL_CALL_ASSESSMENT_KIND",
    "MCP_TOOL_CALL_CONFORMANCE_REPORT_CONTRACT",
    "MCP_TOOL_CALL_CONFORMANCE_REPORT_KIND",
    "MCP_TOOL_CALL_ENVELOPE_CONTRACT",
    "MCP_TOOL_CALL_ENVELOPE_KIND",
    "MCP_TOOL_CALL_PROFILE_CONTRACT",
    "MCP_TOOL_CALL_PROFILE_KIND",
    "OPENAI_FUNCTION_CALL_BINDING_CONTRACT",
    "OPENAI_FUNCTION_CALL_BINDING_KIND",
    "OPENAI_FUNCTION_TOOL_PREFLIGHT_CONTRACT",
    "OPENAI_FUNCTION_TOOL_PREFLIGHT_KIND",
    "CONFORMANCE_PACK_CONTRACT",
    "CONFORMANCE_PACK_KIND",
    "CONFORMANCE_REPORT_CONTRACT",
    "CONFORMANCE_REPORT_KIND",
    "CONTRACT_MANIFEST_KIND",
    "CONTRACT_MANIFEST_VERSION",
    "LEGACY_TRUST_GATE_DECISION_VERSION",
    "LEGACY_TRUST_RECEIPT_VERSION",
    "MCP_TOOL_CALL_CONFORMANCE_PACK_CONTRACT",
    "MCP_TOOL_CALL_CONFORMANCE_PACK_KIND",
    "PROFILE_MANIFEST_CONTRACT",
    "PROFILE_MANIFEST_KIND",
    "REGISTRY_DIFF_CONTRACT",
    "REGISTRY_DIFF_KIND",
    "REGISTRY_MIGRATION_RECORD_CONTRACT",
    "REGISTRY_MIGRATION_RECORD_KIND",
    "REGISTRY_SNAPSHOT_CONTRACT",
    "REGISTRY_SNAPSHOT_KIND",
    "SUPPORTED_TRUST_GATE_DECISION_VERSIONS",
    "SUPPORTED_TRUST_RECEIPT_VERSIONS",
    "TRUST_GATE_DECISION_CONTRACT",
    "TRUST_GATE_DECISION_KIND",
    "TRUST_RECEIPT_CONTRACT",
    "TRUST_RECEIPT_KIND",
    "TRUST_RECEIPT_REPLAY_REPORT_CONTRACT",
    "TRUST_RECEIPT_REPLAY_REPORT_KIND",
    "artifact_contract_manifest",
    "artifact_contracts",
    "schema_name_for_contract",
]
