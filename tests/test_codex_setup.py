from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_context_substrate.codex_setup import (
    codex_config_paths,
    diagnose_codex,
    doctor_codex,
    read_codex_local_config,
    setup_codex,
    setup_codex_wizard,
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
    assert json.loads((plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert (marketplace_root / ".agents" / "plugins" / "marketplace.json").is_file()
    local_config = read_codex_local_config(plugin_dir)
    assert Path(local_config["project_root"]) == project_root
    assert Path(local_config["wiki_root"]) == wiki_root
    assert Path(local_config["codex_home"]) == codex_home
    assert result.doctor_report is not None
    assert result.doctor_report.checks["codex_plugin_installed"] == "ok"
    assert result.doctor_report.checks["codex_user_hook_installed"] == "not-required"


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
    assert not any(issue.startswith("codex_user_hook_installed=") for issue in report.issues)
    assert "review /hooks" in "\n".join(report.actions)
    assert "--dangerously-bypass-hook-trust" not in "\n".join(report.actions)


def test_setup_codex_user_hook_requires_explicit_opt_in(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    result = setup_codex(
        codex_home=codex_home,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        install_marketplace=False,
        install_user_hook=True,
    )

    assert result.ok is True
    assert (codex_home / "hooks.json").is_file()
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    assert json.loads((plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8")) == {"hooks": {}}
    assert result.doctor_report.checks["codex_user_hook_installed"] == "ok"
    assert "--install-user-hook" in "\n".join(result.actions)


@pytest.mark.parametrize("repair", ["setup", "wizard", "diagnose"])
def test_setup_entry_points_restore_bundled_hook_and_preserve_other_hooks(tmp_path: Path, repair: str) -> None:
    codex_home = tmp_path / "codex"
    paths = dict(
        codex_home=codex_home,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        personal_marketplace_root=tmp_path / "marketplace",
    )
    setup_codex(**paths, install_user_hook=True)
    hooks_path = codex_home / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    other = {"hooks": [{"type": "command", "command": "echo other"}]}
    hooks["hooks"]["Stop"].append(other)
    hooks["hooks"]["SessionStart"] = [other]
    hooks_path.write_text(json.dumps(hooks), encoding="utf-8")
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"

    if repair == "wizard":
        result = setup_codex_wizard(**paths, assume_yes=True)
    elif repair == "diagnose":
        (plugin_dir / "local_config.json").unlink()
        result = diagnose_codex(**paths, fix=True)
    else:
        result = setup_codex(**paths)

    assert result.ok is True
    assert json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"] == {
        "Stop": [other], "SessionStart": [other],
    }
    assert json.loads((plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert result.doctor_report.checks["codex_user_hook_installed"] == "not-required"
    assert "review /hooks" in "\n".join(result.actions).lower()


@pytest.mark.parametrize("broken_bundle", ["empty", "missing-script"])
def test_doctor_warns_when_neither_user_nor_bundled_hook_is_available(tmp_path: Path, broken_bundle: str) -> None:
    paths = dict(codex_home=tmp_path / "codex", project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    setup_codex(**paths, install_marketplace=False)
    hooks_dir = paths["codex_home"] / "plugins" / "agent-context-substrate" / "hooks"
    if broken_bundle == "empty":
        (hooks_dir / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
    else:
        (hooks_dir / "codex_stop_finalize.py").unlink()

    report = diagnose_codex(**paths)

    assert "codex_user_hook_installed=warn" in report.issues
    assert any("restore the bundled Stop hook" in action for action in report.actions)


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
