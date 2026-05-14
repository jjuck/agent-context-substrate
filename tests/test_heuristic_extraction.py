from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.heuristic_extraction import analyze_heuristic_messages  # noqa: E402


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
