import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.packet_builder import PacketBuildOptions, PacketBuildResult, build_packet_from_session  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402


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
                "Create the project scaffold with pyproject.toml and src/agent_context_substrate/models.py",
                1776395278.0,
            ),
            (
                2,
                "session-1",
                "assistant",
                "I will bootstrap the project structure and add tests/test_models.py for the scaffold.",
                1776395280.0,
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_packet_builder_exports_raw_and_context_packet(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    paths = HarnessPaths(project_root=project_root)

    result = build_packet_from_session(
        paths=paths,
        options=PacketBuildOptions(
            session_id="session-1",
            packet_id="packet-1",
            task_title="Task",
            macro_context="Context",
            unit_title="Unit",
            goal="Goal",
            related_pages=["[[Agent Context Substrate]]"],
        ),
    )

    assert isinstance(result, PacketBuildResult)
    assert result.as_tuple() == (
        result.packet,
        result.raw_export_path,
        result.packet_json_path,
        result.packet_markdown_path,
    )
    assert result.raw_export_path == project_root / "data" / "exports" / "session-1.json"
    assert result.packet_json_path == project_root / "data" / "exports" / "context_packets" / "packet-1.json"
    assert result.packet_markdown_path == project_root / "data" / "exports" / "context_packets" / "packet-1.md"
    assert result.raw_export_path.exists()
    assert result.packet_json_path.exists()
    assert result.packet_markdown_path.exists()

    packet_payload = json.loads(result.packet_json_path.read_text(encoding="utf-8"))
    assert packet_payload["packet_id"] == "packet-1"
    assert packet_payload["task_title"] == "Task"
    assert packet_payload["unit_summaries"][0]["title"] == "Unit"
    assert packet_payload["unit_summaries"][0]["related_pages"] == ["[[Agent Context Substrate]]"]
    assert packet_payload["micro_summaries"][0]["micro_id"] == "packet-1-micro-1"
