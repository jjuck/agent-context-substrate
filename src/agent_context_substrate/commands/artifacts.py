from __future__ import annotations

import argparse
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
AddProjectRootArgument = Callable[[argparse.ArgumentParser], None]


def register_artifact_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    add_project_root_argument: AddProjectRootArgument,
) -> None:
    extract = subparsers.add_parser("extract-session", help="Export one Hermes session to JSON")
    extract.add_argument("--session-id", required=True, help="Hermes session id to export")
    add_project_root_argument(extract)

    extract_atoms = subparsers.add_parser(
        "extract-atoms",
        help="Extract claim, decision, entity, concept, and question atoms from v2 summary artifacts",
        description="Extract claim, decision, entity, concept, and question atoms from v2 summary artifacts.",
    )
    extract_atoms.add_argument("--packet-id", required=True, help="Packet id whose v2 summary artifacts should be processed")
    add_project_root_argument(extract_atoms)

    propose_promotions = subparsers.add_parser("propose-promotions", help="Propose wiki promotion candidates from claim atoms")
    propose_promotions.add_argument("--packet-id", required=True, help="Packet id whose claim atoms should be evaluated")
    add_project_root_argument(propose_promotions)

    lint_promotions_parser = subparsers.add_parser(
        "lint-promotions", help="Run semantic lint checks on promotions and wiki patch records"
    )
    lint_promotions_parser.add_argument(
        "--fail-on-issues", action="store_true", help="Return exit code 1 when semantic lint issues exist"
    )
    lint_promotions_parser.add_argument(
        "--report-id",
        default="promotions-lint",
        help="Filename stem for exported semantic lint reports",
    )
    add_project_root_argument(lint_promotions_parser)

    review_promotion = subparsers.add_parser(
        "review-promotion",
        help="Review one promotion candidate: preview evidence or accept/reject/supersede/apply it",
    )
    review_promotion.add_argument(
        "--candidate-id",
        action="append",
        required=True,
        help="Promotion candidate id to review; repeat for batch status updates",
    )
    review_promotion.add_argument(
        "--action",
        choices=["accept", "reject", "supersede", "apply"],
        help="Review action to map to accepted/rejected/superseded/applied status",
    )
    review_promotion.add_argument(
        "--status",
        choices=["pending", "accepted", "rejected", "superseded", "applied"],
        help="Direct status override; kept for script compatibility",
    )
    review_promotion.add_argument("--reviewer", help="Optional reviewer identity to record")
    review_promotion.add_argument("--note", help="Optional review note to record")
    review_promotion.add_argument(
        "--preview-evidence",
        action="store_true",
        help="Print candidate reason/proposed change/evidence before mutating; read-only if no action/status is given",
    )
    add_project_root_argument(review_promotion)

    build_topic_map_parser = subparsers.add_parser(
        "build-topic-map",
        help="Build a graph-style topic map from wiki pages and substrate artifacts",
    )
    build_topic_map_parser.add_argument("--wiki-root", help="Wiki root to inspect for markdown links")
    build_topic_map_parser.add_argument(
        "--report-id",
        default="topic_map",
        help="Filename stem for data/index/<report-id>.{json,md}",
    )
    add_project_root_argument(build_topic_map_parser)


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
