from __future__ import annotations

from typing import Any

from .heuristic_metadata import _collect_text, _truncate_text


def compose_recovery_summary(
    *,
    messages: list[dict[str, Any]],
    request: str | None,
    outcome: str | None,
    key_points: list[str],
    follow_up_questions: list[str],
) -> str:
    """Compose the recovery-oriented summary from extracted heuristic fields."""

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
