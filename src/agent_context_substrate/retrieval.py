from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3

from .models import ContextPacket, MicroSummary, RawSessionReference, UnitSummary
from .paths import HarnessPaths
from .retrieval_graph import (
    find_topic_map_edge as _find_topic_map_edge,
    find_topic_map_node as _find_topic_map_node,
    search_topic_map as _search_topic_map,
)
from .retrieval_ids import decode_hit_id, encode_hit_id
from .retrieval_recovery import (
    search_recovery_briefs as _search_recovery_briefs,
    search_recovery_packets as _search_recovery_packets,
)
from .retrieval_proposals import (
    search_promotions as _search_promotions,
    search_wiki_patches as _search_wiki_patches,
)
from .retrieval_scoring import (
    make_snippet as _make_snippet,
    rank_hits,
    score_text as _score_text,
    tokenize_query as _tokenize,
)
from .retrieval_sources import (
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
