"""Registry-bound evidence ledger for AiNIR public demo.

Pre-v1 Phase 3: model/provider drafts are not allowed to self-attest evidence
with fields such as ``checked: true`` or ``source: claude``. A verified claim is
accepted only when its evidence id resolves to a bundled ledger record whose
scope, producer, reliability, artifact, and optional claim statement hash match.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

import yaml

from .safety_registry import get_registry
from .core import DraftModule, Finding, load_yaml_no_duplicate_keys
from .registry_context import active_registry_bundle

_SELF_ATTEST_FIELDS = {
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


@dataclass(frozen=True)
class LedgerDecision:
    checked: bool
    reason: str
    evidence_id: str | None = None


class EvidenceLedger:
    def __init__(self, data: Mapping[str, Any], root: Path | None = None):
        self.data = dict(data or {})
        self.root = root
        self.records = {}
        for rec in self.data.get("records", []) or []:
            if isinstance(rec, Mapping) and isinstance(rec.get("id"), str):
                self.records[str(rec["id"])] = dict(rec)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "EvidenceLedger":
        if path is not None:
            p = Path(path)
            with p.open("r", encoding="utf-8") as f:
                return cls(load_yaml_no_duplicate_keys(f.read()) or {}, p.parent.parent if p.parent.name == "registries" else p.parent)

        # Prefer the repository-root ledger so artifact hashes can be checked
        # against files in examples/. Packaged resources are a fallback for
        # installed/demo mode, where artifact verification may be unavailable.
        here = Path(__file__).resolve()
        for candidate in (
            here.parents[2] / "registries" / "evidence_ledger.yaml",
            Path.cwd() / "registries" / "evidence_ledger.yaml",
        ):
            if candidate.exists():
                with candidate.open("r", encoding="utf-8") as f:
                    return cls(load_yaml_no_duplicate_keys(f.read()) or {}, candidate.parent.parent)

        try:
            content = resources.files("ainir.registries").joinpath("evidence_ledger.yaml").read_text(encoding="utf-8")
            return cls(load_yaml_no_duplicate_keys(content) or {}, None)
        except Exception:
            pass

        return cls({"records": []}, None)

    def decide(self, ev: Mapping[str, Any], claim: Mapping[str, Any], module_id: str, workflow: str, draft: DraftModule | None = None) -> LedgerDecision:
        eid = ev.get("id")
        if not isinstance(eid, str) or not eid.strip():
            return LedgerDecision(False, "evidence id is missing")

        forbidden = sorted(k for k in ev.keys() if k in _SELF_ATTEST_FIELDS)
        # id/kind is a reference. The rest of evidence facts must come from the ledger.
        forbidden = [k for k in forbidden if k not in {"id", "kind"}]
        if forbidden:
            return LedgerDecision(False, "draft evidence contains self-attested fields: " + ", ".join(forbidden), eid)

        rec = self.records.get(eid)
        if rec is None:
            return LedgerDecision(False, "evidence id is not present in the evidence ledger", eid)

        kind = ev.get("kind")
        if kind is not None and kind != rec.get("kind"):
            return LedgerDecision(False, "evidence kind does not match ledger record", eid)

        registry = get_registry()
        if rec.get("kind") not in set(registry.trusted_evidence.get("allowed_kinds", [])):
            return LedgerDecision(False, "ledger evidence kind is not allowed", eid)
        if rec.get("status") != "checked":
            return LedgerDecision(False, "ledger evidence is not checked", eid)
        producer_kind = rec.get("producer_kind")
        if producer_kind not in set(registry.trusted_evidence.get("trusted_producers", [])):
            return LedgerDecision(False, "ledger evidence producer is not trusted", eid)
        try:
            reliability = float(rec.get("reliability", 0))
        except Exception:
            reliability = 0.0
        if reliability < float(rec.get("min_reliability", 0.8)):
            return LedgerDecision(False, "ledger evidence reliability is below threshold", eid)

        if rec.get("supports_module") and rec.get("supports_module") != module_id:
            return LedgerDecision(False, "ledger evidence does not support this module", eid)
        if rec.get("supports_workflow") and rec.get("supports_workflow") != workflow:
            return LedgerDecision(False, "ledger evidence does not support this workflow", eid)

        claim_id = claim.get("id")
        supported_claims = rec.get("supports_claims") or []
        if supported_claims and claim_id not in supported_claims:
            return LedgerDecision(False, "ledger evidence does not support this claim id", eid)

        expected_statement_hash = rec.get("claim_statement_sha256")
        if expected_statement_hash:
            statement = str(claim.get("statement", ""))
            observed = sha256(statement.encode("utf-8")).hexdigest()
            if observed != expected_statement_hash:
                return LedgerDecision(False, "claim statement hash does not match the ledger-bound statement", eid)

        artifact_ref = rec.get("artifact_ref")
        artifact_sha = rec.get("artifact_sha256")
        if artifact_ref and artifact_sha:
            if self.root is not None:
                artifact = (self.root / str(artifact_ref)).resolve()
                try:
                    root = self.root.resolve()
                    artifact.relative_to(root)
                except Exception:
                    return LedgerDecision(False, "ledger artifact_ref escapes repository root", eid)
                if not artifact.exists():
                    return LedgerDecision(False, "ledger artifact_ref does not exist", eid)
                observed_sha = sha256(artifact.read_bytes()).hexdigest()
                if observed_sha != artifact_sha:
                    return LedgerDecision(False, "ledger artifact hash mismatch", eid)
            if draft is None or not isinstance(draft.raw.get("__source_path__"), str):
                return LedgerDecision(False, "current draft source path is unavailable for artifact binding", eid)
            current_path = Path(str(draft.raw["__source_path__"]))
            if not current_path.exists():
                return LedgerDecision(False, "current draft source path does not exist", eid)
            current_sha = sha256(current_path.read_bytes()).hexdigest()
            if current_sha != artifact_sha:
                # Exact fixture provenance is recorded separately through raw_source_sha256.
                # Evidence binding is semantic: a harmless YAML comment must not erase
                # a claim/evidence warrant when the canonical draft payload is unchanged.
                try:
                    current_payload = {k: v for k, v in draft.raw.items() if not str(k).startswith("__")}
                    artifact_payload = load_yaml_no_duplicate_keys(artifact.read_text(encoding="utf-8")) or {}
                    current_canonical = sha256(yaml.safe_dump(current_payload, sort_keys=True, allow_unicode=True).encode("utf-8")).hexdigest()
                    artifact_canonical = sha256(yaml.safe_dump(artifact_payload, sort_keys=True, allow_unicode=True).encode("utf-8")).hexdigest()
                except Exception:
                    current_canonical = artifact_canonical = None
                if current_canonical != artifact_canonical:
                    return LedgerDecision(False, "ledger evidence is not bound to the current draft artifact or canonical draft", eid)

        return LedgerDecision(True, "evidence is ledger-bound and checked for the current draft", eid)


@lru_cache(maxsize=1)
def _default_evidence_ledger() -> EvidenceLedger:
    return EvidenceLedger.load()


def get_evidence_ledger() -> EvidenceLedger:
    bundle = active_registry_bundle()
    if bundle is not None:
        return bundle.evidence_ledger
    return _default_evidence_ledger()


def claim_statement_sha256(statement: str) -> str:
    return sha256(str(statement).encode("utf-8")).hexdigest()

def ledger_bound_evidence_summary(draft: DraftModule) -> dict[str, Any]:
    """Summarize whether a draft has non-vacuous ledger-bound warrant.

    This intentionally runs independently from the verifier's verified-claim
    check. A draft can be structurally/policy-valid while still being
    ineligible for Trust Gate handoff/lowering because it carries no auditable
    claim/evidence warrant.
    """
    total_claims = len(draft.claims)
    verified_claim_count = 0
    total_evidence_refs = 0
    verified_evidence_refs = 0
    checked_evidence_refs = 0
    checked_verified_evidence_refs = 0
    failed_reasons: list[str] = []
    for claim in draft.claims:
        is_verified_claim = str(claim.get("status", "hypothesized")) == "verified"
        if is_verified_claim:
            verified_claim_count += 1
        evidence = claim.get("evidence", []) or []
        if not isinstance(evidence, list):
            continue
        for ev in evidence:
            if not isinstance(ev, Mapping):
                continue
            total_evidence_refs += 1
            if is_verified_claim:
                verified_evidence_refs += 1
            decision = get_evidence_ledger().decide(ev, claim, draft.module_id, draft.workflow, draft)
            if decision.checked:
                checked_evidence_refs += 1
                if is_verified_claim:
                    checked_verified_evidence_refs += 1
            else:
                failed_reasons.append(f"{decision.evidence_id or 'evidence'}: {decision.reason}")
    return {
        "claim_count": total_claims,
        "verified_claim_count": verified_claim_count,
        "evidence_ref_count": total_evidence_refs,
        "verified_evidence_ref_count": verified_evidence_refs,
        "ledger_bound_checked_evidence_count": checked_evidence_refs,
        "ledger_bound_checked_verified_evidence_count": checked_verified_evidence_refs,
        "failed_reasons": failed_reasons,
    }


def non_vacuous_evidence_findings(draft: DraftModule, *, target: str = "evidence.bindings") -> list[Finding]:
    """Return critical findings when handoff/lowering would be evidence-vacuous."""
    summary = ledger_bound_evidence_summary(draft)
    if summary["claim_count"] <= 0:
        return [
            Finding(
                rule="TR000.ledger_bound_claim_required",
                severity="critical",
                target="claims",
                message="Trust Gate handoff/lowering requires at least one verified, ledger-bound claim; no claims were provided.",
                suggestion="Add a verified claim with evidence bound to registries/evidence_ledger.yaml, or keep the draft at verification-only status without handoff/lowering.",
            )
        ]
    if summary.get("verified_claim_count", 0) <= 0:
        return [
            Finding(
                rule="TR000.verified_ledger_bound_claim_required",
                severity="critical",
                target="claims",
                message="Trust Gate handoff/lowering requires at least one verified claim; unverified or hypothesized claims are not sufficient for handoff.",
                suggestion="Promote at least one claim to status=verified and bind it to checked ledger evidence before requesting handoff or lowering.",
            )
        ]
    if summary["evidence_ref_count"] <= 0:
        return [
            Finding(
                rule="TR001.handoff_requires_ledger_bound_evidence",
                severity="critical",
                target=target,
                message="Trust Gate handoff/lowering requires at least one evidence reference bound to the bundled evidence ledger.",
                suggestion="Reference an evidence id present in registries/evidence_ledger.yaml before requesting handoff or lowering.",
            )
        ]
    if summary.get("ledger_bound_checked_verified_evidence_count", 0) <= 0:
        reasons = "; ".join(summary["failed_reasons"][:4])
        return [
            Finding(
                rule="TR001.handoff_requires_ledger_bound_evidence",
                severity="critical",
                target=target,
                message="Trust Gate handoff/lowering requires at least one checked evidence reference bound to a verified claim; none were accepted." + (f" Reasons: {reasons}" if reasons else ""),
                suggestion="Use evidence ids that are checked, trusted, bound to this module/workflow/source artifact, and attached to a verified claim.",
            )
        ]
    unwarranted: list[str] = []
    for claim in draft.claims:
        cid = str(claim.get("id", "<claim>")) if isinstance(claim, Mapping) else "<claim>"
        if not isinstance(claim, Mapping) or str(claim.get("status", "hypothesized")) != "verified":
            unwarranted.append(cid + ": not verified")
            continue
        accepted = False
        for ev in claim.get("evidence", []) or []:
            if isinstance(ev, Mapping) and get_evidence_ledger().decide(ev, claim, draft.module_id, draft.workflow, draft).checked:
                accepted = True
                break
        if not accepted:
            unwarranted.append(cid + ": no checked ledger-bound evidence")
    if unwarranted:
        return [
            Finding(
                rule="TR002.unwarranted_handoff_claim",
                severity="critical",
                target="claims",
                message="Every handoff-visible claim must be verified and bound to checked ledger evidence; unwarranted claims: " + "; ".join(unwarranted[:8]),
                suggestion="Remove, quarantine, or bind every handoff-visible claim before Trust Gate handoff/lowering.",
            )
        ]
    return []
