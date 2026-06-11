from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .atoms import ClaimAtom


@dataclass(frozen=True)
class PromotionCandidate:
    candidate_id: str
    packet_id: str
    kind: str
    target_page: str
    reason: str
    evidence: list[str]
    proposed_change: str
    proposed_action: str
    confidence: float
    status: str
    category: str | None = None
    language: str | None = None
    page_type: str | None = None
    placement_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "packet_id": self.packet_id,
            "kind": self.kind,
            "target_page": self.target_page,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "proposed_change": self.proposed_change,
            "proposed_action": self.proposed_action,
            "confidence": self.confidence,
            "status": self.status,
        }
        if self.category is not None:
            payload["category"] = self.category
        if self.language is not None:
            payload["language"] = self.language
        if self.page_type is not None:
            payload["page_type"] = self.page_type
        if self.placement_reason is not None:
            payload["placement_reason"] = self.placement_reason
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionCandidate":
        return cls(
            candidate_id=str(payload["candidate_id"]),
            packet_id=str(payload["packet_id"]),
            kind=str(payload["kind"]),
            target_page=str(payload["target_page"]),
            reason=str(payload["reason"]),
            evidence=list(payload.get("evidence", [])),
            proposed_change=str(payload.get("proposed_change", "")),
            proposed_action=str(payload["proposed_action"]),
            confidence=float(payload["confidence"]),
            status=str(payload["status"]),
            category=_optional_string(payload.get("category")),
            language=_optional_string(payload.get("language")),
            page_type=_optional_string(payload.get("page_type")),
            placement_reason=_optional_string(payload.get("placement_reason")),
        )


def propose_promotion_candidates(*, packet_id: str, claims: list[ClaimAtom]) -> list[PromotionCandidate]:
    candidates: list[PromotionCandidate] = []
    for claim in claims:
        index = len(candidates) + 1
        target_page = _target_page_for_claim(claim)
        candidates.append(
            PromotionCandidate(
                candidate_id=f"{packet_id}-candidate-{index}",
                packet_id=packet_id,
                kind="wiki_update",
                target_page=target_page,
                reason=f"Claim atom {claim.atom_id} may update durable wiki knowledge.",
                evidence=[f"claim:{claim.atom_id}", *claim.source_refs],
                proposed_change=claim.text,
                proposed_action="update_existing" if target_page else "review_required",
                confidence=claim.confidence,
                status="pending",
            )
        )
    return candidates


def render_promotion_candidates_markdown(*, packet_id: str, candidates: list[PromotionCandidate]) -> str:
    lines = [f"# Promotion Candidates: {packet_id}", ""]
    if not candidates:
        lines.extend(["No promotion candidates.", ""])
        return "\n".join(lines)

    for candidate in candidates:
        lines.extend(
            [
                f"## {candidate.candidate_id}",
                "",
                f"- Kind: `{candidate.kind}`",
                f"- Target page: `{candidate.target_page or '(review required)'}`",
                f"- Proposed action: `{candidate.proposed_action}`",
                f"- Confidence: `{candidate.confidence}`",
                f"- Status: `{candidate.status}`",
                f"- Category: `{candidate.category or '(unspecified)'}`",
                f"- Page type: `{candidate.page_type or '(unspecified)'}`",
                f"- Reason: {candidate.reason}",
                f"- Proposed change: {candidate.proposed_change}",
                "- Evidence:",
            ]
        )
        for evidence in candidate.evidence:
            lines.append(f"  - `{evidence}`")
        lines.append("")
    return "\n".join(lines)


def _target_page_for_claim(claim: ClaimAtom) -> str:
    return claim.subjects[0] if claim.subjects else ""


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
