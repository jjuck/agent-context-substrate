from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_context_substrate import cli


class _FakeTextStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))


def test_cli_configures_text_stdio_for_utf8(monkeypatch) -> None:
    stdout = _FakeTextStream()
    stderr = _FakeTextStream()
    monkeypatch.setattr(cli.sys, "stdout", stdout)
    monkeypatch.setattr(cli.sys, "stderr", stderr)

    cli.configure_text_stdio()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_codex_commands_are_registered() -> None:
    parser = cli.build_parser()

    assert parser.parse_args(["setup-codex", "--project-root", "C:/project"]).command == "setup-codex"
    assert parser.parse_args(
        ["setup-codex", "--project-root", "C:/project", "--user-hook-fallback"]
    ).user_hook_fallback is True
    assert parser.parse_args(["setup-codex-wizard", "--project-root", "C:/project", "--yes"]).command == "setup-codex-wizard"
    doctor_args = parser.parse_args(["doctor-codex", "--project-root", "C:/project", "--summary-smoke"])
    assert doctor_args.command == "doctor-codex"
    assert doctor_args.summary_smoke is True
    assert parser.parse_args(["diagnose-codex", "--project-root", "C:/project", "--fix"]).command == "diagnose-codex"
    assert parser.parse_args(["config-codex", "paths", "--project-root", "C:/project"]).command == "config-codex"
    assert parser.parse_args(["codex-status", "--codex-home", "C:/codex"]).command == "codex-status"
    assert parser.parse_args(
        [
            "codex-finalize",
            "--thread-id",
            "thread-1",
            "--codex-home",
            "C:/codex",
            "--project-root",
            "C:/project",
            "--wiki-root",
            "C:/wiki",
            "--summary-mode",
            "auto",
            "--codex-cli-command",
            "C:/OpenAI/Codex/bin/codex.exe",
            "--wiki-auto-mode",
            "apply-flexible",
        ]
    ).command == "codex-finalize"
    assert (
        parser.parse_args(
            [
                "codex-watch",
                "--codex-home",
                "C:/codex",
                "--once",
                "--wiki-auto-mode",
                "apply-flexible",
                "--wiki-write-judge-mode",
                "auto",
            ]
        ).wiki_auto_mode
        == "apply-flexible"
    )
    assert (
        parser.parse_args(
            [
                "build-context-packet",
                "--session-id",
                "session-1",
                "--packet-id",
                "packet-1",
                "--task-title",
                "Task",
                "--macro-context",
                "Context",
                "--unit-title",
                "Unit",
                "--goal",
                "Goal",
                "--summary-mode",
                "codex-cli",
                "--project-root",
                "C:/project",
            ]
        ).summary_mode
        == "codex-cli"
    )
    assert parser.parse_args(["codex-watch", "--codex-home", "C:/codex", "--once"]).command == "codex-watch"
    assert parser.parse_args(["search-knowledge", "--query", "codex"]).mode == "knowledge"
    assert parser.parse_args(["expand-hit", "--hit-id", "abc"]).command == "expand-hit"
    assert parser.parse_args(
        [
            "install-codex-plugin",
            "--codex-home",
            "C:/codex",
            "--project-root",
            "C:/project",
            "--wiki-root",
            "C:/wiki",
        ]
    ).command == "install-codex-plugin"


@pytest.mark.parametrize("command", ["setup-codex", "setup-codex-wizard"])
def test_setup_codex_help_renders_userprofile_template(command: str, capsys) -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args([command, "--help"])

    assert exc.value.code == 0
    assert "%USERPROFILE%\\Documents\\LLM Wiki" in capsys.readouterr().out


def test_codex_watch_custom_command_requires_summarizer_command(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "codex-watch",
                "--once",
                "--codex-home",
                str(tmp_path / "codex"),
                "--project-root",
                str(tmp_path / "project"),
                "--summary-mode",
                "custom-command",
            ]
        )

    assert exc_info.value.code == "--summary-mode custom-command requires --summarizer-command"


def test_codex_status_cli_prints_threads(tmp_path: Path, capsys) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()

    exit_code = cli.main(["codex-status", "--codex-home", str(codex_home)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "codex_home=" in captured.out
    assert "hook_support=supported" in captured.out
    assert "hook_primary=not-installed" in captured.out
    assert "watcher_fallback=available" in captured.out


def test_setup_codex_cli_dry_run_prints_json(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            "setup-codex",
            "--codex-home",
            str(tmp_path / "codex"),
            "--project-root",
            str(tmp_path / "project"),
            "--wiki-root",
            str(tmp_path / "wiki"),
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "dry-run"
    assert payload["ok"] is True
    assert "install-codex-plugin" in "\n".join(payload["actions"])


def test_doctor_codex_cli_fail_on_issues_returns_nonzero(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            "doctor-codex",
            "--codex-home",
            str(tmp_path / "missing-codex"),
            "--project-root",
            str(tmp_path / "missing-project"),
            "--wiki-root",
            str(tmp_path / "missing-wiki"),
            "--fail-on-issues",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "doctor-codex ok=False" in captured.out
    assert "codex_plugin_installed=missing" in captured.out


def test_config_codex_paths_cli_prints_user_facing_paths(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            "config-codex",
            "paths",
            "--codex-home",
            str(tmp_path / "codex"),
            "--project-root",
            str(tmp_path / "project"),
            "--wiki-root",
            str(tmp_path / "wiki"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "codex_sqlite=" in captured.out
    assert "llm_wiki_root=" in captured.out
    assert "wiki_root_source=explicit" in captured.out
    assert "wiki_root_effective=" in captured.out
    assert "acs_artifacts=" in captured.out


def test_config_codex_paths_uses_installed_config_wiki_root(tmp_path: Path, capsys, monkeypatch) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    installed_wiki = tmp_path / "installed-wiki"
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "local_config.json").write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "wiki_root": str(installed_wiki),
                "wiki_root_source": "explicit",
                "codex_home": str(codex_home),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", raising=False)
    monkeypatch.delenv("WIKI_PATH", raising=False)

    exit_code = cli.main(
        [
            "config-codex",
            "paths",
            "--codex-home",
            str(codex_home),
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"wiki_root={installed_wiki}" in captured.out
    assert "wiki_root_source=explicit" in captured.out
    assert f"wiki_root_effective={installed_wiki.resolve(strict=False)}" in captured.out


def test_config_codex_show_prints_effective_wiki_root_for_template(tmp_path: Path, capsys, monkeypatch) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    env_home = tmp_path / "home"
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "local_config.json").write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "wiki_root": "%USERPROFILE%\\Documents\\LLM Wiki",
                "wiki_root_source": "default-template",
                "codex_home": str(codex_home),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USERPROFILE", str(env_home))

    exit_code = cli.main(
        [
            "config-codex",
            "show",
            "--codex-home",
            str(codex_home),
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "wiki_root=%USERPROFILE%\\Documents\\LLM Wiki" in captured.out
    assert "wiki_root_source=default-template" in captured.out
    assert f"wiki_root_effective={env_home / 'Documents' / 'LLM Wiki'}" in captured.out
