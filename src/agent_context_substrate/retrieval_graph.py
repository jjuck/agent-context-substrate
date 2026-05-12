from __future__ import annotations

from pathlib import Path

from .retrieval_ids import encode_hit_id
from .retrieval_scoring import make_snippet, score_text
from .retrieval_sources import json_search_text, load_json_object
from .retrieval_types import RetrievalHit
from .safe_paths import is_safe_project_artifact_path


def search_topic_map(terms: list[str], project_root: Path, *, graph_depth: int = 0) -> list[RetrievalHit]:
    index_dir = project_root / "data" / "index"
    if not index_dir.exists():
        return []
    hits_by_provenance: dict[str, RetrievalHit] = {}
    for path in sorted(index_dir.glob("topic_map*.json")):
        if not is_safe_project_artifact_path(path, project_root, "data", "index"):
            continue
        payload = load_json_object(path)
        if not payload:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        nodes = [node for node in payload.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in payload.get("edges", []) if isinstance(edge, dict)]
        nodes_by_id = {str(node.get("node_id", "")): node for node in nodes if str(node.get("node_id", ""))}
        seed_node_ids: set[str] = set()

        for node in nodes:
            content = json_search_text(node)
            score = score_text(content, terms)
            if score <= 0:
                continue
            hit = topic_map_node_hit(node, rel_path=rel_path, terms=terms, score=score)
            add_hit_once(hits_by_provenance, hit)
            seed_node_ids.add(str(node.get("node_id", "")))

        for edge in edges:
            content = json_search_text(edge)
            score = score_text(content, terms)
            if score <= 0:
                continue
            hit = topic_map_edge_hit(edge, rel_path=rel_path, terms=terms, score=score)
            if hit is None:
                continue
            add_hit_once(hits_by_provenance, hit)
            seed_node_ids.add(str(edge.get("source", "")))
            seed_node_ids.add(str(edge.get("target", "")))

        if graph_depth > 0 and seed_node_ids:
            add_topic_map_neighbors(
                hits_by_provenance,
                seed_node_ids=seed_node_ids,
                nodes_by_id=nodes_by_id,
                edges=edges,
                rel_path=rel_path,
                terms=terms,
                depth=graph_depth,
            )
    return list(hits_by_provenance.values())


def topic_map_node_hit(
    node: dict[str, object],
    *,
    rel_path: str,
    terms: list[str],
    score: float,
) -> RetrievalHit:
    node_id = str(node.get("node_id", ""))
    node_type = str(node.get("type", ""))
    title = str(node.get("label") or node_id)
    provenance = [f"topic-map-node:{node_id}"]
    payload = {
        "source_type": "topic_map_node",
        "source_path": rel_path,
        "node_id": node_id,
        "node_type": node_type,
        "title": title,
        "provenance": provenance,
    }
    return RetrievalHit(
        hit_id=encode_hit_id(payload),
        source_type="topic_map_node",
        source_path=rel_path,
        title=title,
        snippet=make_snippet(json_search_text(node), terms),
        score=score,
        provenance=provenance,
    )


def topic_map_edge_hit(
    edge: dict[str, object],
    *,
    rel_path: str,
    terms: list[str],
    score: float,
) -> RetrievalHit | None:
    source = str(edge.get("source", ""))
    target = str(edge.get("target", ""))
    edge_type = str(edge.get("type", ""))
    if not source or not target or not edge_type:
        return None
    title = f"{source} --{edge_type}--> {target}"
    provenance = [f"topic-map-edge:{source}->{target}:{edge_type}"]
    payload = {
        "source_type": "topic_map_edge",
        "source_path": rel_path,
        "edge_source": source,
        "edge_target": target,
        "edge_type": edge_type,
        "title": title,
        "provenance": provenance,
    }
    return RetrievalHit(
        hit_id=encode_hit_id(payload),
        source_type="topic_map_edge",
        source_path=rel_path,
        title=title,
        snippet=make_snippet(json_search_text(edge), terms),
        score=score,
        provenance=provenance,
    )


