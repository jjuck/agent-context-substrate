"""Formatting helpers for durable wiki recovery context."""

from __future__ import annotations

from typing import Any, Dict, List

RECOVERY_MARKER = "Durable wiki recovery context"


def already_injected(messages: List[Dict[str, Any]]) -> bool:
    return any(
        message.get("role") == "system"
        and RECOVERY_MARKER in str(message.get("content", ""))
        for message in messages
    )


def format_recovery_context(brief: dict[str, Any]) -> str:
    lines = [
        f"# {RECOVERY_MARKER}",
        "Use this durable wiki/context-packet recovery brief before replaying raw history.",
        f"Session: {brief.get('session_id', '')}",
        f"Packet: {brief.get('packet_id', '')}",
        f"Task: {brief.get('task_title', '')}",
        f"Macro context: {brief.get('macro_context', '')}",
    ]
    _append_list(lines, "Decisions", brief.get("decisions", []))
    _append_list(lines, "Critical files", brief.get("critical_files", []))
    _append_list(lines, "Open questions", brief.get("open_questions", []))
    _append_list(lines, "Related wiki pages", brief.get("related_pages", []))
    _append_list(lines, "Provenance", brief.get("provenance", []))
    return "\n".join(line for line in lines if line != "")


def _append_list(lines: list[str], title: str, values: Any) -> None:
    if not isinstance(values, list) or not values:
        return
    lines.append(f"{title}:")
    for value in values[:8]:
        lines.append(f"- {value}")
