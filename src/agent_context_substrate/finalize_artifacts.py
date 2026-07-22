from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from .context_packet import build_context_packet, export_context_packet
from .llm_runtime import AgentLLMRouter, LLMInputSafetyOptions
from .models import ContextPacket, UnitSummary
from .naming import derive_goal, derive_task_title, derive_unit_title
from .paths import HarnessPaths
from .session_bundle import SessionBundle
from .summarizer import build_micro_summary, build_unit_summary
from .summary_pipeline import SummaryArtifactResult, SummaryOptions, build_v2_summary_artifacts


@dataclass(frozen=True)
class FinalizeArtifactOptions:
    session_id: str
    packet_id: str
    macro_context: str
    task_title: str | None = None
    unit_title: str | None = None
    goal: str | None = None
    related_pages: tuple[str, ...] = ()
    summary_mode: str | None = None
    summarizer_command: str | None = None
    summary_routing_hints: dict[str, object] | None = None
    summary_cache: bool = False
    agent_llm_router: AgentLLMRouter | None = None
    llm_safety: LLMInputSafetyOptions | None = None


@dataclass(frozen=True)
class FinalizeArtifactResult:
    raw_export_path: Path
    task_title: str
    unit_title: str
    goal: str
    unit_summary: UnitSummary
    packet: ContextPacket
    packet_json_path: Path
    packet_markdown_path: Path
    summary_artifacts: SummaryArtifactResult | None = None


def build_finalize_artifacts(
    *,
    session_bundle: SessionBundle,
    raw_export_path: Path,
    paths: HarnessPaths,
    options: FinalizeArtifactOptions,
) -> FinalizeArtifactResult:
    """Build source-neutral packet and summary artifacts from a typed session."""

    task_title = options.task_title or derive_task_title(
        session_bundle=session_bundle,
        session_id=options.session_id,
    )
    unit_title = options.unit_title or derive_unit_title(
        session_bundle=session_bundle,
        task_title=task_title,
    )
    unit_id = f"{options.packet_id}-unit-1"
    micro_summary = build_micro_summary(
        session_bundle=session_bundle,
        micro_id=f"{options.packet_id}-micro-1",
        parent_unit_id=unit_id,
    )
    goal = options.goal or derive_goal(task_title, micro_summary)
    related_pages = list(options.related_pages)
    unit_summary = build_unit_summary(
        unit_id=unit_id,
        session_id=options.session_id,
        title=unit_title,
        goal=goal,
        micro_summaries=[micro_summary],
        related_pages=related_pages,
    )
    packet = build_context_packet(
        packet_id=options.packet_id,
        task_title=task_title,
        macro_context=options.macro_context,
        unit_summary=unit_summary,
        micro_summaries=[micro_summary],
    )
    packet_json_path, packet_markdown_path = export_context_packet(packet=packet, paths=paths)
    summary_artifacts = None
    if options.summary_mode:
        summary_artifacts = build_v2_summary_artifacts(
            session_bundle=session_bundle,
            paths=paths,
            options=SummaryOptions(
                session_id=options.session_id,
                packet_id=options.packet_id,
                unit_title=unit_title,
                goal=goal,
                related_pages=related_pages,
                summary_mode=options.summary_mode,
                summarizer_command=options.summarizer_command,
                routing_hints=dict(options.summary_routing_hints or {}),
                summary_cache=options.summary_cache,
                agent_llm_router=options.agent_llm_router,
                llm_safety=options.llm_safety or LLMInputSafetyOptions(),
            ),
        )
    return FinalizeArtifactResult(
        raw_export_path=raw_export_path,
        task_title=task_title,
        unit_title=unit_title,
        goal=goal,
        unit_summary=unit_summary,
        packet=packet,
        packet_json_path=packet_json_path,
        packet_markdown_path=packet_markdown_path,
        summary_artifacts=summary_artifacts,
    )


def summary_artifact_paths(summary_artifacts: SummaryArtifactResult | None) -> dict[str, str]:
    if summary_artifacts is None:
        return {}
    artifact_paths = {
        "summary_micro_path": str(summary_artifacts.micro_path),
        "summary_unit_path": str(summary_artifacts.unit_path),
        "summary_evidence_path": str(summary_artifacts.evidence_path),
    }
    artifact_paths.update(_summary_metadata_artifact_paths(summary_artifacts.micro_path, prefix="summary_micro"))
    artifact_paths.update(_summary_metadata_artifact_paths(summary_artifacts.unit_path, prefix="summary_unit"))
    if summary_artifacts.judge_path is not None:
        artifact_paths["summary_judge_path"] = str(summary_artifacts.judge_path)
    return artifact_paths


def _summary_metadata_artifact_paths(path: Path, *, prefix: str) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        return {}
    return {
        f"{prefix}_{key}": str(value)
        for key in ("mode", "fallback_from", "fallback_reason")
        if (value := metadata.get(key))
    }
