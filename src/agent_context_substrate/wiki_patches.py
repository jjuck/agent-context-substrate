from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .promotions import PromotionCandidate
from .safe_paths import safe_wiki_target_path

MANAGED_CLAIMS_START = "<!-- acs:auto:claims:start -->"
MANAGED_CLAIMS_END = "<!-- acs:auto:claims:end -->"

ALPHA_WIKI_PATCH_OPERATIONS = frozenset({"create_page", "insert_claim_block", "append_section", "append_managed_section"})
EXPERIMENTAL_WIKI_PATCH_OPERATIONS = frozenset({"add_link", "mark_stale"})
FUTURE_WIKI_PATCH_OPERATIONS = frozenset(
    {"replace_section", "add_alias", "mark_deprecated", "merge_pages", "split_page"}
)


@dataclass(frozen=True)
class WikiPatchApplyResult:
    dry_run: bool
    applied_patch_ids: list[str]
    skipped_patch_ids: list[str]
    planned_patch_ids: list[str]
    skipped_reasons: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "applied_patch_ids": list(self.applied_patch_ids),
            "skipped_patch_ids": list(self.skipped_patch_ids),
            "planned_patch_ids": list(self.planned_patch_ids),
            "skipped_reasons": dict(self.skipped_reasons),
        }


@dataclass(frozen=True)
class WikiPatchOperation:
    patch_id: str
    candidate_id: str
    target: str
    operation: str
    rationale: str
    evidence: list[str]
    risk: str
    diff: dict[str, str]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "candidate_id": self.candidate_id,
            "target": self.target,
            "operation": self.operation,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "risk": self.risk,
            "diff": dict(self.diff),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WikiPatchOperation":
        return cls(
            patch_id=str(payload["patch_id"]),
            candidate_id=str(payload["candidate_id"]),
            target=str(payload["target"]),
            operation=str(payload["operation"]),
            rationale=str(payload["rationale"]),
            evidence=list(payload.get("evidence", [])),
            risk=str(payload["risk"]),
            diff={str(key): str(value) for key, value in dict(payload.get("diff", {})).items()},
            status=str(payload["status"]),
        )


@dataclass(frozen=True)
class WikiPatchProposal:
    proposal_id: str
    packet_id: str
    operations: list[WikiPatchOperation]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "packet_id": self.packet_id,
            "operations": [operation.to_dict() for operation in self.operations],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WikiPatchProposal":
        return cls(
            proposal_id=str(payload["proposal_id"]),
            packet_id=str(payload["packet_id"]),
            operations=[WikiPatchOperation.from_dict(item) for item in payload.get("operations", [])],
            status=str(payload["status"]),
        )


def plan_wiki_patch_proposal(
    *,
    packet_id: str,
    candidates: list[PromotionCandidate],
    wiki_root: Path,
) -> WikiPatchProposal:
    operations: list[WikiPatchOperation] = []
    for candidate in candidates:
        if candidate.status != "pending":
            continue
        index = len(operations) + 1
        target = _target_file_for_candidate(candidate)
        target_path = _safe_target_path(wiki_root=wiki_root, target=target)
        if target_path is None:
            target = "_review/untriaged.md"
            target_path = _safe_target_path(wiki_root=wiki_root, target=target)
        if target_path is None:
            continue
        existing_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        claim_block = _claim_block_for_candidate(candidate)
        before = _existing_claim_block(existing_text)
        operation = "insert_claim_block" if target_path.exists() else "create_page"
        after = claim_block if operation != "create_page" else _seed_page_for_candidate(candidate=candidate, target_path=target_path)
        operations.append(
            WikiPatchOperation(
                patch_id=f"{packet_id}-patch-{index}",
                candidate_id=candidate.candidate_id,
                target=target,
                operation=operation,
                rationale=candidate.reason,
                evidence=list(candidate.evidence),
                risk="low" if target_path.exists() else "medium",
                diff={"before": before, "after": after},
                status="proposed",
            )
        )
    return WikiPatchProposal(
        proposal_id=f"{packet_id}-wiki-patch-proposal",
        packet_id=packet_id,
        operations=operations,
        status="proposed",
    )


