from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

import agent_context_substrate.distribution as distribution

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
    marketplace_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    codex_user_hooks_path = codex_home / "hooks.json"
    manifest_text = (plugin_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    codex_cache_plugin_dir = (
        codex_home / "plugins" / "cache" / "personal" / "agent-context-substrate" / json.loads(manifest_text)["version"]
    )
    local_config = json.loads((plugin_dir / "local_config.json").read_text(encoding="utf-8"))
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    user_hooks = json.loads(codex_user_hooks_path.read_text(encoding="utf-8"))
    assert result.status == "installed"
    assert (plugin_dir / "skills" / "agent-context-substrate" / "SKILL.md").is_file()
    assert (plugin_dir / "hooks" / "hooks.json").is_file()
    assert (plugin_dir / "hooks" / "codex_stop_finalize.py").is_file()
    assert (marketplace_plugin_dir / ".codex-plugin" / "plugin.json").is_file()
    assert (codex_cache_plugin_dir / ".codex-plugin" / "plugin.json").is_file()
    for installed_dir in (plugin_dir, marketplace_plugin_dir, codex_cache_plugin_dir):
        assert json.loads((installed_dir / "hooks" / "hooks.json").read_text(encoding="utf-8")) == {"hooks": {}}
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


def test_codex_trigger_modes_preserve_mixed_groups_and_are_repeatable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(distribution, "_timestamp", lambda: "fixed-second")
    codex_home = tmp_path / "codex-home"
    marketplace_root = tmp_path / "marketplace"
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    hook_script = plugin_dir / "hooks" / "codex_stop_finalize.py"
    trusted_handler = {
        "type": "command",
        "command": f'python3 "{hook_script.as_posix()}"',
        "commandWindows": f'python "{hook_script}"',
        "timeout": 120,
        "statusMessage": "Finalizing Codex thread into Agent Context Substrate",
    }
    unrelated_handler = {"type": "command", "command": "echo preserved"}
    other_event = [{"hooks": [{"type": "command", "command": "echo session-start"}]}]
    payload = {
        "custom_top_level": {"preserve": True},
        "hooks": {
            "SessionStart": other_event,
            "Stop": [
                {"matcher": "", "custom_group": "mixed", "hooks": [unrelated_handler, trusted_handler]},
                {"matcher": "*", "custom_group": "duplicate", "hooks": [trusted_handler, unrelated_handler]},
            ],
        },
    }
    hooks_path = codex_home / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps(payload), encoding="utf-8")
    previous_mode = None
    previous_hooks = None
    for user_mode in (True, True, False, False, True, True):
        result = install_codex_plugin(
            codex_home=codex_home,
            project_root=tmp_path / "project",
            wiki_root=tmp_path / "wiki",
            personal_marketplace_root=marketplace_root,
            install_user_hook=user_mode,
            overwrite=True,
        )
        hook_bytes = hooks_path.read_bytes()
        if user_mode == previous_mode:
            assert hook_bytes == previous_hooks
        previous_mode, previous_hooks = user_mode, hook_bytes
        configured = json.loads(hook_bytes)
        assert configured["custom_top_level"] == payload["custom_top_level"]
        assert configured["hooks"]["SessionStart"] == other_event
        groups = configured["hooks"]["Stop"]
        assert groups[0]["matcher"] == ""
        assert groups[0]["custom_group"] == "mixed"
        assert groups[1]["matcher"] == "*"
        assert groups[1]["custom_group"] == "duplicate"
        assert unrelated_handler in groups[0]["hooks"]
        assert groups[1]["hooks"] == [unrelated_handler]
        acs_handlers = [
            handler for group in groups for handler in group["hooks"]
            if "codex_stop_finalize.py" in handler.get("command", "")
        ]
        assert acs_handlers == ([trusted_handler] if user_mode else [])
        for installed_dir in (
            plugin_dir, marketplace_root / "plugins" / "agent-context-substrate", result.paths["codex_plugin_cache_dir"]
        ):
            bundled = json.loads((installed_dir / "hooks" / "hooks.json").read_text(encoding="utf-8"))
            assert bool(bundled["hooks"].get("Stop")) is not user_mode
        marketplace = json.loads((marketplace_root / ".agents" / "plugins" / "marketplace.json").read_text())
        assert len([entry for entry in marketplace["plugins"] if entry["name"] == "agent-context-substrate"]) == 1


