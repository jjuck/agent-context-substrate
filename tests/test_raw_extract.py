import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.paths import HarnessPaths  # noqa: E402
from agent_context_substrate.raw_extract import (  # noqa: E402
    build_session_bundle,
    export_session_bundle,
)
from agent_context_substrate.session_store import SessionStore  # noqa: E402


def _build_sample_state_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            user_id TEXT,
            model TEXT,
            model_config TEXT,
            system_prompt TEXT,
            parent_session_id TEXT,
            started_at REAL NOT NULL,
            ended_at REAL,
            end_reason TEXT,
            message_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_write_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            billing_provider TEXT,
            billing_base_url TEXT,
            billing_mode TEXT,
            estimated_cost_usd REAL,
            actual_cost_usd REAL,
            cost_status TEXT,
            cost_source TEXT,
            pricing_version TEXT,
            title TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL,
            token_count INTEGER,
            finish_reason TEXT,
            reasoning TEXT,
            reasoning_details TEXT,
            codex_reasoning_items TEXT
        )
        """
    )
    cur.execute(
        "INSERT INTO sessions (id, source, started_at, message_count, title) VALUES (?, ?, ?, ?, ?)",
        ("session-1", "telegram", 1776395277.0, 2, "Harness planning"),
    )
    cur.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "session-1", "user", "Create the project scaffold", 1776395278.0),
            (2, "session-1", "assistant", "I will bootstrap the project structure.", 1776395280.0),
        ],
    )
    conn.commit()
    conn.close()


def test_session_store_reads_session_and_messages(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    _build_sample_state_db(db_path)

    store = SessionStore(db_path)

    session = store.get_session("session-1")
    messages = store.list_messages("session-1")

    assert session["id"] == "session-1"
    assert session["title"] == "Harness planning"
    assert [message["content"] for message in messages] == [
        "Create the project scaffold",
        "I will bootstrap the project structure.",
    ]


def test_export_session_bundle_writes_json_export(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    db_path = hermes_home / "state.db"
    _build_sample_state_db(db_path)

    paths = HarnessPaths(project_root=project_root)

    export_path = export_session_bundle("session-1", paths=paths)

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert export_path == project_root / "data" / "exports" / "session-1.json"
    assert payload["session"]["id"] == "session-1"
    assert len(payload["messages"]) == 2


def test_build_session_bundle_can_slice_by_message_id_range(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    db_path = hermes_home / "state.db"
    _build_sample_state_db(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (3, "session-1", "user", "Focus on pyproject.toml and src/agent_context_substrate/models.py", 1776395282.0),
            (4, "session-1", "assistant", "I also created tests/test_models.py for the scaffold", 1776395284.0),
        ],
    )
    conn.commit()
    conn.close()

    paths = HarnessPaths(project_root=project_root)

    payload = build_session_bundle("session-1", paths=paths, start_message_id=2, end_message_id=3)

    assert [message["id"] for message in payload["messages"]] == [2, 3]
    assert payload["slice"] == {"start_message_id": 2, "end_message_id": 3}
    assert payload["message_count"] == 2
