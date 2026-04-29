from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.context_packet import (  # noqa: E402
    build_context_packet,
    export_context_packet,
)
from agent_context_substrate.models import MicroSummary, RawSessionReference, UnitSummary  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402


def _sample_reference(message_ids: list[int]) -> RawSessionReference:
    return RawSessionReference(
        session_id="session-1",
        message_ids=message_ids,
        source="telegram",
        started_at="1776395277.0",
        ended_at=None,
        title="Harness planning",
    )


def _sample_micro(
    micro_id: str,
    message_ids: list[int],
    files: list[str],
    concepts: list[str],
    parent_unit_id: str = "unit-1",
) -> MicroSummary:
    return MicroSummary(
        micro_id=micro_id,
        session_id="session-1",
        message_ids=message_ids,
        summary=f"Summary for {micro_id}",
        why_it_matters=f"Why {micro_id} matters",
        artifacts=list(files),
        files=list(files),
        entities=["Hermes"],
        concepts=list(concepts),
        parent_unit_id=parent_unit_id,
        provenance=_sample_reference(message_ids),
    )


def test_build_context_packet_filters_to_relevant_micro_summaries() -> None:
    micro_a = _sample_micro(
        micro_id="micro-a",
        message_ids=[1, 2],
        files=["pyproject.toml", "README.md"],
        concepts=["context-packet"],
    )
    micro_b = _sample_micro(
        micro_id="micro-b",
        message_ids=[3],
        files=["src/agent_context_substrate/context_packet.py"],
        concepts=["summarization"],
    )
    unrelated = _sample_micro(
        micro_id="micro-other",
        message_ids=[4],
        files=["notes.txt"],
        concepts=["other"],
        parent_unit_id="unit-2",
    )
    unit = UnitSummary(
        unit_id="unit-1",
        session_id="session-1",
        title="Build context packet support",
        goal="Create a reusable resumption packet",
        decisions=["Keep the packet compact"],
        progress=[micro_a.summary, micro_b.summary],
        open_questions=["Should Markdown exports include raw message ids?"],
        micro_ids=["micro-a", "micro-b"],
        related_pages=["architectures/agent-context-substrate.md"],
        provenance=_sample_reference([1, 2, 3]),
    )

    packet = build_context_packet(
        packet_id="packet-1",
        task_title="Resume harness work",
        macro_context="Need a compact packet for future session recovery",
        unit_summary=unit,
        micro_summaries=[micro_a, micro_b, unrelated],
    )

    assert packet.packet_id == "packet-1"
    assert [summary.micro_id for summary in packet.micro_summaries] == ["micro-a", "micro-b"]
    assert [summary.unit_id for summary in packet.unit_summaries] == ["unit-1"]
    assert packet.critical_files == [
        "README.md",
        "pyproject.toml",
        "src/agent_context_substrate/context_packet.py",
    ]
    assert [pointer.message_ids for pointer in packet.raw_pointers] == [[1, 2], [3]]
    assert packet.open_questions == ["Should Markdown exports include raw message ids?"]


def test_export_context_packet_writes_json_and_markdown(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))
    paths = HarnessPaths(project_root=project_root)

    micro = _sample_micro(
        micro_id="micro-a",
        message_ids=[1, 2],
        files=["pyproject.toml"],
        concepts=["context-packet"],
    )
    unit = UnitSummary(
        unit_id="unit-1",
        session_id="session-1",
        title="Build context packet support",
        goal="Create a reusable resumption packet",
        decisions=["Keep the packet compact"],
        progress=[micro.summary],
        open_questions=["Should Markdown exports include raw message ids?"],
        micro_ids=["micro-a"],
        related_pages=["architectures/agent-context-substrate.md"],
        provenance=_sample_reference([1, 2]),
    )
    packet = build_context_packet(
        packet_id="packet-1",
        task_title="Resume harness work",
        macro_context="Need a compact packet for future session recovery",
        unit_summary=unit,
        micro_summaries=[micro],
    )

    json_path, markdown_path = export_context_packet(packet=packet, paths=paths)

    assert json_path == project_root / "data" / "exports" / "context_packets" / "packet-1.json"
    assert markdown_path == project_root / "data" / "exports" / "context_packets" / "packet-1.md"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["packet_id"] == "packet-1"
    assert payload["critical_files"] == ["pyproject.toml"]

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Context Packet: Resume harness work" in markdown
    assert "## Macro Context" in markdown
    assert "## Critical Files" in markdown
    assert "pyproject.toml" in markdown
