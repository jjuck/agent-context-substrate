import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.commands.legacy_promotions import (  # noqa: E402
    load_context_packet,
    slugify_promotion_stem,
)
from agent_context_substrate.models import ContextPacket  # noqa: E402


def test_load_context_packet_reads_exported_packet_json(tmp_path: Path) -> None:
    packet = ContextPacket(
        packet_id="packet-1",
        task_title="Maintenance Refactor",
        macro_context="Keep CLI thin.",
        critical_files=["src/agent_context_substrate/cli.py"],
        open_questions=["Which seam is next?"],
    )
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet.to_dict(), ensure_ascii=False), encoding="utf-8")

    loaded = load_context_packet(packet_path)

    assert loaded == packet


def test_slugify_promotion_stem_matches_legacy_cli_defaults() -> None:
    assert slugify_promotion_stem("  Build Context Packet: Summary Glue!  ") == "build-context-packet-summary-glue"
    assert slugify_promotion_stem("한글 제목") == "artifact"
