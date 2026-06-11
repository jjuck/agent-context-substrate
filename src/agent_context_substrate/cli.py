from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .artifact_pipeline import (
    apply_wiki_patch_file,
    export_atoms,
    export_promotion_candidates,
    export_semantic_lint_report,
    export_wiki_patch_proposal,
    lint_promotions,
    render_promotion_evidence_preview,
    render_promotions_listing,
    render_wiki_patches_listing,
    update_promotion_candidate_status,
)
from .commands.artifacts import (
    handle_build_topic_map_command,
    handle_extract_atoms_command,
    handle_extract_session_command,
    handle_lint_promotions_command,
    handle_propose_promotions_command,
    handle_review_promotion_command,
    register_artifact_commands,
)
from .commands.build_context_packet import (
    build_llm_safety_options,
    build_summary_routing_hints,
    export_v2_summary_artifacts,
    handle_build_context_packet_command,
)
from .commands.codex import (
    default_wiki_root,
    handle_codex_finalize_command,
    handle_codex_status_command,
    handle_codex_watch_command,
    handle_expand_hit_command,
    handle_search_knowledge_command,
)
from .commands.codex_setup import (
    handle_config_codex_command,
    handle_diagnose_codex_command,
    handle_doctor_codex_command,
    handle_setup_codex_command,
    handle_setup_codex_wizard_command,
)
from .commands.distribution import (
    handle_doctor_command,
    handle_fresh_install_smoke_command,
    handle_init_wiki_command,
    handle_install_codex_plugin_command,
    handle_install_context_engine_command,
    handle_install_plugin_command,
)
from .commands.legacy_promotions import (
    handle_promote_packet_plan_command,
    handle_promote_packet_query_command,
    handle_promote_unit_architecture_command,
    handle_promote_unit_concept_command,
    handle_run_e2e_pipeline_command,
)
from .commands.lint_wiki import handle_lint_wiki_command
from .commands.wiki_patches import (
    handle_apply_wiki_patch_command,
    handle_list_promotions_command,
    handle_list_wiki_patches_command,
    handle_plan_wiki_patches_command,
)
from .packet_builder import build_packet_from_session
from .paths import HarnessPaths


def configure_text_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _add_project_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing the local data/ directory",
    )


def _add_wiki_auto_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--wiki-auto-mode",
        choices=["off", "propose", "apply-managed", "apply-flexible"],
        default="off",
        help="Automatically judge and optionally write LLM Wiki updates after finalize.",
    )
    parser.add_argument(
        "--wiki-write-judge-mode",
        choices=["off", "hybrid", "auto", "codex-cli"],
        default="off",
        help="LLM judge mode for deciding whether generated knowledge should be written into the LLM Wiki.",
    )
    parser.add_argument(
        "--wiki-auto-min-score",
        type=float,
        default=0.85,
        help="Minimum judge score required for automatic Wiki writes.",
    )


