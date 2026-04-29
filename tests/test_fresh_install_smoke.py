from __future__ import annotations

from pathlib import Path
import sqlite3

from agent_context_substrate.distribution import run_fresh_install_smoke


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
            (
                1,
                "session-1",
                "user",
                "Create a context packet and recovery brief for Agent Context Substrate distribution.",
                1776395278.0,
            ),
            (
                2,
                "session-1",
                "assistant",
                "Built packet-only finalize artifacts, recovery JSON, and retrieval evidence for distribution smoke.",
                1776395280.0,
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_fresh_install_smoke_runs_packet_recovery_retrieval_and_lint(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    hermes_agent_root = tmp_path / "hermes-agent"

    result = run_fresh_install_smoke(
        session_id="session-1",
        hermes_home=hermes_home,
        project_root=project_root,
        wiki_root=wiki_root,
        hermes_agent_root=hermes_agent_root,
    )

    assert result.ok is True
    assert result.artifacts["packet_json_path"].exists()
    assert result.artifacts["recovery_json_path"].exists()
    assert result.retrieval_hit_count > 0
    assert result.expanded_content_length > 0
    assert result.lint_issue_count == 0
    assert (hermes_home / "plugins" / "agent-context-substrate" / "plugin.yaml").exists()
    assert (
        hermes_agent_root / "plugins" / "context_engine" / "agent_context_substrate" / "engine.py"
    ).exists()
