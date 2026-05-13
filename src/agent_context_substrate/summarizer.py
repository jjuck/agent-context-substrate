from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from .models import (
    EvidenceBackedText,
    MicroSummary,
    MicroSummaryV2,
    RawSessionReference,
    SummaryMetadata,
    UnitSummary,
    UnitSummaryV2,
)
from .session_bundle import SessionBundle, SessionMessage, ensure_session_bundle

_FILE_PATTERN = re.compile(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+")
_ALLOWED_FILE_EXTENSIONS = {
    "bash",
    "bat",
    "cfg",
    "conf",
    "css",
    "csv",
    "db",
    "env",
    "html",
    "ini",
    "ipynb",
    "java",
    "js",
    "json",
    "jsx",
    "lock",
    "log",
    "md",
    "pdf",
    "ps1",
    "py",
    "rst",
    "sh",
    "sql",
    "tar",
    "tgz",
    "toml",
    "ts",
    "tsx",
    "txt",
    "xml",
    "yaml",
    "yml",
    "zip",
    "gz",
}
_ALLOWED_SPECIAL_FILENAMES = {
    ".env",
    ".gitignore",
    ".gitattributes",
    "dockerfile",
    "justfile",
    "makefile",
}
_CONVERSATION_ROLES = {"user", "assistant"}
_SECTION_STOP_MARKERS = ("evidence", "proof", "원하면", "next step", "next steps")


def _collect_text(messages: list[dict[str, Any]]) -> str:
    return " ".join(str(message.get("content") or "").strip() for message in messages).strip()


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
    return re.sub(r"\s+", " ", text).strip()


def _truncate_text(text: str, limit: int = 140) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    cutoff = normalized[: limit - 3].rstrip()
    return f"{cutoff}..."


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"`([^`]*)`", r"\1", text)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    return _normalize_text(cleaned)


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


def _message_content(message: dict[str, Any]) -> str:
    return _normalize_text(str(message.get("content") or ""))


def _raw_message_content(message: dict[str, Any]) -> str:
    return str(message.get("content") or "").strip()


def _select_messages_by_role(messages: list[dict[str, Any]], role: str) -> list[str]:
    selected: list[str] = []
    for message in messages:
        if str(message.get("role") or "") != role:
            continue
        content = _message_content(message)
        if content:
            selected.append(content)
    return selected


def _select_raw_messages_by_role(messages: list[dict[str, Any]], role: str) -> list[str]:
    selected: list[str] = []
    for message in messages:
        if str(message.get("role") or "") != role:
            continue
        content = _raw_message_content(message)
        if content:
            selected.append(content)
    return selected


def _select_salient_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    salient: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = _message_content(message)
        if role not in _CONVERSATION_ROLES:
            continue
        if not content:
            continue
        salient.append({"role": role, "content": content})
    return salient


def _extract_request(messages: list[dict[str, Any]], follow_up_questions: list[str] | None = None) -> str | None:
    user_messages = _select_messages_by_role(messages, "user")
    if not user_messages:
        return None
    trailing_questions = set(follow_up_questions or [])
    request_messages = [message for message in user_messages if message not in trailing_questions]
    if not request_messages:
        request_messages = user_messages
    return _truncate_text(" Then: ".join(request_messages[:2]), limit=220)


def _split_message_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()]


def _is_list_line(text: str) -> bool:
    return bool(re.match(r"^(?:[-*]|\d+[.)])\s+", text))


def _normalize_list_line(text: str) -> str:
    stripped = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", text).strip()
    return _strip_markdown(stripped)


def _should_stop_key_point_collection(text: str) -> bool:
    lowered = _strip_markdown(text).lower().rstrip(":")
    return any(lowered.startswith(marker) for marker in _SECTION_STOP_MARKERS)


def _extract_outcome(messages: list[dict[str, Any]]) -> str | None:
    assistant_messages = _select_raw_messages_by_role(messages, "assistant")
    for content in reversed(assistant_messages):
        for line in _split_message_lines(content):
            if _is_list_line(line):
                continue
            cleaned = _strip_markdown(line).rstrip(":")
            if cleaned:
                return _truncate_text(cleaned, limit=220)
        cleaned_content = _strip_markdown(content)
        if cleaned_content:
            return _truncate_text(cleaned_content, limit=220)
    return None


def _should_skip_key_point(text: str) -> bool:
    lowered = _strip_markdown(text).lower()
    return lowered.startswith(("즉,", "so ", "meaning "))


