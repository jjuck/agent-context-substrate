from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import re
import tomllib


REQUIRED_ASSET_FILES = [
    "user_plugin/agent_context_substrate/plugin.yaml",
    "user_plugin/agent_context_substrate/__init__.py",
    "user_plugin/agent_context_substrate/config.py",
    "user_plugin/agent_context_substrate/runtime.py",
    "context_engine/agent_context_substrate/plugin.yaml",
    "context_engine/agent_context_substrate/__init__.py",
    "context_engine/agent_context_substrate/config.py",
    "context_engine/agent_context_substrate/engine.py",
    "context_engine/agent_context_substrate/formatting.py",
    "context_engine/agent_context_substrate/recovery_loader.py",
    "context_engine/agent_context_substrate/retrieval_tools.py",
]


def test_distribution_assets_are_packaged_without_user_paths() -> None:
    asset_root = files("agent_context_substrate") / "assets"

    for relative_path in REQUIRED_ASSET_FILES:
        asset = asset_root / relative_path
        assert asset.is_file(), f"missing packaged asset: {relative_path}"
        text = asset.read_text(encoding="utf-8")
        windows_mount_user_prefix = "/mnt/" "c/Users/"
        windows_drive_user_prefix = "C:" + "\\\\Users\\\\"
        assert windows_mount_user_prefix not in text
        assert windows_drive_user_prefix not in text


def test_distribution_assets_keep_expected_generic_defaults() -> None:
    asset_root = files("agent_context_substrate") / "assets"

    plugin_config = (asset_root / "user_plugin/agent_context_substrate/config.py").read_text(encoding="utf-8")
    context_config = (asset_root / "context_engine/agent_context_substrate/config.py").read_text(encoding="utf-8")

    assert "AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT" in plugin_config
    assert "AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT" in plugin_config
    assert "~/.hermes/agent-context-substrate" in plugin_config
    assert "~/LLM Wiki" in plugin_config
    assert "local_config" in context_config
    assert "AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT" in context_config
    assert "~/.hermes/agent-context-substrate" in context_config
    assert "~/LLM Wiki" in context_config


def test_distribution_assets_do_not_include_python_bytecode() -> None:
    asset_root = files("agent_context_substrate") / "assets"
    bytecode_files = [str(path) for path in asset_root.rglob("*.pyc")]
    pycache_dirs = [str(path) for path in asset_root.rglob("__pycache__") if path.is_dir()]

    assert bytecode_files == []
    assert pycache_dirs == []


def test_user_plugin_registers_single_wiki_language_command() -> None:
    asset_root = files("agent_context_substrate") / "assets"
    plugin_init = (asset_root / "user_plugin/agent_context_substrate/__init__.py").read_text(encoding="utf-8")
    registered_commands = re.findall(r'ctx\.register_command\(\s*\n\s*"([^"]+)"', plugin_init)

    assert "wiki-language" in registered_commands
    assert "wiki-lang" not in registered_commands
    assert len(registered_commands) == len(set(registered_commands))


def test_pyproject_uses_pep639_license_expression_without_deprecated_license_classifier() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload["project"]

    assert project["license"] == "MIT"
    assert "License :: OSI Approved :: MIT License" not in project.get("classifiers", [])
