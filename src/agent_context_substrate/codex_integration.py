from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import time

from .artifact_pipeline import (
    apply_wiki_patch_file,
    export_atoms,
    export_promotion_candidates,
    load_promotion_candidates,
)
from .codex_source import (
    CodexThreadRecord,
    build_codex_session_bundle,
    discover_codex_threads,
    export_codex_session_bundle,
    resolve_codex_home,
)
from .context_packet import build_context_packet, export_context_packet
from .integration import IntegrationResult, _lint_issue_count, _summary_artifact_paths
from .ledger import SessionLedger
from .lint import export_lint_report, lint_wiki
from .naming import derive_goal, derive_task_title, derive_unit_title
from .paths import HarnessPaths
from .recovery import build_recovery_brief
from .safe_paths import safe_artifact_stem, safe_child_path
from .summarizer import build_micro_summary, build_unit_summary
from .summarizer_backends import AgentLLMRouter, LLMInputSafetyOptions
from .summary_pipeline import SummaryArtifactResult, SummaryOptions, build_v2_summary_artifacts
from .wiki_patches import (
    WikiPatchApplyResult,
    WikiPatchProposal,
    plan_wiki_patch_proposal,
    render_wiki_patch_proposal_markdown,
)
from .wiki_write_judge import (
    WikiWriteDecision,
    evaluate_wiki_write_with_judge,
    export_wiki_write_decision,
    normalize_wiki_auto_mode,
    normalize_wiki_write_judge_mode,
)


@dataclass(frozen=True)
class CodexWatchResult:
    processed_thread_ids: list[str]
    results: list[IntegrationResult]


@dataclass(frozen=True)
class CodexWikiAutoResult:
    decision: WikiWriteDecision
    decision_path: Path
    patch_json_path: Path | None
    patch_markdown_path: Path | None
    apply_result: WikiPatchApplyResult | None


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
) -> IntegrationResult:
    related_pages = list(related_pages or [])
    wiki_auto_mode = normalize_wiki_auto_mode(wiki_auto_mode)
    wiki_write_judge_mode = normalize_wiki_write_judge_mode(wiki_write_judge_mode)
    if wiki_auto_mode != "off" and not summary_mode:
        summary_mode = "auto"
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
            summary_artifacts: SummaryArtifactResult | None = None
            if summary_mode:
                summary_artifacts = build_v2_summary_artifacts(
                    session_bundle=session_bundle,
                    paths=paths,
                    options=SummaryOptions(
                        session_id=thread_id,
                        packet_id=packet_id,
                        unit_title=resolved_unit_title,
                        goal=resolved_goal,
                        related_pages=related_pages,
                        summary_mode=summary_mode,
                        summarizer_command=summarizer_command,
                        routing_hints=_build_codex_summary_routing_hints(
                            summary_model=summary_model,
                            summary_budget=summary_budget,
                            codex_cli_command=codex_cli_command,
                            codex_project_root=paths.project_root,
                            codex_timeout_seconds=codex_timeout_seconds,
                        ),
                        summary_cache=summary_cache,
                        llm_safety=llm_safety or LLMInputSafetyOptions(),
                    ),
                )
            wiki_auto_result: CodexWikiAutoResult | None = None
            if wiki_auto_mode != "off" and summary_artifacts is not None:
                wiki_auto_result = _run_codex_wiki_auto(
                    packet_id=packet_id,
                    paths=paths,
                    wiki_root=Path(wiki_root),
                    wiki_auto_mode=wiki_auto_mode,
                    wiki_write_judge_mode=wiki_write_judge_mode,
                    wiki_auto_min_score=wiki_auto_min_score,
                    wiki_write_judge_router=wiki_write_judge_router,
                    summary_model=summary_model,
                    summary_budget=summary_budget,
                    codex_cli_command=codex_cli_command,
                    codex_timeout_seconds=codex_timeout_seconds,
                    llm_safety=llm_safety,
                )
            lint_report = lint_wiki(paths)
            lint_json_path, lint_markdown_path = export_lint_report(
                report=lint_report,
                paths=paths,
                report_id=f"{packet_id}-lint",
            )
            artifact_paths = {
                "promotion_mode": "packet-only",
                "summary_mode": summary_mode or "",
                "summary_judge_mode": "off",
                "wiki_auto_mode": wiki_auto_mode,
                "wiki_write_judge_mode": wiki_write_judge_mode,
                "raw_export_path": str(raw_export_path),
                "packet_json_path": str(packet_json_path),
                "packet_markdown_path": str(packet_markdown_path),
                "lint_json_path": str(lint_json_path),
                "lint_markdown_path": str(lint_markdown_path),
            }
            artifact_paths.update(_summary_artifact_paths(summary_artifacts))
            artifact_paths.update(_wiki_auto_artifact_paths(wiki_auto_result))
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
                summary_micro_path=summary_artifacts.micro_path if summary_artifacts is not None else None,
                summary_unit_path=summary_artifacts.unit_path if summary_artifacts is not None else None,
                summary_evidence_path=summary_artifacts.evidence_path if summary_artifacts is not None else None,
                wiki_decision_path=wiki_auto_result.decision_path if wiki_auto_result is not None else None,
                wiki_patch_path=wiki_auto_result.patch_json_path if wiki_auto_result is not None else None,
                wiki_patch_markdown_path=wiki_auto_result.patch_markdown_path if wiki_auto_result is not None else None,
                wiki_apply_result=wiki_auto_result.apply_result if wiki_auto_result is not None else None,
            )
        except Exception as exc:
            ledger.mark_failed(
                session_id=thread_id,
                pipeline="session_finalize",
                error=f"{type(exc).__name__}: {exc}",
                artifact_paths=partial_artifact_paths,
            )
            raise


