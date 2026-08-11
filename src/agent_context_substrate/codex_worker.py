from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import os
import signal
import subprocess
import sys
import time

from .codex_hook import (
    CodexHookCommandRunnerResult,
    _append_hook_event,
    _mark_watcher_state_processed,
    _subprocess_environment,
    build_codex_stop_finalize_decision,
)
from .codex_jobs import (
    CodexJob,
    CodexJobQueue,
    decode_rollout_fingerprint,
    default_codex_jobs_path,
    encode_rollout_fingerprint,
)
from .codex_runtime_config import codex_config_digest, load_codex_runtime_config
from .codex_source import CodexThreadRecord, discover_codex_threads
from .ledger import SessionLedger
from .process_lock import InterProcessFileLock, LockTimeoutError


CodexWorkerCommandRunner = Callable[..., CodexHookCommandRunnerResult]
CODEX_FINALIZE_LOCK_BUSY_EXIT_CODE = 75
CODEX_FINALIZE_LOCK_BUSY_MARKER = "ACS_CODEX_FINALIZE_LOCK_BUSY"
_KEEP_LAST_ERROR = object()


@dataclass(frozen=True)
class CodexWorkerResult:
    lock_acquired: bool
    claimed_count: int = 0
    completed_count: int = 0
    retried_count: int = 0
    dead_letter_count: int = 0
    refreshed_count: int = 0


def default_codex_worker_status_path(project_root: Path | str) -> Path:
    return Path(project_root) / "data" / "index" / "codex_worker_status.json"


