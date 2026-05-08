from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.models import (  # noqa: E402
    ContextPacket,
    EvidenceBackedText,
    MicroSummary,
    RawSessionReference,
    SummaryMetadata,
    UnitSummary,
)


def test_raw_session_reference_round_trips_to_dict() -> None:
    reference = RawSessionReference(
        session_id="session-123",
        message_ids=[1, 2, 3],
        source="telegram",
        started_at="2026-04-17T12:07:57Z",
        ended_at="2026-04-17T12:09:00Z",
        title="Test session",
    )

    payload = reference.to_dict()

    assert payload["session_id"] == "session-123"
    assert payload["message_ids"] == [1, 2, 3]
    assert RawSessionReference.from_dict(payload) == reference


def test_context_packet_preserves_nested_summary_ids() -> None:
    reference = RawSessionReference(
        session_id="session-123",
        message_ids=[10, 11],
        source="telegram",
        started_at=None,
        ended_at=None,
        title="Harness planning",
    )
    micro = MicroSummary(
        micro_id="micro-1",
        session_id="session-123",
        message_ids=[10, 11],
        summary="Created the implementation plan",
        why_it_matters="Needed before bootstrapping the project",
        request="Write the initial implementation plan",
        outcome="Created the implementation plan",
        key_points=["Kept Hermes state.db as the raw substrate"],
        follow_up_questions=["How should context packets be exported?"],
        artifacts=[".hermes/plans/plan.md"],
        files=["README.md"],
        entities=["Hermes"],
        concepts=["context-packet"],
        parent_unit_id="unit-1",
        provenance=reference,
    )
    unit = UnitSummary(
        unit_id="unit-1",
        session_id="session-123",
        title="Plan the MVP",
        goal="Turn architecture into an executable project plan",
        decisions=["Keep Hermes state.db as raw substrate"],
        progress=["Created MVP plan"],
        open_questions=["How should context packets be exported?"],
        micro_ids=["micro-1"],
        related_pages=["architectures/agent-context-substrate.md"],
        provenance=reference,
    )
    packet = ContextPacket(
        packet_id="packet-1",
        task_title="Bootstrap Hermes harness",
        macro_context="Project scaffold needs to be created next",
        unit_summaries=[unit],
        micro_summaries=[micro],
        raw_pointers=[reference],
        critical_files=["pyproject.toml", "src/agent_context_substrate/models.py"],
        open_questions=["What should raw extraction export format be?"],
    )

    payload = packet.to_dict()

    assert payload["unit_summaries"][0]["unit_id"] == "unit-1"
    assert payload["micro_summaries"][0]["micro_id"] == "micro-1"
    assert ContextPacket.from_dict(payload) == packet


def test_summary_metadata_round_trips_to_dict() -> None:
    metadata = SummaryMetadata(
        mode="heuristic",
        schema_version="micro_summary_v2",
        prompt_version=None,
        model=None,
        input_hash="sha256:abc123",
        created_at="2026-05-07T13:46:00+00:00",
        confidence=0.74,
    )

    payload = metadata.to_dict()

    assert payload == {
        "mode": "heuristic",
        "schema_version": "micro_summary_v2",
        "prompt_version": None,
        "model": None,
        "input_hash": "sha256:abc123",
        "created_at": "2026-05-07T13:46:00+00:00",
        "confidence": 0.74,
        "fallback_from": None,
        "fallback_reason": None,
    }
    assert SummaryMetadata.from_dict(payload) == metadata


def test_summary_metadata_preserves_fallback_reason() -> None:
    metadata = SummaryMetadata(
        mode="heuristic",
        schema_version="micro_summary_v2",
        prompt_version=None,
        model=None,
        input_hash="sha256:abc123",
        created_at="2026-05-07T13:46:00+00:00",
        confidence=0.6,
        fallback_from="agent-llm",
        fallback_reason="lint:no_new_files",
    )

    payload = metadata.to_dict()

    assert payload["fallback_from"] == "agent-llm"
    assert payload["fallback_reason"] == "lint:no_new_files"
    assert SummaryMetadata.from_dict(payload) == metadata


def test_evidence_backed_text_round_trips_to_dict() -> None:
    backed_text = EvidenceBackedText(
        text="Keep heuristic extraction as a grounding pass.",
        evidence_message_ids=[12, 13],
        confidence=0.91,
    )

    payload = backed_text.to_dict()

    assert payload == {
        "text": "Keep heuristic extraction as a grounding pass.",
        "evidence_message_ids": [12, 13],
        "confidence": 0.91,
    }
    assert EvidenceBackedText.from_dict(payload) == backed_text
