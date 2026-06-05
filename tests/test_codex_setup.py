from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.codex_setup import (
    codex_config_paths,
    detect_codex_cli,
    diagnose_codex,
    doctor_codex,
    read_codex_local_config,
    setup_codex,
    update_codex_local_config,
)


def test_setup_codex_installs_default_windows_codex_integration(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "Documents" / "LLM Wiki"
    marketplace_root = tmp_path / "marketplace"
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    result = setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=marketplace_root,
        install_marketplace=True,
        overwrite=True,
    )

    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    assert result.ok is True
    assert result.status == "installed"
    assert (wiki_root / "_system" / "config.yaml").is_file()
    assert (plugin_dir / "local_config.json").is_file()
    assert not (codex_home / "hooks.json").exists()
    assert (marketplace_root / ".agents" / "plugins" / "marketplace.json").is_file()
    local_config = read_codex_local_config(plugin_dir)
    assert Path(local_config["project_root"]) == project_root
    assert Path(local_config["wiki_root"]) == wiki_root
    assert Path(local_config["codex_home"]) == codex_home
    assert result.doctor_report is not None
    assert result.doctor_report.checks["codex_plugin_installed"] == "ok"
    assert result.doctor_report.checks["codex_user_hook_installed"] == "warn"
    assert result.doctor_report.checks["hook_primary_installed"] == "ok"


def test_setup_codex_user_hook_fallback_is_explicit_opt_in(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    result = setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        install_user_hook=True,
        overwrite=True,
    )

    assert result.ok is True
    assert (codex_home / "hooks.json").is_file()
    assert result.doctor_report is not None
    assert result.doctor_report.checks["codex_user_hook_installed"] == "ok"


def test_setup_codex_dry_run_does_not_write_paths(tmp_path: Path) -> None:
    result = setup_codex(
        codex_home=tmp_path / "codex-home",
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        dry_run=True,
    )

    assert result.ok is True
    assert result.status == "dry-run"
    assert not (tmp_path / "codex-home").exists()
    assert "init-wiki" in "\n".join(result.actions)
    assert "install-codex-plugin" in "\n".join(result.actions)


def test_doctor_codex_reports_required_and_optional_checks(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        overwrite=True,
    )

    report = doctor_codex(codex_home=codex_home, project_root=project_root, wiki_root=wiki_root)

    assert report.ok is True
    assert report.checks["package_importable"] == "ok"
    assert report.checks["codex_plugin_installed"] == "ok"
    assert report.checks["codex_state_sqlite_exists"] == "warn"
    assert report.checks["watcher_fallback_available"] == "ok"
    assert "Codex source SQLite" in "\n".join(report.messages)


def test_diagnose_codex_fix_recreates_safe_missing_codex_files(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    report = diagnose_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        fix=True,
    )

    assert report.ok is True
    assert (wiki_root / "_system" / "config.yaml").is_file()
    assert (codex_home / "plugins" / "agent-context-substrate" / "local_config.json").is_file()
    assert not (codex_home / "hooks.json").exists()
    assert "review /hooks" in "\n".join(report.actions)
    assert "--dangerously-bypass-hook-trust" not in "\n".join(report.actions)


def test_codex_config_paths_and_updates_local_config(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        overwrite=True,
    )
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"

    paths = codex_config_paths(codex_home=codex_home, project_root=project_root, wiki_root=wiki_root)
    assert paths["codex_sqlite"] == codex_home / "state_5.sqlite"
    assert paths["llm_wiki_root"] == wiki_root
    assert paths["acs_artifacts"] == project_root / "data"

    updated = update_codex_local_config(plugin_dir, {"hook_timeout_seconds": 42})

    assert updated["hook_timeout_seconds"] == 42
    assert json.loads((plugin_dir / "local_config.json").read_text(encoding="utf-8"))["hook_timeout_seconds"] == 42


def test_detect_codex_cli_prefers_windows_app_candidate_when_path_codex_is_npm_shim(tmp_path: Path) -> None:
    npm_dir = tmp_path / "npm"
    app_dir = tmp_path / "local-app-data" / "OpenAI" / "Codex" / "bin" / "abcd1234"
    npm_dir.mkdir()
    app_dir.mkdir(parents=True)
    path_shim = npm_dir / "codex.ps1"
    app_cli = app_dir / "codex.exe"
    path_shim.write_text("# npm shim\n", encoding="utf-8")
    app_cli.write_text("", encoding="utf-8")

    detection = detect_codex_cli(path_entries=[npm_dir], local_app_data=tmp_path / "local-app-data")

    assert detection.status == "ok"
    assert detection.path_kind == "npm-shim"
    assert detection.path_codex == path_shim
    assert detection.app_cli_path == app_cli
    assert detection.recommended_path == app_cli
    assert "npm shim" in "\n".join(detection.messages)


def test_detect_codex_cli_reports_missing_when_only_npm_shim_exists(tmp_path: Path) -> None:
    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    path_shim = npm_dir / "codex.cmd"
    path_shim.write_text("@echo off\n", encoding="utf-8")

    detection = detect_codex_cli(path_entries=[npm_dir], local_app_data=tmp_path / "missing-local-app-data")

    assert detection.status == "warn"
    assert detection.path_kind == "npm-shim"
    assert detection.recommended_path is None
    assert "Codex app CLI candidate was not found" in "\n".join(detection.messages)
