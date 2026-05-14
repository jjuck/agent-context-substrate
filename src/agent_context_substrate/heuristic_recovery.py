from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .heuristic_composition import compose_recovery_summary
from .heuristic_metadata import (
    _dedupe_preserve_order,
    _select_messages_by_role,
    _select_raw_messages_by_role,
    _select_salient_messages,
    _strip_markdown,
    _truncate_text,
)

_SECTION_STOP_MARKERS = ("evidence", "proof", "원하면", "next step", "next steps")


@dataclass(frozen=True)
class HeuristicRecoveryFields:
    request: str | None
    outcome: str | None
    key_points: list[str]
    follow_up_questions: list[str]
    recovery_summary: str


def extract_recovery_fields(messages: list[dict[str, Any]]) -> HeuristicRecoveryFields:
    """Extract request/outcome/key-point fields used by recovery summaries."""

    message_list = list(messages)
    follow_up_questions = _extract_follow_up_questions(message_list)
    request = _extract_request(message_list, follow_up_questions)
    outcome = _extract_outcome(message_list)
    key_points = _extract_key_points(message_list)
    recovery_summary = compose_recovery_summary(
        messages=message_list,
        request=request,
        outcome=outcome,
        key_points=key_points,
        follow_up_questions=follow_up_questions,
    )
    return HeuristicRecoveryFields(
        request=request,
        outcome=outcome,
        key_points=key_points,
        follow_up_questions=follow_up_questions,
        recovery_summary=recovery_summary,
    )


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
