import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.integration import run_session_finalize_pipeline  # noqa: E402
from agent_context_substrate.recovery import build_recovery_brief  # noqa: E402


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
        ("session-1", "telegram", 1776395277.0, 5, "Recovery brief planning"),
    )
    cur.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "session-1", "user", "Attach agent-context-substrate to Hermes Agent and recover previous work quickly.", 1776395278.0),
            (2, "session-1", "assistant", "I will inspect state.db and the plugin/context-engine extension points.", 1776395280.0),
            (3, "session-1", "assistant", "Key files: /home/example/.hermes/hermes-agent/hermes_state.py, gateway/run.py, hermes_cli/plugins.py", 1776395282.0),
            (4, "session-1", "assistant", "Next step: build recovery.py so /wiki-resume can show a compact packet summary.", 1776395283.0),
            (5, "session-1", "user", "Export a short recovery brief after finalize.", 1776395284.0),
        ],
    )
    conn.commit()
    conn.close()


def test_build_recovery_brief_reads_packet_and_exports_json(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    integration_result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        promotion_mode="full",
    )
    brief = build_recovery_brief(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        max_items=2,
    )

    assert integration_result.recovery_json_path.exists()
    assert brief.session_id == "session-1"
    assert brief.packet_id == "session-1"
    assert brief.task_title == "Recovery brief planning"
    assert brief.recovery_json_path == integration_result.recovery_json_path
    assert len(brief.critical_files) <= 2
    assert len(brief.related_pages) == 2
    assert len(brief.provenance) <= 2

    payload = json.loads(brief.recovery_json_path.read_text(encoding="utf-8"))
    assert payload["packet_id"] == "session-1"
    assert payload["task_title"] == "Recovery brief planning"
    assert payload["related_pages"] == brief.related_pages
