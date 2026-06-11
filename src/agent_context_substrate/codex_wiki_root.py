from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os
import re


DEFAULT_CODEX_WIKI_ROOT_TEMPLATE = "%USERPROFILE%\\Documents\\LLM Wiki"
WIKI_ROOT_ENV_KEYS = ("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", "WIKI_PATH")
WIKI_ROOT_SOURCES = {"default-template", "explicit", "legacy"}

_PERCENT_ENV_PATTERN = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_DOLLAR_ENV_PATTERN = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


@dataclass(frozen=True)
class CodexWikiRootResolution:
    path: Path | None
    source: str
    raw_value: str


def default_codex_wiki_root_template() -> str:
    return DEFAULT_CODEX_WIKI_ROOT_TEMPLATE


def resolve_codex_wiki_root(
    config: Mapping[str, object] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> CodexWikiRootResolution:
    env_map = os.environ if env is None else env
    for key in WIKI_ROOT_ENV_KEYS:
        value = str(env_map.get(key) or "").strip()
        if value:
            return _resolve_wiki_root_value(value, source=f"env:{key}", env=env_map)

    config = config or {}
    config_value = str(config.get("wiki_root") or "").strip()
    if config_value:
        configured_source = str(config.get("wiki_root_source") or "").strip()
        source = configured_source if configured_source in WIKI_ROOT_SOURCES else "legacy"
        return _resolve_wiki_root_value(config_value, source=source, env=env_map)

    return _resolve_wiki_root_value(DEFAULT_CODEX_WIKI_ROOT_TEMPLATE, source="default-template", env=env_map)


def _resolve_wiki_root_value(
    value: str,
    *,
    source: str,
    env: Mapping[str, str],
) -> CodexWikiRootResolution:
    expanded = _expand_env_templates(value, env=env)
    if expanded is None:
        return CodexWikiRootResolution(path=None, source=source, raw_value=value)
    expanded = _expand_home(expanded, env=env)
    return CodexWikiRootResolution(
        path=Path(expanded).expanduser().resolve(strict=False),
        source=source,
        raw_value=value,
    )


def _expand_env_templates(value: str, *, env: Mapping[str, str]) -> str | None:
    missing = False

    def replace_percent(match: re.Match[str]) -> str:
        nonlocal missing
        replacement = _env_value(match.group(1), env=env)
        if replacement is None:
            missing = True
            return match.group(0)
        return replacement

    def replace_dollar(match: re.Match[str]) -> str:
        nonlocal missing
        name = match.group(1) or match.group(2)
        replacement = _env_value(str(name), env=env)
        if replacement is None:
            missing = True
            return match.group(0)
        return replacement

    expanded = _PERCENT_ENV_PATTERN.sub(replace_percent, value)
    expanded = _DOLLAR_ENV_PATTERN.sub(replace_dollar, expanded)
    return None if missing else expanded


def _env_value(name: str, *, env: Mapping[str, str]) -> str | None:
    value = env.get(name)
    if value:
        return str(value)
    if name == "USERPROFILE":
        return str(env.get("HOME") or Path.home())
    if name == "HOME":
        return str(env.get("USERPROFILE") or Path.home())
    return None


def _expand_home(value: str, *, env: Mapping[str, str]) -> str:
    if value == "~":
        return _env_value("HOME", env=env) or str(Path.home())
    if value.startswith("~/") or value.startswith("~\\"):
        home = _env_value("HOME", env=env) or str(Path.home())
        return str(Path(home) / value[2:])
    return value
