from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import sqlite3
import sys

from ..codex_integration import (
    run_codex_thread_finalize_pipeline,
    run_codex_watch_loop,
    run_codex_watch_once,
)
from ..codex_jobs import CodexJob, CodexJobQueue, default_codex_jobs_path
from ..codex_runtime_config import load_codex_runtime_config
from ..codex_source import (
    codex_hook_support_status,
    codex_installed_hook_status,
    discover_codex_threads,
    resolve_codex_home,
)
from ..retrieval import expand_hit, search_knowledge
from ..summarizer_backends import LLMInputSafetyOptions
from ..codex_worker import (
    CODEX_FINALIZE_LOCK_BUSY_EXIT_CODE,
    CODEX_FINALIZE_LOCK_BUSY_MARKER,
    read_codex_worker_status,
    run_codex_worker,
)
from ..process_lock import LockTimeoutError


def default_wiki_root() -> str:
    return os.environ.get("WIKI_PATH") or str(Path.home() / "LLM Wiki")


def handle_codex_status_command(*, args: Any) -> int:
    codex_home = resolve_codex_home(getattr(args, "codex_home", None))
    threads = discover_codex_threads(codex_home=codex_home)
    plugin_root = codex_home / "plugins" / "agent-context-substrate"
    config = load_codex_runtime_config(plugin_root)
    print(f"codex_home={codex_home}")
    print(f"state_db={codex_home / 'state_5.sqlite'}")
    print(f"hook_support={codex_hook_support_status(codex_home=codex_home)}")
    print(f"hook_primary={codex_installed_hook_status(codex_home=codex_home)}")
    print("watcher_fallback=available")
    _print_codex_async_status(config)
    print(f"thread_count={len(threads)}")
    for thread in threads[:10]:
        print(
            " ".join(
                [
                    f"thread_id={thread.thread_id}",
                    f"title={thread.title or ''}",
                    f"rollout_path={thread.rollout_path}",
                ]
            )
        )
    return 0


def handle_codex_finalize_command(*, args: Any) -> int:
    if args.summary_mode == "custom-command" and not args.summarizer_command:
        raise SystemExit("--summary-mode custom-command requires --summarizer-command")
    expected_values = [args.expected_rollout_path, args.expected_rollout_mtime_ns, args.expected_rollout_size]
    if any(value is not None for value in expected_values) and not all(value is not None for value in expected_values):
        raise SystemExit("expected rollout fingerprint arguments must be provided together")
    expected_fingerprint = None
    if all(value is not None for value in expected_values):
        expected_fingerprint = {
            "thread_id": args.thread_id,
            "rollout_path": args.expected_rollout_path,
            "mtime_ns": args.expected_rollout_mtime_ns,
            "size": args.expected_rollout_size,
        }
    try:
        result = run_codex_thread_finalize_pipeline(
            thread_id=args.thread_id,
            codex_home=args.codex_home,
            project_root=args.project_root,
            wiki_root=args.wiki_root,
            task_title=args.task_title,
            unit_title=args.unit_title,
            goal=args.goal,
            related_pages=list(args.related_pages),
            max_tool_output_chars=args.max_tool_output_chars,
            summary_mode=args.summary_mode,
            summarizer_command=args.summarizer_command,
            summary_model=args.summary_model,
            summary_budget=args.summary_budget,
            summary_cache=args.summary_cache == "on",
            codex_cli_command=args.codex_cli_command,
            codex_timeout_seconds=args.codex_timeout_seconds,
            llm_safety=_llm_safety_from_args(args),
            wiki_auto_mode=args.wiki_auto_mode,
            wiki_write_judge_mode=args.wiki_write_judge_mode,
            wiki_auto_min_score=args.wiki_auto_min_score,
            expected_rollout_fingerprint=expected_fingerprint,
            expected_config_digest=args.expected_config_digest,
            runtime_plugin_root=args.runtime_plugin_root,
        )
    except LockTimeoutError as exc:
        print(f"{CODEX_FINALIZE_LOCK_BUSY_MARKER}: {exc}", file=sys.stderr)
        return CODEX_FINALIZE_LOCK_BUSY_EXIT_CODE
    print(f"raw_export_path={result.raw_export_path}")
    print(f"packet_json_path={result.packet_json_path}")
    print(f"packet_markdown_path={result.packet_markdown_path}")
    print(f"recovery_json_path={result.recovery_json_path}")
    if result.summary_micro_path is not None:
        print(f"summary_micro_path={result.summary_micro_path}")
    if result.summary_unit_path is not None:
        print(f"summary_unit_path={result.summary_unit_path}")
    if result.summary_evidence_path is not None:
        print(f"summary_evidence_path={result.summary_evidence_path}")
    if result.wiki_decision_path is not None:
        print(f"wiki_decision_path={result.wiki_decision_path}")
    if result.wiki_patch_path is not None:
        print(f"wiki_patch_path={result.wiki_patch_path}")
    if result.wiki_patch_markdown_path is not None:
        print(f"wiki_patch_markdown_path={result.wiki_patch_markdown_path}")
    if result.wiki_apply_result is not None:
        print(f"wiki_apply_dry_run={result.wiki_apply_result.dry_run}")
        print(f"wiki_apply_applied_count={len(result.wiki_apply_result.applied_patch_ids)}")
    print(f"lint_issue_count={result.lint_issue_count}")
    return 0


