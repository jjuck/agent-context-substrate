from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .promotions import PromotionCandidate
from .safe_paths import safe_wiki_target_path
from .wiki_config import load_wiki_config
from .wiki_placement import WikiPlacement, safe_resolved_wiki_placement
from .wiki_pages import collect_durable_wiki_pages

MANAGED_CLAIMS_START = "<!-- acs:auto:claims:start -->"
MANAGED_CLAIMS_END = "<!-- acs:auto:claims:end -->"

ALPHA_WIKI_PATCH_OPERATIONS = frozenset(
    {"create_page", "replace_page", "insert_claim_block", "append_section", "append_managed_section"}
)
EXPERIMENTAL_WIKI_PATCH_OPERATIONS = frozenset({"add_link", "mark_stale"})
FUTURE_WIKI_PATCH_OPERATIONS = frozenset(
    {"replace_section", "add_alias", "mark_deprecated", "merge_pages", "split_page"}
)
_TRANSIENT_SMOKE_TEST_PATTERN = re.compile(r"(?i)\bsmoke(?:-|\s*)test\b|\btest\b|테스트")


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
    candidate_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "candidate_id": self.candidate_id,
            "candidate_ids": list(self.candidate_ids or [self.candidate_id]),
            "target": self.target,
            "operation": self.operation,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "risk": self.risk,
            "diff": dict(self.diff),
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WikiPatchOperation":
        candidate_id = str(payload["candidate_id"])
        raw_candidate_ids = payload.get("candidate_ids")
        candidate_ids = [str(item) for item in raw_candidate_ids] if isinstance(raw_candidate_ids, list) else [candidate_id]
        return cls(
            patch_id=str(payload["patch_id"]),
            candidate_id=candidate_id,
            target=str(payload["target"]),
            operation=str(payload["operation"]),
            rationale=str(payload["rationale"]),
            evidence=list(payload.get("evidence", [])),
            risk=str(payload["risk"]),
            diff={str(key): str(value) for key, value in dict(payload.get("diff", {})).items()},
            status=str(payload["status"]),
            candidate_ids=candidate_ids,
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class WikiPatchProposal:
    proposal_id: str
    packet_id: str
    operations: list[WikiPatchOperation]
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "packet_id": self.packet_id,
            "operations": [operation.to_dict() for operation in self.operations],
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WikiPatchProposal":
        return cls(
            proposal_id=str(payload["proposal_id"]),
            packet_id=str(payload["packet_id"]),
            operations=[WikiPatchOperation.from_dict(item) for item in payload.get("operations", [])],
            status=str(payload["status"]),
            metadata=dict(payload.get("metadata", {})),
        )


def plan_wiki_patch_proposal(
    *,
    packet_id: str,
    candidates: list[PromotionCandidate],
    wiki_root: Path,
    write_mode: str = "managed",
    judge_mode: str = "off",
    judge_verdict: str | None = None,
) -> WikiPatchProposal:
    if write_mode not in {"managed", "flexible"}:
        raise ValueError(f"Unsupported wiki write_mode: {write_mode}")
    operations: list[WikiPatchOperation] = []
    if write_mode == "flexible":
        operations = _plan_flexible_wiki_patch_operations(
            packet_id=packet_id,
            candidates=candidates,
            wiki_root=wiki_root,
        )
        return WikiPatchProposal(
            proposal_id=f"{packet_id}-wiki-patch-proposal",
            packet_id=packet_id,
            operations=operations,
            status="proposed",
            metadata=_proposal_metadata(
                write_mode=write_mode,
                judge_mode=judge_mode,
                judge_verdict=judge_verdict,
            ),
        )

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
        diff = {"before": before, "after": after}
        operations.append(
            WikiPatchOperation(
                patch_id=f"{packet_id}-patch-{index}",
                candidate_id=candidate.candidate_id,
                candidate_ids=[candidate.candidate_id],
                target=target,
                operation=operation,
                rationale=candidate.reason,
                evidence=list(candidate.evidence),
                risk=_risk_for_operation(operation),
                diff=diff,
                status="proposed",
            )
        )
    return WikiPatchProposal(
        proposal_id=f"{packet_id}-wiki-patch-proposal",
        packet_id=packet_id,
        operations=operations,
        status="proposed",
        metadata=_proposal_metadata(
            write_mode=write_mode,
            judge_mode=judge_mode,
            judge_verdict=judge_verdict,
        ),
    )


def _plan_flexible_wiki_patch_operations(
    *,
    packet_id: str,
    candidates: list[PromotionCandidate],
    wiki_root: Path,
) -> list[WikiPatchOperation]:
    config = load_wiki_config(wiki_root)
    grouped: dict[str, tuple[str, Path, WikiPlacement, list[PromotionCandidate]]] = {}
    for candidate in candidates:
        if candidate.status != "pending":
            continue
        if _is_transient_validation_candidate(candidate):
            continue
        resolved = safe_resolved_wiki_placement(candidate=candidate, wiki_root=wiki_root, config=config)
        if resolved is None:
            continue
        placement, target_path = resolved
        group_key = str(target_path.resolve()).lower()
        if group_key not in grouped:
            grouped[group_key] = (placement.target, target_path, placement, [])
        grouped[group_key][3].append(candidate)

    operations: list[WikiPatchOperation] = []
    for target, target_path, placement, target_candidates in grouped.values():
        index = len(operations) + 1
        existing_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        operation = "replace_page" if target_path.exists() else "create_page"
        after = _flexible_page_revision_for_candidates(
            candidates=target_candidates,
            placement=placement,
            target_path=target_path,
            existing_text=existing_text,
            wiki_root=wiki_root,
        )
        primary_candidate = target_candidates[0]
        operations.append(
            WikiPatchOperation(
                patch_id=f"{packet_id}-patch-{index}",
                candidate_id=primary_candidate.candidate_id,
                candidate_ids=[candidate.candidate_id for candidate in target_candidates],
                target=target,
                operation=operation,
                rationale="; ".join(_dedupe([candidate.reason for candidate in target_candidates])),
                evidence=_candidate_evidence(target_candidates),
                risk=_risk_for_operation(operation),
                diff={
                    "before": existing_text,
                    "after": after,
                    "base_sha256": _sha256(existing_text),
                },
                status="proposed",
                metadata={"placement": placement.to_metadata()},
            )
        )
    return operations


def _is_transient_validation_candidate(candidate: PromotionCandidate) -> bool:
    text = " ".join([candidate.reason, candidate.proposed_change, candidate.target_page])
    return bool(_TRANSIENT_SMOKE_TEST_PATTERN.search(text))


def _remove_transient_validation_lines(markdown: str) -> str:
    lines = [
        line for line in markdown.splitlines()
        if not _TRANSIENT_SMOKE_TEST_PATTERN.search(line)
    ]
    return "\n".join(lines).rstrip() + ("\n" if markdown.endswith("\n") else "")


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
        policy_reason = _write_policy_rejection_reason(proposal=proposal, operation=operation)
        if policy_reason is not None:
            skipped_patch_ids.append(operation.patch_id)
            skipped_reasons[operation.patch_id] = policy_reason
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


def _proposal_metadata(*, write_mode: str, judge_mode: str, judge_verdict: str | None) -> dict[str, Any]:
    if write_mode != "flexible":
        return {}
    verdict = judge_verdict or "not_requested"
    return {
        "write_mode": "flexible",
        "judge_mode": judge_mode,
        "judge_verdict": verdict,
        "policy_verdict": "approved" if verdict == "approved" else "proposal_only",
        "rubric_advisories": [
            "Treat page-type sections as examples, not mandatory structure.",
            "Integrate new claims into readable wiki prose with evidence and links.",
            "Mark uncertainty, contradictions, and unresolved questions instead of hiding them.",
        ],
    }


def _risk_for_operation(operation: str) -> str:
    if operation == "insert_claim_block":
        return "low"
    if operation == "replace_page":
        return "medium"
    return "medium"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _flexible_page_revision_for_candidates(
    *,
    candidates: list[PromotionCandidate],
    placement: WikiPlacement,
    target_path: Path,
    existing_text: str,
    wiki_root: Path,
) -> str:
    title = placement.title or _title_for_target(target_path)
    evidence = _candidate_evidence(candidates)
    addition = _flexible_candidate_notes(candidates)
    if existing_text.strip():
        existing_text = _remove_transient_validation_lines(existing_text)
        base = _ensure_flexible_page_frontmatter(
            markdown=existing_text.rstrip(),
            placement=placement,
            evidence=evidence,
        )
        if all(candidate.proposed_change in existing_text for candidate in candidates):
            return base + "\n"
        return f"{base}\n\n{addition}\n"
    related_links = _related_wikilinks_for_candidates(candidates=candidates, wiki_root=wiki_root, target_path=target_path)
    frontmatter = [
        "---",
        f"title: {title}",
        f"lang: {placement.language}",
        f"type: {placement.page_type}",
    ]
    if placement.category:
        frontmatter.append(f"category: {placement.category}")
    frontmatter.extend(
        [
            f"status: {_status_for_placement(placement)}",
            "review_needed: true",
            f"sources: {json.dumps(evidence, ensure_ascii=False)}",
            "---",
        ]
    )
    return "\n".join(
        [
            *frontmatter,
            f"# {title}",
            "",
            "## Current Understanding",
            "",
            *_claim_lines(candidates),
            "",
            *_related_pages_section(related_links),
            "## Sources and Evidence",
            *_evidence_lines(evidence),
            "",
        ]
    )


def _flexible_candidate_notes(candidates: list[PromotionCandidate]) -> str:
    lines: list[str] = ["## Current Understanding", ""]
    lines.extend(_claim_lines(candidates))
    evidence = _candidate_evidence(candidates)
    lines.extend(["", "## Sources and Evidence", *_evidence_lines(evidence)])
    return "\n".join(lines)


def _ensure_flexible_page_frontmatter(*, markdown: str, placement: WikiPlacement, evidence: list[str]) -> str:
    required = {
        "title": placement.title,
        "lang": placement.language,
        "type": placement.page_type,
        "status": _status_for_placement(placement),
        "review_needed": "true",
    }
    if placement.category:
        required["category"] = placement.category
    sources = json.dumps(evidence, ensure_ascii=False)
    if not markdown.startswith("---\n"):
        frontmatter = [f"{key}: {value}" for key, value in required.items()]
        frontmatter.append(f"sources: {sources}")
        return "---\n" + "\n".join(frontmatter) + "\n---\n" + markdown.lstrip()

    lines = markdown.splitlines()
    end_index = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end_index is None:
        frontmatter = [f"{key}: {value}" for key, value in required.items()]
        frontmatter.append(f"sources: {sources}")
        return "---\n" + "\n".join(frontmatter) + "\n---\n" + markdown.lstrip()

    frontmatter_lines = list(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).lstrip()
    seen_keys: set[str] = set()
    updated_frontmatter: list[str] = []
    for line in frontmatter_lines:
        key = _frontmatter_key(line)
        if key:
            seen_keys.add(key)
        if key == "sources":
            updated_frontmatter.append(f"sources: {_merged_sources_json(line, evidence)}")
        else:
            updated_frontmatter.append(line)
    for key, value in required.items():
        if key not in seen_keys:
            updated_frontmatter.append(f"{key}: {value}")
    if "sources" not in seen_keys:
        updated_frontmatter.append(f"sources: {sources}")
    return "---\n" + "\n".join(updated_frontmatter) + "\n---\n" + body


def _status_for_placement(placement: WikiPlacement) -> str:
    return "review_needed" if placement.fallback and not placement.registered else "seed"


def _frontmatter_key(line: str) -> str:
    if ":" not in line:
        return ""
    key = line.split(":", 1)[0].strip()
    return key if key.replace("_", "").replace("-", "").isalnum() else ""


def _merged_sources_json(line: str, evidence: list[str]) -> str:
    raw_value = line.split(":", 1)[1].strip() if ":" in line else ""
    existing: list[str] = []
    if raw_value.startswith("["):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            existing = [str(item) for item in parsed]
    return json.dumps(_dedupe([*existing, *evidence]), ensure_ascii=False)


def _claim_lines(candidates: list[PromotionCandidate]) -> list[str]:
    return [f"- {claim}" for claim in _dedupe([candidate.proposed_change for candidate in candidates]) if claim]


def _candidate_evidence(candidates: list[PromotionCandidate]) -> list[str]:
    evidence: list[str] = []
    for candidate in candidates:
        evidence.extend(candidate.evidence)
    return _dedupe(evidence)


def _evidence_lines(evidence: list[str]) -> list[str]:
    if not evidence:
        return ["- review required before these claims are promoted"]
    return [f"- `{item}`" for item in evidence]


def _related_pages_section(related_links: list[str]) -> list[str]:
    if not related_links:
        return []
    return ["## Related Pages", "", *[f"- [[{link}]]" for link in related_links], ""]


def _related_wikilinks_for_candidates(
    *,
    candidates: list[PromotionCandidate],
    wiki_root: Path,
    target_path: Path,
) -> list[str]:
    existing_pages = _existing_wiki_page_stems(wiki_root)
    target_stem = target_path.stem
    related: list[str] = []
    for candidate in candidates:
        candidate_target = Path(_target_file_for_candidate(candidate)).stem
        if candidate_target in existing_pages and candidate_target != target_stem:
            related.append(candidate_target)
    if not related:
        related.extend(stem for stem in existing_pages if stem != target_stem)
    return _dedupe(related)[:3]


def _existing_wiki_page_stems(wiki_root: Path) -> set[str]:
    return {path.stem for path in collect_durable_wiki_pages(wiki_root)}


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _evidence_sentence(evidence: list[str]) -> str:
    if not evidence:
        return "Evidence: review required before this claim is promoted."
    rendered = ", ".join(f"`{item}`" for item in evidence)
    return f"Evidence: {rendered}"


def _title_for_target(target_path: Path) -> str:
    return target_path.stem.replace("-", " ").title()


def _seed_page_for_candidate(*, candidate: PromotionCandidate, target_path: Path) -> str:
    title = _title_for_target(target_path)
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
    if operation.operation == "replace_page":
        expected_hash = operation.diff.get("base_sha256", "")
        if not expected_hash:
            return "conflict: replace_page missing base hash"
        current_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        if _sha256(current_text) != expected_hash:
            return "conflict: current page hash differs from proposal base"
        return None
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
    if operation.operation == "replace_page":
        updated = after
    elif operation.operation in {"insert_claim_block", "create_page"}:
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


def _write_policy_rejection_reason(*, proposal: WikiPatchProposal, operation: WikiPatchOperation) -> str | None:
    if operation.operation == "replace_page" and proposal.metadata.get("write_mode") != "flexible":
        return "replace_page requires flexible write metadata"
    if not _requires_flexible_write_policy(proposal=proposal, operation=operation):
        return None
    if not operation.evidence:
        return "flexible write requires evidence"
    if proposal.metadata.get("judge_verdict") != "approved":
        return "flexible write requires approved judge verdict"
    return None


def _requires_flexible_write_policy(*, proposal: WikiPatchProposal, operation: WikiPatchOperation) -> bool:
    if operation.operation == "replace_page":
        return True
    return proposal.metadata.get("write_mode") == "flexible" and operation.operation == "create_page"



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
