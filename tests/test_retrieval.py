from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.retrieval import expand_hit, search_knowledge


def test_search_knowledge_returns_wiki_hits_with_provenance(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (wiki_root / "architectures").mkdir(parents=True)
    page = wiki_root / "architectures" / "agent-context-substrate.md"
    page.write_text(
        "# Agent Context Substrate\n\n"
        "The retrieval layer should search durable wiki pages before raw evidence.\n"
        "It supports RAG-like knowledge lookup during user requests.\n",
        encoding="utf-8",
    )

    hits = search_knowledge(
        "RAG-like retrieval durable wiki",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=3,
    )

    assert hits
    assert hits[0].source_type == "wiki"
    assert hits[0].title == "Agent Context Substrate"
    assert "durable wiki" in hits[0].snippet
    assert hits[0].provenance == ["wiki:architectures/agent-context-substrate.md"]
    assert hits[0].score > 0


def test_search_knowledge_skips_system_templates_and_archive_by_default(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (wiki_root / "01 지식").mkdir(parents=True)
    (wiki_root / "_system" / "templates" / "ko").mkdir(parents=True)
    (wiki_root / "90 보관" / "자동생성 아카이브").mkdir(parents=True)

    (wiki_root / "01 지식" / "Context Packet.md").write_text(
        "# Context Packet\n\nHuman-facing durable retrieval knowledge.",
        encoding="utf-8",
    )
    (wiki_root / "_system" / "templates" / "ko" / "knowledge.md").write_text(
        "# Template\n\nretrieval template should not be searched.",
        encoding="utf-8",
    )
    (wiki_root / "90 보관" / "자동생성 아카이브" / "old.md").write_text(
        "# Archived\n\nretrieval archive should not be searched by default.",
        encoding="utf-8",
    )

    hits = search_knowledge("retrieval", project_root=project_root, wiki_root=wiki_root, limit=10)

    assert [hit.source_path for hit in hits] == ["01 지식/Context Packet.md"]



def test_search_knowledge_includes_packet_and_micro_summary_hits(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    packet_dir = project_root / "data" / "exports" / "context_packets"
    packet_dir.mkdir(parents=True)
    packet_json = packet_dir / "packet-1.json"
    packet_json.write_text(
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

    hits = search_knowledge(
        "wiki_knowledge_search read-only retrieval",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=5,
    )

    assert any(hit.source_type == "packet" and hit.source_path.endswith("packet-1.json") for hit in hits)
    micro_hits = [hit for hit in hits if hit.source_type == "micro_summary"]
    assert micro_hits
    assert "read-only" in micro_hits[0].snippet
    assert "hermes-session:session-1#messages=10,11" in micro_hits[0].provenance


def test_expand_hit_returns_full_wiki_or_packet_detail(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (wiki_root / "concepts").mkdir(parents=True)
    page = wiki_root / "concepts" / "retrieval.md"
    page.write_text("# Retrieval\n\nFull detail about wiki search and grounding.", encoding="utf-8")

    hits = search_knowledge("grounding retrieval", project_root=project_root, wiki_root=wiki_root)
    detail = expand_hit(hits[0].hit_id, project_root=project_root, wiki_root=wiki_root)

    assert detail.hit.hit_id == hits[0].hit_id
    assert detail.content.startswith("# Retrieval")
    assert detail.metadata["source_type"] == "wiki"


def test_search_knowledge_can_query_raw_evidence_sqlite(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    db_path = hermes_home / "state.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, source TEXT)")
        connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp TEXT)"
        )
        connection.execute(
            "INSERT INTO sessions (id, title, source) VALUES ('session-raw', 'Raw retrieval', 'telegram')"
        )
        connection.execute(
            "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (42, 'session-raw', 'assistant', 'Raw evidence mentions vectorless RAG replacement.', 'now')"
        )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    hits = search_knowledge(
        "vectorless RAG replacement",
        project_root=project_root,
        wiki_root=wiki_root,
        include_raw=True,
    )

    raw_hits = [hit for hit in hits if hit.source_type == "raw_message"]
    assert raw_hits
    assert raw_hits[0].provenance == ["hermes-session:session-raw#messages=42"]
