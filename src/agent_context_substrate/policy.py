from __future__ import annotations

import re


def should_process_bundle(
    raw_bundle: dict,
    *,
    min_message_count: int,
    allowed_sources: list[str] | None = None,
    skip_title_patterns: list[str] | None = None,
) -> bool:
    session = raw_bundle.get("session", {})
    messages = list(raw_bundle.get("messages", []))

    if len(messages) < min_message_count:
        return False

    source = str(session.get("source") or "")
    if allowed_sources is not None and source not in set(allowed_sources):
        return False

    title = str(session.get("title") or "").strip()
    for pattern in skip_title_patterns or []:
        if re.search(pattern, title):
            return False

    return True
