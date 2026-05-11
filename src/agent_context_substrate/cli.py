from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

from .atoms import (
    ClaimAtom,
    extract_claim_atoms,
    extract_concept_atoms,
    extract_decision_atoms,
    extract_entity_atoms,
    extract_question_atoms,
)
from .commands.artifacts import (
    handle_build_topic_map_command,
    handle_extract_atoms_command,
    handle_extract_session_command,
    handle_lint_promotions_command,
    handle_propose_promotions_command,
)
from .commands.build_context_packet import handle_build_context_packet_command
from .commands.distribution import (
    handle_doctor_command,
    handle_fresh_install_smoke_command,
    handle_init_wiki_command,
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
from .lint import count_lint_issues
from .models import ContextPacket, MicroSummaryV2
from .paths import HarnessPaths
from .promotions import (
    PromotionCandidate,
    propose_promotion_candidates,
    render_promotion_candidates_markdown,
)
from .raw_extract import build_session_bundle
from .safe_paths import safe_artifact_stem, safe_child_path
from .semantic_lint import lint_promotion_substrate, render_semantic_lint_report
from .wiki_patches import (
    WikiPatchApplyResult,
    WikiPatchProposal,
    apply_wiki_patch_proposal,
    plan_wiki_patch_proposal,
    render_wiki_patch_proposal_markdown,
)
from .summarizer_backends import AgentLLMRouter, LLMInputSafetyOptions
from .summary_pipeline import SummaryOptions, build_v2_summary_artifacts


def _add_project_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing the local data/ directory",
    )


def _load_packet(packet_json_path: str | Path) -> ContextPacket:
    payload = json.loads(Path(packet_json_path).read_text(encoding="utf-8"))
    return ContextPacket.from_dict(payload)


def _load_micro_summary_v2(path: Path) -> MicroSummaryV2:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return MicroSummaryV2.from_dict(payload)


def _export_atoms(*, packet_id: str, paths: HarnessPaths) -> list[Path]:
    packet_id = safe_artifact_stem(packet_id, label="packet id")
    micro_path = safe_child_path(paths.exports_dir / "summaries", f"{packet_id}-micro-v2", ".json", label="summary artifact id")
    if not micro_path.exists():
        raise FileNotFoundError(
            f"Missing v2 micro summary artifact: {micro_path}. Run build-context-packet --summary-mode first."
        )
    micro_summaries = [_load_micro_summary_v2(micro_path)]
    atom_dir = paths.project_root / "data" / "atoms"
    atom_dir.mkdir(parents=True, exist_ok=True)
    exports = [
        ("claims.jsonl", f"{packet_id}-claim-", [atom.to_dict() for atom in extract_claim_atoms(packet_id=packet_id, micro_summaries=micro_summaries)]),
        ("decisions.jsonl", f"{packet_id}-decision-", [atom.to_dict() for atom in extract_decision_atoms(packet_id=packet_id, micro_summaries=micro_summaries)]),
        ("entities.jsonl", f"{packet_id}-entity-", [atom.to_dict() for atom in extract_entity_atoms(packet_id=packet_id, micro_summaries=micro_summaries)]),
        ("concepts.jsonl", f"{packet_id}-concept-", [atom.to_dict() for atom in extract_concept_atoms(packet_id=packet_id, micro_summaries=micro_summaries)]),
        ("questions.jsonl", f"{packet_id}-question-", [atom.to_dict() for atom in extract_question_atoms(packet_id=packet_id, micro_summaries=micro_summaries)]),
    ]
    written_paths: list[Path] = []
    for filename, atom_id_prefix, atoms in exports:
        output_path = atom_dir / filename
        _write_atom_jsonl(output_path=output_path, atom_id_prefix=atom_id_prefix, atoms=atoms)
        written_paths.append(output_path)
    return written_paths


def _write_atom_jsonl(*, output_path: Path, atom_id_prefix: str, atoms: list[dict[str, object]]) -> None:
    existing: list[dict[str, object]] = []
    if output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if not str(item.get("atom_id", "")).startswith(atom_id_prefix):
                existing.append(item)
    updated = [*existing, *atoms]
    output_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in updated),
        encoding="utf-8",
    )


