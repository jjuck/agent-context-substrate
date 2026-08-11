from __future__ import annotations

from pathlib import Path
import json
import subprocess
from types import SimpleNamespace

import pytest

import agent_context_substrate.codex_worker as codex_worker_module
from agent_context_substrate.codex_hook import CodexHookCommandRunnerResult
from agent_context_substrate.codex_jobs import (
    CodexJobQueue,
    default_codex_jobs_path,
    encode_rollout_fingerprint,
)
from agent_context_substrate.codex_source import discover_codex_threads
from agent_context_substrate.codex_worker import codex_config_digest, run_codex_worker
from agent_context_substrate.ledger import SessionLedger
from agent_context_substrate.process_lock import InterProcessFileLock


def test_monitor_exception_terminates_finalize_process_tree_before_propagating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    descendants = [SimpleNamespace(running=True), SimpleNamespace(running=True)]

    class FinalizeProcess:
        pid = 8123
        returncode = None
        running = True

        def communicate(self, *, timeout: float | None = None) -> tuple[str, str]:
            events.append("communicate")
            raise subprocess.TimeoutExpired(["finalize"], timeout)

    class FailingLeaseQueue:
        def renew(self, *_args: object, **_kwargs: object) -> bool:
            events.append("renew")
            raise RuntimeError("simulated queue outage")

    process = FinalizeProcess()

    def terminate_tree(candidate: FinalizeProcess) -> None:
        events.append("terminate-tree")
        candidate.running = False
        for descendant in descendants:
            descendant.running = False

    monkeypatch.setattr(codex_worker_module.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(codex_worker_module, "_terminate_process", terminate_tree)

    job = SimpleNamespace(id=17, thread_id="thread-monitor", lease_token="lease-token")
    with pytest.raises(RuntimeError, match="simulated queue outage"):
        codex_worker_module._run_command_with_lease_heartbeat(
            ["finalize"],
            cwd=tmp_path,
            env={},
            timeout_seconds=30,
            queue=FailingLeaseQueue(),
            job=job,
            lease_seconds=60,
            heartbeat_seconds=0.1,
            status_path=tmp_path / "worker-status.json",
            worker_id="worker-1",
        )

    assert events == ["communicate", "renew", "terminate-tree"]
    assert process.running is False
    assert all(descendant.running is False for descendant in descendants)


def _write_config(
    plugin_root: Path,
    *,
    project_root: Path,
    wiki_root: Path,
    codex_home: Path,
    **overrides: object,
) -> dict[str, object]:
    config: dict[str, object] = {
        "project_root": str(project_root),
        "wiki_root": str(wiki_root),
        "codex_home": str(codex_home),
        "trigger_strategy": "hook-enqueue",
        "worker_idle_grace_seconds": 0,
        "worker_lease_seconds": 600,
        "worker_max_attempts": 3,
        "worker_retry_base_seconds": 60,
    }
    config.update(overrides)
    plugin_root.mkdir(parents=True)
    (plugin_root / "local_config.json").write_text(json.dumps(config), encoding="utf-8")
    return config


def _write_rollout(codex_home: Path, thread_id: str, text: str = "hello") -> Path:
    rollout_path = codex_home / "sessions" / f"rollout-{thread_id}.jsonl"
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    rollout_path.write_text(json.dumps({"payload": {"type": "user_message", "message": text}}) + "\n", encoding="utf-8")
    return rollout_path


def _enqueue(queue: CodexJobQueue, *, config: dict[str, object], codex_home: Path, thread_id: str) -> int:
    thread = next(
        thread
        for thread in discover_codex_threads(codex_home=codex_home, include_archived=True)
        if thread.thread_id == thread_id
    )
    job = queue.enqueue(
        thread_id=thread_id,
        rollout_fingerprint=encode_rollout_fingerprint(thread.fingerprint),
        config_digest=codex_config_digest(config),
        payload={"cwd": str(Path(str(config["project_root"]))), "turn_id": f"turn-{thread_id}"},
    )
    return job.id


def test_worker_completes_a_durable_job_with_captured_fingerprint_args(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=wiki_root,
        codex_home=codex_home,
    )
    _write_rollout(codex_home, "thread-1")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    job_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-1")
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs) -> CodexHookCommandRunnerResult:
        calls.append(command)
        return CodexHookCommandRunnerResult(returncode=0)

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner)

    assert result.completed_count == 1
    assert result.retried_count == 0
    assert queue.get(job_id).status == "completed"
    assert len(calls) == 1
    assert "--expected-rollout-path" in calls[0]
    assert "--expected-rollout-mtime-ns" in calls[0]
    assert "--expected-rollout-size" in calls[0]
    assert "--runtime-plugin-root" in calls[0]
    assert "--expected-config-digest" in calls[0]
    watcher_state = json.loads(
        (project_root / "data" / "index" / "codex_watcher_state.json").read_text(encoding="utf-8")
    )
    assert watcher_state["thread-1"]["rollout_path"].endswith("rollout-thread-1.jsonl")


