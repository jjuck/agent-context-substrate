import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.integration import run_session_finalize_pipeline  # noqa: E402
from agent_context_substrate.ledger import SessionLedger  # noqa: E402


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
        ("session-1", "telegram", 1776395277.0, 4, "Harness integration planning"),
    )
    cur.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "session-1", "user", "Attach agent-context-substrate to Hermes Agent.", 1776395278.0),
            (2, "session-1", "assistant", "I will inspect plugin hooks and state.db.", 1776395280.0),
            (3, "session-1", "assistant", "Key files: hermes_state.py, gateway/run.py, hermes_cli/plugins.py", 1776395282.0),
            (4, "session-1", "user", "Add a ledger so finalize hooks do not reprocess sessions twice.", 1776395284.0),
        ],
    )
    conn.commit()
    conn.close()


def test_session_ledger_round_trips_completed_records(tmp_path) -> None:
    ledger = SessionLedger(tmp_path / "data" / "index" / "session_ledger.json")

    ledger.mark_completed(
        session_id="session-1",
        pipeline="session_finalize",
        artifact_paths={
            "packet_json": "/tmp/project/data/exports/context_packets/session-1.json",
            "lint_json": "/tmp/project/data/exports/lint/session-1-lint.json",
        },
    )

    record = ledger.get_record("session-1", "session_finalize")
    payload = json.loads((tmp_path / "data" / "index" / "session_ledger.json").read_text(encoding="utf-8"))

    assert record is not None
    assert record.status == "completed"
    assert record.artifact_paths["packet_json"].endswith("session-1.json")
    assert payload["session_finalize"]["session-1"]["status"] == "completed"


def test_run_session_finalize_pipeline_skips_already_completed_session(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    first = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
    )
    second = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
    )

    assert first.skipped is False
    assert second.skipped is True
    assert second.packet_json_path == first.packet_json_path
    assert second.lint_json_path == first.lint_json_path

    ledger_path = project_root / "data" / "index" / "session_ledger.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert payload["session_finalize"]["session-1"]["status"] == "completed"
