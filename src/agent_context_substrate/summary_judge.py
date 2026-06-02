from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
import json
from pathlib import Path
from typing import Any

from .models import MicroEvidenceBundle, MicroSummaryV2, UnitSummaryV2
from .recovery import RecoveryQualityReport
from .safe_paths import safe_artifact_stem, safe_child_path
from .summarizer_backends import AgentLLMRouter, LLMInputSafetyOptions, _call_router_with_json_repair
from .summary_lint import SummaryLintReport


JUDGE_DECISIONS = {"accept", "review_required", "fallback_to_heuristic", "revise_summary"}
JUDGE_SEVERITIES = {"info", "warning", "error"}
SUMMARY_JUDGE_SCHEMA_VERSION = "summary_judge_v1"


@dataclass(frozen=True)
class JudgeIssue:
    code: str
    severity: str
    field: str
    message: str
    evidence_refs: list[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JudgeIssue":
        if not isinstance(payload, dict):
            raise ValueError("summary judge issue must be an object")
        severity = str(payload.get("severity", "warning"))
        if severity not in JUDGE_SEVERITIES:
            severity = "warning"
        code = str(payload.get("code", ""))
        message = str(payload.get("message", ""))
        if not code.strip():
            raise ValueError("summary judge issue code must be non-empty")
        if not message.strip():
            raise ValueError("summary judge issue message must be non-empty")
        evidence_refs = payload.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            raise ValueError("summary judge issue evidence_refs must be a list")
        if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
            raise ValueError("summary judge issue evidence_refs must contain non-empty strings")
        return cls(
            code=code,
            severity=severity,
            field=str(payload.get("field", "")),
            message=message,
            evidence_refs=list(evidence_refs),
        )


@dataclass(frozen=True)
class JudgeVerdict:
    ok: bool
    score: float
    decision: str
    issues: list[JudgeIssue]
    rationale: str
    metadata: dict[str, object] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "score": self.score,
            "decision": self.decision,
            "issues": [issue.to_dict() for issue in self.issues],
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JudgeVerdict":
        decision = str(payload["decision"])
        if decision not in JUDGE_DECISIONS:
            raise ValueError(f"Unsupported summary judge decision: {decision}")
        ok = _coerce_bool(payload.get("ok"), default=decision == "accept")
        if (decision == "accept") != ok:
            raise ValueError("summary judge ok must match accept decision")
        raw_issues = payload.get("issues", [])
        if not isinstance(raw_issues, list):
            raise ValueError("summary judge issues must be a list")
        issues = [JudgeIssue.from_dict(item) for item in raw_issues]
        if decision == "accept" and any(issue.severity == "error" for issue in issues):
            raise ValueError("summary judge accept decision cannot include error severity issues")
        rationale = str(payload.get("rationale", ""))
        if not rationale.strip():
            raise ValueError("summary judge rationale must be non-empty")
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("judge_mode", "hybrid")
        metadata.setdefault("schema_version", SUMMARY_JUDGE_SCHEMA_VERSION)
        return cls(
            ok=ok,
            score=_coerce_score(payload["score"]),
            decision=decision,
            issues=issues,
            rationale=rationale,
            metadata=metadata,
        )


def evaluate_summary_with_judge(
    *,
    packet_id: str,
    evidence: MicroEvidenceBundle,
    micro_summary: MicroSummaryV2,
    unit_summary: UnitSummaryV2,
    micro_lint: SummaryLintReport,
    unit_lint: SummaryLintReport,
    recovery_quality_gate: RecoveryQualityReport | None = None,
    router: AgentLLMRouter | None = None,
    mode: str = "off",
    routing_hints: dict[str, object] | None = None,
    llm_safety: LLMInputSafetyOptions | None = None,
) -> JudgeVerdict:
    """Evaluate summary quality with an opt-in Agent LLM judge.

    The judge never mutates summaries or wiki files. It only returns a verdict
    suitable for export under data/exports/evals.
    """

    normalized_mode = (mode or "off").strip().lower()
    if normalized_mode not in {"off", "hybrid"}:
        raise ValueError("summary judge mode must be one of: off, hybrid")

    if not micro_lint.ok or not unit_lint.ok:
        return _mechanical_lint_bypass_verdict(micro_lint=micro_lint, unit_lint=unit_lint)

    if normalized_mode == "off":
        return _mechanical_verdict(
            recovery_quality_gate=recovery_quality_gate,
            metadata={"judge_mode": "off", "schema_version": SUMMARY_JUDGE_SCHEMA_VERSION},
        )

    if router is None:
        return _mechanical_verdict(
            recovery_quality_gate=recovery_quality_gate,
            extra_issues=[
                JudgeIssue(
                    code="judge_unavailable",
                    severity="warning",
                    field="router",
                    message="Summary judge router was not provided; using mechanical lint verdict only.",
                )
            ],
            metadata={"judge_mode": "degraded", "schema_version": SUMMARY_JUDGE_SCHEMA_VERSION},
        )

    request = _build_judge_request(
        packet_id=packet_id,
        evidence=evidence,
        micro_summary=micro_summary,
        unit_summary=unit_summary,
        micro_lint=micro_lint,
        unit_lint=unit_lint,
        recovery_quality_gate=recovery_quality_gate,
        routing_hints=dict(routing_hints or {}),
    )
    try:
        payload = _call_router_with_json_repair(
            router=router,
            request=request,
            safety=llm_safety or LLMInputSafetyOptions(),
            error_label="Summary judge router",
        )
        return JudgeVerdict.from_dict(payload)
    except Exception as exc:
        return _mechanical_verdict(
            recovery_quality_gate=recovery_quality_gate,
            extra_issues=[
                JudgeIssue(
                    code="judge_unavailable",
                    severity="warning",
                    field="router",
                    message=f"Summary judge router failed; using mechanical lint verdict only: {type(exc).__name__}",
                )
            ],
            metadata={"judge_mode": "degraded", "schema_version": SUMMARY_JUDGE_SCHEMA_VERSION},
        )


def export_summary_judge_verdict(*, packet_id: str, verdict: JudgeVerdict, exports_dir: Path) -> Path:
    safe_packet_id = safe_artifact_stem(packet_id, label="packet id")
    eval_dir = Path(exports_dir) / "evals"
    eval_dir.mkdir(parents=True, exist_ok=True)
    export_path = safe_child_path(eval_dir, f"{safe_packet_id}-summary-judge", ".json", label="judge artifact id")
    export_path.write_text(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return export_path


def _build_judge_request(
    *,
    packet_id: str,
    evidence: MicroEvidenceBundle,
    micro_summary: MicroSummaryV2,
    unit_summary: UnitSummaryV2,
    micro_lint: SummaryLintReport,
    unit_lint: SummaryLintReport,
    recovery_quality_gate: RecoveryQualityReport | None,
    routing_hints: dict[str, object],
) -> dict[str, object]:
    return {
        "kind": "summary-judge",
        "schema_version": SUMMARY_JUDGE_SCHEMA_VERSION,
        "packet_id": packet_id,
        "evaluation_contract": {
            "decisions": sorted(JUDGE_DECISIONS),
            "instruction": (
                "Judge recovery usefulness, hallucination risk, missing next steps, and wiki candidate noise. "
                "Return strict JSON with ok, score, decision, issues, rationale, and metadata. "
                "Do not rewrite the summary or propose wiki writes."
            ),
        },
        "mechanical_lint": {
            "micro": micro_lint.to_dict(),
            "unit": unit_lint.to_dict(),
        },
        "recovery_quality_gate": recovery_quality_gate.to_dict() if recovery_quality_gate else None,
        "evidence": evidence.to_dict(),
        "micro_summary": micro_summary.to_dict(),
        "unit_summary": unit_summary.to_dict(),
        "routing_hints": dict(routing_hints),
    }


def _mechanical_lint_bypass_verdict(*, micro_lint: SummaryLintReport, unit_lint: SummaryLintReport) -> JudgeVerdict:
    refs = _lint_issue_refs(micro_lint=micro_lint, unit_lint=unit_lint)
    codes = ", ".join(ref.rsplit(":", 1)[-1] for ref in refs)
    return JudgeVerdict(
        ok=False,
        score=0.0,
        decision="review_required",
        issues=[
            JudgeIssue(
                code="mechanical_lint_failed",
                severity="error",
                field="summary_lint",
                message=f"Summary judge bypassed because mechanical lint reported: {codes}",
                evidence_refs=refs,
            )
        ],
        rationale="Mechanical summary lint failed, so semantic judging was bypassed.",
        metadata={"judge_mode": "bypassed", "schema_version": SUMMARY_JUDGE_SCHEMA_VERSION},
    )


def _mechanical_verdict(
    *,
    recovery_quality_gate: RecoveryQualityReport | None,
    extra_issues: list[JudgeIssue] | None = None,
    metadata: dict[str, object] | None = None,
) -> JudgeVerdict:
    issues = list(extra_issues or [])
    recovery_ok = recovery_quality_gate is None or recovery_quality_gate.ok
    if recovery_quality_gate is not None and not recovery_quality_gate.ok:
        issues.append(_recovery_quality_issue(recovery_quality_gate))
    decision = "accept" if recovery_ok else "review_required"
    return JudgeVerdict(
        ok=decision == "accept",
        score=1.0 if recovery_quality_gate is None else recovery_quality_gate.score,
        decision=decision,
        issues=issues,
        rationale="Mechanical summary lint passed; no semantic judge verdict was available.",
        metadata=dict(metadata or {}),
    )


def _recovery_quality_issue(report: RecoveryQualityReport) -> JudgeIssue:
    refs = [f"recovery_quality_gate:{issue.code}" for issue in report.issues]
    severities = {issue.severity for issue in report.issues}
    severity = "error" if "error" in severities else "warning"
    return JudgeIssue(
        code="recovery_quality_gate_failed",
        severity=severity,
        field="recovery_quality_gate",
        message=f"Recovery quality gate score {report.score} is below alpha usefulness expectations.",
        evidence_refs=refs,
    )


def _lint_issue_refs(*, micro_lint: SummaryLintReport, unit_lint: SummaryLintReport) -> list[str]:
    refs: list[str] = []
    refs.extend(f"summary_lint:micro:{issue.code}" for issue in micro_lint.issues)
    refs.extend(f"summary_lint:unit:{issue.code}" for issue in unit_lint.issues)
    return refs


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"summary judge score must be numeric, got {value!r}")
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"summary judge score must be between 0.0 and 1.0, got {score}")
    return score