def handle_codex_worker_command(*, args: Any) -> int:
    result = run_codex_worker(
        plugin_root=args.plugin_root,
        worker_id=args.worker_id,
        max_jobs=args.max_jobs,
    )
    print(f"worker_lock_acquired={str(result.lock_acquired).lower()}")
    print(f"claimed_count={result.claimed_count}")
    print(f"completed_count={result.completed_count}")
    print(f"retried_count={result.retried_count}")
    print(f"dead_letter_count={result.dead_letter_count}")
    print(f"refreshed_count={result.refreshed_count}")
    return 0


def handle_codex_jobs_command(*, args: Any) -> int:
    codex_home = resolve_codex_home(getattr(args, "codex_home", None))
    plugin_root = codex_home / "plugins" / "agent-context-substrate"
    config = load_codex_runtime_config(plugin_root)
    project_root_value = str(config.get("project_root") or "").strip()
    if not project_root_value:
        print("codex_jobs_error=installed config has no project_root")
        return 1
    queue_path = default_codex_jobs_path(Path(project_root_value).expanduser().resolve(strict=False))
    if not queue_path.exists():
        if args.jobs_action == "list":
            print("job_count=0")
            return 0
        print(f"codex_jobs_error=queue is not initialized: {queue_path}")
        return 1
    try:
        queue = CodexJobQueue(queue_path)
        if args.jobs_action == "retry":
            requeued = queue.requeue_dead_letter(args.job_id)
            print(f"job_id={args.job_id}")
            print(f"requeued={str(requeued).lower()}")
            if requeued:
                print(f"next_command=agent-context-substrate codex-worker --plugin-root {plugin_root}")
            return 0 if requeued else 1
        jobs = queue.list_jobs(status=args.status, limit=args.limit)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"codex_jobs_error={type(exc).__name__}: {exc}")
        return 1
    if args.json:
        print(json.dumps([_codex_job_view(job) for job in jobs], ensure_ascii=False, indent=2))
    else:
        print(f"job_count={len(jobs)}")
        for job in jobs:
            print(
                " ".join(
                    [
                        f"job_id={job.id}",
                        f"thread_id={job.thread_id}",
                        f"status={job.status}",
                        f"attempts={job.attempt_count}",
                        f"last_error={job.last_error}",
                    ]
                )
            )
    return 0


def handle_codex_watch_command(*, args: Any) -> int:
    if args.summary_mode == "custom-command" and not args.summarizer_command:
        raise SystemExit("--summary-mode custom-command requires --summarizer-command")
    if args.once:
        result = run_codex_watch_once(
            codex_home=args.codex_home,
            project_root=args.project_root,
            wiki_root=args.wiki_root,
            idle_seconds=args.idle_seconds,
            state_path=args.state_path,
            max_tool_output_chars=args.max_tool_output_chars,
            summary_mode=args.summary_mode,
            summarizer_command=args.summarizer_command,
            summary_model=args.summary_model,
            summary_budget=args.summary_budget,
            summary_cache=args.summary_cache == "on",
            codex_cli_command=args.codex_cli_command,
            codex_timeout_seconds=args.codex_timeout_seconds,
            llm_safety=_llm_safety_from_args(args),
            wiki_auto_mode=args.wiki_auto_mode,
            wiki_write_judge_mode=args.wiki_write_judge_mode,
            wiki_auto_min_score=args.wiki_auto_min_score,
        )
        print(f"processed={len(result.processed_thread_ids)}")
        for thread_id in result.processed_thread_ids:
            print(f"thread_id={thread_id}")
        return 0
    try:
        run_codex_watch_loop(
            codex_home=args.codex_home,
            project_root=args.project_root,
            wiki_root=args.wiki_root,
            interval_seconds=args.interval_seconds,
            idle_seconds=args.idle_seconds,
            state_path=args.state_path,
            max_tool_output_chars=args.max_tool_output_chars,
            summary_mode=args.summary_mode,
            summarizer_command=args.summarizer_command,
            summary_model=args.summary_model,
            summary_budget=args.summary_budget,
            summary_cache=args.summary_cache == "on",
            codex_cli_command=args.codex_cli_command,
            codex_timeout_seconds=args.codex_timeout_seconds,
            llm_safety=_llm_safety_from_args(args),
            wiki_auto_mode=args.wiki_auto_mode,
            wiki_write_judge_mode=args.wiki_write_judge_mode,
            wiki_auto_min_score=args.wiki_auto_min_score,
        )
    except KeyboardInterrupt:
        print("codex-watch stopped")
    return 0