def _run_codex_wiki_auto(
    *,
    packet_id: str,
    paths: HarnessPaths,
    wiki_root: Path,
    wiki_auto_mode: str,
    wiki_write_judge_mode: str,
    wiki_auto_min_score: float,
    wiki_write_judge_router: AgentLLMRouter | None,
    summary_model: str | None,
    summary_budget: str | None,
    codex_cli_command: Path | str | None,
    codex_timeout_seconds: int | None,
    llm_safety: LLMInputSafetyOptions | None,
) -> CodexWikiAutoResult:
    export_atoms(packet_id=packet_id, paths=paths)
    promotion_json_path, _promotion_markdown_path = export_promotion_candidates(packet_id=packet_id, paths=paths)
    candidates = load_promotion_candidates(promotion_json_path)
    write_mode = "managed" if wiki_auto_mode == "apply-managed" else "flexible"
    proposal = plan_wiki_patch_proposal(
        packet_id=packet_id,
        candidates=candidates,
        wiki_root=wiki_root,
        write_mode=write_mode,
        judge_mode=wiki_write_judge_mode,
    )
    decision = evaluate_wiki_write_with_judge(
        packet_id=packet_id,
        candidates=candidates,
        proposal=proposal,
        mode=wiki_write_judge_mode,
        router=wiki_write_judge_router,
        routing_hints=_build_codex_wiki_judge_routing_hints(
            summary_model=summary_model,
            summary_budget=summary_budget,
            codex_cli_command=codex_cli_command,
            codex_project_root=paths.project_root,
            codex_timeout_seconds=codex_timeout_seconds,
        ),
        min_score=wiki_auto_min_score,
        llm_safety=llm_safety or LLMInputSafetyOptions(),
    )
    decision_path = export_wiki_write_decision(packet_id=packet_id, decision=decision, project_root=paths.project_root)
    if not candidates:
        return CodexWikiAutoResult(
            decision=decision,
            decision_path=decision_path,
            patch_json_path=None,
            patch_markdown_path=None,
            apply_result=None,
        )
    should_apply = decision.approved_for_auto_apply(wiki_auto_mode)
    final_proposal = plan_wiki_patch_proposal(
        packet_id=packet_id,
        candidates=candidates,
        wiki_root=wiki_root,
        write_mode=write_mode,
        judge_mode=wiki_write_judge_mode,
        judge_verdict="approved" if should_apply else decision.decision,
    )
    patch_json_path, patch_markdown_path = _export_codex_wiki_patch_proposal(paths=paths, proposal=final_proposal)
    apply_result = apply_wiki_patch_file(
        patch_file=patch_json_path,
        paths=paths,
        wiki_root=wiki_root,
        dry_run=not should_apply,
    )
    return CodexWikiAutoResult(
        decision=decision,
        decision_path=decision_path,
        patch_json_path=patch_json_path,
        patch_markdown_path=patch_markdown_path,
        apply_result=apply_result,
    )


