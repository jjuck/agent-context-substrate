from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.artifact_pipeline import (  # noqa: E402
    render_promotion_evidence_preview,
    render_promotions_listing,
    update_promotion_candidate_status,
)
from agent_context_substrate.paths import HarnessPaths  # noqa: E402


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
