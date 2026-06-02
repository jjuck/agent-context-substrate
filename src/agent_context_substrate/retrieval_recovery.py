from __future__ import annotations

from pathlib import Path

from .models import ContextPacket
from .retrieval_ids import encode_hit_id
from .retrieval_scoring import make_snippet, score_text
from .retrieval_sources import load_context_packet, load_json_object
from .retrieval_types import RetrievalHit
from .safe_paths import is_safe_project_artifact_path


_RECOVERY_BRIEF_PREFIX = ("data", "exports", "recovery")
_RECOVERY_PACKET_PREFIX = ("data", "exports", "context_packets")


def search_recovery_briefs(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    recovery_dir = project_root / "data" / "exports" / "recovery"
    if not recovery_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(recovery_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_RECOVERY_BRIEF_PREFIX):
            continue
        payload = load_json_object(path)
        if payload is None:
            continue
        content = recovery_brief_search_text(payload)
        score = score_text(content, terms)
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
                snippet=make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits


def search_recovery_packets(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    packet_dir = project_root / "data" / "exports" / "context_packets"
    if not packet_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(packet_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_RECOVERY_PACKET_PREFIX):
            continue
        packet = load_context_packet(path)
        if packet is None:
            continue
        content = packet_recovery_search_text(packet)
        score = score_text(content, terms)
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
                snippet=make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits


def recovery_brief_search_text(payload: dict[str, object]) -> str:
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


def packet_recovery_search_text(packet: ContextPacket) -> str:
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


def _format_pointer(pointer: object) -> str:
    if pointer is None:
        return ""
    source_ref = getattr(pointer, "source_ref", None)
    if callable(source_ref):
        return str(source_ref())
    session_id = getattr(pointer, "session_id")
    message_ids = ",".join(str(message_id) for message_id in getattr(pointer, "message_ids"))
    return f"hermes-session:{session_id}#messages={message_ids}"
