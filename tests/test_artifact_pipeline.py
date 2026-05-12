from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.artifact_pipeline import render_promotions_listing  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402


def test_artifact_pipeline_renders_promotion_queue_listing(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    promotions_dir = paths.project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True)
    (promotions_dir / "packet-1.json").write_text(
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "status": "pending",
                    "kind": "claim",
                    "target_page": "concepts/retrieval.md",
                    "confidence": 0.8,
                },
                {
                    "candidate_id": "packet-1-candidate-2",
                    "packet_id": "packet-1",
                    "status": "applied",
                    "kind": "claim",
                    "target_page": "concepts/old.md",
                    "confidence": 0.7,
                },
            ],
        ),
        encoding="utf-8",
    )

    listing = render_promotions_listing(paths=paths, status="pending")

    assert listing.splitlines() == [
        "promotions total=1 pending=1",
        "packet-1-candidate-1 packet=packet-1 status=pending kind=claim target=concepts/retrieval.md confidence=0.8",
    ]
