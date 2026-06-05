from pathlib import Path
import argparse
import json
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.commands import build_context_packet as build_context_packet_module  # noqa: E402
from agent_context_substrate.commands.build_context_packet import (  # noqa: E402
    build_llm_safety_options,
    build_summary_routing_hints,
    export_v2_summary_artifacts,
    handle_build_context_packet_command,
)
from agent_context_substrate.packet_builder import PacketBuildOptions, PacketBuildResult  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402
from agent_context_substrate.session_bundle import SessionBundle, SessionMessage  # noqa: E402


class _FakePacket:
    micro_summaries = [object()]
    unit_summaries = [object()]
    critical_files = ["src/example.py"]


def test_build_context_packet_helpers_build_routing_hints_and_llm_safety_options() -> None:
    assert build_summary_routing_hints(summary_model="sonnet", summary_budget="small") == {
        "model": "sonnet",
        "budget": "small",
    }
    assert build_summary_routing_hints(
        summary_model=None,
        summary_budget=None,
        codex_cli_command="C:/OpenAI/Codex/bin/codex.exe",
        codex_project_root=Path("C:/project"),
    ) == {
        "codex_cli_command": "C:/OpenAI/Codex/bin/codex.exe",
        "codex_project_root": str(Path("C:/project")),
    }

    safety = build_llm_safety_options(
        llm_redact="off",
        llm_max_input_chars=1234,
        llm_allow_code_snippets="on",
        llm_path_policy="allow",
    )

    assert safety.redact is False
    assert safety.max_input_chars == 1234
    assert safety.allow_code_snippets is True
    assert safety.path_policy == "allow"