def read_codex_worker_status(project_root: Path | str) -> dict[str, Any]:
    path = default_codex_worker_status_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def run_codex_worker(
    *,
    plugin_root: Path | str,
    worker_id: str | None = None,
    max_jobs: int | None = None,
    command_runner: CodexWorkerCommandRunner | None = None,
) -> CodexWorkerResult:
    if max_jobs is not None and max_jobs <= 0:
        raise ValueError("max_jobs must be greater than zero")
    plugin_root_path = Path(plugin_root).expanduser().resolve(strict=False)
    config = load_codex_runtime_config(plugin_root_path)
    project_root = _required_path(config, "project_root")
    queue = CodexJobQueue(default_codex_jobs_path(project_root))
    worker_identity = worker_id or f"{os.getpid()}-{uuid4().hex}"
    lock_timeout = _config_float(config, "worker_lock_timeout_seconds", 5.0, minimum=0.0)
    lock = InterProcessFileLock(
        project_root / "data" / "index" / "codex_worker.lock",
        timeout_seconds=lock_timeout,
    )
    try:
        lock.acquire()
    except LockTimeoutError:
        return CodexWorkerResult(lock_acquired=False)

    counts = {
        "claimed_count": 0,
        "completed_count": 0,
        "retried_count": 0,
        "dead_letter_count": 0,
        "refreshed_count": 0,
    }
    status_path = default_codex_worker_status_path(project_root)
    try:
        _write_worker_status(
            status_path,
            worker_id=worker_identity,
            status="running",
            queue=queue,
        )
        _drain_queue(
            plugin_root=plugin_root_path,
            project_root=project_root,
            queue=queue,
            worker_id=worker_identity,
            max_jobs=max_jobs,
            command_runner=command_runner,
            counts=counts,
            status_path=status_path,
        )
        _write_worker_status(
            status_path,
            worker_id=worker_identity,
            status="idle",
            queue=queue,
        )
    except Exception as exc:
        _write_worker_status(
            status_path,
            worker_id=worker_identity,
            status="failed",
            queue=queue,
            last_error=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        lock.release()
    return CodexWorkerResult(lock_acquired=True, **counts)


def _drain_queue(
    *,
    plugin_root: Path,
    project_root: Path,
    queue: CodexJobQueue,
    worker_id: str,
    max_jobs: int | None,
    command_runner: CodexWorkerCommandRunner | None,
    counts: dict[str, int],
    status_path: Path,
) -> None:
    empty_since: float | None = None
    while max_jobs is None or counts["claimed_count"] < max_jobs:
        config = load_codex_runtime_config(plugin_root)
        lease_seconds = _config_float(config, "worker_lease_seconds", 600.0, minimum=1.0)
        job = queue.claim(worker_id=worker_id, lease_seconds=lease_seconds)
        if job is None:
            health = queue.health()
            if health.pending_count:
                _write_worker_status(
                    status_path,
                    worker_id=worker_id,
                    status="waiting-retry",
                    queue=queue,
                )
                time.sleep(_config_float(config, "worker_poll_seconds", 1.0, minimum=0.05))
                continue
            grace = _config_float(config, "worker_idle_grace_seconds", 1.0, minimum=0.0)
            if grace == 0:
                return
            empty_since = empty_since or time.monotonic()
            if time.monotonic() - empty_since >= grace:
                return
            time.sleep(min(0.1, grace))
            continue
        empty_since = None
        counts["claimed_count"] += 1
        _write_worker_status(
            status_path,
            worker_id=worker_id,
            status="processing",
            queue=queue,
            current_job_id=job.id,
            current_thread_id=job.thread_id,
        )
        outcome = _process_job(
            plugin_root=plugin_root,
            project_root=project_root,
            config=config,
            queue=queue,
            job=job,
            lease_seconds=lease_seconds,
            command_runner=command_runner,
            worker_id=worker_id,
            status_path=status_path,
        )
        counts[f"{outcome}_count"] += 1
        stored = queue.get(job.id)
        _write_worker_status(
            status_path,
            worker_id=worker_id,
            status=outcome,
            queue=queue,
            last_error=stored.last_error if outcome in {"retried", "dead_letter"} else "",
        )


def _process_job(
    *,
    plugin_root: Path,
    project_root: Path,
    config: dict[str, Any],
    queue: CodexJobQueue,
    job: CodexJob,
    lease_seconds: float,
    command_runner: CodexWorkerCommandRunner | None,
    worker_id: str,
    status_path: Path,
) -> str:
    lease_token = job.lease_token
    payload = _hook_payload(job)
    try:
        current_config = load_codex_runtime_config(plugin_root)
        _validate_runtime_config(current_config, expected_project_root=project_root)
        current_digest = codex_config_digest(current_config)
        current_thread = _find_thread(job.thread_id, current_config)
        current_fingerprint = encode_rollout_fingerprint(current_thread.fingerprint)
        if job.config_digest != current_digest or job.rollout_fingerprint != current_fingerprint:
            queue.enqueue(
                thread_id=job.thread_id,
                rollout_fingerprint=current_fingerprint,
                config_digest=current_digest,
                payload=job.payload,
            )
            if not queue.complete(job.id, lease_token):
                raise RuntimeError(f"lost lease while refreshing job {job.id}")
            _append_hook_event(
                current_config,
                payload=payload,
                status="refreshed",
                detail=f"stale queued snapshot replaced; job_id={job.id}",
            )
            return "refreshed"

        decision = build_codex_stop_finalize_decision(
            payload=payload,
            plugin_root=plugin_root,
            python_executable=str(current_config.get("python_executable") or sys.executable),
            config=current_config,
        )
        if not decision.should_finalize:
            if not queue.complete(job.id, lease_token):
                raise RuntimeError(f"lost lease while skipping job {job.id}")
            _append_hook_event(
                current_config,
                payload=payload,
                status="skipped",
                detail=f"worker skipped job_id={job.id}: {decision.skip_reason}",
            )
            return "completed"

        expected = decode_rollout_fingerprint(job.rollout_fingerprint)
        if _has_durable_completion_receipt(project_root=project_root, job=job):
            if not queue.complete(job.id, lease_token):
                raise RuntimeError(f"lost lease while accepting completion receipt for job {job.id}")
            _mark_watcher_state_processed(decision, fingerprint=expected)
            _append_hook_event(
                current_config,
                payload=payload,
                status="finalized",
                detail=f"worker recovered durable completion receipt; job_id={job.id}",
            )
            return "completed"
        _append_expected_fingerprint_args(decision.command, expected)
        decision.command.extend(
            [
                "--runtime-plugin-root",
                str(plugin_root),
                "--expected-config-digest",
                job.config_digest,
            ]
        )
        if not queue.renew(job.id, lease_token, lease_seconds=lease_seconds):
            raise RuntimeError(f"lost lease before running job {job.id}")
        timeout_seconds = _config_float(current_config, "worker_job_timeout_seconds", 600.0, minimum=1.0)
        if command_runner is None:
            result = _run_command_with_lease_heartbeat(
                decision.command,
                cwd=decision.cwd or project_root,
                env=_subprocess_environment(current_config, project_root=project_root),
                timeout_seconds=timeout_seconds,
                queue=queue,
                job=job,
                lease_seconds=lease_seconds,
                heartbeat_seconds=_config_float(
                    current_config,
                    "worker_heartbeat_seconds",
                    min(30.0, lease_seconds / 3.0),
                    minimum=0.1,
                ),
                status_path=status_path,
                worker_id=worker_id,
            )
        else:
            result = command_runner(
                decision.command,
                cwd=decision.cwd or project_root,
                timeout_seconds=timeout_seconds,
            )
        if _is_finalize_lock_contention(result):
            return _defer_lock_contention_job(
                config=current_config,
                queue=queue,
                job=job,
                lease_token=lease_token,
                payload=payload,
                result=result,
            )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            raise RuntimeError(detail)
        if not queue.renew(job.id, lease_token, lease_seconds=lease_seconds):
            raise RuntimeError(f"lost lease after running job {job.id}")
        latest_config = load_codex_runtime_config(plugin_root)
        _validate_runtime_config(latest_config, expected_project_root=project_root)
        latest_thread = _find_thread(job.thread_id, latest_config)
        latest_fingerprint = encode_rollout_fingerprint(latest_thread.fingerprint)
        latest_digest = codex_config_digest(latest_config)
        if latest_fingerprint != job.rollout_fingerprint or latest_digest != job.config_digest:
            queue.enqueue(
                thread_id=job.thread_id,
                rollout_fingerprint=latest_fingerprint,
                config_digest=latest_digest,
                payload=job.payload,
            )
            if not queue.complete(job.id, lease_token):
                raise RuntimeError(f"lost lease while refreshing completed job {job.id}")
            _append_hook_event(
                latest_config,
                payload=payload,
                status="refreshed",
                detail=f"rollout changed during finalize; newest snapshot queued; job_id={job.id}",
            )
            return "refreshed"
        if not queue.complete(job.id, lease_token):
            raise RuntimeError(f"lost lease while completing job {job.id}")
        _mark_watcher_state_processed(decision, fingerprint=expected)
        _append_hook_event(
            current_config,
            payload=payload,
            status="finalized",
            detail=f"worker completed durable job; job_id={job.id}",
        )
        return "completed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if _refresh_failed_job_if_inputs_changed(
            plugin_root=plugin_root,
            project_root=project_root,
            queue=queue,
            job=job,
            lease_token=lease_token,
            payload=payload,
        ):
            return "refreshed"
        return _transition_failed_job(
            config=config,
            queue=queue,
            job=job,
            lease_token=lease_token,
            payload=payload,
            error=error,
        )


