from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import HarnessPaths
from .session_store import SessionStore


def build_session_bundle(
    session_id: str,
    paths: HarnessPaths,
    start_message_id: int | None = None,
    end_message_id: int | None = None,
) -> dict[str, Any]:
    store = SessionStore(paths.state_db_path)
    session = store.get_session(session_id)
    messages = store.list_messages(session_id)

    if start_message_id is not None:
        messages = [message for message in messages if message["id"] >= start_message_id]
    if end_message_id is not None:
        messages = [message for message in messages if message["id"] <= end_message_id]

    slice_start = start_message_id if start_message_id is not None else (messages[0]["id"] if messages else None)
    slice_end = end_message_id if end_message_id is not None else (messages[-1]["id"] if messages else None)

    return {
        "session": session,
        "messages": messages,
        "slice": {
            "start_message_id": slice_start,
            "end_message_id": slice_end,
        },
        "message_count": len(messages),
    }


def export_session_bundle(
    session_id: str,
    paths: HarnessPaths,
    start_message_id: int | None = None,
    end_message_id: int | None = None,
) -> Path:
    paths.ensure_project_dirs()
    payload = build_session_bundle(
        session_id=session_id,
        paths=paths,
        start_message_id=start_message_id,
        end_message_id=end_message_id,
    )
    export_path = paths.exports_dir / f"{session_id}.json"
    export_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return export_path
