from __future__ import annotations

import re

from .models import MicroSummary


def derive_task_title(raw_bundle: dict, session_id: str) -> str:
    session = raw_bundle.get("session", {})
    title = str(session.get("title") or "").strip()
    if title:
        return title

    for message in raw_bundle.get("messages", []):
        if str(message.get("role") or "") != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content[:120]

    return f"Resume session {session_id}"


def derive_unit_title(raw_bundle: dict, task_title: str) -> str:
    for message in raw_bundle.get("messages", []):
        if str(message.get("role") or "") != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content[:120]
    return task_title


def derive_goal(task_title: str, micro_summary: MicroSummary | None = None) -> str:
    if micro_summary is not None:
        if micro_summary.request:
            return f"Capture the main facts, artifacts, and next steps for: {micro_summary.request}"
        if micro_summary.outcome:
            return f"Preserve the completed outcome and follow-up context for {task_title}: {micro_summary.outcome}"
    return f"Capture the main facts, artifacts, and next steps for {task_title}."


def slugify_label(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "artifact"
