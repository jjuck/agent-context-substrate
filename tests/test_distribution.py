from __future__ import annotations

from pathlib import Path

from hermes_llm_wiki_harness.distribution import (
    doctor,
    init_wiki,
    install_context_engine,
    install_user_plugin,
)


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

    plugin_dir = hermes_home / "plugins" / "wiki-harness"
    assert result.status == "installed"
    assert (plugin_dir / "plugin.yaml").is_file()
    assert (plugin_dir / "runtime.py").is_file()
    assert (plugin_dir / "config.py").is_file()
    local_config = (plugin_dir / "local_config.py").read_text(encoding="utf-8")
    assert str(project_root) in local_config
    assert str(wiki_root) in local_config
    assert "/mnt/c/Users/" not in (plugin_dir / "config.py").read_text(encoding="utf-8")


def test_install_user_plugin_refuses_overwrite_without_flag(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    plugin_dir = hermes_home / "plugins" / "wiki-harness"
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


def test_install_context_engine_copies_assets(tmp_path: Path) -> None:
    hermes_agent_root = tmp_path / "hermes-agent"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"

    result = install_context_engine(
        hermes_agent_root=hermes_agent_root,
        project_root=project_root,
        wiki_root=wiki_root,
    )

    engine_dir = hermes_agent_root / "plugins" / "context_engine" / "wiki_harness"
    assert result.status == "installed"
    assert (engine_dir / "plugin.yaml").is_file()
    assert (engine_dir / "engine.py").is_file()
    assert (engine_dir / "retrieval_tools.py").is_file()
    assert (engine_dir / "local_config.py").is_file()
    local_config = (engine_dir / "local_config.py").read_text(encoding="utf-8")
    assert str(project_root) in local_config
    assert str(wiki_root) in local_config
    assert "/mnt/c/Users/" not in (engine_dir / "config.py").read_text(encoding="utf-8")


def test_install_context_engine_overwrite_backup_is_not_discoverable_engine(tmp_path: Path) -> None:
    hermes_agent_root = tmp_path / "hermes-agent"
    install_context_engine(hermes_agent_root=hermes_agent_root)
    context_engine_root = hermes_agent_root / "plugins" / "context_engine"
    legacy_backup = context_engine_root / "wiki_harness.bak-legacy"
    legacy_backup.mkdir()
    (legacy_backup / "__init__.py").write_text("", encoding="utf-8")

    result = install_context_engine(hermes_agent_root=hermes_agent_root, overwrite=True)

    backup_path = result.paths["backup_path"]
    assert backup_path.parent == context_engine_root / "_backups"
    assert not any(
        child.name.startswith("wiki_harness.bak")
        for child in context_engine_root.iterdir()
        if child.is_dir()
    )
    assert (context_engine_root / "_backups" / "wiki_harness.bak-legacy").is_dir()


def test_doctor_allows_explicit_local_config_paths(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_agent_root = tmp_path / "hermes-agent"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (hermes_home).mkdir()
    (hermes_home / "state.db").write_bytes(b"")
    (project_root / "src" / "hermes_llm_wiki_harness").mkdir(parents=True)
    init_wiki(wiki_root)
    install_user_plugin(hermes_home=hermes_home, project_root=project_root, wiki_root=wiki_root)
    install_context_engine(hermes_agent_root=hermes_agent_root)
    local_config = hermes_home / "plugins" / "wiki-harness" / "local_config.py"
    local_config.write_text(
        "PROJECT_ROOT = '/mnt/c/Users/example/Desktop/py/My_Project/hermes-llm-wiki-harness'\n"
        "WIKI_ROOT = '/mnt/c/Users/example/Documents/LLM Wiki'\n",
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
    (project_root / "src" / "hermes_llm_wiki_harness").mkdir(parents=True)
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
