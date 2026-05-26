from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .atoms import (
    ClaimAtom,
    extract_claim_atoms,
    extract_concept_atoms,
    extract_decision_atoms,
    extract_entity_atoms,
    extract_question_atoms,
)
from .models import MicroSummaryV2
from .paths import HarnessPaths
from .promotions import (
    PromotionCandidate,
    propose_promotion_candidates,
    render_promotion_candidates_markdown,
)
from .safe_paths import safe_artifact_stem, safe_child_path
from .semantic_lint import lint_promotion_substrate, render_semantic_lint_report
from .wiki_patches import (
    WikiPatchApplyResult,
    WikiPatchProposal,
    apply_wiki_patch_proposal,
    plan_wiki_patch_proposal,
    render_wiki_patch_proposal_markdown,
)


def load_micro_summary_v2(path: Path) -> MicroSummaryV2:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return MicroSummaryV2.from_dict(payload)


def export_atoms(*, packet_id: str, paths: HarnessPaths) -> list[Path]:
    packet_id = safe_artifact_stem(packet_id, label="packet id")
    micro_path = safe_child_path(
        paths.exports_dir / "summaries",
        f"{packet_id}-micro-v2",
        ".json",
        label="summary artifact id",
    )
    if not micro_path.exists():
        raise FileNotFoundError(
            f"Missing v2 micro summary artifact: {micro_path}. Run build-context-packet --summary-mode first."
        )
    micro_summaries = [load_micro_summary_v2(micro_path)]
    atom_dir = paths.project_root / "data" / "atoms"
    atom_dir.mkdir(parents=True, exist_ok=True)
    exports = [
        (
            "claims.jsonl",
            f"{packet_id}-claim-",
            [atom.to_dict() for atom in extract_claim_atoms(packet_id=packet_id, micro_summaries=micro_summaries)],
        ),
        (
            "decisions.jsonl",
            f"{packet_id}-decision-",
            [atom.to_dict() for atom in extract_decision_atoms(packet_id=packet_id, micro_summaries=micro_summaries)],
        ),
        (
            "entities.jsonl",
            f"{packet_id}-entity-",
            [atom.to_dict() for atom in extract_entity_atoms(packet_id=packet_id, micro_summaries=micro_summaries)],
        ),
        (
            "concepts.jsonl",
            f"{packet_id}-concept-",
            [atom.to_dict() for atom in extract_concept_atoms(packet_id=packet_id, micro_summaries=micro_summaries)],
        ),
        (
            "questions.jsonl",
            f"{packet_id}-question-",
            [atom.to_dict() for atom in extract_question_atoms(packet_id=packet_id, micro_summaries=micro_summaries)],
        ),
    ]
    written_paths: list[Path] = []
    for filename, atom_id_prefix, atoms in exports:
        output_path = atom_dir / filename
        write_atom_jsonl(output_path=output_path, atom_id_prefix=atom_id_prefix, atoms=atoms)
        written_paths.append(output_path)
    return written_paths


def write_atom_jsonl(*, output_path: Path, atom_id_prefix: str, atoms: list[dict[str, object]]) -> None:
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


def load_claim_atoms_for_packet(*, packet_id: str, paths: HarnessPaths) -> list[ClaimAtom]:
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


