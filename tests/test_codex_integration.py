from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent_context_substrate.codex_integration import (
    CodexWatcherState,
    discover_due_codex_threads,
    run_codex_thread_finalize_pipeline,
)
from agent_context_substrate.retrieval import search_knowledge


def _write_codex_thread(codex_home: Path, *, thread_id: str, rollout_path: Path) -> None:
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    rollout_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-06-01T00:00:00Z", "payload": {"type": "user_message", "message": "Build Codex support"}}),
                json.dumps({"timestamp": "2026-06-01T00:01:00Z", "payload": {"type": "agent_message", "message": "Codex support is implemented"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with sqlite3.connect(codex_home / "state_5.sqlite") as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, rollout_path TEXT, updated_at TEXT, cwd TEXT, title TEXT, archived INTEGER)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO threads (id, rollout_path, updated_at, cwd, title, archived) VALUES (?, ?, ?, ?, ?, 0)",
            (thread_id, str(rollout_path), "2026-06-01T00:01:00Z", str(codex_home / "project"), "Codex support"),
        )


def test_codex_finalize_exports_packet_recovery_and_ledger(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home.mkdir()
    wiki_root.mkdir()
    _write_codex_thread(
        codex_home,
        thread_id="thread-1",
        rollout_path=codex_home / "sessions" / "rollout-thread-1.jsonl",
    )

    result = run_codex_thread_finalize_pipeline(
        thread_id="thread-1",
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
    )

    assert result.session_id == "thread-1"
    assert result.raw_export_path.exists()
    assert result.packet_json_path.exists()
    assert result.packet_markdown_path.exists()
    assert result.recovery_json_path.exists()
    assert (project_root / "data" / "index" / "session_ledger.json").exists()
    packet_payload = json.loads(result.packet_json_path.read_text(encoding="utf-8"))
    assert packet_payload["raw_pointers"][0]["source"] == "codex"
    assert packet_payload["micro_summaries"][0]["provenance"]["source"] == "codex"
    assert packet_payload["unit_summaries"][0]["provenance"]["source"] == "codex"
    recovery_payload = json.loads(result.recovery_json_path.read_text(encoding="utf-8"))
    assert recovery_payload["provenance"] == ["codex-thread:thread-1#messages=1,2"]
    hits = search_knowledge("Codex support", project_root=project_root, wiki_root=wiki_root, mode="knowledge")
    codex_hits = [hit for hit in hits if hit.source_path == "data/exports/context_packets/thread-1.json"]
    assert codex_hits
    assert all("codex-thread:thread-1#messages=1,2" in hit.provenance for hit in codex_hits)


def test_codex_watcher_selects_idle_threads_once(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    codex_home.mkdir()
    rollout_path = codex_home / "sessions" / "rollout-thread-1.jsonl"
    _write_codex_thread(codex_home, thread_id="thread-1", rollout_path=rollout_path)
    state = CodexWatcherState(project_root / "data" / "index" / "codex_watcher_state.json")

    due = discover_due_codex_threads(
        codex_home=codex_home,
        state=state,
        idle_seconds=0,
    )
    state.mark_processed(due[0])
    second_due = discover_due_codex_threads(
        codex_home=codex_home,
        state=state,
        idle_seconds=0,
    )

    assert [thread.thread_id for thread in due] == ["thread-1"]
    assert second_due == []


def test_codex_watcher_state_can_record_discovery_fingerprint(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    codex_home.mkdir()
    rollout_path = codex_home / "sessions" / "rollout-thread-1.jsonl"
    _write_codex_thread(codex_home, thread_id="thread-1", rollout_path=rollout_path)
    state = CodexWatcherState(project_root / "data" / "index" / "codex_watcher_state.json")
    thread = discover_due_codex_threads(codex_home=codex_home, state=state, idle_seconds=0)[0]
    fingerprint = thread.fingerprint
    rollout_path.write_text(rollout_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    state.mark_processed(thread, fingerprint=fingerprint)

    assert state.is_processed(thread) is False
