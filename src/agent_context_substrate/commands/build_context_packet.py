from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from ..packet_builder import PacketBuildOptions, PacketBuildResult


BuildPacketCallback = Callable[..., PacketBuildResult]
ExportV2Callback = Callable[..., tuple[Any, Any, Any]]
RoutingHintsCallback = Callable[..., dict[str, object]]


def handle_build_context_packet_command(
    *,
    args: Any,
    parser: Any,
    paths: Any,
    build_packet_from_session: BuildPacketCallback,
    export_v2_summary_artifacts: ExportV2Callback,
    summary_routing_hints: RoutingHintsCallback,
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
