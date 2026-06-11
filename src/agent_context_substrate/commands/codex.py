from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os

from ..codex_integration import (
    run_codex_thread_finalize_pipeline,
    run_codex_watch_loop,
    run_codex_watch_once,
)
from ..codex_source import (
    codex_hook_support_status,
    codex_installed_hook_status,
    discover_codex_threads,
    resolve_codex_home,
)
from ..retrieval import expand_hit, search_knowledge
from ..summarizer_backends import LLMInputSafetyOptions


def default_wiki_root() -> str:
    return os.environ.get("WIKI_PATH") or str(Path.home() / "LLM Wiki")


def handle_codex_status_command(*, args: Any) -> int:
    codex_home = resolve_codex_home(getattr(args, "codex_home", None))
    threads = discover_codex_threads(codex_home=codex_home)
    print(f"codex_home={codex_home}")
    print(f"state_db={codex_home / 'state_5.sqlite'}")
    print(f"hook_support={codex_hook_support_status(codex_home=codex_home)}")
    print(f"hook_primary={codex_installed_hook_status(codex_home=codex_home)}")
    print("watcher_fallback=available")
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
    )
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