def _add_registration_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--register",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Update wiki index.md and log.md for this promotion (default: enabled)",
    )

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-context-substrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_artifact_commands(subparsers, add_project_root_argument=_add_project_root_argument)

    plan_wiki_patches = subparsers.add_parser("plan-wiki-patches", help="Plan dry-run wiki patch proposals from promotion candidates")
    plan_wiki_patches.add_argument("--promotion-file", required=True, help="Path to data/promotions/<packet_id>.json")
    plan_wiki_patches.add_argument("--wiki-root", help="Wiki root used to inspect existing target pages")
    plan_wiki_patches.add_argument(
        "--write-mode",
        choices=["managed", "flexible"],
        default="managed",
        help="Wiki proposal style: managed claim blocks or flexible rubric-guided page revisions.",
    )
    _add_project_root_argument(plan_wiki_patches)

    apply_wiki_patch = subparsers.add_parser(
        "apply-wiki-patch",
        help="Apply or dry-run alpha-safe wiki patch operations from a proposal",
    )
    apply_wiki_patch.add_argument("--patch-file", required=True, help="Path to data/wiki_patches/<packet_id>.json")
    apply_wiki_patch.add_argument("--wiki-root", help="Wiki root containing target pages")
    apply_wiki_patch.add_argument(
        "--apply",
        action="store_true",
        help="Actually write alpha-safe managed-block/append changes. Default is dry-run.",
    )
    _add_project_root_argument(apply_wiki_patch)

    list_promotions = subparsers.add_parser("list-promotions", help="List promotion queue candidates")
    list_promotions.add_argument("--status", help="Optional promotion status filter, e.g. pending or applied")
    _add_project_root_argument(list_promotions)

    list_wiki_patches = subparsers.add_parser("list-wiki-patches", help="List wiki patch proposals and applied patch records")
    list_wiki_patches.add_argument("--status", choices=["proposed", "applied"], help="Optional patch status filter")
    _add_project_root_argument(list_wiki_patches)

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
    build_packet.add_argument(
        "--summary-mode",
        choices=["heuristic", "agent-llm", "hybrid", "custom-command", "codex-cli", "auto"],
        help="Optional v2 summary export mode. Default build remains legacy packet-only summaries.",
    )
    build_packet.add_argument(
        "--summarizer-command",
        help="Command for --summary-mode custom-command. Receives JSON on stdin and returns JSON on stdout.",
    )
    build_packet.add_argument(
        "--summary-cache",
        choices=["on", "off"],
        default="off",
        help="Reuse v2 summary artifacts from data/cache/summaries when input/schema/mode match.",
    )
    build_packet.add_argument(
        "--summary-model",
        help="Optional model routing hint for host Agent LLM summary modes; stored in cache keys/artifacts.",
    )
    build_packet.add_argument(
        "--summary-budget",
        help="Optional budget routing hint for host Agent LLM summary modes, e.g. cheap, balanced, or quality.",
    )
    build_packet.add_argument(
        "--codex-cli-command",
        help="Optional Codex executable path for --summary-mode codex-cli/auto; auto-detects when omitted.",
    )
    build_packet.add_argument(
        "--codex-timeout-seconds",
        type=int,
        default=None,
        help="Timeout for each codex exec summary call in codex-cli/auto modes.",
    )
    build_packet.add_argument(
        "--summary-judge-mode",
        choices=["off", "hybrid"],
        default="off",
        help="Opt-in summary quality evaluation export. Hybrid requires a host Agent LLM router to make semantic judgments.",
    )
    build_packet.add_argument(
        "--llm-redact",
        choices=["on", "off"],
        default="on",
        help="Redact common secrets and emails before sending evidence to opt-in LLM/custom summary modes.",
    )
    build_packet.add_argument(
        "--llm-max-input-chars",
        type=int,
        default=12_000,
        help="Maximum JSON payload size sent to opt-in LLM/custom summary modes after safety filtering.",
    )
    build_packet.add_argument(
        "--llm-allow-code-snippets",
        choices=["on", "off"],
        default="off",
        help="Allow code blocks in opt-in LLM/custom summary payloads. Default omits them.",
    )
    build_packet.add_argument(
        "--llm-path-policy",
        choices=["redact", "allow"],
        default="redact",
        help="How to handle local absolute paths in opt-in LLM/custom summary payloads.",
    )
    _add_project_root_argument(build_packet)

    promote_query = subparsers.add_parser(
        "promote-packet-query",
        help="Legacy: promote an exported context packet JSON file into wiki queries/",
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
        help="Legacy: promote an exported context packet JSON file into wiki plans/",
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
        help="Legacy: promote the first unit summary inside a packet JSON file into wiki concepts/",
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
        help="Legacy: promote the first unit summary inside a packet JSON file into wiki architectures/",
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
        help="Legacy full promotion pipeline: extract, packet build, query/concept/plan/architecture promotion, and wiki lint",
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
    lint.add_argument(
        "--semantic",
        action="store_true",
        help="Run semantic substrate lint. Without include flags, checks promotions, wiki patches, and atoms.",
    )
    lint.add_argument(
        "--include-promotions",
        action="store_true",
        help="Include promotion queue and wiki patch records in semantic lint.",
    )
    lint.add_argument(
        "--include-atoms",
        action="store_true",
        help="Include claim and concept atoms in semantic lint.",
    )

    init_wiki_parser = subparsers.add_parser("init-wiki", help="Initialize a human-facing LLM Wiki skeleton")
    init_wiki_parser.add_argument("--wiki-root", required=True, help="Wiki root directory to initialize")

    install_plugin = subparsers.add_parser("install-plugin", help="Install the Hermes user plugin from packaged assets")
    install_plugin.add_argument("--hermes-home", required=True, help="Hermes home directory, usually ~/.hermes")
    install_plugin.add_argument("--project-root", required=True, help="Harness project root used by the plugin")
    install_plugin.add_argument("--wiki-root", required=True, help="Obsidian/LLM Wiki root used by the plugin")
    install_plugin.add_argument("--overwrite", action="store_true", help="Backup and replace an existing plugin install")

    install_codex_plugin = subparsers.add_parser(
        "install-codex-plugin",
        help="Install the non-MCP Codex plugin asset and local config",
    )
    install_codex_plugin.add_argument("--codex-home", required=True, help="Codex home directory, usually ~/.codex")
    install_codex_plugin.add_argument("--project-root", required=True, help="Harness project root used by Codex CLI commands")
    install_codex_plugin.add_argument("--wiki-root", required=True, help="Obsidian/LLM Wiki root used by Codex CLI commands")
    install_codex_plugin.add_argument(
        "--personal-marketplace-root",
        help="Optional Codex marketplace source root, usually the user home directory",
    )
    install_codex_plugin.add_argument(
        "--install-user-hook",
        action="store_true",
        help="Also register the Stop hook in ~/.codex/hooks.json for non-plugin hook fallback",
    )
    install_codex_plugin.add_argument("--overwrite", action="store_true", help="Backup and replace an existing plugin install")

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

    setup_codex = subparsers.add_parser(
        "setup-codex",
        help="One-shot Windows Codex app setup for ACS plugin, wiki, hooks, and diagnostics",
    )
    setup_codex.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    setup_codex.add_argument("--wiki-root", default=None, help="LLM Wiki root; default uses %%USERPROFILE%%\\Documents\\LLM Wiki template")
    setup_codex.add_argument("--personal-marketplace-root", default=None, help="Optional personal marketplace root, usually the user home")
    setup_codex.add_argument("--yes", action="store_true", help="Accept the displayed defaults for non-interactive setup")
    setup_codex.add_argument("--dry-run", action="store_true", help="Print planned setup actions without writing files")
    setup_codex.add_argument("--json", action="store_true", help="Print JSON instead of text")
    setup_codex.add_argument(
        "--user-hook-fallback",
        action="store_true",
        help="Also register ~/.codex/hooks.json fallback. Off by default to avoid duplicate Stop hooks.",
    )
    setup_codex.add_argument(
        "--no-user-hook",
        action="store_true",
        help="Deprecated compatibility flag; user hook fallback is already off by default.",
    )
    setup_codex.add_argument("--no-marketplace", action="store_true", help="Do not install personal marketplace/cache entry")
    setup_codex.add_argument("--no-overwrite", action="store_true", help="Do not replace an existing ACS Codex plugin")
    _add_project_root_argument(setup_codex)

    setup_codex_wizard = subparsers.add_parser(
        "setup-codex-wizard",
        help="Interactive Windows Codex app setup wizard",
    )
    setup_codex_wizard.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    setup_codex_wizard.add_argument("--wiki-root", default=None, help="LLM Wiki root; default uses %%USERPROFILE%%\\Documents\\LLM Wiki template")
    setup_codex_wizard.add_argument("--personal-marketplace-root", default=None, help="Optional personal marketplace root")
    setup_codex_wizard.add_argument("--yes", action="store_true", help="Run without asking for confirmation")
    setup_codex_wizard.add_argument("--json", action="store_true", help="Print JSON instead of text")
    _add_project_root_argument(setup_codex_wizard)

    doctor_codex = subparsers.add_parser("doctor-codex", help="Check Windows Codex app ACS setup health")
    doctor_codex.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    doctor_codex.add_argument("--wiki-root", default=None, help="LLM Wiki root; default uses installed/env/default template")
    doctor_codex.add_argument(
        "--summary-smoke",
        action="store_true",
        help="Run a brief read-only codex exec smoke when summary_mode=auto/codex-cli is configured.",
    )
    doctor_codex.add_argument("--json", action="store_true", help="Print JSON instead of text")
    doctor_codex.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 if required checks fail")
    _add_project_root_argument(doctor_codex)

    diagnose_codex = subparsers.add_parser("diagnose-codex", help="Explain and optionally repair safe Codex setup issues")
    diagnose_codex.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    diagnose_codex.add_argument("--wiki-root", default=None, help="LLM Wiki root; default uses installed/env/default template")
    diagnose_codex.add_argument("--personal-marketplace-root", default=None, help="Optional personal marketplace root for --fix")
    diagnose_codex.add_argument("--fix", action="store_true", help="Repair safe local ACS files; does not bypass hook trust")
    diagnose_codex.add_argument("--json", action="store_true", help="Print JSON instead of text")
    _add_project_root_argument(diagnose_codex)

    config_codex = subparsers.add_parser("config-codex", help="Inspect or update installed Codex plugin local_config.json")
    config_actions = config_codex.add_subparsers(dest="config_action", required=True)
    for action_name, help_text in [
        ("paths", "Show user-facing Codex, wiki, and ACS artifact paths"),
        ("show", "Show installed local_config.json"),
        ("write", "Write default local_config.json"),
        ("export-env", "Print PowerShell environment variable exports"),
    ]:
        action_parser = config_actions.add_parser(action_name, help=help_text)
        action_parser.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
        action_parser.add_argument("--wiki-root", default=None, help="LLM Wiki root; default uses installed/env/default template")
        action_parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
        _add_project_root_argument(action_parser)
    config_set = config_actions.add_parser("set", help="Set one local_config.json key")
    config_set.add_argument("--key", required=True, help="Config key to update")
    config_set.add_argument("--value", required=True, help="Config value; JSON scalars are accepted")
    config_set.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    config_set.add_argument("--wiki-root", default=None, help="LLM Wiki root; default uses installed/env/default template")
    config_set.add_argument("--json", action="store_true", help="Print JSON instead of text")
    _add_project_root_argument(config_set)

    codex_status = subparsers.add_parser("codex-status", help="Inspect Codex local session source and integration mode")
    codex_status.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")

    codex_finalize = subparsers.add_parser("codex-finalize", help="Finalize one Codex thread into ACS artifacts")
    codex_finalize.add_argument("--thread-id", required=True, help="Codex thread id from state_5.sqlite")
    codex_finalize.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    codex_finalize.add_argument("--wiki-root", required=True, help="Obsidian/LLM Wiki root")
    codex_finalize.add_argument("--task-title", help="Optional packet task title override")
    codex_finalize.add_argument("--unit-title", help="Optional unit title override")
    codex_finalize.add_argument("--goal", help="Optional unit goal override")
    codex_finalize.add_argument(
        "--related-page",
        action="append",
        dest="related_pages",
        default=[],
        help="Related wiki page path or slug; may be repeated",
    )
    codex_finalize.add_argument(
        "--max-tool-output-chars",
        type=int,
        default=12_000,
        help="Maximum function_call_output characters retained in raw Codex exports",
    )
    codex_finalize.add_argument(
        "--summary-mode",
        choices=["heuristic", "custom-command", "codex-cli", "auto"],
        help="Optional v2 summary export mode for this Codex thread.",
    )
    codex_finalize.add_argument(
        "--summarizer-command",
        help="Command for --summary-mode custom-command. Receives JSON on stdin and returns JSON on stdout.",
    )
    codex_finalize.add_argument(
        "--summary-cache",
        choices=["on", "off"],
        default="off",
        help="Reuse v2 summary artifacts from data/cache/summaries when input/schema/mode match.",
    )
    codex_finalize.add_argument("--summary-model", help="Optional model hint for LLM summary modes.")
    codex_finalize.add_argument("--summary-budget", help="Optional budget hint for LLM summary modes.")
    codex_finalize.add_argument(
        "--codex-cli-command",
        help="Optional Codex executable path for --summary-mode codex-cli/auto; auto-detects when omitted.",
    )
    codex_finalize.add_argument(
        "--codex-timeout-seconds",
        type=int,
        default=None,
        help="Timeout for each codex exec summary call in codex-cli/auto modes.",
    )
    codex_finalize.add_argument("--llm-redact", choices=["on", "off"], default="on")
    codex_finalize.add_argument("--llm-max-input-chars", type=int, default=12_000)
    codex_finalize.add_argument("--llm-allow-code-snippets", choices=["on", "off"], default="off")
    codex_finalize.add_argument("--llm-path-policy", choices=["redact", "allow"], default="redact")
    _add_wiki_auto_arguments(codex_finalize)
    _add_project_root_argument(codex_finalize)

    codex_watch = subparsers.add_parser("codex-watch", help="Watch Codex rollout JSONL files and finalize idle threads")
    codex_watch.add_argument("--codex-home", default=None, help="Codex home directory, usually ~/.codex")
    codex_watch.add_argument("--wiki-root", default=default_wiki_root(), help="Obsidian/LLM Wiki root")
    codex_watch.add_argument("--interval-seconds", type=int, default=15, help="Polling interval for watcher mode")
    codex_watch.add_argument("--idle-seconds", type=int, default=90, help="Minimum rollout idle time before finalizing")
    codex_watch.add_argument("--state-path", help="Optional watcher state JSON path")
    codex_watch.add_argument("--once", action="store_true", help="Process currently idle threads once and exit")
    codex_watch.add_argument(
        "--max-tool-output-chars",
        type=int,
        default=12_000,
        help="Maximum function_call_output characters retained in raw Codex exports",
    )
    codex_watch.add_argument(
        "--summary-mode",
        choices=["heuristic", "custom-command", "codex-cli", "auto"],
        help="Optional v2 summary export mode for finalized Codex threads.",
    )
    codex_watch.add_argument(
        "--summarizer-command",
        help="Command for --summary-mode custom-command. Receives JSON on stdin and returns JSON on stdout.",
    )
    codex_watch.add_argument("--summary-cache", choices=["on", "off"], default="off")
    codex_watch.add_argument("--summary-model", help="Optional model hint for LLM summary modes.")
    codex_watch.add_argument("--summary-budget", help="Optional budget hint for LLM summary modes.")
    codex_watch.add_argument(
        "--codex-cli-command",
        help="Optional Codex executable path for --summary-mode codex-cli/auto; auto-detects when omitted.",
    )
    codex_watch.add_argument("--codex-timeout-seconds", type=int, default=None)
    codex_watch.add_argument("--llm-redact", choices=["on", "off"], default="on")
    codex_watch.add_argument("--llm-max-input-chars", type=int, default=12_000)
    codex_watch.add_argument("--llm-allow-code-snippets", choices=["on", "off"], default="off")
    codex_watch.add_argument("--llm-path-policy", choices=["redact", "allow"], default="redact")
    _add_wiki_auto_arguments(codex_watch)
    _add_project_root_argument(codex_watch)

    search_parser = subparsers.add_parser("search-knowledge", help="Search wiki, packets, recovery, graph, and optional raw messages")
    search_parser.add_argument("--query", required=True, help="Search query")
    search_parser.add_argument("--wiki-root", default=default_wiki_root(), help="Obsidian/LLM Wiki root")
    search_parser.add_argument("--mode", choices=["knowledge", "recovery", "graph"], default="knowledge")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--include-raw", action="store_true", help="Include raw Hermes state.db messages")
    search_parser.add_argument("--graph-depth", type=int, default=0)
    search_parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    _add_project_root_argument(search_parser)

    expand_parser = subparsers.add_parser("expand-hit", help="Expand a retrieval hit id into full content")
    expand_parser.add_argument("--hit-id", required=True, help="Retrieval hit id from search-knowledge")
    expand_parser.add_argument("--wiki-root", default=default_wiki_root(), help="Obsidian/LLM Wiki root")
    expand_parser.add_argument("--json", action="store_true", help="Print JSON detail instead of content")
    _add_project_root_argument(expand_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_text_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-wiki":
        return handle_init_wiki_command(args=args)

    if args.command == "install-plugin":
        return handle_install_plugin_command(args=args)

    if args.command == "install-codex-plugin":
        return handle_install_codex_plugin_command(args=args)

    if args.command == "install-context-engine":
        return handle_install_context_engine_command(args=args)

    if args.command == "doctor":
        return handle_doctor_command(args=args)

    if args.command == "fresh-install-smoke":
        return handle_fresh_install_smoke_command(args=args)

    if args.command == "setup-codex":
        return handle_setup_codex_command(args=args)

    if args.command == "setup-codex-wizard":
        return handle_setup_codex_wizard_command(args=args)

    if args.command == "doctor-codex":
        return handle_doctor_codex_command(args=args)

    if args.command == "diagnose-codex":
        return handle_diagnose_codex_command(args=args)

    if args.command == "config-codex":
        return handle_config_codex_command(args=args)

    if args.command == "codex-status":
        return handle_codex_status_command(args=args)

    paths = HarnessPaths(project_root=Path(args.project_root).resolve())

    if args.command == "codex-finalize":
        return handle_codex_finalize_command(args=args)

    if args.command == "codex-watch":
        return handle_codex_watch_command(args=args)

    if args.command == "search-knowledge":
        return handle_search_knowledge_command(args=args)

    if args.command == "expand-hit":
        return handle_expand_hit_command(args=args)

    if args.command == "extract-session":
        return handle_extract_session_command(args=args, paths=paths)

    if args.command == "extract-atoms":
        return handle_extract_atoms_command(args=args, paths=paths, export_atoms=export_atoms)

    if args.command == "propose-promotions":
        return handle_propose_promotions_command(
            args=args,
            paths=paths,
            export_promotion_candidates=export_promotion_candidates,
        )

    if args.command == "plan-wiki-patches":
        return handle_plan_wiki_patches_command(
            args=args,
            paths=paths,
            export_wiki_patch_proposal=export_wiki_patch_proposal,
        )

    if args.command == "apply-wiki-patch":
        return handle_apply_wiki_patch_command(
            args=args,
            paths=paths,
            apply_wiki_patch_file=apply_wiki_patch_file,
        )

    if args.command == "list-promotions":
        return handle_list_promotions_command(
            args=args,
            paths=paths,
            render_promotions_listing=render_promotions_listing,
        )

    if args.command == "review-promotion":
        return handle_review_promotion_command(
            args=args,
            paths=paths,
            update_promotion_candidate_status=update_promotion_candidate_status,
            render_promotion_evidence_preview=render_promotion_evidence_preview,
        )

    if args.command == "list-wiki-patches":
        return handle_list_wiki_patches_command(
            args=args,
            paths=paths,
            render_wiki_patches_listing=render_wiki_patches_listing,
        )

    if args.command == "lint-promotions":
        return handle_lint_promotions_command(
            args=args,
            paths=paths,
            lint_promotions=lint_promotions,
            export_semantic_lint_report=export_semantic_lint_report,
        )

    if args.command == "build-topic-map":
        return handle_build_topic_map_command(args=args, paths=paths)

    if args.command == "build-context-packet":
        return handle_build_context_packet_command(
            args=args,
            parser=parser,
            paths=paths,
            build_packet_from_session=build_packet_from_session,
            export_v2_summary_artifacts=export_v2_summary_artifacts,
            summary_routing_hints=build_summary_routing_hints,
            llm_safety_options=build_llm_safety_options,
        )

    if args.command == "promote-packet-query":
        return handle_promote_packet_query_command(
            args=args,
            paths=paths,
        )

    if args.command == "promote-packet-plan":
        return handle_promote_packet_plan_command(
            args=args,
            paths=paths,
        )

    if args.command == "promote-unit-concept":
        return handle_promote_unit_concept_command(
            args=args,
            parser=parser,
            paths=paths,
        )

    if args.command == "promote-unit-architecture":
        return handle_promote_unit_architecture_command(
            args=args,
            parser=parser,
            paths=paths,
        )

    if args.command == "run-e2e-pipeline":
        return handle_run_e2e_pipeline_command(
            args=args,
            paths=paths,
        )

    if args.command == "lint-wiki":
        return handle_lint_wiki_command(
            args=args,
            paths=paths,
            lint_promotions=lint_promotions,
            export_semantic_lint_report=export_semantic_lint_report,
        )

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
