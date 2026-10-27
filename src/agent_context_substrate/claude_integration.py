from __future__ import annotations

from pathlib import Path
from typing import Callable

from .claude_runtime_config import load_claude_runtime_config
from .claude_source import (
    build_claude_session_bundle,
    export_claude_session_bundle,
    resolve_claude_session,
)
from .codex_integration import _run_codex_thread_finalize_pipeline_unlocked, _same_rollout_fingerprint
from .codex_runtime_config import codex_config_digest
from .integration import IntegrationResult
from .llm_runtime import AgentLLMRouter, LLMInputSafetyOptions
from .process_lock import InterProcessFileLock
from .session_bundle import SessionBundle


class ClaudeSessionChangedError(RuntimeError):
    """Raised when a queued Claude transcript is no longer the captured snapshot."""


class ClaudeConfigChangedError(RuntimeError):
    """Raised when the Claude adapter config changes during finalization."""


def current_claude_transcript_fingerprint(
    *,
    session_id: str,
    transcript_path: Path | str | None = None,
    claude_home: Path | str | None = None,
) -> dict[str, int | str] | None:
    try:
        return resolve_claude_session(
            session_id=session_id,
            transcript_path=transcript_path,
            claude_home=claude_home,
        ).fingerprint
    except (KeyError, OSError):
        return None


def run_claude_session_finalize_pipeline(
    *,
    session_id: str,
    transcript_path: Path | str | None = None,
    claude_home: Path | str | None = None,
    project_root: Path | str,
    wiki_root: Path | str,
    task_title: str | None = None,
    unit_title: str | None = None,
    goal: str | None = None,
    related_pages: list[str] | None = None,
    max_tool_output_chars: int = 12_000,
    summary_mode: str | None = None,
    summarizer_command: str | None = None,
    summary_model: str | None = None,
    summary_budget: str | None = None,
    summary_cache: bool = False,
    codex_cli_command: Path | str | None = None,
    codex_timeout_seconds: int | None = None,
    llm_safety: LLMInputSafetyOptions | None = None,
    wiki_auto_mode: str = "off",
    wiki_write_judge_mode: str = "off",
    wiki_auto_min_score: float = 0.85,
    wiki_write_judge_router: AgentLLMRouter | None = None,
    expected_transcript_fingerprint: dict[str, int | str] | None = None,
    expected_config_digest: str | None = None,
    runtime_config_path: Path | str | None = None,
    finalize_lock_timeout_seconds: float = 30.0,
) -> IntegrationResult:
    project_root_path = Path(project_root).resolve()
    record = resolve_claude_session(session_id=session_id, transcript_path=transcript_path, claude_home=claude_home)
    captured_fingerprint = expected_transcript_fingerprint or record.fingerprint
    if bool(expected_config_digest) != bool(runtime_config_path):
        raise ValueError("expected_config_digest and runtime_config_path must be provided together")

    def ensure_fresh_inputs() -> None:
        current = current_claude_transcript_fingerprint(session_id=session_id, transcript_path=record.transcript_path)
        if current is None or not _same_rollout_fingerprint(current, captured_fingerprint):
            raise ClaudeSessionChangedError(f"Claude session changed after it was queued: {session_id}")
        if expected_config_digest is not None and runtime_config_path is not None:
            current_digest = codex_config_digest(load_claude_runtime_config(runtime_config_path))
            if current_digest != expected_config_digest:
                raise ClaudeConfigChangedError("Claude adapter runtime config changed during finalization")

    def load_session(artifact_root: Path) -> tuple[SessionBundle, Path]:
        bundle = build_claude_session_bundle(
            session_id=session_id,
            transcript_path=record.transcript_path,
            max_tool_output_chars=max_tool_output_chars,
        )
        return bundle, export_claude_session_bundle(bundle=bundle, project_root=artifact_root)

    freshness_guard: Callable[[], None] = ensure_fresh_inputs
    # Shares the Codex finalize lock so only one adapter writes the wiki at a time.
    lock_path = project_root_path / "data" / "index" / "codex_finalize.lock"
    with InterProcessFileLock(lock_path, timeout_seconds=finalize_lock_timeout_seconds):
        return _run_codex_thread_finalize_pipeline_unlocked(
            thread_id=session_id,
            codex_home=None,
            project_root=project_root_path,
            wiki_root=wiki_root,
            task_title=task_title,
            unit_title=unit_title,
            goal=goal,
            related_pages=related_pages,
            max_tool_output_chars=max_tool_output_chars,
            summary_mode=summary_mode,
            summarizer_command=summarizer_command,
            summary_model=summary_model,
            summary_budget=summary_budget,
            summary_cache=summary_cache,
            codex_cli_command=codex_cli_command,
            codex_timeout_seconds=codex_timeout_seconds,
            llm_safety=llm_safety,
            wiki_auto_mode=wiki_auto_mode,
            wiki_write_judge_mode=wiki_write_judge_mode,
            wiki_auto_min_score=wiki_auto_min_score,
            wiki_write_judge_router=wiki_write_judge_router,
            freshness_guard=freshness_guard,
            source_fingerprint=captured_fingerprint,
            config_digest=expected_config_digest,
            session_loader=load_session,
            macro_context=f"Recover Claude Code session {session_id} without replaying the full raw transcript.",
        )
