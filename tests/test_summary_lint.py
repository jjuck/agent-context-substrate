from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.models import EvidenceBackedText, UnitSummaryV2  # noqa: E402
from agent_context_substrate.summarizer import build_micro_summary_v2, build_unit_summary_v2  # noqa: E402
from agent_context_substrate.summary_lint import lint_micro_summary_v2, lint_unit_summary_v2  # noqa: E402


def _raw_bundle() -> dict:
    return {
        "session": {"id": "session-lint", "source": "telegram", "title": "Summary lint"},
        "messages": [
            {"id": 1, "role": "user", "content": "Update README.md"},
            {"id": 2, "role": "assistant", "content": "Done.\n- Updated README.md"},
        ],
    }


def test_lint_micro_summary_v2_accepts_grounded_heuristic_summary() -> None:
    summary = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-lint")

    report = lint_micro_summary_v2(summary, raw_bundle=_raw_bundle())

    assert report.ok is True
    assert report.issue_count == 0
    assert report.issues == []


def test_lint_micro_summary_v2_reports_missing_and_invalid_evidence() -> None:
    summary = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-lint")
    bad_summary = replace(
        summary,
        decisions=[
            EvidenceBackedText(
                text="Decision without evidence",
                evidence_message_ids=[],
                confidence=0.5,
            ),
            EvidenceBackedText(
                text="Decision with invented message id",
                evidence_message_ids=[999],
                confidence=0.5,
            ),
        ],
    )

    report = lint_micro_summary_v2(bad_summary, raw_bundle=_raw_bundle())

    assert report.ok is False
    assert [issue.code for issue in report.issues] == ["evidence_required", "evidence_exists"]


def test_lint_micro_summary_v2_reports_invented_files_and_empty_summaries() -> None:
    summary = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-lint")
    bad_summary = replace(
        summary,
        recovery_summary="",
        knowledge_summary="",
        retrieval_summary="",
        files=["README.md", "invented.py"],
    )

    report = lint_micro_summary_v2(bad_summary, raw_bundle=_raw_bundle())

    assert report.ok is False
    assert [issue.code for issue in report.issues] == ["summary_not_empty", "no_new_files"]


def test_lint_unit_summary_v2_accepts_grounded_heuristic_unit_summary() -> None:
    micro = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-lint")
    unit = build_unit_summary_v2(
        unit_id="unit-lint",
        session_id="session-lint",
        title="Summary lint",
        goal="Verify summary lint.",
        micro_summaries=[micro],
    )

    report = lint_unit_summary_v2(unit, micro_summaries=[micro])

    assert report.ok is True
    assert report.issues == []


def test_lint_unit_summary_v2_reports_unknown_micro_ids_and_invalid_evidence() -> None:
    micro = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-lint")
    bad_unit = UnitSummaryV2(
        unit_id="unit-lint",
        session_id="session-lint",
        title="Summary lint",
        goal="Verify summary lint.",
        state="completed",
        decisions=[EvidenceBackedText(text="Invented evidence", evidence_message_ids=[999], confidence=0.5)],
        wiki_candidates=[EvidenceBackedText(text="No evidence", evidence_message_ids=[], confidence=0.5)],
        micro_ids=["micro-lint", "invented-micro"],
    )

    report = lint_unit_summary_v2(bad_unit, micro_summaries=[micro])

    assert report.ok is False
    assert [issue.code for issue in report.issues] == [
        "evidence_exists",
        "evidence_required",
        "micro_reference_exists",
    ]
