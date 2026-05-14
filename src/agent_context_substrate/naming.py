from __future__ import annotations

import re
from typing import Any, Mapping

from .models import MicroSummary
from .session_bundle import SessionBundle, resolve_session_bundle


def derive_task_title(
    raw_bundle: Mapping[str, Any] | SessionBundle | None = None,
    session_id: str | None = None,
    *,
    session_bundle: Mapping[str, Any] | SessionBundle | None = None,
) -> str:
    if session_id is None:
        raise TypeError("session_id is required")
    bundle = resolve_session_bundle(raw_bundle, session_bundle=session_bundle)
    title = str(bundle.title or "").strip()
    if title:
        return title

    for message in bundle.messages:
        if message.role != "user":
            continue
        content = message.content.strip()
        if content:
            return content[:120]

    return f"Resume session {session_id}"


def derive_unit_title(
    raw_bundle: Mapping[str, Any] | SessionBundle | None = None,
    task_title: str | None = None,
    *,
    session_bundle: Mapping[str, Any] | SessionBundle | None = None,
) -> str:
    if task_title is None:
        raise TypeError("task_title is required")
    bundle = resolve_session_bundle(raw_bundle, session_bundle=session_bundle)
    for message in bundle.messages:
        if message.role != "user":
            continue
        content = message.content.strip()
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
