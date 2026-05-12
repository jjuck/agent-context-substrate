from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3

from .models import ContextPacket, MicroSummary, RawSessionReference, UnitSummary
from .paths import HarnessPaths
from .retrieval_ids import decode_hit_id, encode_hit_id
from .retrieval_scoring import (
    make_snippet as _make_snippet,
    rank_hits,
    score_text as _score_text,
    tokenize_query as _tokenize,
)
from .retrieval_sources import (
    iter_jsonl_objects,
    json_search_text,
    load_context_packet,
    load_json_list,
    load_json_object,
    load_jsonl_record,
    read_text_lossy,
)
from .safe_paths import is_safe_project_artifact_path, is_safe_wiki_page_path
from .retrieval_types import RetrievalHit, RetrievalHitDetail


def search_knowledge(
    query: str,
    *,
    project_root: Path,
    wiki_root: Path,
    limit: int = 5,
    include_raw: bool = False,
    mode: str = "knowledge",
    graph_depth: int = 0,
) -> list[RetrievalHit]:
    """Search durable wiki, packet artifacts, summaries, topic map, and optionally raw messages.

    This is intentionally vectorless for the MVP: it provides deterministic,
    read-only retrieval with provenance so Hermes can use it as a RAG-like
    fallback while performing user requests.
    """
    project_root = Path(project_root)
    wiki_root = Path(wiki_root)
    terms = _tokenize(query)
    if not terms:
        return []

    normalized_mode = mode.strip().lower() if mode else "knowledge"
    if normalized_mode not in {"knowledge", "graph", "recovery"}:
        raise ValueError(f"Unsupported retrieval mode: {mode!r}")

    hits: list[RetrievalHit] = []
    if normalized_mode == "graph":
        hits.extend(_search_topic_map(terms, project_root, graph_depth=graph_depth))
        return rank_hits(hits)[: max(0, limit)]
    if normalized_mode == "recovery":
        hits.extend(_search_recovery_briefs(terms, project_root))
        hits.extend(_search_recovery_packets(terms, project_root))
        return rank_hits(hits, source_priority_first=True)[: max(0, limit)]

    hits.extend(_search_wiki(terms, wiki_root))
    hits.extend(_search_packets(terms, project_root))
    hits.extend(_search_topic_map(terms, project_root))
    hits.extend(_search_promotions(terms, project_root))
    hits.extend(_search_wiki_patches(terms, project_root))
    if include_raw:
        hits.extend(_search_raw_messages(terms, project_root))

    return rank_hits(hits)[: max(0, limit)]


