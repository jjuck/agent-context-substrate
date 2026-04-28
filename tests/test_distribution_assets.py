from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import tomllib


REQUIRED_ASSET_FILES = [
    "user_plugin/wiki_harness/plugin.yaml",
    "user_plugin/wiki_harness/__init__.py",
    "user_plugin/wiki_harness/config.py",
    "user_plugin/wiki_harness/runtime.py",
    "context_engine/wiki_harness/plugin.yaml",
    "context_engine/wiki_harness/__init__.py",
    "context_engine/wiki_harness/config.py",
    "context_engine/wiki_harness/engine.py",
    "context_engine/wiki_harness/formatting.py",
    "context_engine/wiki_harness/recovery_loader.py",
    "context_engine/wiki_harness/retrieval_tools.py",
]


def test_distribution_assets_are_packaged_without_user_paths() -> None:
    asset_root = files("hermes_llm_wiki_harness") / "assets"

    for relative_path in REQUIRED_ASSET_FILES:
        asset = asset_root / relative_path
        assert asset.is_file(), f"missing packaged asset: {relative_path}"
        text = asset.read_text(encoding="utf-8")
        assert "/mnt/c/Users/" not in text
        assert "C:\\Users\\" not in text


def test_distribution_assets_keep_expected_generic_defaults() -> None:
    asset_root = files("hermes_llm_wiki_harness") / "assets"

    plugin_config = (asset_root / "user_plugin/wiki_harness/config.py").read_text(encoding="utf-8")
    context_config = (asset_root / "context_engine/wiki_harness/config.py").read_text(encoding="utf-8")

    assert "HERMES_WIKI_HARNESS_PROJECT_ROOT" in plugin_config
    assert "HERMES_WIKI_HARNESS_WIKI_ROOT" in plugin_config
    assert "~/.hermes/llm-wiki-harness" in plugin_config
    assert "~/LLM Wiki" in plugin_config
    assert "local_config" in context_config
    assert "HERMES_WIKI_HARNESS_PROJECT_ROOT" in context_config
    assert "~/.hermes/llm-wiki-harness" in context_config
    assert "~/LLM Wiki" in context_config


def test_pyproject_uses_pep639_license_expression_without_deprecated_license_classifier() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload["project"]

    assert project["license"] == "MIT"
    assert "License :: OSI Approved :: MIT License" not in project.get("classifiers", [])
