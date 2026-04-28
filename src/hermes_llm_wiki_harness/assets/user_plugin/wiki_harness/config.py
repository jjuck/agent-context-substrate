from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os

_DEFAULT_PROJECT_ROOT = Path("~/.hermes/llm-wiki-harness").expanduser()
_DEFAULT_WIKI_ROOT = Path("~/LLM Wiki").expanduser()
try:
    from local_config import PROJECT_ROOT as _LOCAL_PROJECT_ROOT, WIKI_ROOT as _LOCAL_WIKI_ROOT
except Exception:
    _LOCAL_PROJECT_ROOT = _DEFAULT_PROJECT_ROOT
    _LOCAL_WIKI_ROOT = _DEFAULT_WIKI_ROOT


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WikiHarnessPluginConfig:
    project_root: Path
    wiki_root: Path
    auto_finalize_enabled: bool = True
    min_message_count: int = 3
    allowed_sources: list[str] = field(default_factory=lambda: ["telegram", "cli"])
    skip_title_patterns: list[str] = field(default_factory=list)
    gateway_policy: str = "trigger-only"
    promotion_mode: str = "packet-only"


def load_plugin_config() -> WikiHarnessPluginConfig:
    return WikiHarnessPluginConfig(
        project_root=Path(os.environ.get("HERMES_WIKI_HARNESS_PROJECT_ROOT", str(_LOCAL_PROJECT_ROOT))).expanduser(),
        wiki_root=Path(os.environ.get("HERMES_WIKI_HARNESS_WIKI_ROOT", str(_LOCAL_WIKI_ROOT))).expanduser(),
        auto_finalize_enabled=_env_bool("HERMES_WIKI_HARNESS_AUTO_FINALIZE", True),
        min_message_count=_env_int("HERMES_WIKI_HARNESS_MIN_MESSAGE_COUNT", 3),
        allowed_sources=_env_list("HERMES_WIKI_HARNESS_ALLOWED_SOURCES", ["telegram", "cli"]),
        skip_title_patterns=_env_list("HERMES_WIKI_HARNESS_SKIP_TITLE_PATTERNS", []),
        gateway_policy=os.environ.get("HERMES_WIKI_HARNESS_GATEWAY_POLICY", "trigger-only").strip() or "trigger-only",
        promotion_mode=os.environ.get("HERMES_WIKI_HARNESS_PROMOTION_MODE", "packet-only").strip() or "packet-only",
    )
