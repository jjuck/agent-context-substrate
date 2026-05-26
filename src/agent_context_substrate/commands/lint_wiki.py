from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..lint import count_lint_issues, export_lint_report, lint_wiki
from ..paths import HarnessPaths
from ..semantic_lint import render_semantic_lint_report

LintPromotions = Callable[..., Any]
ExportSemanticLintReport = Callable[..., tuple[Any, Any]]


def _semantic_lint_includes(args: Any) -> tuple[bool, bool, bool]:
    semantic_enabled = bool(args.semantic or args.include_promotions or args.include_atoms)
    explicit_includes = bool(args.include_promotions or args.include_atoms)
    include_promotions = bool(args.include_promotions or (args.semantic and not explicit_includes))
    include_atoms = bool(args.include_atoms or (args.semantic and not explicit_includes))
    return semantic_enabled, include_promotions, include_atoms


def handle_lint_wiki_command(
    *,
    args: Any,
    paths: HarnessPaths,
    lint_promotions: LintPromotions,
    export_semantic_lint_report: ExportSemanticLintReport,
) -> int:
    report = lint_wiki(paths)
    json_path, markdown_path = export_lint_report(
        report=report,
        paths=paths,
        report_id=args.report_id,
    )
    semantic_report = None
    semantic_json_path = None
    semantic_markdown_path = None
    semantic_enabled, include_promotions, include_atoms = _semantic_lint_includes(args)
    if semantic_enabled:
        semantic_report = lint_promotions(
            paths,
            include_promotions=include_promotions,
            include_atoms=include_atoms,
        )
        semantic_json_path, semantic_markdown_path = export_semantic_lint_report(
            paths=paths,
            report=semantic_report,
        )
    print(json_path)
    print(markdown_path)
    if semantic_report is not None and semantic_json_path is not None and semantic_markdown_path is not None:
        print(semantic_json_path)
        print(semantic_markdown_path)
        print(render_semantic_lint_report(semantic_report))
    print(
        " ".join(
            [
                f"checked_pages={len(report.checked_pages)}",
                f"missing_provenance={len(report.missing_provenance_pages)}",
                f"orphan_pages={len(report.orphan_pages)}",
                f"missing_from_index={len(report.pages_missing_from_index)}",
                f"broken_wikilinks={len(report.broken_wikilinks)}",
                f"semantic_issues={len(semantic_report.issues) if semantic_report is not None else 0}",
                f"promotion_issues={len(semantic_report.issues) if semantic_report is not None else 0}",
            ]
        )
    )
    if args.fail_on_issues and (count_lint_issues(report) > 0 or (semantic_report is not None and not semantic_report.ok)):
        return 1
    return 0
