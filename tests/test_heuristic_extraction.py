from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate import summarizer as summarizer_module  # noqa: E402
from agent_context_substrate.heuristic_extraction import (  # noqa: E402
    analyze_heuristic_messages,
    compose_recovery_summary,
)


def test_analyze_heuristic_messages_pins_recovery_extraction_outputs() -> None:
    messages = [
        {
            "id": 1,
            "role": "user",
            "content": "Please inspect README.md and explain context packet flow.",
        },
        {
            "id": 2,
            "role": "assistant",
            "content": """Done.
- README.md documents the context packet path.
- Hermes keeps recovery context grounded.
Evidence:
- ignored after stop marker
""",
        },
        {
            "id": 3,
            "role": "user",
            "content": "Should we tune summarization next?",
        },
    ]

    analysis = analyze_heuristic_messages(messages)

    assert analysis.files == ["README.md"]
    assert analysis.concepts == ["context-packet", "summarization"]
    assert analysis.entities == ["Hermes"]
    assert analysis.follow_up_questions == ["Should we tune summarization next?"]
    assert analysis.request == "Please inspect README.md and explain context packet flow."
    assert analysis.outcome == "Done."
    assert analysis.key_points == [
        "README.md documents the context packet path.",
        "Hermes keeps recovery context grounded.",
    ]
    assert analysis.recovery_summary == (
        "Request: Please inspect README.md and explain context packet flow. "
        "Outcome: Done. "
        "Key points: README.md documents the context packet path.; Hermes keeps recovery context grounded. "
        "Open question: Should we tune summarization next?"
    )


def test_compose_recovery_summary_is_a_named_stage() -> None:
    messages = [{"role": "assistant", "content": "Fallback transcript text."}]

    assert compose_recovery_summary(
        messages=messages,
        request="Request text",
        outcome="Outcome text",
        key_points=["Point A", "Point B", "Point C", "Point D"],
        follow_up_questions=["Open question?"],
    ) == "Request: Request text Outcome: Outcome text Key points: Point A; Point B; Point C Open question: Open question?"
    assert compose_recovery_summary(
        messages=messages,
        request=None,
        outcome=None,
        key_points=[],
        follow_up_questions=[],
    ) == "Fallback transcript text."


def test_summarizer_no_longer_owns_heuristic_extraction_helpers() -> None:
    duplicate_helpers = [
        "_extract_request",
        "_extract_outcome",
        "_extract_key_points",
        "_extract_follow_up_questions",
        "_extract_files",
        "_extract_entities",
        "_extract_concepts",
        "_build_summary_text",
    ]

    assert [name for name in duplicate_helpers if hasattr(summarizer_module, name)] == []