def _load_claim_atoms_for_packet(*, packet_id: str, paths: HarnessPaths) -> list[ClaimAtom]:
    packet_id = safe_artifact_stem(packet_id, label="packet id")
    claims_path = paths.project_root / "data" / "atoms" / "claims.jsonl"
    if not claims_path.exists():
        raise FileNotFoundError(f"Missing claim atoms file: {claims_path}. Run extract-atoms first.")
    claims: list[ClaimAtom] = []
    for line in claims_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        atom = ClaimAtom.from_dict(json.loads(line))
        if atom.atom_id.startswith(f"{packet_id}-claim-"):
            claims.append(atom)
    return claims


def _export_promotion_candidates(*, packet_id: str, paths: HarnessPaths) -> tuple[Path, Path]:
    packet_id = safe_artifact_stem(packet_id, label="packet id")
    candidates = propose_promotion_candidates(
        packet_id=packet_id,
        claims=_load_claim_atoms_for_packet(packet_id=packet_id, paths=paths),
    )
    promotions_dir = paths.project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True, exist_ok=True)
    json_path = safe_child_path(promotions_dir, packet_id, ".json", label="packet id")
    markdown_path = safe_child_path(promotions_dir, packet_id, ".md", label="packet id")
    json_path.write_text(
        json.dumps([candidate.to_dict() for candidate in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_promotion_candidates_markdown(packet_id=packet_id, candidates=candidates),
        encoding="utf-8",
    )
    return json_path, markdown_path


def _load_promotion_candidates(path: Path) -> list[PromotionCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Promotion file must contain a JSON list: {path}")
    return [PromotionCandidate.from_dict(item) for item in payload]


def _packet_id_from_promotion_file(path: Path, candidates: list[PromotionCandidate]) -> str:
    if candidates:
        return candidates[0].packet_id
    return path.stem


def _export_wiki_patch_proposal(
    *,
    promotion_file: Path,
    paths: HarnessPaths,
    wiki_root: Path | None = None,
) -> tuple[Path, Path, WikiPatchProposal]:
    candidates = _load_promotion_candidates(promotion_file)
    packet_id = _packet_id_from_promotion_file(promotion_file, candidates)
    proposal = plan_wiki_patch_proposal(
        packet_id=packet_id,
        candidates=candidates,
        wiki_root=wiki_root or paths.wiki_root,
    )
    wiki_patches_dir = paths.project_root / "data" / "wiki_patches"
    wiki_patches_dir.mkdir(parents=True, exist_ok=True)
    packet_id = safe_artifact_stem(packet_id, label="packet id")
    json_path = safe_child_path(wiki_patches_dir, packet_id, ".json", label="packet id")
    markdown_path = safe_child_path(wiki_patches_dir, packet_id, ".md", label="packet id")
    json_path.write_text(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_wiki_patch_proposal_markdown(proposal), encoding="utf-8")
    return json_path, markdown_path, proposal


def _load_wiki_patch_proposal(path: Path) -> WikiPatchProposal:
    return WikiPatchProposal.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _apply_wiki_patch_file(
    *,
    patch_file: Path,
    paths: HarnessPaths,
    wiki_root: Path | None = None,
    dry_run: bool = True,
) -> WikiPatchApplyResult:
    proposal = _load_wiki_patch_proposal(patch_file)
    result = apply_wiki_patch_proposal(
        proposal=proposal,
        wiki_root=wiki_root or paths.wiki_root,
        dry_run=dry_run,
    )
    if not dry_run:
        _append_applied_wiki_patch_log(paths=paths, proposal=proposal, result=result)
        _mark_applied_promotion_candidates(paths=paths, proposal=proposal, result=result)
    return result


def _append_applied_wiki_patch_log(
    *,
    paths: HarnessPaths,
    proposal: WikiPatchProposal,
    result: WikiPatchApplyResult,
) -> None:
    if not result.applied_patch_ids:
        return
    operations_by_id = {operation.patch_id: operation for operation in proposal.operations}
    log_path = paths.project_root / "data" / "wiki_patches" / "applied.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        for patch_id in result.applied_patch_ids:
            operation = operations_by_id[patch_id]
            handle.write(
                json.dumps(
                    {
                        "created_at": created_at,
                        "proposal_id": proposal.proposal_id,
                        "packet_id": proposal.packet_id,
                        "patch_id": operation.patch_id,
                        "candidate_id": operation.candidate_id,
                        "target": operation.target,
                        "operation": operation.operation,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _mark_applied_promotion_candidates(
    *,
    paths: HarnessPaths,
    proposal: WikiPatchProposal,
    result: WikiPatchApplyResult,
) -> None:
    if not result.applied_patch_ids:
        return
    promotion_path = safe_child_path(paths.project_root / "data" / "promotions", proposal.packet_id, ".json", label="packet id")
    if not promotion_path.exists():
        return
    operations_by_id = {operation.patch_id: operation for operation in proposal.operations}
    applied_candidate_ids = {
        operations_by_id[patch_id].candidate_id
        for patch_id in result.applied_patch_ids
        if patch_id in operations_by_id
    }
    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return
    for candidate in payload:
        if isinstance(candidate, dict) and candidate.get("candidate_id") in applied_candidate_ids:
            candidate["status"] = "applied"
    promotion_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_all_promotion_payloads(paths: HarnessPaths) -> list[dict[str, object]]:
    promotions_dir = paths.project_root / "data" / "promotions"
    if not promotions_dir.exists():
        return []
    items: list[dict[str, object]] = []
    for path in sorted(promotions_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            items.extend(item for item in payload if isinstance(item, dict))
    return items


def _render_promotions_listing(*, paths: HarnessPaths, status: str | None = None) -> str:
    promotions = _load_all_promotion_payloads(paths)
    if status:
        promotions = [item for item in promotions if item.get("status") == status]
    lines = [_status_summary("promotions", promotions)]
    for item in promotions:
        lines.append(
            " ".join(
                [
                    str(item.get("candidate_id", "")),
                    f"packet={item.get('packet_id', '')}",
                    f"status={item.get('status', '')}",
                    f"kind={item.get('kind', '')}",
                    f"target={item.get('target_page', '')}",
                    f"confidence={item.get('confidence', '')}",
                ]
            )
        )
    return "\n".join(lines)


def _load_wiki_patch_records(paths: HarnessPaths) -> tuple[list[WikiPatchProposal], list[dict[str, object]]]:
    wiki_patches_dir = paths.project_root / "data" / "wiki_patches"
    proposals: list[WikiPatchProposal] = []
    applied: list[dict[str, object]] = []
    if not wiki_patches_dir.exists():
        return proposals, applied
    for path in sorted(wiki_patches_dir.glob("*.json")):
        proposals.append(_load_wiki_patch_proposal(path))
    applied_log = wiki_patches_dir / "applied.jsonl"
    if applied_log.exists():
        for line in applied_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                payload = json.loads(line)
                if isinstance(payload, dict):
                    applied.append(payload)
    return proposals, applied


def _render_wiki_patches_listing(*, paths: HarnessPaths, status: str | None = None) -> str:
    proposals, applied = _load_wiki_patch_records(paths)
    proposed_operations = [operation for proposal in proposals for operation in proposal.operations]
    applied_records = applied
    rows: list[dict[str, object]] = []
    if status in (None, "proposed"):
        rows.extend(
            {
                "patch_id": operation.patch_id,
                "candidate_id": operation.candidate_id,
                "target": operation.target,
                "operation": operation.operation,
                "status": operation.status,
            }
            for operation in proposed_operations
        )
    if status in (None, "applied"):
        rows.extend({**record, "status": "applied"} for record in applied_records)
    lines = [f"wiki_patches proposals={len(proposals)} operations={len(proposed_operations)} applied={len(applied_records)}"]
    for row in rows:
        lines.append(
            " ".join(
                [
                    str(row.get("patch_id", "")),
                    f"candidate={row.get('candidate_id', '')}",
                    f"status={row.get('status', '')}",
                    f"operation={row.get('operation', '')}",
                    f"target={row.get('target', '')}",
                ]
            )
        )
    return "\n".join(lines)


def _load_jsonl_dicts(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    items: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _lint_promotions(paths: HarnessPaths):
    patch_proposals, applied_patch_records = _load_wiki_patch_records(paths)
    atoms_dir = paths.project_root / "data" / "atoms"
    return lint_promotion_substrate(
        promotions=_load_all_promotion_payloads(paths),
        patch_proposals=patch_proposals,
        applied_patch_records=applied_patch_records,
        claim_atoms=_load_jsonl_dicts(atoms_dir / "claims.jsonl"),
        concept_atoms=_load_jsonl_dicts(atoms_dir / "concepts.jsonl"),
    )


def _export_semantic_lint_report(*, paths: HarnessPaths, report, report_id: str = "promotions-lint") -> tuple[Path, Path]:
    lint_dir = paths.project_root / "data" / "lint"
    lint_dir.mkdir(parents=True, exist_ok=True)
    json_path = safe_child_path(lint_dir, report_id, ".json", label="semantic lint report id")
    markdown_path = safe_child_path(lint_dir, report_id, ".md", label="semantic lint report id")
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_semantic_lint_report(report) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _status_summary(label: str, items: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    order = ["pending", "accepted", "rejected", "applied", "superseded", "proposed", "unknown"]
    parts = [f"{label} total={len(items)}"]
    for status in order:
        if status in counts:
            parts.append(f"{status}={counts.pop(status)}")
    for status in sorted(counts):
        parts.append(f"{status}={counts[status]}")
    return " ".join(parts)


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "artifact"


def _summary_routing_hints(*, summary_model: str | None, summary_budget: str | None) -> dict[str, object]:
    hints: dict[str, object] = {}
    if summary_model:
        hints["model"] = summary_model
    if summary_budget:
        hints["budget"] = summary_budget
    return hints


def _llm_safety_options(*, llm_redact: str, llm_max_input_chars: int, llm_allow_code_snippets: str) -> LLMInputSafetyOptions:
    return LLMInputSafetyOptions(
        redact=llm_redact == "on",
        max_input_chars=llm_max_input_chars,
        allow_code_snippets=llm_allow_code_snippets == "on",
    )


def _export_v2_summary_artifacts(
    *,
    session_id: str,
    packet_id: str,
    unit_title: str,
    goal: str,
    related_pages: list[str],
    summary_mode: str,
    summarizer_command: str | None,
    paths: HarnessPaths,
    agent_llm_router: AgentLLMRouter | None = None,
    routing_hints: dict[str, object] | None = None,
    summary_cache: bool = False,
    llm_safety: LLMInputSafetyOptions | None = None,
) -> tuple[Path, Path, Path]:
    raw_bundle = build_session_bundle(session_id=session_id, paths=paths)
    result = build_v2_summary_artifacts(
        raw_bundle=raw_bundle,
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
    return count_lint_issues(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-context-substrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract-session", help="Export one Hermes session to JSON")
    extract.add_argument("--session-id", required=True, help="Hermes session id to export")
    _add_project_root_argument(extract)

    extract_atoms = subparsers.add_parser(
        "extract-atoms",
        help="Extract claim, decision, entity, concept, and question atoms from v2 summary artifacts",
        description="Extract claim, decision, entity, concept, and question atoms from v2 summary artifacts.",
    )
    extract_atoms.add_argument("--packet-id", required=True, help="Packet id whose v2 summary artifacts should be processed")
    _add_project_root_argument(extract_atoms)

    propose_promotions = subparsers.add_parser("propose-promotions", help="Propose wiki promotion candidates from claim atoms")
    propose_promotions.add_argument("--packet-id", required=True, help="Packet id whose claim atoms should be evaluated")
    _add_project_root_argument(propose_promotions)

    plan_wiki_patches = subparsers.add_parser("plan-wiki-patches", help="Plan dry-run wiki patch proposals from promotion candidates")
    plan_wiki_patches.add_argument("--promotion-file", required=True, help="Path to data/promotions/<packet_id>.json")
    plan_wiki_patches.add_argument("--wiki-root", help="Wiki root used to inspect existing target pages")
    _add_project_root_argument(plan_wiki_patches)

    apply_wiki_patch = subparsers.add_parser("apply-wiki-patch", help="Apply or dry-run a wiki patch proposal")
    apply_wiki_patch.add_argument("--patch-file", required=True, help="Path to data/wiki_patches/<packet_id>.json")
    apply_wiki_patch.add_argument("--wiki-root", help="Wiki root containing target pages")
    apply_wiki_patch.add_argument(
        "--apply",
        action="store_true",
        help="Actually write safe managed-block changes. Default is dry-run.",
    )
    _add_project_root_argument(apply_wiki_patch)

    list_promotions = subparsers.add_parser("list-promotions", help="List promotion queue candidates")
    list_promotions.add_argument("--status", help="Optional promotion status filter, e.g. pending or applied")
    _add_project_root_argument(list_promotions)

    list_wiki_patches = subparsers.add_parser("list-wiki-patches", help="List wiki patch proposals and applied patch records")
    list_wiki_patches.add_argument("--status", choices=["proposed", "applied"], help="Optional patch status filter")
    _add_project_root_argument(list_wiki_patches)

    lint_promotions = subparsers.add_parser("lint-promotions", help="Run semantic lint checks on promotions and wiki patch records")
    lint_promotions.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 when semantic lint issues exist")
    lint_promotions.add_argument(
        "--report-id",
        default="promotions-lint",
        help="Filename stem for exported semantic lint reports",
    )
    _add_project_root_argument(lint_promotions)

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
    _add_project_root_argument(build_topic_map_parser)

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
        choices=["heuristic", "agent-llm", "hybrid", "custom-command"],
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
        "--include-promotions",
        action="store_true",
        help="Also run promotion semantic lint and export data/lint/promotions-lint.{json,md}",
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
        return handle_init_wiki_command(args=args)

    if args.command == "install-plugin":
        return handle_install_plugin_command(args=args)

    if args.command == "install-context-engine":
        return handle_install_context_engine_command(args=args)

    if args.command == "doctor":
        return handle_doctor_command(args=args)

    if args.command == "fresh-install-smoke":
        return handle_fresh_install_smoke_command(args=args)

    paths = HarnessPaths(project_root=Path(args.project_root).resolve())

    if args.command == "extract-session":
        return handle_extract_session_command(args=args, paths=paths)

    if args.command == "extract-atoms":
        return handle_extract_atoms_command(args=args, paths=paths, export_atoms=_export_atoms)

    if args.command == "propose-promotions":
        return handle_propose_promotions_command(
            args=args,
            paths=paths,
            export_promotion_candidates=_export_promotion_candidates,
        )

    if args.command == "plan-wiki-patches":
        return handle_plan_wiki_patches_command(
            args=args,
            paths=paths,
            export_wiki_patch_proposal=_export_wiki_patch_proposal,
        )

    if args.command == "apply-wiki-patch":
        return handle_apply_wiki_patch_command(
            args=args,
            paths=paths,
            apply_wiki_patch_file=_apply_wiki_patch_file,
        )

    if args.command == "list-promotions":
        return handle_list_promotions_command(
            args=args,
            paths=paths,
            render_promotions_listing=_render_promotions_listing,
        )

    if args.command == "list-wiki-patches":
        return handle_list_wiki_patches_command(
            args=args,
            paths=paths,
            render_wiki_patches_listing=_render_wiki_patches_listing,
        )

    if args.command == "lint-promotions":
        return handle_lint_promotions_command(
            args=args,
            paths=paths,
            lint_promotions=_lint_promotions,
            export_semantic_lint_report=_export_semantic_lint_report,
        )

    if args.command == "build-topic-map":
        return handle_build_topic_map_command(args=args, paths=paths)

    if args.command == "build-context-packet":
        return handle_build_context_packet_command(
            args=args,
            parser=parser,
            paths=paths,
            build_packet_from_session=build_packet_from_session,
            export_v2_summary_artifacts=_export_v2_summary_artifacts,
            summary_routing_hints=_summary_routing_hints,
            llm_safety_options=_llm_safety_options,
        )

    if args.command == "promote-packet-query":
        return handle_promote_packet_query_command(
            args=args,
            paths=paths,
            load_packet=_load_packet,
            register_promoted_page=_register_promoted_page,
        )

    if args.command == "promote-packet-plan":
        return handle_promote_packet_plan_command(
            args=args,
            paths=paths,
            load_packet=_load_packet,
            register_promoted_page=_register_promoted_page,
        )

    if args.command == "promote-unit-concept":
        return handle_promote_unit_concept_command(
            args=args,
            parser=parser,
            paths=paths,
            load_packet=_load_packet,
            register_promoted_page=_register_promoted_page,
        )

    if args.command == "promote-unit-architecture":
        return handle_promote_unit_architecture_command(
            args=args,
            parser=parser,
            paths=paths,
            load_packet=_load_packet,
            register_promoted_page=_register_promoted_page,
        )

    if args.command == "run-e2e-pipeline":
        return handle_run_e2e_pipeline_command(
            args=args,
            paths=paths,
            slugify=_slugify,
            upsert_index_entry=_upsert_index_entry,
            append_log_entry=_append_log_entry,
        )

    if args.command == "lint-wiki":
        return handle_lint_wiki_command(
            args=args,
            paths=paths,
            lint_promotions=_lint_promotions,
            export_semantic_lint_report=_export_semantic_lint_report,
        )

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
