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


def _write_plugin_config(plugin_root: Path, *, project_root: Path, wiki_root: Path | str, codex_home: Path) -> None:
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


def test_stop_hook_prefers_env_wiki_root_over_local_config(tmp_path: Path, monkeypatch) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    config_wiki_root = tmp_path / "config-wiki"
    env_wiki_root = tmp_path / "env-wiki"
    codex_home = tmp_path / "codex"
    _write_plugin_config(plugin_root, project_root=project_root, wiki_root=config_wiki_root, codex_home=codex_home)
    monkeypatch.setenv("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", str(env_wiki_root))

    decision = build_codex_stop_finalize_decision(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is True
    assert decision.command[decision.command.index("--wiki-root") + 1] == str(env_wiki_root.resolve(strict=False))


def test_stop_hook_expands_template_wiki_root_from_local_config(tmp_path: Path, monkeypatch) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    home = tmp_path / "home"
    codex_home = tmp_path / "codex"
    _write_plugin_config(
        plugin_root,
        project_root=project_root,
        wiki_root="%USERPROFILE%\\Documents\\LLM Wiki",
        codex_home=codex_home,
    )
    monkeypatch.setenv("USERPROFILE", str(home))

    decision = build_codex_stop_finalize_decision(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is True
    assert decision.command[decision.command.index("--wiki-root") + 1] == str((home / "Documents" / "LLM Wiki").resolve(strict=False))


def test_stop_hook_skips_when_wiki_root_cannot_be_resolved(tmp_path: Path, monkeypatch) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    codex_home = tmp_path / "codex"
    _write_plugin_config(
        plugin_root,
        project_root=project_root,
        wiki_root="%MISSING_ACS_WIKI_ROOT%\\LLM Wiki",
        codex_home=codex_home,
    )
    monkeypatch.delenv("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", raising=False)
    monkeypatch.delenv("WIKI_PATH", raising=False)

    decision = build_codex_stop_finalize_decision(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is False
    assert decision.skip_reason == "no wiki root resolved"


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


def test_stop_hook_decision_passes_summary_config_to_codex_finalize(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    codex_cli = tmp_path / "Codex" / "bin" / "codex.exe"
    plugin_root.mkdir(parents=True)
    (plugin_root / "local_config.json").write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "wiki_root": str(wiki_root),
                "codex_home": str(codex_home),
                "summary_mode": "auto",
                "summary_cache": True,
                "summary_model": "gpt-5.4",
                "summary_budget": "balanced",
                "codex_cli_command": str(codex_cli),
                "llm_redact": False,
                "llm_max_input_chars": 2048,
                "llm_allow_code_snippets": True,
                "llm_path_policy": "allow",
            }
        ),
        encoding="utf-8",
    )

    decision = build_codex_stop_finalize_decision(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is True
    assert "--summary-mode" in decision.command
    assert decision.command[decision.command.index("--summary-mode") + 1] == "auto"
    assert "--summary-cache" in decision.command
    assert decision.command[decision.command.index("--summary-cache") + 1] == "on"
    assert "--summary-model" in decision.command
    assert decision.command[decision.command.index("--summary-model") + 1] == "gpt-5.4"
    assert "--summary-budget" in decision.command
    assert decision.command[decision.command.index("--summary-budget") + 1] == "balanced"
    assert "--codex-cli-command" in decision.command
    assert decision.command[decision.command.index("--codex-cli-command") + 1] == str(codex_cli)
    assert "--llm-redact" in decision.command
    assert decision.command[decision.command.index("--llm-redact") + 1] == "off"
    assert "--llm-max-input-chars" in decision.command
    assert decision.command[decision.command.index("--llm-max-input-chars") + 1] == "2048"
    assert "--llm-allow-code-snippets" in decision.command
    assert decision.command[decision.command.index("--llm-allow-code-snippets") + 1] == "on"
    assert "--llm-path-policy" in decision.command
    assert decision.command[decision.command.index("--llm-path-policy") + 1] == "allow"
    assert "False" not in decision.command
    assert "True" not in decision.command


def test_stop_hook_decision_passes_wiki_auto_config_to_codex_finalize(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    codex_home = tmp_path / "codex"
    plugin_root.mkdir(parents=True)
    (plugin_root / "local_config.json").write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "wiki_root": str(wiki_root),
                "codex_home": str(codex_home),
                "summary_mode": "auto",
                "wiki_auto_mode": "apply-flexible",
                "wiki_write_judge_mode": "auto",
                "wiki_auto_min_score": 0.87,
            }
        ),
        encoding="utf-8",
    )

    decision = build_codex_stop_finalize_decision(
        payload={
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "cwd": str(project_root),
        },
        plugin_root=plugin_root,
        python_executable="python",
    )

    assert decision.should_finalize is True
    assert "--wiki-auto-mode" in decision.command
    assert decision.command[decision.command.index("--wiki-auto-mode") + 1] == "apply-flexible"
    assert "--wiki-write-judge-mode" in decision.command
    assert decision.command[decision.command.index("--wiki-write-judge-mode") + 1] == "auto"
    assert "--wiki-auto-min-score" in decision.command
    assert decision.command[decision.command.index("--wiki-auto-min-score") + 1] == "0.87"


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
                "summary_mode": "auto",
                "summary_cache": True,
                "codex_cli_command": str(tmp_path / "missing-codex.exe"),
                "llm_redact": False,
                "llm_allow_code_snippets": True,
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
    summary_path = project_root / "data" / "exports" / "summaries" / "thread-utf8-micro-v2.json"
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["metadata"]["fallback_from"] == "auto"
    assert summary_payload["metadata"]["fallback_reason"] == "codex_cli_unavailable"
