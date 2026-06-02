from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from agent_context_substrate.distribution import (
    doctor,
    init_wiki,
    install_codex_plugin,
    install_context_engine,
    install_user_plugin,
)


def _load_local_config_paths(local_config_path: Path) -> tuple[Path, Path]:
    spec = importlib.util.spec_from_file_location(f"local_config_{id(local_config_path)}", local_config_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PROJECT_ROOT, module.WIKI_ROOT


def test_init_wiki_creates_human_facing_vault_skeleton(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"

    result = init_wiki(wiki_root)

    assert result.status == "initialized"
    for relative_path in [
        "01 지식",
        "02 내 아이디어",
        "03 인물과 조직",
        "04 프로젝트",
        "05 계획",
        "06 원천 자료",
        "90 보관",
        "_system/templates/ko",
        "_system/templates/en",
        "_system/styles",
    ]:
        assert (wiki_root / relative_path).exists()
    config_text = (wiki_root / "_system/config.yaml").read_text(encoding="utf-8")
    assert "default_language: ko" in config_text
    assert "supported_languages" in config_text
    assert (wiki_root / "index.md").is_file()
    assert (wiki_root / "log.md").is_file()


def test_install_user_plugin_copies_assets_and_writes_local_config(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    wiki_root.mkdir()

    result = install_user_plugin(
        hermes_home=hermes_home,
        project_root=project_root,
        wiki_root=wiki_root,
    )

    plugin_dir = hermes_home / "plugins" / "agent-context-substrate"
    assert result.status == "installed"
    assert (plugin_dir / "plugin.yaml").is_file()
    assert (plugin_dir / "runtime.py").is_file()
    assert (plugin_dir / "config.py").is_file()
    local_project_root, local_wiki_root = _load_local_config_paths(plugin_dir / "local_config.py")
    assert local_project_root == project_root
    assert local_wiki_root == wiki_root
    windows_mount_user_prefix = "/mnt/" "c/Users/"
    assert windows_mount_user_prefix not in (plugin_dir / "config.py").read_text(encoding="utf-8")


def test_install_user_plugin_refuses_overwrite_without_flag(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    plugin_dir = hermes_home / "plugins" / "agent-context-substrate"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "config.py").write_text("# user edit\n", encoding="utf-8")

    result = install_user_plugin(
        hermes_home=hermes_home,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        overwrite=False,
    )

    assert result.status == "skipped"
    assert (plugin_dir / "config.py").read_text(encoding="utf-8") == "# user edit\n"


def test_install_codex_plugin_copies_non_mcp_asset_and_writes_local_config(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    marketplace_root = tmp_path / "marketplace-root"

    result = install_codex_plugin(
        codex_home=codex_home,
        project_root=project_root,
        wiki_root=wiki_root,
        personal_marketplace_root=marketplace_root,
        install_user_hook=True,
    )

    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    marketplace_plugin_dir = marketplace_root / "plugins" / "agent-context-substrate"
    codex_cache_plugin_dir = (
        codex_home / "plugins" / "cache" / "personal" / "agent-context-substrate" / "local"
    )
    marketplace_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    codex_user_hooks_path = codex_home / "hooks.json"
    manifest_text = (plugin_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    local_config = json.loads((plugin_dir / "local_config.json").read_text(encoding="utf-8"))
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    user_hooks = json.loads(codex_user_hooks_path.read_text(encoding="utf-8"))
    assert result.status == "installed"
    assert (plugin_dir / "skills" / "agent-context-substrate" / "SKILL.md").is_file()
    assert (plugin_dir / "hooks" / "hooks.json").is_file()
    assert (plugin_dir / "hooks" / "codex_stop_finalize.py").is_file()
    assert (marketplace_plugin_dir / ".codex-plugin" / "plugin.json").is_file()
    assert (codex_cache_plugin_dir / ".codex-plugin" / "plugin.json").is_file()
    assert result.paths["codex_user_hooks_path"] == codex_user_hooks_path
    assert '"mcpServers"' not in manifest_text
    assert '"hooks"' not in manifest_text
    assert Path(local_config["project_root"]) == project_root
    assert Path(local_config["wiki_root"]) == wiki_root
    assert local_config["python_path_entries"] == [str(project_root / "src")]
    assert Path(local_config["hook_event_log_path"]) == project_root / "data" / "index" / "codex_hook_events.jsonl"
    assert local_config["trigger_strategy"] == "hook-primary"
    assert marketplace["plugins"][0]["name"] == "agent-context-substrate"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/agent-context-substrate"
    assert marketplace["plugins"][0]["policy"]["installation"] == "INSTALLED_BY_DEFAULT"
    stop_handler = user_hooks["hooks"]["Stop"][0]["hooks"][0]
    assert stop_handler["commandWindows"].replace("\\", "/").endswith(
        'agent-context-substrate/hooks/codex_stop_finalize.py"'
    )
    assert "mcpServers" not in user_hooks


def test_install_codex_plugin_user_hook_accepts_existing_bom_json(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    hooks_path = codex_home / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        '\ufeff{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo preserved"}]}]}}\n',
        encoding="utf-8",
    )

    install_codex_plugin(
        codex_home=codex_home,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        install_user_hook=True,
    )

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    stop_groups = hooks["hooks"]["Stop"]
    assert stop_groups[0]["hooks"][0]["command"] == "echo preserved"
    assert stop_groups[1]["hooks"][0]["command"].endswith("/hooks/codex_stop_finalize.py\"")


def test_install_user_plugin_overwrite_backup_is_not_discoverable_plugin(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    plugins_root = hermes_home / "plugins"
    install_user_plugin(
        hermes_home=hermes_home,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
    )
    legacy_direct_backup = plugins_root / "agent-context-substrate.bak-legacy"
    legacy_direct_backup.mkdir()
    (legacy_direct_backup / "plugin.yaml").write_text("name: agent-context-substrate\n", encoding="utf-8")
    legacy_category_backup = plugins_root / "_backups" / "agent-context-substrate.bak-temp-root"
    legacy_category_backup.mkdir(parents=True)
    (legacy_category_backup / "plugin.yaml").write_text("name: agent-context-substrate\n", encoding="utf-8")

    result = install_user_plugin(
        hermes_home=hermes_home,
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        overwrite=True,
    )

    backup_path = result.paths["backup_path"]
    assert backup_path.parent == hermes_home / "_backups" / "plugins"
    assert not any(
        child.name.startswith("agent-context-substrate.bak")
        for child in plugins_root.iterdir()
        if child.is_dir()
    )
    assert not (plugins_root / "_backups").exists()
    assert (hermes_home / "_backups" / "plugins" / "agent-context-substrate.bak-legacy").is_dir()
    assert (hermes_home / "_backups" / "plugins" / "agent-context-substrate.bak-temp-root").is_dir()


def test_install_context_engine_copies_assets(tmp_path: Path) -> None:
    hermes_agent_root = tmp_path / "hermes-agent"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"

    result = install_context_engine(
        hermes_agent_root=hermes_agent_root,
        project_root=project_root,
        wiki_root=wiki_root,
    )

    engine_dir = hermes_agent_root / "plugins" / "context_engine" / "agent_context_substrate"
    assert result.status == "installed"
    assert (engine_dir / "plugin.yaml").is_file()
    assert (engine_dir / "engine.py").is_file()
    assert (engine_dir / "retrieval_tools.py").is_file()
    assert (engine_dir / "local_config.py").is_file()
    local_project_root, local_wiki_root = _load_local_config_paths(engine_dir / "local_config.py")
    assert local_project_root == project_root
    assert local_wiki_root == wiki_root
    windows_mount_user_prefix = "/mnt/" "c/Users/"
    assert windows_mount_user_prefix not in (engine_dir / "config.py").read_text(encoding="utf-8")


def test_install_context_engine_overwrite_backup_is_not_discoverable_engine(tmp_path: Path) -> None:
    hermes_agent_root = tmp_path / "hermes-agent"
    install_context_engine(hermes_agent_root=hermes_agent_root)
    context_engine_root = hermes_agent_root / "plugins" / "context_engine"
    legacy_backup = context_engine_root / "agent_context_substrate.bak-legacy"
    legacy_backup.mkdir()
    (legacy_backup / "__init__.py").write_text("", encoding="utf-8")

    result = install_context_engine(hermes_agent_root=hermes_agent_root, overwrite=True)

    backup_path = result.paths["backup_path"]
    assert backup_path.parent == context_engine_root / "_backups"
    assert not any(
        child.name.startswith("agent_context_substrate.bak")
        for child in context_engine_root.iterdir()
        if child.is_dir()
    )
    assert (context_engine_root / "_backups" / "agent_context_substrate.bak-legacy").is_dir()


def test_doctor_allows_explicit_local_config_paths(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_agent_root = tmp_path / "hermes-agent"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (hermes_home).mkdir()
    (hermes_home / "state.db").write_bytes(b"")
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)
    init_wiki(wiki_root)
    install_user_plugin(hermes_home=hermes_home, project_root=project_root, wiki_root=wiki_root)
    install_context_engine(hermes_agent_root=hermes_agent_root)
    local_config = hermes_home / "plugins" / "agent-context-substrate" / "local_config.py"
    generic_windows_mount_home = "/mnt/" "c/Users/example"
    local_config.write_text(
        f"PROJECT_ROOT = '{generic_windows_mount_home}/Desktop/py/My_Project/agent-context-substrate'\n"
        f"WIKI_ROOT = '{generic_windows_mount_home}/Documents/LLM Wiki'\n",
        encoding="utf-8",
    )

    report = doctor(
        hermes_home=hermes_home,
        project_root=project_root,
        wiki_root=wiki_root,
        hermes_agent_root=hermes_agent_root,
    )

    assert report.checks["installed_templates_are_generic"] is True


def test_doctor_reports_installed_components(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_agent_root = tmp_path / "hermes-agent"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (hermes_home).mkdir()
    (hermes_home / "state.db").write_bytes(b"")
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)
    init_wiki(wiki_root)
    install_user_plugin(hermes_home=hermes_home, project_root=project_root, wiki_root=wiki_root)
    install_context_engine(hermes_agent_root=hermes_agent_root)

    report = doctor(
        hermes_home=hermes_home,
        project_root=project_root,
        wiki_root=wiki_root,
        hermes_agent_root=hermes_agent_root,
    )

    assert report.ok is True
    assert report.checks["state_db_exists"] is True
    assert report.checks["wiki_config_exists"] is True
    assert report.checks["user_plugin_installed"] is True
    assert report.checks["context_engine_installed"] is True
    assert report.checks["installed_templates_are_generic"] is True
