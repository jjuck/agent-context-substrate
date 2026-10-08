from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agent_context_substrate.codex_source import (
    build_codex_session_bundle,
    discover_codex_threads,
    export_codex_session_bundle,
    format_codex_provenance,
)


def _write_rollout(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"timestamp": "2026-06-01T00:00:00Z", "payload": event}) + "\n" for event in events),
        encoding="utf-8",
    )


def _write_state(codex_home: Path, *, thread_id: str, rollout_path: Path, cwd: Path | None = None) -> Path:
    state_path = codex_home / "state_5.sqlite"
    with sqlite3.connect(state_path) as connection:
        connection.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                rollout_path TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                cwd TEXT,
                title TEXT,
                archived INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO threads (id, rollout_path, created_at, updated_at, cwd, title, archived)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                thread_id,
                str(rollout_path),
                "2026-06-01T00:00:00Z",
                "2026-06-01T00:05:00Z",
                str(cwd or codex_home / "project"),
                "Codex rollout review",
            ),
        )
    return state_path


def test_discover_codex_threads_reads_state_db_rollout_paths(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    rollout_path = codex_home / "sessions" / "2026" / "06" / "01" / "rollout-thread-1.jsonl"
    _write_rollout(rollout_path, [{"type": "user_message", "message": "Please review this project"}])
    _write_state(codex_home, thread_id="thread-1", rollout_path=rollout_path)

    threads = discover_codex_threads(codex_home=codex_home)

    assert [thread.thread_id for thread in threads] == ["thread-1"]
    assert threads[0].rollout_path == rollout_path
    assert threads[0].title == "Codex rollout review"


def test_build_codex_session_bundle_filters_and_formats_messages(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    rollout_path = codex_home / "sessions" / "rollout-thread-1.jsonl"
    _write_rollout(
        rollout_path,
        [
            {"type": "session_meta", "id": "thread-1"},
            {"type": "message", "role": "system", "content": [{"text": "hidden system prompt"}]},
            {"type": "message", "role": "developer", "content": [{"text": "hidden developer prompt"}]},
            {"type": "reasoning", "summary": [{"text": "private chain of thought"}]},
            {"type": "token_count", "input_tokens": 10},
            {"type": "user_message", "message": "Implement Codex support"},
            {"type": "agent_message", "message": "I will inspect the repo.", "phase": "commentary"},
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "shell_command",
                "arguments": "{\"command\":\"rg Codex\"}",
            },
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": "x" * 80,
            },
            {"type": "agent_message", "message": "Done."},
            {"type": "user_message", "message": "secret", "encrypted": True},
        ],
    )
    _write_state(codex_home, thread_id="thread-1", rollout_path=rollout_path)

    bundle = build_codex_session_bundle(
        thread_id="thread-1",
        codex_home=codex_home,
        max_tool_output_chars=24,
    )

    assert bundle.session_id == "thread-1"
    assert bundle.source == "codex"
    assert bundle.title == "Codex rollout review"
    assert [message.role for message in bundle.messages] == ["user", "assistant", "tool", "tool", "assistant"]
    assert [message.id for message in bundle.messages] == [6, 7, 8, 9, 10]
    contents = [message.content for message in bundle.messages]
    assert "Implement Codex support" in contents[0]
    assert "shell_command" in contents[2]
    assert contents[3].endswith("[truncated]")
    assert "private chain of thought" not in "\n".join(contents)
    assert "hidden developer prompt" not in "\n".join(contents)
    assert bundle.slice_start_message_id == 6
    assert bundle.slice_end_message_id == 10


