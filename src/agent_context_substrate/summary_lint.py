from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import EvidenceBackedText, MicroSummaryV2, UnitSummaryV2
from .summarizer import _extract_files


@dataclass(frozen=True)
class SummaryLintIssue:
    code: str
    message: str
    field: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass(frozen=True)
class SummaryLintReport:
    issues: list[SummaryLintIssue]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "issue_count": self.issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _raw_message_ids(raw_bundle: dict[str, Any]) -> set[int]:
    return {int(message["id"]) for message in raw_bundle.get("messages", [])}


def _raw_text(raw_bundle: dict[str, Any]) -> str:
    return "\n".join(str(message.get("content") or "") for message in raw_bundle.get("messages", []))


def _lint_evidence_items(
    items: list[EvidenceBackedText],
    *,
    field: str,
    valid_message_ids: set[int],
) -> list[SummaryLintIssue]:
    issues: list[SummaryLintIssue] = []
    for item in items:
        if not item.evidence_message_ids:
            issues.append(
                SummaryLintIssue(
                    code="evidence_required",
                    field=field,
                    message=f"{field} item has no evidence_message_ids: {item.text}",
                )
            )
            continue
        unknown_ids = [message_id for message_id in item.evidence_message_ids if message_id not in valid_message_ids]
        if unknown_ids:
            issues.append(
                SummaryLintIssue(
                    code="evidence_exists",
                    field=field,
                    message=f"{field} item cites unknown message ids: {unknown_ids}",
                )
            )
    return issues


def lint_micro_summary_v2(summary: MicroSummaryV2, *, raw_bundle: dict[str, Any]) -> SummaryLintReport:
    valid_message_ids = _raw_message_ids(raw_bundle)
    issues: list[SummaryLintIssue] = []

    if not summary.recovery_summary.strip() or not summary.knowledge_summary.strip() or not summary.retrieval_summary.strip():
        issues.append(
            SummaryLintIssue(
                code="summary_not_empty",
                field="summary",
                message="recovery_summary, knowledge_summary, and retrieval_summary must be non-empty",
            )
        )

    for field, items in (
        ("decisions", summary.decisions),
        ("claims", summary.claims),
        ("action_items", summary.action_items),
    ):
        issues.extend(_lint_evidence_items(items, field=field, valid_message_ids=valid_message_ids))

    source_files = set(_extract_files(_raw_text(raw_bundle)))
    invented_files = [file_path for file_path in summary.files if file_path not in source_files]
    if invented_files:
        issues.append(
            SummaryLintIssue(
                code="no_new_files",
                field="files",
                message=f"summary cites files absent from raw bundle: {invented_files}",
            )
        )

    return SummaryLintReport(issues=issues)


def lint_unit_summary_v2(summary: UnitSummaryV2, *, micro_summaries: list[MicroSummaryV2]) -> SummaryLintReport:
    valid_micro_ids = {micro.micro_id for micro in micro_summaries}
    valid_message_ids = {message_id for micro in micro_summaries for message_id in micro.message_ids}
    issues: list[SummaryLintIssue] = []

    if not summary.title.strip() or not summary.goal.strip() or not summary.state.strip():
        issues.append(
            SummaryLintIssue(
                code="summary_not_empty",
                field="unit",
                message="title, goal, and state must be non-empty",
            )
        )

    for field, items in (
        ("decisions", summary.decisions),
        ("wiki_candidates", summary.wiki_candidates),
    ):
        issues.extend(_lint_evidence_items(items, field=field, valid_message_ids=valid_message_ids))

    unknown_micro_ids = [micro_id for micro_id in summary.micro_ids if micro_id not in valid_micro_ids]
    if unknown_micro_ids:
        issues.append(
            SummaryLintIssue(
                code="micro_reference_exists",
                field="micro_ids",
                message=f"unit summary references unknown micro ids: {unknown_micro_ids}",
            )
        )

    return SummaryLintReport(issues=issues)
