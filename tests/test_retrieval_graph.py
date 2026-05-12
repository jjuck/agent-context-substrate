from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.retrieval_graph import (
    find_topic_map_edge,
    find_topic_map_node,
    format_topic_map_path,
    search_topic_map,
)


def test_search_topic_map_returns_node_edge_and_neighbor_path_hits(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
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

    hits = search_topic_map(["heuristic", "spine"], project_root, graph_depth=2)

    hit_keys = {hit.provenance[0] for hit in hits}
    assert "topic-map-node:claim:packet-1-claim-1" in hit_keys
    assert "topic-map-edge:claim:packet-1-claim-1->promotion:packet-1-candidate-1:promoted_as" in hit_keys
    assert "topic-map-node:promotion:packet-1-candidate-1" in hit_keys
    assert "topic-map-edge:promotion:packet-1-candidate-1->wiki_patch:packet-1-patch-1:planned_as" in hit_keys
    assert "topic-map-path:claim:packet-1-claim-1->promotion:packet-1-candidate-1->wiki_patch:packet-1-patch-1" in hit_keys


def test_format_topic_map_path_preserves_edge_direction() -> None:
    path_summary = format_topic_map_path(
        ["claim:1", "promotion:1", "wiki_patch:1"],
        [
            {"source": "claim:1", "target": "promotion:1", "type": "promoted_as"},
            {"source": "wiki_patch:1", "target": "promotion:1", "type": "planned_from"},
        ],
    )

    assert path_summary == "claim:1 --promoted_as--> promotion:1 <--planned_from-- wiki_patch:1"


def test_find_topic_map_node_and_edge_return_matching_records(tmp_path: Path) -> None:
    topic_map_path = tmp_path / "topic_map.json"
    topic_map_path.write_text(
        json.dumps(
            {
                "nodes": [{"node_id": "claim:1", "type": "claim", "label": "Claim one"}],
                "edges": [{"source": "claim:1", "target": "promotion:1", "type": "promoted_as"}],
            }
        ),
        encoding="utf-8",
    )

    assert find_topic_map_node(topic_map_path, "claim:1")["label"] == "Claim one"
    assert find_topic_map_edge(
        topic_map_path,
        source="claim:1",
        target="promotion:1",
        edge_type="promoted_as",
    )["type"] == "promoted_as"
