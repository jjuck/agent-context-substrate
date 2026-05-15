from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.retrieval_proposals import search_promotions, search_wiki_patches


def test_proposal_search_helpers_return_promotions_patches_and_applied_logs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    promotions_dir = project_root / "data" / "promotions"
    patches_dir = project_root / "data" / "wiki_patches"
    promotions_dir.mkdir(parents=True)
    patches_dir.mkdir(parents=True)

    (promotions_dir / "packet-1.json").write_text(
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Claim atom should update durable summarization knowledge.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Hybrid summarizer uses heuristic spine before semantic interpretation.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (patches_dir / "packet-1.json").write_text(
        json.dumps(
            {
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "status": "proposed",
                "operations": [
                    {
                        "patch_id": "packet-1-patch-1",
                        "candidate_id": "packet-1-candidate-1",
                        "target": "concepts/summarization.md",
                        "operation": "insert_claim_block",
                        "rationale": "Apply hybrid summarizer claim into managed block.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {"before": "", "after": "Hybrid summarizer managed block."},
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (patches_dir / "applied.jsonl").write_text(
        json.dumps(
            {
                "created_at": "2026-05-07T00:00:00+00:00",
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "patch_id": "packet-1-patch-1",
                "candidate_id": "packet-1-candidate-1",
                "target": "concepts/summarization.md",
                "operation": "insert_claim_block",
                "note": "Hybrid summarizer claim applied.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    promotion_hits = search_promotions(["hybrid", "summarizer"], project_root)
    patch_hits = search_wiki_patches(["hybrid", "summarizer"], project_root)

    assert [hit.source_type for hit in promotion_hits] == ["promotion_candidate"]
    assert promotion_hits[0].source_path == "data/promotions/packet-1.json"
    assert promotion_hits[0].provenance == ["promotion:packet-1-candidate-1", "claim:packet-1-claim-1"]

    source_types = {hit.source_type for hit in patch_hits}
    assert source_types == {"wiki_patch", "applied_patch"}
    patch_hit = next(hit for hit in patch_hits if hit.source_type == "wiki_patch")
    applied_hit = next(hit for hit in patch_hits if hit.source_type == "applied_patch")
    assert patch_hit.provenance == ["wiki-patch:packet-1-patch-1", "claim:packet-1-claim-1"]
    assert applied_hit.provenance == ["applied-patch:packet-1-patch-1"]
