from __future__ import annotations

import json
from pathlib import Path

from .models import ContextPacket, MicroSummary, UnitSummary
from .paths import HarnessPaths
from .safe_paths import safe_child_path


def build_context_packet(
    packet_id: str,
    task_title: str,
    macro_context: str,
    unit_summary: UnitSummary,
    micro_summaries: list[MicroSummary],
) -> ContextPacket:
    relevant_micro_summaries = [
        summary for summary in micro_summaries if summary.micro_id in unit_summary.micro_ids
    ]

    critical_files = sorted(
        {
            file_path
            for summary in relevant_micro_summaries
            for file_path in summary.files
        }
    )
    raw_pointers = [
        summary.provenance
        for summary in relevant_micro_summaries
        if summary.provenance is not None
    ]

    return ContextPacket(
        packet_id=packet_id,
        task_title=task_title,
        macro_context=macro_context,
        unit_summaries=[unit_summary],
        micro_summaries=relevant_micro_summaries,
        raw_pointers=raw_pointers,
        critical_files=critical_files,
        open_questions=list(unit_summary.open_questions),
    )


def render_context_packet_markdown(packet: ContextPacket) -> str:
    lines: list[str] = [
        f"# Context Packet: {packet.task_title}",
        "",
        f"- Packet ID: `{packet.packet_id}`",
        "",
        "## Macro Context",
        packet.macro_context,
        "",
        "## Unit Summaries",
    ]

    for unit in packet.unit_summaries:
        lines.extend(
            [
                f"- **{unit.title}** — {unit.goal}",
            ]
        )

    lines.extend(["", "## Micro Summaries"])
    for summary in packet.micro_summaries:
        lines.extend(
            [
                f"- `{summary.micro_id}`: {summary.summary}",
            ]
        )

    lines.extend(["", "## Critical Files"])
    for file_path in packet.critical_files:
        lines.append(f"- `{file_path}`")

    if packet.open_questions:
        lines.extend(["", "## Open Questions"])
        for question in packet.open_questions:
            lines.append(f"- {question}")

    if packet.raw_pointers:
        lines.extend(["", "## Raw Pointers"])
        for pointer in packet.raw_pointers:
            lines.append(
                f"- `{pointer.session_id}` messages {pointer.message_ids}"
            )

    lines.append("")
    return "\n".join(lines)


def export_context_packet(packet: ContextPacket, paths: HarnessPaths) -> tuple[Path, Path]:
    paths.ensure_project_dirs()
    export_dir = paths.exports_dir / "context_packets"
    export_dir.mkdir(parents=True, exist_ok=True)

    json_path = safe_child_path(export_dir, packet.packet_id, ".json", label="packet id")
    markdown_path = safe_child_path(export_dir, packet.packet_id, ".md", label="packet id")

    json_path.write_text(
        json.dumps(packet.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_context_packet_markdown(packet), encoding="utf-8")
    return json_path, markdown_path
