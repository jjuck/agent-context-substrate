from __future__ import annotations

import re
from typing import Any, Mapping

from .session_bundle import SessionBundle, resolve_session_bundle


def should_process_bundle(
    raw_bundle: Mapping[str, Any] | SessionBundle | None = None,
    *,
    min_message_count: int,
    allowed_sources: list[str] | None = None,
    skip_title_patterns: list[str] | None = None,
    session_bundle: Mapping[str, Any] | SessionBundle | None = None,
) -> bool:
    bundle = resolve_session_bundle(raw_bundle, session_bundle=session_bundle)

    if len(bundle.messages) < min_message_count:
        return False

    source = bundle.source
    if allowed_sources is not None and source not in set(allowed_sources):
        return False

    title = str(bundle.title or "").strip()
    for pattern in skip_title_patterns or []:
        if re.search(pattern, title):
            return False

    return True
