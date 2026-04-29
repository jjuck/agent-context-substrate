from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re

from .context_packet import build_context_packet, export_context_packet
from .distribution import (
    doctor,
    init_wiki,
    install_context_engine,
    install_user_plugin,
    run_fresh_install_smoke,
)
from .lint import export_lint_report, lint_wiki
from .models import ContextPacket
from .paths import HarnessPaths
from .promotion import (
    promote_context_packet_to_plan,
    promote_context_packet_to_query,
    promote_unit_summary_to_architecture,
    promote_unit_summary_to_concept,
)
from .raw_extract import build_session_bundle, export_session_bundle
from .summarizer import build_micro_summary, build_unit_summary


def _add_project_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing the local data/ directory",
    )


def _load_packet(packet_json_path: str | Path) -> ContextPacket:
    payload = json.loads(Path(packet_json_path).read_text(encoding="utf-8"))
    return ContextPacket.from_dict(payload)


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "artifact"


def _build_packet_from_session(
    *,
    session_id: str,
    packet_id: str,
    task_title: str,
    macro_context: str,
    unit_title: str,
    goal: str,
    related_pages: list[str],
    paths: HarnessPaths,
) -> tuple[ContextPacket, Path, Path, Path]:
    raw_export_path = export_session_bundle(session_id=session_id, paths=paths)
    raw_bundle = build_session_bundle(session_id=session_id, paths=paths)
    unit_id = f"{packet_id}-unit-1"
    micro_summary = build_micro_summary(
        raw_bundle=raw_bundle,
        micro_id=f"{packet_id}-micro-1",
        parent_unit_id=unit_id,
    )
    unit_summary = build_unit_summary(
        unit_id=unit_id,
        session_id=session_id,
        title=unit_title,
        goal=goal,
        micro_summaries=[micro_summary],
        related_pages=list(related_pages),
    )
    packet = build_context_packet(
        packet_id=packet_id,
        task_title=task_title,
        macro_context=macro_context,
        unit_summary=unit_summary,
        micro_summaries=[micro_summary],
    )
    packet_json_path, packet_markdown_path = export_context_packet(packet=packet, paths=paths)
    return packet, raw_export_path, packet_json_path, packet_markdown_path


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
        while empty_index + 1 < len(lines) and lines[empty_index + 1] == "":
            del lines[empty_index + 1]
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.insert(section_end, entry_line)
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_log_entry(log_path: Path, heading: str, bullet_lines: list[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Wiki Log\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    entry = "\n".join([heading, *bullet_lines]) + "\n"
    log_path.write_text(existing + ("\n" if existing.strip() else "") + entry, encoding="utf-8")


def _add_registration_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--register",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Update wiki index.md and log.md for this promotion (default: enabled)",
    )


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
        f"## [{date.today().isoformat()}] {command_name} | {slug}",
        bullet_lines,
    )


