from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3
import sys

from ..claude_hook import default_claude_jobs_path
from ..claude_integration import run_claude_session_finalize_pipeline
from ..claude_runtime_config import default_claude_config_path, load_claude_runtime_config
from ..claude_source import claude_transcript_fingerprint, discover_claude_sessions, resolve_claude_home
from ..claude_worker import read_claude_worker_status, run_claude_worker
from ..codex_jobs import CodexJobQueue
from ..codex_runtime_config import load_codex_runtime_config
from ..codex_source import resolve_codex_home
from ..codex_wiki_root import DEFAULT_CODEX_WIKI_ROOT_TEMPLATE
from ..codex_worker import CODEX_FINALIZE_LOCK_BUSY_EXIT_CODE, CODEX_FINALIZE_LOCK_BUSY_MARKER
from ..process_lock import LockTimeoutError
from .codex import _codex_job_view, _llm_safety_from_args


# Policy keys shared with the Codex adapter; setup-claude copies them so both agents
# summarize and write the wiki the same way.
_SHARED_POLICY_KEYS = (
    "wiki_root",
    "wiki_root_source",
    "python_path_entries",
    "workspace_scope",
    "allowed_workspace_roots",
    "hook_timeout_seconds",
    "worker_job_timeout_seconds",
    "worker_lease_seconds",
    "worker_lock_timeout_seconds",
    "worker_lock_contention_retry_seconds",
    "worker_idle_grace_seconds",
    "worker_poll_seconds",
    "worker_heartbeat_seconds",
    "worker_max_attempts",
    "worker_retry_base_seconds",
    "worker_retry_max_seconds",
    "summary_mode",
    "summary_cache",
    "summary_model",
    "summary_budget",
    "summarizer_command",
    "codex_cli_command",
    "codex_timeout_seconds",
    "llm_redact",
    "llm_max_input_chars",
    "llm_allow_code_snippets",
    "llm_path_policy",
    "wiki_auto_mode",
    "wiki_write_judge_mode",
    "wiki_auto_min_score",
)


def handle_claude_finalize_command(*, args: Any) -> int:
    if args.summary_mode == "custom-command" and not args.summarizer_command:
        raise SystemExit("--summary-mode custom-command requires --summarizer-command")
    expected_values = [args.expected_transcript_path, args.expected_transcript_mtime_ns, args.expected_transcript_size]
    if any(value is not None for value in expected_values) and not all(value is not None for value in expected_values):
        raise SystemExit("expected transcript fingerprint arguments must be provided together")
    expected_fingerprint = None
    if all(value is not None for value in expected_values):
        expected_fingerprint = claude_transcript_fingerprint(
            session_id=args.session_id,
            transcript_path=args.expected_transcript_path,
            mtime_ns=args.expected_transcript_mtime_ns,
            size=args.expected_transcript_size,
        )
    try:
        result = run_claude_session_finalize_pipeline(
            session_id=args.session_id,
            transcript_path=args.transcript_path,
            claude_home=args.claude_home,
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
            expected_transcript_fingerprint=expected_fingerprint,
            expected_config_digest=args.expected_config_digest,
            runtime_config_path=args.runtime_config_path,
        )
    except LockTimeoutError as exc:
        print(f"{CODEX_FINALIZE_LOCK_BUSY_MARKER}: {exc}", file=sys.stderr)
        return CODEX_FINALIZE_LOCK_BUSY_EXIT_CODE
    print(f"raw_export_path={result.raw_export_path}")
    print(f"packet_json_path={result.packet_json_path}")
    print(f"packet_markdown_path={result.packet_markdown_path}")
    print(f"recovery_json_path={result.recovery_json_path}")
    if result.summary_unit_path is not None:
        print(f"summary_unit_path={result.summary_unit_path}")
    if result.wiki_decision_path is not None:
        print(f"wiki_decision_path={result.wiki_decision_path}")
    if result.wiki_apply_result is not None:
        print(f"wiki_apply_dry_run={result.wiki_apply_result.dry_run}")
        print(f"wiki_apply_applied_count={len(result.wiki_apply_result.applied_patch_ids)}")
    print(f"lint_issue_count={result.lint_issue_count}")
    return 0


