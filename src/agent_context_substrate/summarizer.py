from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .heuristic_extraction import analyze_heuristic_messages
from .models import (
    EvidenceBackedText,
    MicroSummary,
    MicroSummaryV2,
    RawSessionReference,
    SummaryMetadata,
    UnitSummary,
    UnitSummaryV2,
)
from .session_bundle import SessionBundle, SessionMessage, resolve_session_bundle

def _raw_message_payloads(messages: list[SessionMessage]) -> list[dict[str, Any]]:
    return [message.to_dict() for message in messages]


def _session_bundle_payload(bundle: SessionBundle) -> dict[str, Any]:
    session: dict[str, Any] = {
        "id": bundle.session_id,
        "source": bundle.source,
        **dict(bundle.metadata),
    }
    if bundle.title is not None:
        session["title"] = bundle.title
    if bundle.started_at is not None:
        session["started_at"] = bundle.started_at
    if bundle.ended_at is not None:
        session["ended_at"] = bundle.ended_at
    return {
        "session": session,
        "messages": _raw_message_payloads(list(bundle.messages)),
        "slice": {
            "start_message_id": bundle.slice_start_message_id,
            "end_message_id": bundle.slice_end_message_id,
        },
        "message_count": len(bundle.messages),
    }


def _normalize_text(text: str) -> str:
    return " ".join(str(text).split()).strip()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _format_file_list(files: list[str], max_items: int = 3) -> str:
    if not files:
        return ""
    preview = files[:max_items]
    suffix = f" (+{len(files) - max_items} more)" if len(files) > max_items else ""
    return ", ".join(preview) + suffix


def _build_why_it_matters(
    *,
    title: str,
    message_ids: list[int],
    files: list[str],
    concepts: list[str],
    entities: list[str],
) -> str:
    if files:
        return (
            f"Preserves the key artifact context from {title}: "
            f"{_format_file_list(files)}."
        )
    if concepts:
        return (
            f"Preserves the main conceptual thread from {title}: "
            f"{', '.join(concepts[:3])}."
        )
    if entities:
        return (
            f"Preserves the entity-focused discussion from {title}: "
            f"{', '.join(entities[:3])}."
        )
    return (
        f"Preserves {len(message_ids)} conversational messages from {title} "
        f"for later retrieval."
    )

def build_micro_summary(
    raw_bundle: dict[str, Any] | SessionBundle | None = None,
    micro_id: str | None = None,
    parent_unit_id: str | None = None,
    *,
    session_bundle: dict[str, Any] | SessionBundle | None = None,
) -> MicroSummary:
    if micro_id is None:
        raise TypeError("micro_id is required")
    raw_bundle = _session_bundle_payload(resolve_session_bundle(raw_bundle, session_bundle=session_bundle))
    session = raw_bundle["session"]
    messages = list(raw_bundle.get("messages", []))
    analysis = analyze_heuristic_messages(messages)
    message_ids = [int(message["id"]) for message in messages]
    files = list(analysis.files)
    entities = list(analysis.entities)
    concepts = list(analysis.concepts)
    follow_up_questions = list(analysis.follow_up_questions)
    request = analysis.request
    outcome = analysis.outcome
    key_points = list(analysis.key_points)

    summary_text = analysis.recovery_summary
    if not summary_text:
        summary_text = f"Session slice from {session.get('id', 'unknown-session')}"

    title = session.get("title") or session.get("id") or "unknown session"
    why_it_matters = _build_why_it_matters(
        title=title,
        message_ids=message_ids,
        files=files,
        concepts=concepts,
        entities=entities,
    )

    provenance = RawSessionReference(
        session_id=session["id"],
        message_ids=message_ids,
        source=str(session.get("source") or "unknown"),
        started_at=(str(session.get("started_at")) if session.get("started_at") is not None else None),
        ended_at=(str(session.get("ended_at")) if session.get("ended_at") is not None else None),
        title=session.get("title"),
    )

    return MicroSummary(
        micro_id=micro_id,
        session_id=session["id"],
        message_ids=message_ids,
        summary=summary_text,
        why_it_matters=why_it_matters,
        request=request,
        outcome=outcome,
        key_points=key_points,
        follow_up_questions=follow_up_questions,
        artifacts=list(files),
        files=files,
        entities=entities,
        concepts=concepts,
        parent_unit_id=parent_unit_id,
        provenance=provenance,
    )


def build_unit_summary(
    unit_id: str,
    session_id: str,
    title: str,
    goal: str,
    micro_summaries: list[MicroSummary],
    related_pages: list[str] | None = None,
) -> UnitSummary:
    decisions = _dedupe_preserve_order(
        [
            point
            for summary in micro_summaries
            for point in summary.key_points
        ]
    )
    progress = [
        summary.outcome or summary.summary
        for summary in micro_summaries
        if (summary.outcome or summary.summary)
    ]
    open_questions = _dedupe_preserve_order(
        [
            question
            for summary in micro_summaries
            for question in summary.follow_up_questions
        ]
    )
    return UnitSummary(
        unit_id=unit_id,
        session_id=session_id,
        title=title,
        goal=goal,
        decisions=decisions,
        progress=progress,
        open_questions=open_questions,
        micro_ids=[summary.micro_id for summary in micro_summaries],
        related_pages=list(related_pages or []),
        provenance=(micro_summaries[0].provenance if micro_summaries else None),
    )


