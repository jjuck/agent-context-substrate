from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate import heuristic_extraction as heuristic_module  # noqa: E402
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


def test_heuristic_stages_live_in_dedicated_modules() -> None:
    from agent_context_substrate.heuristic_composition import (
        compose_recovery_summary as module_compose_recovery_summary,
    )
    from agent_context_substrate.heuristic_metadata import (
        HeuristicMetadataSignals,
        extract_metadata_signals as module_extract_metadata_signals,
    )
    from agent_context_substrate.heuristic_recovery import (
        HeuristicRecoveryFields,
        extract_recovery_fields as module_extract_recovery_fields,
    )

    assert module_extract_metadata_signals is heuristic_module.extract_metadata_signals
    assert module_extract_recovery_fields is heuristic_module.extract_recovery_fields
    assert module_compose_recovery_summary is compose_recovery_summary
    assert HeuristicMetadataSignals is heuristic_module.HeuristicMetadataSignals
    assert HeuristicRecoveryFields is heuristic_module.HeuristicRecoveryFields


def test_extract_metadata_signals_is_a_named_stage() -> None:
    messages = [
        {"role": "system", "content": "ignore setup chatter"},
        {"role": "user", "content": "Inspect README.md and src/app.py for context packet flow."},
        {"role": "assistant", "content": "Hermes summarization keeps recovery grounded."},
    ]

    signals = heuristic_module.extract_metadata_signals(messages)

    assert signals.salient_messages == [
        {"role": "user", "content": "Inspect README.md and src/app.py for context packet flow."},
        {"role": "assistant", "content": "Hermes summarization keeps recovery grounded."},
    ]
    assert signals.text == (
        "Inspect README.md and src/app.py for context packet flow. "
        "Hermes summarization keeps recovery grounded."
    )
    assert signals.files == ["README.md", "src/app.py"]
    assert signals.entities == ["Hermes"]
    assert signals.concepts == ["context-packet", "summarization"]

    analysis = analyze_heuristic_messages(messages)
    assert analysis.metadata_signals == signals
    assert analysis.salient_messages == signals.salient_messages
    assert analysis.text == signals.text
    assert analysis.files == signals.files
    assert analysis.entities == signals.entities
    assert analysis.concepts == signals.concepts


def test_extract_recovery_fields_is_a_named_stage() -> None:
    messages = [
        {"role": "user", "content": "Summarize README.md."},
        {
            "role": "assistant",
            "content": """Done.
- README.md explains recovery flow.
- Context packets stay grounded.
""",
        },
        {"role": "user", "content": "Should we refine extraction next?"},
    ]

    fields = heuristic_module.extract_recovery_fields(messages)

    assert fields.request == "Summarize README.md."
    assert fields.outcome == "Done."
    assert fields.key_points == [
        "README.md explains recovery flow.",
        "Context packets stay grounded.",
    ]
    assert fields.follow_up_questions == ["Should we refine extraction next?"]
    assert fields.recovery_summary == compose_recovery_summary(
        messages=messages,
        request=fields.request,
        outcome=fields.outcome,
        key_points=fields.key_points,
        follow_up_questions=fields.follow_up_questions,
    )

    analysis = analyze_heuristic_messages(messages)
    assert analysis.recovery_fields == fields
    assert analysis.request == fields.request
    assert analysis.outcome == fields.outcome
    assert analysis.key_points == fields.key_points
    assert analysis.follow_up_questions == fields.follow_up_questions
    assert analysis.recovery_summary == fields.recovery_summary


def test_extract_recovery_fields_stops_key_points_before_status_sections() -> None:
    messages = [
        {"role": "user", "content": "Refactor heuristic recovery extraction."},
        {
            "role": "assistant",
            "content": """완료.
변경:
- `heuristic_recovery.py` now owns recovery fields.
- `summary_lint.py` uses public stages.
검증:
- `python -m pytest -q` passed.
커밋:
- `abc1234 refactor: improve recovery extraction`
다음 후보:
1. Tune metadata extraction.
""",
        },
    ]

    fields = heuristic_module.extract_recovery_fields(messages)

    assert fields.outcome == "완료."
    assert fields.key_points == [
        "heuristic_recovery.py now owns recovery fields.",
        "summary_lint.py uses public stages.",
    ]


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


def test_evidence_and_lint_use_public_heuristic_stages() -> None:
    for relative_path in [
        "src/agent_context_substrate/evidence.py",
        "src/agent_context_substrate/summary_lint.py",
    ]:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "from .heuristic_metadata import _" not in source
        assert "from .heuristic_recovery import _" not in source


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
