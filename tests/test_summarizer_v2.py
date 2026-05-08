from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.models import MicroSummaryV2, UnitSummaryV2  # noqa: E402
from agent_context_substrate.summarizer import (  # noqa: E402
    build_micro_summary_v2,
    build_unit_summary_v2,
)


def _raw_bundle() -> dict:
    return {
        "session": {
            "id": "session-v2",
            "source": "telegram",
            "title": "Hybrid summarizer design",
            "started_at": 1776395277.0,
            "ended_at": None,
        },
        "messages": [
            {
                "id": 20,
                "role": "user",
                "content": "Design hybrid summarization around README.md and summary-lint.",
            },
            {
                "id": 21,
                "role": "assistant",
                "content": (
                    "Proposed the design.\n\n"
                    "- Keep heuristic extraction as the evidence pass\n"
                    "- Add structured summaries for recovery, knowledge, and retrieval\n"
                    "- Add summary-lint before accepting LLM output"
                ),
            },
            {
                "id": 22,
                "role": "user",
                "content": "Which provider should be first?",
            },
        ],
    }


def test_build_micro_summary_v2_from_heuristics() -> None:
    summary = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-v2")

    assert isinstance(summary, MicroSummaryV2)
    assert summary.micro_id == "micro-v2"
    assert summary.session_id == "session-v2"
    assert summary.message_ids == [20, 21, 22]
    assert summary.user_intent == "Design hybrid summarization around README.md and summary-lint."
    assert summary.assistant_outcome == "Proposed the design."
    assert summary.recovery_summary.startswith("Request: Design hybrid summarization")
    assert "heuristic extraction" in summary.knowledge_summary
    assert "README.md" in summary.retrieval_summary
    assert "summary-lint" in summary.retrieval_summary
    assert summary.decisions[0].text == "Keep heuristic extraction as the evidence pass"
    assert summary.decisions[0].evidence_message_ids == [20, 21, 22]
    assert summary.open_questions == ["Which provider should be first?"]
    assert summary.metadata.mode == "heuristic"
    assert summary.metadata.schema_version == "micro_summary_v2"
    assert summary.metadata.input_hash.startswith("sha256:")
    assert summary.provenance is not None

    assert MicroSummaryV2.from_dict(summary.to_dict()) == summary


def test_build_unit_summary_v2_from_micro_summaries() -> None:
    micro = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-v2")

    unit = build_unit_summary_v2(
        unit_id="unit-v2",
        session_id="session-v2",
        title="Design hybrid summarizer",
        goal="Separate evidence extraction from semantic summarization.",
        micro_summaries=[micro],
        related_pages=["01 지식/Agent Context Substrate.md"],
    )

    assert isinstance(unit, UnitSummaryV2)
    assert unit.unit_id == "unit-v2"
    assert unit.state == "in_progress"
    assert unit.decisions == micro.decisions
    assert unit.progress == [micro.assistant_outcome]
    assert unit.next_actions == []
    assert unit.open_questions == ["Which provider should be first?"]
    assert unit.wiki_candidates == micro.claims
    assert unit.micro_ids == ["micro-v2"]
    assert unit.related_pages == ["01 지식/Agent Context Substrate.md"]
    assert unit.metadata.schema_version == "unit_summary_v2"

    assert UnitSummaryV2.from_dict(unit.to_dict()) == unit
