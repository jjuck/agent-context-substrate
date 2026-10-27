from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import sys

from .claude_hook import (
    ClaudeStopFinalizeDecision,
    append_claude_hook_event,
    build_claude_stop_finalize_decision,
    default_claude_jobs_path,
)
from .claude_runtime_config import load_claude_runtime_config
from .claude_source import resolve_claude_session
from .codex_jobs import CodexJob
from .codex_worker import (
    CodexWorkerCommandRunner,
    CodexWorkerResult,
    DurableWorkerAdapter,
    _required_path,
    run_durable_worker,
)


def default_claude_worker_status_path(project_root: Path | str) -> Path:
    return Path(project_root) / "data" / "index" / "claude_worker_status.json"


def read_claude_worker_status(project_root: Path | str) -> dict[str, Any]:
    path = default_claude_worker_status_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def run_claude_worker(
    *,
    config_path: Path | str,
    worker_id: str | None = None,
    max_jobs: int | None = None,
    command_runner: CodexWorkerCommandRunner | None = None,
) -> CodexWorkerResult:
    return run_durable_worker(
        adapter=claude_worker_adapter(Path(config_path).expanduser().resolve(strict=False)),
        worker_id=worker_id,
        max_jobs=max_jobs,
        command_runner=command_runner,
    )


def claude_worker_adapter(config_path: Path) -> DurableWorkerAdapter:
    def build_decision(payload: dict[str, Any], config: dict[str, Any]) -> ClaudeStopFinalizeDecision:
        return build_claude_stop_finalize_decision(
            payload=payload,
            config=config,
            python_executable=str(config.get("python_executable") or sys.executable),
        )

    def current_fingerprint(job: CodexJob, config: dict[str, Any]) -> dict[str, int | str]:
        return resolve_claude_session(
            session_id=job.thread_id,
            transcript_path=str(job.payload.get("transcript_path") or "") or None,
            claude_home=config.get("claude_home"),
        ).fingerprint

    def finalize_args(job: CodexJob, expected: dict[str, int | str]) -> list[str]:
        return [
            "--expected-transcript-path",
            str(expected["rollout_path"]),
            "--expected-transcript-mtime-ns",
            str(expected["mtime_ns"]),
            "--expected-transcript-size",
            str(expected["size"]),
            "--runtime-config-path",
            str(config_path),
            "--expected-config-digest",
            job.config_digest,
        ]

    return DurableWorkerAdapter(
        label="Claude",
        jobs_path=default_claude_jobs_path,
        lock_path=lambda project_root: project_root / "data" / "index" / "claude_worker.lock",
        status_path=default_claude_worker_status_path,
        load_config=lambda: load_claude_runtime_config(config_path),
        validate_config=_validate_runtime_config,
        current_fingerprint=current_fingerprint,
        build_decision=build_decision,
        hook_payload=_hook_payload,
        append_event=lambda config, **kwargs: append_claude_hook_event(config, **kwargs),
        # Claude has no history watcher, so there is no processed-state to update.
        mark_processed=lambda _decision, **_kwargs: None,
        finalize_args=finalize_args,
    )


def _hook_payload(job: CodexJob) -> dict[str, Any]:
    return {
        "hook_event_name": "Stop",
        "session_id": job.thread_id,
        "transcript_path": str(job.payload.get("transcript_path") or ""),
        "cwd": str(job.payload.get("cwd") or ""),
        "stop_hook_active": False,
    }


def _validate_runtime_config(config: dict[str, Any], expected_project_root: Path) -> None:
    if not config:
        raise ValueError("Claude adapter config is missing or invalid")
    configured_project_root = _required_path(config, "project_root")
    if os.path.normcase(str(configured_project_root)) != os.path.normcase(str(expected_project_root)):
        raise ValueError("Claude adapter project_root changed while this worker was draining")


__all__ = [
    "claude_worker_adapter",
    "default_claude_worker_status_path",
    "read_claude_worker_status",
    "run_claude_worker",
]
