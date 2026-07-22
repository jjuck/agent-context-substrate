from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import os
import re
import subprocess
import sys

from .codex_wiki_root import resolve_codex_wiki_root


DEFAULT_HOOK_TIMEOUT_SECONDS = 110
_PERCENT_ENV_PATTERN = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_DOLLAR_ENV_PATTERN = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


@dataclass(frozen=True)
class CodexHookCommandRunnerResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class CodexStopFinalizeDecision:
    should_finalize: bool
    command: list[str] = field(default_factory=list)
    cwd: Path | None = None
    skip_reason: str = ""
    timeout_seconds: int = DEFAULT_HOOK_TIMEOUT_SECONDS
    thread_id: str = ""
    project_root: Path | None = None
    codex_home: Path | None = None


CodexHookCommandRunner = Callable[
    [list[str]],
    CodexHookCommandRunnerResult,
]


def build_codex_stop_finalize_decision(
    *,
    payload: dict[str, Any],
    plugin_root: Path | str,
    python_executable: str = sys.executable,
    config: dict[str, Any] | None = None,
) -> CodexStopFinalizeDecision:
    plugin_root_path = Path(plugin_root).expanduser()
    if str(payload.get("hook_event_name") or "") != "Stop":
        return CodexStopFinalizeDecision(should_finalize=False, skip_reason="unsupported hook event")

    thread_id = str(payload.get("session_id") or "").strip()
    if not thread_id:
        return CodexStopFinalizeDecision(should_finalize=False, skip_reason="missing session_id")

    config = dict(config) if config is not None else _load_config(plugin_root_path)
    if not config:
        return CodexStopFinalizeDecision(should_finalize=False, skip_reason="missing or invalid local_config.json")

    project_root_value = config.get("project_root")
    wiki_root_resolution = resolve_codex_wiki_root(config)
    if not project_root_value:
        return CodexStopFinalizeDecision(should_finalize=False, skip_reason="missing project_root or wiki_root")
    if wiki_root_resolution.path is None:
        return CodexStopFinalizeDecision(should_finalize=False, skip_reason="no wiki root resolved")

    project_root = _resolve_non_strict(Path(str(project_root_value)).expanduser())
    wiki_root = wiki_root_resolution.path
    cwd_value = payload.get("cwd") or project_root
    cwd = _resolve_non_strict(Path(str(cwd_value)).expanduser())
    if not _workspace_is_allowed(config, cwd=cwd, project_root=project_root):
        return CodexStopFinalizeDecision(
            should_finalize=False,
            skip_reason="cwd outside configured allowed_workspace_roots",
        )

    command = [
        python_executable,
        "-m",
        "agent_context_substrate.cli",
        "codex-finalize",
        "--thread-id",
        thread_id,
        "--project-root",
        str(project_root),
        "--wiki-root",
        str(wiki_root),
    ]
    codex_home = config.get("codex_home")
    if codex_home:
        command.extend(["--codex-home", str(_resolve_non_strict(Path(str(codex_home)).expanduser()))])
    _append_summary_args(command, config)
    _append_wiki_auto_args(command, config)

    return CodexStopFinalizeDecision(
        should_finalize=True,
        command=command,
        cwd=project_root,
        timeout_seconds=_hook_timeout_seconds(config),
        thread_id=thread_id,
        project_root=project_root,
        codex_home=_resolve_non_strict(Path(str(codex_home)).expanduser()) if codex_home else None,
    )