def add_topic_map_neighbors(
    hits_by_provenance: dict[str, RetrievalHit],
    *,
    seed_node_ids: set[str],
    nodes_by_id: dict[str, dict[str, object]],
    edges: list[dict[str, object]],
    rel_path: str,
    terms: list[str],
    depth: int,
) -> None:
    visited = {node_id for node_id in seed_node_ids if node_id}
    frontier: list[tuple[str, list[str], list[dict[str, object]]]] = [
        (node_id, [node_id], []) for node_id in sorted(visited)
    ]
    neighbor_score = 0.1
    path_score = 0.05
    for _step in range(max(0, depth)):
        next_frontier: list[tuple[str, list[str], list[dict[str, object]]]] = []
        for current_node_id, path_nodes, path_edges in frontier:
            for edge in edges:
                source = str(edge.get("source", ""))
                target = str(edge.get("target", ""))
                edge_type = str(edge.get("type", ""))
                if not source or not target or not edge_type:
                    continue
                if source == current_node_id:
                    next_node_id = target
                elif target == current_node_id:
                    next_node_id = source
                else:
                    continue

                edge_hit = topic_map_edge_hit(edge, rel_path=rel_path, terms=terms, score=neighbor_score)
                if edge_hit is not None:
                    add_hit_once(hits_by_provenance, edge_hit)
                for node_id in (source, target):
                    if node_id in nodes_by_id:
                        node_hit = topic_map_node_hit(
                            nodes_by_id[node_id],
                            rel_path=rel_path,
                            terms=terms,
                            score=neighbor_score,
                        )
                        add_hit_once(hits_by_provenance, node_hit)

                if next_node_id in path_nodes:
                    continue
                next_path_nodes = [*path_nodes, next_node_id]
                next_path_edges = [*path_edges, topic_map_edge_ref(edge)]
                if next_path_edges:
                    path_hit = topic_map_path_hit(
                        next_path_nodes,
                        next_path_edges,
                        nodes_by_id=nodes_by_id,
                        rel_path=rel_path,
                        score=path_score + len(next_path_edges) * 0.001,
                    )
                    add_hit_once(hits_by_provenance, path_hit)
                if next_node_id not in visited:
                    next_frontier.append((next_node_id, next_path_nodes, next_path_edges))
                    visited.add(next_node_id)
        frontier = next_frontier
        if not frontier:
            break


def topic_map_edge_ref(edge: dict[str, object]) -> dict[str, str]:
    return {
        "source": str(edge.get("source", "")),
        "target": str(edge.get("target", "")),
        "type": str(edge.get("type", "")),
    }


def topic_map_path_hit(
    path_nodes: list[str],
    path_edges: list[dict[str, object]],
    *,
    nodes_by_id: dict[str, dict[str, object]],
    rel_path: str,
    score: float,
) -> RetrievalHit:
    title = " → ".join(topic_map_node_type(node_id, nodes_by_id) for node_id in path_nodes)
    path_summary = format_topic_map_path(path_nodes, path_edges)
    provenance = [f"topic-map-path:{'->'.join(path_nodes)}"]
    payload = {
        "source_type": "topic_map_path",
        "source_path": rel_path,
        "path_nodes": path_nodes,
        "path_edges": path_edges,
        "path_summary": path_summary,
        "title": title,
        "provenance": provenance,
    }
    return RetrievalHit(
        hit_id=encode_hit_id(payload),
        source_type="topic_map_path",
        source_path=rel_path,
        title=title,
        snippet=path_summary,
        score=score,
        provenance=provenance,
    )


def topic_map_node_type(node_id: str, nodes_by_id: dict[str, dict[str, object]]) -> str:
    node = nodes_by_id.get(node_id)
    if node is not None and str(node.get("type", "")):
        return str(node.get("type", ""))
    return node_id.split(":", 1)[0]


def format_topic_map_path(path_nodes: list[str], path_edges: list[dict[str, object]]) -> str:
    if not path_nodes:
        return ""
    pieces = [path_nodes[0]]
    current = path_nodes[0]
    for edge, next_node in zip(path_edges, path_nodes[1:]):
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        edge_type = str(edge.get("type", ""))
        if current == source and next_node == target:
            pieces.append(f"--{edge_type}--> {next_node}")
        elif current == target and next_node == source:
            pieces.append(f"<--{edge_type}-- {next_node}")
        else:
            pieces.append(f"--{edge_type}-- {next_node}")
        current = next_node
    return " ".join(pieces)


def add_hit_once(hits_by_provenance: dict[str, RetrievalHit], hit: RetrievalHit) -> None:
    key = hit.provenance[0] if hit.provenance else hit.hit_id
    existing = hits_by_provenance.get(key)
    if existing is None or hit.score > existing.score:
        hits_by_provenance[key] = hit


def find_topic_map_node(path: Path, node_id: str) -> dict[str, object]:
    payload = load_json_object(path)
    if payload is None:
        raise ValueError(f"Expected topic map object in {path}")
    for node in payload.get("nodes", []):
        if isinstance(node, dict) and str(node.get("node_id", "")) == node_id:
            return node
    raise KeyError(f"Missing topic map node_id={node_id!r} in {path}")


def find_topic_map_edge(path: Path, *, source: str, target: str, edge_type: str) -> dict[str, object]:
    payload = load_json_object(path)
    if payload is None:
        raise ValueError(f"Expected topic map object in {path}")
    for edge in payload.get("edges", []):
        if not isinstance(edge, dict):
            continue
        if (
            str(edge.get("source", "")) == source
            and str(edge.get("target", "")) == target
            and str(edge.get("type", "")) == edge_type
        ):
            return edge
    raise KeyError(f"Missing topic map edge {source!r}->{target!r}:{edge_type!r} in {path}")
