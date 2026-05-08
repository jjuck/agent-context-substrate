from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import base64
import json
import re
import sqlite3

from .models import ContextPacket, MicroSummary, RawSessionReference, UnitSummary
from .paths import HarnessPaths


@dataclass(frozen=True)
class RetrievalHit:
    hit_id: str
    source_type: str
    source_path: str
    title: str
    snippet: str
    score: float
    provenance: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "hit_id": self.hit_id,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class RetrievalHitDetail:
    hit: RetrievalHit
    content: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "hit": self.hit.to_dict(),
            "content": self.content,
            "metadata": dict(self.metadata),
        }


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
    if normalized_mode not in {"knowledge", "graph"}:
        raise ValueError(f"Unsupported retrieval mode: {mode!r}")

    hits: list[RetrievalHit] = []
    if normalized_mode == "graph":
        hits.extend(_search_topic_map(terms, project_root, graph_depth=graph_depth))
        hits.sort(key=lambda hit: (-hit.score, _source_rank(hit.source_type), hit.title, hit.hit_id))
        return hits[: max(0, limit)]

    hits.extend(_search_wiki(terms, wiki_root))
    hits.extend(_search_packets(terms, project_root))
    hits.extend(_search_topic_map(terms, project_root))
    hits.extend(_search_promotions(terms, project_root))
    hits.extend(_search_wiki_patches(terms, project_root))
    if include_raw:
        hits.extend(_search_raw_messages(terms, project_root))

    hits.sort(key=lambda hit: (-hit.score, _source_rank(hit.source_type), hit.title, hit.hit_id))
    return hits[: max(0, limit)]


def expand_hit(
    hit_id: str,
    *,
    project_root: Path,
    wiki_root: Path,
) -> RetrievalHitDetail:
    payload = _decode_hit_id(hit_id)
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

    if source_type in {"packet", "unit_summary", "micro_summary"}:
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
        record = _load_jsonl_record(path, int(payload.get("line_index", -1)))
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


def _is_searchable_wiki_path(path: Path, wiki_root: Path) -> bool:
    try:
        resolved_root = wiki_root.resolve()
        resolved_path = path.resolve()
        relative_parts = resolved_path.relative_to(resolved_root).parts
    except (OSError, ValueError):
        return False
    if any(part.startswith(".") for part in relative_parts):
        return False
    if not relative_parts:
        return False
    top_level = relative_parts[0]
    if top_level in {"_system", "90 보관"}:
        return False
    return True


def _search_wiki(terms: list[str], wiki_root: Path) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    if not wiki_root.exists():
        return hits
    for path in sorted(wiki_root.rglob("*.md")):
        if not _is_searchable_wiki_path(path, wiki_root):
            continue
        content = _safe_read_text(path)
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
                hit_id=_encode_hit_id(payload),
                source_type="wiki",
                source_path=rel_path,
                title=title,
                snippet=snippet,
                score=score,
                provenance=[f"wiki:{rel_path}"],
            )
        )
    return hits


def _search_packets(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    packet_dir = project_root / "data" / "exports" / "context_packets"
    if not packet_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(packet_dir.glob("*.json")):
        packet = _load_packet(path)
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
                    hit_id=_encode_hit_id(payload),
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
            hit_id=_encode_hit_id(payload),
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
        payload = _load_json_object(path)
        if not payload:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        nodes = [node for node in payload.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in payload.get("edges", []) if isinstance(edge, dict)]
        nodes_by_id = {str(node.get("node_id", "")): node for node in nodes if str(node.get("node_id", ""))}
        seed_node_ids: set[str] = set()

        for node in nodes:
            content = _json_search_text(node)
            score = _score_text(content, terms)
            if score <= 0:
                continue
            hit = _topic_map_node_hit(node, rel_path=rel_path, terms=terms, score=score)
            _add_hit_once(hits_by_provenance, hit)
            seed_node_ids.add(str(node.get("node_id", "")))

        for edge in edges:
            content = _json_search_text(edge)
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
        hit_id=_encode_hit_id(payload),
        source_type="topic_map_node",
        source_path=rel_path,
        title=title,
        snippet=_make_snippet(_json_search_text(node), terms),
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
        hit_id=_encode_hit_id(payload),
        source_type="topic_map_edge",
        source_path=rel_path,
        title=title,
        snippet=_make_snippet(_json_search_text(edge), terms),
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
        hit_id=_encode_hit_id(payload),
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
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, list):
            continue
        rel_path = path.relative_to(project_root).as_posix()
        for candidate in payload:
            if not isinstance(candidate, dict):
                continue
            content = _json_search_text(candidate)
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
                    hit_id=_encode_hit_id(hit_payload),
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
        try:
            proposal = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(proposal, dict):
            continue
        rel_path = path.relative_to(project_root).as_posix()
        packet_id = str(proposal.get("packet_id", ""))
        for operation in proposal.get("operations", []):
            if not isinstance(operation, dict):
                continue
            content = _json_search_text(operation)
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
                    hit_id=_encode_hit_id(hit_payload),
                    source_type="wiki_patch",
                    source_path=rel_path,
                    title=title,
                    snippet=_make_snippet(content, terms),
                    score=score,
                    provenance=provenance,
                )
            )
    applied_log = wiki_patches_dir / "applied.jsonl"
    if applied_log.exists():
        hits.extend(_search_applied_patch_log(terms, project_root, applied_log))
    return hits


