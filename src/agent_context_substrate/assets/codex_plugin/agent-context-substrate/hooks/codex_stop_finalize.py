from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sqlite3
import subprocess
import sys


DEFAULT_TIMEOUT_SECONDS = 110
DEFAULT_WIKI_ROOT_TEMPLATE = "%USERPROFILE%\\Documents\\LLM Wiki"
WIKI_ROOT_ENV_KEYS = ("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", "WIKI_PATH")
_PERCENT_ENV_PATTERN = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_DOLLAR_ENV_PATTERN = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def main() -> int:
    try:
        payload = json.loads(_read_stdin_json_text() or "{}")
        output = run(payload)
    except Exception as exc:
        output = _failure(f"ACS Codex finalize hook failed: {exc}")
    print(json.dumps(output, ensure_ascii=False))
    return 0


def run(payload: dict[str, object]) -> dict[str, object]:
    plugin_root = _plugin_root()
    config = _load_config(plugin_root)
    if str(payload.get("hook_event_name") or "") != "Stop":
        _append_hook_event(config, payload=payload, status="skipped", detail="unsupported hook event")
        return {"continue": True}
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        _append_hook_event(config, payload=payload, status="skipped", detail="missing session_id")
        return {"continue": True}

    project_root_value = config.get("project_root")
    wiki_root, wiki_root_source, _ = _resolve_wiki_root(config)
    if not project_root_value:
        _append_hook_event(config, payload=payload, status="skipped", detail="missing project_root or wiki_root")
        return {"continue": True}
    if wiki_root is None:
        _append_hook_event(config, payload=payload, status="skipped", detail="no wiki root resolved")
        return {"continue": True}

    project_root = _resolve_non_strict(Path(str(project_root_value)).expanduser())
    cwd = _resolve_non_strict(Path(str(payload.get("cwd") or project_root)).expanduser())
    if not _is_relative_to(cwd, project_root):
        _append_hook_event(config, payload=payload, status="skipped", detail="cwd outside configured project_root")
        return {"continue": True}

    python_executable = str(config.get("python_executable") or sys.executable)
    command = [
        python_executable,
        "-m",
        "agent_context_substrate.cli",
        "codex-finalize",
        "--thread-id",
        session_id,
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

    try:
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            env=_subprocess_env(config, project_root=project_root),
            timeout=_timeout_seconds(config),
            check=False,
        )
    except Exception as exc:
        message = f"ACS Codex finalize hook failed: {exc}"
        _append_hook_event(config, payload=payload, status="failed", detail=message)
        return _failure(message)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        message = f"ACS Codex finalize hook failed: {detail}"
        _append_hook_event(config, payload=payload, status="failed", detail=message)
        return _failure(message)
    _mark_watcher_state_processed(config, session_id=session_id, project_root=project_root)
    _append_hook_event(
        config,
        payload=payload,
        status="finalized",
        detail=f"codex-finalize completed; wiki_root_source={wiki_root_source}",
    )
    return {"continue": True}


