from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate import cli


def test_codex_commands_are_registered() -> None:
    parser = cli.build_parser()

    assert parser.parse_args(["setup-codex", "--project-root", "C:/project"]).command == "setup-codex"
    assert parser.parse_args(["setup-codex-wizard", "--project-root", "C:/project", "--yes"]).command == "setup-codex-wizard"
    assert parser.parse_args(["doctor-codex", "--project-root", "C:/project"]).command == "doctor-codex"
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
        ]
    ).command == "codex-finalize"
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
    assert "acs_artifacts=" in captured.out
