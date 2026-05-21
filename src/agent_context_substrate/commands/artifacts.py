from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..paths import HarnessPaths
from ..raw_extract import export_session_bundle
from ..semantic_lint import render_semantic_lint_report
from ..topic_map import build_topic_map, export_topic_map

ExportAtoms = Callable[..., list[Path]]
ExportPromotionCandidates = Callable[..., tuple[Path, Path]]
LintPromotions = Callable[..., Any]
ExportSemanticLintReport = Callable[..., tuple[Path, Path]]
UpdatePromotionCandidateStatus = Callable[..., tuple[Path, dict[str, object]]]
RenderPromotionEvidencePreview = Callable[..., str]


def handle_extract_session_command(*, args: Any, paths: HarnessPaths) -> int:
    export_path = export_session_bundle(session_id=args.session_id, paths=paths)
    print(export_path)
    return 0


def handle_extract_atoms_command(*, args: Any, paths: HarnessPaths, export_atoms: ExportAtoms) -> int:
    atom_paths = export_atoms(packet_id=args.packet_id, paths=paths)
    for atom_path in atom_paths:
        print(atom_path)
    return 0


def handle_propose_promotions_command(
    *, args: Any, paths: HarnessPaths, export_promotion_candidates: ExportPromotionCandidates
) -> int:
    promotion_json_path, promotion_markdown_path = export_promotion_candidates(packet_id=args.packet_id, paths=paths)
    print(promotion_json_path)
    print(promotion_markdown_path)
    return 0


def handle_lint_promotions_command(
    *,
    args: Any,
    paths: HarnessPaths,
    lint_promotions: LintPromotions,
    export_semantic_lint_report: ExportSemanticLintReport,
) -> int:
    report = lint_promotions(paths)
    print(render_semantic_lint_report(report))
    lint_json_path, lint_markdown_path = export_semantic_lint_report(
        paths=paths,
        report=report,
        report_id=args.report_id,
    )
    print(lint_json_path)
    print(lint_markdown_path)
    if args.fail_on_issues and not report.ok:
        return 1
    return 0


def handle_review_promotion_command(
    *,
    args: Any,
    paths: HarnessPaths,
    update_promotion_candidate_status: UpdatePromotionCandidateStatus,
    render_promotion_evidence_preview: RenderPromotionEvidencePreview,
) -> int:
    candidate_ids = getattr(args, "candidate_id", [])
    if isinstance(candidate_ids, str):
        candidate_ids = [candidate_ids]
    if getattr(args, "preview_evidence", False):
        for index, candidate_id in enumerate(candidate_ids):
            if index:
                print()
            print(render_promotion_evidence_preview(paths=paths, candidate_id=candidate_id))
    action = getattr(args, "action", None)
    status = getattr(args, "status", None)
    if not action and not status:
        return 0
    for candidate_id in candidate_ids:
        updated_path, updated = update_promotion_candidate_status(
            paths=paths,
            candidate_id=candidate_id,
            action=action,
            status=status,
            reviewer=getattr(args, "reviewer", None),
            note=getattr(args, "note", None),
        )
        print(f"updated {updated.get('candidate_id', candidate_id)} status={updated.get('status')} file={updated_path}")
    return 0


def handle_build_topic_map_command(*, args: Any, paths: HarnessPaths) -> int:
    topic_map = build_topic_map(
        project_root=paths.project_root,
        wiki_root=Path(args.wiki_root).expanduser() if args.wiki_root else paths.wiki_root,
    )
    json_path, markdown_path = export_topic_map(
        topic_map=topic_map,
        project_root=paths.project_root,
        report_id=args.report_id,
    )
    print(json_path)
    print(markdown_path)
    print(f"nodes={len(topic_map.nodes)} edges={len(topic_map.edges)}")
    return 0