def _export_codex_wiki_patch_proposal(*, paths: HarnessPaths, proposal: WikiPatchProposal) -> tuple[Path, Path]:
    wiki_patches_dir = paths.project_root / "data" / "wiki_patches"
    wiki_patches_dir.mkdir(parents=True, exist_ok=True)
    safe_packet_id = safe_artifact_stem(proposal.packet_id, label="packet id")
    json_path = safe_child_path(wiki_patches_dir, safe_packet_id, ".json", label="packet id")
    markdown_path = safe_child_path(wiki_patches_dir, safe_packet_id, ".md", label="packet id")
    json_path.write_text(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_wiki_patch_proposal_markdown(proposal), encoding="utf-8")
    return json_path, markdown_path


def _wiki_auto_artifact_paths(result: CodexWikiAutoResult | None) -> dict[str, str]:
    if result is None:
        return {}
    artifact_paths = {
        "wiki_decision_path": str(result.decision_path),
        "wiki_write_decision": result.decision.decision,
        "wiki_write_score": str(result.decision.score),
    }
    if result.patch_json_path is not None:
        artifact_paths["wiki_patch_path"] = str(result.patch_json_path)
    if result.patch_markdown_path is not None:
        artifact_paths["wiki_patch_markdown_path"] = str(result.patch_markdown_path)
    if result.apply_result is not None:
        artifact_paths["wiki_apply_dry_run"] = str(result.apply_result.dry_run)
        artifact_paths["wiki_apply_planned_count"] = str(len(result.apply_result.planned_patch_ids))
        artifact_paths["wiki_apply_applied_count"] = str(len(result.apply_result.applied_patch_ids))
        artifact_paths["wiki_apply_skipped_count"] = str(len(result.apply_result.skipped_patch_ids))
    return artifact_paths


def _build_codex_wiki_judge_routing_hints(
    *,
    summary_model: str | None,
    summary_budget: str | None,
    codex_cli_command: Path | str | None,
    codex_project_root: Path,
    codex_timeout_seconds: int | None,
) -> dict[str, object]:
    hints: dict[str, object] = {"codex_project_root": str(codex_project_root)}
    if summary_model:
        hints["model"] = summary_model
    if summary_budget:
        hints["budget"] = summary_budget
    if codex_cli_command:
        hints["codex_cli_command"] = str(codex_cli_command)
    if codex_timeout_seconds is not None:
        hints["codex_timeout_seconds"] = codex_timeout_seconds
    return hints


def run_codex_watch_once(
    *,
    codex_home: Path | str | None,
    project_root: Path | str,
    wiki_root: Path | str,
    idle_seconds: int,
    state_path: Path | str | None = None,
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
) -> None:
    while True:
        run_codex_watch_once(
            codex_home=codex_home,
            project_root=project_root,
            wiki_root=wiki_root,
            idle_seconds=idle_seconds,
            state_path=state_path,
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
        )
        time.sleep(interval_seconds)


def _build_codex_summary_routing_hints(
    *,
    summary_model: str | None,
    summary_budget: str | None,
    codex_cli_command: Path | str | None,
    codex_project_root: Path,
    codex_timeout_seconds: int | None,
) -> dict[str, object]:
    hints: dict[str, object] = {"codex_project_root": str(codex_project_root)}
    if summary_model:
        hints["model"] = summary_model
    if summary_budget:
        hints["budget"] = summary_budget
    if codex_cli_command:
        hints["codex_cli_command"] = str(codex_cli_command)
    if codex_timeout_seconds is not None:
        hints["codex_timeout_seconds"] = codex_timeout_seconds
    return hints


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
