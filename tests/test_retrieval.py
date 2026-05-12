from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_context_substrate.retrieval import expand_hit, search_knowledge
from agent_context_substrate.retrieval_ids import encode_hit_id


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


def test_search_knowledge_recovery_mode_prioritizes_recovery_briefs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    recovery_dir = project_root / "data" / "exports" / "recovery"
    recovery_dir.mkdir(parents=True)
    (wiki_root / "notes").mkdir(parents=True)
    (wiki_root / "notes" / "llm-safety.md").write_text(
        "# LLM Safety\n\nnext action LLM input safety next action LLM input safety",
        encoding="utf-8",
    )
    recovery_path = recovery_dir / "session-1.json"
    recovery_path.write_text(
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

    hits = search_knowledge(
        "next action LLM input safety",
        project_root=project_root,
        wiki_root=wiki_root,
        mode="recovery",
        limit=5,
    )

    assert hits
    assert hits[0].source_type == "recovery_brief"
    assert hits[0].source_path == "data/exports/recovery/session-1.json"
    assert hits[0].title == "Resume alpha work"
    assert "Next action" in hits[0].snippet
    assert hits[0].provenance == ["recovery:session-1", "hermes-session:session-1#messages=1,2"]
    assert all(hit.source_type != "wiki" for hit in hits)

    detail = expand_hit(hits[0].hit_id, project_root=project_root, wiki_root=wiki_root)
    assert detail.metadata["source_type"] == "recovery_brief"
    assert detail.metadata["session_id"] == "session-1"
    assert "implement LLM input safety controls" in detail.content


def test_search_knowledge_recovery_mode_includes_packet_recovery_fields(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    packet_dir = project_root / "data" / "exports" / "context_packets"
    packet_dir.mkdir(parents=True)
    packet_json = packet_dir / "packet-1.json"
    packet_json.write_text(
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

    hits = search_knowledge(
        "resume checklist critical_files",
        project_root=project_root,
        wiki_root=wiki_root,
        mode="recovery",
        limit=5,
    )

    assert hits
    assert hits[0].source_type == "recovery_packet"
    assert hits[0].source_path == "data/exports/context_packets/packet-1.json"
    assert "Resume work" in hits[0].snippet

    detail = expand_hit(hits[0].hit_id, project_root=project_root, wiki_root=wiki_root)
    assert detail.metadata["source_type"] == "recovery_packet"
    assert detail.metadata["packet_id"] == "packet-1"
    assert "critical_files" in detail.content


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


def test_search_knowledge_skips_project_artifact_symlinks_that_escape_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    promotions_dir = project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True)
    outside = tmp_path / "outside-promotions.json"
    outside.write_text(
        json.dumps(
            [
                {
                    "candidate_id": "outside-candidate",
                    "packet_id": "outside-packet",
                    "kind": "concept_update",
                    "target_page": "outside",
                    "reason": "This outside artifact must not be searchable.",
                    "evidence": ["claim:outside"],
                    "proposed_change": "secret outside symlink payload",
                    "proposed_action": "update_existing",
                    "confidence": 0.9,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (promotions_dir / "linked.json").symlink_to(outside)

    hits = search_knowledge("secret outside symlink", project_root=project_root, wiki_root=wiki_root, limit=10)

    assert hits == []


def test_search_knowledge_includes_promotions_wiki_patches_and_applied_logs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    promotions_dir = project_root / "data" / "promotions"
    patches_dir = project_root / "data" / "wiki_patches"
    promotions_dir.mkdir(parents=True)
    patches_dir.mkdir(parents=True)

    (promotions_dir / "packet-1.json").write_text(
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Claim atom should update durable summarization knowledge.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Hybrid summarizer uses heuristic spine before semantic interpretation.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (patches_dir / "packet-1.json").write_text(
        json.dumps(
            {
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "status": "proposed",
                "operations": [
                    {
                        "patch_id": "packet-1-patch-1",
                        "candidate_id": "packet-1-candidate-1",
                        "target": "concepts/summarization.md",
                        "operation": "insert_claim_block",
                        "rationale": "Apply hybrid summarizer claim into managed block.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {"before": "", "after": "Hybrid summarizer managed block."},
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (patches_dir / "applied.jsonl").write_text(
        json.dumps(
            {
                "created_at": "2026-05-07T00:00:00+00:00",
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "patch_id": "packet-1-patch-1",
                "candidate_id": "packet-1-candidate-1",
                "target": "concepts/summarization.md",
                "operation": "insert_claim_block",
                "note": "Hybrid summarizer claim applied.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    hits = search_knowledge(
        "hybrid summarizer managed block",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=10,
    )

    source_types = {hit.source_type for hit in hits}
    assert "promotion_candidate" in source_types
    assert "wiki_patch" in source_types
    assert "applied_patch" in source_types
    promotion_hit = next(hit for hit in hits if hit.source_type == "promotion_candidate")
    assert promotion_hit.source_path == "data/promotions/packet-1.json"
    assert promotion_hit.provenance == ["promotion:packet-1-candidate-1", "claim:packet-1-claim-1"]
    patch_hit = next(hit for hit in hits if hit.source_type == "wiki_patch")
    assert patch_hit.provenance == ["wiki-patch:packet-1-patch-1", "claim:packet-1-claim-1"]
    applied_hit = next(hit for hit in hits if hit.source_type == "applied_patch")
    assert applied_hit.provenance == ["applied-patch:packet-1-patch-1"]

    detail = expand_hit(promotion_hit.hit_id, project_root=project_root, wiki_root=wiki_root)

    assert detail.metadata["source_type"] == "promotion_candidate"
    assert detail.metadata["candidate_id"] == "packet-1-candidate-1"
    assert "Hybrid summarizer uses heuristic spine" in detail.content


def test_search_knowledge_includes_topic_map_nodes_and_edges(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    topic_map_path = project_root / "data" / "index" / "topic_map.json"
    topic_map_path.parent.mkdir(parents=True)
    topic_map_path.write_text(
        json.dumps(
            {
                "schema_version": "topic_map_v1",
                "nodes": [
                    {
                        "node_id": "claim:packet-1-claim-1",
                        "type": "claim",
                        "label": "Hybrid summarizer keeps heuristic spine.",
                        "source_path": "data/atoms/claims.jsonl",
                        "metadata": {"status": "active"},
                    },
                    {
                        "node_id": "promotion:packet-1-candidate-1",
                        "type": "promotion",
                        "label": "packet-1-candidate-1",
                        "source_path": "data/promotions/packet-1.json",
                        "metadata": {"target_page": "summarization"},
                    },
                ],
                "edges": [
                    {
                        "source": "claim:packet-1-claim-1",
                        "target": "promotion:packet-1-candidate-1",
                        "type": "promoted_as",
                        "metadata": {"reason": "heuristic spine became durable knowledge candidate"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_knowledge(
        "heuristic spine promoted_as",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=10,
    )

    source_types = {hit.source_type for hit in hits}
    assert "topic_map_node" in source_types
    assert "topic_map_edge" in source_types
    edge_hit = next(hit for hit in hits if hit.source_type == "topic_map_edge")
    assert edge_hit.source_path == "data/index/topic_map.json"
    assert edge_hit.provenance == ["topic-map-edge:claim:packet-1-claim-1->promotion:packet-1-candidate-1:promoted_as"]

    detail = expand_hit(edge_hit.hit_id, project_root=project_root, wiki_root=wiki_root)

    assert detail.metadata["source_type"] == "topic_map_edge"
    assert detail.metadata["edge_type"] == "promoted_as"
    assert "heuristic spine became durable knowledge candidate" in detail.content


def test_search_knowledge_graph_mode_returns_only_topic_map_hits(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (wiki_root / "concepts").mkdir(parents=True)
    (wiki_root / "concepts" / "graph.md").write_text(
        "# Graph\n\nheuristic spine promoted_as should not win in graph mode.",
        encoding="utf-8",
    )
    topic_map_path = project_root / "data" / "index" / "topic_map.json"
    topic_map_path.parent.mkdir(parents=True)
    topic_map_path.write_text(
        json.dumps(
            {
                "schema_version": "topic_map_v1",
                "nodes": [
                    {
                        "node_id": "claim:packet-1-claim-1",
                        "type": "claim",
                        "label": "Hybrid summarizer heuristic spine.",
                        "source_path": "data/atoms/claims.jsonl",
                        "metadata": {},
                    }
                ],
                "edges": [
                    {
                        "source": "claim:packet-1-claim-1",
                        "target": "promotion:packet-1-candidate-1",
                        "type": "promoted_as",
                        "metadata": {"reason": "graph mode relation"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_knowledge(
        "heuristic spine promoted_as",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=10,
        mode="graph",
    )

    assert hits
    assert {hit.source_type for hit in hits} <= {"topic_map_node", "topic_map_edge"}
    assert any(hit.source_type == "topic_map_edge" for hit in hits)


def test_search_knowledge_graph_mode_can_expand_neighbor_edges_and_nodes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    topic_map_path = project_root / "data" / "index" / "topic_map.json"
    topic_map_path.parent.mkdir(parents=True)
    topic_map_path.write_text(
        json.dumps(
            {
                "schema_version": "topic_map_v1",
                "nodes": [
                    {
                        "node_id": "claim:packet-1-claim-1",
                        "type": "claim",
                        "label": "Hybrid summarizer keeps heuristic spine.",
                        "source_path": "data/atoms/claims.jsonl",
                        "metadata": {},
                    },
                    {
                        "node_id": "promotion:packet-1-candidate-1",
                        "type": "promotion",
                        "label": "packet-1-candidate-1",
                        "source_path": "data/promotions/packet-1.json",
                        "metadata": {},
                    },
                    {
                        "node_id": "wiki_patch:packet-1-patch-1",
                        "type": "wiki_patch",
                        "label": "packet-1-patch-1",
                        "source_path": "data/wiki_patches/packet-1.json",
                        "metadata": {},
                    },
                ],
                "edges": [
                    {
                        "source": "claim:packet-1-claim-1",
                        "target": "promotion:packet-1-candidate-1",
                        "type": "promoted_as",
                        "metadata": {},
                    },
                    {
                        "source": "promotion:packet-1-candidate-1",
                        "target": "wiki_patch:packet-1-patch-1",
                        "type": "planned_as",
                        "metadata": {},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_knowledge(
        "heuristic spine",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=10,
        mode="graph",
        graph_depth=2,
    )

    hit_ids = {hit.provenance[0] for hit in hits}
    assert "topic-map-node:claim:packet-1-claim-1" in hit_ids
    assert "topic-map-edge:claim:packet-1-claim-1->promotion:packet-1-candidate-1:promoted_as" in hit_ids
    assert "topic-map-node:promotion:packet-1-candidate-1" in hit_ids
    assert "topic-map-edge:promotion:packet-1-candidate-1->wiki_patch:packet-1-patch-1:planned_as" in hit_ids
    assert "topic-map-node:wiki_patch:packet-1-patch-1" in hit_ids


def test_search_knowledge_graph_mode_returns_human_readable_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    topic_map_path = project_root / "data" / "index" / "topic_map.json"
    topic_map_path.parent.mkdir(parents=True)
    topic_map_path.write_text(
        json.dumps(
            {
                "schema_version": "topic_map_v1",
                "nodes": [
                    {
                        "node_id": "claim:packet-1-claim-1",
                        "type": "claim",
                        "label": "Hybrid summarizer keeps heuristic spine.",
                        "source_path": "data/atoms/claims.jsonl",
                        "metadata": {},
                    },
                    {
                        "node_id": "promotion:packet-1-candidate-1",
                        "type": "promotion",
                        "label": "packet-1-candidate-1",
                        "source_path": "data/promotions/packet-1.json",
                        "metadata": {},
                    },
                    {
                        "node_id": "wiki_patch:packet-1-patch-1",
                        "type": "wiki_patch",
                        "label": "packet-1-patch-1",
                        "source_path": "data/wiki_patches/packet-1.json",
                        "metadata": {},
                    },
                    {
                        "node_id": "wiki_page:concepts/summarization.md",
                        "type": "wiki_page",
                        "label": "Summarization",
                        "source_path": "concepts/summarization.md",
                        "metadata": {},
                    },
                ],
                "edges": [
                    {
                        "source": "claim:packet-1-claim-1",
                        "target": "promotion:packet-1-candidate-1",
                        "type": "promoted_as",
                        "metadata": {},
                    },
                    {
                        "source": "promotion:packet-1-candidate-1",
                        "target": "wiki_patch:packet-1-patch-1",
                        "type": "planned_as",
                        "metadata": {},
                    },
                    {
                        "source": "wiki_patch:packet-1-patch-1",
                        "target": "wiki_page:concepts/summarization.md",
                        "type": "targets",
                        "metadata": {},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    hits = search_knowledge(
        "heuristic spine",
        project_root=project_root,
        wiki_root=wiki_root,
        limit=20,
        mode="graph",
        graph_depth=3,
    )

    path_hit = next(hit for hit in hits if hit.source_type == "topic_map_path")
    assert path_hit.title == "claim → promotion → wiki_patch → wiki_page"
    assert (
        "claim:packet-1-claim-1 --promoted_as--> promotion:packet-1-candidate-1"
        " --planned_as--> wiki_patch:packet-1-patch-1"
        " --targets--> wiki_page:concepts/summarization.md"
    ) in path_hit.snippet
    assert path_hit.provenance == [
        "topic-map-path:claim:packet-1-claim-1->promotion:packet-1-candidate-1->wiki_patch:packet-1-patch-1->wiki_page:concepts/summarization.md"
    ]

    detail = expand_hit(path_hit.hit_id, project_root=project_root, wiki_root=wiki_root)

    assert detail.metadata["source_type"] == "topic_map_path"
    assert detail.metadata["path_length"] == 3
    assert "promoted_as" in detail.content
    assert "targets" in detail.content



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


def _forged_hit_id(payload: dict[str, object]) -> str:
    return encode_hit_id(payload)


def test_expand_hit_rejects_forged_wiki_path_traversal(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("outside secret should not be readable", encoding="utf-8")
    hit_id = _forged_hit_id(
        {
            "source_type": "wiki",
            "source_path": "../secret.md",
            "title": "forged",
            "provenance": [],
        }
    )

    with pytest.raises(ValueError):
        expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)


def test_expand_hit_rejects_forged_project_absolute_path(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    wiki_root.mkdir()
    outside = tmp_path / "promotions.json"
    outside.write_text("[]", encoding="utf-8")
    hit_id = _forged_hit_id(
        {
            "source_type": "promotion_candidate",
            "source_path": str(outside),
            "candidate_id": "candidate-1",
            "title": "forged",
            "provenance": [],
        }
    )

    with pytest.raises(ValueError):
        expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)


def test_expand_hit_rejects_forged_excluded_wiki_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    secret_page = wiki_root / "_system" / "secret.md"
    secret_page.parent.mkdir(parents=True)
    secret_page.write_text("# Secret\n\nexcluded wiki content", encoding="utf-8")
    hit_id = _forged_hit_id(
        {
            "source_type": "wiki",
            "source_path": "_system/secret.md",
            "title": "forged",
            "provenance": [],
        }
    )

    with pytest.raises(ValueError):
        expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)


def test_expand_hit_rejects_forged_project_path_outside_allowed_artifact_dirs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    raw_export = project_root / "data" / "exports" / "session-1.json"
    raw_export.parent.mkdir(parents=True)
    raw_export.write_text('{"private": "raw export should not be expandable"}', encoding="utf-8")
    hit_id = _forged_hit_id(
        {
            "source_type": "packet",
            "source_path": "data/exports/session-1.json",
            "packet_id": "session-1",
            "title": "forged",
            "provenance": [],
        }
    )

    with pytest.raises(ValueError):
        expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)


@pytest.mark.parametrize(
    ("source_type", "source_path"),
    [
        ("recovery_brief", "data/exports/recovery/link.json"),
        ("recovery_packet", "data/exports/context_packets/link.json"),
    ],
)
def test_expand_hit_rejects_project_artifact_symlink_boundary_bypass(
    tmp_path: Path, source_type: str, source_path: str
) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    secret_json = project_root / "data" / "exports" / "private" / "secret.json"
    secret_json.parent.mkdir(parents=True)
    secret_json.write_text('{"private": "symlink boundary bypass"}', encoding="utf-8")
    link = project_root / source_path
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(secret_json)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    hit_id = _forged_hit_id(
        {
            "source_type": source_type,
            "source_path": source_path,
            "packet_id": "packet-forged",
            "session_id": "session-forged",
            "title": "forged",
            "provenance": [],
        }
    )

    with pytest.raises(ValueError):
        expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)


def test_expand_hit_rejects_forged_raw_message_hit(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    wiki_root.mkdir()
    hit_id = _forged_hit_id(
        {
            "source_type": "raw_message",
            "source_path": "state.db:session-1:1",
            "session_id": "session-1",
            "message_id": 1,
            "title": "forged",
            "provenance": [],
        }
    )

    with pytest.raises(ValueError):
        expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)


def test_search_knowledge_skips_wiki_symlink_outside_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    outside = tmp_path / "outside-secret.md"
    outside.write_text("# Secret\n\noutside-only-sentinel", encoding="utf-8")
    link = wiki_root / "link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")

    hits = search_knowledge("outside-only-sentinel", project_root=project_root, wiki_root=wiki_root)

    assert hits == []