def expand_hit(
    hit_id: str,
    *,
    project_root: Path,
    wiki_root: Path,
) -> RetrievalHitDetail:
    payload = decode_hit_id(hit_id)
    source_type = str(payload["source_type"])
    source_path = str(payload.get("source_path", ""))
    project_root = Path(project_root)
    wiki_root = Path(wiki_root)

    if source_type == "wiki":
        path = _resolve_wiki_path(wiki_root, source_path)
        content = path.read_text(encoding="utf-8")
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={"source_type": source_type, "source_path": source_path},
        )

    if source_type in {"packet", "unit_summary", "micro_summary", "recovery_packet"}:
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        payload_json = json.loads(path.read_text(encoding="utf-8"))
        content = json.dumps(payload_json, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "packet_id": payload.get("packet_id", ""),
                "item_id": payload.get("item_id", ""),
            },
        )

    if source_type == "recovery_brief":
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        payload_json = json.loads(path.read_text(encoding="utf-8"))
        content = json.dumps(payload_json, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "session_id": payload.get("session_id", ""),
                "packet_id": payload.get("packet_id", ""),
            },
        )

    if source_type == "topic_map_node":
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        node = _find_topic_map_node(path, str(payload.get("node_id", "")))
        content = json.dumps(node, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "node_id": payload.get("node_id", ""),
                "node_type": payload.get("node_type", ""),
            },
        )

    if source_type == "topic_map_edge":
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        edge = _find_topic_map_edge(
            path,
            source=str(payload.get("edge_source", "")),
            target=str(payload.get("edge_target", "")),
            edge_type=str(payload.get("edge_type", "")),
        )
        content = json.dumps(edge, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "edge_source": payload.get("edge_source", ""),
                "edge_target": payload.get("edge_target", ""),
                "edge_type": payload.get("edge_type", ""),
            },
        )

    if source_type == "topic_map_path":
        path_nodes = [str(item) for item in payload.get("path_nodes", []) if item]
        path_edges = [edge for edge in payload.get("path_edges", []) if isinstance(edge, dict)]
        content_payload = {
            "path_summary": str(payload.get("path_summary", "")),
            "path_nodes": path_nodes,
            "path_edges": path_edges,
        }
        content = json.dumps(content_payload, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=str(payload.get("path_summary", "")))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "path_length": len(path_edges),
            },
        )

    if source_type == "promotion_candidate":
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        candidate = _find_json_list_item(path, "candidate_id", str(payload.get("candidate_id", "")))
        content = json.dumps(candidate, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "candidate_id": payload.get("candidate_id", ""),
                "packet_id": payload.get("packet_id", ""),
            },
        )

    if source_type == "wiki_patch":
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        operation = _find_wiki_patch_operation(path, str(payload.get("patch_id", "")))
        content = json.dumps(operation, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "patch_id": payload.get("patch_id", ""),
                "candidate_id": payload.get("candidate_id", ""),
                "packet_id": payload.get("packet_id", ""),
            },
        )

    if source_type == "applied_patch":
        path = _resolve_project_path(project_root, source_path, source_type=source_type)
        record = load_jsonl_record(path, int(payload.get("line_index", -1)))
        content = json.dumps(record, ensure_ascii=False, indent=2)
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "source_path": source_path,
                "line_index": payload.get("line_index", -1),
                "patch_id": payload.get("patch_id", ""),
                "candidate_id": payload.get("candidate_id", ""),
                "packet_id": payload.get("packet_id", ""),
            },
        )

    if source_type == "raw_message":
        raise ValueError("Raw message expansion is disabled; use search snippets and provenance for raw hits")

    raise ValueError(f"Unknown retrieval hit source_type={source_type!r}")


def _search_wiki(terms: list[str], wiki_root: Path) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    if not wiki_root.exists():
        return hits
    for path in sorted(wiki_root.rglob("*.md")):
        if not is_safe_wiki_page_path(path, wiki_root):
            continue
        content = read_text_lossy(path)
        score = _score_text(content, terms)
        if score <= 0:
            continue
        rel_path = path.relative_to(wiki_root).as_posix()
        title = _extract_markdown_title(content) or path.stem
        snippet = _make_snippet(content, terms)
        payload = {
            "source_type": "wiki",
            "source_path": rel_path,
            "title": title,
            "provenance": [f"wiki:{rel_path}"],
        }
        hits.append(
            RetrievalHit(
                hit_id=encode_hit_id(payload),
                source_type="wiki",
                source_path=rel_path,
                title=title,
                snippet=snippet,
                score=score,
                provenance=[f"wiki:{rel_path}"],
            )
        )
    return hits


