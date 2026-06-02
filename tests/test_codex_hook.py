from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import json
import os
import subprocess
import sys

from agent_context_substrate.codex_hook import (
    CodexHookCommandRunnerResult,
    build_codex_stop_finalize_decision,
    run_codex_stop_finalize_hook,
)


def _write_plugin_config(plugin_root: Path, *, project_root: Path, wiki_root: Path, codex_home: Path) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "local_config.json").write_text(
        (
            "{"
            f'"project_root": {str(project_root)!r}, '
            f'"wiki_root": {str(wiki_root)!r}, '
            f'"codex_home": {str(codex_home)!r}'
            "}"
        ).replace("'", '"'),
        encoding="utf-8",
    )


def test_stop_hook_decision_builds_codex_finalize_command_for_project_thread(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    _write_plugin_config(plugin_root, project_root=project_root, wiki_root=wiki_root, codex_home=codex_home)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "thread-1",
        "cwd": str(project_root / "subdir"),
    }

    decision = build_codex_stop_finalize_decision(
        payload=payload,
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is True
    assert decision.command == [
        "python",
        "-m",
        "agent_context_substrate.cli",
        "codex-finalize",
        "--thread-id",
        "thread-1",
        "--project-root",
        str(project_root),
        "--wiki-root",
        str(wiki_root),
        "--codex-home",
        str(codex_home),
    ]
    assert decision.cwd == project_root


def test_stop_hook_decision_skips_non_project_cwd(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    _write_plugin_config(plugin_root, project_root=project_root, wiki_root=wiki_root, codex_home=codex_home)

    decision = build_codex_stop_finalize_decision(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(tmp_path / "other"),
        },
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is False
    assert decision.skip_reason == "cwd outside configured project_root"


def test_stop_hook_runner_never_blocks_codex_on_finalize_failure(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    _write_plugin_config(plugin_root, project_root=project_root, wiki_root=wiki_root, codex_home=codex_home)
    calls: list[list[str]] = []

    def runner(command: list[str], *, cwd: Path, timeout_seconds: int) -> CodexHookCommandRunnerResult:
        calls.append(command)
        return CodexHookCommandRunnerResult(returncode=7, stdout="", stderr="boom")

    output = run_codex_stop_finalize_hook(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
        runner=runner,
    )

    assert calls
    assert output["continue"] is True
    assert "systemMessage" in output


def test_stop_hook_success_marks_watcher_state_processed(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    rollout_path = codex_home / "sessions" / "rollout-thread-1.jsonl"
    rollout_path.parent.mkdir(parents=True)
    rollout_path.write_text('{"payload":{"type":"user_message","message":"hello"}}\n', encoding="utf-8")
    _write_plugin_config(plugin_root, project_root=project_root, wiki_root=wiki_root, codex_home=codex_home)

    def runner(command: list[str], *, cwd: Path, timeout_seconds: int) -> CodexHookCommandRunnerResult:
        return CodexHookCommandRunnerResult(returncode=0, stdout="", stderr="")

    output = run_codex_stop_finalize_hook(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
        runner=runner,
    )

    state_path = project_root / "data" / "index" / "codex_watcher_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert output["continue"] is True
    assert state["thread-1"]["rollout_path"] == str(rollout_path)


def test_packaged_stop_hook_script_accepts_utf8_stdin_on_windows_paths(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project-\uac00"
    wiki_root = tmp_path / "wiki-\ub098"
    codex_home = tmp_path / "codex"
    rollout_path = codex_home / "sessions" / "rollout-thread-utf8.jsonl"
    rollout_path.parent.mkdir(parents=True)
    project_root.mkdir()
    wiki_root.mkdir()
    plugin_root.mkdir()
    rollout_path.write_text('{"payload":{"type":"user_message","message":"hello"}}\n', encoding="utf-8")
    (plugin_root / "local_config.json").write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "wiki_root": str(wiki_root),
                "codex_home": str(codex_home),
                "python_executable": sys.executable,
                "python_path_entries": [str(Path(__file__).resolve().parents[1] / "src")],
                "hook_timeout_seconds": 60,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    script_path = (
        files("agent_context_substrate")
        / "assets"
        / "codex_plugin"
        / "agent-context-substrate"
        / "hooks"
        / "codex_stop_finalize.py"
    )
    payload = json.dumps(
        {
            "hook_event_name": "Stop",
            "session_id": "thread-utf8",
            "cwd": str(project_root),
            "last_assistant_message": "\uc815\ub9ac \uc644\ub8cc",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    env = {
        **{key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        "PLUGIN_ROOT": str(plugin_root),
    }

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        input=payload,
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )

    state = json.loads((project_root / "data" / "index" / "codex_watcher_state.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (project_root / "data" / "index" / "codex_hook_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert completed.returncode == 0
    assert json.loads(completed.stdout.decode("utf-8")) == {"continue": True}
    assert state["thread-utf8"]["rollout_path"] == str(rollout_path)
    assert events[-1]["status"] == "finalized"
    assert events[-1]["session_id"] == "thread-utf8"
