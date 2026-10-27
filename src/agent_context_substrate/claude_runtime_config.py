from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from .claude_source import resolve_claude_home
from .codex_runtime_config import _read_json_object, _same_path


CLAUDE_CONFIG_ENV = "ACS_CLAUDE_CONFIG"


def default_claude_config_path(claude_home: Path | str | None = None) -> Path:
    """Config lives outside the plugin because marketplace installs replace plugin copies."""

    return resolve_claude_home(claude_home) / "agent-context-substrate" / "local_config.json"


def resolve_claude_config_path(plugin_root: Path | str | None = None) -> Path:
    explicit = os.environ.get(CLAUDE_CONFIG_ENV, "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve(strict=False)
    if plugin_root is not None:
        bundled = Path(plugin_root).expanduser() / "local_config.json"
        if bundled.is_file():
            return bundled.resolve(strict=False)
    return default_claude_config_path().resolve(strict=False)


def load_claude_runtime_config(config_path: Path | str) -> dict[str, Any]:
    """Load the Claude adapter config, following ``canonical_config_path`` once."""

    path = Path(config_path).expanduser().resolve(strict=False)
    bootstrap = _read_json_object(path)
    if not bootstrap:
        return {}
    canonical_value = str(bootstrap.get("canonical_config_path") or "").strip()
    if not canonical_value:
        return bootstrap
    canonical_path = Path(canonical_value).expanduser().resolve(strict=False)
    if _same_path(canonical_path, path) or not canonical_path.exists():
        return bootstrap
    return _read_json_object(canonical_path)
