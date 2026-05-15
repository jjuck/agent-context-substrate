from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.retrieval_packets import search_packets


def test_packet_search_helper_returns_packet_and_summary_hits(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    packet_dir = project_root / "data" / "exports" / "context_packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / "packet-1.json").write_text(
        json.dumps(
            {
                "packet_id": "packet-1",
                "task_title": "Retrieval smoke packet",
                "macro_context": "Search packets for RAG-like retrieval decisions.",
                "unit_summaries": [
                    {
                        "unit_id": "unit-1",
                        "session_id": "session-1",
                        "title": "Design retrieval API",
                        "goal": "Expose packet search as a tool.",
                        "decisions": ["Search wiki first, then packets, then raw evidence."],
                        "progress": [],
                        "open_questions": [],
                        "micro_ids": ["micro-1"],
                        "related_pages": [],
                        "provenance": None,
                    }
                ],
                "micro_summaries": [
                    {
                        "micro_id": "micro-1",
                        "session_id": "session-1",
                        "message_ids": [10, 11],
                        "summary": "Implemented retrieval tool planning.",
                        "why_it_matters": "Allows request-time search.",
                        "request": "Add RAG-like lookup",
                        "outcome": "Defined wiki_knowledge_search tool",
                        "key_points": ["Retrieval should be read-only by default."],
                        "follow_up_questions": [],
                        "artifacts": [],
                        "files": ["src/agent_context_substrate/retrieval.py"],
                        "entities": [],
                        "concepts": ["RAG-like retrieval"],
                        "parent_unit_id": "unit-1",
                        "provenance": {
                            "session_id": "session-1",
                            "message_ids": [10, 11],
                            "source": "telegram",
                            "started_at": None,
                            "ended_at": None,
                            "title": "Retrieval planning",
                        },
                    }
                ],
                "raw_pointers": [
                    {
                        "session_id": "session-1",
                        "message_ids": [10, 11],
                        "source": "telegram",
                        "started_at": None,
                        "ended_at": None,
                        "title": "Retrieval planning",
                    }
                ],
                "critical_files": ["src/agent_context_substrate/retrieval.py"],
                "open_questions": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_packets(["wiki_knowledge_search", "read-only", "retrieval"], project_root)

    source_types = {hit.source_type for hit in hits}
    assert "packet" in source_types
    assert "micro_summary" in source_types
    micro_hit = next(hit for hit in hits if hit.source_type == "micro_summary")
    assert micro_hit.source_path == "data/exports/context_packets/packet-1.json"
    assert "read-only" in micro_hit.snippet
    assert "hermes-session:session-1#messages=10,11" in micro_hit.provenance
