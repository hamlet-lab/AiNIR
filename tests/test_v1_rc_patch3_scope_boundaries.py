from pathlib import Path

from ainir.core import DraftModule
from ainir.verifier import verify_draft

ROOT = Path(__file__).resolve().parents[1]


def test_patch3_scope_docs_exist():
    required = [
        "docs/workflow_registry_extension.md",
        "docs/evidence_provider_interface.md",
        "docs/effect_taxonomy_and_canonical_effects.md",
        "docs/trust_receipt_registry_evolution.md",
        "docs/executable_claim_semantics.md",
        "docs/verified_intent_packet_scope.md",
        "docs/v1_roadmap.md",
        "docs/archive/release-history/v1_rc_candidate_patch3.md",
    ]
    for rel in required:
        assert (ROOT / rel).exists(), rel


def test_unknown_workflow_finding_suggests_profile_registration():
    draft = DraftModule({
        "module": "demo.unknown_workflow",
        "workflow": "UnknownWorkflow",
        "task": "UnknownWorkflow",
        "operations": [
            {
                "id": "op.noop",
                "op": "data.noop",
                "effects": [],
                "capabilities": [],
            }
        ],
    })
    report = verify_draft(draft)
    finding = next(f for f in report.findings if f.rule == "W001.unknown_workflow")
    assert finding.severity == "critical"
    assert finding.suggestion
    assert "Register a workflow profile" in finding.suggestion


def test_readme_declares_bounded_public_scope():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "bounded public demo scope" in text.lower()
    assert "closed-world" in text.lower()
    assert "workflow registry" in text.lower()
