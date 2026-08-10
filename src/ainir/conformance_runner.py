"""Standalone Profile Manifest v1 conformance runner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Mapping
from xml.etree import ElementTree as ET

import yaml

from .canonical import canonical_json, sha256_json
from .contracts import CONFORMANCE_REPORT_CONTRACT, CONFORMANCE_REPORT_KIND
from .core import dump_yaml, load_draft, load_yaml_no_duplicate_keys
from .execution_context import TrustedExecutionContext
from .golden_trace_harness import run_golden_traces
from .negative_conformance_harness import run_negative_conformance_corpus
from .profile_manifest import (
    CONFORMANCE_PACK_CONTRACT,
    CONFORMANCE_PACK_KIND,
    LoadedProfileManifest,
    ProfileManifestError,
    validate_profile_manifest,
)
from .profile_runtime import compile_profile, profile_registry_context
from .trust_gate import evaluate_trust_gate
from .trust_receipt_store import issue_trust_receipt, replay_trust_receipt

_ALLOWED_CATEGORIES = {"positive", "negative", "mutation", "replay"}
_MUTATION_PREFIXES = (
    "safety_critical_effect_suffix_variants",
    "provider_source_evidence_variants",
    "hidden_operation_effectless_variants",
)


@dataclass(frozen=True)
class ConformanceCaseResult:
    case_id: str
    category: str
    passed: bool
    expected_trust_status: str | None
    actual_trust_status: str | None
    lowering_allowed: bool | None
    receipt_replay_status: str
    finding_rules: tuple[str, ...] = ()
    notes: str = ""
    source: str = "generic"
    receipt_id: str | None = None
    receipt_projection_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "expected_trust_status": self.expected_trust_status,
            "actual_trust_status": self.actual_trust_status,
            "lowering_allowed": self.lowering_allowed,
            "receipt_replay_status": self.receipt_replay_status,
            "finding_rules": list(self.finding_rules),
            "notes": self.notes,
            "source": self.source,
            "receipt_id": self.receipt_id,
            "receipt_projection_hash": self.receipt_projection_hash,
        }


@dataclass(frozen=True)
class ConformanceRunReport:
    profile_id: str
    profile_version: str
    manifest_sha256: str
    registry_mode: str
    registry_snapshot_hash: str
    results: tuple[ConformanceCaseResult, ...]
    output_dir: str
    source_pack: str
    production_runtime_ready: bool = False

    @property
    def overall_status(self) -> str:
        return "passed" if self.results and all(result.passed for result in self.results) else "failed"

    def as_dict(self) -> dict[str, Any]:
        category_counts: dict[str, dict[str, int]] = {
            category: {"total": 0, "passed": 0, "failed": 0}
            for category in sorted(_ALLOWED_CATEGORIES)
        }
        for result in self.results:
            if result.category in category_counts:
                category_counts[result.category]["total"] += 1
                category_counts[result.category]["passed" if result.passed else "failed"] += 1
            if result.receipt_replay_status in {"passed", "failed"} and result.category != "replay":
                category_counts["replay"]["total"] += 1
                category_counts["replay"]["passed" if result.receipt_replay_status == "passed" else "failed"] += 1
        payload = {
            "kind": CONFORMANCE_REPORT_KIND,
            "version": CONFORMANCE_REPORT_CONTRACT,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "manifest_sha256": self.manifest_sha256,
            "registry_mode": self.registry_mode,
            "registry_snapshot_hash": self.registry_snapshot_hash,
            "source_pack": self.source_pack,
            "overall_status": self.overall_status,
            "case_count": len(self.results),
            "passed": sum(1 for result in self.results if result.passed),
            "failed": sum(1 for result in self.results if not result.passed),
            "category_counts": category_counts,
            "results": [result.as_dict() for result in self.results],
            "output_dir": self.output_dir,
            "production_runtime_ready": self.production_runtime_ready,
        }
        stable = {key: value for key, value in payload.items() if key not in {"output_dir", "report_sha256"}}
        payload["report_sha256"] = sha256_json(stable)
        return payload


class ConformancePackError(ValueError):
    """Raised when a conformance pack is malformed or unsafe to load."""


def _load_pack(path: Path, profile_id: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = load_yaml_no_duplicate_keys(raw)
    except Exception as exc:
        raise ConformancePackError(f"cannot load conformance pack {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConformancePackError("conformance pack root must be an object")
    if data.get("kind") != CONFORMANCE_PACK_KIND:
        raise ConformancePackError(f"conformance pack kind must be {CONFORMANCE_PACK_KIND}")
    if data.get("version") != CONFORMANCE_PACK_CONTRACT:
        raise ConformancePackError(f"conformance pack version must be {CONFORMANCE_PACK_CONTRACT}")
    if data.get("profile_id") != profile_id:
        raise ConformancePackError(
            f"conformance pack profile_id {data.get('profile_id')!r} does not match manifest {profile_id!r}"
        )
    cases = data.get("cases", [])
    sources = data.get("sources", [])
    if not isinstance(cases, list) or not isinstance(sources, list):
        raise ConformancePackError("conformance pack cases and sources must be arrays")
    seen: set[str] = set()
    for collection_name, collection in (("case", cases), ("source", sources)):
        for index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                raise ConformancePackError(f"{collection_name} at index {index} must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ConformancePackError(f"{collection_name} at index {index} has no id")
            combined = f"{collection_name}:{item_id}"
            if combined in seen:
                raise ConformancePackError(f"duplicate {collection_name} id {item_id!r}")
            seen.add(combined)
            if collection_name == "case" and item.get("category") not in _ALLOWED_CATEGORIES:
                raise ConformancePackError(f"case {item_id!r} has invalid category {item.get('category')!r}")
            if collection_name == "source" and item.get("type") not in {"golden_traces", "negative_corpus"}:
                raise ConformancePackError(f"source {item_id!r} has unsupported type {item.get('type')!r}")
    return data


def _safe_child(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConformancePackError(f"{label} must be a relative path string")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ConformancePackError(f"{label} must not be absolute")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ConformancePackError(f"{label} escapes the profile directory") from exc
    return resolved


def _draft_path_for_case(case: Mapping[str, Any], root: Path, case_dir: Path) -> Path:
    present = [key for key in ("draft", "raw_yaml", "draft_ref") if key in case]
    if len(present) != 1:
        raise ConformancePackError(f"case {case.get('id')!r} must define exactly one of draft, raw_yaml, or draft_ref")
    if "draft_ref" in case:
        path = _safe_child(root, case.get("draft_ref"), f"case {case.get('id')} draft_ref")
        if not path.exists():
            raise ConformancePackError(f"case draft_ref does not exist: {path}")
        return path
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / "draft.yaml"
    if "raw_yaml" in case:
        value = case.get("raw_yaml")
        if not isinstance(value, str):
            raise ConformancePackError(f"case {case.get('id')!r} raw_yaml must be a string")
        path.write_text(value, encoding="utf-8")
    else:
        value = case.get("draft")
        if not isinstance(value, Mapping):
            raise ConformancePackError(f"case {case.get('id')!r} draft must be an object")
        path.write_text(yaml.safe_dump(dict(value), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _case_result(case: Mapping[str, Any], root: Path, out_dir: Path, environment: str) -> ConformanceCaseResult:
    case_id = str(case.get("id"))
    category = str(case.get("category"))
    case_dir = out_dir / "cases" / _safe_name(case_id)
    draft_path = _draft_path_for_case(case, root, case_dir)
    expected = case.get("expected") if isinstance(case.get("expected"), Mapping) else {}
    expected_status = expected.get("trust_status")
    if expected_status is not None and expected_status not in {"passed", "refused", "invalid"}:
        raise ConformancePackError(f"case {case_id!r} expected trust_status is invalid")
    context = TrustedExecutionContext.from_environment(
        environment,
        source="profile_conformance",
        purpose="case:" + _safe_name(case_id),
    )
    draft = load_draft(draft_path)
    decision = evaluate_trust_gate(draft, context).as_dict()
    actual_status = str(decision.get("status"))
    actual_lowering = bool(decision.get("lowering_allowed"))
    findings = decision.get("findings") if isinstance(decision.get("findings"), list) else []
    finding_rules = tuple(sorted({str(item.get("rule")) for item in findings if isinstance(item, Mapping) and item.get("rule")}))
    required_rules = {str(item) for item in expected.get("required_findings", []) or []}
    forbidden_rules = {str(item) for item in expected.get("forbidden_findings", []) or []}
    status_ok = expected_status is None or actual_status == expected_status
    lowering_expected = expected.get("lowering_allowed")
    lowering_ok = lowering_expected is None or actual_lowering == bool(lowering_expected)
    required_ok = required_rules.issubset(set(finding_rules))
    forbidden_ok = not (forbidden_rules & set(finding_rules))

    replay_expected = expected.get("receipt_replay")
    replay_status = "not_requested"
    receipt_id = None
    projection_hash = None
    replay_ok = True
    if replay_expected is not None:
        receipt_dir = case_dir / "receipt"
        issued = issue_trust_receipt(draft_path, receipt_dir, context)
        receipt_id = str(issued.receipt.get("receipt_id"))
        projection_hash = issued.receipt.get("stable_receipt_projection_hash")
        replay = replay_trust_receipt(issued.receipt_path, draft_path, context)
        replay_status = "passed" if replay.overall_status == "passed" else "failed"
        replay_ok = (replay_status == "passed") == bool(replay_expected)
        (case_dir / "replay_report.json").write_text(
            json.dumps(replay.as_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    notes: list[str] = []
    if not status_ok:
        notes.append(f"expected trust status {expected_status!r}, got {actual_status!r}")
    if not lowering_ok:
        notes.append(f"expected lowering_allowed={lowering_expected!r}, got {actual_lowering!r}")
    if not required_ok:
        notes.append(f"missing required findings {sorted(required_rules - set(finding_rules))}")
    if not forbidden_ok:
        notes.append(f"forbidden findings present {sorted(forbidden_rules & set(finding_rules))}")
    if not replay_ok:
        notes.append(f"receipt replay expectation {replay_expected!r} did not match {replay_status}")

    (case_dir / "decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return ConformanceCaseResult(
        case_id=case_id,
        category=category,
        passed=status_ok and lowering_ok and required_ok and forbidden_ok and replay_ok,
        expected_trust_status=str(expected_status) if expected_status is not None else None,
        actual_trust_status=actual_status,
        lowering_allowed=actual_lowering,
        receipt_replay_status=replay_status,
        finding_rules=finding_rules,
        notes="; ".join(notes),
        source="generic",
        receipt_id=receipt_id,
        receipt_projection_hash=str(projection_hash) if projection_hash is not None else None,
    )


def _adapt_golden(source_id: str, summary: Mapping[str, Any]) -> list[ConformanceCaseResult]:
    results: list[ConformanceCaseResult] = []
    for item in summary.get("results", []) or []:
        if not isinstance(item, Mapping):
            continue
        expected = str(item.get("expected_status"))
        actual = str(item.get("actual_status"))
        replay_status = "passed" if item.get("trust_receipt_status") == "replayed" else "failed"
        results.append(ConformanceCaseResult(
            case_id=str(item.get("trace_id")),
            category="positive" if expected == "passed" else "negative",
            passed=bool(item.get("passed")),
            expected_trust_status="passed" if expected == "passed" else None,
            actual_trust_status="passed" if actual == "passed" else "refused",
            lowering_allowed=item.get("lowering_status") == "lowered",
            receipt_replay_status=replay_status,
            notes=str(item.get("notes") or ""),
            source=f"golden_traces:{source_id}",
            receipt_id=str(item.get("receipt_id")) if item.get("receipt_id") else None,
        ))
    return results


def _adapt_negative(source_id: str, summary: Mapping[str, Any]) -> list[ConformanceCaseResult]:
    results: list[ConformanceCaseResult] = []
    for item in summary.get("results", []) or []:
        if not isinstance(item, Mapping):
            continue
        case_id = str(item.get("case_id"))
        category = "mutation" if case_id.startswith(_MUTATION_PREFIXES) else "negative"
        expected = str(item.get("expected_status"))
        actual = str(item.get("actual_status"))
        results.append(ConformanceCaseResult(
            case_id=case_id,
            category=category,
            passed=bool(item.get("passed")),
            expected_trust_status="invalid" if expected == "invalid" else None,
            actual_trust_status="invalid" if actual == "invalid" else ("passed" if actual == "passed" else "refused"),
            lowering_allowed=not bool(item.get("lowering_refused")),
            receipt_replay_status="not_requested",
            notes=str(item.get("notes") or ""),
            source=f"negative_corpus:{source_id}",
        ))
    return results


def _run_source(source: Mapping[str, Any], root: Path, out_dir: Path, environment: str) -> list[ConformanceCaseResult]:
    source_id = str(source.get("id"))
    source_type = str(source.get("type"))
    path = _safe_child(root, source.get("path"), f"source {source_id} path")
    if not path.exists():
        raise ConformancePackError(f"source file does not exist: {path}")
    source_out = out_dir / "sources" / _safe_name(source_id)
    if source_type == "golden_traces":
        return _adapt_golden(source_id, run_golden_traces(path, source_out, environment))
    if source_type == "negative_corpus":
        return _adapt_negative(source_id, run_negative_conformance_corpus(path, source_out, environment))
    raise ConformancePackError(f"unsupported source type {source_type!r}")


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:120]


def _write_jsonl(report: Mapping[str, Any], path: Path) -> None:
    lines = [
        {"record_type": "header", **{key: report.get(key) for key in ("kind", "version", "profile_id", "manifest_sha256", "registry_snapshot_hash")}},
    ]
    lines.extend({"record_type": "case", **item} for item in report.get("results", []) or [])
    lines.append({
        "record_type": "summary",
        **{key: report.get(key) for key in ("overall_status", "case_count", "passed", "failed", "report_sha256")},
    })
    path.write_text("".join(canonical_json(line) + "\n" for line in lines), encoding="utf-8")


def _write_junit(report: Mapping[str, Any], path: Path) -> None:
    suite = ET.Element(
        "testsuite",
        {
            "name": f"AiNIR profile {report.get('profile_id')}",
            "tests": str(report.get("case_count", 0)),
            "failures": str(report.get("failed", 0)),
        },
    )
    for item in report.get("results", []) or []:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": str(item.get("category", "conformance")),
                "name": str(item.get("case_id", "unknown")),
            },
        )
        if not item.get("passed"):
            failure = ET.SubElement(case, "failure", {"message": str(item.get("notes") or "conformance mismatch")})
            failure.text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        output = ET.SubElement(case, "system-out")
        output.text = json.dumps(item, ensure_ascii=False, sort_keys=True)
    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def run_profile_conformance(
    manifest: LoadedProfileManifest,
    *,
    out_dir: str | Path,
    environment: str = "public_demo",
) -> ConformanceRunReport:
    validation = validate_profile_manifest(manifest)
    if not validation.valid:
        raise ProfileManifestError(
            "profile validation failed: " + "; ".join(f"{issue.code}@{issue.path}" for issue in validation.issues[:12])
        )
    compiled = compile_profile(manifest)
    conformance = manifest.data.get("conformance") if isinstance(manifest.data.get("conformance"), Mapping) else {}
    pack_path = _safe_child(manifest.root, conformance.get("pack"), "conformance.pack")
    pack = _load_pack(pack_path, manifest.profile_id)
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[ConformanceCaseResult] = []

    with profile_registry_context(compiled):
        for source in pack.get("sources", []) or []:
            results.extend(_run_source(source, manifest.root, output, environment))
        for case in pack.get("cases", []) or []:
            results.append(_case_result(case, manifest.root, output, environment))

    registry_hash = (
        str(compiled.bundle.snapshot.get("combined_sha256"))
        if compiled.bundle is not None
        else compiled.base_snapshot_hash
    )
    report = ConformanceRunReport(
        profile_id=manifest.profile_id,
        profile_version=str(manifest.data.get("profile_version")),
        manifest_sha256=manifest.canonical_sha256,
        registry_mode=compiled.registry_mode,
        registry_snapshot_hash=registry_hash,
        results=tuple(results),
        output_dir=str(output),
        source_pack=str(pack_path),
    )
    payload = report.as_dict()
    (output / "conformance_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_jsonl(payload, output / "conformance_report.jsonl")
    _write_junit(payload, output / "conformance_report.junit.xml")
    dump_yaml(payload, output / "conformance_report.yaml")
    return report


def render_conformance_report(report: ConformanceRunReport, format_name: str) -> str:
    payload = report.as_dict()
    if format_name == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if format_name == "jsonl":
        lines = [
            canonical_json({"record_type": "case", **item})
            for item in payload.get("results", []) or []
        ]
        lines.append(canonical_json({
            "record_type": "summary",
            "overall_status": payload.get("overall_status"),
            "case_count": payload.get("case_count"),
            "passed": payload.get("passed"),
            "failed": payload.get("failed"),
            "report_sha256": payload.get("report_sha256"),
        }))
        return "\n".join(lines) + "\n"
    if format_name == "junit":
        return Path(report.output_dir, "conformance_report.junit.xml").read_text(encoding="utf-8")
    lines = [
        f"AiNIR profile conformance: {payload['overall_status']}",
        f"profile: {payload['profile_id']} version={payload['profile_version']}",
        f"cases: {payload['case_count']} passed={payload['passed']} failed={payload['failed']}",
        f"registry_snapshot_hash: {payload['registry_snapshot_hash']}",
    ]
    for item in payload.get("results", []) or []:
        marker = "PASS" if item.get("passed") else "FAIL"
        lines.append(f"[{marker}] {item.get('category')} {item.get('case_id')} {item.get('notes') or ''}".rstrip())
    lines.append(f"reports: {report.output_dir}")
    return "\n".join(lines) + "\n"


__all__ = [
    "CONFORMANCE_REPORT_CONTRACT",
    "CONFORMANCE_REPORT_KIND",
    "ConformanceCaseResult",
    "ConformancePackError",
    "ConformanceRunReport",
    "render_conformance_report",
    "run_profile_conformance",
]
