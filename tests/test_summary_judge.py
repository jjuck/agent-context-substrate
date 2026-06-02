from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.evidence import build_micro_evidence_bundle  # noqa: E402
from agent_context_substrate.models import EvidenceBackedText, MicroSummaryV2, SummaryMetadata, UnitSummaryV2  # noqa: E402
from agent_context_substrate.recovery import RecoveryQualityIssue, RecoveryQualityReport  # noqa: E402
from agent_context_substrate.summary_judge import (  # noqa: E402
    JudgeIssue,
    JudgeVerdict,
    evaluate_summary_with_judge,
    export_summary_judge_verdict,
)
from agent_context_substrate.summary_lint import SummaryLintIssue, SummaryLintReport  # noqa: E402
from agent_context_substrate.summarizer_backends import LLMInputSafetyOptions  # noqa: E402


def _raw_bundle() -> dict[str, object]:
    return {
        "session": {"id": "session-judge", "source": "telegram", "title": "Judge"},
        "messages": [
            {
                "id": 1,
                "role": "user",
                "content": (
                    "Summarize recovery work for README.md. "
                    "api_key=sk-secret-value /home/user/private.py "
                    "```python\nprint('secret code')\n```"
                ),
            },
            {
                "id": 2,
                "role": "assistant",
                "content": "Added Summary Judge planning and the next action is to verify the eval artifact.",
            },
        ],
    }


def _metadata(*, mode: str = "hybrid", schema_version: str) -> SummaryMetadata:
    return SummaryMetadata(
        mode=mode,
        schema_version=schema_version,
        prompt_version="test",
        model=None,
        input_hash="sha256:test",
        created_at="2026-05-27T00:00:00+00:00",
        confidence=0.9,
    )


def _micro_summary() -> MicroSummaryV2:
    return MicroSummaryV2(
        micro_id="packet-judge-micro-1",
        session_id="session-judge",
        message_ids=[1, 2],
        recovery_summary="Recovery context captures the next verification step.",
        knowledge_summary="Summary Judge evaluates semantic quality after mechanical lint.",
        retrieval_summary="Summary Judge README.md recovery verification",
        user_intent="Evaluate summary quality.",
        assistant_outcome="Planned judge artifact export.",
        decisions=[
            EvidenceBackedText(
                text="Use Agent LLM only as an opt-in evaluator.",
                evidence_message_ids=[1, 2],
                confidence=0.9,
            )
        ],
        claims=[],
        action_items=[
            EvidenceBackedText(
                text="Verify the eval artifact path.",
                evidence_message_ids=[2],
                confidence=0.8,
            )
        ],
        files=["README.md"],
        entities=[],
        concepts=["Summary Judge"],
        metadata=_metadata(schema_version="micro_summary_v2"),
    )


def _unit_summary() -> UnitSummaryV2:
    return UnitSummaryV2(
        unit_id="packet-judge-unit-1",
        session_id="session-judge",
        title="Summary Judge",
        goal="Evaluate summary and recovery quality.",
        state="ready_for_review",
        decisions=[
            EvidenceBackedText(
                text="Use Agent LLM only as an opt-in evaluator.",
                evidence_message_ids=[1, 2],
                confidence=0.9,
            )
        ],
        progress=["Planned judge artifact export."],
        next_actions=["Verify the eval artifact path."],
        risk_notes=[],
        wiki_candidates=[],
        micro_ids=["packet-judge-micro-1"],
        related_pages=["README.md"],
        metadata=_metadata(schema_version="unit_summary_v2"),
    )


def _ok_recovery_gate() -> RecoveryQualityReport:
    return RecoveryQualityReport(score=0.83, issues=[])