def render_wiki_patch_proposal_markdown(proposal: WikiPatchProposal) -> str:
    lines = [f"# Wiki Patch Proposal: {proposal.packet_id}", "", f"- Proposal id: `{proposal.proposal_id}`", f"- Status: `{proposal.status}`", ""]
    if not proposal.operations:
        lines.extend(["No wiki patch operations proposed.", ""])
        return "\n".join(lines)

    for operation in proposal.operations:
        lines.extend(
            [
                f"## {operation.patch_id}",
                "",
                f"- Candidate: `{operation.candidate_id}`",
                f"- Target: `{operation.target}`",
                f"- Operation: `{operation.operation}`",
                f"- Risk: `{operation.risk}`",
                f"- Status: `{operation.status}`",
                f"- Rationale: {operation.rationale}",
                "- Evidence:",
            ]
        )
        for evidence in operation.evidence:
            lines.append(f"  - `{evidence}`")
        lines.extend(
            [
                "",
                "### Proposed diff",
                "",
                "```diff",
                "--- before",
                operation.diff.get("before", ""),
                "+++ after",
                operation.diff.get("after", ""),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def apply_wiki_patch_proposal(
    *,
    proposal: WikiPatchProposal,
    wiki_root: Path,
    dry_run: bool = True,
) -> WikiPatchApplyResult:
    planned_patch_ids: list[str] = []
    applied_patch_ids: list[str] = []
    skipped_patch_ids: list[str] = []
    skipped_reasons: dict[str, str] = {}

    for operation in proposal.operations:
        if operation.status != "proposed":
            skipped_patch_ids.append(operation.patch_id)
            skipped_reasons[operation.patch_id] = f"status is {operation.status}, expected proposed"
            continue
        planned_patch_ids.append(operation.patch_id)
        target_path = _safe_target_path(wiki_root=wiki_root, target=operation.target)
        if target_path is None:
            skipped_patch_ids.append(operation.patch_id)
            skipped_reasons[operation.patch_id] = "unsafe target path"
            continue
        if operation.operation not in ALPHA_WIKI_PATCH_OPERATIONS:
            skipped_patch_ids.append(operation.patch_id)
            skipped_reasons[operation.patch_id] = f"unsupported operation: {operation.operation}"
            continue
        conflict_reason = _preflight_conflict_reason(operation=operation, target_path=target_path)
        if conflict_reason is not None:
            skipped_patch_ids.append(operation.patch_id)
            skipped_reasons[operation.patch_id] = conflict_reason
            continue
        if dry_run:
            continue
        _apply_operation(operation=operation, target_path=target_path)
        applied_patch_ids.append(operation.patch_id)

    return WikiPatchApplyResult(
        dry_run=dry_run,
        applied_patch_ids=applied_patch_ids,
        skipped_patch_ids=skipped_patch_ids,
        planned_patch_ids=planned_patch_ids,
        skipped_reasons=skipped_reasons,
    )


def _target_file_for_candidate(candidate: PromotionCandidate) -> str:
    target = candidate.target_page.strip()
    if not target:
        return "_review/untriaged.md"
    if target.endswith(".md") or "/" in target:
        return target
    return f"concepts/{target}.md"


def _claim_block_for_candidate(candidate: PromotionCandidate) -> str:
    primary_evidence = candidate.evidence[0] if candidate.evidence else "no-evidence"
    return "\n".join(
        [
            MANAGED_CLAIMS_START,
            f"- {candidate.proposed_change} `{primary_evidence}`",
            MANAGED_CLAIMS_END,
        ]
    )


def _seed_page_for_candidate(*, candidate: PromotionCandidate, target_path: Path) -> str:
    title = target_path.stem.replace("-", " ").title()
    return "\n".join(
        [
            "---",
            "status: seed",
            "maturity: 0.2",
            "review_needed: true",
            "---",
            f"# {title}",
            "",
            _claim_block_for_candidate(candidate),
            "",
        ]
    )


def _existing_claim_block(markdown: str) -> str:
    start = markdown.find(MANAGED_CLAIMS_START)
    end = markdown.find(MANAGED_CLAIMS_END)
    if start == -1 or end == -1 or end < start:
        return ""
    return markdown[start : end + len(MANAGED_CLAIMS_END)]


def _safe_target_path(*, wiki_root: Path, target: str) -> Path | None:
    return safe_wiki_target_path(wiki_root=wiki_root, target=target)


def _preflight_conflict_reason(*, operation: WikiPatchOperation, target_path: Path) -> str | None:
    if operation.operation == "create_page" and target_path.exists():
        return "conflict: create_page target already exists"
    if operation.operation not in {"insert_claim_block", "create_page"}:
        return None
    expected_before = operation.diff.get("before", "")
    current_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    current_before = _existing_claim_block(current_text)
    if current_before != expected_before:
        return "conflict: current managed claim block differs from proposal before"
    return None


def _apply_operation(*, operation: WikiPatchOperation, target_path: Path) -> None:
    after = operation.diff.get("after", "")
    if operation.operation == "create_page" and not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if after.startswith("---\n") or after.startswith("# "):
            target_path.write_text(after, encoding="utf-8")
        else:
            title = target_path.stem.replace("-", " ").title()
            target_path.write_text(f"# {title}\n\n{after}\n", encoding="utf-8")
        return

    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    if operation.operation in {"insert_claim_block", "create_page"}:
        updated = _replace_or_append_claim_block(markdown=existing, claim_block=after)
    elif operation.operation in {"append_section", "append_managed_section"}:
        updated = _append_to_section(
            markdown=existing,
            section=operation.diff.get("section", ""),
            addition=after,
        )
    else:
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(updated, encoding="utf-8")



def _append_to_section(*, markdown: str, section: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return markdown
    heading = section.strip().lstrip("# ").strip()
    if not heading:
        base = markdown.rstrip()
        return f"{base}\n\n{addition}\n" if base else f"{addition}\n"

    lines = markdown.splitlines()
    heading_index = None
    for index, line in enumerate(lines):
        if line.strip().lower() == f"## {heading}".lower():
            heading_index = index
            break
    if heading_index is None:
        base = markdown.rstrip()
        return f"{base}\n\n## {heading}\n{addition}\n" if base else f"## {heading}\n{addition}\n"

    insert_index = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if lines[index].startswith("## "):
            insert_index = index
            break
    while insert_index > heading_index + 1 and lines[insert_index - 1] == "":
        insert_index -= 1
    lines.insert(insert_index, addition)
    return "\n".join(lines) + "\n"


def _replace_or_append_claim_block(*, markdown: str, claim_block: str) -> str:
    start = markdown.find(MANAGED_CLAIMS_START)
    end = markdown.find(MANAGED_CLAIMS_END)
    if start != -1 and end != -1 and end >= start:
        end += len(MANAGED_CLAIMS_END)
        return markdown[:start] + claim_block + markdown[end:]
    base = markdown.rstrip()
    if not base:
        return claim_block + "\n"
    return base + "\n\n" + claim_block + "\n"
