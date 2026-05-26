from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from ..packet_builder import PacketBuildOptions, PacketBuildResult
from ..raw_extract import build_typed_session_bundle
from ..summarizer_backends import AgentLLMRouter, LLMInputSafetyOptions
from ..summary_pipeline import SummaryOptions, build_v2_summary_artifacts


BuildPacketCallback = Callable[..., PacketBuildResult]
ExportV2Callback = Callable[..., tuple[Any, Any, Any]]
RoutingHintsCallback = Callable[..., dict[str, object]]
LLMSafetyOptionsCallback = Callable[..., object]


def build_summary_routing_hints(*, summary_model: str | None, summary_budget: str | None) -> dict[str, object]:
    hints: dict[str, object] = {}
    if summary_model:
        hints["model"] = summary_model
    if summary_budget:
        hints["budget"] = summary_budget
    return hints


def build_llm_safety_options(
    *,
    llm_redact: str,
    llm_max_input_chars: int,
    llm_allow_code_snippets: str,
    llm_path_policy: str = "redact",
) -> LLMInputSafetyOptions:
    return LLMInputSafetyOptions(
        redact=llm_redact == "on",
        max_input_chars=llm_max_input_chars,
        allow_code_snippets=llm_allow_code_snippets == "on",
        path_policy=llm_path_policy,
    )


def export_v2_summary_artifacts(
    *,
    session_id: str,
    packet_id: str,
    unit_title: str,
    goal: str,
    related_pages: list[str],
    summary_mode: str,
    summarizer_command: str | None,
    paths: Any,
    agent_llm_router: AgentLLMRouter | None = None,
    routing_hints: dict[str, object] | None = None,
    summary_cache: bool = False,
    llm_safety: LLMInputSafetyOptions | None = None,
) -> tuple[Path, Path, Path]:
    session_bundle = build_typed_session_bundle(session_id=session_id, paths=paths)
    result = build_v2_summary_artifacts(
        session_bundle=session_bundle,
        paths=paths,
        options=SummaryOptions(
            session_id=session_id,
            packet_id=packet_id,
            unit_title=unit_title,
            goal=goal,
            related_pages=list(related_pages),
            summary_mode=summary_mode,
            summarizer_command=summarizer_command,
            routing_hints=dict(routing_hints or {}),
            summary_cache=summary_cache,
            agent_llm_router=agent_llm_router,
            llm_safety=llm_safety or LLMInputSafetyOptions(),
        ),
    )
    return result.as_tuple()


def handle_build_context_packet_command(
    *,
    args: Any,
    parser: Any,
    paths: Any,
    build_packet_from_session: BuildPacketCallback,
    export_v2_summary_artifacts: ExportV2Callback,
    summary_routing_hints: RoutingHintsCallback,
    llm_safety_options: LLMSafetyOptionsCallback | None = None,
) -> int:
    """Handle the build-context-packet CLI command.

    The heavy packet/summary pipeline is injected as callbacks for now so this
    command handler can be split out without changing packet-only behavior.
    """

    if args.summary_mode == "custom-command" and not args.summarizer_command:
        parser.error("--summary-mode custom-command requires --summarizer-command")
    if args.summary_mode in {"agent-llm", "hybrid"}:
        parser.error("--summary-mode agent-llm/hybrid requires host Agent integration with an injected Agent LLM router")

    result = build_packet_from_session(
        paths=paths,
        options=PacketBuildOptions(
            session_id=args.session_id,
            packet_id=args.packet_id,
            task_title=args.task_title,
            macro_context=args.macro_context,
            unit_title=args.unit_title,
            goal=args.goal,
            related_pages=list(args.related_pages),
        ),
    )
    packet = result.packet
    print(result.raw_export_path)
    print(result.packet_json_path)
    print(result.packet_markdown_path)
    if args.summary_mode:
        micro_v2_path, unit_v2_path, evidence_path = export_v2_summary_artifacts(
            session_id=args.session_id,
            packet_id=args.packet_id,
            unit_title=args.unit_title,
            goal=args.goal,
            related_pages=list(args.related_pages),
            summary_mode=args.summary_mode,
            summarizer_command=args.summarizer_command,
            paths=paths,
            routing_hints=summary_routing_hints(
                summary_model=args.summary_model,
                summary_budget=args.summary_budget,
            ),
            summary_cache=args.summary_cache == "on",
            llm_safety=(
                llm_safety_options(
                    llm_redact=getattr(args, "llm_redact", "on"),
                    llm_max_input_chars=getattr(args, "llm_max_input_chars", 12_000),
                    llm_allow_code_snippets=getattr(args, "llm_allow_code_snippets", "off"),
                    llm_path_policy=getattr(args, "llm_path_policy", "redact"),
                )
                if llm_safety_options is not None
                else None
            ),
        )
        print(micro_v2_path)
        print(unit_v2_path)
        print(evidence_path)
        _warn_for_summary_fallbacks(micro_v2_path, unit_v2_path)
    print(
        " ".join(
            [
                f"micro_summaries={len(packet.micro_summaries)}",
                f"unit_summaries={len(packet.unit_summaries)}",
                f"critical_files={len(packet.critical_files)}",
            ]
        )
    )
    return 0


def _warn_for_summary_fallbacks(*summary_paths: Path) -> None:
    """Print a concise CLI warning when a v2 summary used fallback behavior."""

    for summary_path in summary_paths:
        warning = _summary_fallback_warning(summary_path)
        if warning:
            print(warning, file=sys.stderr)


def _summary_fallback_warning(summary_path: Path) -> str | None:
    try:
        payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        return None
    fallback_from = metadata.get("fallback_from")
    fallback_reason = metadata.get("fallback_reason")
    if not fallback_from:
        return None
    reason = f" reason={fallback_reason}" if fallback_reason else ""
    return f"WARNING: summary fallback in {Path(summary_path).name}: from={fallback_from}{reason}"