def _search_recovery_briefs(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    recovery_dir = project_root / "data" / "exports" / "recovery"
    if not recovery_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(recovery_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROJECT_SOURCE_PREFIXES["recovery_brief"]):
            continue
        payload = load_json_object(path)
        if payload is None:
            continue
        content = _recovery_brief_search_text(payload)
        score = _score_text(content, terms)
        if score <= 0:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        session_id = str(payload.get("session_id") or path.stem)
        packet_id = str(payload.get("packet_id", ""))
        title = str(payload.get("task_title") or session_id)
        provenance = [f"recovery:{session_id}"]
        provenance.extend(str(item) for item in payload.get("provenance", []) if item)
        hit_payload = {
            "source_type": "recovery_brief",
            "source_path": rel_path,
            "session_id": session_id,
            "packet_id": packet_id,
            "title": title,
            "provenance": provenance,
        }
        hits.append(
            RetrievalHit(
                hit_id=encode_hit_id(hit_payload),
                source_type="recovery_brief",
                source_path=rel_path,
                title=title,
                snippet=_make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits


def _search_recovery_packets(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    packet_dir = project_root / "data" / "exports" / "context_packets"
    if not packet_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(packet_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROJECT_SOURCE_PREFIXES["recovery_packet"]):
            continue
        packet = load_context_packet(path)
        if packet is None:
            continue
        content = _packet_recovery_search_text(packet)
        score = _score_text(content, terms)
        if score <= 0:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        provenance = [_format_pointer(pointer) for pointer in packet.raw_pointers]
        hit_payload = {
            "source_type": "recovery_packet",
            "source_path": rel_path,
            "packet_id": packet.packet_id,
            "title": packet.task_title,
            "provenance": provenance,
        }
        hits.append(
            RetrievalHit(
                hit_id=encode_hit_id(hit_payload),
                source_type="recovery_packet",
                source_path=rel_path,
                title=packet.task_title,
                snippet=_make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits


def _search_packets(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    packet_dir = project_root / "data" / "exports" / "context_packets"
    if not packet_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(packet_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROJECT_SOURCE_PREFIXES["packet"]):
            continue
        packet = load_context_packet(path)
        if packet is None:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        packet_text = _packet_search_text(packet)
        packet_score = _score_text(packet_text, terms)
        if packet_score > 0:
            provenance = [_format_pointer(pointer) for pointer in packet.raw_pointers]
            payload = {
                "source_type": "packet",
                "source_path": rel_path,
                "packet_id": packet.packet_id,
                "title": packet.task_title,
                "provenance": provenance,
            }
            hits.append(
                RetrievalHit(
                    hit_id=encode_hit_id(payload),
                    source_type="packet",
                    source_path=rel_path,
                    title=packet.task_title,
                    snippet=_make_snippet(packet_text, terms),
                    score=packet_score,
                    provenance=provenance,
                )
            )
        for unit in packet.unit_summaries:
            hits.extend(_summary_hit_if_match(terms, project_root, rel_path, packet, unit))
        for micro in packet.micro_summaries:
            hits.extend(_summary_hit_if_match(terms, project_root, rel_path, packet, micro))
    return hits


def _summary_hit_if_match(
    terms: list[str],
    project_root: Path,
    rel_path: str,
    packet: ContextPacket,
    summary: UnitSummary | MicroSummary,
) -> list[RetrievalHit]:
    if isinstance(summary, UnitSummary):
        source_type = "unit_summary"
        item_id = summary.unit_id
        title = summary.title
        content = "\n".join(
            [
                summary.title,
                summary.goal,
                *summary.decisions,
                *summary.progress,
                *summary.open_questions,
                *summary.related_pages,
            ]
        )
        provenance = [_format_pointer(summary.provenance)] if summary.provenance else []
    else:
        source_type = "micro_summary"
        item_id = summary.micro_id
        title = summary.request or summary.summary[:80] or summary.micro_id
        content = "\n".join(
            [
                summary.summary,
                summary.why_it_matters,
                summary.request or "",
                summary.outcome or "",
                *summary.key_points,
                *summary.follow_up_questions,
                *summary.files,
                *summary.entities,
                *summary.concepts,
            ]
        )
        provenance = [_format_pointer(summary.provenance)] if summary.provenance else []

    score = _score_text(content, terms)
    if score <= 0:
        return []
    payload = {
        "source_type": source_type,
        "source_path": rel_path,
        "packet_id": packet.packet_id,
        "item_id": item_id,
        "title": title,
        "provenance": provenance,
    }
    return [
        RetrievalHit(
            hit_id=encode_hit_id(payload),
            source_type=source_type,
            source_path=rel_path,
            title=title,
            snippet=_make_snippet(content, terms),
            score=score,
            provenance=provenance,
        )
    ]


def _search_topic_map(terms: list[str], project_root: Path, *, graph_depth: int = 0) -> list[RetrievalHit]:
    index_dir = project_root / "data" / "index"
    if not index_dir.exists():
        return []
    hits_by_provenance: dict[str, RetrievalHit] = {}
    for path in sorted(index_dir.glob("topic_map*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROJECT_SOURCE_PREFIXES["topic_map_node"]):
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
            score = _score_text(content, terms)
            if score <= 0:
                continue
            hit = _topic_map_node_hit(node, rel_path=rel_path, terms=terms, score=score)
            _add_hit_once(hits_by_provenance, hit)
            seed_node_ids.add(str(node.get("node_id", "")))

        for edge in edges:
            content = json_search_text(edge)
            score = _score_text(content, terms)
            if score <= 0:
                continue
            hit = _topic_map_edge_hit(edge, rel_path=rel_path, terms=terms, score=score)
            if hit is None:
                continue
            _add_hit_once(hits_by_provenance, hit)
            seed_node_ids.add(str(edge.get("source", "")))
            seed_node_ids.add(str(edge.get("target", "")))

        if graph_depth > 0 and seed_node_ids:
            _add_topic_map_neighbors(
                hits_by_provenance,
                seed_node_ids=seed_node_ids,
                nodes_by_id=nodes_by_id,
                edges=edges,
                rel_path=rel_path,
                terms=terms,
                depth=graph_depth,
            )
    return list(hits_by_provenance.values())


def _topic_map_node_hit(
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
        snippet=_make_snippet(json_search_text(node), terms),
        score=score,
        provenance=provenance,
    )


def _topic_map_edge_hit(
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
        snippet=_make_snippet(json_search_text(edge), terms),
        score=score,
        provenance=provenance,
    )


def _add_topic_map_neighbors(
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

                edge_hit = _topic_map_edge_hit(edge, rel_path=rel_path, terms=terms, score=neighbor_score)
                if edge_hit is not None:
                    _add_hit_once(hits_by_provenance, edge_hit)
                for node_id in (source, target):
                    if node_id in nodes_by_id:
                        node_hit = _topic_map_node_hit(
                            nodes_by_id[node_id],
                            rel_path=rel_path,
                            terms=terms,
                            score=neighbor_score,
                        )
                        _add_hit_once(hits_by_provenance, node_hit)

                if next_node_id in path_nodes:
                    continue
                next_path_nodes = [*path_nodes, next_node_id]
                next_path_edges = [*path_edges, _topic_map_edge_ref(edge)]
                if next_path_edges:
                    path_hit = _topic_map_path_hit(
                        next_path_nodes,
                        next_path_edges,
                        nodes_by_id=nodes_by_id,
                        rel_path=rel_path,
                        score=path_score + len(next_path_edges) * 0.001,
                    )
                    _add_hit_once(hits_by_provenance, path_hit)
                if next_node_id not in visited:
                    next_frontier.append((next_node_id, next_path_nodes, next_path_edges))
                    visited.add(next_node_id)
        frontier = next_frontier
        if not frontier:
            break


def _topic_map_edge_ref(edge: dict[str, object]) -> dict[str, str]:
    return {
        "source": str(edge.get("source", "")),
        "target": str(edge.get("target", "")),
        "type": str(edge.get("type", "")),
    }


def _topic_map_path_hit(
    path_nodes: list[str],
    path_edges: list[dict[str, object]],
    *,
    nodes_by_id: dict[str, dict[str, object]],
    rel_path: str,
    score: float,
) -> RetrievalHit:
    title = " → ".join(_topic_map_node_type(node_id, nodes_by_id) for node_id in path_nodes)
    path_summary = _format_topic_map_path(path_nodes, path_edges)
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


def _topic_map_node_type(node_id: str, nodes_by_id: dict[str, dict[str, object]]) -> str:
    node = nodes_by_id.get(node_id)
    if node is not None and str(node.get("type", "")):
        return str(node.get("type", ""))
    return node_id.split(":", 1)[0]


def _format_topic_map_path(path_nodes: list[str], path_edges: list[dict[str, object]]) -> str:
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


def _add_hit_once(hits_by_provenance: dict[str, RetrievalHit], hit: RetrievalHit) -> None:
    key = hit.provenance[0] if hit.provenance else hit.hit_id
    existing = hits_by_provenance.get(key)
    if existing is None or hit.score > existing.score:
        hits_by_provenance[key] = hit


def _search_promotions(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    promotions_dir = project_root / "data" / "promotions"
    if not promotions_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(promotions_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROJECT_SOURCE_PREFIXES["promotion_candidate"]):
            continue
        payload = load_json_list(path)
        if payload is None:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        for candidate in payload:
            if not isinstance(candidate, dict):
                continue
            content = json_search_text(candidate)
            score = _score_text(content, terms)
            if score <= 0:
                continue
            candidate_id = str(candidate.get("candidate_id", ""))
            packet_id = str(candidate.get("packet_id", ""))
            evidence = [str(item) for item in candidate.get("evidence", []) if item]
            provenance = [f"promotion:{candidate_id}", *evidence] if candidate_id else evidence
            title = candidate_id or f"Promotion candidate in {path.name}"
            hit_payload = {
                "source_type": "promotion_candidate",
                "source_path": rel_path,
                "candidate_id": candidate_id,
                "packet_id": packet_id,
                "title": title,
                "provenance": provenance,
            }
            hits.append(
                RetrievalHit(
                    hit_id=encode_hit_id(hit_payload),
                    source_type="promotion_candidate",
                    source_path=rel_path,
                    title=title,
                    snippet=_make_snippet(content, terms),
                    score=score,
                    provenance=provenance,
                )
            )
    return hits


def _search_wiki_patches(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    wiki_patches_dir = project_root / "data" / "wiki_patches"
    if not wiki_patches_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(wiki_patches_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROJECT_SOURCE_PREFIXES["wiki_patch"]):
            continue
        proposal = load_json_object(path)
        if proposal is None:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        packet_id = str(proposal.get("packet_id", ""))
        for operation in proposal.get("operations", []):
            if not isinstance(operation, dict):
                continue
            content = json_search_text(operation)
            score = _score_text(content, terms)
            if score <= 0:
                continue
            patch_id = str(operation.get("patch_id", ""))
            candidate_id = str(operation.get("candidate_id", ""))
            evidence = [str(item) for item in operation.get("evidence", []) if item]
            provenance = [f"wiki-patch:{patch_id}", *evidence] if patch_id else evidence
            title = patch_id or f"Wiki patch in {path.name}"
            hit_payload = {
                "source_type": "wiki_patch",
                "source_path": rel_path,
                "patch_id": patch_id,
                "candidate_id": candidate_id,
                "packet_id": packet_id,
                "title": title,
                "provenance": provenance,
            }
            hits.append(
                RetrievalHit(
                    hit_id=encode_hit_id(hit_payload),
                    source_type="wiki_patch",
                    source_path=rel_path,
                    title=title,
                    snippet=_make_snippet(content, terms),
                    score=score,
                    provenance=provenance,
                )
            )
    applied_log = wiki_patches_dir / "applied.jsonl"
    if applied_log.exists() and is_safe_project_artifact_path(applied_log, project_root, *_PROJECT_SOURCE_PREFIXES["applied_patch"]):
        hits.extend(_search_applied_patch_log(terms, project_root, applied_log))
    return hits


def _search_applied_patch_log(terms: list[str], project_root: Path, path: Path) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    rel_path = path.relative_to(project_root).as_posix()
    for line_index, record in iter_jsonl_objects(path):
        content = json_search_text(record)
        score = _score_text(content, terms)
        if score <= 0:
            continue
        patch_id = str(record.get("patch_id", ""))
        candidate_id = str(record.get("candidate_id", ""))
        packet_id = str(record.get("packet_id", ""))
        provenance = [f"applied-patch:{patch_id}"] if patch_id else [f"applied-patch-line:{line_index}"]
        title = patch_id or f"Applied patch line {line_index}"
        payload = {
            "source_type": "applied_patch",
            "source_path": rel_path,
            "line_index": line_index,
            "patch_id": patch_id,
            "candidate_id": candidate_id,
            "packet_id": packet_id,
            "title": title,
            "provenance": provenance,
        }
        hits.append(
            RetrievalHit(
                hit_id=encode_hit_id(payload),
                source_type="applied_patch",
                source_path=rel_path,
                title=title,
                snippet=_make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits


def _search_raw_messages(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    paths = HarnessPaths(project_root=project_root)
    db_path = paths.state_db_path
    if not db_path.exists():
        return []
    where = " OR ".join(["LOWER(m.content) LIKE ?" for _ in terms])
    params = [f"%{term}%" for term in terms]
    query = f"""
        SELECT m.id, m.session_id, m.role, m.content, s.title, s.source
        FROM messages m
        LEFT JOIN sessions s ON s.id = m.session_id
        WHERE {where}
        ORDER BY m.id DESC
        LIMIT 50
    """
    hits: list[RetrievalHit] = []
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()
    except sqlite3.Error:
        return []
    for row in rows:
        content = str(row["content"] or "")
        score = _score_text(content, terms)
        if score <= 0:
            continue
        session_id = str(row["session_id"])
        message_id = int(row["id"])
        title = str(row["title"] or session_id)
        provenance = [f"hermes-session:{session_id}#messages={message_id}"]
        payload = {
            "source_type": "raw_message",
            "source_path": f"state.db:{session_id}:{message_id}",
            "session_id": session_id,
            "message_id": message_id,
            "title": title,
            "provenance": provenance,
        }
        hits.append(
            RetrievalHit(
                hit_id=encode_hit_id(payload),
                source_type="raw_message",
                source_path=f"state.db:{session_id}:{message_id}",
                title=title,
                snippet=_make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits



def _find_topic_map_node(path: Path, node_id: str) -> dict[str, object]:
    payload = load_json_object(path)
    if payload is None:
        raise ValueError(f"Expected topic map object in {path}")
    for node in payload.get("nodes", []):
        if isinstance(node, dict) and str(node.get("node_id", "")) == node_id:
            return node
    raise KeyError(f"Missing topic map node_id={node_id!r} in {path}")


def _find_topic_map_edge(path: Path, *, source: str, target: str, edge_type: str) -> dict[str, object]:
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


def _find_json_list_item(path: Path, key: str, value: str) -> dict[str, object]:
    payload = load_json_list(path)
    if payload is None:
        raise ValueError(f"Expected JSON list in {path}")
    for item in payload:
        if isinstance(item, dict) and str(item.get(key, "")) == value:
            return item
    raise KeyError(f"Missing {key}={value!r} in {path}")


def _find_wiki_patch_operation(path: Path, patch_id: str) -> dict[str, object]:
    payload = load_json_object(path)
    if payload is None:
        raise ValueError(f"Expected wiki patch proposal object in {path}")
    for operation in payload.get("operations", []):
        if isinstance(operation, dict) and str(operation.get("patch_id", "")) == patch_id:
            return operation
    raise KeyError(f"Missing patch_id={patch_id!r} in {path}")


def _recovery_brief_search_text(payload: dict[str, object]) -> str:
    pieces: list[str] = []
    for key in (
        "session_id",
        "packet_id",
        "task_title",
        "macro_context",
        "decisions",
        "critical_files",
        "open_questions",
        "related_pages",
        "provenance",
    ):
        pieces.extend(_flatten_text_value(payload.get(key)))
    return "\n".join(piece for piece in pieces if piece)


def _packet_recovery_search_text(packet: ContextPacket) -> str:
    pieces: list[str] = [packet.packet_id, packet.task_title, packet.macro_context]
    pieces.extend(packet.critical_files)
    pieces.extend(packet.open_questions)
    for unit in packet.unit_summaries:
        pieces.extend([unit.title, unit.goal, *unit.decisions, *unit.progress, *unit.open_questions])
    for micro in packet.micro_summaries:
        pieces.extend(
            [
                micro.summary,
                micro.why_it_matters,
                micro.request or "",
                micro.outcome or "",
                *micro.key_points,
                *micro.follow_up_questions,
                *micro.files,
                *micro.concepts,
            ]
        )
    return "\n".join(piece for piece in pieces if piece)


def _flatten_text_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        pieces: list[str] = []
        for item in value:
            pieces.extend(_flatten_text_value(item))
        return pieces
    if isinstance(value, dict):
        pieces: list[str] = []
        for item in value.values():
            pieces.extend(_flatten_text_value(item))
        return pieces
    return [str(value)]


def _packet_search_text(packet: ContextPacket) -> str:
    pieces: list[str] = [packet.packet_id, packet.task_title, packet.macro_context]
    pieces.extend(packet.critical_files)
    pieces.extend(packet.open_questions)
    for unit in packet.unit_summaries:
        pieces.extend([unit.title, unit.goal, *unit.decisions, *unit.progress, *unit.open_questions])
    for micro in packet.micro_summaries:
        pieces.extend(
            [
                micro.summary,
                micro.why_it_matters,
                micro.request or "",
                micro.outcome or "",
                *micro.key_points,
                *micro.follow_up_questions,
                *micro.files,
                *micro.concepts,
            ]
        )
    return "\n".join(piece for piece in pieces if piece)


def _extract_markdown_title(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _format_pointer(pointer: RawSessionReference | None) -> str:
    if pointer is None:
        return ""
    message_ids = ",".join(str(message_id) for message_id in pointer.message_ids)
    return f"hermes-session:{pointer.session_id}#messages={message_ids}"


def _hit_from_payload(payload: dict[str, Any], *, content: str) -> RetrievalHit:
    return RetrievalHit(
        hit_id=encode_hit_id(payload),
        source_type=str(payload["source_type"]),
        source_path=str(payload.get("source_path", "")),
        title=str(payload.get("title", "")),
        snippet=content[:240],
        score=0.0,
        provenance=[str(item) for item in payload.get("provenance", []) if item],
    )


_PROJECT_SOURCE_PREFIXES = {
    "recovery_brief": ("data", "exports", "recovery"),
    "recovery_packet": ("data", "exports", "context_packets"),
    "packet": ("data", "exports", "context_packets"),
    "unit_summary": ("data", "exports", "context_packets"),
    "micro_summary": ("data", "exports", "context_packets"),
    "topic_map_node": ("data", "index"),
    "topic_map_edge": ("data", "index"),
    "promotion_candidate": ("data", "promotions"),
    "wiki_patch": ("data", "wiki_patches"),
    "applied_patch": ("data", "wiki_patches"),
}


def _resolve_wiki_path(wiki_root: Path, value: str) -> Path:
    resolved = _resolve_child_path(wiki_root, value, "wiki")
    if not is_safe_wiki_page_path(resolved, wiki_root.resolve()):
        raise ValueError(f"Unsafe wiki path: {value!r}")
    return resolved


def _resolve_project_path(project_root: Path, value: str, *, source_type: str) -> Path:
    path = Path(value)
    allowed_prefix = _PROJECT_SOURCE_PREFIXES.get(source_type)
    if allowed_prefix is None:
        raise ValueError(f"Unsupported project source_type: {source_type!r}")
    if tuple(path.parts[: len(allowed_prefix)]) != allowed_prefix:
        raise ValueError(f"Unsafe project path for {source_type}: {value!r}")
    resolved = _resolve_child_path(project_root, value, "project")
    allowed_root = (project_root.resolve() / Path(*allowed_prefix)).resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"Unsafe project path for {source_type}: {value!r}") from exc
    return resolved


def _resolve_child_path(root: Path, value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe {label} path: {value!r}")
    resolved_root = root.resolve()
    resolved = (resolved_root / path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Unsafe {label} path: {value!r}") from exc
    return resolved
