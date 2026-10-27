from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import os
import subprocess
import sys

from .claude_runtime_config import load_claude_runtime_config
from .claude_source import resolve_claude_session
from .codex_hook import (
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    CodexHookCommandRunnerResult,
    _append_summary_args,
    _append_wiki_auto_args,
    _hook_timeout_seconds,
    _resolve_non_strict,
    _run_command,
    _subprocess_environment,
    _workspace_is_allowed,
)
from .codex_jobs import CodexJob, CodexJobQueue, encode_rollout_fingerprint
from .codex_runtime_config import codex_config_digest
from .codex_wiki_root import resolve_codex_wiki_root


_CONFIG_ERRORS = {
    "missing or invalid Claude adapter config",
    "missing project_root",
    "no wiki root resolved",
}


@dataclass(frozen=True)
class ClaudeStopFinalizeDecision:
    should_finalize: bool
    command: list[str] = field(default_factory=list)
    cwd: Path | None = None
    skip_reason: str = ""
    timeout_seconds: int = DEFAULT_HOOK_TIMEOUT_SECONDS
    thread_id: str = ""
    transcript_path: Path | None = None
    project_root: Path | None = None


def default_claude_jobs_path(project_root: Path | str) -> Path:
    return Path(project_root) / "data" / "index" / "claude_jobs.sqlite3"


def default_claude_hook_event_log_path(project_root: Path | str) -> Path:
    return Path(project_root) / "data" / "index" / "claude_hook_events.jsonl"


def build_claude_stop_finalize_decision(
    *,
    payload: dict[str, Any],
    config: dict[str, Any],
    python_executable: str = sys.executable,
) -> ClaudeStopFinalizeDecision:
    if str(payload.get("hook_event_name") or "") != "Stop":
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="unsupported hook event")
    if payload.get("stop_hook_active") is True:
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="stop_hook_active")
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="missing session_id")
    if not config:
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="missing or invalid Claude adapter config")

    project_root_value = config.get("project_root")
    if not project_root_value:
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="missing project_root")
    wiki_root_resolution = resolve_codex_wiki_root(config)
    if wiki_root_resolution.path is None:
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="no wiki root resolved")

    project_root = _resolve_non_strict(Path(str(project_root_value)).expanduser())
    cwd = _resolve_non_strict(Path(str(payload.get("cwd") or project_root)).expanduser())
    if not _workspace_is_allowed(config, cwd=cwd, project_root=project_root):
        return ClaudeStopFinalizeDecision(
            should_finalize=False,
            skip_reason="cwd outside configured allowed_workspace_roots",
        )
    try:
        record = resolve_claude_session(
            session_id=session_id,
            transcript_path=str(payload.get("transcript_path") or "").strip() or None,
            claude_home=config.get("claude_home"),
        )
    except KeyError:
        return ClaudeStopFinalizeDecision(should_finalize=False, skip_reason="transcript not found")

    command = [
        python_executable,
        "-m",
        "agent_context_substrate.cli",
        "claude-finalize",
        "--session-id",
        session_id,
        "--transcript-path",
        str(record.transcript_path),
        "--project-root",
        str(project_root),
        "--wiki-root",
        str(wiki_root_resolution.path),
    ]
    _append_summary_args(command, config)
    _append_wiki_auto_args(command, config)
    return ClaudeStopFinalizeDecision(
        should_finalize=True,
        command=command,
        cwd=project_root,
        timeout_seconds=_hook_timeout_seconds(config),
        thread_id=session_id,
        transcript_path=record.transcript_path,
        project_root=project_root,
    )