def run_codex_stop_finalize_hook(
    *,
    payload: dict[str, Any],
    plugin_root: Path | str,
    python_executable: str = sys.executable,
    runner: Callable[..., CodexHookCommandRunnerResult] | None = None,
) -> dict[str, Any]:
    plugin_root_path = Path(plugin_root).expanduser()
    config = _load_config(plugin_root_path)
    decision = build_codex_stop_finalize_decision(
        payload=payload,
        plugin_root=plugin_root_path,
        python_executable=python_executable,
        config=config,
    )
    if not decision.should_finalize:
        _append_hook_event(config, payload=payload, status="skipped", detail=decision.skip_reason)
        return {"continue": True}

    try:
        if runner is None:
            result = _run_command(
                decision.command,
                cwd=decision.cwd or Path.cwd(),
                timeout_seconds=decision.timeout_seconds,
                env=_subprocess_environment(config, project_root=decision.project_root or Path.cwd()),
            )
        else:
            result = runner(
                decision.command,
                cwd=decision.cwd or Path.cwd(),
                timeout_seconds=decision.timeout_seconds,
            )
    except Exception as exc:
        message = f"ACS Codex finalize hook failed: {exc}"
        _append_hook_event(config, payload=payload, status="failed", detail=message)
        return _non_blocking_failure(message)

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        message = f"ACS Codex finalize hook failed: {detail}"
        _append_hook_event(config, payload=payload, status="failed", detail=message)
        return _non_blocking_failure(message)
    _mark_watcher_state_processed(decision)
    wiki_root_resolution = resolve_codex_wiki_root(config)
    _append_hook_event(
        config,
        payload=payload,
        status="finalized",
        detail=f"codex-finalize completed; wiki_root_source={wiki_root_resolution.source}",
    )
    return {"continue": True}


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str],
) -> CodexHookCommandRunnerResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout_seconds,
        check=False,
    )
    return CodexHookCommandRunnerResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _load_config(plugin_root: Path) -> dict[str, Any]:
    try:
        config = json.loads((plugin_root / "local_config.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return config if isinstance(config, dict) else {}


def _subprocess_environment(config: dict[str, Any], *, project_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    entries: list[str] = []
    configured_entries = config.get("python_path_entries")
    if isinstance(configured_entries, list):
        entries.extend(str(entry) for entry in configured_entries if str(entry).strip())
    project_src = project_root / "src"
    if project_src.exists():
        entries.append(str(project_src))
    if entries:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join([*entries, existing] if existing else entries)
    return env


def _append_hook_event(
    config: dict[str, Any],
    *,
    payload: dict[str, Any],
    status: str,
    detail: str,
) -> None:
    try:
        project_root_value = config.get("project_root")
        if not project_root_value:
            return
        project_root = _resolve_non_strict(Path(str(project_root_value)).expanduser())
        configured_log_path = config.get("hook_event_log_path")
        log_path = (
            _resolve_non_strict(Path(str(configured_log_path)).expanduser())
            if configured_log_path
            else project_root / "data" / "index" / "codex_hook_events.jsonl"
        )
        wiki_root_resolution = resolve_codex_wiki_root(config)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "detail": detail,
            "hook_event_name": str(payload.get("hook_event_name") or ""),
            "session_id": str(payload.get("session_id") or ""),
            "turn_id": str(payload.get("turn_id") or ""),
            "cwd": str(payload.get("cwd") or ""),
            "wiki_root": wiki_root_resolution.raw_value,
            "wiki_root_source": wiki_root_resolution.source,
            "wiki_root_effective": str(wiki_root_resolution.path or ""),
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        return


def _non_blocking_failure(message: str) -> dict[str, Any]:
    return {
        "continue": True,
        "systemMessage": f"{message}. codex-watch remains available as fallback.",
    }


def _append_summary_args(command: list[str], config: dict[str, Any]) -> None:
    summary_mode = str(config.get("summary_mode") or "").strip().lower()
    if not summary_mode or summary_mode in {"off", "none", "disabled"}:
        return
    command.extend(["--summary-mode", summary_mode])
    for config_key, flag in [
        ("summarizer_command", "--summarizer-command"),
        ("summary_model", "--summary-model"),
        ("summary_budget", "--summary-budget"),
        ("codex_cli_command", "--codex-cli-command"),
        ("codex_timeout_seconds", "--codex-timeout-seconds"),
        ("llm_redact", "--llm-redact"),
        ("llm_max_input_chars", "--llm-max-input-chars"),
        ("llm_allow_code_snippets", "--llm-allow-code-snippets"),
        ("llm_path_policy", "--llm-path-policy"),
    ]:
        value = _summary_cli_value(config_key=config_key, value=config.get(config_key))
        if value is not None:
            command.extend([flag, value])
    if _config_bool(config.get("summary_cache")):
        command.extend(["--summary-cache", "on"])


def _append_wiki_auto_args(command: list[str], config: dict[str, Any]) -> None:
    wiki_auto_mode = str(config.get("wiki_auto_mode") or "").strip().lower()
    if not wiki_auto_mode or wiki_auto_mode in {"off", "none", "disabled"}:
        return
    command.extend(["--wiki-auto-mode", wiki_auto_mode])
    for config_key, flag in [
        ("wiki_write_judge_mode", "--wiki-write-judge-mode"),
        ("wiki_auto_min_score", "--wiki-auto-min-score"),
    ]:
        value = _summary_cli_value(config_key=config_key, value=config.get(config_key))
        if value is not None:
            command.extend([flag, value])


def _summary_cli_value(*, config_key: str, value: Any) -> str | None:
    if value is None:
        return None
    if config_key in {"llm_redact", "llm_allow_code_snippets"}:
        return _config_on_off(value)
    text = str(value).strip()
    return text or None


def _config_on_off(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return "on"
    if text in {"0", "false", "no", "off"}:
        return "off"
    return text


def _config_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _hook_timeout_seconds(config: dict[str, Any]) -> int:
    try:
        value = int(config.get("hook_timeout_seconds", DEFAULT_HOOK_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_HOOK_TIMEOUT_SECONDS
    return max(1, value)


def _allowed_workspace_roots(config: dict[str, Any], *, project_root: Path) -> list[Path]:
    configured = config.get("allowed_workspace_roots")
    values: list[str] = []
    if isinstance(configured, list):
        values.extend(str(value).strip() for value in configured if str(value).strip())
    elif isinstance(configured, str) and configured.strip():
        values.append(configured.strip())
    roots = [project_root]
    for value in values:
        resolved = _resolve_template_path(value)
        if resolved is not None:
            roots.append(resolved)
    return _dedupe_paths(roots)


def _workspace_is_allowed(config: dict[str, Any], *, cwd: Path, project_root: Path) -> bool:
    scope = str(config.get("workspace_scope") or "").strip().lower()
    configured = config.get("allowed_workspace_roots")
    has_explicit_roots = (
        any(str(value).strip() for value in configured)
        if isinstance(configured, list)
        else isinstance(configured, str) and bool(configured.strip())
    )
    if scope == "all" or (scope != "restricted" and not has_explicit_roots):
        return True
    return any(_is_path_relative_to(cwd, root) for root in _allowed_workspace_roots(config, project_root=project_root))


def _resolve_template_path(value: str) -> Path | None:
    expanded = _expand_env_templates(value)
    if expanded is None:
        return None
    expanded = _expand_home(expanded)
    return _resolve_non_strict(Path(expanded).expanduser())


def _expand_env_templates(value: str) -> str | None:
    missing = False

    def replace_percent(match: re.Match[str]) -> str:
        nonlocal missing
        replacement = _env_value(match.group(1))
        if replacement is None:
            missing = True
            return match.group(0)
        return replacement

    def replace_dollar(match: re.Match[str]) -> str:
        nonlocal missing
        name = match.group(1) or match.group(2)
        replacement = _env_value(str(name))
        if replacement is None:
            missing = True
            return match.group(0)
        return replacement

    expanded = _PERCENT_ENV_PATTERN.sub(replace_percent, value)
    expanded = _DOLLAR_ENV_PATTERN.sub(replace_dollar, expanded)
    return None if missing else expanded


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if name == "USERPROFILE":
        return os.environ.get("HOME") or str(Path.home())
    if name == "HOME":
        return os.environ.get("USERPROFILE") or str(Path.home())
    return None


def _expand_home(value: str) -> str:
    if value == "~":
        return _env_value("HOME") or str(Path.home())
    if value.startswith("~/") or value.startswith("~\\"):
        return str(Path(_env_value("HOME") or str(Path.home())) / value[2:])
    return value


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _mark_watcher_state_processed(decision: CodexStopFinalizeDecision) -> None:
    if decision.project_root is None or not decision.thread_id:
        return
    try:
        from .codex_integration import CodexWatcherState, default_codex_watcher_state_path
        from .codex_source import discover_codex_threads

        state = CodexWatcherState(default_codex_watcher_state_path(decision.project_root))
        for thread in discover_codex_threads(codex_home=decision.codex_home, include_archived=True):
            if thread.thread_id == decision.thread_id:
                state.mark_processed(thread, fingerprint=thread.fingerprint)
                return
    except Exception:
        return


def _resolve_non_strict(path: Path) -> Path:
    return path.resolve(strict=False)


def _is_path_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
