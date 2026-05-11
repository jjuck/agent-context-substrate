from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from ..lint import export_lint_report, lint_wiki
from ..packet_builder import PacketBuildOptions, build_packet_from_session
from ..paths import HarnessPaths
from ..promotion import (
    promote_context_packet_to_plan,
    promote_context_packet_to_query,
    promote_unit_summary_to_architecture,
    promote_unit_summary_to_concept,
)

LoadPacket = Callable[..., Any]
RegisterPromotedPage = Callable[..., None]
Slugify = Callable[[str], str]
UpsertIndexEntry = Callable[[Path, str, str], None]
AppendLogEntry = Callable[[Path, str, list[str]], None]


def handle_promote_packet_query_command(
    *, args: Any, paths: HarnessPaths, load_packet: LoadPacket, register_promoted_page: RegisterPromotedPage
) -> int:
    packet = load_packet(args.packet_json)
    output_path = promote_context_packet_to_query(
        packet=packet,
        paths=paths,
        slug=args.slug,
        title=args.title,
        summary=args.summary,
        related_pages=list(args.related_pages),
        tags=list(args.tags),
    )
    if args.register:
        register_promoted_page(
            paths=paths,
            section_heading="Queries",
            slug=args.slug,
            summary=args.summary,
            output_path=output_path,
            command_name="promote-packet-query",
            extra_lines=[f"- Source packet: `{args.packet_json}`"],
        )
    print(output_path)
    return 0


def handle_promote_packet_plan_command(
    *, args: Any, paths: HarnessPaths, load_packet: LoadPacket, register_promoted_page: RegisterPromotedPage
) -> int:
    packet = load_packet(args.packet_json)
    output_path = promote_context_packet_to_plan(
        packet=packet,
        paths=paths,
        slug=args.slug,
        title=args.title,
        summary=args.summary,
        related_pages=list(args.related_pages),
        tags=list(args.tags),
    )
    if args.register:
        register_promoted_page(
            paths=paths,
            section_heading="Plans",
            slug=args.slug,
            summary=args.summary,
            output_path=output_path,
            command_name="promote-packet-plan",
            extra_lines=[f"- Source packet: `{args.packet_json}`"],
        )
    print(output_path)
    return 0


def handle_promote_unit_concept_command(
    *, args: Any, parser: Any, paths: HarnessPaths, load_packet: LoadPacket, register_promoted_page: RegisterPromotedPage
) -> int:
    packet = load_packet(args.packet_json)
    if not packet.unit_summaries:
        parser.error("promote-unit-concept requires a packet with at least one unit summary")
    output_path = promote_unit_summary_to_concept(
        unit_summary=packet.unit_summaries[0],
        micro_summaries=packet.micro_summaries,
        paths=paths,
        slug=args.slug,
        title=args.title,
        summary=args.summary,
        related_pages=list(args.related_pages),
        tags=list(args.tags),
    )
    if args.register:
        register_promoted_page(
            paths=paths,
            section_heading="Concepts",
            slug=args.slug,
            summary=args.summary,
            output_path=output_path,
            command_name="promote-unit-concept",
            extra_lines=[f"- Source packet: `{args.packet_json}`"],
        )
    print(output_path)
    return 0


def handle_promote_unit_architecture_command(
    *, args: Any, parser: Any, paths: HarnessPaths, load_packet: LoadPacket, register_promoted_page: RegisterPromotedPage
) -> int:
    packet = load_packet(args.packet_json)
    if not packet.unit_summaries:
        parser.error("promote-unit-architecture requires a packet with at least one unit summary")
    output_path = promote_unit_summary_to_architecture(
        unit_summary=packet.unit_summaries[0],
        micro_summaries=packet.micro_summaries,
        paths=paths,
        slug=args.slug,
        title=args.title,
        summary=args.summary,
        related_pages=list(args.related_pages),
        tags=list(args.tags),
    )
    if args.register:
        register_promoted_page(
            paths=paths,
            section_heading="Architectures",
            slug=args.slug,
            summary=args.summary,
            output_path=output_path,
            command_name="promote-unit-architecture",
            extra_lines=[f"- Source packet: `{args.packet_json}`"],
        )
    print(output_path)
    return 0


