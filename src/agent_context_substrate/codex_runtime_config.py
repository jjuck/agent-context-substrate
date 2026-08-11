from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import hashlib
import json


def load_codex_runtime_config(plugin_root: Path | str) -> dict[str, Any]:
    """Load the canonical config, using a plugin copy only as bootstrap metadata."""

    plugin_root_path = Path(plugin_root).expanduser().resolve(strict=False)
    bootstrap_path = plugin_root_path / "local_config.json"
    bootstrap = _read_json_object(bootstrap_path)
    if not bootstrap:
        return {}
    canonical_path = _canonical_config_path(bootstrap)
    if canonical_path is None or _same_path(canonical_path, bootstrap_path):
        return bootstrap
    if not canonical_path.exists():
        return bootstrap
    return _read_json_object(canonical_path)


def codex_config_digest(config: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(config), ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_config_path(bootstrap: Mapping[str, Any]) -> Path | None:
    explicit = str(bootstrap.get("canonical_config_path") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve(strict=False)
    codex_home = str(bootstrap.get("codex_home") or "").strip()
    if not codex_home:
        return None
    return (Path(codex_home).expanduser() / "plugins" / "agent-context-substrate" / "local_config.json").resolve(
        strict=False
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _same_path(left: Path, right: Path) -> bool:
    return str(left.resolve(strict=False)).casefold() == str(right.resolve(strict=False)).casefold()