def _lint_issue_count(report) -> int:
    return sum(
        len(items)
        for items in [
            report.missing_provenance_pages,
            report.orphan_pages,
            report.pages_missing_from_index,
            report.broken_wikilinks,
            report.micro_summaries_missing_parent_unit,
            report.micro_summaries_with_unknown_parent_unit,
            report.unit_summaries_with_missing_micro_references,
            report.packet_micro_summaries_unreferenced,
            report.packets_missing_raw_pointers,
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-context-substrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract-session", help="Export one Hermes session to JSON")
    extract.add_argument("--session-id", required=True, help="Hermes session id to export")
    _add_project_root_argument(extract)

    build_packet = subparsers.add_parser(
        "build-context-packet",
        help="Build a context packet from one Hermes session and export raw + packet artifacts",
    )
    build_packet.add_argument("--session-id", required=True, help="Hermes session id to summarize")
    build_packet.add_argument("--packet-id", required=True, help="Packet identifier for exported files")
    build_packet.add_argument("--task-title", required=True, help="High-level task title for the packet")
    build_packet.add_argument("--macro-context", required=True, help="Macro framing text for future resumption")
    build_packet.add_argument("--unit-title", required=True, help="Title for the derived unit summary")
    build_packet.add_argument("--goal", required=True, help="Goal for the derived unit summary")
    build_packet.add_argument(
        "--related-page",
        action="append",
        dest="related_pages",
        default=[],
        help="Related wiki page path or slug; may be repeated",
    )
    _add_project_root_argument(build_packet)

    promote_query = subparsers.add_parser(
        "promote-packet-query",
        help="Promote an exported context packet JSON file into wiki queries/",
    )
    promote_query.add_argument("--packet-json", required=True, help="Path to an exported context packet JSON file")
    promote_query.add_argument("--slug", required=True, help="Output markdown filename stem")
    promote_query.add_argument("--title", required=True, help="Page title")
    promote_query.add_argument("--summary", required=True, help="Top-level summary for the query page")
    promote_query.add_argument(
        "--related-page",
        action="append",
        dest="related_pages",
        default=[],
        help="Related wiki page path or slug; may be repeated",
    )
    promote_query.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        help="Tag to include in frontmatter; may be repeated",
    )
    _add_registration_argument(promote_query)
    _add_project_root_argument(promote_query)

    promote_plan = subparsers.add_parser(
        "promote-packet-plan",
        help="Promote an exported context packet JSON file into wiki plans/",
    )
    promote_plan.add_argument("--packet-json", required=True, help="Path to an exported context packet JSON file")
    promote_plan.add_argument("--slug", required=True, help="Output markdown filename stem")
    promote_plan.add_argument("--title", required=True, help="Page title")
    promote_plan.add_argument("--summary", required=True, help="Top-level summary for the plan page")
    promote_plan.add_argument(
        "--related-page",
        action="append",
        dest="related_pages",
        default=[],
        help="Related wiki page path or slug; may be repeated",
    )
    promote_plan.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        help="Tag to include in frontmatter; may be repeated",
    )
    _add_registration_argument(promote_plan)
    _add_project_root_argument(promote_plan)

    promote_concept = subparsers.add_parser(
        "promote-unit-concept",
        help="Promote the first unit summary inside a packet JSON file into wiki concepts/",
    )
    promote_concept.add_argument("--packet-json", required=True, help="Path to an exported context packet JSON file")
    promote_concept.add_argument("--slug", required=True, help="Output markdown filename stem")
    promote_concept.add_argument("--title", required=True, help="Page title")
    promote_concept.add_argument("--summary", required=True, help="Top-level summary for the concept page")
    promote_concept.add_argument(
        "--related-page",
        action="append",
        dest="related_pages",
        default=[],
        help="Related wiki page path or slug; may be repeated",
    )
    promote_concept.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        help="Tag to include in frontmatter; may be repeated",
    )
    _add_registration_argument(promote_concept)
    _add_project_root_argument(promote_concept)

    promote_architecture = subparsers.add_parser(
        "promote-unit-architecture",
        help="Promote the first unit summary inside a packet JSON file into wiki architectures/",
    )
    promote_architecture.add_argument("--packet-json", required=True, help="Path to an exported context packet JSON file")
    promote_architecture.add_argument("--slug", required=True, help="Output markdown filename stem")
    promote_architecture.add_argument("--title", required=True, help="Page title")
    promote_architecture.add_argument("--summary", required=True, help="Top-level summary for the architecture page")
    promote_architecture.add_argument(
        "--related-page",
        action="append",
        dest="related_pages",
        default=[],
        help="Related wiki page path or slug; may be repeated",
    )
    promote_architecture.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        help="Tag to include in frontmatter; may be repeated",
    )
    _add_registration_argument(promote_architecture)
    _add_project_root_argument(promote_architecture)

    e2e = subparsers.add_parser(
        "run-e2e-pipeline",
        help="Run extract, packet build, query/concept/plan/architecture promotion, and wiki lint in one command",
    )
    e2e.add_argument("--session-id", required=True, help="Hermes session id to process")
    e2e.add_argument("--packet-id", required=True, help="Packet identifier for exported files")
    e2e.add_argument("--task-title", required=True, help="High-level task title for the packet")
    e2e.add_argument("--macro-context", required=True, help="Macro framing text for future resumption")
    e2e.add_argument("--unit-title", required=True, help="Title for the derived unit summary")
    e2e.add_argument("--goal", required=True, help="Goal for the derived unit summary")
    e2e.add_argument(
        "--packet-related-page",
        action="append",
        dest="packet_related_pages",
        default=[],
        help="Related wiki page path or slug to attach to the packet/unit stage; may be repeated",
    )
    e2e.add_argument(
        "--query-related-page",
        action="append",
        dest="query_related_pages",
        default=[],
        help="Related wiki page path or slug for the promoted query page; may be repeated",
    )
    e2e.add_argument(
        "--query-tag",
        action="append",
        dest="query_tags",
        default=[],
        help="Tag to include in the promoted query page; may be repeated",
    )
    e2e.add_argument(
        "--concept-related-page",
        action="append",
        dest="concept_related_pages",
        default=[],
        help="Related wiki page path or slug for the promoted concept page; may be repeated",
    )
    e2e.add_argument(
        "--concept-tag",
        action="append",
        dest="concept_tags",
        default=[],
        help="Tag to include in the promoted concept page; may be repeated",
    )
    e2e.add_argument(
        "--plan-related-page",
        action="append",
        dest="plan_related_pages",
        default=[],
        help="Related wiki page path or slug for the promoted plan page; may be repeated",
    )
    e2e.add_argument(
        "--plan-tag",
        action="append",
        dest="plan_tags",
        default=[],
        help="Tag to include in the promoted plan page; may be repeated",
    )
    e2e.add_argument(
        "--architecture-related-page",
        action="append",
        dest="architecture_related_pages",
        default=[],
        help="Related wiki page path or slug for the promoted architecture page; may be repeated",
    )
    e2e.add_argument(
        "--architecture-tag",
        action="append",
        dest="architecture_tags",
        default=[],
        help="Tag to include in the promoted architecture page; may be repeated",
    )
    e2e.add_argument(
        "--query-slug",
        help="Optional output filename stem for the query page; defaults to packet id",
    )
    e2e.add_argument(
        "--query-title",
        help="Optional query page title; defaults to task title",
    )
    e2e.add_argument(
        "--query-summary",
        help="Optional query page summary; defaults to an auto-generated summary",
    )
    e2e.add_argument(
        "--concept-slug",
        help="Optional output filename stem for the concept page; defaults to a slugified unit title",
    )
    e2e.add_argument(
        "--concept-title",
        help="Optional concept page title; defaults to the unit title",
    )
    e2e.add_argument(
        "--concept-summary",
        help="Optional concept page summary; defaults to an auto-generated summary",
    )
    e2e.add_argument(
        "--plan-slug",
        help="Optional output filename stem for the plan page; defaults to '<packet-id>-plan'",
    )
    e2e.add_argument(
        "--plan-title",
        help="Optional plan page title; defaults to '<task title> Plan'",
    )
    e2e.add_argument(
        "--plan-summary",
        help="Optional plan page summary; defaults to an auto-generated summary",
    )
    e2e.add_argument(
        "--architecture-slug",
        help="Optional output filename stem for the architecture page; defaults to '<unit-title>-architecture'",
    )
    e2e.add_argument(
        "--architecture-title",
        help="Optional architecture page title; defaults to '<unit title> Architecture'",
    )
    e2e.add_argument(
        "--architecture-summary",
        help="Optional architecture page summary; defaults to an auto-generated summary",
    )
    e2e.add_argument(
        "--report-id",
        default="wiki-lint",
        help="Filename stem for exported lint reports",
    )
    _add_project_root_argument(e2e)

    lint = subparsers.add_parser("lint-wiki", help="Run wiki lint checks and export a report")
    _add_project_root_argument(lint)
    lint.add_argument(
        "--report-id",
        default="wiki-lint",
        help="Filename stem for exported lint reports",
    )
    lint.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Return exit code 1 when any wiki or internal graph issue is detected",
    )

    init_wiki_parser = subparsers.add_parser("init-wiki", help="Initialize a human-facing LLM Wiki skeleton")
    init_wiki_parser.add_argument("--wiki-root", required=True, help="Wiki root directory to initialize")

    install_plugin = subparsers.add_parser("install-plugin", help="Install the Hermes user plugin from packaged assets")
    install_plugin.add_argument("--hermes-home", required=True, help="Hermes home directory, usually ~/.hermes")
    install_plugin.add_argument("--project-root", required=True, help="Harness project root used by the plugin")
    install_plugin.add_argument("--wiki-root", required=True, help="Obsidian/LLM Wiki root used by the plugin")
    install_plugin.add_argument("--overwrite", action="store_true", help="Backup and replace an existing plugin install")

    install_engine = subparsers.add_parser(
        "install-context-engine",
        help="Install the Hermes agent_context_substrate context engine from packaged assets",
    )
    install_engine.add_argument("--hermes-agent-root", required=True, help="Hermes Agent source/root directory")
    install_engine.add_argument("--project-root", help="Optional harness project root for context-engine local_config.py")
    install_engine.add_argument("--wiki-root", help="Optional Obsidian/LLM Wiki root for context-engine local_config.py")
    install_engine.add_argument("--overwrite", action="store_true", help="Backup and replace an existing context engine install")

    doctor_parser = subparsers.add_parser("doctor", help="Check agent-context-substrate installation health")
    doctor_parser.add_argument("--hermes-home", required=True, help="Hermes home directory, usually ~/.hermes")
    doctor_parser.add_argument("--project-root", required=True, help="Harness project root")
    doctor_parser.add_argument("--wiki-root", required=True, help="Obsidian/LLM Wiki root")
    doctor_parser.add_argument("--hermes-agent-root", required=True, help="Hermes Agent source/root directory")
    doctor_parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 if any check fails")

    smoke_parser = subparsers.add_parser(
        "fresh-install-smoke",
        help="Run init, install, packet-only finalize, recovery, retrieval, and lint smoke checks",
    )
    smoke_parser.add_argument("--session-id", required=True, help="Hermes session id to process")
    smoke_parser.add_argument("--hermes-home", required=True, help="Hermes home containing state.db")
    smoke_parser.add_argument("--project-root", required=True, help="Temporary or real harness project root")
    smoke_parser.add_argument("--wiki-root", required=True, help="Temporary or real wiki root")
    smoke_parser.add_argument("--hermes-agent-root", required=False, help="Optional Hermes Agent root for context-engine install")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-wiki":
        result = init_wiki(Path(args.wiki_root).resolve())
        print(result.status)
        for name, path in result.paths.items():
            print(f"{name}={path}")
        for message in result.messages:
            print(message)
        return 0

    if args.command == "install-plugin":
        result = install_user_plugin(
            hermes_home=Path(args.hermes_home).expanduser(),
            project_root=Path(args.project_root).expanduser(),
            wiki_root=Path(args.wiki_root).expanduser(),
            overwrite=args.overwrite,
        )
        print(result.status)
        for name, path in result.paths.items():
            print(f"{name}={path}")
        for message in result.messages:
            print(message)
        return 0

    if args.command == "install-context-engine":
        result = install_context_engine(
            hermes_agent_root=Path(args.hermes_agent_root).expanduser(),
            project_root=Path(args.project_root).expanduser() if args.project_root else None,
            wiki_root=Path(args.wiki_root).expanduser() if args.wiki_root else None,
            overwrite=args.overwrite,
        )
        print(result.status)
        for name, path in result.paths.items():
            print(f"{name}={path}")
        for message in result.messages:
            print(message)
        return 0

    if args.command == "doctor":
        report = doctor(
            hermes_home=Path(args.hermes_home).expanduser(),
            project_root=Path(args.project_root).expanduser(),
            wiki_root=Path(args.wiki_root).expanduser(),
            hermes_agent_root=Path(args.hermes_agent_root).expanduser(),
        )
        print(f"doctor ok={report.ok}")
        for name, ok in report.checks.items():
            print(f"{name}={'ok' if ok else 'missing'}")
        for message in report.messages:
            print(message)
        if args.fail_on_issues and not report.ok:
            return 1
        return 0

    if args.command == "fresh-install-smoke":
        result = run_fresh_install_smoke(
            session_id=args.session_id,
            hermes_home=Path(args.hermes_home).expanduser(),
            project_root=Path(args.project_root).expanduser(),
            wiki_root=Path(args.wiki_root).expanduser(),
            hermes_agent_root=Path(args.hermes_agent_root).expanduser() if args.hermes_agent_root else None,
        )
        print(f"fresh-install-smoke ok={result.ok}")
        print(f"retrieval_hit_count={result.retrieval_hit_count}")
        print(f"expanded_content_length={result.expanded_content_length}")
        print(f"lint_issue_count={result.lint_issue_count}")
        for name, path in result.artifacts.items():
            print(f"{name}={path}")
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1

    paths = HarnessPaths(project_root=Path(args.project_root).resolve())

    if args.command == "extract-session":
        export_path = export_session_bundle(session_id=args.session_id, paths=paths)
        print(export_path)
        return 0

    if args.command == "build-context-packet":
        packet, raw_export_path, packet_json_path, packet_markdown_path = _build_packet_from_session(
            session_id=args.session_id,
            packet_id=args.packet_id,
            task_title=args.task_title,
            macro_context=args.macro_context,
            unit_title=args.unit_title,
            goal=args.goal,
            related_pages=list(args.related_pages),
            paths=paths,
        )
        print(raw_export_path)
        print(packet_json_path)
        print(packet_markdown_path)
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

    if args.command == "promote-packet-query":
        packet = _load_packet(args.packet_json)
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
            _register_promoted_page(
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

    if args.command == "promote-packet-plan":
        packet = _load_packet(args.packet_json)
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
            _register_promoted_page(
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

    if args.command == "promote-unit-concept":
        packet = _load_packet(args.packet_json)
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
            _register_promoted_page(
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

    if args.command == "promote-unit-architecture":
        packet = _load_packet(args.packet_json)
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
            _register_promoted_page(
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

    if args.command == "run-e2e-pipeline":
        packet, raw_export_path, packet_json_path, packet_markdown_path = _build_packet_from_session(
            session_id=args.session_id,
            packet_id=args.packet_id,
            task_title=args.task_title,
            macro_context=args.macro_context,
            unit_title=args.unit_title,
            goal=args.goal,
            related_pages=list(args.packet_related_pages),
            paths=paths,
        )
        query_slug = args.query_slug or args.packet_id
        query_title = args.query_title or args.task_title
        query_summary = args.query_summary or (
            f"Durable query page derived from context packet {args.packet_id}."
        )
        concept_slug = args.concept_slug or _slugify(args.unit_title)
        concept_title = args.concept_title or args.unit_title
        concept_summary = args.concept_summary or (
            f"Durable concept page derived from the unit summary for {args.unit_title}."
        )
        plan_slug = args.plan_slug or f"{args.packet_id}-plan"
        plan_title = args.plan_title or f"{args.task_title} Plan"
        plan_summary = args.plan_summary or (
            f"Durable plan page derived from context packet {args.packet_id}."
        )
        architecture_slug = args.architecture_slug or f"{_slugify(args.unit_title)}-architecture"
        architecture_title = args.architecture_title or f"{args.unit_title} Architecture"
        architecture_summary = args.architecture_summary or (
            f"Durable architecture page derived from the unit summary for {args.unit_title}."
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
            _upsert_index_entry(
                paths.wiki_root / "index.md",
                section_heading,
                f"- [[{slug}]] — {summary}",
            )
        _append_log_entry(
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

    if args.command == "lint-wiki":
        report = lint_wiki(paths)
        json_path, markdown_path = export_lint_report(
            report=report,
            paths=paths,
            report_id=args.report_id,
        )
        print(json_path)
        print(markdown_path)
        print(
            " ".join(
                [
                    f"checked_pages={len(report.checked_pages)}",
                    f"missing_provenance={len(report.missing_provenance_pages)}",
                    f"orphan_pages={len(report.orphan_pages)}",
                    f"missing_from_index={len(report.pages_missing_from_index)}",
                    f"broken_wikilinks={len(report.broken_wikilinks)}",
                ]
            )
        )
        if args.fail_on_issues and _lint_issue_count(report) > 0:
            return 1
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
