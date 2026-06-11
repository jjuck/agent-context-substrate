from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.artifact_pipeline import (  # noqa: E402
    apply_wiki_patch_file,
    render_promotion_evidence_preview,
    render_promotions_listing,
    update_promotion_candidate_status,
)
from agent_context_substrate.paths import HarnessPaths  # noqa: E402
from agent_context_substrate.promotions import PromotionCandidate  # noqa: E402
from agent_context_substrate.wiki_patches import plan_wiki_patch_proposal  # noqa: E402


def _write_promotion_file(paths: HarnessPaths) -> Path:
    promotions_dir = paths.project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True)
    path = promotions_dir / "packet-1.json"
    path.write_text(
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "claim",
                    "target_page": "concepts/retrieval.md",
                    "reason": "Useful retrieval claim.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Recovery mode should be exposed to agents.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "pending",
                },
                {
                    "candidate_id": "packet-1-candidate-2",
                    "packet_id": "packet-1",
                    "kind": "claim",
                    "target_page": "concepts/old.md",
                    "reason": "Already applied claim.",
                    "evidence": ["claim:packet-1-claim-2"],
                    "proposed_change": "Old claim.",
                    "proposed_action": "update_existing",
                    "confidence": 0.7,
                    "status": "applied",
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_artifact_pipeline_renders_promotion_queue_listing(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    _write_promotion_file(paths)

    listing = render_promotions_listing(paths=paths, status="pending")

    assert listing.splitlines() == [
        "promotions total=1 pending=1",
        "packet-1-candidate-1 packet=packet-1 status=pending kind=claim target=concepts/retrieval.md confidence=0.8",
    ]


def test_update_promotion_candidate_status_records_review_metadata(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    promotion_path = _write_promotion_file(paths)

    updated_path, updated = update_promotion_candidate_status(
        paths=paths,
        candidate_id="packet-1-candidate-1",
        status="accepted",
        note="Looks useful for the recovery search page.",
    )

    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert updated_path == promotion_path
    assert updated["status"] == "accepted"
    assert updated["review_note"] == "Looks useful for the recovery search page."
    assert "reviewed_at" in updated
    assert payload[0]["status"] == "accepted"
    assert payload[0]["review_note"] == "Looks useful for the recovery search page."
    assert payload[1]["status"] == "applied"


def test_update_promotion_candidate_status_accepts_review_actions(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    _write_promotion_file(paths)

    for action, expected_status in [
        ("accept", "accepted"),
        ("reject", "rejected"),
        ("supersede", "superseded"),
        ("apply", "applied"),
    ]:
        _, updated = update_promotion_candidate_status(
            paths=paths,
            candidate_id="packet-1-candidate-1",
            action=action,
            reviewer="reviewer-1",
            note=f"mark {action}",
        )
        assert updated["status"] == expected_status
        assert updated["reviewer"] == "reviewer-1"
        assert updated["review_note"] == f"mark {action}"


def test_render_promotion_evidence_preview_shows_review_context(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    _write_promotion_file(paths)
    atoms_dir = paths.project_root / "data" / "atoms"
    atoms_dir.mkdir(parents=True)
    (atoms_dir / "claims.jsonl").write_text(
        json.dumps(
            {
                "atom_id": "packet-1-claim-1",
                "text": "Recovery retrieval mode lets agents resume context from substrate artifacts.",
                "type": "design_claim",
                "subjects": ["retrieval", "recovery"],
                "source_refs": ["session:packet-1", "summary:micro"],
                "confidence": 0.92,
                "status": "active",
                "first_seen": "2026-05-15T00:00:00+00:00",
                "last_seen": "2026-05-15T00:00:00+00:00",
                "supports": [],
                "contradicts": [],
                "supersedes": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    preview = render_promotion_evidence_preview(
        paths=paths,
        candidate_id="packet-1-candidate-1",
    )

    assert preview.splitlines() == [
        "promotion packet-1-candidate-1 packet=packet-1 status=pending kind=claim",
        "target=concepts/retrieval.md confidence=0.8 action=update_existing",
        "reason: Useful retrieval claim.",
        "proposed_change: Recovery mode should be exposed to agents.",
        "evidence:",
        "- claim:packet-1-claim-1",
        "  text: Recovery retrieval mode lets agents resume context from substrate artifacts.",
        "  source_refs: session:packet-1, summary:micro",
        "  confidence=0.92 status=active type=design_claim",
        "  subjects: retrieval, recovery",
    ]


def test_apply_wiki_patch_file_marks_merged_candidates_and_registers_page(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    paths = HarnessPaths(project_root=project_root, wiki_root=wiki_root, home_dir=tmp_path)
    candidates = [
        PromotionCandidate(
            candidate_id="packet-1-candidate-1",
            packet_id="packet-1",
            kind="wiki_update",
            target_page="Agent Context Substrate",
            reason="Watcher claim should become durable.",
            evidence=["claim:packet-1-claim-1"],
            proposed_change="run_codex_watch_once finalizes due Codex threads.",
            proposed_action="update_existing",
            confidence=0.9,
            status="pending",
            category="codex-runtime-insight",
            page_type="runtime-note",
        ),
        PromotionCandidate(
            candidate_id="packet-1-candidate-2",
            packet_id="packet-1",
            kind="wiki_update",
            target_page="Agent Context Substrate",
            reason="Finalize claim should become durable.",
            evidence=["claim:packet-1-claim-2"],
            proposed_change="codex-finalize writes approved flexible wiki patches.",
            proposed_action="update_existing",
            confidence=0.91,
            status="pending",
            category="codex-runtime-insight",
            page_type="runtime-note",
        ),
    ]
    promotions_dir = project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True)
    promotion_path = promotions_dir / "packet-1.json"
    promotion_path.write_text(
        json.dumps([candidate.to_dict() for candidate in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=candidates,
        wiki_root=wiki_root,
        write_mode="flexible",
        judge_verdict="approved",
    )
    patch_dir = project_root / "data" / "wiki_patches"
    patch_dir.mkdir(parents=True)
    patch_path = patch_dir / "packet-1.json"
    patch_path.write_text(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    result = apply_wiki_patch_file(patch_file=patch_path, paths=paths, dry_run=False)

    assert result.applied_patch_ids == ["packet-1-patch-1"]
    page_text = (wiki_root / "Agent Context Substrate.md").read_text(encoding="utf-8")
    assert "run_codex_watch_once finalizes due Codex threads." in page_text
    assert "codex-finalize writes approved flexible wiki patches." in page_text
    assert "category: codex-runtime-insight" in page_text
    assert "type: runtime-note" in page_text
    updated_candidates = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert [candidate["status"] for candidate in updated_candidates] == ["applied", "applied"]
    applied_records = [
        json.loads(line)
        for line in (patch_dir / "applied.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert applied_records[0]["candidate_id"] == "packet-1-candidate-1"
    assert applied_records[0]["candidate_ids"] == ["packet-1-candidate-1", "packet-1-candidate-2"]
    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "## Codex Runtime Insight" in index_text
    assert "[[Agent Context Substrate]]" in index_text
    assert "Agent Context Substrate.md" in (wiki_root / "log.md").read_text(encoding="utf-8")


def test_apply_wiki_patch_file_registers_uncategorized_root_page(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    paths = HarnessPaths(project_root=project_root, wiki_root=wiki_root, home_dir=tmp_path)
    candidate = PromotionCandidate(
        candidate_id="packet-1-candidate-1",
        packet_id="packet-1",
        kind="wiki_update",
        target_page="Hybrid Memory",
        reason="Root-level knowledge should become durable.",
        evidence=["claim:packet-1-claim-1"],
        proposed_change="Hybrid Memory pages should use metadata instead of fixed folders.",
        proposed_action="update_existing",
        confidence=0.91,
        status="pending",
    )
    promotions_dir = project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True)
    (promotions_dir / "packet-1.json").write_text(
        json.dumps([candidate.to_dict()], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[candidate],
        wiki_root=wiki_root,
        write_mode="flexible",
        judge_verdict="approved",
    )
    patch_dir = project_root / "data" / "wiki_patches"
    patch_dir.mkdir(parents=True)
    patch_path = patch_dir / "packet-1.json"
    patch_path.write_text(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    result = apply_wiki_patch_file(patch_file=patch_path, paths=paths, dry_run=False)

    assert result.applied_patch_ids == ["packet-1-patch-1"]
    assert (wiki_root / "Hybrid Memory.md").is_file()
    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "## Unclassified / Review Needed" in index_text
    assert "[[Hybrid Memory]]" in index_text
    assert "Hybrid Memory.md" in (wiki_root / "log.md").read_text(encoding="utf-8")