def _refresh_failed_job_if_inputs_changed(
    *,
    plugin_root: Path,
    project_root: Path,
    queue: CodexJobQueue,
    job: CodexJob,
    lease_token: str | None,
    payload: dict[str, Any],
) -> bool:
    try:
        current_config = load_codex_runtime_config(plugin_root)
        _validate_runtime_config(current_config, expected_project_root=project_root)
        current_thread = _find_thread(job.thread_id, current_config)
        current_fingerprint = encode_rollout_fingerprint(current_thread.fingerprint)
        current_digest = codex_config_digest(current_config)
    except Exception:
        return False
    if current_fingerprint == job.rollout_fingerprint and current_digest == job.config_digest:
        return False
    queue.enqueue(
        thread_id=job.thread_id,
        rollout_fingerprint=current_fingerprint,
        config_digest=current_digest,
        payload=job.payload,
    )
    if not queue.complete(job.id, lease_token):
        return False
    _append_hook_event(
        current_config,
        payload=payload,
        status="refreshed",
        detail=f"finalize inputs changed; newest snapshot queued; job_id={job.id}",
    )
    return True


def _transition_failed_job(
    *,
    config: dict[str, Any],
    queue: CodexJobQueue,
    job: CodexJob,
    lease_token: str | None,
    payload: dict[str, Any],
    error: str,
) -> str:
    max_attempts = _config_int(config, "worker_max_attempts", 3, minimum=1)
    if job.attempt_count >= max_attempts:
        if not queue.dead_letter(job.id, lease_token, error=error):
            raise RuntimeError(f"lost lease while dead-lettering job {job.id}: {error}")
        _append_hook_event(
            config,
            payload=payload,
            status="dead-letter",
            detail=f"job_id={job.id}; attempts={job.attempt_count}; error={error}",
        )
        return "dead_letter"
    base_delay = _config_float(config, "worker_retry_base_seconds", 15.0, minimum=0.0)
    max_delay = _config_float(config, "worker_retry_max_seconds", 300.0, minimum=0.0)
    delay = min(max_delay, base_delay * (2 ** max(0, job.attempt_count - 1)))
    if not queue.retry(job.id, lease_token, error=error, delay_seconds=delay):
        raise RuntimeError(f"lost lease while retrying job {job.id}: {error}")
    _append_hook_event(
        config,
        payload=payload,
        status="retry",
        detail=f"job_id={job.id}; attempts={job.attempt_count}; retry_in={delay:g}s; error={error}",
    )
    return "retried"