def test_worker_exits_cleanly_when_another_singleton_owns_the_lock(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=tmp_path / "wiki",
        codex_home=tmp_path / "codex",
        worker_lock_timeout_seconds=0,
    )
    assert config["trigger_strategy"] == "hook-enqueue"

    with InterProcessFileLock(project_root / "data" / "index" / "codex_worker.lock"):
        result = run_codex_worker(plugin_root=plugin_root)

    assert result.lock_acquired is False
    assert result.claimed_count == 0


def test_worker_does_not_backfill_historical_rollouts_from_an_empty_queue(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_config(
        plugin_root,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        codex_home=tmp_path / "codex",
    )
    _write_rollout(tmp_path / "codex", "historical-thread")

    result = run_codex_worker(
        plugin_root=plugin_root,
        command_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    assert result.lock_acquired is True
    assert result.claimed_count == 0


def test_worker_retries_one_failure_and_continues_to_the_next_job(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=wiki_root,
        codex_home=codex_home,
    )
    _write_rollout(codex_home, "thread-fails")
    _write_rollout(codex_home, "thread-ok")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    failed_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-fails")
    ok_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-ok")

    def runner(command: list[str], **_kwargs) -> CodexHookCommandRunnerResult:
        thread_id = command[command.index("--thread-id") + 1]
        return CodexHookCommandRunnerResult(
            returncode=7 if thread_id == "thread-fails" else 0,
            stderr="boom" if thread_id == "thread-fails" else "",
        )

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner, max_jobs=2)

    assert result.completed_count == 1
    assert result.retried_count == 1
    assert queue.get(failed_id).status == "retry"
    assert queue.get(ok_id).status == "completed"


def test_worker_dead_letters_after_the_configured_attempt_budget(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=wiki_root,
        codex_home=codex_home,
        worker_max_attempts=1,
    )
    _write_rollout(codex_home, "thread-dead")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    job_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-dead")

    result = run_codex_worker(
        plugin_root=plugin_root,
        command_runner=lambda *_args, **_kwargs: CodexHookCommandRunnerResult(returncode=9, stderr="fatal"),
    )

    assert result.dead_letter_count == 1
    assert queue.get(job_id).status == "dead_letter"
    worker_status = json.loads(
        (project_root / "data" / "index" / "codex_worker_status.json").read_text(encoding="utf-8")
    )
    assert "fatal" in worker_status["last_error"]


def test_finalize_lock_contention_is_deferred_without_consuming_attempt_budget(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=tmp_path / "wiki",
        codex_home=codex_home,
        worker_max_attempts=1,
        worker_lock_contention_retry_seconds=45,
    )
    _write_rollout(codex_home, "thread-lock-busy")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    job_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-lock-busy")

    result = run_codex_worker(
        plugin_root=plugin_root,
        command_runner=lambda *_args, **_kwargs: CodexHookCommandRunnerResult(
            returncode=75,
            stderr="ACS_CODEX_FINALIZE_LOCK_BUSY: another finalize owns the writer lock",
        ),
        max_jobs=1,
    )

    stored = queue.get(job_id)
    assert result.retried_count == 1
    assert result.dead_letter_count == 0
    assert stored.status == "retry"
    assert stored.attempt_count == 0
    assert stored.available_at - stored.updated_at == pytest.approx(45.0)


def test_worker_refreshes_a_stale_snapshot_before_running_finalize(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=wiki_root,
        codex_home=codex_home,
    )
    rollout_path = _write_rollout(codex_home, "thread-stale", "first")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    stale_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-stale")
    rollout_path.write_text(rollout_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs) -> CodexHookCommandRunnerResult:
        calls.append(command)
        return CodexHookCommandRunnerResult(returncode=0)

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner)

    assert result.refreshed_count == 1
    assert result.completed_count == 1
    assert queue.get(stale_id).status == "completed"
    assert len(calls) == 1
    assert queue.health().pending_count == 0