def run_claude_stop_finalize_hook(
    *,
    payload: dict[str, Any],
    config_path: Path | str,
    python_executable: str = sys.executable,
    runner: Callable[..., CodexHookCommandRunnerResult] | None = None,
) -> dict[str, Any]:
    # A Stop hook re-entered after another hook continued the turn must stay inert.
    if payload.get("stop_hook_active") is True:
        return {}
    config_path = Path(config_path).expanduser()
    config = load_claude_runtime_config(config_path)
    decision = build_claude_stop_finalize_decision(
        payload=payload,
        config=config,
        python_executable=python_executable,
    )
    if not decision.should_finalize:
        append_claude_hook_event(config, payload=payload, status="skipped", detail=decision.skip_reason)
        if decision.skip_reason in _CONFIG_ERRORS:
            return _non_blocking_failure(f"ACS Claude hook configuration error: {decision.skip_reason}")
        return _ok()

    trigger_strategy = str(config.get("trigger_strategy") or "hook-enqueue").strip().lower()
    if trigger_strategy == "hook-enqueue":
        try:
            job = enqueue_claude_stop_job(config=config, payload=payload, decision=decision)
            append_claude_hook_event(
                config,
                payload=payload,
                status="enqueued",
                detail=f"durable Claude finalize job queued; job_id={job.id}",
            )
            _start_claude_worker(config_path=config_path, python_executable=python_executable, config=config)
        except Exception as exc:
            message = f"ACS Claude enqueue hook failed: {exc}"
            append_claude_hook_event(config, payload=payload, status="failed", detail=message)
            return _non_blocking_failure(message)
        return _ok()
    if trigger_strategy != "hook-primary":
        message = f"ACS Claude hook has unsupported trigger_strategy={trigger_strategy!r}"
        append_claude_hook_event(config, payload=payload, status="failed", detail=message)
        return _non_blocking_failure(message)

    try:
        if runner is None:
            result = _run_command(
                decision.command,
                cwd=decision.cwd or Path.cwd(),
                timeout_seconds=decision.timeout_seconds,
                env=_subprocess_environment(config, project_root=decision.project_root or Path.cwd()),
            )
        else:
            result = runner(decision.command, cwd=decision.cwd or Path.cwd(), timeout_seconds=decision.timeout_seconds)
    except Exception as exc:
        message = f"ACS Claude finalize hook failed: {exc}"
        append_claude_hook_event(config, payload=payload, status="failed", detail=message)
        return _non_blocking_failure(message)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        message = f"ACS Claude finalize hook failed: {detail}"
        append_claude_hook_event(config, payload=payload, status="failed", detail=message)
        return _non_blocking_failure(message)
    append_claude_hook_event(config, payload=payload, status="finalized", detail="claude-finalize completed")
    return _ok()


def enqueue_claude_stop_job(
    *,
    config: dict[str, Any],
    payload: dict[str, Any],
    decision: ClaudeStopFinalizeDecision,
) -> CodexJob:
    if decision.project_root is None or decision.transcript_path is None or not decision.thread_id:
        raise ValueError("enqueue decision is missing project_root, transcript_path, or session_id")
    record = resolve_claude_session(session_id=decision.thread_id, transcript_path=decision.transcript_path)
    queue = CodexJobQueue(default_claude_jobs_path(decision.project_root))
    return queue.enqueue(
        thread_id=decision.thread_id,
        rollout_fingerprint=encode_rollout_fingerprint(record.fingerprint),
        config_digest=codex_config_digest(config),
        payload={
            "transcript_path": str(record.transcript_path),
            "cwd": str(payload.get("cwd") or ""),
        },
    )


def append_claude_hook_event(
    config: dict[str, Any],
    *,
    payload: dict[str, Any],
    status: str,
    detail: str,
) -> None:
    try:
        project_root_value = config.get("project_root")
        if not project_root_value:
            return
        project_root = _resolve_non_strict(Path(str(project_root_value)).expanduser())
        configured_log_path = config.get("claude_hook_event_log_path")
        log_path = (
            _resolve_non_strict(Path(str(configured_log_path)).expanduser())
            if configured_log_path
            else default_claude_hook_event_log_path(project_root)
        )
        wiki_root_resolution = resolve_codex_wiki_root(config)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "detail": detail,
            "hook_event_name": str(payload.get("hook_event_name") or ""),
            "session_id": str(payload.get("session_id") or ""),
            "transcript_path": str(payload.get("transcript_path") or ""),
            "cwd": str(payload.get("cwd") or ""),
            "wiki_root_source": wiki_root_resolution.source,
            "wiki_root_effective": str(wiki_root_resolution.path or ""),
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        return


def _start_claude_worker(*, config_path: Path, python_executable: str, config: dict[str, Any]) -> None:
    project_root = _resolve_non_strict(Path(str(config["project_root"])).expanduser())
    command = [
        python_executable,
        "-m",
        "agent_context_substrate.cli",
        "claude-worker",
        "--config",
        str(config_path),
    ]
    kwargs: dict[str, Any] = {
        "cwd": str(project_root),
        "env": _subprocess_environment(config, project_root=project_root),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def _ok() -> dict[str, Any]:
    return {"continue": True, "suppressOutput": True}


def _non_blocking_failure(message: str) -> dict[str, Any]:
    # Claude Code shows systemMessage as a warning; never emit decision=block from this hook.
    return {
        "continue": True,
        "suppressOutput": True,
        "systemMessage": f"{message}. Run `agent-context-substrate claude-status` to inspect the queue.",
    }
