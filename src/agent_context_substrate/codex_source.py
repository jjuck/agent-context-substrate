from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import os
import re
import sqlite3

from .safe_paths import safe_child_path
from .session_bundle import SessionBundle, SessionMessage


DEFAULT_MAX_TOOL_OUTPUT_CHARS = 12_000
_SENSITIVE_KEY_RE = re.compile(r"(?i)(api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]\s*([^\s,\"]+)")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


@dataclass(frozen=True)
class CodexThreadRecord:
    thread_id: str
    rollout_path: Path
    created_at: str | None = None
    updated_at: str | None = None
    cwd: str | None = None
    title: str | None = None
    archived: bool = False

    @property
    def fingerprint(self) -> dict[str, int | str]:
        stat = self.rollout_path.stat()
        return {
            "thread_id": self.thread_id,
            "rollout_path": str(self.rollout_path),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }


def resolve_codex_home(codex_home: Path | str | None = None) -> Path:
    if codex_home is not None:
        return Path(codex_home).expanduser()
    value = os.environ.get("CODEX_HOME")
    if value:
        return Path(value).expanduser()
    home = Path(os.environ.get("HOME") or str(Path.home())).expanduser()
    return home / ".codex"


def discover_codex_threads(*, codex_home: Path | str | None = None, include_archived: bool = False) -> list[CodexThreadRecord]:
    root = resolve_codex_home(codex_home)
    records = _discover_threads_from_state_db(root, include_archived=include_archived)
    if records:
        return sorted(records, key=lambda record: record.rollout_path.stat().st_mtime, reverse=True)
    return _discover_threads_from_rollout_glob(root)


def build_codex_session_bundle(
    *,
    thread_id: str,
    codex_home: Path | str | None = None,
    rollout_path: Path | str | None = None,
    max_tool_output_chars: int = DEFAULT_MAX_TOOL_OUTPUT_CHARS,
) -> SessionBundle:
    record = _resolve_thread_record(thread_id=thread_id, codex_home=codex_home, rollout_path=rollout_path)
    messages: list[SessionMessage] = []
    for line_number, timestamp, payload in _iter_rollout_payloads(record.rollout_path):
        message = _message_from_payload(
            line_number=line_number,
            timestamp=timestamp,
            payload=payload,
            max_tool_output_chars=max_tool_output_chars,
        )
        if message is not None:
            messages.append(message)

    message_ids = [message.id for message in messages]
    metadata: dict[str, Any] = {
        "rollout_path": str(record.rollout_path),
        "provenance": format_codex_provenance(thread_id, message_ids),
    }
    if record.cwd:
        metadata["cwd"] = record.cwd
    return SessionBundle(
        session_id=thread_id,
        source="codex",
        title=record.title,
        started_at=record.created_at,
        ended_at=record.updated_at,
        messages=messages,
        slice_start_message_id=(message_ids[0] if message_ids else None),
        slice_end_message_id=(message_ids[-1] if message_ids else None),
        metadata=metadata,
    )


