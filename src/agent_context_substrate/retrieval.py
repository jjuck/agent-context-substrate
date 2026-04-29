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
) -> list[RetrievalHit]:
    """Search durable wiki, packet artifacts, summaries, and optionally raw messages.

    This is intentionally vectorless for the MVP: it provides deterministic,
    read-only retrieval with provenance so Hermes can use it as a RAG-like
    fallback while performing user requests.
    """
    project_root = Path(project_root)
    wiki_root = Path(wiki_root)
    terms = _tokenize(query)
    if not terms:
        return []

    hits: list[RetrievalHit] = []
    hits.extend(_search_wiki(terms, wiki_root))
    hits.extend(_search_packets(terms, project_root))
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
        path = wiki_root / source_path
        content = path.read_text(encoding="utf-8")
        hit = _hit_from_payload(payload, content=_make_snippet(content, _tokenize(content)[:1]))
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={"source_type": source_type, "source_path": source_path},
        )

    if source_type in {"packet", "unit_summary", "micro_summary"}:
        path = _resolve_project_path(project_root, source_path)
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

    if source_type == "raw_message":
        content = _load_raw_message_content(project_root, str(payload["session_id"]), int(payload["message_id"]))
        hit = _hit_from_payload(payload, content=content)
        return RetrievalHitDetail(
            hit=hit,
            content=content,
            metadata={
                "source_type": source_type,
                "session_id": payload["session_id"],
                "message_id": payload["message_id"],
            },
        )

    raise ValueError(f"Unknown retrieval hit source_type={source_type!r}")


def _is_searchable_wiki_path(path: Path, wiki_root: Path) -> bool:
    relative_parts = path.relative_to(wiki_root).parts
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


def _load_raw_message_content(project_root: Path, session_id: str, message_id: int) -> str:
    paths = HarnessPaths(project_root=project_root)
    with sqlite3.connect(paths.state_db_path) as connection:
        row = connection.execute(
            "SELECT content FROM messages WHERE session_id = ? AND id = ?",
            (session_id, message_id),
        ).fetchone()
    if row is None:
        raise KeyError(f"Unknown raw message: {session_id}#{message_id}")
    return str(row[0] or "")


def _load_packet(path: Path) -> ContextPacket | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ContextPacket.from_dict(payload)
    except Exception:
        return None


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
        "raw_message": 4,
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


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path
