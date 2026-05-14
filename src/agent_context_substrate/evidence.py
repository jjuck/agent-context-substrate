from __future__ import annotations

import json
from pathlib import Path
import re

from .safe_paths import safe_artifact_stem, safe_child_path
from typing import Any

from .heuristic_metadata import _extract_files
from .heuristic_recovery import (
    _extract_follow_up_questions,
    _extract_key_points,
    _extract_outcome,
    _extract_request,
)
from .models import EvidenceMessage, MicroEvidenceBundle
from .session_bundle import SessionBundle, SessionMessage, resolve_session_bundle

_CONVERSATION_ROLES = {"user", "assistant"}
_CODE_BLOCK_PATTERN = re.compile(r"```(.*?)```", re.DOTALL)
_URL_PATTERN = re.compile(r"https?://[^\s)\]>}]+")
_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _message_content(message: SessionMessage) -> str:
    return str(message.content or "").strip()


def _conversation_messages(messages: list[SessionMessage]) -> list[SessionMessage]:
    return [
        message
        for message in messages
        if str(message.role or "") in _CONVERSATION_ROLES
        and _message_content(message)
    ]


def _evidence_messages(messages: list[SessionMessage], role: str) -> list[EvidenceMessage]:
    return [
        EvidenceMessage(
            message_id=int(message.id),
            role=str(message.role or ""),
            content=_message_content(message),
        )
        for message in messages
        if str(message.role or "") == role and _message_content(message)
    ]


def _collect_text(messages: list[SessionMessage]) -> str:
    return "\n".join(_message_content(message) for message in messages if _message_content(message))


def _raw_message_payloads(messages: list[SessionMessage]) -> list[dict[str, Any]]:
    return [message.to_dict() for message in messages]


def _extract_code_blocks(text: str) -> list[str]:
    return [match.strip() for match in _CODE_BLOCK_PATTERN.findall(text) if match.strip()]


def _extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_PATTERN.findall(text):
        url = match.rstrip(".,")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _extract_headings(text: str) -> list[str]:
    return [match.strip() for match in _HEADING_PATTERN.findall(text) if match.strip()]


def _strip_heading_marker(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(r"^#{1,6}\s+", "", text).strip()


def _extract_explicit_questions(text: str) -> list[str]:
    questions: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.endswith(("?", "？")):
            continue
        if stripped not in seen:
            seen.add(stripped)
            questions.append(stripped)
    return questions


def build_micro_evidence_bundle(
    raw_bundle: dict[str, Any] | SessionBundle | None = None,
    micro_id: str | None = None,
    *,
    session_bundle: dict[str, Any] | SessionBundle | None = None,
) -> MicroEvidenceBundle:
    if micro_id is None:
        raise TypeError("micro_id is required")
    typed_bundle = resolve_session_bundle(raw_bundle, session_bundle=session_bundle)
    messages = list(typed_bundle.messages)
    raw_messages = _raw_message_payloads(messages)
    conversation_messages = _conversation_messages(messages)
    text_source = conversation_messages if conversation_messages else messages
    text = _collect_text(text_source)
    follow_up_questions = _extract_follow_up_questions(raw_messages)

    return MicroEvidenceBundle(
        session_id=typed_bundle.session_id,
        micro_id=micro_id,
        message_ids=[int(message.id) for message in messages],
        user_messages=_evidence_messages(messages, "user"),
        assistant_messages=_evidence_messages(messages, "assistant"),
        heuristic_request=_extract_request(raw_messages, follow_up_questions),
        heuristic_outcome=_strip_heading_marker(_extract_outcome(raw_messages)),
        heuristic_key_points=_extract_key_points(raw_messages),
        files=_extract_files(text),
        code_blocks=_extract_code_blocks(text),
        urls=_extract_urls(text),
        headings=_extract_headings(text),
        explicit_questions=_extract_explicit_questions(text),
    )


def export_micro_evidence_bundle(*, bundle: MicroEvidenceBundle, exports_dir: Path) -> Path:
    evidence_dir = Path(exports_dir) / "evidence" / safe_artifact_stem(bundle.session_id, label="session id")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    export_path = safe_child_path(evidence_dir, bundle.micro_id, ".json", label="micro id")
    export_path.write_text(
        json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return export_path
