from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import os

from .context_packet import build_context_packet, export_context_packet
from .ledger import SessionLedger
from .lint import count_lint_issues, export_lint_report, lint_wiki
from .naming import derive_goal, derive_task_title, derive_unit_title, slugify_label
from .paths import HarnessPaths
from .policy import should_process_bundle
from .promotion import (
    promote_context_packet_to_plan,
    promote_context_packet_to_query,
    promote_unit_summary_to_architecture,
    promote_unit_summary_to_concept,
)
from .recovery import build_recovery_brief
from .raw_extract import build_session_bundle, export_session_bundle
from .summarizer import build_micro_summary, build_unit_summary


@dataclass(frozen=True)
class IntegrationResult:
    session_id: str
    packet_id: str
    raw_export_path: Path
    packet_json_path: Path
    packet_markdown_path: Path
    promoted_paths: dict[str, Path]
    lint_json_path: Path
    lint_markdown_path: Path
    recovery_json_path: Path
    lint_issue_count: int
    skipped: bool = False


@dataclass(frozen=True)
class PacketBuildArtifacts:
    raw_export_path: Path
    task_title: str
    unit_title: str
    unit_summary: object
    packet: object
    packet_json_path: Path
    packet_markdown_path: Path


@dataclass(frozen=True)
class PromotionPlan:
    query_slug: str
    concept_slug: str
    plan_slug: str
    architecture_slug: str
    summaries: dict[str, str]
    related_pages_by_kind: dict[str, list[str]]

    @property
    def slugs(self) -> list[str]:
        return [self.query_slug, self.concept_slug, self.plan_slug, self.architecture_slug]


@dataclass(frozen=True)
class LintArtifacts:
    json_path: Path
    markdown_path: Path
    issue_count: int


class PipelineRetryExhaustedError(RuntimeError):

    """Raised when a previously failing pipeline has exhausted its retry budget."""


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


