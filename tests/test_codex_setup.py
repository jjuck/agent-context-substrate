from __future__ import annotations

import json
from pathlib import Path

from agent_context_substrate.codex_setup import (
    codex_config_paths,
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
        install_user_hook=True,
        install_marketplace=True,
        overwrite=True,
    )

    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    assert result.ok is True
    assert result.status == "installed"
    assert (wiki_root / "_system" / "config.yaml").is_file()
    assert (plugin_dir / "local_config.json").is_file()
    assert (codex_home / "hooks.json").is_file()
    assert (marketplace_root / ".agents" / "plugins" / "marketplace.json").is_file()
    local_config = read_codex_local_config(plugin_dir)
    assert Path(local_config["project_root"]) == project_root
    assert Path(local_config["wiki_root"]) == wiki_root
    assert Path(local_config["codex_home"]) == codex_home
    assert result.doctor_report is not None
    assert result.doctor_report.checks["codex_plugin_installed"] == "ok"
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
    assert (codex_home / "hooks.json").is_file()
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