def test_export_v2_summary_artifacts_uses_typed_session_bundle(monkeypatch, tmp_path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    typed_bundle = SessionBundle(
        session_id="session-typed",
        source="telegram",
        title="Typed CLI",
        messages=[SessionMessage(id=1, role="user", content="typed summary", metadata={"timestamp": 1.0})],
    )
    observed: dict[str, object] = {}

    def fake_build_typed_session_bundle(*, session_id, paths):
        observed["session_id"] = session_id
        observed["paths"] = paths
        return typed_bundle

    def fake_build_v2_summary_artifacts(*, session_bundle, paths, options):
        observed["session_bundle"] = session_bundle
        observed["options"] = options
        micro_path = paths.project_root / "micro.json"
        unit_path = paths.project_root / "unit.json"
        evidence_path = paths.project_root / "evidence.json"
        judge_path = paths.project_root / "judge.json"
        return SimpleNamespace(as_tuple=lambda: (micro_path, unit_path, evidence_path), judge_path=judge_path)

    monkeypatch.setattr(build_context_packet_module, "build_typed_session_bundle", fake_build_typed_session_bundle)
    monkeypatch.setattr(build_context_packet_module, "build_v2_summary_artifacts", fake_build_v2_summary_artifacts)

    micro_path, unit_path, evidence_path = export_v2_summary_artifacts(
        session_id="session-typed",
        packet_id="packet-1",
        unit_title="Unit",
        goal="Goal",
        related_pages=["Architecture"],
        summary_mode="heuristic",
        summarizer_command=None,
        paths=paths,
    )

    assert observed["session_bundle"] is typed_bundle
    assert observed["session_id"] == "session-typed"
    assert observed["paths"] is paths
    assert observed["options"].session_id == "session-typed"
    assert micro_path.name == "micro.json"
    assert unit_path.name == "unit.json"
    assert evidence_path.name == "evidence.json"


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


def test_build_context_packet_handler_rejects_summary_judge_without_summary_mode(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")

    def fake_packet_builder(*, paths, options):
        raise AssertionError("packet export should not run when summary judge mode is invalid")

    with pytest.raises(SystemExit):
        handle_build_context_packet_command(
            args=SimpleNamespace(
                session_id="session-1",
                packet_id="packet-1",
                task_title="Task",
                macro_context="Context",
                unit_title="Unit",
                goal="Goal",
                related_pages=[],
                summary_mode=None,
                summarizer_command=None,
                summary_model=None,
                summary_budget=None,
                summary_cache="off",
                summary_judge_mode="hybrid",
            ),
            parser=argparse.ArgumentParser(prog="acs"),
            paths=paths,
            build_packet_from_session=fake_packet_builder,
            export_v2_summary_artifacts=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("no export")),
            summary_routing_hints=lambda **_kwargs: {},
        )

    captured = capsys.readouterr()
    assert "--summary-judge-mode requires --summary-mode" in captured.err


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


def test_build_context_packet_handler_passes_summary_judge_mode_to_export(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    captured: dict[str, object] = {}

    def fake_packet_builder(*, paths, options):
        return PacketBuildResult(
            packet=_FakePacket(),
            raw_export_path=paths.project_root / "data" / "exports" / "session-1.json",
            packet_json_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.json",
            packet_markdown_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.md",
        )

    def fake_export_v2_summary_artifacts(**kwargs):
        captured.update(kwargs)
        return (
            paths.project_root / "micro.json",
            paths.project_root / "unit.json",
            paths.project_root / "evidence.json",
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
            summary_budget="quality",
            summary_cache="off",
            summary_judge_mode="hybrid",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=fake_export_v2_summary_artifacts,
        summary_routing_hints=build_summary_routing_hints,
    )

    assert exit_code == 0
    assert captured["summary_judge_mode"] == "hybrid"
    assert captured["routing_hints"] == {"budget": "quality"}


def test_build_context_packet_handler_allows_codex_cli_and_passes_codex_hints(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    captured: dict[str, object] = {}

    def fake_packet_builder(*, paths, options):
        return PacketBuildResult(
            packet=_FakePacket(),
            raw_export_path=paths.project_root / "data" / "exports" / "session-1.json",
            packet_json_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.json",
            packet_markdown_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.md",
        )

    def fake_export_v2_summary_artifacts(**kwargs):
        captured.update(kwargs)
        return (
            paths.project_root / "micro.json",
            paths.project_root / "unit.json",
            paths.project_root / "evidence.json",
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
            summary_mode="codex-cli",
            summarizer_command=None,
            summary_model="gpt-5.4",
            summary_budget="balanced",
            summary_cache="off",
            summary_judge_mode="off",
            codex_cli_command="C:/OpenAI/Codex/bin/codex.exe",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=fake_export_v2_summary_artifacts,
        summary_routing_hints=build_summary_routing_hints,
    )

    assert exit_code == 0
    assert captured["summary_mode"] == "codex-cli"
    assert captured["routing_hints"] == {
        "model": "gpt-5.4",
        "budget": "balanced",
        "codex_cli_command": "C:/OpenAI/Codex/bin/codex.exe",
        "codex_project_root": str(paths.project_root),
    }


def test_build_context_packet_handler_prints_summary_judge_path(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    judge_path = paths.project_root / "data" / "exports" / "evals" / "packet-1-summary-judge.json"

    def fake_packet_builder(*, paths, options):
        return PacketBuildResult(
            packet=_FakePacket(),
            raw_export_path=paths.project_root / "data" / "exports" / "session-1.json",
            packet_json_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.json",
            packet_markdown_path=paths.project_root / "data" / "exports" / "context_packets" / "packet-1.md",
        )

    def fake_export_v2_summary_artifacts(**_kwargs):
        judge_path.parent.mkdir(parents=True)
        judge_path.write_text("{}", encoding="utf-8")
        return (
            paths.project_root / "micro.json",
            paths.project_root / "unit.json",
            paths.project_root / "evidence.json",
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
            summary_judge_mode="hybrid",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=fake_export_v2_summary_artifacts,
        summary_routing_hints=lambda **_kwargs: {},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(judge_path) in captured.out


def test_build_context_packet_handler_ignores_injected_judge_path_when_judge_mode_is_off(
    tmp_path,
    capsys,
) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    judge_path = paths.project_root / "data" / "exports" / "evals" / "packet-1-summary-judge.json"
    judge_path.parent.mkdir(parents=True)
    judge_path.write_text("{}", encoding="utf-8")

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
            summary_judge_mode="off",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=lambda **_kwargs: (
            paths.project_root / "micro.json",
            paths.project_root / "unit.json",
            paths.project_root / "evidence.json",
            judge_path,
        ),
        summary_routing_hints=lambda **_kwargs: {},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(judge_path) not in captured.out


def test_build_context_packet_handler_ignores_missing_injected_judge_path(tmp_path, capsys) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    judge_path = paths.project_root / "data" / "exports" / "evals" / "packet-1-summary-judge.json"

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
            summary_judge_mode="hybrid",
        ),
        parser=argparse.ArgumentParser(prog="acs"),
        paths=paths,
        build_packet_from_session=fake_packet_builder,
        export_v2_summary_artifacts=lambda **_kwargs: (
            paths.project_root / "micro.json",
            paths.project_root / "unit.json",
            paths.project_root / "evidence.json",
            judge_path,
        ),
        summary_routing_hints=lambda **_kwargs: {},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(judge_path) not in captured.out