def _upsert_index_entry(index_path: Path, section_heading: str, entry_line: str) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        index_path.write_text("# Wiki Index\n", encoding="utf-8")
    lines = index_path.read_text(encoding="utf-8").splitlines()
    if entry_line in lines:
        return

    section_line = f"## {section_heading}"
    try:
        section_index = lines.index(section_line)
    except ValueError:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend([section_line, entry_line])
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    section_end = section_index + 1
    while section_end < len(lines) and not lines[section_end].startswith("## "):
        section_end += 1

    empty_marker = "<!-- empty -->"
    if empty_marker in lines[section_index + 1:section_end]:
        empty_index = lines.index(empty_marker, section_index + 1, section_end)
        lines[empty_index] = entry_line
    else:
        lines.insert(section_end, entry_line)

    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_log_entry(log_path: Path, heading: str, bullet_lines: list[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Wiki Log\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    entry = "\n".join([heading, *bullet_lines]) + "\n"
    log_path.write_text(existing + ("\n" if existing.strip() else "") + entry, encoding="utf-8")


def _register_promoted_page(
    *,
    paths: HarnessPaths,
    section_heading: str,
    slug: str,
    summary: str,
    output_path: Path,
    command_name: str,
    extra_lines: list[str] | None = None,
) -> None:
    _upsert_index_entry(
        paths.wiki_root / "index.md",
        section_heading,
        f"- [[{slug}]] — {summary}",
    )
    bullet_lines = [f"- Created/updated: `{output_path.relative_to(paths.wiki_root).as_posix()}`"]
    bullet_lines.extend(list(extra_lines or []))
    _append_log_entry(
        paths.wiki_root / "log.md",
        f"## session-finalize | {slug}",
        bullet_lines,
    )


def _lint_issue_count(report) -> int:
    return count_lint_issues(report)


def _dedupe_related_pages(pages: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for page in pages:
        normalized = page.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _cross_link_targets(current_slug: str, all_slugs: list[str], extra_pages: list[str]) -> list[str]:
    return _dedupe_related_pages(
        [page for page in all_slugs if page != current_slug] + list(extra_pages)
    )


def _build_default_promotion_plan(
    *,
    packet_id: str,
    session_id: str,
    task_title: str,
    unit_title: str,
    related_pages: list[str],
) -> PromotionPlan:
    query_slug = packet_id
    concept_slug = slugify_label(unit_title)
    plan_slug = f"{packet_id}-plan"
    architecture_slug = f"{concept_slug}-architecture"
    all_slugs = [query_slug, concept_slug, plan_slug, architecture_slug]

    summaries = {
        "query": f"Durable query page derived from session {session_id}.",
        "concept": f"Durable concept page derived from session {session_id}.",
        "plan": f"Durable plan page derived from session {session_id}.",
        "architecture": f"Durable architecture page derived from session {session_id}.",
    }
    related_pages_by_kind = {
        "query": _cross_link_targets(query_slug, all_slugs, related_pages),
        "concept": _cross_link_targets(concept_slug, all_slugs, related_pages),
        "plan": _cross_link_targets(plan_slug, all_slugs, related_pages),
        "architecture": _cross_link_targets(architecture_slug, all_slugs, related_pages),
    }
    return PromotionPlan(
        query_slug=query_slug,
        concept_slug=concept_slug,
        plan_slug=plan_slug,
        architecture_slug=architecture_slug,
        summaries=summaries,
        related_pages_by_kind=related_pages_by_kind,
    )


def _build_packet_artifacts(
    *,
    session_id: str,
    packet_id: str,
    paths: HarnessPaths,
    task_title: str | None,
    unit_title: str | None,
    goal: str | None,
    related_pages: list[str],
) -> PacketBuildArtifacts:
    raw_export_path = export_session_bundle(session_id=session_id, paths=paths)
    raw_bundle = build_session_bundle(session_id=session_id, paths=paths)

    resolved_task_title = task_title or derive_task_title(raw_bundle, session_id)
    resolved_unit_title = unit_title or derive_unit_title(raw_bundle, resolved_task_title)
    unit_id = f"{packet_id}-unit-1"

    micro_summary = build_micro_summary(
        raw_bundle=raw_bundle,
        micro_id=f"{packet_id}-micro-1",
        parent_unit_id=unit_id,
    )
    resolved_goal = goal or derive_goal(resolved_task_title, micro_summary)
    unit_summary = build_unit_summary(
        unit_id=unit_id,
        session_id=session_id,
        title=resolved_unit_title,
        goal=resolved_goal,
        micro_summaries=[micro_summary],
        related_pages=list(related_pages),
    )
    packet = build_context_packet(
        packet_id=packet_id,
        task_title=resolved_task_title,
        macro_context=f"Recover session {session_id} without replaying the full raw transcript.",
        unit_summary=unit_summary,
        micro_summaries=[micro_summary],
    )
    packet_json_path, packet_markdown_path = export_context_packet(packet=packet, paths=paths)
    return PacketBuildArtifacts(
        raw_export_path=raw_export_path,
        task_title=resolved_task_title,
        unit_title=resolved_unit_title,
        unit_summary=unit_summary,
        packet=packet,
        packet_json_path=packet_json_path,
        packet_markdown_path=packet_markdown_path,
    )


def _promote_default_artifacts(
    *,
    packet_artifacts: PacketBuildArtifacts,
    promotion_plan: PromotionPlan,
    paths: HarnessPaths,
) -> dict[str, Path]:
    packet = packet_artifacts.packet
    unit_summary = packet_artifacts.unit_summary
    return {
        "query": promote_context_packet_to_query(
            packet=packet,
            paths=paths,
            slug=promotion_plan.query_slug,
            title=packet_artifacts.task_title,
            summary=promotion_plan.summaries["query"],
            related_pages=promotion_plan.related_pages_by_kind["query"],
            tags=["question", "context-packet"],
        ),
        "concept": promote_unit_summary_to_concept(
            unit_summary=unit_summary,
            micro_summaries=packet.micro_summaries,
            paths=paths,
            slug=promotion_plan.concept_slug,
            title=packet_artifacts.unit_title,
            summary=promotion_plan.summaries["concept"],
            related_pages=promotion_plan.related_pages_by_kind["concept"],
            tags=["implementation", "knowledge-base"],
        ),
        "plan": promote_context_packet_to_plan(
            packet=packet,
            paths=paths,
            slug=promotion_plan.plan_slug,
            title=f"{packet_artifacts.task_title} Plan",
            summary=promotion_plan.summaries["plan"],
            related_pages=promotion_plan.related_pages_by_kind["plan"],
            tags=["plan", "implementation"],
        ),
        "architecture": promote_unit_summary_to_architecture(
            unit_summary=unit_summary,
            micro_summaries=packet.micro_summaries,
            paths=paths,
            slug=promotion_plan.architecture_slug,
            title=f"{packet_artifacts.unit_title} Architecture",
            summary=promotion_plan.summaries["architecture"],
            related_pages=promotion_plan.related_pages_by_kind["architecture"],
            tags=["implementation", "architecture"],
        ),
    }


def _register_default_promotions(
    *,
    paths: HarnessPaths,
    promotion_plan: PromotionPlan,
    promoted_paths: dict[str, Path],
    packet_json_path: Path,
) -> None:
    registrations = [
        ("Queries", "query", promotion_plan.query_slug),
        ("Concepts", "concept", promotion_plan.concept_slug),
        ("Plans", "plan", promotion_plan.plan_slug),
        ("Architectures", "architecture", promotion_plan.architecture_slug),
    ]
    for section_heading, kind, slug in registrations:
        _register_promoted_page(
            paths=paths,
            section_heading=section_heading,
            slug=slug,
            summary=promotion_plan.summaries[kind],
            output_path=promoted_paths[kind],
            command_name="run-session-finalize",
            extra_lines=[f"- Source packet: `{packet_json_path}`"],
        )


def _export_lint_artifacts(*, paths: HarnessPaths, packet_id: str) -> LintArtifacts:
    report = lint_wiki(paths)
    lint_json_path, lint_markdown_path = export_lint_report(
        report=report,
        paths=paths,
        report_id=f"{packet_id}-lint",
    )
    return LintArtifacts(
        json_path=lint_json_path,
        markdown_path=lint_markdown_path,
        issue_count=_lint_issue_count(report),
    )


def _build_base_artifact_paths(
    *,
    packet_artifacts: PacketBuildArtifacts,
    promoted_paths: dict[str, Path],
    lint_artifacts: LintArtifacts,
    promotion_mode: str,
) -> dict[str, str]:
    artifact_paths = {
        "promotion_mode": promotion_mode,
        "raw_export_path": str(packet_artifacts.raw_export_path),
        "packet_json_path": str(packet_artifacts.packet_json_path),
        "packet_markdown_path": str(packet_artifacts.packet_markdown_path),
        "lint_json_path": str(lint_artifacts.json_path),
        "lint_markdown_path": str(lint_artifacts.markdown_path),
    }
    artifact_paths.update({name: str(path) for name, path in promoted_paths.items()})
    return artifact_paths


def _completed_result_if_reusable(
    *,
    existing,
    session_id: str,
    packet_id: str,
    promotion_mode: str,
) -> IntegrationResult | None:
    if existing is None or existing.status != "completed":
        return None
    if existing.artifact_paths.get("promotion_mode") != promotion_mode:
        return None
    if not _completed_artifacts_exist(existing.artifact_paths, session_id):
        return None
    return _result_from_artifacts(
        session_id=session_id,
        packet_id=packet_id,
        artifact_paths=existing.artifact_paths,
        lint_issue_count=existing.issue_count,
        skipped=True,
    )


def _raise_if_retry_budget_exhausted(*, existing, session_id: str, pipeline_name: str, max_retry_attempts: int) -> None:
    if existing is None or existing.status != "failed" or existing.attempt_count < max_retry_attempts:
        return
    raise PipelineRetryExhaustedError(
        f"Retry budget exhausted for session_id={session_id} "
        f"pipeline={pipeline_name} attempts={existing.attempt_count}"
    )


def _completed_artifacts_exist(artifact_paths: dict[str, str], session_id: str) -> bool:
    required_keys = [
        "raw_export_path",
        "packet_json_path",
        "packet_markdown_path",
        "lint_json_path",
        "lint_markdown_path",
    ]
    optional_promotion_keys = ["query", "concept", "plan", "architecture"]
    for key in [*required_keys, *[key for key in optional_promotion_keys if key in artifact_paths]]:
        value = artifact_paths.get(key)
        if not value or not Path(value).exists():
            return False

    recovery_value = artifact_paths.get("recovery_json_path")
    if recovery_value:
        return Path(recovery_value).exists()

    fallback_recovery_path = (
        Path(artifact_paths["packet_json_path"]).resolve().parents[1]
        / "recovery"
        / f"{session_id}.json"
    )
    return fallback_recovery_path.exists()


def _result_from_artifacts(
    *,
    session_id: str,
    packet_id: str,
    artifact_paths: dict[str, str],
    lint_issue_count: int,
    skipped: bool,
) -> IntegrationResult:
    promoted_paths = {
        name: Path(artifact_paths[name])
        for name in ["query", "concept", "plan", "architecture"]
        if name in artifact_paths
    }
    return IntegrationResult(
        session_id=session_id,
        packet_id=packet_id,
        raw_export_path=Path(artifact_paths["raw_export_path"]),
        packet_json_path=Path(artifact_paths["packet_json_path"]),
        packet_markdown_path=Path(artifact_paths["packet_markdown_path"]),
        promoted_paths=promoted_paths,
        lint_json_path=Path(artifact_paths["lint_json_path"]),
        lint_markdown_path=Path(artifact_paths["lint_markdown_path"]),
        recovery_json_path=Path(
            artifact_paths.get(
                "recovery_json_path",
                str(Path(artifact_paths["packet_json_path"]).resolve().parents[1] / "recovery" / f"{session_id}.json"),
            )
        ),
        lint_issue_count=lint_issue_count,
        skipped=skipped,
    )


def should_process_session(
    session_id: str,
    *,
    min_message_count: int,
    allowed_sources: list[str] | None = None,
    skip_title_patterns: list[str] | None = None,
) -> bool:
    paths = HarnessPaths(project_root=Path.cwd())
    try:
        raw_bundle = build_session_bundle(session_id=session_id, paths=paths)
    except KeyError:
        return False

    return should_process_bundle(
        raw_bundle,
        min_message_count=min_message_count,
        allowed_sources=allowed_sources,
        skip_title_patterns=skip_title_patterns,
    )


def _normalize_promotion_mode(promotion_mode: str | None) -> str:
    mode = (promotion_mode or "packet-only").strip().lower()
    allowed_modes = {"packet-only", "full"}
    if mode not in allowed_modes:
        raise ValueError(f"Unsupported promotion_mode={promotion_mode!r}; expected one of {sorted(allowed_modes)}")
    return mode


def run_session_finalize_pipeline(
    session_id: str,
    *,
    project_root: Path,
    wiki_root: Path,
    task_title: str | None = None,
    unit_title: str | None = None,
    goal: str | None = None,
    related_pages: list[str] | None = None,
    promotion_mode: str = "packet-only",
    max_retry_attempts: int = 3,
) -> IntegrationResult:
    related_pages = list(related_pages or [])
    promotion_mode = _normalize_promotion_mode(promotion_mode)
    packet_id = session_id
    pipeline_name = "session_finalize"

    with _temporary_wiki_root(Path(wiki_root)):
        paths = HarnessPaths(project_root=Path(project_root).resolve())
        ledger = SessionLedger(paths.index_dir / "session_ledger.json")
        existing = ledger.get_record(session_id, pipeline_name)

        reusable_result = _completed_result_if_reusable(
            existing=existing,
            session_id=session_id,
            packet_id=packet_id,
            promotion_mode=promotion_mode,
        )
        if reusable_result is not None:
            return reusable_result
        _raise_if_retry_budget_exhausted(
            existing=existing,
            session_id=session_id,
            pipeline_name=pipeline_name,
            max_retry_attempts=max_retry_attempts,
        )

        try:
            partial_artifact_paths: dict[str, str] = {}
            packet_artifacts = _build_packet_artifacts(
                session_id=session_id,
                packet_id=packet_id,
                paths=paths,
                task_title=task_title,
                unit_title=unit_title,
                goal=goal,
                related_pages=related_pages,
            )
            promoted_paths: dict[str, Path] = {}
            if promotion_mode == "full":
                promotion_plan = _build_default_promotion_plan(
                    packet_id=packet_id,
                    session_id=session_id,
                    task_title=packet_artifacts.task_title,
                    unit_title=packet_artifacts.unit_title,
                    related_pages=related_pages,
                )
                promoted_paths = _promote_default_artifacts(
                    packet_artifacts=packet_artifacts,
                    promotion_plan=promotion_plan,
                    paths=paths,
                )
                _register_default_promotions(
                    paths=paths,
                    promotion_plan=promotion_plan,
                    promoted_paths=promoted_paths,
                    packet_json_path=packet_artifacts.packet_json_path,
                )

            lint_artifacts = _export_lint_artifacts(paths=paths, packet_id=packet_id)
            base_artifact_paths = _build_base_artifact_paths(
                packet_artifacts=packet_artifacts,
                promoted_paths=promoted_paths,
                lint_artifacts=lint_artifacts,
                promotion_mode=promotion_mode,
            )
            partial_artifact_paths = dict(base_artifact_paths)
            ledger.mark_completed(
                session_id=session_id,
                pipeline=pipeline_name,
                artifact_paths=base_artifact_paths,
                issue_count=lint_artifacts.issue_count,
            )

            recovery_brief = build_recovery_brief(
                session_id=session_id,
                project_root=paths.project_root,
                wiki_root=paths.wiki_root,
            )
            artifact_paths = {
                **base_artifact_paths,
                "recovery_json_path": str(recovery_brief.recovery_json_path),
            }
            partial_artifact_paths = dict(artifact_paths)
            ledger.mark_completed(
                session_id=session_id,
                pipeline=pipeline_name,
                artifact_paths=artifact_paths,
                issue_count=lint_artifacts.issue_count,
            )

            return IntegrationResult(
                session_id=session_id,
                packet_id=packet_id,
                raw_export_path=packet_artifacts.raw_export_path,
                packet_json_path=packet_artifacts.packet_json_path,
                packet_markdown_path=packet_artifacts.packet_markdown_path,
                promoted_paths=promoted_paths,
                lint_json_path=lint_artifacts.json_path,
                lint_markdown_path=lint_artifacts.markdown_path,
                recovery_json_path=recovery_brief.recovery_json_path,
                lint_issue_count=lint_artifacts.issue_count,
                skipped=False,
            )
        except Exception as exc:
            ledger.mark_failed(
                session_id=session_id,
                pipeline=pipeline_name,
                error=f"{type(exc).__name__}: {exc}",
                artifact_paths=partial_artifact_paths,
            )
            raise
