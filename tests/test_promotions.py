from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.atoms import ClaimAtom  # noqa: E402
from agent_context_substrate.promotions import (  # noqa: E402
    PromotionCandidate,
    propose_promotion_candidates,
    render_promotion_candidates_markdown,
)


def _claim() -> ClaimAtom:
    return ClaimAtom(
        atom_id="packet-1-claim-1",
        text="Heuristic summarizer should remain the default for privacy.",
        type="design_claim",
        subjects=["summarization"],
        source_refs=["packet:packet-1#micro-1", "hermes-session:session-1#messages=1,2"],
        confidence=0.75,
        status="active",
        first_seen="2026-05-07T00:00:00+00:00",
        last_seen="2026-05-07T00:00:00+00:00",
        supports=[],
        contradicts=[],
        supersedes=[],
    )


def test_propose_promotion_candidates_from_claim_atoms() -> None:
    candidates = propose_promotion_candidates(packet_id="packet-1", claims=[_claim()])

    assert candidates == [
        PromotionCandidate(
            candidate_id="packet-1-candidate-1",
            packet_id="packet-1",
            kind="wiki_update",
            target_page="summarization",
            reason="Claim atom packet-1-claim-1 may update durable wiki knowledge.",
            proposed_change="Heuristic summarizer should remain the default for privacy.",
            evidence=["claim:packet-1-claim-1", "packet:packet-1#micro-1", "hermes-session:session-1#messages=1,2"],
            proposed_action="update_existing",
            confidence=0.75,
            status="pending",
        )
    ]
    assert PromotionCandidate.from_dict(candidates[0].to_dict()) == candidates[0]


def test_promotion_candidate_loads_legacy_json_without_optional_fields() -> None:
    candidate = PromotionCandidate.from_dict(
        {
            "candidate_id": "packet-1-candidate-legacy",
            "packet_id": "packet-1",
            "kind": "concept_update",
            "target_page": "summarization",
            "reason": "Legacy candidate.",
            "evidence": ["claim:legacy"],
            "proposed_change": "Legacy concept update.",
            "proposed_action": "update_existing",
            "confidence": 0.7,
            "status": "pending",
        }
    )

    assert candidate.category is None
    assert candidate.language is None
    assert candidate.page_type is None
    assert candidate.placement_reason is None


def test_render_promotion_candidates_markdown() -> None:
    markdown = render_promotion_candidates_markdown(
        packet_id="packet-1",
        candidates=propose_promotion_candidates(packet_id="packet-1", claims=[_claim()]),
    )

    assert "# Promotion Candidates: packet-1" in markdown
    assert "packet-1-candidate-1" in markdown
    assert "Heuristic summarizer" in markdown
    assert "claim:packet-1-claim-1" in markdown
