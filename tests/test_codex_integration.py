from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import agent_context_substrate.codex_integration as codex_integration
from agent_context_substrate.codex_integration import (
    CodexWatcherState,
    discover_due_codex_threads,
    run_codex_thread_finalize_pipeline,
)
from agent_context_substrate.promotions import PromotionCandidate
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


def test_codex_finalize_auto_summary_falls_back_and_records_ledger_metadata(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    missing_codex = tmp_path / "missing-codex.exe"
    codex_home.mkdir()
    wiki_root.mkdir()
    _write_codex_thread(
        codex_home,
        thread_id="thread-auto",
        rollout_path=codex_home / "sessions" / "rollout-thread-auto.jsonl",
    )

    result = run_codex_thread_finalize_pipeline(
        thread_id="thread-auto",
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        summary_mode="auto",
        codex_cli_command=missing_codex,
        summary_cache=True,
    )

    assert result.summary_micro_path is not None
    assert result.summary_unit_path is not None
    micro_payload = json.loads(result.summary_micro_path.read_text(encoding="utf-8"))
    unit_payload = json.loads(result.summary_unit_path.read_text(encoding="utf-8"))
    assert micro_payload["metadata"]["mode"] == "heuristic"
    assert micro_payload["metadata"]["fallback_from"] == "auto"
    assert micro_payload["metadata"]["fallback_reason"] == "codex_cli_unavailable"
    assert unit_payload["metadata"]["fallback_from"] == "auto"

    ledger_payload = json.loads((project_root / "data" / "index" / "session_ledger.json").read_text(encoding="utf-8"))
    record = ledger_payload["session_finalize"]["thread-auto"]
    assert record["artifact_paths"]["summary_mode"] == "auto"
    assert record["artifact_paths"]["summary_micro_mode"] == "heuristic"
    assert record["artifact_paths"]["summary_micro_fallback_from"] == "auto"
    assert record["artifact_paths"]["summary_micro_fallback_reason"] == "codex_cli_unavailable"


def test_codex_finalize_auto_applies_flexible_wiki_patch_when_judge_approves(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home.mkdir()
    wiki_root.mkdir()
    _write_codex_thread(
        codex_home,
        thread_id="thread-wiki",
        rollout_path=codex_home / "sessions" / "rollout-thread-wiki.jsonl",
    )
    requests: list[dict[str, object]] = []

    def judge_router(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        return {
            "ok": True,
            "score": 0.93,
            "decision": "apply_flexible",
            "candidate_ids": [request["candidates"][0]["candidate_id"]],
            "issues": [],
            "rationale": "The thread contains durable implementation knowledge for the LLM Wiki.",
            "metadata": {"model": "judge-test"},
        }

    result = run_codex_thread_finalize_pipeline(
        thread_id="thread-wiki",
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        summary_mode="heuristic",
        wiki_auto_mode="apply-flexible",
        wiki_write_judge_mode="hybrid",
        wiki_write_judge_router=judge_router,
    )

    assert result.wiki_decision_path is not None
    assert result.wiki_patch_path is not None
    assert result.wiki_apply_result is not None
    assert result.wiki_apply_result.applied_patch_ids
    assert requests[0]["kind"] == "wiki-write-judge"
    assert list(wiki_root.rglob("*.md"))
    ledger_payload = json.loads((project_root / "data" / "index" / "session_ledger.json").read_text(encoding="utf-8"))
    record = ledger_payload["session_finalize"]["thread-wiki"]
    assert record["artifact_paths"]["wiki_auto_mode"] == "apply-flexible"
    assert record["artifact_paths"]["wiki_write_decision"] == "apply_flexible"


def test_codex_finalize_auto_merges_same_target_candidates_and_lints_clean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home.mkdir()
    wiki_root.mkdir()
    _write_codex_thread(
        codex_home,
        thread_id="thread-wiki-merged",
        rollout_path=codex_home / "sessions" / "rollout-thread-wiki-merged.jsonl",
    )
    candidates = [
        PromotionCandidate(
            candidate_id="thread-wiki-merged-candidate-1",
            packet_id="thread-wiki-merged",
            kind="wiki_update",
            target_page="Agent Context Substrate",
            reason="Watcher behavior is durable.",
            evidence=["claim:thread-wiki-merged-claim-1"],
            proposed_change="run_codex_watch_once discovers due Codex threads and finalizes them.",
            proposed_action="update_existing",
            confidence=0.91,
            status="pending",
            category="codex-runtime-insight",
            page_type="runtime-note",
        ),
        PromotionCandidate(
            candidate_id="thread-wiki-merged-candidate-2",
            packet_id="thread-wiki-merged",
            kind="wiki_update",
            target_page="Agent Context Substrate",
            reason="Flexible write behavior is durable.",
            evidence=["claim:thread-wiki-merged-claim-2"],
            proposed_change="Approved flexible wiki writes should produce lint-clean durable pages.",
            proposed_action="update_existing",
            confidence=0.92,
            status="pending",
            category="codex-runtime-insight",
            page_type="runtime-note",
        ),
    ]

    def export_candidates(*, packet_id: str, paths):
        promotion_dir = paths.project_root / "data" / "promotions"
        promotion_dir.mkdir(parents=True, exist_ok=True)
        json_path = promotion_dir / f"{packet_id}.json"
        markdown_path = promotion_dir / f"{packet_id}.md"
        json_path.write_text(
            json.dumps([candidate.to_dict() for candidate in candidates], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        markdown_path.write_text("# Promotion Candidates\n", encoding="utf-8")
        return json_path, markdown_path

    monkeypatch.setattr(codex_integration, "export_promotion_candidates", export_candidates)

    def judge_router(request: dict[str, object]) -> dict[str, object]:
        return {
            "ok": True,
            "score": 0.94,
            "decision": "apply_flexible",
            "candidate_ids": [candidate["candidate_id"] for candidate in request["candidates"]],
            "issues": [],
            "rationale": "Both candidates describe durable ACS behavior.",
            "metadata": {"model": "judge-test"},
        }

    result = run_codex_thread_finalize_pipeline(
        thread_id="thread-wiki-merged",
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        summary_mode="heuristic",
        wiki_auto_mode="apply-flexible",
        wiki_write_judge_mode="hybrid",
        wiki_write_judge_router=judge_router,
    )

    assert result.wiki_apply_result is not None
    assert result.wiki_apply_result.dry_run is False
    assert result.wiki_apply_result.applied_patch_ids == ["thread-wiki-merged-patch-1"]
    assert result.lint_issue_count == 0
    page_text = (wiki_root / "Agent Context Substrate.md").read_text(encoding="utf-8")
    assert "run_codex_watch_once discovers due Codex threads and finalizes them." in page_text
    assert "Approved flexible wiki writes should produce lint-clean durable pages." in page_text
    assert "category: codex-runtime-insight" in page_text
    assert "[[Agent Context Substrate]]" in (wiki_root / "index.md").read_text(encoding="utf-8")
    promotion_payload = json.loads((project_root / "data" / "promotions" / "thread-wiki-merged.json").read_text(encoding="utf-8"))
    assert [candidate["status"] for candidate in promotion_payload] == ["applied", "applied"]


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
