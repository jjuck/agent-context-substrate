from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.retrieval_recovery import search_recovery_briefs, search_recovery_packets


def test_recovery_search_helpers_return_brief_hits_with_provenance(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    recovery_dir = project_root / "data" / "exports" / "recovery"
    recovery_dir.mkdir(parents=True)
    (recovery_dir / "session-1.json").write_text(
        json.dumps(
            {
                "session_id": "session-1",
                "packet_id": "packet-1",
                "task_title": "Resume alpha work",
                "macro_context": "Next action: implement LLM input safety controls.",
                "decisions": ["Recovery retrieval ships before provider-specific policy."],
                "critical_files": ["src/agent_context_substrate/retrieval.py"],
                "open_questions": ["Should max input chars default to 12000?"],
                "related_pages": ["Agent Context Substrate"],
                "provenance": ["hermes-session:session-1#messages=1,2"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_recovery_briefs(["llm", "safety"], project_root)

    assert len(hits) == 1
    assert hits[0].source_type == "recovery_brief"
    assert hits[0].source_path == "data/exports/recovery/session-1.json"
    assert hits[0].title == "Resume alpha work"
    assert "LLM input safety" in hits[0].snippet
    assert hits[0].provenance == ["recovery:session-1", "hermes-session:session-1#messages=1,2"]


def test_recovery_search_helpers_return_packet_recovery_hits(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    packet_dir = project_root / "data" / "exports" / "context_packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / "packet-1.json").write_text(
        json.dumps(
            {
                "packet_id": "packet-1",
                "task_title": "Recovery retrieval packet",
                "macro_context": "Resume work by checking recovery retrieval tests first.",
                "unit_summaries": [
                    {
                        "unit_id": "unit-1",
                        "session_id": "session-1",
                        "title": "Build recovery search",
                        "goal": "Expose recovery artifacts as first-class retrieval input.",
                        "decisions": ["Recovery mode searches packet fields when no brief exists."],
                        "progress": ["Context packet exists."],
                        "open_questions": ["How should expand return packet recovery excerpts?"],
                        "micro_ids": ["micro-1"],
                        "related_pages": [],
                        "provenance": None,
                    }
                ],
                "micro_summaries": [
                    {
                        "micro_id": "micro-1",
                        "session_id": "session-1",
                        "message_ids": [1, 2],
                        "summary": "Recovery-oriented summary text mentions resume checklist.",
                        "why_it_matters": "Next sessions can continue from the right file.",
                        "request": "Add recovery mode",
                        "outcome": "Packet recovery fields are searchable.",
                        "key_points": ["critical_files guide the next edit."],
                        "follow_up_questions": [],
                        "artifacts": [],
                        "files": ["src/agent_context_substrate/retrieval.py"],
                        "entities": [],
                        "concepts": ["recovery retrieval"],
                        "parent_unit_id": "unit-1",
                        "provenance": {
                            "session_id": "session-1",
                            "message_ids": [1, 2],
                            "source": "telegram",
                            "started_at": None,
                            "ended_at": None,
                            "title": "Recovery retrieval",
                        },
                    }
                ],
                "raw_pointers": [],
                "critical_files": ["src/agent_context_substrate/retrieval.py"],
                "open_questions": ["Should recovery_packet ranking follow recovery_brief?"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_recovery_packets(["resume", "checklist"], project_root)

    assert len(hits) == 1
    assert hits[0].source_type == "recovery_packet"
    assert hits[0].source_path == "data/exports/context_packets/packet-1.json"
    assert hits[0].title == "Recovery retrieval packet"
    assert "Resume work" in hits[0].snippet