def export_codex_session_bundle(*, bundle: SessionBundle, project_root: Path | str) -> Path:
    export_dir = Path(project_root) / "data" / "exports" / "raw" / "codex"
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = safe_child_path(export_dir, bundle.session_id, ".json", label="codex thread id")
    output_path.write_text(
        json.dumps(bundle.to_raw_bundle(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def format_codex_provenance(thread_id: str, message_ids: Iterable[int]) -> str:
    ids = ",".join(str(message_id) for message_id in message_ids)
    return f"codex-thread:{thread_id}#messages={ids}"


def codex_hook_support_status(*, codex_home: Path | str | None = None) -> str:
    """Return current local hook capability for Codex plugins.

    Codex documents plugin-bundled lifecycle hooks, including Stop hooks. ACS
    keeps hooks out of the manifest for local validator compatibility and ships
    the default hook under hooks/hooks.json.
    """

    return "supported"


def codex_installed_hook_status(*, codex_home: Path | str | None = None) -> str:
    root = resolve_codex_home(codex_home)
    plugin_root = root / "plugins" / "agent-context-substrate"
    if (plugin_root / "hooks" / "hooks.json").is_file() and (
        plugin_root / "hooks" / "codex_stop_finalize.py"
    ).is_file():
        return "installed"
    return "not-installed"


def _resolve_thread_record(
    *,
    thread_id: str,
    codex_home: Path | str | None,
    rollout_path: Path | str | None,
) -> CodexThreadRecord:
    if rollout_path is not None:
        return CodexThreadRecord(thread_id=thread_id, rollout_path=Path(rollout_path).expanduser())
    for record in discover_codex_threads(codex_home=codex_home, include_archived=True):
        if record.thread_id == thread_id:
            return record
    raise KeyError(f"Codex thread not found: {thread_id}")


def _discover_threads_from_state_db(root: Path, *, include_archived: bool) -> list[CodexThreadRecord]:
    state_path = root / "state_5.sqlite"
    if not state_path.exists():
        return []
    try:
        uri = state_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='threads'"
            ).fetchone()
            if table is None:
                return []
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(threads)").fetchall()}
            required = {"id", "rollout_path"}
            if not required.issubset(columns):
                return []
            optional = [
                column
                for column in ["created_at", "updated_at", "cwd", "title", "archived"]
                if column in columns
            ]
            query_columns = ["id", "rollout_path", *optional]
            order_columns = [column for column in ["updated_at", "created_at", "id"] if column in columns]
            order_sql = ", ".join(order_columns) if order_columns else "id"
            rows = connection.execute(
                f"SELECT {', '.join(query_columns)} FROM threads ORDER BY {order_sql} DESC"
            ).fetchall()
    except sqlite3.Error:
        return []

    records: list[CodexThreadRecord] = []
    for row in rows:
        archived = bool(int(row["archived"])) if "archived" in row.keys() and row["archived"] is not None else False
        if archived and not include_archived:
            continue
        rollout = Path(str(row["rollout_path"])).expanduser()
        if not rollout.is_absolute():
            rollout = root / rollout
        if not rollout.exists():
            continue
        records.append(
            CodexThreadRecord(
                thread_id=str(row["id"]),
                rollout_path=rollout,
                created_at=_optional_row_str(row, "created_at"),
                updated_at=_optional_row_str(row, "updated_at"),
                cwd=_optional_row_str(row, "cwd"),
                title=_optional_row_str(row, "title"),
                archived=archived,
            )
        )
    return records


def _discover_threads_from_rollout_glob(root: Path) -> list[CodexThreadRecord]:
    session_root = root / "sessions"
    records: list[CodexThreadRecord] = []
    if not session_root.exists():
        return records
    for path in sorted(session_root.rglob("rollout-*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True):
        records.append(
            CodexThreadRecord(
                thread_id=path.stem.removeprefix("rollout-"),
                rollout_path=path,
                updated_at=None,
                title=path.stem,
            )
        )
    return records


def _optional_row_str(row: sqlite3.Row, key: str) -> str | None:
    if key not in row.keys() or row[key] is None:
        return None
    return str(row[key])


def _iter_rollout_payloads(path: Path) -> Iterable[tuple[int, str | None, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload", record)
            if not isinstance(payload, dict):
                continue
            timestamp = record.get("timestamp") if isinstance(record, dict) else None
            yield line_number, (str(timestamp) if timestamp is not None else None), payload


def _message_from_payload(
    *,
    line_number: int,
    timestamp: str | None,
    payload: dict[str, Any],
    max_tool_output_chars: int,
) -> SessionMessage | None:
    if _is_encrypted_payload(payload):
        return None
    event_type = str(payload.get("type") or "")
    metadata: dict[str, Any] = {
        "codex_event_type": event_type,
        "rollout_line": line_number,
    }
    if timestamp is not None:
        metadata["timestamp"] = timestamp

    if event_type == "user_message":
        return SessionMessage(
            id=line_number,
            role="user",
            content=_redact_text(str(payload.get("message") or "")),
            metadata=metadata,
        )
    if event_type == "agent_message":
        phase = payload.get("phase")
        if phase is not None:
            metadata["phase"] = str(phase)
        return SessionMessage(
            id=line_number,
            role="assistant",
            content=_redact_text(str(payload.get("message") or "")),
            metadata=metadata,
        )
    if event_type == "function_call":
        name = str(payload.get("name") or "function_call")
        call_id = str(payload.get("call_id") or "")
        arguments = _jsonish(payload.get("arguments", ""))
        metadata.update({"tool_name": name, "call_id": call_id})
        return SessionMessage(
            id=line_number,
            role="tool",
            content=_redact_text(f"function_call name={name} call_id={call_id} arguments={arguments}"),
            metadata=metadata,
        )
    if event_type == "function_call_output":
        call_id = str(payload.get("call_id") or "")
        metadata["call_id"] = call_id
        return SessionMessage(
            id=line_number,
            role="tool",
            content=_truncate_tool_text(_redact_text(str(payload.get("output") or "")), max_chars=max_tool_output_chars),
            metadata=metadata,
        )
    if event_type == "message":
        role = str(payload.get("role") or "")
        if role in {"system", "developer"}:
            return None
        if role in {"user", "assistant", "tool"}:
            return SessionMessage(
                id=line_number,
                role=role,
                content=_redact_text(_flatten_content(payload.get("content"))),
                metadata=metadata,
            )
    return None


def _is_encrypted_payload(payload: dict[str, Any]) -> bool:
    if payload.get("encrypted") is True:
        return True
    return any(key in payload for key in ("encrypted_content", "ciphertext"))


def _flatten_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        pieces: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text is not None:
                    pieces.append(str(text))
            else:
                pieces.append(str(item))
        return "\n".join(piece for piece in pieces if piece)
    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        if text is not None:
            return str(text)
    return str(value)


def _jsonish(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _redact_text(value: str) -> str:
    redacted = _SENSITIVE_KEY_RE.sub(r"\1=[REDACTED]", value)
    return _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)


def _truncate_tool_text(value: str, *, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n[truncated]"
