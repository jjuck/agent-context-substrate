from __future__ import annotations

from pathlib import Path

from .models import ContextPacket, MicroSummary, RawSessionReference, UnitSummary
from .retrieval_ids import encode_hit_id
from .retrieval_scoring import make_snippet, score_text
from .retrieval_sources import load_context_packet
from .retrieval_types import RetrievalHit
from .safe_paths import is_safe_project_artifact_path


_PACKET_PREFIX = ("data", "exports", "context_packets")


def search_packets(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    packet_dir = project_root / "data" / "exports" / "context_packets"
    if not packet_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(packet_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PACKET_PREFIX):
            continue
        packet = load_context_packet(path)
        if packet is None:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        packet_text = packet_search_text(packet)
        packet_score = score_text(packet_text, terms)
        if packet_score > 0:
            provenance = [format_pointer(pointer) for pointer in packet.raw_pointers]
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
                    snippet=make_snippet(packet_text, terms),
                    score=packet_score,
                    provenance=provenance,
                )
            )
        for unit in packet.unit_summaries:
            hits.extend(summary_hit_if_match(terms, rel_path, packet, unit))
        for micro in packet.micro_summaries:
            hits.extend(summary_hit_if_match(terms, rel_path, packet, micro))
    return hits


def summary_hit_if_match(
    terms: list[str],
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
        provenance = [format_pointer(summary.provenance)] if summary.provenance else []
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
        provenance = [format_pointer(summary.provenance)] if summary.provenance else []

    score = score_text(content, terms)
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
            snippet=make_snippet(content, terms),
            score=score,
            provenance=provenance,
        )
    ]


def packet_search_text(packet: ContextPacket) -> str:
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


def format_pointer(pointer: RawSessionReference | None) -> str:
    if pointer is None:
        return ""
    return pointer.source_ref()
