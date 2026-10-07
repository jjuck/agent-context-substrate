from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import json
import os
import subprocess
import sys
import shutil

import pytest

from agent_context_substrate.codex_hook import (
    CodexHookCommandRunnerResult,
    build_codex_stop_finalize_decision,
    run_codex_stop_finalize_hook,
)


def _write_plugin_config(plugin_root: Path, *, project_root: Path, wiki_root: Path, codex_home: Path) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "local_config.json").write_text(
        json.dumps({"project_root": str(project_root), "wiki_root": str(wiki_root),
                    "codex_home": str(codex_home)}),
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
    assert events[-1]["plugin_root"] == str(plugin_root)
    assert Path(events[-1]["script_path"]).name == "codex_stop_finalize.py"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows commandWindows launcher regression")
@pytest.mark.parametrize("shell", ["powershell.exe", "cmd.exe"])
def test_packaged_windows_command_launches_from_unrelated_cwd(tmp_path: Path, shell: str) -> None:
    """Exercise the shipped command, including shell parsing and plugin-root lookup."""
    asset = files("agent_context_substrate") / "assets/codex_plugin/agent-context-substrate"
    plugin_root = tmp_path / "plugin 한글 & apostrophe's $root %value%"
    (plugin_root / "hooks").mkdir(parents=True)
    shutil.copyfile(asset / "hooks/codex_stop_finalize.py", plugin_root / "hooks/codex_stop_finalize.py")
    project_root = tmp_path / "project"
    project_root.mkdir()
    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    (plugin_root / "local_config.json").write_text(json.dumps({
        "project_root": str(project_root), "wiki_root": str(tmp_path / "wiki")
    }), encoding="utf-8")
    command = json.loads((asset / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"][0]["commandWindows"]
    env = {**os.environ, "PLUGIN_ROOT": str(plugin_root),
           "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")}
    if shell == "cmd.exe":
        # cmd /s /c needs an intact command line; list2cmdline would escape its inner quotes.
        argv = subprocess.list2cmdline([shutil.which(shell), "/d", "/s", "/c"]) + ' "' + command + '"'
    else:
        argv = [shell, "-NoProfile", "-NonInteractive", "-Command", command]
    completed = subprocess.run(argv, input=json.dumps({
        "hook_event_name": "Stop", "session_id": "launcher-check", "cwd": str(cwd)
    }).encode(), cwd=cwd, env=env, capture_output=True, timeout=20, check=False)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert json.loads(completed.stdout) == {"continue": True}
    event = json.loads((project_root / "data/index/codex_hook_events.jsonl").read_text(encoding="utf-8"))
    assert event["status"] == "skipped"
    assert event["detail"] == "cwd outside configured project_root"
    assert event["plugin_root"] == str(plugin_root)


def test_packaged_hook_failure_is_ascii_json_with_utf8_child_output(tmp_path: Path) -> None:
    asset = files("agent_context_substrate") / "assets/codex_plugin/agent-context-substrate"
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    project_root.mkdir()
    plugin_root.mkdir()
    # A failing CLI fixture proves stderr survives Windows code pages and produces valid JSON.
    module = tmp_path / "module/agent_context_substrate"
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "cli.py").write_text("import sys\nprint('실패: 경로 확인', file=sys.stderr)\nsys.exit(7)\n", encoding="utf-8")
    (plugin_root / "local_config.json").write_text(json.dumps({
        "project_root": str(project_root), "wiki_root": str(tmp_path / "wiki"),
        "python_executable": sys.executable, "python_path_entries": [str(module.parent)]
    }), encoding="utf-8")
    completed = subprocess.run([sys.executable, str(asset / "hooks/codex_stop_finalize.py")],
        input=json.dumps({"hook_event_name": "Stop", "session_id": "failure-check", "cwd": str(project_root)}).encode(),
        env={**os.environ, "PLUGIN_ROOT": str(plugin_root), "PYTHONIOENCODING": "ascii"},
        capture_output=True, timeout=20, check=False)
    assert completed.returncode == 0
    output = json.loads(completed.stdout.decode("ascii"))
    assert output["continue"] is True
    assert "실패: 경로 확인" in output["systemMessage"]
    event = json.loads((project_root / "data/index/codex_hook_events.jsonl").read_text(encoding="utf-8"))
    assert event["status"] == "failed"
    assert "실패: 경로 확인" in event["detail"]