def _extract_key_points(messages: list[dict[str, Any]], limit: int = 4) -> list[str]:
    assistant_messages = _select_raw_messages_by_role(messages, "assistant")
    points: list[str] = []
    for content in assistant_messages:
        for line in _split_message_lines(content):
            if _should_stop_key_point_collection(line):
                return _dedupe_preserve_order(points)[:limit]
            if not _is_list_line(line):
                continue
            normalized = _normalize_list_line(line)
            if not normalized or _should_skip_key_point(normalized):
                continue
            points.append(_truncate_text(normalized, limit=160))
    return _dedupe_preserve_order(points)[:limit]


def _extract_follow_up_questions(messages: list[dict[str, Any]]) -> list[str]:
    salient_messages = _select_salient_messages(messages)
    if not salient_messages:
        return []
    last_message = salient_messages[-1]
    if last_message["role"] != "user":
        return []
    question = _truncate_text(last_message["content"], limit=220)
    if not question:
        return []
    if "?" not in question and "？" not in question:
        return []
    return [question]


def _format_file_list(files: list[str], max_items: int = 3) -> str:
    if not files:
        return ""
    preview = files[:max_items]
    suffix = f" (+{len(files) - max_items} more)" if len(files) > max_items else ""
    return ", ".join(preview) + suffix


def _build_summary_text(
    *,
    messages: list[dict[str, Any]],
    request: str | None,
    outcome: str | None,
    key_points: list[str],
    follow_up_questions: list[str],
) -> str:
    parts: list[str] = []
    if request:
        parts.append(f"Request: {request}")
    if outcome:
        parts.append(f"Outcome: {outcome}")
    if key_points:
        parts.append(f"Key points: {'; '.join(key_points[:3])}")
    if follow_up_questions:
        parts.append(f"Open question: {follow_up_questions[0]}")
    if parts:
        return " ".join(parts)

    fallback_text = _collect_text(messages)
    if fallback_text:
        return _truncate_text(fallback_text)
    return ""


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


def _clean_file_candidate(candidate: str) -> str:
    return candidate.strip().strip("`'\"([{<").rstrip("`'\".,:;!?)]}>")


def _is_probable_file_candidate(candidate: str) -> bool:
    basename = candidate.replace("\\", "/").rsplit("/", 1)[-1]
    lowered = basename.lower()
    if lowered in _ALLOWED_SPECIAL_FILENAMES:
        return True
    if "." not in basename:
        return False
    extension = basename.rsplit(".", 1)[-1]
    if extension != extension.lower():
        return False
    return extension in _ALLOWED_FILE_EXTENSIONS


def _extract_files(text: str) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    for match in _FILE_PATTERN.findall(text):
        cleaned = _clean_file_candidate(match)
        if not cleaned:
            continue
        if not re.search(r"[A-Za-z_]", cleaned):
            continue
        if not _is_probable_file_candidate(cleaned):
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            files.append(cleaned)
    return files


def _extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    if "Hermes" in text:
        entities.append("Hermes")
    return entities


def _extract_concepts(text: str) -> list[str]:
    concepts: list[str] = []
    lower = text.lower()
    if "context packet" in lower or "context-packet" in lower:
        concepts.append("context-packet")
    if "summarization" in lower:
        concepts.append("summarization")
    return concepts


def build_micro_summary(
    raw_bundle: dict[str, Any] | SessionBundle,
    micro_id: str,
    parent_unit_id: str | None = None,
) -> MicroSummary:
    raw_bundle = _session_bundle_payload(ensure_session_bundle(raw_bundle))
    session = raw_bundle["session"]
    messages = list(raw_bundle.get("messages", []))
    salient_messages = _select_salient_messages(messages)
    text_source = salient_messages if salient_messages else messages
    text = _collect_text(text_source)
    message_ids = [int(message["id"]) for message in messages]
    files = _extract_files(text)
    entities = _extract_entities(text)
    concepts = _extract_concepts(text)
    follow_up_questions = _extract_follow_up_questions(messages)
    request = _extract_request(messages, follow_up_questions)
    outcome = _extract_outcome(messages)
    key_points = _extract_key_points(messages)

    summary_text = _build_summary_text(
        messages=messages,
        request=request,
        outcome=outcome,
        key_points=key_points,
        follow_up_questions=follow_up_questions,
    )
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
    raw_bundle: dict[str, Any] | SessionBundle,
    micro_id: str,
    parent_unit_id: str | None = None,
) -> MicroSummaryV2:
    raw_bundle = _session_bundle_payload(ensure_session_bundle(raw_bundle))
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