def export_promotion_candidates(*, packet_id: str, paths: HarnessPaths) -> tuple[Path, Path]:
    packet_id = safe_artifact_stem(packet_id, label="packet id")
    candidates = propose_promotion_candidates(
        packet_id=packet_id,
        claims=load_claim_atoms_for_packet(packet_id=packet_id, paths=paths),
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


def load_promotion_candidates(path: Path) -> list[PromotionCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Promotion file must contain a JSON list: {path}")
    return [PromotionCandidate.from_dict(item) for item in payload]


def packet_id_from_promotion_file(path: Path, candidates: list[PromotionCandidate]) -> str:
    if candidates:
        return candidates[0].packet_id
    return path.stem


def export_wiki_patch_proposal(
    *,
    promotion_file: Path,
    paths: HarnessPaths,
    wiki_root: Path | None = None,
) -> tuple[Path, Path, WikiPatchProposal]:
    candidates = load_promotion_candidates(promotion_file)
    packet_id = packet_id_from_promotion_file(promotion_file, candidates)
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


def load_wiki_patch_proposal(path: Path) -> WikiPatchProposal:
    return WikiPatchProposal.from_dict(json.loads(path.read_text(encoding="utf-8")))


def apply_wiki_patch_file(
    *,
    patch_file: Path,
    paths: HarnessPaths,
    wiki_root: Path | None = None,
    dry_run: bool = True,
) -> WikiPatchApplyResult:
    proposal = load_wiki_patch_proposal(patch_file)
    result = apply_wiki_patch_proposal(
        proposal=proposal,
        wiki_root=wiki_root or paths.wiki_root,
        dry_run=dry_run,
    )
    if not dry_run:
        append_applied_wiki_patch_log(paths=paths, proposal=proposal, result=result)
        mark_applied_promotion_candidates(paths=paths, proposal=proposal, result=result)
    return result


def append_applied_wiki_patch_log(
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


def mark_applied_promotion_candidates(
    *,
    paths: HarnessPaths,
    proposal: WikiPatchProposal,
    result: WikiPatchApplyResult,
) -> None:
    if not result.applied_patch_ids:
        return
    promotion_path = safe_child_path(
        paths.project_root / "data" / "promotions",
        proposal.packet_id,
        ".json",
        label="packet id",
    )
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


def load_all_promotion_payloads(paths: HarnessPaths) -> list[dict[str, object]]:
    promotions_dir = paths.project_root / "data" / "promotions"
    if not promotions_dir.exists():
        return []
    items: list[dict[str, object]] = []
    for path in sorted(promotions_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            items.extend(item for item in payload if isinstance(item, dict))
    return items


PROMOTION_REVIEW_ACTION_STATUSES = {
    "accept": "accepted",
    "reject": "rejected",
    "supersede": "superseded",
    "apply": "applied",
}
PROMOTION_REVIEW_STATUSES = {"pending", "accepted", "rejected", "applied", "superseded"}


def normalize_promotion_review_status(*, status: str | None = None, action: str | None = None) -> str | None:
    if action and status:
        raise ValueError("Use either action or status, not both")
    if action:
        normalized_action = action.strip().lower()
        if normalized_action not in PROMOTION_REVIEW_ACTION_STATUSES:
            raise ValueError(
                f"Unsupported promotion action={action!r}; expected one of {sorted(PROMOTION_REVIEW_ACTION_STATUSES)}"
            )
        return PROMOTION_REVIEW_ACTION_STATUSES[normalized_action]
    if status:
        normalized_status = status.strip().lower()
        if normalized_status not in PROMOTION_REVIEW_STATUSES:
            raise ValueError(f"Unsupported promotion status={status!r}; expected one of {sorted(PROMOTION_REVIEW_STATUSES)}")
        return normalized_status
    return None


def find_promotion_candidate(
    *, paths: HarnessPaths, candidate_id: str
) -> tuple[Path, list[object], dict[str, object]]:
    promotions_dir = paths.project_root / "data" / "promotions"
    for path in sorted(promotions_dir.glob("*.json")) if promotions_dir.exists() else []:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and item.get("candidate_id") == candidate_id:
                return path, payload, item
    raise KeyError(f"Promotion candidate not found: {candidate_id}")


def update_promotion_candidate_status(
    *,
    paths: HarnessPaths,
    candidate_id: str,
    status: str | None = None,
    action: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
) -> tuple[Path, dict[str, object]]:
    normalized_status = normalize_promotion_review_status(status=status, action=action)
    if normalized_status is None:
        raise ValueError("Promotion review requires status or action")

    path, payload, item = find_promotion_candidate(paths=paths, candidate_id=candidate_id)
    item["status"] = normalized_status
    item["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if reviewer is not None and reviewer.strip():
        item["reviewer"] = reviewer.strip()
    if note is not None and note.strip():
        item["review_note"] = note.strip()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, dict(item)


def render_promotion_evidence_preview(*, paths: HarnessPaths, candidate_id: str) -> str:
    _, _, item = find_promotion_candidate(paths=paths, candidate_id=candidate_id)
    atom_lookup = load_atom_payloads_by_evidence_ref(paths)
    lines = [
        " ".join(
            [
                f"promotion {item.get('candidate_id', '')}",
                f"packet={item.get('packet_id', '')}",
                f"status={item.get('status', '')}",
                f"kind={item.get('kind', '')}",
            ]
        ),
        " ".join(
            [
                f"target={item.get('target_page', '')}",
                f"confidence={item.get('confidence', '')}",
                f"action={item.get('proposed_action', '')}",
            ]
        ),
        f"reason: {item.get('reason', '')}",
        f"proposed_change: {item.get('proposed_change', '')}",
        "evidence:",
    ]
    evidence = item.get("evidence", [])
    if isinstance(evidence, list) and evidence:
        for evidence_item in evidence:
            lines.extend(render_evidence_item_preview(evidence_item, atom_lookup=atom_lookup))
    else:
        lines.append("- (none)")
    return "\n".join(str(line) for line in lines)


def load_atom_payloads_by_evidence_ref(paths: HarnessPaths) -> dict[str, dict[str, object]]:
    atoms_dir = paths.project_root / "data" / "atoms"
    atom_files = {
        "claim": atoms_dir / "claims.jsonl",
        "decision": atoms_dir / "decisions.jsonl",
        "entity": atoms_dir / "entities.jsonl",
        "concept": atoms_dir / "concepts.jsonl",
        "question": atoms_dir / "questions.jsonl",
    }
    lookup: dict[str, dict[str, object]] = {}
    for prefix, path in atom_files.items():
        for atom in load_jsonl_dicts(path):
            atom_id = atom.get("atom_id")
            if not atom_id:
                continue
            lookup[str(atom_id)] = atom
            lookup[f"{prefix}:{atom_id}"] = atom
    return lookup


def render_evidence_item_preview(
    evidence_item: object,
    *,
    atom_lookup: dict[str, dict[str, object]],
) -> list[str]:
    label = evidence_label(evidence_item)
    lines = [f"- {label}"]
    atom = atom_lookup.get(label)
    if atom is None and ":" in label:
        atom = atom_lookup.get(label.split(":", 1)[1])
    if atom is None:
        return lines

    text = atom.get("text") or atom.get("name")
    if text:
        lines.append(f"  text: {text}")
    source_refs = atom.get("source_refs")
    if isinstance(source_refs, list) and source_refs:
        lines.append("  source_refs: " + ", ".join(str(ref) for ref in source_refs))
    details: list[str] = []
    if "confidence" in atom:
        details.append(f"confidence={atom.get('confidence')}")
    if atom.get("status"):
        details.append(f"status={atom.get('status')}")
    if atom.get("type"):
        details.append(f"type={atom.get('type')}")
    if details:
        lines.append("  " + " ".join(details))
    subjects = atom.get("subjects")
    if isinstance(subjects, list) and subjects:
        lines.append("  subjects: " + ", ".join(str(subject) for subject in subjects))
    return lines


def evidence_label(evidence_item: object) -> str:
    if isinstance(evidence_item, dict):
        label = evidence_item.get("id") or evidence_item.get("atom_id") or evidence_item.get("source")
        return str(label if label is not None else evidence_item)
    return str(evidence_item)


def render_promotions_listing(*, paths: HarnessPaths, status: str | None = None) -> str:
    promotions = load_all_promotion_payloads(paths)
    if status:
        promotions = [item for item in promotions if item.get("status") == status]
    lines = [status_summary("promotions", promotions)]
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


def load_wiki_patch_records(paths: HarnessPaths) -> tuple[list[WikiPatchProposal], list[dict[str, object]]]:
    wiki_patches_dir = paths.project_root / "data" / "wiki_patches"
    proposals: list[WikiPatchProposal] = []
    applied: list[dict[str, object]] = []
    if not wiki_patches_dir.exists():
        return proposals, applied
    for path in sorted(wiki_patches_dir.glob("*.json")):
        proposals.append(load_wiki_patch_proposal(path))
    applied_log = wiki_patches_dir / "applied.jsonl"
    if applied_log.exists():
        for line in applied_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                payload = json.loads(line)
                if isinstance(payload, dict):
                    applied.append(payload)
    return proposals, applied


def render_wiki_patches_listing(*, paths: HarnessPaths, status: str | None = None) -> str:
    proposals, applied = load_wiki_patch_records(paths)
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


def load_jsonl_dicts(path: Path) -> list[dict[str, object]]:
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


def lint_promotions(
    paths: HarnessPaths,
    *,
    include_promotions: bool = True,
    include_atoms: bool = True,
):
    patch_proposals, applied_patch_records = load_wiki_patch_records(paths) if include_promotions else ([], [])
    atoms_dir = paths.project_root / "data" / "atoms"
    return lint_promotion_substrate(
        promotions=load_all_promotion_payloads(paths) if include_promotions else [],
        patch_proposals=patch_proposals,
        applied_patch_records=applied_patch_records,
        claim_atoms=load_jsonl_dicts(atoms_dir / "claims.jsonl") if include_atoms else [],
        concept_atoms=load_jsonl_dicts(atoms_dir / "concepts.jsonl") if include_atoms else [],
    )


def export_semantic_lint_report(*, paths: HarnessPaths, report, report_id: str = "promotions-lint") -> tuple[Path, Path]:
    lint_dir = paths.project_root / "data" / "lint"
    lint_dir.mkdir(parents=True, exist_ok=True)
    json_path = safe_child_path(lint_dir, report_id, ".json", label="semantic lint report id")
    markdown_path = safe_child_path(lint_dir, report_id, ".md", label="semantic lint report id")
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_semantic_lint_report(report) + "\n", encoding="utf-8")
    return json_path, markdown_path


def status_summary(label: str, items: list[dict[str, object]]) -> str:
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