def _search_applied_patch_log(terms: list[str], project_root: Path, path: Path) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    rel_path = path.relative_to(project_root).as_posix()
    for line_index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        content = _json_search_text(record)
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
                hit_id=_encode_hit_id(payload),
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
                hit_id=_encode_hit_id(payload),
                source_type="raw_message",
                source_path=f"state.db:{session_id}:{message_id}",
                title=title,
                snippet=_make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits



def _load_packet(path: Path) -> ContextPacket | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ContextPacket.from_dict(payload)
    except Exception:
        return None


def _json_search_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _load_json_object(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _find_topic_map_node(path: Path, node_id: str) -> dict[str, object]:
    payload = _load_json_object(path)
    if payload is None:
        raise ValueError(f"Expected topic map object in {path}")
    for node in payload.get("nodes", []):
        if isinstance(node, dict) and str(node.get("node_id", "")) == node_id:
            return node
    raise KeyError(f"Missing topic map node_id={node_id!r} in {path}")


def _find_topic_map_edge(path: Path, *, source: str, target: str, edge_type: str) -> dict[str, object]:
    payload = _load_json_object(path)
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {path}")
    for item in payload:
        if isinstance(item, dict) and str(item.get(key, "")) == value:
            return item
    raise KeyError(f"Missing {key}={value!r} in {path}")


def _find_wiki_patch_operation(path: Path, patch_id: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected wiki patch proposal object in {path}")
    for operation in payload.get("operations", []):
        if isinstance(operation, dict) and str(operation.get("patch_id", "")) == patch_id:
            return operation
    raise KeyError(f"Missing patch_id={patch_id!r} in {path}")


def _load_jsonl_record(path: Path, line_index: int) -> dict[str, object]:
    if line_index < 0:
        raise KeyError(f"Invalid JSONL line_index={line_index}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if line_index >= len(lines):
        raise KeyError(f"Missing JSONL line_index={line_index} in {path}")
    record = json.loads(lines[line_index])
    if not isinstance(record, dict):
        raise ValueError(f"Expected JSON object at {path}:{line_index}")
    return record


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


def _tokenize(query: str) -> list[str]:
    tokens = re.findall(r"[\w가-힣.-]+", query.lower())
    return [token for token in tokens if len(token) > 1]


def _score_text(text: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    for term in terms:
        count = lower.count(term)
        if count:
            score += 1.0 + min(count - 1, 3) * 0.25
    if terms and all(term in lower for term in terms):
        score += 2.0
    return score


def _make_snippet(text: str, terms: list[str], radius: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    lower = compact.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    if not positions:
        return compact[: radius * 2]
    center = min(positions)
    start = max(0, center - radius)
    end = min(len(compact), center + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def _extract_markdown_title(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _format_pointer(pointer: RawSessionReference | None) -> str:
    if pointer is None:
        return ""
    message_ids = ",".join(str(message_id) for message_id in pointer.message_ids)
    return f"hermes-session:{pointer.session_id}#messages={message_ids}"


def _source_rank(source_type: str) -> int:
    return {
        "wiki": 0,
        "packet": 1,
        "unit_summary": 2,
        "micro_summary": 3,
        "topic_map_node": 4,
        "topic_map_edge": 5,
        "topic_map_path": 6,
        "promotion_candidate": 7,
        "wiki_patch": 8,
        "applied_patch": 9,
        "raw_message": 10,
    }.get(source_type, 99)


def _encode_hit_id(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_hit_id(hit_id: str) -> dict[str, Any]:
    padding = "=" * (-len(hit_id) % 4)
    raw = base64.urlsafe_b64decode((hit_id + padding).encode("ascii"))
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid retrieval hit id")
    return payload


def _hit_from_payload(payload: dict[str, Any], *, content: str) -> RetrievalHit:
    return RetrievalHit(
        hit_id=_encode_hit_id(payload),
        source_type=str(payload["source_type"]),
        source_path=str(payload.get("source_path", "")),
        title=str(payload.get("title", "")),
        snippet=content[:240],
        score=0.0,
        provenance=[str(item) for item in payload.get("provenance", []) if item],
    )


_PROJECT_SOURCE_PREFIXES = {
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
    if not _is_searchable_wiki_path(resolved, wiki_root.resolve()):
        raise ValueError(f"Unsafe wiki path: {value!r}")
    return resolved


def _resolve_project_path(project_root: Path, value: str, *, source_type: str) -> Path:
    path = Path(value)
    allowed_prefix = _PROJECT_SOURCE_PREFIXES.get(source_type)
    if allowed_prefix is None:
        raise ValueError(f"Unsupported project source_type: {source_type!r}")
    if tuple(path.parts[: len(allowed_prefix)]) != allowed_prefix:
        raise ValueError(f"Unsafe project path for {source_type}: {value!r}")
    return _resolve_child_path(project_root, value, "project")


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
