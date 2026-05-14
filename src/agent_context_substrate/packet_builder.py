from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .context_packet import build_context_packet, export_context_packet
from .models import ContextPacket, MicroSummary, UnitSummary
from .paths import HarnessPaths
from .raw_extract import build_typed_session_bundle, export_session_bundle
from .session_bundle import SessionBundle
from .summarizer import build_micro_summary, build_unit_summary


@dataclass(frozen=True)
class PacketBuildOptions:
    session_id: str
    packet_id: str
    task_title: str
    macro_context: str
    unit_title: str
    goal: str
    related_pages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PacketBuildResult:
    packet: ContextPacket
    raw_export_path: Path
    packet_json_path: Path
    packet_markdown_path: Path

    def as_tuple(self) -> tuple[ContextPacket, Path, Path, Path]:
        return self.packet, self.raw_export_path, self.packet_json_path, self.packet_markdown_path


BuildSessionBundle = Callable[..., SessionBundle]
ExportSessionBundle = Callable[..., Path]
BuildMicroSummary = Callable[..., MicroSummary]
BuildUnitSummary = Callable[..., UnitSummary]
BuildContextPacket = Callable[..., ContextPacket]
ExportContextPacket = Callable[..., tuple[Path, Path]]


def build_packet_from_session(
    *,
    paths: HarnessPaths,
    options: PacketBuildOptions,
    build_session_bundle_func: BuildSessionBundle = build_typed_session_bundle,
    export_session_bundle_func: ExportSessionBundle = export_session_bundle,
    build_micro_summary_func: BuildMicroSummary = build_micro_summary,
    build_unit_summary_func: BuildUnitSummary = build_unit_summary,
    build_context_packet_func: BuildContextPacket = build_context_packet,
    export_context_packet_func: ExportContextPacket = export_context_packet,
) -> PacketBuildResult:
    """Build and export the legacy packet-only context artifacts for a session."""

    raw_export_path = export_session_bundle_func(session_id=options.session_id, paths=paths)
    session_bundle = build_session_bundle_func(session_id=options.session_id, paths=paths)
    unit_id = f"{options.packet_id}-unit-1"
    micro_summary = build_micro_summary_func(
        session_bundle=session_bundle,
        micro_id=f"{options.packet_id}-micro-1",
        parent_unit_id=unit_id,
    )
    unit_summary = build_unit_summary_func(
        unit_id=unit_id,
        session_id=options.session_id,
        title=options.unit_title,
        goal=options.goal,
        micro_summaries=[micro_summary],
        related_pages=list(options.related_pages),
    )
    packet = build_context_packet_func(
        packet_id=options.packet_id,
        task_title=options.task_title,
        macro_context=options.macro_context,
        unit_summary=unit_summary,
        micro_summaries=[micro_summary],
    )
    packet_json_path, packet_markdown_path = export_context_packet_func(packet=packet, paths=paths)
    return PacketBuildResult(
        packet=packet,
        raw_export_path=raw_export_path,
        packet_json_path=packet_json_path,
        packet_markdown_path=packet_markdown_path,
    )
