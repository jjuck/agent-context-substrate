from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .wiki_patches import WikiPatchProposal


@dataclass(frozen=True)
class SemanticLintIssue:
    code: str
    severity: str
    ref: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "ref": self.ref,
            "message": self.message,
        }


@dataclass(frozen=True)
class SemanticLintReport:
    issues: list[SemanticLintIssue]

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.to_dict() for issue in self.issues]}


def lint_promotion_substrate(
    *,
    promotions: list[dict[str, object]],
    patch_proposals: list[WikiPatchProposal],
    applied_patch_records: list[dict[str, object]],
    claim_atoms: list[dict[str, object]] | None = None,
    concept_atoms: list[dict[str, object]] | None = None,
    promotion_backlog_threshold: int | None = None,
) -> SemanticLintReport:
    issues: list[SemanticLintIssue] = []
    promotion_candidate_ids = {str(candidate.get("candidate_id", "")) for candidate in promotions}
    applied_candidate_ids = {str(record.get("candidate_id", "")) for record in applied_patch_records}
    applied_patch_ids = {str(record.get("patch_id", "")) for record in applied_patch_records}

    for candidate in promotions:
        candidate_id = str(candidate.get("candidate_id", ""))
        ref = f"promotion:{candidate_id}"
        if not candidate.get("evidence"):
            issues.append(
                SemanticLintIssue(
                    code="promotion_missing_evidence",
                    severity="warning",
                    ref=ref,
                    message="Promotion candidate has no evidence refs.",
                )
            )
        if not str(candidate.get("target_page", "")).strip():
            issues.append(
                SemanticLintIssue(
                    code="promotion_missing_target_page",
                    severity="warning",
                    ref=ref,
                    message="Promotion candidate has no target_page and requires review.",
                )
            )
        if candidate.get("status") == "applied" and candidate_id not in applied_candidate_ids:
            issues.append(
                SemanticLintIssue(
                    code="applied_promotion_without_applied_patch",
                    severity="error",
                    ref=ref,
                    message="Promotion is marked applied but has no applied patch log record.",
                )
            )

    issues.extend(_lint_patch_proposals(
        patch_proposals,
        promotion_candidate_ids=promotion_candidate_ids,
        applied_patch_ids=applied_patch_ids,
    ))
    issues.extend(_lint_claim_atoms(claim_atoms or []))
    issues.extend(_lint_duplicate_concepts(concept_atoms or []))
    if promotion_backlog_threshold is not None:
        issues.extend(_lint_promotion_backlog(promotions, threshold=promotion_backlog_threshold))

    return SemanticLintReport(issues=issues)


def _lint_patch_proposals(
    patch_proposals: list[WikiPatchProposal],
    *,
    promotion_candidate_ids: set[str],
    applied_patch_ids: set[str],
) -> list[SemanticLintIssue]:
    issues: list[SemanticLintIssue] = []
    for proposal in patch_proposals:
        for operation in proposal.operations:
            ref = f"wiki_patch:{operation.patch_id}"
            if operation.candidate_id not in promotion_candidate_ids:
                issues.append(
                    SemanticLintIssue(
                        code="patch_without_candidate",
                        severity="error",
                        ref=ref,
                        message=(
                            "Wiki patch operation references a missing promotion candidate: "
                            f"{operation.candidate_id}."
                        ),
                    )
                )
            if operation.status == "applied" and operation.patch_id not in applied_patch_ids:
                issues.append(
                    SemanticLintIssue(
                        code="applied_patch_missing_log",
                        severity="error",
                        ref=ref,
                        message="Wiki patch operation is marked applied but has no applied patch log record.",
                    )
                )
    return issues


def _lint_claim_atoms(claim_atoms: list[dict[str, object]]) -> list[SemanticLintIssue]:
    issues: list[SemanticLintIssue] = []
    for claim in claim_atoms:
        atom_id = str(claim.get("atom_id", ""))
        if not claim.get("source_refs"):
            issues.append(
                SemanticLintIssue(
                    code="claim_without_source",
                    severity="error",
                    ref=f"claim:{atom_id}",
                    message="Claim atom has no source_refs.",
                )
            )
    return issues


def _lint_duplicate_concepts(concept_atoms: list[dict[str, object]]) -> list[SemanticLintIssue]:
    by_name: dict[str, list[str]] = defaultdict(list)
    for concept in concept_atoms:
        if str(concept.get("status", "active")) != "active":
            continue
        normalized = _normalize_name(str(concept.get("name", "")))
        if not normalized:
            continue
        by_name[normalized].append(str(concept.get("atom_id", "")))

    issues: list[SemanticLintIssue] = []
    for normalized, atom_ids in sorted(by_name.items()):
        if len(atom_ids) <= 1:
            continue
        issues.append(
            SemanticLintIssue(
                code="duplicate_concept",
                severity="warning",
                ref=f"concept:{normalized}",
                message=f"Active concept atoms duplicate the same normalized name: {', '.join(atom_ids)}.",
            )
        )
    return issues


def _lint_promotion_backlog(promotions: list[dict[str, object]], *, threshold: int) -> list[SemanticLintIssue]:
    pending_count = sum(1 for item in promotions if item.get("status") == "pending")
    if pending_count < threshold:
        return []
    return [
        SemanticLintIssue(
            code="promotion_backlog",
            severity="warning",
            ref="promotions:pending",
            message=f"Pending promotion backlog is {pending_count}, meeting or exceeding threshold {threshold}.",
        )
    ]


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def render_semantic_lint_report(report: SemanticLintReport) -> str:
    lines = [f"semantic_lint ok={report.ok} issues={len(report.issues)}"]
    for issue in report.issues:
        lines.append(f"{issue.severity} {issue.code} {issue.ref} - {issue.message}")
    return "\n".join(lines)
