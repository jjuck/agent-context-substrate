from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.models import MicroSummary, RawSessionReference  # noqa: E402
from agent_context_substrate.summarizer import (  # noqa: E402
    build_micro_summary,
    build_unit_summary,
)


def test_build_micro_summary_from_raw_bundle_extracts_basic_artifacts() -> None:
    raw_bundle = {
        "session": {
            "id": "session-1",
            "source": "telegram",
            "title": "Harness planning",
            "started_at": 1776395277.0,
            "ended_at": None,
        },
        "messages": [
            {
                "id": 10,
                "role": "user",
                "content": "Use Hermes state.db and create pyproject.toml plus src/agent_context_substrate/models.py",
            },
            {
                "id": 11,
                "role": "assistant",
                "content": "I created README.md, tests/test_models.py, and drafted a context packet export plan.",
            },
        ],
        "slice": {"start_message_id": 10, "end_message_id": 11},
        "message_count": 2,
    }

    summary = build_micro_summary(raw_bundle=raw_bundle, micro_id="micro-1", parent_unit_id="unit-1")

    assert summary.micro_id == "micro-1"
    assert summary.session_id == "session-1"
    assert summary.message_ids == [10, 11]
    assert "pyproject.toml" in summary.files
    assert "README.md" in summary.files
    assert "tests/test_models.py" in summary.files
    assert summary.parent_unit_id == "unit-1"
    assert summary.provenance == RawSessionReference(
        session_id="session-1",
        message_ids=[10, 11],
        source="telegram",
        started_at=str(1776395277.0),
        ended_at=None,
        title="Harness planning",
    )
    assert summary.summary
    assert summary.why_it_matters


def test_build_micro_summary_prefers_user_and_assistant_content_over_tool_noise() -> None:
    raw_bundle = {
        "session": {
            "id": "session-1",
            "source": "telegram",
            "title": "Harness planning",
            "started_at": 1776395277.0,
            "ended_at": None,
        },
        "messages": [
            {
                "id": 10,
                "role": "user",
                "content": "Create pyproject.toml and README.md for the harness bootstrap.",
            },
            {
                "id": 11,
                "role": "tool",
                "content": '{"bytes_written": 1234, "path": "tmp/noisy.json"}',
            },
            {
                "id": 12,
                "role": "assistant",
                "content": "Created pyproject.toml and README.md; next step is context packet export.",
            },
        ],
        "slice": {"start_message_id": 10, "end_message_id": 12},
        "message_count": 3,
    }

    summary = build_micro_summary(raw_bundle=raw_bundle, micro_id="micro-2", parent_unit_id="unit-1")

    assert "Request:" in summary.summary
    assert "Outcome:" in summary.summary
    assert "bytes_written" not in summary.summary
    assert "tmp/noisy.json" not in summary.summary
    assert "pyproject.toml" in summary.why_it_matters
    assert "README.md" in summary.why_it_matters


def test_build_micro_summary_extracts_structured_request_outcome_key_points_and_open_question() -> None:
    raw_bundle = {
        "session": {
            "id": "session-2",
            "source": "telegram",
            "title": "Reasoning settings inspection",
            "started_at": 1776395277.0,
            "ended_at": None,
        },
        "messages": [
            {
                "id": 20,
                "role": "user",
                "content": "Please confirm the model, provider, and reasoning effort in .hermes/config.yaml.",
            },
            {
                "id": 21,
                "role": "assistant",
                "content": (
                    "Confirmed the current Hermes settings.\n\n"
                    "- Model: `gpt-5.4`\n"
                    "- Provider: `openai-codex`\n"
                    "- Reasoning effort: `high`\n\n"
                    "Evidence:\n"
                    "- .hermes/config.yaml\n"
                    "- run_agent.py"
                ),
            },
            {
                "id": 22,
                "role": "user",
                "content": "Then is show reasoning disabled too?",
            },
        ],
        "slice": {"start_message_id": 20, "end_message_id": 22},
        "message_count": 3,
    }

    summary = build_micro_summary(raw_bundle=raw_bundle, micro_id="micro-structured", parent_unit_id="unit-7")

    assert summary.request == "Please confirm the model, provider, and reasoning effort in .hermes/config.yaml."
    assert summary.outcome == "Confirmed the current Hermes settings."
    assert summary.key_points == [
        "Model: gpt-5.4",
        "Provider: openai-codex",
        "Reasoning effort: high",
    ]
    assert summary.follow_up_questions == ["Then is show reasoning disabled too?"]
    assert "Request: Please confirm the model, provider, and reasoning effort in .hermes/config.yaml." in summary.summary
    assert "Outcome: Confirmed the current Hermes settings." in summary.summary
    assert "Key points: Model: gpt-5.4; Provider: openai-codex; Reasoning effort: high" in summary.summary
    assert "Open question: Then is show reasoning disabled too?" in summary.summary