def test_judge_bypasses_llm_when_mechanical_lint_has_errors() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="packet-judge-micro-1")
    micro_lint = SummaryLintReport(
        issues=[
            SummaryLintIssue(
                code="no_new_files",
                field="files",
                message="summary cites files absent from raw bundle: ['invented.py']",
            )
        ]
    )

    def router(_request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("judge router should be bypassed when mechanical lint fails")

    verdict = evaluate_summary_with_judge(
        packet_id="packet-judge",
        evidence=evidence,
        micro_summary=_micro_summary(),
        unit_summary=_unit_summary(),
        micro_lint=micro_lint,
        unit_lint=SummaryLintReport(issues=[]),
        recovery_quality_gate=_ok_recovery_gate(),
        router=router,
        mode="hybrid",
    )

    assert verdict.decision == "review_required"
    assert verdict.ok is False
    assert verdict.issues == [
        JudgeIssue(
            code="mechanical_lint_failed",
            severity="error",
            field="summary_lint",
            message="Summary judge bypassed because mechanical lint reported: no_new_files",
            evidence_refs=["summary_lint:micro:no_new_files"],
        )
    ]
    assert verdict.metadata["judge_mode"] == "bypassed"


def test_judge_uses_agent_router_and_exports_verdict(tmp_path: Path) -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="packet-judge-micro-1")
    requests: list[dict[str, object]] = []

    def router(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        return {
            "ok": False,
            "score": 0.64,
            "decision": "review_required",
            "issues": [
                {
                    "code": "missing_next_step",
                    "severity": "warning",
                    "field": "unit_summary.next_actions",
                    "message": "The next action is present but too generic for recovery.",
                    "evidence_refs": ["message:2"],
                }
            ],
            "rationale": "Recovery is usable, but the next step should be sharper before wiki promotion.",
            "metadata": {"model": "host-default"},
        }

    verdict = evaluate_summary_with_judge(
        packet_id="packet-judge",
        evidence=evidence,
        micro_summary=_micro_summary(),
        unit_summary=_unit_summary(),
        micro_lint=SummaryLintReport(issues=[]),
        unit_lint=SummaryLintReport(issues=[]),
        recovery_quality_gate=_ok_recovery_gate(),
        router=router,
        mode="hybrid",
        routing_hints={"budget": "quality"},
    )
    export_path = export_summary_judge_verdict(
        packet_id="packet-judge",
        verdict=verdict,
        exports_dir=tmp_path / "exports",
    )

    assert verdict == JudgeVerdict(
        ok=False,
        score=0.64,
        decision="review_required",
        issues=[
            JudgeIssue(
                code="missing_next_step",
                severity="warning",
                field="unit_summary.next_actions",
                message="The next action is present but too generic for recovery.",
                evidence_refs=["message:2"],
            )
        ],
        rationale="Recovery is usable, but the next step should be sharper before wiki promotion.",
        metadata={"model": "host-default", "judge_mode": "hybrid", "schema_version": "summary_judge_v1"},
    )
    assert requests[0]["kind"] == "summary-judge"
    assert requests[0]["routing_hints"] == {"budget": "quality"}
    assert requests[0]["mechanical_lint"]["micro"]["ok"] is True
    assert requests[0]["recovery_quality_gate"] == {"ok": True, "score": 0.83, "issues": []}
    assert export_path == tmp_path / "exports" / "evals" / "packet-judge-summary-judge.json"
    assert json.loads(export_path.read_text(encoding="utf-8")) == verdict.to_dict()


def test_judge_router_failure_degrades_to_mechanical_verdict() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="packet-judge-micro-1")

    def router(_request: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("router unavailable")

    verdict = evaluate_summary_with_judge(
        packet_id="packet-judge",
        evidence=evidence,
        micro_summary=_micro_summary(),
        unit_summary=_unit_summary(),
        micro_lint=SummaryLintReport(issues=[]),
        unit_lint=SummaryLintReport(issues=[]),
        recovery_quality_gate=_ok_recovery_gate(),
        router=router,
        mode="hybrid",
    )

    assert verdict.ok is True
    assert verdict.decision == "accept"
    assert verdict.issues == [
        JudgeIssue(
            code="judge_unavailable",
            severity="warning",
            field="router",
            message="Summary judge router failed; using mechanical lint verdict only: RuntimeError",
            evidence_refs=[],
        )
    ]
    assert verdict.metadata["judge_mode"] == "degraded"


def test_judge_invalid_router_verdict_degrades_to_mechanical_verdict() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="packet-judge-micro-1")

    def router(_request: dict[str, object]) -> dict[str, object]:
        return {
            "ok": False,
            "score": 0.91,
            "decision": "accept",
            "issues": [],
            "rationale": "Claims acceptance while marking the verdict as not ok.",
            "metadata": {},
        }

    verdict = evaluate_summary_with_judge(
        packet_id="packet-judge",
        evidence=evidence,
        micro_summary=_micro_summary(),
        unit_summary=_unit_summary(),
        micro_lint=SummaryLintReport(issues=[]),
        unit_lint=SummaryLintReport(issues=[]),
        recovery_quality_gate=_ok_recovery_gate(),
        router=router,
        mode="hybrid",
    )

    assert verdict.ok is True
    assert verdict.decision == "accept"
    assert verdict.issues == [
        JudgeIssue(
            code="judge_unavailable",
            severity="warning",
            field="router",
            message="Summary judge router failed; using mechanical lint verdict only: ValueError",
            evidence_refs=[],
        )
    ]
    assert verdict.metadata["judge_mode"] == "degraded"