def test_worker_requeues_when_rollout_changes_while_finalize_is_running(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=wiki_root,
        codex_home=codex_home,
    )
    rollout_path = _write_rollout(codex_home, "thread-moving", "first")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-moving")
    calls = 0

    def runner(_command: list[str], **_kwargs) -> CodexHookCommandRunnerResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            rollout_path.write_text(rollout_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return CodexHookCommandRunnerResult(returncode=0)

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner)

    assert result.refreshed_count == 1
    assert result.completed_count == 1
    assert calls == 2
    assert queue.health().pending_count == 0


def test_worker_refreshes_changed_rollout_even_when_stale_child_fails_at_attempt_limit(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=tmp_path / "wiki",
        codex_home=codex_home,
        worker_max_attempts=1,
    )
    rollout_path = _write_rollout(codex_home, "thread-stale-failure", "first")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-stale-failure")
    calls = 0

    def runner(_command: list[str], **_kwargs) -> CodexHookCommandRunnerResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            rollout_path.write_text(rollout_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            return CodexHookCommandRunnerResult(returncode=1, stderr="stale guard")
        return CodexHookCommandRunnerResult(returncode=0)

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner)

    assert result.refreshed_count == 1
    assert result.completed_count == 1
    assert result.dead_letter_count == 0
    assert calls == 2
    assert queue.health().pending_count == 0


def test_worker_never_completes_job_when_runtime_config_becomes_invalid(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=tmp_path / "wiki",
        codex_home=codex_home,
    )
    _write_rollout(codex_home, "thread-config-loss")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    job_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-config-loss")

    def runner(_command: list[str], **_kwargs) -> CodexHookCommandRunnerResult:
        (plugin_root / "local_config.json").write_text("{invalid", encoding="utf-8")
        return CodexHookCommandRunnerResult(returncode=1, stderr="config guard")

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner, max_jobs=1)

    assert result.retried_count == 1
    assert queue.get(job_id).status == "retry"
    assert queue.health().completed_count == 0


def test_worker_accepts_matching_durable_completion_receipt_after_crash(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    codex_home = tmp_path / "codex"
    config = _write_config(
        plugin_root,
        project_root=project_root,
        wiki_root=tmp_path / "wiki",
        codex_home=codex_home,
    )
    _write_rollout(codex_home, "thread-receipt")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    job_id = _enqueue(queue, config=config, codex_home=codex_home, thread_id="thread-receipt")
    job = queue.get(job_id)
    recovery_path = project_root / "data" / "exports" / "recovery" / "thread-receipt.json"
    recovery_path.parent.mkdir(parents=True)
    recovery_path.write_text("{}", encoding="utf-8")
    SessionLedger(project_root / "data" / "index" / "session_ledger.json").mark_completed(
        session_id="thread-receipt",
        pipeline="session_finalize",
        artifact_paths={
            "rollout_fingerprint": job.rollout_fingerprint,
            "config_digest": job.config_digest,
            "recovery_json_path": str(recovery_path),
        },
    )
    calls = 0

    def runner(*_args, **_kwargs) -> CodexHookCommandRunnerResult:
        nonlocal calls
        calls += 1
        return CodexHookCommandRunnerResult(returncode=0)

    result = run_codex_worker(plugin_root=plugin_root, command_runner=runner)

    assert result.completed_count == 1
    assert calls == 0
    assert queue.get(job_id).status == "completed"