def _summary_input_hash(payload: dict[str, Any], *, schema_version: str, mode: str) -> str:
    raw = json.dumps(
        {"payload": payload, "schema_version": schema_version, "mode": mode},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _summary_metadata(*, payload: dict[str, Any], schema_version: str, mode: str = "heuristic", confidence: float | None = None) -> SummaryMetadata:
    return SummaryMetadata(
        mode=mode,
        schema_version=schema_version,
        prompt_version=None,
        model=None,
        input_hash=_summary_input_hash(payload, schema_version=schema_version, mode=mode),
        created_at=datetime.now(timezone.utc).isoformat(),
        confidence=confidence,
    )


def _evidence_items_from_points(points: list[str], message_ids: list[int], *, confidence: float = 0.6) -> list[EvidenceBackedText]:
    return [
        EvidenceBackedText(
            text=point,
            evidence_message_ids=list(message_ids),
            confidence=confidence,
        )
        for point in points
    ]


def _retrieval_summary(*, summary: MicroSummary) -> str:
    pieces = [
        summary.request or "",
        summary.outcome or "",
        *summary.key_points,
        *summary.files,
        *summary.entities,
        *summary.concepts,
    ]
    return " ".join(piece for piece in _dedupe_preserve_order(pieces) if piece)


def _knowledge_summary(*, summary: MicroSummary) -> str:
    if summary.key_points:
        return "; ".join(summary.key_points)
    return summary.outcome or summary.summary


def build_micro_summary_v2(
    raw_bundle: dict[str, Any] | SessionBundle | None = None,
    micro_id: str | None = None,
    parent_unit_id: str | None = None,
    *,
    session_bundle: dict[str, Any] | SessionBundle | None = None,
) -> MicroSummaryV2:
    if micro_id is None:
        raise TypeError("micro_id is required")
    raw_bundle = _session_bundle_payload(resolve_session_bundle(raw_bundle, session_bundle=session_bundle))
    legacy_summary = build_micro_summary(
        raw_bundle=raw_bundle,
        micro_id=micro_id,
        parent_unit_id=parent_unit_id,
    )
    decisions = _evidence_items_from_points(
        legacy_summary.key_points,
        legacy_summary.message_ids,
    )
    claims = _evidence_items_from_points(
        legacy_summary.key_points,
        legacy_summary.message_ids,
        confidence=0.5,
    )
    return MicroSummaryV2(
        micro_id=legacy_summary.micro_id,
        session_id=legacy_summary.session_id,
        message_ids=list(legacy_summary.message_ids),
        recovery_summary=legacy_summary.summary,
        knowledge_summary=_knowledge_summary(summary=legacy_summary),
        retrieval_summary=_retrieval_summary(summary=legacy_summary),
        user_intent=legacy_summary.request,
        assistant_outcome=legacy_summary.outcome,
        decisions=decisions,
        claims=claims,
        action_items=[],
        open_questions=list(legacy_summary.follow_up_questions),
        files=list(legacy_summary.files),
        entities=list(legacy_summary.entities),
        concepts=list(legacy_summary.concepts),
        metadata=_summary_metadata(
            payload=raw_bundle,
            schema_version="micro_summary_v2",
            confidence=0.6,
        ),
        provenance=legacy_summary.provenance,
    )


def build_unit_summary_v2(
    unit_id: str,
    session_id: str,
    title: str,
    goal: str,
    micro_summaries: list[MicroSummaryV2],
    related_pages: list[str] | None = None,
) -> UnitSummaryV2:
    decisions = _dedupe_evidence_texts(
        [item for summary in micro_summaries for item in summary.decisions]
    )
    open_questions = _dedupe_preserve_order(
        [question for summary in micro_summaries for question in summary.open_questions]
    )
    progress = [
        summary.assistant_outcome or summary.recovery_summary
        for summary in micro_summaries
        if (summary.assistant_outcome or summary.recovery_summary)
    ]
    wiki_candidates = _dedupe_evidence_texts(
        [item for summary in micro_summaries for item in summary.claims]
    )
    payload = {
        "unit_id": unit_id,
        "session_id": session_id,
        "title": title,
        "goal": goal,
        "micro_summaries": [summary.to_dict() for summary in micro_summaries],
    }
    return UnitSummaryV2(
        unit_id=unit_id,
        session_id=session_id,
        title=title,
        goal=goal,
        state="in_progress" if open_questions else "completed",
        decisions=decisions,
        progress=progress,
        next_actions=[
            item.text for summary in micro_summaries for item in summary.action_items
        ],
        open_questions=open_questions,
        risk_notes=[],
        wiki_candidates=wiki_candidates,
        micro_ids=[summary.micro_id for summary in micro_summaries],
        related_pages=list(related_pages or []),
        metadata=_summary_metadata(
            payload=payload,
            schema_version="unit_summary_v2",
            confidence=0.6,
        ),
        provenance=(micro_summaries[0].provenance if micro_summaries else None),
    )


def _dedupe_evidence_texts(items: list[EvidenceBackedText]) -> list[EvidenceBackedText]:
    seen: set[str] = set()
    deduped: list[EvidenceBackedText] = []
    for item in items:
        if item.text in seen:
            continue
        seen.add(item.text)
        deduped.append(item)
    return deduped