def test_export_codex_session_bundle_preserves_codex_provenance(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    codex_home.mkdir()
    rollout_path = codex_home / "sessions" / "rollout-thread-1.jsonl"
    _write_rollout(
        rollout_path,
        [
            {"type": "user_message", "message": "Find the bug"},
            {"type": "agent_message", "message": "The bug is fixed."},
        ],
    )
    _write_state(codex_home, thread_id="thread-1", rollout_path=rollout_path)
    bundle = build_codex_session_bundle(thread_id="thread-1", codex_home=codex_home)

    path = export_codex_session_bundle(bundle=bundle, project_root=project_root)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path == project_root / "data" / "exports" / "raw" / "codex" / "thread-1.json"
    assert payload["session"]["source"] == "codex"
    assert payload["session"]["provenance"] == "codex-thread:thread-1#messages=1,2"
    assert format_codex_provenance("thread-1", [1, 2]) == "codex-thread:thread-1#messages=1,2"


_INSTRUCTIONS = "# AGENTS.md instructions\n\n<INSTRUCTIONS>\nRun tests.\n</INSTRUCTIONS>"
_ENVIRONMENT = "<environment_context>\n<cwd>C:/repo</cwd>\n</environment_context>"


@pytest.mark.parametrize("context", [
    _INSTRUCTIONS,
    _INSTRUCTIONS + "\n" + _ENVIRONMENT,
    _INSTRUCTIONS.replace("instructions", "instructions for C:/repo"),
    _ENVIRONMENT,
])
def test_codex_excludes_injected_context_and_keeps_original_line_provenance(tmp_path: Path, context: str) -> None:
    path = tmp_path / "rollout.jsonl"
    _write_rollout(path, [
        {"type": "message", "role": "user", "content": [{"text": context}]},
        {"type": "message", "role": "user", "content": [{"text": "Fix the ACS hook."}]},
        {"type": "message", "role": "assistant", "content": [{"text": "The hook is fixed."}]},
    ])
    original = path.read_bytes()
    bundle = build_codex_session_bundle(thread_id="test", rollout_path=path)
    assert [m.content for m in bundle.messages] == ["Fix the ACS hook.", "The hook is fixed."]
    assert [m.id for m in bundle.messages] == [2, 3]
    assert bundle.metadata["excluded_context_message_ids"] == [1]
    assert bundle.to_raw_bundle()["session"]["excluded_context_message_ids"] == [1]
    assert bundle.metadata["provenance"] == "codex-thread:test#messages=2,3"
    assert path.read_bytes() == original


@pytest.mark.parametrize("user_text", [
    "Please edit AGENTS.md and explain <environment_context>.",
    "```markdown\n" + _INSTRUCTIONS + "\n```",
    _INSTRUCTIONS + "\nPlease explain these rules.",
    _ENVIRONMENT + "\nFix my environment.",
    _ENVIRONMENT + "\nCompare these environments.\n" + _ENVIRONMENT,
    _INSTRUCTIONS + "\nCompare these instructions.\n" + _INSTRUCTIONS,
    "# AGENTS.md instructions\n<INSTRUCTIONS>incomplete",
    "# AGENTS.md instructions<INSTRUCTIONS>Run tests.</INSTRUCTIONS>",
    "    <environment_context>indented code example</environment_context>",
])
def test_codex_preserves_user_requests_about_instructions(tmp_path: Path, user_text: str) -> None:
    path = tmp_path / "rollout.jsonl"
    _write_rollout(path, [{"type": "message", "role": "user", "content": [{"text": user_text}]}])
    bundle = build_codex_session_bundle(thread_id="test", rollout_path=path)
    assert [m.content for m in bundle.messages] == [user_text]


@pytest.mark.parametrize("event_first", [False, True])
@pytest.mark.parametrize("event", [
    {"type": "user_message", "message": _INSTRUCTIONS},
    {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"text": _INSTRUCTIONS}]}},
    {"type": "item_completed", "item": {"type": "userMessage", "content": [{"text": _INSTRUCTIONS}]}},
])
def test_codex_explicit_user_event_preserves_literal_context_envelope(tmp_path: Path, event: dict, event_first: bool) -> None:
    path = tmp_path / "rollout.jsonl"
    events = [
        {"type": "message", "role": "user", "content": [{"text": _INSTRUCTIONS}]},
        event,
    ]
    _write_rollout(path, list(reversed(events)) if event_first else events)
    bundle = build_codex_session_bundle(thread_id="test", rollout_path=path)
    assert any(m.metadata["codex_event_type"] == "message" and m.content == _INSTRUCTIONS for m in bundle.messages)
    assert "excluded_context_message_ids" not in bundle.metadata


def test_codex_preserves_envelope_text_with_image_attachment(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    _write_rollout(path, [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": _INSTRUCTIONS},
        {"type": "input_image", "image_url": "data:image/png;base64,test"},
    ]}])
    bundle = build_codex_session_bundle(thread_id="test", rollout_path=path)
    assert len(bundle.messages) == 1
    assert bundle.messages[0].content == _INSTRUCTIONS
