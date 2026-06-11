from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent_context_substrate.codex_setup import (
    codex_config_paths,
    default_codex_local_config,
    detect_codex_cli,
    diagnose_codex,
    doctor_codex,
    resolve_codex_wiki_root,
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
    assert local_config["summary_mode"] == "auto"
    assert local_config["wiki_auto_mode"] == "apply-flexible"
    assert local_config["wiki_write_judge_mode"] == "auto"
    assert local_config["wiki_auto_min_score"] == 0.85
    assert result.doctor_report is not None
    assert result.doctor_report.checks["codex_plugin_installed"] == "ok"
    assert result.doctor_report.checks["codex_user_hook_installed"] == "warn"
    assert result.doctor_report.checks["hook_primary_installed"] == "ok"


def test_setup_codex_default_wiki_root_is_portable_template(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    marketplace_root = tmp_path / "marketplace"
    expected_effective = home / "Documents" / "LLM Wiki"
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", raising=False)
    monkeypatch.delenv("WIKI_PATH", raising=False)
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    result = setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=None,
        personal_marketplace_root=marketplace_root,
        install_marketplace=True,
        overwrite=True,
    )

    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    local_config = read_codex_local_config(plugin_dir)
    assert result.ok is True
    assert (expected_effective / "_system" / "config.yaml").is_file()
    assert local_config["wiki_root"] == "%USERPROFILE%\\Documents\\LLM Wiki"
    assert str(home) not in local_config["wiki_root"]
    assert local_config["wiki_root_source"] == "default-template"
    assert "wiki_root_effective" not in local_config
    assert result.paths["llm_wiki_root"] == expected_effective.resolve(strict=False)
    assert result.paths["wiki_root_effective"] == expected_effective.resolve(strict=False)


def test_setup_codex_explicit_wiki_root_is_recorded_as_explicit(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "custom-wiki"
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        overwrite=True,
    )

    local_config = read_codex_local_config(codex_home / "plugins" / "agent-context-substrate")
    assert Path(local_config["wiki_root"]) == wiki_root
    assert local_config["wiki_root_source"] == "explicit"


def test_codex_wiki_root_resolver_preserves_legacy_absolute_config(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy-wiki"

    resolved = resolve_codex_wiki_root({"wiki_root": str(legacy_root)}, env={})

    assert resolved.path == legacy_root.resolve(strict=False)
    assert resolved.source == "legacy"


def test_codex_wiki_root_resolver_prefers_env_override(tmp_path: Path) -> None:
    config_root = tmp_path / "config-wiki"
    env_root = tmp_path / "env-wiki"

    resolved = resolve_codex_wiki_root(
        {"wiki_root": str(config_root), "wiki_root_source": "explicit"},
        env={"AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT": str(env_root)},
    )

    assert resolved.path == env_root.resolve(strict=False)
    assert resolved.source == "env:AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT"


def test_default_codex_local_config_does_not_persist_env_wiki_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", str(tmp_path / "env-wiki"))

    config = default_codex_local_config(
        codex_home=tmp_path / "codex-home",
        project_root=tmp_path / "project",
        wiki_root=None,
    )

    assert config["wiki_root"] == "%USERPROFILE%\\Documents\\LLM Wiki"
    assert config["wiki_root_source"] == "default-template"


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
    assert detection.versioned_app_cli_candidates == [app_cli]
    assert "npm shim" in "\n".join(detection.messages)


def test_detect_codex_cli_reports_all_windows_candidates_and_path_order(tmp_path: Path) -> None:
    npm_dir = tmp_path / "AppData" / "Roaming" / "npm"
    standalone_dir = tmp_path / "LocalAppData" / "Programs" / "OpenAI" / "Codex" / "bin"
    direct_app_dir = tmp_path / "LocalAppData" / "OpenAI" / "Codex" / "bin"
    versioned_app_dir = direct_app_dir / "fb2111b91430cb17"
    npm_dir.mkdir(parents=True)
    standalone_dir.mkdir(parents=True)
    versioned_app_dir.mkdir(parents=True)
    path_shim = npm_dir / "codex.ps1"
    standalone_cli = standalone_dir / "codex.exe"
    versioned_cli = versioned_app_dir / "codex.exe"
    path_shim.write_text("# npm shim\n", encoding="utf-8")
    standalone_cli.write_text("", encoding="utf-8")
    versioned_cli.write_text("", encoding="utf-8")

    detection = detect_codex_cli(
        path_entries=[npm_dir, standalone_dir],
        local_app_data=tmp_path / "LocalAppData",
    )

    assert detection.path_kind == "npm-shim"
    assert detection.path_codex_candidates == [path_shim, standalone_cli]
    assert detection.standalone_cli_path == standalone_cli
    assert detection.versioned_app_cli_candidates == [versioned_cli]
    assert detection.recommended_path == standalone_cli
    assert detection.npm_precedes_openai_cli is True
    assert "All PATH codex candidates" in "\n".join(detection.messages)


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


def test_setup_codex_pins_detected_direct_codex_cli(tmp_path: Path, monkeypatch) -> None:
    local_app_data = tmp_path / "LocalAppData"
    codex_cli = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
    codex_cli.parent.mkdir(parents=True)
    codex_cli.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("PATH", "")
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    result = setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        overwrite=True,
    )

    local_config = read_codex_local_config(codex_home / "plugins" / "agent-context-substrate")
    assert result.ok is True
    assert local_config["codex_cli_command"] == str(codex_cli)
    assert result.doctor_report is not None
    assert result.doctor_report.checks["codex_summary_cli_direct"] == "ok"
    assert "Codex summary CLI pinned" in "\n".join(result.messages)


def test_doctor_codex_reports_summary_cli_and_service_tier_default(tmp_path: Path) -> None:
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
    update_codex_local_config(
        plugin_dir,
        {"summary_mode": "auto", "codex_cli_command": str(tmp_path / "missing-codex.exe")},
    )
    (codex_home / "config.toml").write_text('service_tier = "default"\n', encoding="utf-8")

    report = doctor_codex(codex_home=codex_home, project_root=project_root, wiki_root=wiki_root)

    assert report.checks["codex_summary_cli_config"] == "warn"
    assert report.checks["codex_summary_cli_direct"] == "warn"
    assert report.checks["codex_summary_smoke"] == "skipped"
    assert report.checks["codex_config_service_tier"] == "warn"
    assert "Codex summary CLI kind" in "\n".join(report.messages)
    assert "service_tier=\"default\"" in "\n".join(report.messages)


def test_doctor_codex_classifies_configured_direct_summary_cli(tmp_path: Path, monkeypatch) -> None:
    local_app_data = tmp_path / "LocalAppData"
    codex_cli = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
    codex_cli.parent.mkdir(parents=True)
    codex_cli.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
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
    update_codex_local_config(
        codex_home / "plugins" / "agent-context-substrate",
        {"summary_mode": "auto", "codex_cli_command": str(codex_cli)},
    )

    report = doctor_codex(codex_home=codex_home, project_root=project_root, wiki_root=wiki_root)

    assert report.checks["codex_summary_cli_config"] == "ok"
    assert report.checks["codex_summary_cli_direct"] == "ok"
    assert "Codex summary CLI kind: direct-app-cli" in "\n".join(report.messages)


def test_doctor_codex_summary_smoke_is_opt_in(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    fake_codex = tmp_path / "codex.exe"
    fake_codex.write_text("", encoding="utf-8")
    setup_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=tmp_path / "marketplace",
        overwrite=True,
    )
    update_codex_local_config(
        codex_home / "plugins" / "agent-context-substrate",
        {"summary_mode": "auto", "codex_cli_command": str(fake_codex)},
    )

    def fake_run(command, **kwargs):
        assert command[0] == str(fake_codex)
        assert "service_tier=fast" in command
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ACS_CODEX_SUMMARY_SMOKE_OK\n", stderr="")

    monkeypatch.setattr("agent_context_substrate.codex_setup.subprocess.run", fake_run)

    skipped = doctor_codex(codex_home=codex_home, project_root=project_root, wiki_root=wiki_root)
    smoked = doctor_codex(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        summary_smoke=True,
    )

    assert skipped.checks["codex_summary_smoke"] == "skipped"
    assert smoked.checks["codex_summary_smoke"] == "ok"
