from pathlib import Path
import argparse
import json
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.commands.build_context_packet import (  # noqa: E402
    build_llm_safety_options,
    build_summary_routing_hints,
    handle_build_context_packet_command,
)
from agent_context_substrate.packet_builder import PacketBuildOptions, PacketBuildResult  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402


class _FakePacket:
    micro_summaries = [object()]
    unit_summaries = [object()]
    critical_files = ["src/example.py"]


def test_build_context_packet_helpers_build_routing_hints_and_llm_safety_options() -> None:
    assert build_summary_routing_hints(summary_model="sonnet", summary_budget="small") == {
        "model": "sonnet",
        "budget": "small",
    }
    assert build_summary_routing_hints(summary_model=None, summary_budget=None) == {}

    safety = build_llm_safety_options(
        llm_redact="off",
        llm_max_input_chars=1234,
        llm_allow_code_snippets="on",
    )

    assert safety.redact is False
    assert safety.max_input_chars == 1234
    assert safety.allow_code_snippets is True


def test_build_context_packet_handler_uses_packet_builder_options(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    calls: list[PacketBuildOptions] = []

    def fake_packet_builder(*, paths, options):
        calls.append(options)
        return PacketBuildResult(
            packet=_FakePacket(),
            raw_export_path=paths.project_root / "data" / "exports" / "session-1.json",
            packet_json_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.json",
            packet_markdown_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.md",
        )

    def fake_export_v2_summary_artifacts(**_kwargs):
        raise AssertionError("v2 summary export should not run when summary_mode is omitted")

    exit_code = handle_build_context_packet_command(
        args=SimpleNamespace(
            session_id="session-1",
            packet_id="packet-1",
            task_title="Task",
            macro_context="Context",
            unit_title="Unit",
            goal="Goal",
            related_pages=["[[Page]]"],
            summary_mode=None,
            summarizer_command=None,
            summary_model=None,
            summary_budget=None,
            summary_cache="off",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=fake_export_v2_summary_artifacts,
        summary_routing_hints=lambda **_kwargs: {},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [
        PacketBuildOptions(
            session_id="session-1",
            packet_id="packet-1",
            task_title="Task",
            macro_context="Context",
            unit_title="Unit",
            goal="Goal",
            related_pages=["[[Page]]"],
        )
    ]
    assert "micro_summaries=1 unit_summaries=1 critical_files=1" in captured.out


def test_build_context_packet_handler_warns_when_v2_summary_falls_back(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    summary_dir = paths.project_root / "data" / "exports" / "summaries"
    summary_dir.mkdir(parents=True)
    evidence_dir = paths.project_root / "data" / "exports" / "evidence" / "session-1"
    evidence_dir.mkdir(parents=True)
    micro_path = summary_dir / "packet-1-micro-v2.json"
    unit_path = summary_dir / "packet-1-unit-v2.json"
    evidence_path = evidence_dir / "packet-1-micro-1.json"
    micro_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "mode": "heuristic",
                    "fallback_from": "custom-command",
                    "fallback_reason": "command_failed",
                }
            }
        ),
        encoding="utf-8",
    )
    unit_path.write_text(json.dumps({"metadata": {"mode": "heuristic"}}), encoding="utf-8")
    evidence_path.write_text(json.dumps({"session_id": "session-1"}), encoding="utf-8")

    def fake_packet_builder(*, paths, options):
        return PacketBuildResult(
            packet=_FakePacket(),
            raw_export_path=paths.project_root / "data" / "exports" / "session-1.json",
            packet_json_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.json",
            packet_markdown_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.md",
        )

    exit_code = handle_build_context_packet_command(
        args=SimpleNamespace(
            session_id="session-1",
            packet_id="packet-1",
            task_title="Task",
            macro_context="Context",
            unit_title="Unit",
            goal="Goal",
            related_pages=[],
            summary_mode="heuristic",
            summarizer_command=None,
            summary_model=None,
            summary_budget=None,
            summary_cache="off",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=lambda **_kwargs: (micro_path, unit_path, evidence_path),
        summary_routing_hints=lambda **_kwargs: {},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "WARNING" in captured.err
    assert "summary fallback" in captured.err
    assert "custom-command" in captured.err
    assert "command_failed" in captured.err