def test_judge_verdict_rejects_internally_contradictory_payloads() -> None:
    valid_payload: dict[str, object] = {
        "ok": True,
        "score": 0.91,
        "decision": "accept",
        "issues": [],
        "rationale": "Grounded enough for alpha evaluation.",
        "metadata": {},
    }
    invalid_payloads = [
        {**valid_payload, "ok": False},
        {**valid_payload, "ok": True, "decision": "review_required"},
        {
            **valid_payload,
            "issues": [
                {
                    "code": "hallucination_risk",
                    "severity": "error",
                    "field": "claims",
                    "message": "The summary contains an unsupported claim.",
                }
            ],
        },
        {**valid_payload, "issues": {"code": "not_a_list"}},
        {**valid_payload, "issues": ["not_an_object"]},
        {
            **valid_payload,
            "issues": [
                {
                    "code": "",
                    "severity": "warning",
                    "field": "claims",
                    "message": "The summary contains an unsupported claim.",
                }
            ],
        },
        {
            **valid_payload,
            "issues": [
                {
                    "code": "hallucination_risk",
                    "severity": "warning",
                    "field": "claims",
                    "message": "",
                }
            ],
        },
        {
            **valid_payload,
            "issues": [
                {
                    "code": "hallucination_risk",
                    "severity": "warning",
                    "field": "claims",
                    "message": "Evidence refs must be a list, not a string.",
                    "evidence_refs": "message:2",
                }
            ],
        },
        {
            **valid_payload,
            "issues": [
                {
                    "code": "hallucination_risk",
                    "severity": "warning",
                    "field": "claims",
                    "message": "Evidence refs must contain strings.",
                    "evidence_refs": [{"message_id": 2}],
                }
            ],
        },
        {**valid_payload, "rationale": "   "},
    ]

    for payload in invalid_payloads:
        try:
            JudgeVerdict.from_dict(payload)
        except ValueError:
            continue
        raise AssertionError(f"payload should have been rejected: {payload!r}")


def test_judge_applies_llm_safety_redaction_and_input_bound() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="packet-judge-micro-1")
    request_json: list[str] = []

    def router(request: dict[str, object]) -> dict[str, object]:
        serialized = json.dumps(request, ensure_ascii=False, sort_keys=True)
        request_json.append(serialized)
        return {
            "ok": True,
            "score": 0.91,
            "decision": "accept",
            "issues": [],
            "rationale": "Grounded enough for alpha evaluation.",
            "metadata": {},
        }

    verdict = evaluate_summary_with_judge(
        packet_id="packet-judge",
        evidence=evidence,
        micro_summary=_micro_summary(),
        unit_summary=_unit_summary(),
        micro_lint=SummaryLintReport(issues=[]),
        unit_lint=SummaryLintReport(issues=[]),
        recovery_quality_gate=RecoveryQualityReport(
            score=0.67,
            issues=[
                RecoveryQualityIssue(
                    code="missing_active_context",
                    severity="warning",
                    message="Recovery brief should include critical files or related pages.",
                )
            ],
        ),
        router=router,
        mode="hybrid",
        llm_safety=LLMInputSafetyOptions(max_input_chars=5_000),
    )

    assert verdict.decision == "accept"
    assert request_json
    assert len(request_json[0]) <= 5_000
    assert "sk-secret-value" not in request_json[0]
    assert "/home/user/private.py" not in request_json[0]
    assert "print('secret code')" not in request_json[0]
    assert "<REDACTED_SECRET>" in request_json[0]
    assert "<REDACTED_LOCAL_PATH>" in request_json[0]