def _plugin_root() -> Path:
    configured = os.environ.get("PLUGIN_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1]


def _load_config(plugin_root: Path) -> dict[str, object]:
    try:
        config = json.loads((plugin_root / "local_config.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(config, dict):
        return config
    return {}


def _read_stdin_json_text() -> str:
    data = sys.stdin.buffer.read()
    if not data:
        return ""
    for encoding in ("utf-8-sig", "utf-8", sys.getdefaultencoding()):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _resolve_wiki_root(config: dict[str, object]) -> tuple[Path | None, str, str]:
    for key in WIKI_ROOT_ENV_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return _resolve_wiki_root_value(value, source=f"env:{key}")
    raw_value = str(config.get("wiki_root") or "").strip()
    if raw_value:
        source = str(config.get("wiki_root_source") or "").strip() or "legacy"
        return _resolve_wiki_root_value(raw_value, source=source)
    return _resolve_wiki_root_value(DEFAULT_WIKI_ROOT_TEMPLATE, source="default-template")


def _resolve_wiki_root_value(value: str, *, source: str) -> tuple[Path | None, str, str]:
    expanded = _expand_env_templates(value)
    if expanded is None:
        return None, source, value
    expanded = _expand_home(expanded)
    return _resolve_non_strict(Path(expanded).expanduser()), source, value


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


def _timeout_seconds(config: dict[str, object]) -> int:
    try:
        value = int(config.get("hook_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(1, value)


def _subprocess_env(config: dict[str, object], *, project_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    entries: list[str] = []
    configured_entries = config.get("python_path_entries")
    if isinstance(configured_entries, list):
        entries.extend(str(entry) for entry in configured_entries if entry)
    project_src = project_root / "src"
    if project_src.exists():
        entries.append(str(project_src))
    if entries:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join([*entries, existing] if existing else entries)
    return env


def _append_hook_event(
    config: dict[str, object],
    *,
    payload: dict[str, object],
    status: str,
    detail: str,
) -> None:
    try:
        project_root_value = config.get("project_root")
        if not project_root_value:
            return
        project_root = _resolve_non_strict(Path(str(project_root_value)).expanduser())
        configured_log_path = config.get("hook_event_log_path")
        if configured_log_path:
            log_path = _resolve_non_strict(Path(str(configured_log_path)).expanduser())
        else:
            log_path = project_root / "data" / "index" / "codex_hook_events.jsonl"
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "detail": detail,
            "hook_event_name": str(payload.get("hook_event_name") or ""),
            "session_id": str(payload.get("session_id") or ""),
            "turn_id": str(payload.get("turn_id") or ""),
            "cwd": str(payload.get("cwd") or ""),
        }
        wiki_root, wiki_root_source, wiki_root_raw = _resolve_wiki_root(config)
        record["wiki_root"] = wiki_root_raw
        record["wiki_root_source"] = wiki_root_source
        record["wiki_root_effective"] = str(wiki_root) if wiki_root is not None else ""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        return


def _mark_watcher_state_processed(config: dict[str, object], *, session_id: str, project_root: Path) -> None:
    try:
        rollout_path = _find_rollout_path(config, session_id=session_id)
        if rollout_path is None or not rollout_path.exists():
            return
        stat = rollout_path.stat()
        state_path = project_root / "data" / "index" / "codex_watcher_state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
        else:
            state = {}
        if not isinstance(state, dict):
            state = {}
        state[session_id] = {
            "thread_id": session_id,
            "rollout_path": str(rollout_path),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _find_rollout_path(config: dict[str, object], *, session_id: str) -> Path | None:
    codex_home_value = config.get("codex_home") or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
    codex_home = Path(str(codex_home_value)).expanduser()
    state_db = codex_home / "state_5.sqlite"
    if state_db.exists():
        try:
            uri = state_db.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                row = connection.execute("SELECT rollout_path FROM threads WHERE id = ?", (session_id,)).fetchone()
            if row is not None:
                path = Path(str(row[0])).expanduser()
                if not path.is_absolute():
                    path = codex_home / path
                return path
        except sqlite3.Error:
            pass
    matches = list((codex_home / "sessions").rglob(f"rollout-{session_id}.jsonl"))
    return matches[0] if matches else None


def _failure(message: str) -> dict[str, object]:
    return {
        "continue": True,
        "systemMessage": f"{message}. codex-watch remains available as fallback.",
    }


def _append_summary_args(command: list[str], config: dict[str, object]) -> None:
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


def _append_wiki_auto_args(command: list[str], config: dict[str, object]) -> None:
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


def _summary_cli_value(*, config_key: str, value: object) -> str | None:
    if value is None:
        return None
    if config_key in {"llm_redact", "llm_allow_code_snippets"}:
        return _config_on_off(value)
    text = str(value).strip()
    return text or None


def _config_on_off(value: object) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return "on"
    if text in {"0", "false", "no", "off"}:
        return "off"
    return text


def _config_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_non_strict(path: Path) -> Path:
    return path.resolve(strict=False)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