def _is_finalize_lock_contention(result: CodexHookCommandRunnerResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}"
    return result.returncode == CODEX_FINALIZE_LOCK_BUSY_EXIT_CODE and CODEX_FINALIZE_LOCK_BUSY_MARKER in output


def _defer_lock_contention_job(
    *,
    config: dict[str, Any],
    queue: CodexJobQueue,
    job: CodexJob,
    lease_token: str | None,
    payload: dict[str, Any],
    result: CodexHookCommandRunnerResult,
) -> str:
    configured_delay = _config_float(
        config,
        "worker_lock_contention_retry_seconds",
        60.0,
        minimum=0.0,
    )
    delay = min(300.0, max(5.0, configured_delay))
    detail = result.stderr.strip() or result.stdout.strip() or CODEX_FINALIZE_LOCK_BUSY_MARKER
    error = f"temporary finalize lock contention: {detail}"
    if not queue.defer(job.id, lease_token, error=error, delay_seconds=delay):
        raise RuntimeError(f"lost lease while deferring lock-contended job {job.id}: {error}")
    _append_hook_event(
        config,
        payload=payload,
        status="deferred",
        detail=f"job_id={job.id}; retry_in={delay:g}s; attempt budget preserved; error={error}",
    )
    return "retried"


def _run_command_with_lease_heartbeat(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float,
    queue: CodexJobQueue,
    job: CodexJob,
    lease_seconds: float,
    heartbeat_seconds: float,
    status_path: Path,
    worker_id: str,
) -> CodexHookCommandRunnerResult:
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **popen_kwargs)
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Codex finalize job timed out after {timeout_seconds:g}s")
            try:
                stdout, stderr = process.communicate(timeout=min(heartbeat_seconds, remaining))
                return CodexHookCommandRunnerResult(returncode=process.returncode, stdout=stdout, stderr=stderr)
            except subprocess.TimeoutExpired:
                if not queue.renew(job.id, job.lease_token, lease_seconds=lease_seconds):
                    raise RuntimeError(f"lost lease while job {job.id} was running")
                _write_worker_status(
                    status_path,
                    worker_id=worker_id,
                    status="processing",
                    queue=queue,
                    current_job_id=job.id,
                    current_thread_id=job.thread_id,
                )
    except BaseException:
        try:
            _terminate_process(process)
        except Exception:
            pass
        raise


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        process.communicate()
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate()


