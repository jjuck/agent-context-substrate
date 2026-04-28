from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hermes_llm_wiki_harness.models import (  # noqa: E402
    ContextPacket,
    MicroSummary,
    RawSessionReference,
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
        related_pages=["architectures/hermes-llm-wiki-harness.md"],
        provenance=reference,
    )
    packet = ContextPacket(
        packet_id="packet-1",
        task_title="Bootstrap Hermes harness",
        macro_context="Project scaffold needs to be created next",
        unit_summaries=[unit],
        micro_summaries=[micro],
        raw_pointers=[reference],
        critical_files=["pyproject.toml", "src/hermes_llm_wiki_harness/models.py"],
        open_questions=["What should raw extraction export format be?"],
    )

    payload = packet.to_dict()

    assert payload["unit_summaries"][0]["unit_id"] == "unit-1"
    assert payload["micro_summaries"][0]["micro_id"] == "micro-1"
    assert ContextPacket.from_dict(payload) == packet