@pytest.mark.parametrize("custom_settings", [False, True])
def test_codex_reinstall_keeps_trusted_user_hook_file_unchanged(tmp_path: Path, custom_settings: bool) -> None:
    codex_home = tmp_path / "codex-home"
    args = dict(codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    install_codex_plugin(**args, install_user_hook=True)
    hooks_path = codex_home / "hooks.json"
    original = hooks_path.read_bytes()
    if custom_settings:
        payload = json.loads(original)
        handler = payload["hooks"]["Stop"][0]["hooks"][0]
        hook_script = codex_home / "plugins" / "agent-context-substrate" / "hooks" / "codex_stop_finalize.py"
        handler["command"] = f'"{sys.executable}" -u "{hook_script.as_posix()}"'
        handler["commandWindows"] = f'"{sys.executable}" -u "{hook_script}"'
        handler["timeout"] = 37
        handler["statusMessage"] = "Custom trusted ACS handler"
        original = json.dumps(payload, indent=4).encode("utf-8")
    hooks_path.write_bytes(b"\xef\xbb\xbf" + original)
    trusted_bytes = hooks_path.read_bytes()
    install_codex_plugin(**args, install_user_hook=True, overwrite=True)
    assert hooks_path.read_bytes() == trusted_bytes


@pytest.mark.parametrize("stale_field", ["command", "commandWindows", "script_path"])
def test_codex_reinstall_repairs_stale_user_handler_in_place(tmp_path: Path, stale_field: str) -> None:
    codex_home = tmp_path / "codex-home"
    args = dict(codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    install_codex_plugin(**args, install_user_hook=True)
    hooks_path = codex_home / "hooks.json"
    payload = json.loads(hooks_path.read_text(encoding="utf-8"))
    expected_handler = payload["hooks"]["Stop"][0]["hooks"][0].copy()
    hook_script = codex_home / "plugins" / "agent-context-substrate" / "hooks" / "codex_stop_finalize.py"
    expected_handler["command"] = f'"{sys.executable}" -u "{hook_script.as_posix()}"'
    expected_handler["commandWindows"] = f'"{sys.executable}" -u "{hook_script}"'
    expected_handler["timeout"] = 37
    expected_handler["statusMessage"] = "Keep custom metadata on repair"
    stale_handler = expected_handler.copy()
    stale_script = tmp_path / "retired" / "agent-context-substrate" / "hooks" / "codex_stop_finalize.py"
    if stale_field == "script_path":
        stale_handler["command"] = f'"{sys.executable}" -u "{stale_script.as_posix()}"'
        stale_handler["commandWindows"] = f'"{sys.executable}" -u "{stale_script}"'
    else:
        target = stale_script.as_posix() if stale_field == "command" else str(stale_script)
        stale_handler[stale_field] = f'"{sys.executable}" -u "{target}"'
    before = {"type": "command", "command": "echo before"}
    after = {"type": "command", "command": "echo after"}
    payload["custom_top_level"] = {"retain": True}
    payload["hooks"]["Stop"] = [
        {"matcher": "", "custom_group": "preserve", "hooks": [before, stale_handler, after]},
        {"matcher": "*", "hooks": [after]},
    ]
    hooks_path.write_text(json.dumps(payload), encoding="utf-8")
    install_codex_plugin(**args, install_user_hook=True, overwrite=True)
    repaired = json.loads(hooks_path.read_text(encoding="utf-8"))
    payload["hooks"]["Stop"][0]["hooks"][1] = expected_handler
    assert repaired == payload
    repaired_bytes = hooks_path.read_bytes()
    install_codex_plugin(**args, install_user_hook=True, overwrite=True)
    assert hooks_path.read_bytes() == repaired_bytes


def test_codex_reinstall_prefers_current_user_handler_over_earlier_stale_duplicate(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    args = dict(codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    install_codex_plugin(**args, install_user_hook=True)
    hooks_path = codex_home / "hooks.json"
    payload = json.loads(hooks_path.read_text(encoding="utf-8"))
    current_handler = payload["hooks"]["Stop"][0]["hooks"][0]
    current_handler["timeout"] = 37
    current_handler["statusMessage"] = "Already trusted current handler"
    stale_handler = dict(current_handler)
    stale_script = tmp_path / "retired" / "agent-context-substrate" / "hooks" / "codex_stop_finalize.py"
    stale_handler["command"] = f'python3 "{stale_script.as_posix()}"'
    stale_handler["commandWindows"] = f'python "{stale_script}"'
    unrelated = {"type": "command", "command": "echo preserved"}
    payload["hooks"]["Stop"] = [
        {"matcher": "", "custom_group": "old", "hooks": [unrelated, stale_handler]},
        {"matcher": "*", "custom_group": "current", "hooks": [current_handler, unrelated]},
    ]
    hooks_path.write_text(json.dumps(payload), encoding="utf-8")
    install_codex_plugin(**args, install_user_hook=True, overwrite=True)
    repaired = json.loads(hooks_path.read_text(encoding="utf-8"))
    payload["hooks"]["Stop"][0]["hooks"] = [unrelated]
    assert repaired == payload
    repaired_bytes = hooks_path.read_bytes()
    install_codex_plugin(**args, install_user_hook=True, overwrite=True)
    assert hooks_path.read_bytes() == repaired_bytes


@pytest.mark.parametrize("codex_dir_name", ["codex home", "codex&home"])
def test_codex_reinstall_refuses_unsafe_bare_script_path_repair(tmp_path: Path, codex_dir_name: str) -> None:
    codex_home = tmp_path / codex_dir_name
    args = dict(codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    install_codex_plugin(**args, install_user_hook=True)
    hooks_path = codex_home / "hooks.json"
    payload = json.loads(hooks_path.read_text(encoding="utf-8"))
    handler = payload["hooks"]["Stop"][0]["hooks"][0]
    handler["command"] = "python3 /retired/agent-context-substrate/hooks/codex_stop_finalize.py"
    handler["commandWindows"] = r"python C:\retired\agent-context-substrate\hooks\codex_stop_finalize.py"
    hooks_path.write_text(json.dumps(payload), encoding="utf-8")
    original = hooks_path.read_bytes()
    with pytest.raises(ValueError, match="Cannot safely repair bare ACS user hook path"):
        install_codex_plugin(**args, install_user_hook=True, overwrite=True)
    assert hooks_path.read_bytes() == original


@pytest.mark.parametrize("initial_user_mode", [False, True])
@pytest.mark.parametrize("requested_user_mode", [False, True])
def test_codex_registered_cache_requires_marketplace_root_before_any_writes(
    tmp_path: Path, initial_user_mode: bool, requested_user_mode: bool
) -> None:
    codex_home = tmp_path / "codex-home"
    args = dict(codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    install_codex_plugin(
        **args, personal_marketplace_root=tmp_path / "marketplace", install_user_hook=initial_user_mode
    )
    before_files = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    before_dirs = {path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_dir()}
    with pytest.raises(ValueError, match="explicit --personal-marketplace-root"):
        install_codex_plugin(**args, install_user_hook=requested_user_mode, overwrite=True)
    after_files = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    after_dirs = {path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_dir()}
    assert after_files == before_files
    assert after_dirs == before_dirs


def test_codex_plugin_mode_does_not_create_user_hooks_file(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    install_codex_plugin(
        codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki"
    )
    assert not (codex_home / "hooks.json").exists()


def _codex_assets_with_version(tmp_path: Path, monkeypatch, version: str) -> Path:
    asset_root = tmp_path / "assets"
    plugin_assets = asset_root / "codex_plugin" / "agent-context-substrate"
    shutil.copytree(distribution._asset_root() / "codex_plugin" / "agent-context-substrate", plugin_assets)
    manifest_path = plugin_assets / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(distribution, "_asset_root", lambda: asset_root)
    return plugin_assets


def test_codex_cache_uses_manifest_version_preserves_old_versions_and_backs_up_target(tmp_path: Path, monkeypatch) -> None:
    _codex_assets_with_version(tmp_path, monkeypatch, "0.2.1")
    monkeypatch.setattr(distribution, "_timestamp", lambda: "fixed-second")
    codex_home = tmp_path / "codex-home"
    cache_parent = codex_home / "plugins" / "cache" / "personal" / "agent-context-substrate"
    for old_version in ("0.2.0", "local"):
        old_dir = cache_parent / old_version
        old_dir.mkdir(parents=True)
        (old_dir / "running-host-marker").write_text(old_version, encoding="utf-8")
    args = dict(
        codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki",
        personal_marketplace_root=tmp_path / "marketplace", overwrite=True,
    )
    first = install_codex_plugin(**args)
    target = cache_parent / "0.2.1"
    assert first.paths["codex_plugin_cache_dir"] == target
    (target / "replaced-marker").write_text("original target", encoding="utf-8")
    second = install_codex_plugin(**args)
    third = install_codex_plugin(**args)
    backup = second.paths["codex_plugin_cache_backup_path"]
    assert backup.is_relative_to(codex_home / "_backups")
    assert (backup / "replaced-marker").read_text(encoding="utf-8") == "original target"
    assert third.paths["codex_plugin_cache_backup_path"] != backup
    assert not (target / "replaced-marker").exists()
    assert {child.name for child in cache_parent.iterdir()} == {"0.2.0", "local", "0.2.1"}
    for old_version in ("0.2.0", "local"):
        assert (cache_parent / old_version / "running-host-marker").read_text(encoding="utf-8") == old_version


def test_codex_cache_failed_replacement_restores_running_target(tmp_path: Path, monkeypatch) -> None:
    _codex_assets_with_version(tmp_path, monkeypatch, "0.2.1")
    codex_home = tmp_path / "codex-home"
    target = codex_home / "plugins" / "cache" / "personal" / "agent-context-substrate" / "0.2.1"
    target.mkdir(parents=True)
    (target / "running-host-marker").write_text("preserve", encoding="utf-8")
    original_rename = Path.rename

    def fail_staged_rename(path: Path, destination: Path) -> Path:
        if path.parent.name.startswith("acs-cache-"):
            raise OSError("simulated replacement failure")
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_staged_rename)
    with pytest.raises(OSError, match="simulated replacement failure"):
        install_codex_plugin(
            codex_home=codex_home, project_root=tmp_path / "project", wiki_root=tmp_path / "wiki",
            personal_marketplace_root=tmp_path / "marketplace",
        )
    assert (target / "running-host-marker").read_text(encoding="utf-8") == "preserve"


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