def handle_claude_worker_command(*, args: Any) -> int:
    result = run_claude_worker(
        config_path=_config_path(args),
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


def handle_claude_status_command(*, args: Any) -> int:
    config_path = _config_path(args)
    config = load_claude_runtime_config(config_path)
    claude_home = resolve_claude_home(getattr(args, "claude_home", None) or config.get("claude_home"))
    sessions = discover_claude_sessions(claude_home=claude_home)
    print(f"claude_home={claude_home}")
    print(f"config_path={config_path}")
    print(f"config_status={'ready' if config else 'missing'}")
    print(f"trigger_strategy={config.get('trigger_strategy') or 'hook-enqueue' if config else ''}")
    project_root_value = str(config.get("project_root") or "").strip()
    if project_root_value:
        project_root = Path(project_root_value).expanduser().resolve(strict=False)
        queue_path = default_claude_jobs_path(project_root)
        print(f"job_queue_path={queue_path}")
        if queue_path.exists():
            try:
                health = CodexJobQueue(queue_path).health()
            except (OSError, sqlite3.Error) as exc:
                print(f"queue_error={type(exc).__name__}: {exc}")
            else:
                print(f"queue_pending_count={health.pending_count}")
                print(f"queue_completed_count={health.completed_count}")
                print(f"queue_dead_letter_count={health.dead_letter_count}")
        else:
            print("queue_status=not-initialized")
        worker = read_claude_worker_status(project_root)
        print(f"worker_status={worker.get('status') or 'never-run'}")
        print(f"worker_last_error={worker.get('last_error') or ''}")
    print(f"session_count={len(sessions)}")
    for session in sessions[:10]:
        print(f"session_id={session.session_id} transcript_path={session.transcript_path}")
    return 0


def handle_claude_jobs_command(*, args: Any) -> int:
    config_path = _config_path(args)
    config = load_claude_runtime_config(config_path)
    project_root_value = str(config.get("project_root") or "").strip()
    if not project_root_value:
        print(f"claude_jobs_error=config has no project_root: {config_path}")
        return 1
    queue_path = default_claude_jobs_path(Path(project_root_value).expanduser().resolve(strict=False))
    if not queue_path.exists():
        if args.jobs_action == "list":
            print("job_count=0")
            return 0
        print(f"claude_jobs_error=queue is not initialized: {queue_path}")
        return 1
    try:
        queue = CodexJobQueue(queue_path)
        if args.jobs_action == "retry":
            requeued = queue.requeue_dead_letter(args.job_id)
            print(f"job_id={args.job_id}")
            print(f"requeued={str(requeued).lower()}")
            if requeued:
                print(f"next_command=agent-context-substrate claude-worker --config \"{config_path}\"")
            return 0 if requeued else 1
        jobs = queue.list_jobs(status=args.status, limit=args.limit)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"claude_jobs_error={type(exc).__name__}: {exc}")
        return 1
    if args.json:
        print(json.dumps([_codex_job_view(job) for job in jobs], ensure_ascii=False, indent=2))
        return 0
    print(f"job_count={len(jobs)}")
    for job in jobs:
        print(
            f"job_id={job.id} session_id={job.thread_id} status={job.status} "
            f"attempts={job.attempt_count} last_error={job.last_error}"
        )
    return 0


def handle_setup_claude_command(*, args: Any) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_claude_config_path(args.claude_home)
    project_root = Path(args.project_root).expanduser().resolve(strict=False)
    config: dict[str, Any] = {}
    source = "defaults"
    if args.from_codex != "off":
        codex_home = resolve_codex_home(args.codex_home)
        codex_config = load_codex_runtime_config(codex_home / "plugins" / "agent-context-substrate")
        if codex_config:
            config.update({key: codex_config[key] for key in _SHARED_POLICY_KEYS if key in codex_config})
            source = "codex-config"
        elif args.from_codex == "on":
            print(f"setup_claude_error=no Codex ACS config under {codex_home}")
            return 1
    config.setdefault("wiki_root", DEFAULT_CODEX_WIKI_ROOT_TEMPLATE)
    config.setdefault("wiki_root_source", "default-template")
    config.setdefault("workspace_scope", "all")
    config.setdefault("summary_mode", "auto")
    config.setdefault("python_path_entries", [str(project_root / "src")])
    if args.wiki_root:
        config["wiki_root"] = args.wiki_root
        config["wiki_root_source"] = "explicit"
    config.update(
        {
            "adapter": "claude-code",
            "project_root": str(project_root),
            "claude_home": str(resolve_claude_home(args.claude_home)),
            "python_executable": args.python_executable or sys.executable,
            "trigger_strategy": "hook-enqueue",
        }
    )
    print(f"config_path={config_path}")
    print(f"config_source={source}")
    if not args.yes:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        print("dry_run=true (pass --yes to write)")
        return 0
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("written=true")
    print("next_step=install the plugin from the local marketplace (docs/CLAUDE_CODE_SETUP.md)")
    return 0


def _config_path(args: Any) -> Path:
    value = getattr(args, "config", None)
    if value:
        return Path(value).expanduser().resolve(strict=False)
    return default_claude_config_path(getattr(args, "claude_home", None)).resolve(strict=False)