def _llm_safety_from_args(args: Any) -> LLMInputSafetyOptions:
    return LLMInputSafetyOptions(
        redact=getattr(args, "llm_redact", "on") == "on",
        max_input_chars=getattr(args, "llm_max_input_chars", 12_000),
        allow_code_snippets=getattr(args, "llm_allow_code_snippets", "off") == "on",
        path_policy=getattr(args, "llm_path_policy", "redact"),
    )


def _codex_job_view(job: CodexJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "thread_id": job.thread_id,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "available_at": job.available_at,
        "last_error": job.last_error,
        "payload": job.payload,
    }


def _print_codex_async_status(config: dict[str, Any]) -> None:
    trigger_strategy = str(config.get("trigger_strategy") or "unknown")
    print(f"trigger_strategy={trigger_strategy}")
    project_root_value = str(config.get("project_root") or "").strip()
    if not project_root_value:
        print("job_queue_path=")
        print("queue_status=not-configured")
        print("worker_status=not-configured")
        return
    project_root = Path(project_root_value).expanduser().resolve(strict=False)
    queue_path = default_codex_jobs_path(project_root)
    print(f"job_queue_path={queue_path}")
    if queue_path.exists():
        try:
            health = CodexJobQueue(queue_path).health()
        except (OSError, sqlite3.Error) as exc:
            print("queue_status=error")
            print(f"queue_error={type(exc).__name__}: {exc}")
        else:
            print("queue_status=ready")
            print(f"queue_pending_count={health.pending_count}")
            print(f"queue_queued_count={health.queued_count}")
            print(f"queue_leased_count={health.leased_count}")
            print(f"queue_retry_count={health.retry_count}")
            print(f"queue_dead_letter_count={health.dead_letter_count}")
            oldest = "" if health.oldest_pending_age_seconds is None else f"{health.oldest_pending_age_seconds:.1f}"
            print(f"queue_oldest_pending_age_seconds={oldest}")
    else:
        print("queue_status=not-initialized")
        print("queue_pending_count=0")
        print("queue_queued_count=0")
        print("queue_leased_count=0")
        print("queue_retry_count=0")
        print("queue_dead_letter_count=0")
        print("queue_oldest_pending_age_seconds=")
    worker = read_codex_worker_status(project_root)
    print(f"worker_status={worker.get('status') or 'not-started'}")
    print(f"worker_heartbeat_age_seconds={_heartbeat_age_seconds(worker.get('heartbeat_at'))}")
    print(f"worker_last_error={worker.get('last_error') or ''}")


def _heartbeat_age_seconds(value: object) -> str:
    try:
        timestamp = datetime.fromisoformat(str(value))
    except ValueError:
        return ""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return f"{max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds()):.1f}"


def handle_search_knowledge_command(*, args: Any) -> int:
    hits = search_knowledge(
        args.query,
        project_root=Path(args.project_root).expanduser(),
        wiki_root=Path(args.wiki_root).expanduser(),
        limit=args.limit,
        include_raw=args.include_raw,
        mode=args.mode,
        graph_depth=args.graph_depth,
    )
    if args.json:
        print(json.dumps([hit.to_dict() for hit in hits], ensure_ascii=False, indent=2))
        return 0
    for hit in hits:
        print(
            " ".join(
                [
                    f"hit_id={hit.hit_id}",
                    f"source={hit.source_type}",
                    f"score={hit.score:.3f}",
                    f"title={hit.title}",
                ]
            )
        )
        print(hit.snippet)
        if hit.provenance:
            print("provenance=" + ", ".join(hit.provenance))
    return 0


def handle_expand_hit_command(*, args: Any) -> int:
    detail = expand_hit(
        args.hit_id,
        project_root=Path(args.project_root).expanduser(),
        wiki_root=Path(args.wiki_root).expanduser(),
    )
    if args.json:
        print(json.dumps(detail.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(detail.content)
    return 0