def handle_run_e2e_pipeline_command(
    *,
    args: Any,
    paths: HarnessPaths,
    slugify: Slugify,
    upsert_index_entry: UpsertIndexEntry,
    append_log_entry: AppendLogEntry,
) -> int:
    packet_build = build_packet_from_session(
        paths=paths,
        options=PacketBuildOptions(
            session_id=args.session_id,
            packet_id=args.packet_id,
            task_title=args.task_title,
            macro_context=args.macro_context,
            unit_title=args.unit_title,
            goal=args.goal,
            related_pages=list(args.packet_related_pages),
        ),
    )
    packet = packet_build.packet
    raw_export_path = packet_build.raw_export_path
    packet_json_path = packet_build.packet_json_path
    packet_markdown_path = packet_build.packet_markdown_path
    query_slug = args.query_slug or args.packet_id
    query_title = args.query_title or args.task_title
    query_summary = args.query_summary or f"Durable query page derived from context packet {args.packet_id}."
    concept_slug = args.concept_slug or slugify(args.unit_title)
    concept_title = args.concept_title or args.unit_title
    concept_summary = args.concept_summary or f"Durable concept page derived from the unit summary for {args.unit_title}."
    plan_slug = args.plan_slug or f"{args.packet_id}-plan"
    plan_title = args.plan_title or f"{args.task_title} Plan"
    plan_summary = args.plan_summary or f"Durable plan page derived from context packet {args.packet_id}."
    architecture_slug = args.architecture_slug or f"{slugify(args.unit_title)}-architecture"
    architecture_title = args.architecture_title or f"{args.unit_title} Architecture"
    architecture_summary = (
        args.architecture_summary or f"Durable architecture page derived from the unit summary for {args.unit_title}."
    )

    query_path = promote_context_packet_to_query(
        packet=packet,
        paths=paths,
        slug=query_slug,
        title=query_title,
        summary=query_summary,
        related_pages=list(args.query_related_pages),
        tags=list(args.query_tags),
    )
    concept_path = promote_unit_summary_to_concept(
        unit_summary=packet.unit_summaries[0],
        micro_summaries=packet.micro_summaries,
        paths=paths,
        slug=concept_slug,
        title=concept_title,
        summary=concept_summary,
        related_pages=list(args.concept_related_pages),
        tags=list(args.concept_tags),
    )
    plan_path = promote_context_packet_to_plan(
        packet=packet,
        paths=paths,
        slug=plan_slug,
        title=plan_title,
        summary=plan_summary,
        related_pages=list(args.plan_related_pages),
        tags=list(args.plan_tags),
    )
    architecture_path = promote_unit_summary_to_architecture(
        unit_summary=packet.unit_summaries[0],
        micro_summaries=packet.micro_summaries,
        paths=paths,
        slug=architecture_slug,
        title=architecture_title,
        summary=architecture_summary,
        related_pages=list(args.architecture_related_pages),
        tags=list(args.architecture_tags),
    )
    for section_heading, slug, summary in [
        ("Queries", query_slug, query_summary),
        ("Concepts", concept_slug, concept_summary),
        ("Plans", plan_slug, plan_summary),
        ("Architectures", architecture_slug, architecture_summary),
    ]:
        upsert_index_entry(
            paths.wiki_root / "index.md",
            section_heading,
            f"- [[{slug}]] — {summary}",
        )
    append_log_entry(
        paths.wiki_root / "log.md",
        f"## [{date.today().isoformat()}] e2e pipeline | {args.packet_id}",
        [
            f"- Session: `{args.session_id}`",
            f"- Created/updated: `{query_path.relative_to(paths.wiki_root).as_posix()}`",
            f"- Created/updated: `{concept_path.relative_to(paths.wiki_root).as_posix()}`",
            f"- Created/updated: `{plan_path.relative_to(paths.wiki_root).as_posix()}`",
            f"- Created/updated: `{architecture_path.relative_to(paths.wiki_root).as_posix()}`",
            f"- Packet export: `{packet_json_path}`",
        ],
    )
    report = lint_wiki(paths)
    lint_json_path, lint_markdown_path = export_lint_report(
        report=report,
        paths=paths,
        report_id=args.report_id,
    )
    for output_path in [
        raw_export_path,
        packet_json_path,
        packet_markdown_path,
        query_path,
        concept_path,
        plan_path,
        architecture_path,
        lint_json_path,
        lint_markdown_path,
    ]:
        print(output_path)
    print(
        " ".join(
            [
                f"micro_summaries={len(packet.micro_summaries)}",
                f"critical_files={len(packet.critical_files)}",
                f"orphan_pages={len(report.orphan_pages)}",
                f"broken_wikilinks={len(report.broken_wikilinks)}",
            ]
        )
    )
    return 0