def _find_thread(thread_id: str, config: dict[str, Any]) -> CodexThreadRecord:
    thread = next(
        (
            item
            for item in discover_codex_threads(codex_home=config.get("codex_home"), include_archived=True)
            if item.thread_id == thread_id
        ),
        None,
    )
    if thread is None:
        raise KeyError(f"Codex thread not found: {thread_id}")
    return thread


def _has_durable_completion_receipt(*, project_root: Path, job: CodexJob) -> bool:
    try:
        record = SessionLedger(project_root / "data" / "index" / "session_ledger.json").get_record(
            job.thread_id,
            "session_finalize",
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    if record is None or record.status != "completed":
        return False
    artifacts = record.artifact_paths
    if artifacts.get("rollout_fingerprint") != job.rollout_fingerprint:
        return False
    if artifacts.get("config_digest") != job.config_digest:
        return False
    recovery_path = Path(artifacts.get("recovery_json_path") or "")
    return recovery_path.is_file()


def _append_expected_fingerprint_args(command: list[str], fingerprint: dict[str, int | str]) -> None:
    command.extend(
        [
            "--expected-rollout-path",
            str(fingerprint["rollout_path"]),
            "--expected-rollout-mtime-ns",
            str(fingerprint["mtime_ns"]),
            "--expected-rollout-size",
            str(fingerprint["size"]),
        ]
    )


def _hook_payload(job: CodexJob) -> dict[str, Any]:
    return {
        "hook_event_name": "Stop",
        "session_id": job.thread_id,
        "turn_id": str(job.payload.get("turn_id") or ""),
        "cwd": str(job.payload.get("cwd") or ""),
    }


def _required_path(config: dict[str, Any], key: str) -> Path:
    value = str(config.get(key) or "").strip()
    if not value:
        raise ValueError(f"Codex runtime config is missing {key}")
    return Path(value).expanduser().resolve(strict=False)


def _validate_runtime_config(config: dict[str, Any], *, expected_project_root: Path) -> None:
    if not config:
        raise ValueError("Codex runtime config is missing or invalid")
    configured_project_root = _required_path(config, "project_root")
    if os.path.normcase(str(configured_project_root)) != os.path.normcase(str(expected_project_root)):
        raise ValueError("Codex runtime project_root changed while this worker was draining")
    if not str(config.get("codex_home") or "").strip():
        raise ValueError("Codex runtime config is missing codex_home")


def _config_float(config: dict[str, Any], key: str, default: float, *, minimum: float) -> float:
    try:
        value = float(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _config_int(config: dict[str, Any], key: str, default: int, *, minimum: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _write_worker_status(
    path: Path,
    *,
    worker_id: str,
    status: str,
    queue: CodexJobQueue,
    current_job_id: int | None = None,
    current_thread_id: str = "",
    last_error: str | object = _KEEP_LAST_ERROR,
) -> None:
    health = queue.health()
    if last_error is _KEEP_LAST_ERROR:
        try:
            previous = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        effective_last_error = str(previous.get("last_error") or "") if isinstance(previous, dict) else ""
    else:
        effective_last_error = str(last_error)
    payload = {
        "worker_id": worker_id,
        "pid": os.getpid(),
        "status": status,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "current_job_id": current_job_id,
        "current_thread_id": current_thread_id,
        "last_error": effective_last_error,
        "queue_pending_count": health.pending_count,
        "queue_dead_letter_count": health.dead_letter_count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{worker_id}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


__all__ = [
    "CodexWorkerResult",
    "codex_config_digest",
    "default_codex_worker_status_path",
    "read_codex_worker_status",
    "run_codex_worker",
]
