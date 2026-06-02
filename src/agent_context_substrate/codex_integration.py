from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import time

from .codex_source import (
    CodexThreadRecord,
    build_codex_session_bundle,
    discover_codex_threads,
    export_codex_session_bundle,
    resolve_codex_home,
)
from .context_packet import build_context_packet, export_context_packet
from .integration import IntegrationResult, _lint_issue_count
from .ledger import SessionLedger
from .lint import export_lint_report, lint_wiki
from .naming import derive_goal, derive_task_title, derive_unit_title
from .paths import HarnessPaths
from .recovery import build_recovery_brief
from .summarizer import build_micro_summary, build_unit_summary


@dataclass(frozen=True)
class CodexWatchResult:
    processed_thread_ids: list[str]
    results: list[IntegrationResult]


class CodexWatcherState:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def mark_processed(self, thread: CodexThreadRecord, *, fingerprint: dict[str, int | str] | None = None) -> None:
        payload = self.read()
        processed_fingerprint = fingerprint or thread.fingerprint
        payload[thread.thread_id] = {
            **processed_fingerprint,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_processed(self, thread: CodexThreadRecord) -> bool:
        entry = self.read().get(thread.thread_id)
        if not isinstance(entry, dict):
            return False
        fingerprint = thread.fingerprint
        return (
            str(entry.get("rollout_path")) == str(fingerprint["rollout_path"])
            and int(entry.get("mtime_ns", -1)) == int(fingerprint["mtime_ns"])
            and int(entry.get("size", -1)) == int(fingerprint["size"])
        )


def default_codex_watcher_state_path(project_root: Path | str) -> Path:
    return Path(project_root) / "data" / "index" / "codex_watcher_state.json"


def discover_due_codex_threads(
    *,
    codex_home: Path | str | None = None,
    state: CodexWatcherState,
    idle_seconds: int,
    now: float | None = None,
) -> list[CodexThreadRecord]:
    current_time = time.time() if now is None else now
    due: list[CodexThreadRecord] = []
    for thread in discover_codex_threads(codex_home=codex_home):
        if state.is_processed(thread):
            continue
        try:
            modified_at = thread.rollout_path.stat().st_mtime
        except OSError:
            continue
        if current_time - modified_at >= idle_seconds:
            due.append(thread)
    return due


def run_codex_thread_finalize_pipeline(
    *,
    thread_id: str,
    codex_home: Path | str | None = None,
    project_root: Path | str,
    wiki_root: Path | str,
    task_title: str | None = None,
    unit_title: str | None = None,
    goal: str | None = None,
    related_pages: list[str] | None = None,
    max_tool_output_chars: int = 12_000,
) -> IntegrationResult:
    related_pages = list(related_pages or [])
    codex_home_path = resolve_codex_home(codex_home)
    with _temporary_wiki_root(Path(wiki_root)):
        paths = HarnessPaths(project_root=Path(project_root).resolve())
        paths.ensure_project_dirs()
        ledger = SessionLedger(paths.index_dir / "session_ledger.json")
        packet_id = thread_id
        partial_artifact_paths: dict[str, str] = {}
        try:
            session_bundle = build_codex_session_bundle(
                thread_id=thread_id,
                codex_home=codex_home_path,
                max_tool_output_chars=max_tool_output_chars,
            )
            raw_export_path = export_codex_session_bundle(bundle=session_bundle, project_root=paths.project_root)
            resolved_task_title = task_title or derive_task_title(session_bundle=session_bundle, session_id=thread_id)
            resolved_unit_title = unit_title or derive_unit_title(
                session_bundle=session_bundle,
                task_title=resolved_task_title,
            )
            unit_id = f"{packet_id}-unit-1"
            micro_summary = build_micro_summary(
                session_bundle=session_bundle,
                micro_id=f"{packet_id}-micro-1",
                parent_unit_id=unit_id,
            )
            resolved_goal = goal or derive_goal(resolved_task_title, micro_summary)
            unit_summary = build_unit_summary(
                unit_id=unit_id,
                session_id=thread_id,
                title=resolved_unit_title,
                goal=resolved_goal,
                micro_summaries=[micro_summary],
                related_pages=related_pages,
            )
            packet = build_context_packet(
                packet_id=packet_id,
                task_title=resolved_task_title,
                macro_context=f"Recover Codex thread {thread_id} without replaying the full raw transcript.",
                unit_summary=unit_summary,
                micro_summaries=[micro_summary],
            )
            packet_json_path, packet_markdown_path = export_context_packet(packet=packet, paths=paths)
            lint_report = lint_wiki(paths)
            lint_json_path, lint_markdown_path = export_lint_report(
                report=lint_report,
                paths=paths,
                report_id=f"{packet_id}-lint",
            )
            artifact_paths = {
                "promotion_mode": "packet-only",
                "summary_mode": "",
                "summary_judge_mode": "off",
                "raw_export_path": str(raw_export_path),
                "packet_json_path": str(packet_json_path),
                "packet_markdown_path": str(packet_markdown_path),
                "lint_json_path": str(lint_json_path),
                "lint_markdown_path": str(lint_markdown_path),
            }
            partial_artifact_paths = dict(artifact_paths)
            lint_issue_count = _lint_issue_count(lint_report)
            ledger.mark_completed(
                session_id=thread_id,
                pipeline="session_finalize",
                artifact_paths=artifact_paths,
                issue_count=lint_issue_count,
            )
            recovery_brief = build_recovery_brief(
                session_id=thread_id,
                project_root=paths.project_root,
                wiki_root=Path(wiki_root),
            )
            artifact_paths["recovery_json_path"] = str(recovery_brief.recovery_json_path)
            ledger.mark_completed(
                session_id=thread_id,
                pipeline="session_finalize",
                artifact_paths=artifact_paths,
                issue_count=lint_issue_count,
            )
            return IntegrationResult(
                session_id=thread_id,
                packet_id=packet_id,
                raw_export_path=raw_export_path,
                packet_json_path=packet_json_path,
                packet_markdown_path=packet_markdown_path,
                promoted_paths={},
                lint_json_path=lint_json_path,
                lint_markdown_path=lint_markdown_path,
                recovery_json_path=recovery_brief.recovery_json_path,
                lint_issue_count=lint_issue_count,
                skipped=False,
            )
        except Exception as exc:
            ledger.mark_failed(
                session_id=thread_id,
                pipeline="session_finalize",
                error=f"{type(exc).__name__}: {exc}",
                artifact_paths=partial_artifact_paths,
            )
            raise


def run_codex_watch_once(
    *,
    codex_home: Path | str | None,
    project_root: Path | str,
    wiki_root: Path | str,
    idle_seconds: int,
    state_path: Path | str | None = None,
    max_tool_output_chars: int = 12_000,
) -> CodexWatchResult:
    state = CodexWatcherState(state_path or default_codex_watcher_state_path(project_root))
    results: list[IntegrationResult] = []
    processed: list[str] = []
    for thread in discover_due_codex_threads(codex_home=codex_home, state=state, idle_seconds=idle_seconds):
        fingerprint = thread.fingerprint
        result = run_codex_thread_finalize_pipeline(
            thread_id=thread.thread_id,
            codex_home=codex_home,
            project_root=project_root,
            wiki_root=wiki_root,
            max_tool_output_chars=max_tool_output_chars,
        )
        if thread.fingerprint == fingerprint:
            state.mark_processed(thread, fingerprint=fingerprint)
        results.append(result)
        processed.append(thread.thread_id)
    return CodexWatchResult(processed_thread_ids=processed, results=results)


def run_codex_watch_loop(
    *,
    codex_home: Path | str | None,
    project_root: Path | str,
    wiki_root: Path | str,
    interval_seconds: int,
    idle_seconds: int,
    state_path: Path | str | None = None,
    max_tool_output_chars: int = 12_000,
) -> None:
    while True:
        run_codex_watch_once(
            codex_home=codex_home,
            project_root=project_root,
            wiki_root=wiki_root,
            idle_seconds=idle_seconds,
            state_path=state_path,
            max_tool_output_chars=max_tool_output_chars,
        )
        time.sleep(interval_seconds)


@contextmanager
def _temporary_wiki_root(wiki_root: Path):
    old_value = os.environ.get("WIKI_PATH")
    os.environ["WIKI_PATH"] = str(Path(wiki_root).resolve())
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("WIKI_PATH", None)
        else:
            os.environ["WIKI_PATH"] = old_value