def test_build_micro_summary_filters_noise_and_keeps_probable_file_paths() -> None:
    raw_bundle = {
        "session": {
            "id": "session-1",
            "source": "telegram",
            "title": "Reasoning settings inspection",
            "started_at": 1776395277.0,
            "ended_at": None,
        },
        "messages": [
            {
                "id": 20,
                "role": "user",
                "content": (
                    "Check .hermes/config.yaml, agent/display.py, README.md, pyproject.toml, "
                    "and raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh. "
                    "Do not treat github.com, hermes-agent.nousresearch.com, json.dumps, "
                    "agent.reasoning_effort, CLI_CONFIG.get, gpt-5.4, threading.Lock, or e.g. as files."
                ),
            }
        ],
        "slice": {"start_message_id": 20, "end_message_id": 20},
        "message_count": 1,
    }

    summary = build_micro_summary(raw_bundle=raw_bundle, micro_id="micro-noise", parent_unit_id="unit-1")

    assert ".hermes/config.yaml" in summary.files
    assert "agent/display.py" in summary.files
    assert "README.md" in summary.files
    assert "pyproject.toml" in summary.files
    assert "raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh" in summary.files

    assert "github.com" not in summary.files
    assert "hermes-agent.nousresearch.com" not in summary.files
    assert "json.dumps" not in summary.files
    assert "agent.reasoning_effort" not in summary.files
    assert "CLI_CONFIG.get" not in summary.files
    assert "gpt-5.4" not in summary.files
    assert "threading.Lock" not in summary.files
    assert "e.g." not in summary.files


def test_build_unit_summary_aggregates_multiple_micro_summaries() -> None:
    provenance = RawSessionReference(
        session_id="session-1",
        message_ids=[1, 2, 3],
        source="telegram",
        started_at="1776395277.0",
        ended_at=None,
        title="Harness planning",
    )
    micro_a = MicroSummary(
        micro_id="micro-a",
        session_id="session-1",
        message_ids=[1, 2],
        summary="Created the package skeleton",
        why_it_matters="Bootstraps the project",
        request="Create the package scaffold",
        outcome="Created the package skeleton",
        key_points=["Created pyproject.toml", "Created README.md"],
        follow_up_questions=[],
        artifacts=["pyproject.toml"],
        files=["pyproject.toml", "README.md"],
        entities=["Hermes"],
        concepts=["context-packet"],
        parent_unit_id="unit-1",
        provenance=provenance,
    )
    micro_b = MicroSummary(
        micro_id="micro-b",
        session_id="session-1",
        message_ids=[3],
        summary="Added raw extraction tests",
        why_it_matters="Protects future refactors",
        request="Add regression coverage for raw extraction",
        outcome="Added raw extraction tests",
        key_points=["Protected session bundle export"],
        follow_up_questions=["Should exports include tool payloads by default?"],
        artifacts=["tests/test_raw_extract.py"],
        files=["tests/test_raw_extract.py"],
        entities=[],
        concepts=["summarization"],
        parent_unit_id="unit-1",
        provenance=provenance,
    )

    unit = build_unit_summary(
        unit_id="unit-1",
        session_id="session-1",
        title="Bootstrap project scaffold",
        goal="Create the first usable harness substrate",
        micro_summaries=[micro_a, micro_b],
        related_pages=["architectures/agent-context-substrate.md"],
    )

    assert unit.unit_id == "unit-1"
    assert unit.session_id == "session-1"
    assert unit.micro_ids == ["micro-a", "micro-b"]
    assert unit.related_pages == ["architectures/agent-context-substrate.md"]
    assert unit.provenance == provenance
    assert unit.decisions == [
        "Created pyproject.toml",
        "Created README.md",
        "Protected session bundle export",
    ]
    assert unit.progress == [
        "Created the package skeleton",
        "Added raw extraction tests",
    ]
    assert unit.open_questions == ["Should exports include tool payloads by default?"]
