from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.topic_map import build_topic_map, export_topic_map, render_topic_map_markdown


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_topic_map_connects_claims_promotions_patches_applied_logs_and_wiki_links(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    _write(
        project_root / "data" / "atoms" / "claims.jsonl",
        json.dumps(
            {
                "atom_id": "packet-1-claim-1",
                "text": "Hybrid summarizer keeps heuristic evidence spine.",
                "type": "design_claim",
                "subjects": ["summarization"],
                "source_refs": ["packet:packet-1#packet-1-micro-1", "hermes-session:session-1#messages=1,2"],
                "confidence": 0.8,
                "status": "active",
                "first_seen": "2026-05-07T00:00:00+00:00",
                "last_seen": "2026-05-07T00:00:00+00:00",
                "supports": [],
                "contradicts": [],
                "supersedes": [],
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Claim atom packet-1-claim-1 may update durable wiki knowledge.",
                    "evidence": ["claim:packet-1-claim-1", "packet:packet-1#packet-1-micro-1"],
                    "proposed_change": "Hybrid summarizer keeps heuristic evidence spine.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )
    _write(
        project_root / "data" / "wiki_patches" / "packet-1.json",
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
                        "rationale": "Apply candidate.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {"before": "", "after": "managed block"},
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    _write(
        project_root / "data" / "wiki_patches" / "applied.jsonl",
        json.dumps(
            {
                "created_at": "2026-05-07T00:00:00+00:00",
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "patch_id": "packet-1-patch-1",
                "candidate_id": "packet-1-candidate-1",
                "target": "concepts/summarization.md",
                "operation": "insert_claim_block",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write(
        project_root / "data" / "exports" / "context_packets" / "packet-1.json",
        json.dumps(
            {
                "packet_id": "packet-1",
                "task_title": "Hybrid summarizer work",
                "macro_context": "Build evidence based summaries.",
                "unit_summaries": [],
                "micro_summaries": [],
                "raw_pointers": [],
                "critical_files": [],
                "open_questions": [],
            },
            ensure_ascii=False,
        ),
    )
    _write(wiki_root / "concepts" / "summarization.md", "# Summarization\n\nSee [[agent-context-substrate]].\n")
    _write(wiki_root / "concepts" / "agent-context-substrate.md", "# Agent Context Substrate\n")

    topic_map = build_topic_map(project_root=project_root, wiki_root=wiki_root)

    node_ids = {node.node_id for node in topic_map.nodes}
    edge_pairs = {(edge.source, edge.target, edge.type) for edge in topic_map.edges}

    assert "claim:packet-1-claim-1" in node_ids
    assert "promotion:packet-1-candidate-1" in node_ids
    assert "wiki_patch:packet-1-patch-1" in node_ids
    assert "applied_patch:packet-1-patch-1" in node_ids
    assert "wiki_page:concepts/summarization.md" in node_ids
    assert "packet:packet-1" in node_ids
    assert ("packet:packet-1", "claim:packet-1-claim-1", "contains_claim") in edge_pairs
    assert ("claim:packet-1-claim-1", "promotion:packet-1-candidate-1", "promoted_as") in edge_pairs
    assert ("promotion:packet-1-candidate-1", "wiki_patch:packet-1-patch-1", "planned_as") in edge_pairs
    assert ("wiki_patch:packet-1-patch-1", "wiki_page:concepts/summarization.md", "targets") in edge_pairs
    assert ("wiki_patch:packet-1-patch-1", "applied_patch:packet-1-patch-1", "applied_as") in edge_pairs
    assert ("wiki_page:concepts/summarization.md", "wiki_page:concepts/agent-context-substrate.md", "links_to") in edge_pairs


def test_export_topic_map_writes_json_and_markdown(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    _write(wiki_root / "concepts" / "summarization.md", "# Summarization\n")

    topic_map = build_topic_map(project_root=project_root, wiki_root=wiki_root)
    json_path, markdown_path = export_topic_map(topic_map=topic_map, project_root=project_root)

    assert json_path == project_root / "data" / "index" / "topic_map.json"
    assert markdown_path == project_root / "data" / "index" / "topic_map.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "topic_map_v1"
    assert payload["nodes"]
    assert "# Topic Map" in markdown_path.read_text(encoding="utf-8")
    assert "nodes=" in render_topic_map_markdown(topic_map)



def test_build_topic_map_includes_decision_entity_concept_and_question_atoms(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    _write(
        project_root / "data" / "atoms" / "decisions.jsonl",
        json.dumps(
            {
                "atom_id": "packet-1-decision-1",
                "text": "Keep packet-only default.",
                "source_refs": ["packet:packet-1#micro-1"],
                "confidence": 0.9,
                "status": "active",
                "first_seen": "2026-05-08T00:00:00+00:00",
                "last_seen": "2026-05-08T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write(
        project_root / "data" / "atoms" / "entities.jsonl",
        json.dumps(
            {
                "atom_id": "packet-1-entity-1",
                "name": "Hermes Agent",
                "type": "entity",
                "source_refs": ["packet:packet-1#micro-1"],
                "status": "active",
                "first_seen": "2026-05-08T00:00:00+00:00",
                "last_seen": "2026-05-08T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write(
        project_root / "data" / "atoms" / "concepts.jsonl",
        json.dumps(
            {
                "atom_id": "packet-1-concept-1",
                "name": "packet-only",
                "source_refs": ["packet:packet-1#micro-1"],
                "status": "active",
                "first_seen": "2026-05-08T00:00:00+00:00",
                "last_seen": "2026-05-08T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write(
        project_root / "data" / "atoms" / "questions.jsonl",
        json.dumps(
            {
                "atom_id": "packet-1-question-1",
                "text": "Should stale claims be detected?",
                "source_refs": ["packet:packet-1#micro-1"],
                "status": "open",
                "first_seen": "2026-05-08T00:00:00+00:00",
                "last_seen": "2026-05-08T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    topic_map = build_topic_map(project_root=project_root, wiki_root=wiki_root)

    node_ids = {node.node_id for node in topic_map.nodes}
    edge_pairs = {(edge.source, edge.target, edge.type) for edge in topic_map.edges}
    assert "decision:packet-1-decision-1" in node_ids
    assert "entity:packet-1-entity-1" in node_ids
    assert "concept:packet-1-concept-1" in node_ids
    assert "question:packet-1-question-1" in node_ids
    assert ("packet:packet-1", "decision:packet-1-decision-1", "contains_decision") in edge_pairs
    assert ("packet:packet-1", "entity:packet-1-entity-1", "mentions_entity") in edge_pairs
    assert ("packet:packet-1", "concept:packet-1-concept-1", "mentions_concept") in edge_pairs
    assert ("packet:packet-1", "question:packet-1-question-1", "raises_question") in edge_pairs


def test_build_topic_map_skips_wiki_symlink_outside_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    wiki_root.mkdir()
    outside = tmp_path / "outside-secret.md"
    outside.write_text("# Secret Outside\n\n[[Inside]]", encoding="utf-8")
    link = wiki_root / "link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        return

    topic_map = build_topic_map(project_root=project_root, wiki_root=wiki_root)

    assert all(node.source_path != "link.md" for node in topic_map.nodes)
    assert all("outside" not in node.label.lower() for node in topic_map.nodes)
