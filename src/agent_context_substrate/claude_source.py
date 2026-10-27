from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import os

from .codex_source import DEFAULT_MAX_TOOL_OUTPUT_CHARS, _jsonish, _redact_text, _truncate_tool_text
from .safe_paths import safe_child_path
from .session_bundle import SessionBundle, SessionMessage


_TRANSCRIPT_RECORD_TYPES = {"user", "assistant"}


@dataclass(frozen=True)
class ClaudeSessionRecord:
    session_id: str
    transcript_path: Path
    cwd: str | None = None
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def fingerprint(self) -> dict[str, int | str]:
        stat = self.transcript_path.stat()
        return claude_transcript_fingerprint(
            session_id=self.session_id,
            transcript_path=self.transcript_path,
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
        )


def claude_transcript_fingerprint(
    *,
    session_id: str,
    transcript_path: Path | str,
    mtime_ns: int,
    size: int,
) -> dict[str, int | str]:
    # Same keys as the Codex rollout fingerprint so the durable queue and
    # freshness checks stay source-agnostic.
    return {
        "thread_id": session_id,
        "rollout_path": str(transcript_path),
        "mtime_ns": int(mtime_ns),
        "size": int(size),
    }


def resolve_claude_home(claude_home: Path | str | None = None) -> Path:
    if claude_home is not None:
        return Path(claude_home).expanduser()
    value = os.environ.get("CLAUDE_CONFIG_DIR")
    if value:
        return Path(value).expanduser()
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())).expanduser()
    return home / ".claude"


def discover_claude_sessions(*, claude_home: Path | str | None = None) -> list[ClaudeSessionRecord]:
    projects_root = resolve_claude_home(claude_home) / "projects"
    if not projects_root.exists():
        return []
    records = [
        ClaudeSessionRecord(session_id=path.stem, transcript_path=path)
        for path in projects_root.glob("*/*.jsonl")
        if path.is_file()
    ]
    return sorted(records, key=lambda record: record.transcript_path.stat().st_mtime, reverse=True)


def resolve_claude_session(
    *,
    session_id: str,
    transcript_path: Path | str | None = None,
    claude_home: Path | str | None = None,
) -> ClaudeSessionRecord:
    if transcript_path:
        path = Path(transcript_path).expanduser()
        if not path.is_file():
            raise KeyError(f"Claude transcript not found: {path}")
        return ClaudeSessionRecord(session_id=session_id, transcript_path=path)
    for record in discover_claude_sessions(claude_home=claude_home):
        if record.session_id == session_id:
            return record
    raise KeyError(f"Claude session not found: {session_id}")


def build_claude_session_bundle(
    *,
    session_id: str,
    transcript_path: Path | str | None = None,
    claude_home: Path | str | None = None,
    max_tool_output_chars: int = DEFAULT_MAX_TOOL_OUTPUT_CHARS,
) -> SessionBundle:
    record = resolve_claude_session(session_id=session_id, transcript_path=transcript_path, claude_home=claude_home)
    messages: list[SessionMessage] = []
    cwd: str | None = None
    git_branch: str | None = None
    title: str | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    for line_number, entry in _iter_transcript_entries(record.transcript_path):
        entry_type = str(entry.get("type") or "")
        if entry_type == "custom-title":
            title = str(entry.get("customTitle") or "") or title
            continue
        if entry_type == "summary" and title is None:
            title = str(entry.get("summary") or "") or None
            continue
        if entry_type not in _TRANSCRIPT_RECORD_TYPES:
            continue
        if entry.get("isSidechain") is True or entry.get("isMeta") is True:
            continue
        timestamp = entry.get("timestamp")
        if timestamp is not None:
            first_timestamp = first_timestamp or str(timestamp)
            last_timestamp = str(timestamp)
        cwd = str(entry.get("cwd") or "") or cwd
        git_branch = str(entry.get("gitBranch") or "") or git_branch
        for role, content, extra in _messages_from_entry(entry, max_tool_output_chars=max_tool_output_chars):
            metadata: dict[str, Any] = {
                "claude_event_type": entry_type,
                "transcript_line": line_number,
                **extra,
            }
            if timestamp is not None:
                metadata["timestamp"] = str(timestamp)
            if entry.get("uuid"):
                metadata["uuid"] = str(entry["uuid"])
            messages.append(
                SessionMessage(id=len(messages) + 1, role=role, content=content, metadata=metadata)
            )

    message_ids = [message.id for message in messages]
    metadata: dict[str, Any] = {
        "transcript_path": str(record.transcript_path),
        "provenance": format_claude_provenance(session_id, message_ids),
    }
    if cwd:
        metadata["cwd"] = cwd
    if git_branch:
        metadata["git_branch"] = git_branch
    return SessionBundle(
        session_id=session_id,
        source="claude-code",
        title=title or record.title,
        started_at=first_timestamp,
        ended_at=last_timestamp,
        messages=messages,
        slice_start_message_id=(message_ids[0] if message_ids else None),
        slice_end_message_id=(message_ids[-1] if message_ids else None),
        metadata=metadata,
    )


def export_claude_session_bundle(*, bundle: SessionBundle, project_root: Path | str) -> Path:
    export_dir = Path(project_root) / "data" / "exports" / "raw" / "claude"
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = safe_child_path(export_dir, bundle.session_id, ".json", label="claude session id")
    output_path.write_text(
        json.dumps(bundle.to_raw_bundle(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def format_claude_provenance(session_id: str, message_ids: Iterable[int]) -> str:
    ids = ",".join(str(message_id) for message_id in message_ids)
    return f"claude-session:{session_id}#messages={ids}"


def _iter_transcript_entries(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield line_number, entry


def _messages_from_entry(
    entry: dict[str, Any],
    *,
    max_tool_output_chars: int,
) -> list[tuple[str, str, dict[str, Any]]]:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    role = str(message.get("role") or entry.get("type") or "")
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
        return [(role, _redact_text(text), {})] if text else []
    if not isinstance(content, list):
        return []

    results: list[tuple[str, str, dict[str, Any]]] = []
    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type == "text":
            text = str(block.get("text") or "").strip()
            if text:
                text_parts.append(text)
        elif block_type == "tool_use":
            name = str(block.get("name") or "tool_use")
            call_id = str(block.get("id") or "")
            arguments = _jsonish(block.get("input", {}))
            results.append(
                (
                    "tool",
                    _redact_text(f"function_call name={name} call_id={call_id} arguments={arguments}"),
                    {"tool_name": name, "call_id": call_id},
                )
            )
        elif block_type == "tool_result":
            call_id = str(block.get("tool_use_id") or "")
            output = _truncate_tool_text(
                _redact_text(_flatten_tool_result(block.get("content"))),
                max_chars=max_tool_output_chars,
            )
            extra: dict[str, Any] = {"call_id": call_id}
            if block.get("is_error") is True:
                extra["is_error"] = True
            results.append(("tool", output, extra))
        # thinking/redacted_thinking/image blocks are intentionally dropped.
    if text_parts:
        results.insert(0, (role, _redact_text("\n".join(text_parts)), {}))
    return results


def _flatten_tool_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        pieces: list[str] = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text") is not None:
                    pieces.append(str(item["text"]))
                elif item.get("type") == "image":
                    pieces.append("[image]")
            elif item is not None:
                pieces.append(str(item))
        return "\n".join(piece for piece in pieces if piece)
    return _jsonish(value)
